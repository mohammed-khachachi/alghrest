import { useLanguage, languageDirection, tr } from "../../i18n";
import { useCallback, useEffect, useRef, useState } from 'react';
import { advisoryApi } from '../../lib/advisoryApi';
import { ageLabel, contextRequests, newsContext, refreshDue, relevanceLabel, sourceState, stateLabel, type NewsContext } from '../../lib/newsEvents';

const stamp = (value: string | null) => value ? `${new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC')}` : 'غير معلوم';
const field = 'bg-slate-900 border border-white/20 rounded p-2';

export function NewsEventsPanel() {
  useLanguage();
  const [instrument, setInstrument] = useState<'MES' | 'MNQ'>('MES');
  const [period, setPeriod] = useState(0);
  const [value, setValue] = useState<NewsContext | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const gate = useRef(contextRequests());
  const inFlight = useRef(false);
  const lastAttempt = useRef(Date.now());
  const refresh = useCallback(async () => {
    const ticket = gate.current.next(); inFlight.current = true; lastAttempt.current = Date.now();
    setBusy(true); setError('');
    try {
      const response = await advisoryApi<unknown>(`context/${instrument}`);
      if (gate.current.current(ticket)) setValue(newsContext(response, instrument));
    } catch {
      if (gate.current.current(ticket)) setError('تعذر تحديث السياق. أعد المحاولة؛ إن ظهرت نتائج سابقة فهي لم تتجدد.');
    } finally {
      if (gate.current.current(ticket)) { inFlight.current = false; setBusy(false); }
    }
  }, [instrument]);
  useEffect(() => {
    const timer = window.setInterval(() => {
      const clock = Date.now(); setNow(clock);
      if (refreshDue(period, document.visibilityState === 'visible', inFlight.current, clock - lastAttempt.current)) void refresh();
    }, 1000);
    return () => clearInterval(timer);
  }, [period, refresh]);
  useEffect(() => () => { gate.current.next(); }, []);
  function choose(root: 'MES' | 'MNQ') {
    gate.current.next(); inFlight.current = false; setBusy(false); setValue(null); setError('');
    setInstrument(root); lastAttempt.current = Date.now();
  }
  return <section data-testid="news-events-panel" dir={languageDirection()} className="mt-6 rounded-xl border border-sky-400/30 bg-white/5 p-5 text-sm min-w-0 break-words">
    <h2 className="text-lg font-semibold">{tr("الأخبار والأحداث — سياق جزئي")}</h2>
    <p className="text-amber-300 my-3">{tr("مخاطر الأحداث غير معلومة. غياب خبر أو حدث لا يعني غياب الخطر. هذه اللوحة لا تمنح إذن تداول ولا تحدّث أسعارك أو ملاحظاتك.")}</p>
    <div className="flex flex-wrap items-end gap-3">
      <label>{tr("سياق الأداة ")}<select aria-label={tr("أداة الأخبار")} className={field} value={instrument} onChange={e => choose(e.target.value as 'MES' | 'MNQ')}><option value="MES">{tr("MES")}</option><option value="MNQ">{tr("MNQ")}</option></select></label>
      <button className={field} disabled={busy} onClick={() => void refresh()}>{tr(busy ? 'جارٍ جلب السياق…' : 'تحديث الأخبار والأحداث')}</button>
      <label>{tr("التحديث التلقائي ")}<select aria-label={tr("تحديث الأخبار تلقائيًا")} className={field} value={period} onChange={e => { setPeriod(Number(e.target.value)); lastAttempt.current = Date.now(); }}><option value={0}>{tr("متوقف")}</option><option value={5}>{tr("كل 5 دقائق")}</option><option value={15}>{tr("كل 15 دقيقة")}</option></select></label>
    </div>
    <p className="text-white/60 my-2">{tr("التحديث التلقائي يعمل أثناء ظهور الصفحة فقط. تصنيف الصلة بالكلمات المفتاحية؛ لا يثبت أثر الخبر أو اتجاه السعر.")}</p>
    {error && <p role="alert" className="text-red-300 my-3">{tr(error)}</p>}
    {!value && !busy && <p className="text-white/60">{tr("اضغط تحديث لجلب المصادر؛ لا تحتاج هذه اللوحة إلى مصدر أسعار.")}</p>}
    {value && <>
      <p className="text-white/60 my-3">{tr("وقت فحص السياق: ")}<bdi>{tr(stamp(value.assessed_at))}</bdi>{tr(" · عمر الفحص: ")}{tr(ageLabel(value.assessed_at, now))}</p>
      <h3 className="font-semibold">{tr("حالة المصادر")}</h3>
      <div className="grid sm:grid-cols-2 gap-2 my-2">{value.sources.map(s => <div key={s.name} className="border border-white/15 rounded p-3 min-w-0" data-testid="context-source">
        <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline">{s.name}</a> — {tr(stateLabel[sourceState(s, now)])}
        <p>{tr("آخر محاولة: ")}<bdi>{tr(stamp(s.attempted_at))}</bdi></p>
        <p>{tr("جلب ناجح: ")}<bdi>{tr(stamp(s.fetched_at))}</bdi>{tr(" · عمره: ")}{tr(ageLabel(s.fetched_at, now))}</p>
        <p>{tr("عناصر صالحة وقت الجلب: ")}{tr(s.usable_count)} / {tr(s.parsed_count)}{tr(" · HTTP: ")}{tr(s.http_status ?? 'غير معلوم')}</p>
        {s.kind === 'calendar' && <p>{tr("تواريخ العناصر المعادة من المصدر: ")}{tr((() => { const dates = value.events.filter(e => e.source_name === s.name).flatMap(e => [e.date_start, e.date_end]).filter((d): d is string => d !== null).sort(); return dates.length ? `${dates[0]} — ${dates[dates.length - 1]}` : 'غير معلومة'; })())}{tr(" · ليست ضمان تغطية")}</p>}
      </div>)}</div>
      <h3 className="font-semibold mt-4">{tr("عناوين ذات صلة (")}{tr(value.headlines.length)})</h3>
      {!value.headlines.length && <p>{tr("لا توجد عناوين صالحة معادة؛ لا يُستنتج منها هدوء السوق.")}</p>}
      {value.headlines.map(h => <article key={h.item.id + h.item.source} className="border-b border-white/10 py-3">
        <a href={h.item.url} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline">{h.item.title}</a>
        <p>{h.item.source}{tr(" · نُشر: ")}<bdi>{tr(stamp(h.item.published_at))}</bdi>{tr(" · عمر النشر: ")}{tr(ageLabel(h.item.published_at, now))}</p>
        <p>{tr("سبب الصلة: ")}{h.relevance.map(r => tr(relevanceLabel(r))).join('، ')}</p>
      </article>)}
      <h3 className="font-semibold mt-4">{tr("الجداول الرسمية المتاحة (")}{tr(value.events.length)})</h3>
      <p className="text-white/60">{tr("تُعرض المواعيد كما يصرّح بها المصدر. الوقت والمنطقة غير المعلومين يبقيان غير معلومين. لا توجد درجة تأثير رسمية مستنتجة هنا.")}</p>
      {!value.events.length && <p>{tr("لا أحداث صالحة معادة؛ التغطية غير مكتملة.")}</p>}
      {value.events.map(e => <article key={e.event.id} className="border-b border-white/10 py-3">
        <a href={e.event.source} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline">{e.event.name}</a> — {e.source_name}
        <p>{tr("التاريخ: ")}{tr(e.date_start ?? 'لم يُعلن')}{tr(e.date_end !== e.date_start && ` إلى ${e.date_end}`)}{tr(" · الوقت المطبوع: ")}{tr(e.printed_time ?? 'غير معلن')}{tr(" · المنطقة: ")}{tr(e.timezone ?? 'غير معلومة')}</p>
        <p>{tr("الوقت الدقيق UTC: ")}<bdi>{tr(stamp(e.event.scheduled_at))}</bdi>{tr(" · الحالة: ")}{tr(e.event.status === 'cancelled' ? 'إلغاء معلن في المصدر' : e.event.status === 'unknown' ? 'غير معلومة' : 'موعد معلن')}</p>
        <p>{tr("وقت معرفة المصدر: ")}<bdi>{tr(stamp(e.event.known_at))}</bdi>{tr(" · الصلة: ")}{e.relevance.map(r => tr(relevanceLabel(r))).join('، ')}</p>
      </article>)}
    </>}
  </section>;
}
