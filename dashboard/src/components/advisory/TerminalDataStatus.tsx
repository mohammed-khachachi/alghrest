import { useLanguage, tr } from "../../i18n";
import type { TerminalResearch } from '@/lib/terminalResearch';
import { terminalDataStatus } from '@/lib/terminalDataStatus';

export function TerminalDataStatus({ report, now }: { report: TerminalResearch; now: number }) {
  useLanguage();
  return <section aria-label={tr("حالة بيانات OpenTerminal")} className="space-y-3">
    <h3 className="font-semibold">{tr("حالة البيانات وتوقيتها")}</h3>
    <div className="grid gap-3 lg:grid-cols-3">{terminalDataStatus(report,now).map(card=><article key={card.kind} className="rounded-lg border border-white/10 bg-white/[0.025] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2"><h4 className="font-medium">{tr(card.title)}</h4><span className={`rounded px-2 py-1 text-xs ${card.tone==='error'?'bg-red-500/10 text-red-300':card.tone==='warning'?'bg-amber-500/10 text-amber-200':'bg-white/10 text-white/80'}`}>{tr(card.status)}</span></div>
      <dl className="mt-3 space-y-3">{card.details.map(([label,value])=><div key={label}><dt className="text-xs text-white/40">{tr(label)}</dt><dd className="mt-1 break-words text-sm text-white/80">{tr(value)}</dd></div>)}</dl>
    </article>)}</div>
    <p className="text-xs leading-relaxed text-white/50">{tr("وقت الجلب والاستلام يصف وصول البيانات، وليس وقت تحديث السوق. عمر الشمعة قد يشمل عطلة أو جلسة مغلقة؛ حداثة السوق واكتمال الأخبار غير معتمدتين.")}</p>
  </section>;
}
