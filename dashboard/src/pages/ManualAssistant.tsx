import { useCallback, useEffect, useRef, useState } from 'react';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts';
import { RefreshCw, BookOpen, ShieldCheck, Upload } from 'lucide-react';

import { advisoryApi as api } from '../lib/advisoryApi';
import { personalRiskRequest, validatePersonalRisk, personalRiskCurrent, type UserRiskResult } from '../lib/userRisk';
import { UserPolicyPanel } from '../components/advisory/UserPolicyPanel';
import { NewsEventsPanel } from '../components/advisory/NewsEventsPanel';
import { BriefingPanel } from '../components/advisory/BriefingPanel';
import { ObservationPanel } from '../components/advisory/ObservationPanel';
import { EvaluationPanel, type Evaluation } from '../components/advisory/EvaluationPanel';
import { OpenTerminalContextPanel } from '../components/advisory/OpenTerminalContextPanel';

type Instrument = { id: string; name: string; symbol: string; currency: string; market: string; point_value: string; tick_size: string; source_required: string | null };
type Candle = { close_time: string; close: string };
type Scenario = { direction: string; condition: string; trigger: string; invalidation: string; targets: string[]; rationale: string };
type Research = {
  id: string; instrument: Instrument; interval: string; generated_at: string; status: string;
  market: { source: string; fetched_at: string; data_mode: string; contract: string | null; candles: Candle[]; derivatives: Record<string, string> } | null;
  observations: string[]; indicators: Record<string, string>; scenarios: Scenario[];
  news: { id: string; title: string; url: string; source: string; published_at: string; category: string }[];
  agent_context: { id: string; topic: string; timestamp: string; summary: string }[];
  data_health?: { state: 'HEALTHY' | 'UNHEALTHY' | 'UNKNOWN'; reasons: string[]; policy_version: string; scope: string; trade_permitted: false };
  event_risk?: { state: 'CLEAR' | 'BLOCKED' | 'UNKNOWN'; reasons: string[]; guard_version: string; trade_permitted: false };
};
type Watchlist = { instruments: string[]; interests: string[] };
type Selection = {
  id: string; generated_at: string; interval: string; mode: string; scope: string;
  primary: string | null; backup: string | null; ranked: string[];
  trade_permitted: boolean; execution_enabled: boolean; simultaneous_use_permitted: boolean;
  reasons: string[];
  assessments: { instrument_id: string; contract: string | null; eligible: boolean; reasons: string[]; data_health: { state: string }; event_risk: { state: string } }[];
};
const panel = 'rounded-xl border border-white/10 bg-bg-surface p-5';
const input = 'rounded-lg border border-white/15 bg-bg-dark px-3 py-2 text-sm w-full';
const statusLabel: Record<string, string> = { ready: 'بيانات كافية للبحث الفني', unavailable: 'مصدر الأسعار غير متاح', stale: 'بيانات قديمة / جلسة مغلقة', insufficient: 'بيانات غير كافية' };
const directionLabel: Record<string, string> = { bullish: 'سيناريو الصعود', bearish: 'سيناريو الهبوط', range: 'سيناريو النطاق الجانبي' };
const indicatorLabel: Record<string, string> = { last_close: 'آخر إغلاق', ema20: 'المتوسط الأسي 20', ema50: 'المتوسط الأسي 50', atr14: 'متوسط النطاق 14', rsi14_simple: 'مؤشر القوة النسبية 14', support20: 'دعم آخر 20 شمعة', resistance20: 'مقاومة آخر 20 شمعة', rolling_vwap96: 'السعر المرجح بالحجم / 96 شمعة', bias: 'السياق الفني' };
const date = (v: string) => new Date(v).toLocaleString('ar-MA', { timeZoneName: 'short' });
const number = (v: string) => Number.isFinite(Number(v)) ? Number(v).toLocaleString('en-US', { maximumFractionDigits: 8 }) : v;

export function ManualAssistant({ linkedInstrument, onInstrumentChange }: { linkedInstrument?: string; onInstrumentChange?: (id: string) => void } = {}) {
  const [catalog, setCatalog] = useState<Instrument[]>([]);
  const [watchlist, setWatchlist] = useState<Watchlist>({ instruments: [], interests: [] });
  const [interests, setInterests] = useState('');
  const [selected, setSelected] = useState(linkedInstrument ?? 'MNQ');
  const [interval, setIntervalValue] = useState('15m');
  const [report, setReport] = useState<Research | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [comparing, setComparing] = useState(false);
  const selectionRevision = useRef(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [online, setOnline] = useState(false);
  const [history, setHistory] = useState<{ id: string; created: string; instrument: string }[]>([]);
  const [capital, setCapital] = useState('');
  const [risk, setRisk] = useState('0.5');
  const [entry, setEntry] = useState('');
  const [stop, setStop] = useState('');
  const [fees, setFees] = useState('');
  const [slippage, setSlippage] = useState('');
  const [source, setSource] = useState('');
  const [contract, setContract] = useState('');
  const [evaluationDirty, setEvaluationDirty] = useState(false);
  const worksheetRevision = useRef(0);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [riskContract, setRiskContract] = useState('');
  const [costReference, setCostReference] = useState('');
  const [costSource, setCostSource] = useState<'user_declared' | 'synthetic'>('user_declared');
  const [costsReviewed, setCostsReviewed] = useState(false);
  const [personalResult, setPersonalResult] = useState<UserRiskResult | null>(null);
  const [riskNow, setRiskNow] = useState(Date.now());
  const [buffer, setBuffer] = useState('');
  const riskKey = JSON.stringify([evaluation, evaluationDirty, selected, riskContract, risk, entry, stop, fees, slippage, buffer, costReference, costSource, costsReviewed]);
  const riskKeyRef = useRef(riskKey); riskKeyRef.current = riskKey;
  const [resultKey, setResultKey] = useState('');
  const evaluationChanged = useCallback((v: Evaluation | null) => { worksheetRevision.current += 1; setEvaluation(v); setEvaluationDirty(false); setPersonalResult(null); if (v) setCapital(v.balance); }, []);
  const evaluationDirtyChanged = useCallback(() => { worksheetRevision.current += 1; setEvaluationDirty(true); setPersonalResult(null); }, []);
  useEffect(() => { worksheetRevision.current += 1; }, [selected, capital, risk, entry, stop, fees, slippage, riskContract, buffer, costReference, costSource, costsReviewed]);
  useEffect(() => { worksheetRevision.current += 1; setPersonalResult(null); }, [riskKey]);
  useEffect(() => { const timer = window.setInterval(() => setRiskNow(Date.now()), 500); return () => window.clearInterval(timer); }, []);
  useEffect(() => { if (personalResult?.state === 'CALCULATED' && !personalRiskCurrent(personalResult, riskNow)) { setPersonalResult(null); setError('انتهت صلاحية الحساب أو نافذة الدخول؛ حدّث الملاحظة وأعد الحساب.'); } }, [personalResult, riskNow]);
  const visiblePersonal = resultKey === riskKey && !evaluationDirty && personalResult && (personalResult.state !== 'CALCULATED' || personalRiskCurrent(personalResult, riskNow)) ? personalResult : null;
  useEffect(() => { setCostsReviewed(false); }, [fees, slippage, buffer, costReference, costSource]);
  const current = catalog.find(i => i.id === selected);
  const analysisAllowed = report?.data_health?.state === 'HEALTHY';
  const eventsClear = report?.event_risk?.state === 'CLEAR';
  const scenariosAllowed = analysisAllowed && eventsClear;
  const selectionValid = selection?.scope === 'research_nomination' && selection.trade_permitted === false && selection.execution_enabled === false && selection.simultaneous_use_permitted === false && selection.interval === interval;
  const nominated = (root: string | null | undefined) => selectionValid && root && selection?.assessments.some(row => row.instrument_id === root && row.eligible && row.reasons.length === 0 && row.data_health.state === 'HEALTHY' && row.event_risk.state === 'CLEAR') ? root : '—';
  useEffect(() => { selectionRevision.current += 1; setSelection(null); }, [interval]);

  useEffect(() => {
    let alive = true;
    Promise.all([api<Instrument[]>('catalog'), api<Watchlist>('watchlist'), api<{ id: string; created: string; instrument: string }[]>('history')])
      .then(([items, list, saved]) => { if (alive) { setCatalog(items.sort((a, b) => Number(b.market === 'cme_future') - Number(a.market === 'cme_future'))); setWatchlist(list); setInterests(list.interests.join(', ')); setHistory(saved); setOnline(true); } })
      .catch(() => { if (alive) setError('خدمة المساعد غير متصلة. شغّل python -m api.advisor ثم أعد تحميل الصفحة؛ التداول الأساسي مستقل عنها.'); });
    return () => { alive = false; };
  }, []);

  async function refresh() {
    setBusy(true); setError(''); setNotice(''); setReport(null);
    try {
      const value = await api<Research>(`report/${selected}?interval=${interval}`);
      setReport(value); setEntry(value.data_health?.state === 'HEALTHY' ? value.indicators['last_close'] ?? '' : '');
      setHistory(await api('history'));
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function compareMarkets() {
    const revision = ++selectionRevision.current;
    setComparing(true); setSelection(null); setError('');
    try {
      const value = await api<Selection>(`market-selection?interval=${interval}`);
      if (selectionRevision.current === revision) setSelection(value);
    } catch (e) { if (selectionRevision.current === revision) setError(String(e)); }
    finally { setComparing(false); }
  }
  async function saveWatchlist() {
    try {
      const value = { ...watchlist, interests: interests.split(',').map(x => x.trim()).filter(Boolean) };
      setWatchlist(await api('watchlist', { method: 'PUT', body: JSON.stringify(value) })); setNotice('حُفظت قائمة المتابعة والاهتمامات.');
    } catch (e) { setError(String(e)); }
  }
  async function calculate() {
    setError(''); setPersonalResult(null);
    const revision = ++worksheetRevision.current; const capturedKey = riskKey;
    try {
      if (!evaluation || evaluationDirty || !evaluation.account_revision) throw new Error('اختر سجلًا شخصيًا واحفظ ملاحظة الحساب أولًا.');
      const payload = personalRiskRequest({ instrument_id: selected, contract: riskContract, risk_percent: risk,
        entry, stop, fees_per_unit: fees, slippage_points: slippage, safety_buffer: buffer,
        cost_source: costSource, cost_reference: costReference, costs_reviewed: costsReviewed,
        expected_account_revision: evaluation.account_revision });
      const raw = await api<unknown>(`evaluations/${evaluation.profile.id}/personal-plan`, { method: 'POST', body: JSON.stringify(payload) });
      if (worksheetRevision.current !== revision || riskKeyRef.current !== capturedKey) return;
      const value = validatePersonalRisk(raw, { ...evaluation, account_revision: evaluation.account_revision }, payload, Date.now());
      setRiskNow(Date.now()); setResultKey(capturedKey); setPersonalResult(value);
    } catch (e) { if (worksheetRevision.current === revision && riskKeyRef.current === capturedKey) setError(String(e)); }
  }
  async function upload(file: File) {
    setError('');
    try {
      if (file.size > 400000) throw new Error('الملف يتجاوز 400 KB');
      const text = await file.text();
      if (file.name.endsWith('.csv')) {
        await api('import-csv', { method: 'POST', body: JSON.stringify({ instrument_id: selected, interval, source, contract: contract || null, csv: text }) });
      } else { await api('import', { method: 'POST', body: text }); }
      setReport(null); setNotice('حُفظت البيانات. اضغط تحديث التحليل لبناء تقرير جديد.');
    } catch (e) { setError(String(e)); }
  }
  function choose(id: string, notify = true) { setSelected(id); setReport(null); setEntry(''); setStop(''); if (notify) onInstrumentChange?.(id); }
  useEffect(() => { if (linkedInstrument && linkedInstrument !== selected) choose(linkedInstrument, false); }, [linkedInstrument]);

  return <div dir="rtl" className="space-y-5 max-w-7xl mx-auto pb-8">
    <header className="flex flex-wrap justify-between gap-4 items-center">
      <div><div className="flex gap-2 items-center text-indigo-300"><BookOpen size={22} /><span className="text-xs tracking-wide">ALGHREST · MANUAL RESEARCH</span></div>
        <h1 className="text-2xl font-bold mt-2">مساعد الأسواق والتداول اليدوي</h1><p className="text-white/50 mt-2">MES / MYM / MNQ / MGC · مقارنة الأدلة وسياق السوق ودفتر التقييم.</p></div>
      <span className={`flex items-center gap-2 text-sm rounded-full px-4 py-2 ${online ? 'bg-emerald-500/10 text-emerald-300' : 'bg-amber-500/10 text-amber-300'}`}><ShieldCheck size={16} />{online ? 'خدمة مستقلة · بلا تنفيذ أوامر' : 'بانتظار اتصال خدمة المساعد'}</span>
    </header>
    {error && <div role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-200">{error}</div>}
    {notice && <div role="status" className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-emerald-200">{notice}</div>}
    <section className={panel} aria-label="مقارنة الأسواق">
      <div className="flex flex-wrap justify-between items-center gap-3"><h2 className="text-lg font-semibold">السوق الأساسي والبديل</h2><button className="rounded-lg bg-indigo-600 px-4 py-2 disabled:opacity-40" disabled={!online || comparing || busy} onClick={() => void compareMarkets()}>{comparing ? 'مقارنة الأدلة…' : 'مقارنة الأسواق'}</button></div>
      <p className="text-sm text-white/50 mt-3">ترشيح للبحث فقط. يتطلب بيانات سليمة وأحداثًا واضحة ودليل عائد موجب بعد التكاليف ومحاكاة موثقة. منتجات مؤشرات الأسهم تعرض مترابط؛ البديل لا يعني فتح مركز إضافي.</p>
      {!selection && <p className="text-sm text-white/40 mt-3">لا يوجد ترشيح قبل مقارنة الأدلة. لن تُفترض المقاييس المفقودة.</p>}
      {selection && <>
        <p className="text-amber-200 mt-3">{nominated(selection.primary) === '—' ? 'NO TRADE · لا يوجد سوق مؤهل للترشيح' : 'ترشيح بحثي فقط · لا يمنح إذن دخول أو تنفيذ'}</p>
        <div className="grid grid-cols-2 gap-3 mt-3"><div className="rounded-lg bg-white/[.025] p-3">PRIMARY · الأساسي <strong dir="ltr">{nominated(selection.primary)}</strong></div><div className="rounded-lg bg-white/[.025] p-3">BACKUP · البديل <strong dir="ltr">{nominated(selection.backup)}</strong></div></div>
        <p className="text-xs text-white/40 mt-3">وقت المقارنة: {date(selection.generated_at)} · {selection.mode === 'replay' ? 'إعادة تشغيل تاريخية' : 'أدلة حالية'} · {selection.interval}</p>
        <div className="mt-3 overflow-x-auto"><table className="w-full text-sm [&_th]:px-3 [&_td]:px-3"><thead className="text-white/50"><tr><th className="text-start py-2">السوق</th><th className="text-start">البيانات</th><th className="text-start">الأحداث</th><th className="text-start">الترشيح</th></tr></thead><tbody>{selection.assessments.map(row => <tr key={row.instrument_id} className="border-t border-white/10"><td className="py-3 text-right whitespace-nowrap" dir="ltr">{row.instrument_id}</td><td>{row.data_health.state}</td><td>{row.event_risk.state}</td><td>{selectionValid && row.eligible ? 'مؤهل للبحث' : 'محجوب'}{row.reasons.length > 0 && <details className="text-xs text-white/50 mt-1"><summary className="cursor-pointer">أسباب الحجب</summary><p className="mt-2 break-words" dir="ltr">{row.reasons.join(' · ')}</p></details>}</td></tr>)}</tbody></table></div>
      </>}
    </section>
    <section className={panel}>
      <div className="flex flex-wrap gap-3 items-end">
        <label className="flex-1 min-w-48">الأداة<select className={`${input} mt-2`} value={selected} onChange={e => choose(e.target.value)} disabled={busy}>{catalog.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select></label>
        <label>الإطار الزمني<select className={`${input} mt-2`} value={interval} disabled={busy} onChange={e => { setIntervalValue(e.target.value); setReport(null); }}>{['5m', '15m', '1h', '4h', '1d'].map(v => <option key={v}>{v}</option>)}</select></label>
        <button className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 rounded-lg px-5 py-2.5 flex gap-2" onClick={() => void refresh()} disabled={!online || busy}><RefreshCw size={18} className={busy ? 'animate-spin' : ''} />{busy ? 'جمع الأدلة…' : 'تحديث التحليل'}</button>
      </div>
      <details className="mt-4 text-sm text-white/60"><summary className="cursor-pointer">قائمة المتابعة والاهتمامات</summary>
        <div className="flex gap-4 flex-wrap my-3">{catalog.map(i => <label key={i.id} className="flex gap-2"><input type="checkbox" checked={watchlist.instruments.includes(i.id)} onChange={e => setWatchlist({ ...watchlist, instruments: e.target.checked ? [...watchlist.instruments, i.id] : watchlist.instruments.filter(s => s !== i.id) })} />{i.id}</label>)}</div>
        <label>كلمات اهتمام مفصولة بفواصل<input className={`${input} my-2`} value={interests} onChange={e => setInterests(e.target.value)} /></label><button className="text-indigo-300" onClick={() => void saveWatchlist()}>حفظ المتابعة</button>
      </details>
      {current?.source_required && <details open className="mt-4 text-sm border-t border-white/10 pt-4"><summary className="cursor-pointer text-amber-200">تحتاج هذه الأداة مصدر أسعارك أو ملف شموع موثق</summary>
        <p className="text-white/50 my-3">يمكن استيراد CSV بأعمدة time, open, high, low, close, volume. يجب أن يتضمن الوقت منطقة زمنية أو يكون Unix بالثواني. اختر إطار الملف نفسه، واستخدم رمز العقد المؤرخ للفيوتشر.</p>
        <div className="grid md:grid-cols-3 gap-3"><label>رابط مصدر البيانات<input className={`${input} mt-1`} value={source} onChange={e => setSource(e.target.value)} /></label><label>العقد المؤرخ، إن وجد<input className={`${input} mt-1`} value={contract} onChange={e => setContract(e.target.value)} placeholder={selected === "MNQ" ? "MNQZ26" : "NQZ26"} /></label><label className="cursor-pointer flex items-center gap-2 text-indigo-300"><Upload size={16} />استيراد CSV / JSON<input type="file" accept=".csv,.json" className="max-w-48" onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f); }} /></label></div>
      </details>}
    </section>
    <OpenTerminalContextPanel instrument={selected} />
    <ObservationPanel />
    <NewsEventsPanel />
    {!report && <div className={`${panel} py-12 text-center text-white/40`}>اختر الأداة ثم حدّث التحليل. سيظهر مصدر كل معلومة وحالة حداثتها هنا.</div>}
    {report && <>
      <section className={panel}>
        <div className="flex flex-wrap justify-between gap-3"><h2 className="text-lg font-semibold">{report.instrument.name}</h2><span className={analysisAllowed && report.status === 'ready' ? 'text-emerald-300' : 'text-amber-300'}>{analysisAllowed ? statusLabel[report.status] : 'NO TRADE · جودة البيانات غير مؤكدة أو غير سليمة'}</span></div>
        <p className="text-sm text-amber-200 mt-3">{analysisAllowed ? 'جودة الشموع تسمح بالبحث فقط؛ لا تمنح إذن تداول أو تنفيذ.' : 'التحليل والمستويات محجوبة حتى التحقق من جودة البيانات.'}</p>
        <div className="text-xs text-white/50 mt-2" dir="ltr">{report.data_health?.state ?? 'UNKNOWN'} · {report.data_health?.policy_version ?? 'unassessed'}{!analysisAllowed && ` · ${report.data_health?.reasons.join(', ') ?? 'unassessed'}`}</div>
        <p className="text-sm text-amber-200 mt-3">{eventsClear ? 'حارس الأحداث واضح لهذه اللحظة؛ تبقى بقية بوابات القرار مطلوبة.' : 'NO TRADE · سياق الأحداث غير مؤكد أو داخل فترة حجب؛ السيناريوهات محجوبة.'}</p>
        <p className="text-xs text-white/50 mt-2">حارس الأحداث سياسة مخاطرة داخلية، منفصلة عن قواعد شركة التمويل.</p>
        <div className="text-xs text-white/50 mt-2" dir="ltr">{report.event_risk?.state ?? 'UNKNOWN'} · {report.event_risk?.guard_version ?? 'unassessed'}{!eventsClear && ` · ${report.event_risk?.reasons.join(', ') ?? 'unassessed'}`}</div>
        <div className="text-xs text-white/40 mt-2">وقت التقرير: {date(report.generated_at)} · {report.interval} · {report.market?.contract ?? report.instrument.symbol}</div>
        {report.market && <><a href={report.market.source} target="_blank" rel="noreferrer" className="text-xs text-indigo-300 block my-2">مصدر البيانات · {report.market.data_mode === 'user_import' ? 'استيراد المستخدم' : 'بيانات منصة عامة'} · آخر شمعة: {date(report.market.candles[report.market.candles.length - 1]!.close_time)}</a>
          {analysisAllowed && <div dir="ltr" className="h-64 mt-4"><ResponsiveContainer width="100%" height="100%"><LineChart data={report.market.candles.slice(-100).map(c => ({ time: new Date(c.close_time).toLocaleTimeString(), close: Number(c.close) }))}><XAxis dataKey="time" minTickGap={60} tick={{ fill: '#94a3b8', fontSize: 10 }} /><YAxis domain={['auto', 'auto']} width={80} tick={{ fill: '#94a3b8', fontSize: 11 }} /><Tooltip contentStyle={{ background: '#111827', border: '1px solid #334155' }} /><Line dataKey="close" dot={false} stroke="#818cf8" strokeWidth={2} isAnimationActive={false} />{report.indicators['support20'] && <ReferenceLine y={Number(report.indicators['support20'])} stroke="#34d399" strokeDasharray="4 4" />}{report.indicators['resistance20'] && <ReferenceLine y={Number(report.indicators['resistance20'])} stroke="#f87171" strokeDasharray="4 4" />}</LineChart></ResponsiveContainer></div>}</>}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">{(analysisAllowed ? Object.entries(report.indicators) : []).map(([key, value]) => <div key={key} className="bg-white/[.025] rounded-lg p-3"><div className="text-xs text-white/40">{indicatorLabel[key] ?? key}</div><div className="font-mono mt-1" dir="ltr">{number(value)}</div></div>)}</div>
      </section>
      <section className="grid lg:grid-cols-3 gap-4">{(scenariosAllowed ? report.scenarios : []).map(s => <article key={s.direction} className={panel}><h3 className="text-lg text-indigo-200">{directionLabel[s.direction]}</h3><p className="text-sm text-white/70 leading-7 mt-3">{s.condition}</p><dl className="text-sm space-y-2 my-4"><div className="flex justify-between"><dt>مستوى المراقبة</dt><dd dir="ltr">{number(s.trigger)}</dd></div><div className="flex justify-between"><dt>مستوى الإلغاء</dt><dd dir="ltr">{number(s.invalidation)}</dd></div><div className="flex justify-between"><dt>{s.direction === 'range' ? 'حدود النطاق' : 'مستويات اختبار المسار'}</dt><dd dir="ltr">{s.targets.map(number).join(' / ')}</dd></div></dl><p className="text-xs text-white/40 leading-6">{s.rationale}</p></article>)}</section>
      <section className="grid lg:grid-cols-2 gap-4"><div className={panel}><h2 className="text-lg mb-3">الأخبار والمحركات</h2><p className="text-xs text-white/40 mb-3">عناوين موثقة خلال آخر 7 أيام؛ وقت النشر مستقل عن وقت تحديث التقرير.</p><div className="max-h-96 overflow-auto space-y-4">{report.news.map(n => <article key={n.id}><a className="text-sm text-indigo-200 hover:underline leading-6" href={n.url} target="_blank" rel="noreferrer">{n.title}</a><p className="text-xs text-white/40 mt-1">{n.source} · {date(n.published_at)}</p></article>)}{!report.news.length && <p className="text-white/40">لا توجد أخبار حديثة متاحة من المصادر المحددة.</p>}</div></div>
        <div className={panel}><h2 className="text-lg mb-3">جودة الأدلة وسياق الوكلاء</h2><ul className="space-y-2 text-sm text-amber-100/80 list-disc ps-5">{report.observations.map((o, i) => <li key={i}>{o}</li>)}</ul>
          {analysisAllowed && report.market && Object.keys(report.market.derivatives).length > 0 && <details className="mt-4"><summary className="cursor-pointer text-indigo-300">التمويل والعقود المفتوحة</summary><dl dir="ltr" className="text-xs font-mono space-y-2 mt-3">{Object.entries(report.market.derivatives).map(([k, v]) => <div className="flex justify-between gap-3" key={k}><dt>{k}</dt><dd>{number(v)}</dd></div>)}</dl></details>}
          <div className="mt-4 border-t border-white/10 pt-4">{!report.agent_context.length ? <p className="text-sm text-white/40">لا توجد مخرجات حديثة من الوكلاء لهذه الأداة. يستمر التحليل المستقل.</p> : report.agent_context.map(c => <div key={c.id} className="text-xs my-3"><span className="text-white/40">{c.topic} · {date(c.timestamp)}</span><p className="mt-1 break-words">{c.summary}</p></div>)}</div>
        </div></section>
    </>}
    <EvaluationPanel personal onChange={evaluationChanged} onDirty={evaluationDirtyChanged} />
    <UserPolicyPanel evaluation={evaluation} dirty={evaluationDirty} />
    <BriefingPanel evaluation={evaluation} dirty={evaluationDirty} />
    {evaluation && evaluationDirty && <p role="status" className="text-sm text-amber-200">ملاحظة الحساب معدلة ولم تُحفظ؛ احفظها قبل إعادة حساب الحجم.</p>}
    <section className={panel}><h2 className="text-lg mb-2">ورقة تخطيط المخاطرة</h2><p className="text-sm text-white/50 mb-4">هذه أرقام تخطيطية مستقلة عن رصيد النظام. العملة: {current?.currency ?? '—'}، وقيمة النقطة: {current?.point_value ?? '—'}. لن يُرسل أي أمر.</p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">{[['قيمة حسابك', capital, setCapital], ['المخاطرة % — حتى 1%', risk, setRisk], ['الدخول المخطط', entry, setEntry], ['مستوى الإلغاء / الوقف', stop, setStop], ['رسوم الذهاب والإياب لكل عقد USD', fees, setFees], ['الانزلاق بالنقاط', slippage, setSlippage]].map(([label, value, setter]) => <label key={String(label)} className="text-sm text-white/60">{String(label)}<input disabled={setter === setCapital} className={`${input} mt-1`} inputMode="decimal" value={String(value)} onChange={e => (setter as (v: string) => void)(e.target.value)} /></label>)}</div>
      <div className="mt-4 border-t border-white/10 pt-4 space-y-3">
        <p className="text-sm text-indigo-200">حساب قواعدك الشخصية فقط · MES/MNQ · أقصى حجم 20 Micro لحساب مؤكد خالٍ. الخطر لا يتجاوز 1% ولا الهامش المتبقي. لا إذن لتنفيذ أمر.</p>
        <div className="grid md:grid-cols-3 gap-3">
          <label>عقد التخطيط المؤرخ<input className={input} value={riskContract} onChange={e => setRiskContract(e.target.value)} placeholder="MESZ26" /></label>
          <label>هامش الأمان USD<input className={input} value={buffer} onChange={e => setBuffer(e.target.value)} /></label>
          <label>مرجع الرسوم والانزلاق<input className={input} maxLength={500} value={costReference} onChange={e => setCostReference(e.target.value)} /></label>
          <label>نوع التكاليف<select className={input} value={costSource} onChange={e => setCostSource(e.target.value as 'user_declared' | 'synthetic')}><option value="user_declared">مدخلات راجعتها شخصيًا</option><option value="synthetic">افتراضات صناعية للاختبار فقط</option></select></label>
        </div>
        <label className="flex gap-2 text-sm"><input type="checkbox" checked={costsReviewed} onChange={e => setCostsReviewed(e.target.checked)} />راجعت رسوم الذهاب والإياب لكل عقد والانزلاق وهامش الأمان؛ القيم افتراضات تخطيط معلنة وليست رسومًا مؤكدة من شركة.</label>
      </div>
      <button className="mt-4 px-4 py-2 bg-indigo-600 rounded-lg disabled:opacity-40" onClick={() => void calculate()} disabled={!evaluation || evaluationDirty || !online || !['MES','MNQ'].includes(selected)}>حساب الحجم الشخصي</button>
      {visiblePersonal && <div data-testid="personal-risk-result" role="status" className="mt-4 p-4 bg-indigo-500/10 rounded-lg">
        <p>USER POLICY · الحالة: {visiblePersonal.state} · الحجم: <strong data-testid="personal-size">{visiblePersonal.contracts}</strong> Micro</p>
        <p>ميزانية المخاطرة: {visiblePersonal.risk_budget} USD · الخسارة لكل عقد: {visiblePersonal.loss_per_unit} · الخسارة المقدرة عند الوقف: {visiblePersonal.estimated_loss_at_stop}</p>
        <p>{visiblePersonal.reasons.join(', ')}</p><p className="text-xs text-white/50">{visiblePersonal.request.cost_source === 'synthetic' ? 'SYNTHETIC MECHANICS ONLY · مثال صناعي فقط' : 'تكاليف صرّح بها المستخدم'} · {visiblePersonal.request.cost_reference} · صلاحية النتيجة حتى {visiblePersonal.expires_at}</p>
        <p className="text-xs">trade_permitted=false · execution_enabled=false · الفجوات قد تتجاوز الوقف. ليس دليل عائد أو احتمال اجتياز.</p>
      </div>}

    </section>
    <details className={panel}><summary className="cursor-pointer">التقارير المحفوظة</summary><div className="flex flex-wrap gap-3 mt-4">{history.map(h => <button key={h.id} className="text-xs border border-white/10 px-3 py-2 rounded-lg" onClick={() => { void api<Research>(`saved/${h.id}`).then(value => { choose(value.instrument.id); setIntervalValue(value.interval); setReport(value); setNotice('تقرير محفوظ للمراجعة التاريخية؛ ليس تحديثًا لحظيًا.'); }).catch(e => setError(String(e))); }}>{h.instrument} · {date(h.created)}</button>)}</div></details>
    <footer className="text-xs text-white/35 leading-6">السيناريوهات مشروطة وليست تنبؤًا مؤكدًا. تحقق من مواصفات العقد والهامش والأحداث الاقتصادية في منصتك قبل اتخاذ قرارك. <a className="text-indigo-300" href="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm" target="_blank" rel="noreferrer">تقويم FOMC</a> · <a className="text-indigo-300" href="https://www.bls.gov/schedule/" target="_blank" rel="noreferrer">تقويم BLS</a></footer>
  </div>;
}
