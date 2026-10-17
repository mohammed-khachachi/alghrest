import { useCallback, useEffect, useRef, useState } from 'react';
import { advisoryApi } from '../../lib/advisoryApi';
import { ageLabel, contextRequests, newsContext, refreshDue, relevanceLabel, sourceState, stateLabel, type NewsContext } from '../../lib/newsEvents';

const stamp = (value: string | null) => value ? `${new Date(value).toISOString().replace('T', ' ').replace('.000Z', ' UTC')}` : 'غير معلوم';
const field = 'bg-slate-900 border border-white/20 rounded p-2';

export function NewsEventsPanel() {
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
  return <section data-testid="news-events-panel" dir="rtl" className="mt-6 rounded-xl border border-sky-400/30 bg-white/5 p-5 text-sm min-w-0 break-words">
    <h2 className="text-lg font-semibold">الأخبار والأحداث — سياق جزئي</h2>
    <p className="text-amber-300 my-3">مخاطر الأحداث غير معلومة. غياب خبر أو حدث لا يعني غياب الخطر. هذه اللوحة لا تمنح إذن تداول ولا تحدّث أسعارك أو ملاحظاتك.</p>
    <div className="flex flex-wrap items-end gap-3">
      <label>سياق الأداة <select aria-label="أداة الأخبار" className={field} value={instrument} onChange={e => choose(e.target.value as 'MES' | 'MNQ')}><option>MES</option><option>MNQ</option></select></label>
      <button className={field} disabled={busy} onClick={() => void refresh()}>{busy ? 'جارٍ جلب السياق…' : 'تحديث الأخبار والأحداث'}</button>
      <label>التحديث التلقائي <select aria-label="تحديث الأخبار تلقائيًا" className={field} value={period} onChange={e => { setPeriod(Number(e.target.value)); lastAttempt.current = Date.now(); }}><option value={0}>متوقف</option><option value={5}>كل 5 دقائق</option><option value={15}>كل 15 دقيقة</option></select></label>
    </div>
    <p className="text-white/60 my-2">التحديث التلقائي يعمل أثناء ظهور الصفحة فقط. تصنيف الصلة بالكلمات المفتاحية؛ لا يثبت أثر الخبر أو اتجاه السعر.</p>
    {error && <p role="alert" className="text-red-300 my-3">{error}</p>}
    {!value && !busy && <p className="text-white/60">اضغط تحديث لجلب المصادر؛ لا تحتاج هذه اللوحة إلى مصدر أسعار.</p>}
    {value && <>
      <p className="text-white/60 my-3">وقت فحص السياق: <bdi>{stamp(value.assessed_at)}</bdi> · عمر الفحص: {ageLabel(value.assessed_at, now)}</p>
      <h3 className="font-semibold">حالة المصادر</h3>
      <div className="grid sm:grid-cols-2 gap-2 my-2">{value.sources.map(s => <div key={s.name} className="border border-white/15 rounded p-3 min-w-0" data-testid="context-source">
        <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline">{s.name}</a> — {stateLabel[sourceState(s, now)]}
        <p>آخر محاولة: <bdi>{stamp(s.attempted_at)}</bdi></p>
        <p>جلب ناجح: <bdi>{stamp(s.fetched_at)}</bdi> · عمره: {ageLabel(s.fetched_at, now)}</p>
        <p>عناصر صالحة وقت الجلب: {s.usable_count} / {s.parsed_count} · HTTP: {s.http_status ?? 'غير معلوم'}</p>
        {s.kind === 'calendar' && <p>تواريخ العناصر المعادة من المصدر: {(() => { const dates = value.events.filter(e => e.source_name === s.name).flatMap(e => [e.date_start, e.date_end]).filter((d): d is string => d !== null).sort(); return dates.length ? `${dates[0]} — ${dates[dates.length - 1]}` : 'غير معلومة'; })()} · ليست ضمان تغطية</p>}
      </div>)}</div>
      <h3 className="font-semibold mt-4">عناوين ذات صلة ({value.headlines.length})</h3>
      {!value.headlines.length && <p>لا توجد عناوين صالحة معادة؛ لا يُستنتج منها هدوء السوق.</p>}
      {value.headlines.map(h => <article key={h.item.id + h.item.source} className="border-b border-white/10 py-3">
        <a href={h.item.url} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline">{h.item.title}</a>
        <p>{h.item.source} · نُشر: <bdi>{stamp(h.item.published_at)}</bdi> · عمر النشر: {ageLabel(h.item.published_at, now)}</p>
        <p>سبب الصلة: {h.relevance.map(relevanceLabel).join('، ')}</p>
      </article>)}
      <h3 className="font-semibold mt-4">الجداول الرسمية المتاحة ({value.events.length})</h3>
      <p className="text-white/60">تُعرض المواعيد كما يصرّح بها المصدر. الوقت والمنطقة غير المعلومين يبقيان غير معلومين. لا توجد درجة تأثير رسمية مستنتجة هنا.</p>
      {!value.events.length && <p>لا أحداث صالحة معادة؛ التغطية غير مكتملة.</p>}
      {value.events.map(e => <article key={e.event.id} className="border-b border-white/10 py-3">
        <a href={e.event.source} target="_blank" rel="noopener noreferrer" className="text-sky-300 underline">{e.event.name}</a> — {e.source_name}
        <p>التاريخ: {e.date_start ?? 'لم يُعلن'}{e.date_end !== e.date_start && ` إلى ${e.date_end}`} · الوقت المطبوع: {e.printed_time ?? 'غير معلن'} · المنطقة: {e.timezone ?? 'غير معلومة'}</p>
        <p>الوقت الدقيق UTC: <bdi>{stamp(e.event.scheduled_at)}</bdi> · الحالة: {e.event.status === 'cancelled' ? 'إلغاء معلن في المصدر' : e.event.status === 'unknown' ? 'غير معلومة' : 'موعد معلن'}</p>
        <p>وقت معرفة المصدر: <bdi>{stamp(e.event.known_at)}</bdi> · الصلة: {e.relevance.map(relevanceLabel).join('، ')}</p>
      </article>)}
    </>}
  </section>;
}
