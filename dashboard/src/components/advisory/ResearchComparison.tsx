import { useLanguage, tr } from "../../i18n";
import type { TerminalResearch } from '@/lib/terminalResearch';
import { compareResearch, type ResearchSnapshot } from '@/lib/researchJournal';
import { sourceTime } from '@/lib/terminalDataStatus';

export function ResearchComparison({ current, previous }: { current: TerminalResearch; previous: ResearchSnapshot | null }) {
  useLanguage();
  if (!previous) return <p className="text-sm text-white/60">{tr("لا توجد لقطة سابقة لهذه القراءة. احفظ أول لقطة ثم حدّث البحث للمقارنة.")}</p>;
  const comparison = compareResearch(current, previous.report);
  return <section aria-label={tr("التغيرات منذ اللقطة السابقة")} className="space-y-3">
    <h3 className="font-semibold">{tr("التغيرات منذ اللقطة السابقة")}</h3>
    <p className="text-xs text-white/60">{tr("السابقة: ")}{tr(sourceTime(previous.report.assessed_at))}{tr(" · القراءة المقارنة: ")}{tr(sourceTime(current.assessed_at))}{tr(". وقت حفظ السابقة: ")}{tr(sourceTime(previous.saved_at))}.</p>
    {!comparison.comparable && <p className="text-sm text-amber-200">{tr("قابلية المقارنة غير مؤكدة: الشموع ناقصة أو المزوّد/الإطار مختلف أو غير معلن. القيم أدناه قراءات منفصلة؛ اختلافها لا يثبت حركة سوق بين اللقطتين.")}</p>}
    <div className="overflow-x-auto"><table className="w-full text-end text-sm"><thead><tr className="text-white/60"><th className="p-2">{tr("البند")}</th><th className="p-2">{tr("السابقة")}</th><th className="p-2">{tr("المقارنة")}</th><th className="p-2">{tr("التغير")}</th></tr></thead>
      <tbody>{comparison.rows.map(row => <tr key={row.label} className={row.changed ? 'border-t border-white/10 bg-amber-500/5' : 'border-t border-white/10'}>
        <th className="p-2 font-normal">{tr(row.label)}</th><td className="p-2">{tr(row.before)}</td><td className="p-2">{tr(row.after)}</td><td className="p-2"><span className={row.changed ? 'text-amber-200' : 'text-white/40'}>{tr(row.changed ? 'تغيرت القراءة' : 'دون تغير')}</span>{row.note && <p className="mt-1 text-xs text-white/50">{row.note}</p>}</td>
      </tr>)}</tbody></table></div>
    <p className="text-xs text-white/50">{tr("آخر شمعة: ")}{tr(sourceTime(previous.report.analysis?.last_time))} ← {tr(sourceTime(current.analysis?.last_time))}{tr(" · آخر جلب ناجح: ")}{tr(sourceTime(previous.report.analysis?.history_fetched_at))} ← {tr(sourceTime(current.analysis?.history_fetched_at))}.</p>
    <h4 className="font-medium">{tr("تغير العناوين")}</h4>
    {!comparison.newsAvailable ? <p className="text-amber-200 text-sm">{tr("الأخبار غير متاحة في إحدى القراءتين؛ لا نستنتج ظهور أخبار أو اختفاءها.")}</p> : <>
      <p className="text-sm text-white/60">{tr("ظهرت ")}{tr(comparison.added.length)}{tr(" · تغيّر محتوى ")}{tr(comparison.updated.length)}{tr(" · غابت عن النتائج ")}{tr(comparison.removed.length)}{tr(". هذه مقارنة للعناوين المُعادة فقط، وليست حصرًا لأحداث السوق أو دليلًا على حذف مقال.")}</p>
      {([['ظهرت في النتائج', comparison.added], ['تغيّر العنوان أو توقيته', comparison.updated], ['لم تعد ضمن النتائج', comparison.removed]] as const).map(([label, headlines]) => headlines.length > 0 && <div key={label}><p className="text-sm font-medium">{tr(label)}</p><ul className="mt-1 space-y-2">{headlines.map(h => <li key={h.url} className="text-sm"><a href={h.url} target="_blank" rel="noopener noreferrer" className="text-indigo-300 hover:underline">{h.title}</a><p className="text-xs text-white/50">{h.publisher} · {tr(sourceTime(h.published_at))}</p></li>)}</ul></div>)}
    </>}
  </section>;
}
