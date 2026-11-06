import { useLanguage, tr } from "../../i18n";
import type {TerminalResearch} from '@/lib/terminalResearch';
import type {ResearchSnapshot} from '@/lib/researchJournal';
import {researchAlerts} from '@/lib/researchAlerts';
import {sourceTime} from '@/lib/terminalDataStatus';

export function ResearchAlerts({current,previous,historical=false,importedCurrent=false}:{current:TerminalResearch;previous:ResearchSnapshot|null;historical?:boolean;importedCurrent?:boolean}) {
  useLanguage();
  const result=researchAlerts(current,previous,importedCurrent);
  return <section aria-label={tr("تنبيهات تغير البحث")} className="space-y-3 rounded-lg border border-indigo-400/20 p-4">
    <h3 className="font-semibold">{tr("تنبيهات تغير البحث · ")}{current.symbol}</h3>
    <p className="text-xs text-white/60">{tr(historical?'مقارنة تاريخية محفوظة':'مقارنة عند تحديث القراءة')}{tr(" · مؤشرات وصفية مبدئية؛ الشمعة الأخيرة قد تتغير. تُحسب عند عرض القراءة أو تحديثها فقط.")}</p>
    {result.reason&&<p role="status" className="text-sm text-amber-200">{tr(result.reason)}</p>}
    <ul className="space-y-3">{result.alerts.map(alert=><li key={alert.id} className="rounded bg-indigo-500/10 p-3"><h4 className="text-sm font-medium">{tr(alert.title)}</h4><p className="mt-1 text-sm text-white/70">{tr(alert.evidence)}</p></li>)}</ul>
    {result.alerts.length>0&&previous&&<div className="space-y-1 text-xs text-white/50">
      <p>{tr("المصدر: ")}{tr(current.analysis?.history_provider)}{tr(" · الإطار المعلن: ")}{tr(current.analysis?.interval)}{tr(" · آخر شمعة: ")}{tr(sourceTime(previous.report.analysis?.last_time))} ← {tr(sourceTime(current.analysis?.last_time))}</p>
      <p>{tr("جلب الشموع: ")}{tr(sourceTime(previous.report.analysis?.history_fetched_at))} ← {tr(sourceTime(current.analysis?.history_fetched_at))}{tr(" · قراءة المقارنة: ")}{tr(sourceTime(current.assessed_at))}</p>
      {[previous.report,current].map((r,i)=><p key={i} className="break-all">{tr("بصمة استجابة الشموع ")}{tr(i===0?'السابقة':'المقارنة')}: {tr(r.sources.find(s=>s.kind==='history')?.response_sha256)}</p>)}
      <p>{tr("تقويم الجلسات غير المتحقق يبقى قيدًا معلنًا؛ لا يُستنتج فتح السوق أو إغلاقه.")}</p>
    </div>}
    <details className="text-xs text-white/50"><summary className="cursor-pointer">{tr("قواعد التنبيه وحدودها")}</summary><p className="mt-2">{tr("تغير ترتيب SMA20 وSMA50؛ عبور RSI14 البسيط مستوى 30 أو 70؛ تغير ATR14/الإغلاق بمقدار 25% نسبيًا و0.25 نقطة مئوية معًا. عتبات وصفية اختيرت للعرض ولم تُعاير لإثبات ربحية. يلزم مصدر وإطار متطابقان وشمعة أحدث وجودة تسمح بالمؤشر. تُحجب التنبيهات عند نقص الدليل أو تأخره؛ لا توجد أوامر أو إشعارات خارج التطبيق.")}</p></details>
  </section>;
}
