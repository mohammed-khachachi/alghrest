import { useLanguage, languageDirection, tr } from "../../i18n";
import { useEffect, useRef, useState } from 'react';
import { advisoryApi } from '@/lib/advisoryApi';
import type { TerminalResearch } from '@/lib/terminalResearch';
import { priorSnapshot, researchHistory, researchSnapshot, researchWatchlist, type ResearchSnapshot, type ResearchWatchEntry } from '@/lib/researchJournal';
import { sourceTime } from '@/lib/terminalDataStatus';
import { ResearchAlerts } from './ResearchAlerts';
import { ResearchComparison } from './ResearchComparison';
import { TerminalResearchSummary } from './TerminalResearchSummary';
import { TerminalDataStatus } from './TerminalDataStatus';
import { WatchlistOverview } from './WatchlistOverview';
import { ResearchBriefExport } from './ResearchBriefExport';
import { ResearchBackup } from './ResearchBackup';

export function ResearchJournalPanel({ symbol, currentReport, onSelect }: {
  symbol: string; currentReport: TerminalResearch | null; onSelect: (symbol: string) => void;
}) {
  useLanguage();
  const [watches, setWatches] = useState<ResearchWatchEntry[] | null>(null);
  const [history, setHistory] = useState<{ symbol: string; records: ResearchSnapshot[] } | null>(null);
  const [selected, setSelected] = useState('live');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const active = useRef(symbol); active.current = symbol;
  const revision = useRef(0);
  const watchRevision = useRef(0);
  const pending = useRef(new Map<string, string>());
  const records = history?.symbol === symbol ? history.records : [];
  const watched = watches?.some(w => w.symbol === symbol) ?? false;
  const snapshot = records.find(r => r.id === selected) ?? null;
  const current = snapshot?.report ?? (selected === 'live' && currentReport?.symbol === symbol ? currentReport : null);
  const previous = current ? priorSnapshot(records, current) : null;

  async function loadWatches() {
    const request = ++watchRevision.current;
    const value = researchWatchlist(await advisoryApi<unknown>('research-watchlist'));
    if (request === watchRevision.current) setWatches(value);
  }
  async function loadHistory(selectedSymbol: string) {
    const request = ++revision.current;
    const value = researchHistory(await advisoryApi<unknown>(`research-snapshots/${encodeURIComponent(selectedSymbol)}`), selectedSymbol);
    if (request === revision.current && active.current === selectedSymbol) setHistory({symbol: selectedSymbol, records: value});
  }
  useEffect(() => {
    void loadWatches().catch(() => setError('تعذر تحميل قائمة المتابعة. أعد تحميل السجل.'));
    return () => { watchRevision.current++; };
  }, []);
  useEffect(() => {
    setHistory(null); setSelected('live'); setError(''); setMessage('');
    if (symbol) void loadHistory(symbol).catch(() => {
      if (active.current === symbol) setError('تعذر تحميل اللقطات؛ لا نعرض مقارنة ناقصة. أعد تحميل السجل.');
    });
    return () => { revision.current++; };
  }, [symbol]);
  function failure(reason: unknown) {
    return reason instanceof Error ? reason.message : 'تعذر إكمال العملية.';
  }
  async function toggle() {
    setBusy(true); setError(''); setMessage(''); watchRevision.current++;
    try {
      setWatches(researchWatchlist(await advisoryApi<unknown>(`research-watchlist/${encodeURIComponent(symbol)}`, {
        method: 'PUT', body: JSON.stringify({watched: !watched}),
      })));
      if (active.current === symbol) setMessage(watched ? 'أزيل الرمز من المتابعة؛ لقطاته السابقة محفوظة.' : 'أُضيف الرمز إلى المتابعة.');
    } catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }
  async function capture() {
    setBusy(true); setError(''); setMessage('');
    const id = pending.current.get(symbol) ?? crypto.randomUUID().replaceAll('-', '');
    pending.current.set(symbol, id);
    try {
      const saved = researchSnapshot(await advisoryApi<unknown>(`research-snapshots/${encodeURIComponent(symbol)}`, {
        method: 'POST', body: JSON.stringify({id}),
      }), symbol);
      pending.current.delete(symbol);
      if (active.current === symbol) {
        revision.current++; // Do not let an older list response hide the completed save.
        setHistory(existing => ({symbol, records: [saved, ...(existing?.symbol === symbol ? existing.records : []).filter(r => r.id !== saved.id)]
          .sort((a,b) => Date.parse(b.saved_at) - Date.parse(a.saved_at))}));
        setSelected(saved.id); setMessage('حُفظت اللقطة. أنت تعرض الآن سجلًا تاريخيًا مؤرخًا.');
      }
      try { await loadWatches(); }
      catch { if (active.current === symbol) setError('حُفظت اللقطة، لكن تعذر تحديث أعداد القائمة. أعد تحميل السجل.'); }
    } catch (reason) {
      if (active.current === symbol) setError(`${failure(reason)} أعد المحاولة بنفس الزر؛ الطلب المكرر لا ينشئ لقطة إضافية.`);
    } finally { setBusy(false); }
  }
  async function reload() {
    setBusy(true); setError('');
    try { await Promise.all([loadWatches(), symbol ? loadHistory(symbol) : Promise.resolve()]); }
    catch (reason) { setError(failure(reason)); }
    finally { setBusy(false); }
  }
  return <section dir={languageDirection()} aria-label={tr("قائمة متابعة البحث واللقطات")} className="space-y-4 rounded-xl border border-border bg-bg-surface p-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-lg font-semibold">{tr("متابعة البحث واللقطات المحفوظة")}</h2><button disabled={busy} onClick={() => void reload()} className="rounded border border-white/15 px-3 py-2 text-sm disabled:opacity-40">{tr("إعادة تحميل السجل")}</button></div>
    <p className="text-xs text-white/50">{tr("محفوظة في قاعدة ALGHREST المحلية؛ تبقى بعد إغلاق المتصفح. حتى 50 رمزًا و100 لقطة لكل رمز، دون حذف تلقائي. حفظ اللقطة يجلب قراءة جديدة وقد تكون بياناتها ناقصة أو متأخرة.")}</p>
    <ResearchBriefExport enabled={!!watches?.length} />
    <ResearchBackup onRestored={reload} />
    {watches && <WatchlistOverview watches={watches} selectedSymbol={symbol} onSelect={onSelect} />}
    {watches?.length === 0 && <p className="text-sm text-white/50">{tr("القائمة فارغة؛ اختر رمزًا ثم أضفه للمتابعة.")}</p>}
    {symbol && <div className="flex flex-wrap gap-3">
      <button disabled={busy || watches === null} onClick={() => void toggle()} className="rounded border border-indigo-400/40 px-3 py-2 text-sm disabled:opacity-40">{tr(watched ? `إزالة ${symbol} من المتابعة` : `إضافة ${symbol} للمتابعة`)}</button>
      <button disabled={busy || !watched || history?.symbol !== symbol} onClick={() => void capture()} className="rounded bg-violet-600 px-3 py-2 text-sm disabled:opacity-40">{tr(busy ? 'جارٍ تنفيذ الطلب…' : pending.current.has(symbol) ? 'إعادة محاولة حفظ اللقطة' : `جلب وحفظ لقطة ${symbol}`)}</button>
      <label className="flex items-center gap-2 text-sm">{tr("القراءة المعروضة")}<select aria-label={tr("اختيار لقطة البحث")} value={selected} onChange={event => setSelected(event.target.value)} className="max-w-full rounded border border-white/15 bg-bg-dark px-2 py-2">
        <option value="live">{tr("القراءة الحالية")}</option>{records.map(r => <option key={r.id} value={r.id}>{tr("لقطة ")}{tr(sourceTime(r.saved_at))}</option>)}
      </select></label>
    </div>}
    {error && <p role="alert" className="text-sm text-red-300">{tr(error)}</p>}
    {message && <p role="status" className="text-sm text-indigo-200">{tr(message)}</p>}
    {snapshot && <div className="space-y-4 border-t border-white/10 pt-4">
      <p className="rounded bg-amber-500/10 p-3 text-sm text-amber-200">{tr("لقطة تاريخية محفوظة · ")}{snapshot.report.symbol}{tr(" · حُفظت ")}{tr(sourceTime(snapshot.saved_at))}{tr(". ليست قراءة مباشرة الآن.")}</p>
      {snapshot.restored_from_backup && <p className="text-xs text-amber-200 break-all">{tr("لقطة مستعادة من ملف محلي؛ بصمة الملف للتحقق من الاتساق وليست توقيعًا من مزوّد البيانات. SHA-256: ")}{tr(snapshot.restored_from_backup)}</p>}
      <TerminalResearchSummary report={snapshot.report} />
      <details><summary className="cursor-pointer text-sm text-indigo-200">{tr("مصادر اللقطة وحالة البيانات وقت الحفظ")}</summary><div className="mt-3"><TerminalDataStatus report={snapshot.report} now={Date.parse(snapshot.saved_at)} /></div></details>
    </div>}
    {current && history?.symbol === symbol ? <><ResearchAlerts current={current} previous={previous} historical={!!snapshot} importedCurrent={!!snapshot?.restored_from_backup} /><ResearchComparison current={current} previous={previous} /></>
      : symbol && <p className="text-sm text-white/50">{tr("اختر لقطة محفوظة، أو حدّث التحليل لعرض المقارنة مع قراءة حالية صالحة.")}</p>}
  </section>;
}
