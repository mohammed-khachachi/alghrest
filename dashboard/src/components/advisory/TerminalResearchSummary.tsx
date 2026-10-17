import type { TerminalResearch } from '@/lib/terminalResearch';
import { terminalSummary, researchHeadlines, headlineReadingCue } from '@/lib/terminalSummary';
import { sourceTime } from '@/lib/terminalDataStatus';
import { TERMINAL_ORIGIN } from '@/lib/terminalBridge';
import { TerminalQuality } from './TerminalQuality';

export function TerminalResearchSummary({ report }: { report: TerminalResearch }) {
  const a = report.analysis;
  const news = researchHeadlines(report);
  const newsState = report.sources.find(s => s.kind === 'news')!.state;
  const historySource = report.sources.find(s => s.kind === 'history')!;
  return <section aria-label="ملخص البحث" className="space-y-4 rounded-lg border border-indigo-400/20 bg-indigo-400/5 p-4">
    <div><h3 className="text-lg font-semibold">ملخص البحث · {report.symbol}</h3>
      <p className="mt-1 text-xs text-white/60">شرح محسوب من هذه القراءة · {sourceTime(report.assessed_at)} · الفترات بعدد الشموع، وليست أيامًا ما لم يُعلن إطار يومي.</p></div>
    <TerminalQuality report={report} />
    {a?.history_cache_state === 'stale' && <p role="status" className="text-sm text-amber-200">تعثر تحديث الشموع؛ هذا الملخص يصف النسخة السابقة، وآخر جلب ناجح كان {sourceTime(a.history_fetched_at)}.</p>}
    <div className="grid gap-4 xl:grid-cols-3">{terminalSummary(report).map(item => <article key={item.title} className="space-y-2">
      <h4 className="font-semibold text-indigo-200">{item.title}</h4>
      <p className="text-sm leading-relaxed">{item.explanation}</p>
      <p className="text-xs leading-relaxed text-white/60">{item.evidence}</p>
    </article>)}</div>
    <p className="text-xs leading-relaxed text-white/60">مصدر الحسابات: شموع {report.symbol} عبر OpenTerminal · المزوّد {a && a.history_provider !== 'UNKNOWN' ? a.history_provider : 'غير معلن'} · آخر شمعة {sourceTime(a?.last_time)}. لا نستبدل الإغلاق التاريخي بالسعر الحالي.</p>
    <details className="text-xs text-white/60"><summary className="cursor-pointer">مصدر الشموع وتفاصيل القراءة</summary>
      <p className="mt-2">الإطار المطلوب: {a?.interval_basis === 'provider_request' ? a.interval : 'غير معلن'} · آخر جلب ناجح: {sourceTime(a?.history_fetched_at)} · استلام ALGHREST: {sourceTime(historySource.received_at)}</p>
      <p className="mt-2 break-all" dir="ltr">SHA-256: {historySource.response_sha256 ?? 'غير متاح'}</p>
      <a className="mt-2 inline-block text-indigo-300 underline" href={`${TERMINAL_ORIGIN}/api/history/${encodeURIComponent(report.symbol)}?range=6M&metadata=1`} target="_blank" rel="noopener noreferrer">فتح بيانات OpenTerminal الحالية (قد تختلف عن هذه القراءة)</a>
    </details>
    <div className="space-y-3 border-t border-white/10 pt-3"><h4 className="font-semibold text-indigo-200">ما الذي يستحق القراءة في الأخبار؟</h4>
      <p className="text-xs leading-relaxed text-white/60">{news.matching > 0
        ? `${news.matching} من ${report.headlines.length} عناوين تذكر الرمز أو الاسم المعلن؛ تُعرض أولًا ثم الأحدث. الذكر في العنوان لا يثبت تأثيرًا على السعر.`
        : 'لم نجد ذكرًا واضحًا للرمز أو الاسم في العناوين المتاحة؛ الأخبار التالية سياق من نتائج OpenTerminal، وصلتها المباشرة غير مؤكدة.'} نعتمد على العناوين فقط؛ لم يُقرأ نص المقال ولا نحدد سبب حركة السعر.</p>
      <ul className="space-y-3">{news.selected.map(h => <li key={h.url} className="text-sm">
        <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-indigo-300 hover:underline">{h.title}</a>
        <p className="mt-1 leading-relaxed text-white/80">{headlineReadingCue(h.title)}</p>
        <p className="mt-1 text-xs text-white/60">{h.mentionsSymbol ? 'يذكر الرمز أو الاسم؛ راجع تفاصيل الخبر قبل ربطه بالحركة.' : 'سياق محتمل؛ لا يظهر ذكر واضح للرمز أو الاسم.'} · {h.publisher} · {sourceTime(h.published_at)}</p>
      </li>)}</ul>
      {!news.selected.length && <p className="text-sm text-amber-200">{newsState === 'available' ? 'لم يُرجع المصدر عناوين صالحة؛ لا يعني ذلك عدم وجود أخبار.' : 'الأخبار غير متاحة لهذه القراءة؛ لا يمكن تلخيصها.'}</p>}
    </div>
  </section>;
}
