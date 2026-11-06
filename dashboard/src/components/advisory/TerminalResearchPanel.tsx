import { currentLocale, useLanguage, languageDirection, tr } from "../../i18n";
import { useEffect, useRef, useState } from 'react';
import { advisoryApi } from '@/lib/advisoryApi';
import { terminalResearch, type TerminalResearch } from '@/lib/terminalResearch';
import { ProviderDiagnostics } from './ProviderDiagnostics';
import { TerminalDataStatus } from './TerminalDataStatus';
import { TerminalResearchSummary } from './TerminalResearchSummary';
function number(value: string | null | undefined) {
  return value == null ? 'غير متاح' : Number(value).toLocaleString(currentLocale(), { maximumFractionDigits: 4 });
}

export function TerminalResearchPanel({ symbol, onReport, refreshToken = 0 }: { symbol: string; onReport?: (report: TerminalResearch | null) => void; refreshToken?: number }) {
  useLanguage();
  const [report, setReport] = useState<TerminalResearch | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const [expired, setExpired] = useState(false);
  const revision = useRef(0);
  const current = useRef(symbol); current.current = symbol;
  async function refresh() {
    const request = ++revision.current;
    const selected = symbol;
    setReport(null); setError(''); setExpired(false); setBusy(true);
    try {
      const raw = await advisoryApi<unknown>(`openterminal-research/${encodeURIComponent(selected)}`);
      if (request !== revision.current || current.current !== selected) return;
      const value = terminalResearch(raw, selected);
      if (!value) throw new Error('تعذر اعتماد استجابة OpenTerminal لهذا الرمز.');
      setNow(Date.now()); setExpired(false); setReport(value);
    } catch (reason) {
      if (request === revision.current) setError(reason instanceof Error ? reason.message : 'تعذر جلب البيانات.');
    } finally { if (request === revision.current) setBusy(false); }
  }
  useEffect(() => {
    setReport(null); setError(''); setExpired(false); void refresh();
    return () => { revision.current += 1; };
  }, [symbol, refreshToken]);
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 1000); return () => window.clearInterval(timer); }, []);
  useEffect(() => {
    if (report && !terminalResearch(report, symbol, now)) { setReport(null); setExpired(true); }
  }, [report, symbol, now]);
  const visible = report ? terminalResearch(report, symbol, now) : null;
  const analysis = visible?.analysis;
  useEffect(() => {
    onReport?.(report && terminalResearch(report, symbol) ? report : null);
  }, [report, symbol, onReport]);
  return <section dir={languageDirection()} aria-label={tr("تحليل بيانات OpenTerminal")} className="rounded-xl border border-border bg-bg-surface p-5 space-y-4">
    <div className="flex flex-wrap justify-between gap-3"><div><h2 className="text-lg font-semibold">{tr("تحليل ALGHREST · ")}{tr(symbol)}</h2><p className="mt-1 text-sm text-white/50">{tr("البيانات من OpenTerminal؛ المؤشرات محسوبة على الرمز نفسه.")}</p></div>
      <button disabled={busy} onClick={() => void refresh()} className="rounded-lg bg-violet-600 px-4 py-2 text-sm disabled:opacity-40">{tr(busy ? 'جارٍ قراءة البيانات…' : 'تحديث التحليل من OpenTerminal')}</button></div>
    {error && <p role="alert" className="text-red-300">{tr(error)}</p>}
    {expired && <p role="status" className="text-amber-200">{tr("انتهت صلاحية العرض؛ حدّث التحليل.")}</p>}
    {visible && <>
      <TerminalResearchSummary report={visible} />
      <TerminalDataStatus report={visible} now={now} />
      <ProviderDiagnostics symbol={symbol} revision={visible.assessed_at} />
      {visible.quote && <div className="rounded-lg border border-white/10 p-4"><p>{visible.quote.name ?? symbol}</p><p className="mt-2 text-2xl" dir="ltr">{tr(number(visible.quote.price))} {tr(visible.quote.currency)}</p><p className="mt-2 text-sm text-white/60">{tr("التغير المعلن: ")}{tr(number(visible.quote.change_percent))}{tr("% · المصدر: ")}{visible.quote.provider}{tr(" · وقت السعر: ")}{tr(visible.quote.market_time ? new Date(visible.quote.market_time).toLocaleString(currentLocale()) : 'غير معلن')}</p></div>}
      {analysis ? <>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">{[
          ['متوسط 20 شمعة', analysis.sma20], ['متوسط 50 شمعة', analysis.sma50],
          ['RSI 14 · متوسط بسيط', analysis.rsi14_simple], ['ATR 14 · متوسط بسيط', analysis.atr14_simple],
          ['أدنى آخر 20 شمعة', analysis.recent20_low], ['أعلى آخر 20 شمعة', analysis.recent20_high],
          ['الإغلاق التاريخي الأخير', analysis.last_close],
        ].map(([label, value]) => <div key={label} className="rounded-lg bg-white/5 p-3"><p className="text-xs text-white/50">{tr(label)}</p><p className="mt-2" dir="ltr">{tr(number(value))}</p></div>)}</div>
        <p className="text-xs text-white/50">{tr(analysis.count)}{tr(" شمعة · من ")}{tr(new Date(analysis.first_time).toLocaleDateString(currentLocale()))}{tr(" إلى ")}{tr(new Date(analysis.last_time).toLocaleDateString(currentLocale()))}{tr(" · النطاق المطلوب 6 أشهر؛ المؤشرات بعدد الشموع. تفاصيل المصدر والإطار في حالة البيانات أعلاه.")}</p>
      </> : <p className="text-amber-200">{tr("لم تتوفر سلسلة شموع صالحة لحساب المؤشرات. تبقى البيانات الأخرى المتاحة معروضة.")}</p>}
      <div><h3 className="font-medium">{tr("الأخبار المتاحة")}</h3><ul className="mt-3 space-y-2 text-sm">{visible.headlines.map(h => <li key={h.url}><a href={h.url} target="_blank" rel="noopener noreferrer" className="text-indigo-300 hover:underline">{h.title}</a><span className="mr-2 text-white/40">{h.publisher}</span></li>)}</ul>{!visible.headlines.length && <p className="mt-2 text-sm text-white/50">{tr("لا توجد عناوين صالحة في هذه القراءة.")}</p>}</div>
      <p className="text-xs text-white/40">{tr("قراءة البيانات: ")}{tr(new Date(visible.assessed_at).toLocaleString(currentLocale()))}{tr(". الأسعار قد تتأخر؛ السعر الحالي والإغلاق التاريخي قد يعودان لوقتين مختلفين.")}</p>
    </>}
    <p className="text-xs text-white/40">{tr("تحليل وصفي للبيانات المتاحة، دون تنفيذ أوامر. المؤشرات والأخبار لا تثبت فرصة رابحة أو اكتمال تغطية الأحداث.")}</p>
  </section>;
}
