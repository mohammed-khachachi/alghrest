import type { TerminalResearch } from '@/lib/terminalResearch';
import { compareResearch, type ResearchSnapshot } from '@/lib/researchJournal';
import { sourceTime } from '@/lib/terminalDataStatus';

export function ResearchComparison({ current, previous }: { current: TerminalResearch; previous: ResearchSnapshot | null }) {
  if (!previous) return <p className="text-sm text-white/60">لا توجد لقطة سابقة لهذه القراءة. احفظ أول لقطة ثم حدّث البحث للمقارنة.</p>;
  const comparison = compareResearch(current, previous.report);
  return <section aria-label="التغيرات منذ اللقطة السابقة" className="space-y-3">
    <h3 className="font-semibold">التغيرات منذ اللقطة السابقة</h3>
    <p className="text-xs text-white/60">السابقة: {sourceTime(previous.report.assessed_at)} · القراءة المقارنة: {sourceTime(current.assessed_at)}. وقت حفظ السابقة: {sourceTime(previous.saved_at)}.</p>
    {!comparison.comparable && <p className="text-sm text-amber-200">قابلية المقارنة غير مؤكدة: الشموع ناقصة أو المزوّد/الإطار مختلف أو غير معلن. القيم أدناه قراءات منفصلة؛ اختلافها لا يثبت حركة سوق بين اللقطتين.</p>}
    <div className="overflow-x-auto"><table className="w-full text-right text-sm"><thead><tr className="text-white/60"><th className="p-2">البند</th><th className="p-2">السابقة</th><th className="p-2">المقارنة</th><th className="p-2">التغير</th></tr></thead>
      <tbody>{comparison.rows.map(row => <tr key={row.label} className={row.changed ? 'border-t border-white/10 bg-amber-500/5' : 'border-t border-white/10'}>
        <th className="p-2 font-normal">{row.label}</th><td className="p-2">{row.before}</td><td className="p-2">{row.after}</td><td className="p-2"><span className={row.changed ? 'text-amber-200' : 'text-white/40'}>{row.changed ? 'تغيرت القراءة' : 'دون تغير'}</span>{row.note && <p className="mt-1 text-xs text-white/50">{row.note}</p>}</td>
      </tr>)}</tbody></table></div>
    <p className="text-xs text-white/50">آخر شمعة: {sourceTime(previous.report.analysis?.last_time)} ← {sourceTime(current.analysis?.last_time)} · آخر جلب ناجح: {sourceTime(previous.report.analysis?.history_fetched_at)} ← {sourceTime(current.analysis?.history_fetched_at)}.</p>
    <h4 className="font-medium">تغير العناوين</h4>
    {!comparison.newsAvailable ? <p className="text-amber-200 text-sm">الأخبار غير متاحة في إحدى القراءتين؛ لا نستنتج ظهور أخبار أو اختفاءها.</p> : <>
      <p className="text-sm text-white/60">ظهرت {comparison.added.length} · تغيّر محتوى {comparison.updated.length} · غابت عن النتائج {comparison.removed.length}. هذه مقارنة للعناوين المُعادة فقط، وليست حصرًا لأحداث السوق أو دليلًا على حذف مقال.</p>
      {([['ظهرت في النتائج', comparison.added], ['تغيّر العنوان أو توقيته', comparison.updated], ['لم تعد ضمن النتائج', comparison.removed]] as const).map(([label, headlines]) => headlines.length > 0 && <div key={label}><p className="text-sm font-medium">{label}</p><ul className="mt-1 space-y-2">{headlines.map(h => <li key={h.url} className="text-sm"><a href={h.url} target="_blank" rel="noopener noreferrer" className="text-indigo-300 hover:underline">{h.title}</a><p className="text-xs text-white/50">{h.publisher} · {sourceTime(h.published_at)}</p></li>)}</ul></div>)}
    </>}
  </section>;
}
