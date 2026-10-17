import type {TerminalResearch} from '@/lib/terminalResearch';
import type {ResearchSnapshot} from '@/lib/researchJournal';
import {researchAlerts} from '@/lib/researchAlerts';
import {sourceTime} from '@/lib/terminalDataStatus';

export function ResearchAlerts({current,previous,historical=false,importedCurrent=false}:{current:TerminalResearch;previous:ResearchSnapshot|null;historical?:boolean;importedCurrent?:boolean}) {
  const result=researchAlerts(current,previous,importedCurrent);
  return <section aria-label="تنبيهات تغير البحث" className="space-y-3 rounded-lg border border-indigo-400/20 p-4">
    <h3 className="font-semibold">تنبيهات تغير البحث · {current.symbol}</h3>
    <p className="text-xs text-white/60">{historical?'مقارنة تاريخية محفوظة':'مقارنة عند تحديث القراءة'} · مؤشرات وصفية مبدئية؛ الشمعة الأخيرة قد تتغير. تُحسب عند عرض القراءة أو تحديثها فقط.</p>
    {result.reason&&<p role="status" className="text-sm text-amber-200">{result.reason}</p>}
    <ul className="space-y-3">{result.alerts.map(alert=><li key={alert.id} className="rounded bg-indigo-500/10 p-3"><h4 className="text-sm font-medium">{alert.title}</h4><p className="mt-1 text-sm text-white/70">{alert.evidence}</p></li>)}</ul>
    {result.alerts.length>0&&previous&&<div className="space-y-1 text-xs text-white/50">
      <p>المصدر: {current.analysis?.history_provider} · الإطار المعلن: {current.analysis?.interval} · آخر شمعة: {sourceTime(previous.report.analysis?.last_time)} ← {sourceTime(current.analysis?.last_time)}</p>
      <p>جلب الشموع: {sourceTime(previous.report.analysis?.history_fetched_at)} ← {sourceTime(current.analysis?.history_fetched_at)} · قراءة المقارنة: {sourceTime(current.assessed_at)}</p>
      {[previous.report,current].map((r,i)=><p key={i} className="break-all">بصمة استجابة الشموع {i===0?'السابقة':'المقارنة'}: {r.sources.find(s=>s.kind==='history')?.response_sha256}</p>)}
      <p>تقويم الجلسات غير المتحقق يبقى قيدًا معلنًا؛ لا يُستنتج فتح السوق أو إغلاقه.</p>
    </div>}
    <details className="text-xs text-white/50"><summary className="cursor-pointer">قواعد التنبيه وحدودها</summary><p className="mt-2">تغير ترتيب SMA20 وSMA50؛ عبور RSI14 البسيط مستوى 30 أو 70؛ تغير ATR14/الإغلاق بمقدار 25% نسبيًا و0.25 نقطة مئوية معًا. عتبات وصفية اختيرت للعرض ولم تُعاير لإثبات ربحية. يلزم مصدر وإطار متطابقان وشمعة أحدث وجودة تسمح بالمؤشر. تُحجب التنبيهات عند نقص الدليل أو تأخره؛ لا توجد أوامر أو إشعارات خارج التطبيق.</p></details>
  </section>;
}
