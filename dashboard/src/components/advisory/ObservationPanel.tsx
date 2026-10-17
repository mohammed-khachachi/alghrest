import { useEffect, useRef, useState } from 'react';
import { advisoryApi as api } from '../../lib/advisoryApi';
import { canReview, observationTemplate, observationView, packetSchema, priceAge, responseGate, warningLabel, type ObservationPacket, type ObservationView } from '../../lib/observations';

const field = 'w-full bg-black/30 border border-white/20 rounded p-2 text-white';
const pretty = (v: unknown) => JSON.stringify(v, null, 2);

export function ObservationPanel() {
  const [raw, setRaw] = useState('');
  const [packet, setPacket] = useState<ObservationPacket | null>(null);
  const [saved, setSaved] = useState<ObservationView | null>(null);
  const [history, setHistory] = useState<ObservationView[]>([]);
  const [versions, setVersions] = useState<ObservationView[]>([]);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [now, setNow] = useState(Date.now());
  const gate = useRef(responseGate());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => { clearInterval(timer); gate.current.next(); };
  }, []);

  function change(text: string) {
    gate.current.next(); setBusy(false); setRaw(text); setPacket(null); setDirty(true);
    setWarnings([]); setError(''); setNotice('تحتاج البيانات المعدلة إلى فحص وحفظ جديدين.');
  }
  function manual() { change(pretty(observationTemplate())); setPacket(observationTemplate()); }
  function update(v: ObservationPacket) { change(pretty(v)); setPacket(v); }
  async function request(generation: number, work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (e) { if (gate.current.current(generation)) setError(e instanceof Error ? e.message : 'تعذر إكمال العملية.'); }
    finally { if (gate.current.current(generation)) setBusy(false); }
  }
  function apply(value: ObservationView) {
    setSaved(value); setRaw(value.record.raw_json); setPacket(value.record.packet);
    setWarnings(value.warnings); setDirty(false);
  }
  async function inspect() {
    const generation = gate.current.next(); const text = raw;
    await request(generation, async () => {
      const result = await api<{ packet: unknown; warnings: string[]; trade_permitted: false; execution_enabled: false }>('observations/validate', { method: 'POST', body: JSON.stringify({ raw_json: text, expected_revision: null }) });
      if (!gate.current.current(generation)) return;
      if (result.trade_permitted !== false || result.execution_enabled !== false) throw new Error('استجابة غير صالحة.');
      setPacket(packetSchema.parse(result.packet)); setWarnings(result.warnings);
      setNotice('الصيغة صالحة للمراجعة؛ هذا لا يثبت صحة الأرقام في الصورة.');
    });
  }
  async function save() {
    const generation = gate.current.next(); const text = raw; const previous = saved;
    await request(generation, async () => {
      const result = observationView(await api(previous ? `observations/${previous.record.id}` : 'observations', {
        method: previous ? 'PUT' : 'POST', body: JSON.stringify({ raw_json: text, expected_revision: previous?.record.revision ?? null }),
      }));
      if (!gate.current.current(generation)) return;
      if (result.record.raw_json !== text || result.record.parent_revision !== (previous?.record.revision ?? null) || (previous && result.record.id !== previous.record.id)) throw new Error('الرد لا يطابق النسخة المطلوبة.');
      apply(result); setVersions([]); setNotice('حُفظت نسخة جديدة غير مراجعة.');
    });
  }
  async function review() {
    if (!canReview(saved, dirty) || !saved) return;
    const generation = gate.current.next(); const record = saved.record;
    await request(generation, async () => {
      const result = observationView(await api(`observations/${record.id}/review`, { method: 'POST', body: JSON.stringify({ expected_revision: record.revision, action: 'review_this_revision' }) }));
      if (!gate.current.current(generation)) return;
      if (result.record.id !== record.id || result.record.revision !== record.revision) throw new Error('تغيرت النسخة؛ أعد فتحها.');
      apply(result); setNotice('سُجل تصريحك بمراجعة هذه النسخة؛ لا يمنح ذلك إذن تداول.');
    });
  }
  async function open(id: string, revision?: string) {
    if (dirty && !window.confirm('لديك تعديلات غير محفوظة. هل تريد تركها وفتح النسخة المختارة؟')) return;
    const generation = gate.current.next();
    await request(generation, async () => {
      const value = observationView(await api(`observations/${id}${revision ? `?revision=${revision}` : ''}`));
      if (!gate.current.current(generation)) return;
      if (value.record.id !== id || (revision && value.record.revision !== revision)) throw new Error('هوية النسخة غير مطابقة.');
      apply(value); setVersions([]);
    });
  }
  async function loadHistory(allVersions = false) {
    const generation = gate.current.next(); const id = saved?.record.id;
    await request(generation, async () => {
      const response = await api<unknown>(`observations${allVersions && id ? `?observation_id=${id}` : ''}`);
      if (!gate.current.current(generation)) return;
      if (!Array.isArray(response)) throw new Error('سجل غير صالح.');
      const values = response.map(observationView);
      if (allVersions && values.some(v => v.record.id !== id)) throw new Error('نسخ من ملاحظة أخرى.');
      if (allVersions) setVersions(values); else setHistory(values);
    });
  }
  function fresh() {
    if (dirty && !window.confirm('ترك التعديلات غير المحفوظة وبدء ملاحظة جديدة؟')) return;
    change(''); setSaved(null); setVersions([]); setDirty(false); setNotice('');
  }
  return <section data-testid="observation-panel" dir="rtl" className="mt-6 rounded-xl border border-indigo-400/30 bg-white/5 p-5 text-sm">
    <h2 className="text-lg font-semibold">ملاحظات السوق — إدخال ومراجعة</h2>
    <p className="text-white/60 my-2">أدخل معلوماتك أو الصق النص المنظم. تُحفظ الأصول والتصحيحات منفصلة. هذه ملاحظات معلنة وليست أسعارًا موثقة أو توصية تداول.</p>
    <div className="flex gap-3 flex-wrap my-3">
      <button onClick={fresh} disabled={busy}>ملاحظة جديدة</button>
      <button onClick={manual} disabled={busy}>نموذج إدخال يدوي</button>
      <button onClick={() => void loadHistory()} disabled={busy}>تحميل سجل الملاحظات</button>
    </div>
    <label>البيانات المنقولة JSON<textarea aria-label="البيانات المنقولة JSON" dir="ltr" className={`${field} font-mono text-xs h-44 mt-1`} value={raw} onChange={e => change(e.target.value)} maxLength={100000} /></label>
    {packet && <div className="my-4 space-y-3">
      <div className="grid md:grid-cols-3 gap-3">
        <label>الأداة<select className={field} value={packet.instrument_id} onChange={e => update({ ...packet, instrument_id: e.target.value as 'MES' | 'MNQ' })}><option>MES</option><option>MNQ</option></select></label>
        <label>العقد المؤرخ<input className={field} value={packet.contract ?? ''} placeholder="MESZ26" onChange={e => update({ ...packet, contract: e.target.value || null, frames: packet.frames.map(f => ({ ...f, contract: e.target.value || null })) })} /></label>
        <label>وصف المصدر<input className={field} value={packet.source_reference} onChange={e => update({ ...packet, source_reference: e.target.value })} /></label>
      </div>
      {packet.frames.map((frame, index) => <fieldset className="border border-white/15 p-3 rounded" key={frame.image_id}>
        <legend>الفريم {frame.interval} · {frame.image_id}</legend>
        <div className="grid md:grid-cols-3 gap-3">
          <label>الفريم<select className={field} value={frame.interval} onChange={e => update({ ...packet, frames: packet.frames.map((f, i) => i === index ? { ...f, interval: e.target.value as '5m' | '15m' | '1h' } : f) })}><option>5m</option><option>15m</option><option>1h</option></select></label>
          {(['last', 'bid', 'ask', 'captured_at', 'observed_at', 'last_closed_bar_at'] as const).map(key => <label key={key}>{({last:'آخر سعر',bid:'Bid',ask:'Ask',captured_at:'وقت الالتقاط مع المنطقة الزمنية',observed_at:'وقت السعر مع المنطقة الزمنية',last_closed_bar_at:'آخر إغلاق مؤكد'})[key]}<input className={field} dir="ltr" value={frame[key] ?? ''} placeholder={key.endsWith('_at') ? '2026-10-12T10:00:00Z' : 'غير معلوم'} onChange={e => update({ ...packet, frames: packet.frames.map((f, i) => i === index ? { ...f, [key]: e.target.value || null } : f) })} /></label>)}
          <label>تأخير البيانات<select className={field} value={frame.delay_status} onChange={e => update({ ...packet, frames: packet.frames.map((f, i) => i === index ? { ...f, delay_status: e.target.value as typeof f.delay_status } : f) })}><option value="unknown">غير معلوم</option><option value="delayed">متأخرة</option><option value="real_time_reported">المصدر يصرّح بأنها آنية</option></select></label>
          <label>موضع قراءة الأسعار<input className={field} value={frame.price_evidence} onChange={e => update({ ...packet, frames: packet.frames.map((f, i) => i === index ? { ...f, price_evidence: e.target.value } : f) })} /></label>
        </div>
        {[...frame.printed_levels, ...frame.indicators].map((v, i) => <p key={i}>{v.label}: {v.value ?? 'غير معلوم'} — {v.evidence}</p>)}
        {frame.hypotheses.map((v, i) => <p key={i} className="text-amber-200">فرضية: {v}</p>)}
      </fieldset>)}
      {packet.frames.length < 3 && <button onClick={() => { const interval = (['5m','15m','1h'] as const).find(v => !packet.frames.some(f => f.interval === v)); if (interval) update({ ...packet, frames: [...packet.frames, { ...observationTemplate().frames[0], image_id: `frame-${packet.frames.length+1}`, interval, contract: packet.contract }] }); }}>إضافة فريم</button>}
      <p className="text-amber-200" role="status">{priceAge(packet, now)}</p>
    </div>}
    <div className="flex flex-wrap gap-4 my-3">
      <button disabled={busy || !raw} onClick={() => void inspect()} className="bg-indigo-700 rounded px-4 py-2 disabled:opacity-40">فحص وعرض البيانات</button>
      <button disabled={busy || !raw || (saved !== null && !dirty)} onClick={() => void save()} className="bg-indigo-700 rounded px-4 py-2 disabled:opacity-40">حفظ نسخة</button>
      <button disabled={busy || !canReview(saved, dirty)} onClick={() => void review()} className="border border-white/30 rounded px-4 py-2 disabled:opacity-40">راجعت هذه النسخة</button>
      {saved && <button disabled={busy} onClick={() => void loadHistory(true)}>عرض النسخ السابقة</button>}
    </div>
    {saved && <p>الملاحظة: <span dir="ltr">{saved.record.id}</span> · {dirty ? 'تعديلات غير محفوظة' : saved.reviewed_at ? `مراجعة معلنة: ${saved.reviewed_at}` : 'لم تراجع هذه النسخة'}{saved.record.revision !== saved.latest_revision ? ' · نسخة تاريخية؛ افتح الأحدث قبل تعديلها' : ''}</p>}
    {error && <p role="alert" className="text-red-300 my-2">{error}</p>}
    {notice && <p role="status" className="text-indigo-200 my-2">{notice}</p>}
    {warnings.length > 0 && <ul className="text-amber-200 my-3">{warnings.map(w => <li key={w}>{warningLabel(w)}</li>)}</ul>}
    {history.length > 0 && <div className="my-3"><h3>آخر الملاحظات المحفوظة</h3>{history.map(v => <button key={v.record.id} disabled={busy} className="block underline my-2" onClick={() => void open(v.record.id)}>{v.record.packet.instrument_id} · {v.record.packet.contract ?? 'عقد مجهول'} · {v.record.created_at} · {v.record.id.slice(0,8)}</button>)}</div>}
    {versions.length > 0 && <div className="my-3"><h3>النسخ السابقة</h3>{versions.map(v => <button key={v.record.revision} disabled={busy} className="block underline my-2" onClick={() => void open(v.record.id, v.record.revision)}>{v.record.created_at} · {v.record.revision.slice(0,8)} · {v.reviewed_at ? 'مراجعة معلنة' : 'غير مراجعة'}</button>)}</div>}
  </section>;
}
