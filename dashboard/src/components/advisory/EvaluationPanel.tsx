import { useEffect, useRef, useState } from 'react';
import { advisoryApi as api } from '../../lib/advisoryApi';
import { buildObservation, requestGate, type AccountObservation, type PositionDraft, type OrderDraft } from '../../lib/userPolicy';

type Profile = { id: string; program: string; starting_balance: string; profit_target: string; daily_loss_limit: string; maximum_drawdown: string; minimum_trading_days: number; source: string; verified_on: string };
export type Evaluation = {
  account_revision?: string; personal_terms_match?: boolean;
  profile: Profile; balance: string; total_pnl: string; minimum_balance: string;
  drawdown_remaining: string; daily_loss_remaining: string; best_day: string;
  trading_days: number; profit_remaining: string; consistency_met: boolean;
  consistency_total_required: string; breaches: string[]; fresh_observation: boolean;
  account_state: { health: "KNOWN" | "UNKNOWN" | "INVALID"; reasons: string[]; observation: AccountObservation | null };
  rules_current: boolean; recorded_targets_met: boolean; note: string;
  clock: { session_date: string; chicago_time: string; regular_hours_closed: boolean; note: string };
  sessions: { session_date: string; as_of: string; net_pnl: string; lowest_pnl: string; closed: boolean; traded: boolean; notes: string; account?: AccountObservation | null }[];
};
const input = 'rounded-lg border border-white/15 bg-bg-dark px-3 py-2 text-sm w-full mt-1';
const blank = { id: '', program: 'gauntlet_mini', starting_balance: '', profit_target: '', daily_loss_limit: '', maximum_drawdown: '', minimum_trading_days: '', source: '', verified_on: '' };
const labels: Record<string, string> = { id: 'اسم للسجل (حروف لاتينية)', starting_balance: 'رصيد التقييم الاسمي USD', profit_target: 'هدف الربح USD', daily_loss_limit: 'حد الخسارة اليومية USD', maximum_drawdown: 'السحب الأقصى EOD بالدولار', minimum_trading_days: 'الحد الأدنى لأيام التداول', source: 'رابط قواعد برنامجك', verified_on: 'تاريخ مراجعتك للقواعد YYYY-MM-DD' };

export function EvaluationPanel({ onChange, onDirty, personal = false }: { personal?: boolean; onChange: (v: Evaluation | null) => void; onDirty: () => void }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [form, setForm] = useState(personal ? { ...blank, program: 'trader_career_path', starting_balance: '50000', profit_target: '3000', daily_loss_limit: '1100', maximum_drawdown: '2000', minimum_trading_days: '0', source: `${window.location.origin}/assistant-api/user-policy-rules`, verified_on: new Date().toISOString().slice(0, 10) } : blank);
  const [selected, setSelected] = useState('');
  const [status, setStatus] = useState<Evaluation | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState({ session_date: '', as_of: '', net_pnl: '', lowest_pnl: '', closed: false, traded: true, notes: '' });
  const operation = useRef(requestGate());
  useEffect(() => () => { operation.current.next(); }, []);
  const [accountCash, setAccountCash] = useState('');
  const [accountUnrealized, setAccountUnrealized] = useState('');
  const [accountEquity, setAccountEquity] = useState('');
  const [positions, setPositions] = useState<PositionDraft[]>([]);
  const [orders, setOrders] = useState<OrderDraft[]>([]);
  const [positionsReviewed, setPositionsReviewed] = useState(false);
  const [ordersReviewed, setOrdersReviewed] = useState(false);
  const [costsIncluded, setCostsIncluded] = useState(false);
  function dirty() { onDirty(); setAccountConfirmed(false); }
  function updatePosition(index: number, key: keyof PositionDraft, value: string) {
    dirty(); setPositionsReviewed(false); setPositions(rows => rows.map((p, i) => i === index ? { ...p, [key]: value } : p));
  }
  function updateOrder(index: number, key: keyof OrderDraft, value: string) {
    dirty(); setOrdersReviewed(false); setOrders(rows => rows.map((o, i) => i === index ? { ...o, [key]: value } : o));
  }
  const [accountSource, setAccountSource] = useState('');
  const [accountConfirmed, setAccountConfirmed] = useState(false);
  const [rules, setRules] = useState<{ reviewed_on: string; sources: Record<string, string> } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([api<Profile[]>('evaluations'), personal ? Promise.resolve(null) : api<typeof rules>('evaluation-rules')])
      .then(([p, r]) => { if (active) { setProfiles(p); setRules(r); } })
      .catch(() => { if (active) setError('تعذر الاتصال بسجل التقييم المستقل.'); });
    return () => { active = false; };
  }, [personal]);
  function accept(value: Evaluation) {
    setStatus(value); onChange(value);
    setAccountConfirmed(false);
    const last = value.sessions[value.sessions.length - 1];
    const same = last && !last.closed && last.session_date === value.clock.session_date;
    setAccountCash(same && last.account ? last.account.cash_balance : '');
    const account = same ? last.account : null;
    setAccountSource(account?.source_reference ?? '');
    setAccountUnrealized(account?.unrealized_pnl ?? ''); setAccountEquity(account?.equity ?? '');
    setPositions((account?.positions ?? []).map(row => ({ ...row, contracts: String(row.contracts) })));
    setOrders((account?.working_orders ?? []).map(row => ({ ...row, contracts: String(row.contracts) })));
    setPositionsReviewed(account?.positions != null); setOrdersReviewed(account?.working_orders != null);
    setCostsIncluded(account?.costs_included ?? false);
    setSession({ session_date: value.clock.session_date, as_of: same ? last.as_of : '', net_pnl: same ? last.net_pnl : '', lowest_pnl: same ? last.lowest_pnl : '', closed: false, traded: same ? last.traded : true, notes: same ? last.notes : '' });
  }
  async function load(id: string) {
    const ticket = operation.current.next();
    setSelected(id); setStatus(null); onChange(null); setError(''); setBusy(false);
    if (!id) return;
    setBusy(true);
    try { const value = await api<Evaluation>(`evaluations/${id}${personal ? "/personal-status" : ""}`); if (operation.current.current(ticket)) accept(value); }
    catch (e) { if (operation.current.current(ticket)) setError(String(e)); } finally { if (operation.current.current(ticket)) setBusy(false); }
  }
  async function create() {
    const ticket = operation.current.next();
    setBusy(true); setError('');
    try {
      if (Object.values(form).some(v => !v.trim())) throw new Error('املأ جميع حقول القواعد من حساب التقييم الذي اخترته.');
      const p = await api<Profile>('evaluations', { method: 'POST', body: JSON.stringify({ ...form, minimum_trading_days: Number(form.minimum_trading_days) }) });
      const profiles = await api<Profile[]>('evaluations');
      const value = await api<Evaluation>(`evaluations/${p.id}${personal ? "/personal-status" : ""}`);
      if (operation.current.current(ticket)) { setProfiles(profiles); setSelected(p.id); accept(value); }
    } catch (e) { if (operation.current.current(ticket)) setError(String(e)); } finally { if (operation.current.current(ticket)) setBusy(false); }
  }
  async function verifyRules() {
    if (!status) return;
    const ticket = operation.current.next();
    setBusy(true); setError('');
    try {
      await api('evaluations', { method: 'POST', body: JSON.stringify({ ...status.profile, verified_on: new Date().toISOString().slice(0, 10) }) });
      const value = await api<Evaluation>(`evaluations/${selected}${personal ? "/personal-status" : ""}`);
      if (operation.current.current(ticket)) accept(value);
    } catch (e) { if (operation.current.current(ticket)) setError(String(e)); } finally { if (operation.current.current(ticket)) setBusy(false); }
  }
  async function save() {
    const ticket = operation.current.next();
    setBusy(true); setError('');
    try {
      const account = buildObservation({ accountId: selected, observedAt: session.as_of, source: accountSource,
        cash: accountCash, unrealized: accountUnrealized, equity: accountEquity, positions, orders,
        positionsReviewed, ordersReviewed, confirmed: accountConfirmed, costsIncluded });
      const value = await api<Evaluation>(`evaluations/${selected}/session`, { method: 'PUT', body: JSON.stringify({ ...session, account }) });
      const current = personal ? await api<Evaluation>(`evaluations/${selected}/personal-status`) : value;
      if (operation.current.current(ticket)) accept(current);
    } catch (e) { if (operation.current.current(ticket)) setError(String(e)); }
    finally { if (operation.current.current(ticket)) setBusy(false); }
  }
  return <section className="rounded-xl border border-indigo-400/20 bg-bg-surface p-5 space-y-4">
    <div><h2 className="text-xl font-semibold text-indigo-200">{personal ? 'دفتر الحساب الشخصي · USER POLICY' : 'دفتر تقييم شركة التمويل'}</h2><p className="text-sm text-white/50 mt-2 leading-7">{personal ? 'قواعدك الشخصية: رصيد 50,000، هدف 3,000، خسارة يومية 1,100، سحب EOD 2,000. ليس اعتمادًا من شركة. اختر سجلًا أو أنشئ سجلًا شخصيًا صراحةً؛ السجلات السابقة لا تُحوّل تلقائيًا.' : 'Earn2Trade · مرحلة التقييم بسحب نهاية اليوم. أدخل قواعد حسابك كما تظهر في لوحة الشركة. الحساب الممول يحتاج نموذج قواعد مختلفًا؛ لا تستخدمه هنا.'}</p></div>
    {error && <p role="alert" className="text-red-300 text-sm">{error}</p>}
    <label className="block text-sm">سجل التقييم<select className={input} value={selected} onChange={e => void load(e.target.value)}><option value="">لم أضبط حساب تقييم بعد</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.id} · {p.program} · ${p.starting_balance}</option>)}</select></label>
    <details><summary className="cursor-pointer text-indigo-300 text-sm">{personal ? 'إضافة سجل شخصي بقواعدك' : 'إضافة حساب تقييم وقواعده'}</summary><div className="grid md:grid-cols-3 gap-3 mt-4">
      {!personal && <label className="text-sm">البرنامج<select className={input} value={form.program} onChange={e => setForm({ ...form, program: e.target.value })}><option value="gauntlet_mini">Gauntlet Mini</option><option value="trader_career_path">Trader Career Path</option></select></label>}
      {Object.entries(labels).filter(([key]) => !personal || key === 'id' || key === 'verified_on').map(([key, label]) => <label key={key} className="text-sm text-white/60">{personal && key === 'verified_on' ? 'تاريخ مراجعة القواعد الشخصية' : label}<input className={input} value={form[key as keyof typeof form]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></label>)}
    </div><p className="text-xs text-white/40 mt-3">القواعد محفوظة لكل سجل ولا تُعدّل بأثر رجعي. لتغييرها أنشئ سجلًا جديدًا. الاتساق أقل من 30%، وليس مساويًا لها.</p><button disabled={busy} onClick={() => void create()} className="px-4 py-2 rounded-lg bg-indigo-600 mt-3 disabled:opacity-40">{personal ? 'إنشاء السجل الشخصي' : 'حفظ قواعد التقييم'}</button></details>
    {status && <>
      {personal && <p role="status" className="text-sm text-amber-200">{status.personal_terms_match ? 'القيم المالية تطابق قواعدك الشخصية. وسم البرنامج حقل تخزين قديم؛ لا يثبت مصدر السجل أو امتثال الشركة.' : 'قيم هذا السجل لا تطابق قواعدك؛ لن يُحسب حجم شخصي. أنشئ سجلًا منفصلًا دون تعديل التاريخ.'}</p>}
      <div className="text-xs text-white/50 flex flex-wrap gap-3"><a href={status.profile.source} target="_blank" rel="noreferrer" className="text-indigo-300 underline">قواعد هذا السجل</a><span>آخر مراجعة منك: {status.profile.verified_on}</span><button disabled={busy} onClick={() => void verifyRules()} className="text-indigo-300 underline">تأكيد مراجعة القواعد نفسها اليوم</button></div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[['صافي قيمة الحساب', status.balance], ['الحد الأدنى للحساب', status.minimum_balance], ['المتبقي للخسارة اليومية', status.daily_loss_remaining], ['المتبقي للسحب', status.drawdown_remaining], ['المتبقي لهدف الربح', status.profit_remaining], ['أفضل يوم', status.best_day], ['أيام التداول المسجلة', String(status.trading_days)], ['الربح الكلي المطلوب للاتساق', status.consistency_total_required]].map(([label, value]) => <div key={label} className="bg-white/[.03] rounded-lg p-3"><div className="text-xs text-white/40">{label}</div><div className="font-mono mt-2" dir="ltr">{value}</div></div>)}</div>
      <p className="text-xs text-white/50">وقت شيكاغو عند التحديث: {status.clock.chicago_time} · {status.clock.note}</p>
      <div className="text-sm text-amber-200 space-y-2">{status.breaches.length > 0 && <p>تجاوزات مسجلة: {status.breaches.join(', ')} — تخطيط الحجم محجوب.</p>}{!status.fresh_observation && <p>يلزم تحديث جلسة مفتوحة خلال آخر 30 دقيقة لتخطيط الحجم المقيد.</p>}{!personal && !status.rules_current && <p>تجاوزت مراجعة قواعد هذا السجل 30 يومًا. راجع البرنامج قبل التخطيط.</p>}<p>{status.consistency_met ? 'الاتساق محقق في السجل.' : 'الاتساق غير محقق بعد؛ لا يُعد وحده فشلًا في التقييم.'}</p>{status.recorded_targets_met && <p>{personal ? 'الهدف الشخصي مكتمل حسابيًا وفق السجل؛ لا يثبت أداءً مستقبليًا أو اجتياز شركة.' : 'الأهداف المسجلة مكتملة حسابيًا؛ التأكيد النهائي من شركة التمويل بعد مراجعة بقية القواعد.'}</p>}</div>
      <details open><summary className="cursor-pointer">تحديث الجلسة / سجل القرار</summary><fieldset disabled={busy}><p className="text-xs text-white/40 mt-3 leading-6">صافي الربح والخسارة يشمل العمولات والمراكز المفتوحة. أدخل أدنى قيمة وصل إليها خلال الجلسة، حتى لو تعافى لاحقًا. الجلسة تبدأ 17:00 شيكاغو وتحمل تاريخ اليوم التالي. أضف الجلسات السابقة بالترتيب.</p>
        <div className="grid md:grid-cols-2 gap-3 mt-3">{[['session_date', 'تاريخ الجلسة YYYY-MM-DD'], ['as_of', 'وقت الملاحظة ISO مع المنطقة الزمنية'], ['net_pnl', 'صافي ربح/خسارة الجلسة USD'], ['lowest_pnl', 'أدنى ربح/خسارة خلال الجلسة USD']].map(([key, label]) => <label key={key} className="text-sm text-white/60">{label}<input className={input} value={String(session[key as keyof typeof session])} onChange={e => { dirty(); setSession({ ...session, [key]: e.target.value }); }} /></label>)}</div>
        <button className="text-xs text-indigo-300 mt-2" onClick={() => { dirty(); setSession({ ...session, as_of: new Date().toISOString() }); }}>استخدام الوقت الحالي للملاحظة</button>
        <fieldset className="border border-indigo-400/20 rounded-lg p-3 mt-3 space-y-3">
          <legend className="text-sm text-indigo-200">ملاحظة الحساب من كشف المنصة</legend>
          <p className="text-xs text-white/50 leading-6">التخطيط يتطلب رصيدًا مطابقًا للسجل ومراجعة المراكز والأوامر والرسوم. أدخل جميع المراكز والأوامر كما في الكشف، بما فيها التعرض غير المدعوم. التغطية المفقودة ليست حسابًا خاليًا. اكتب القيم النقدية الدقيقة؛ الخادم يتحقق من تطابقها دون حساب مبالغ في المتصفح.</p>
          <label className="block text-sm">الرصيد النقدي بعد الرسوم USD<input className={input} inputMode="decimal" value={accountCash} onChange={e => { dirty(); setAccountCash(e.target.value); }} /></label>
          <label className="block text-sm">إجمالي الربح غير المحقق USD<input className={input} inputMode="decimal" value={accountUnrealized} onChange={e => { dirty(); setAccountUnrealized(e.target.value); }} /></label>
          <label className="block text-sm">صافي قيمة الحساب من الكشف USD<input className={input} inputMode="decimal" value={accountEquity} onChange={e => { dirty(); setAccountEquity(e.target.value); }} /></label>
          <button type="button" className="text-indigo-300 text-sm" disabled={positions.length > 0 || orders.length > 0 || !accountCash} onClick={() => { dirty(); setAccountUnrealized('0'); setAccountEquity(accountCash); setPositionsReviewed(true); setOrdersReviewed(true); }}>راجعت حسابًا خاليًا: قيمة الحساب تساوي النقدي</button>
          <div data-testid="position-entry" className="space-y-3">
            <h3>المراكز المفتوحة ({positions.length})</h3>
            {positions.map((p, index) => <div key={index} className="border border-white/15 rounded-lg p-3 grid md:grid-cols-3 gap-2">
              {([['position_id', 'معرّف المركز'], ['instrument_id', 'رمز المركز'], ['contract', 'عقد المركز'], ['contracts', 'كمية المركز'], ['unrealized_pnl', 'PnL المركز USD']] as const).map(([key, label]) => <label key={key} className="text-sm">{label}<input className={input} value={p[key]} onChange={e => updatePosition(index, key, e.target.value)} /></label>)}
              <label>اتجاه المركز<select className={input} value={p.side} onChange={e => updatePosition(index, 'side', e.target.value)}><option>BUY</option><option>SELL</option></select></label>
              <button type="button" className="text-red-300 text-sm" onClick={() => { dirty(); setPositionsReviewed(false); setPositions(rows => rows.filter((_, i) => i !== index)); }}>حذف صف المركز من التقرير</button>
            </div>)}
            <button type="button" className="text-indigo-300 text-sm" disabled={positions.length >= 200} onClick={() => { dirty(); setPositionsReviewed(false); setPositions(rows => [...rows, { position_id: '', instrument_id: '', contract: '', side: 'BUY', contracts: '', unrealized_pnl: '' }]); }}>إضافة صف مركز</button>
            <label className="flex gap-2 text-sm"><input type="checkbox" checked={positionsReviewed} onChange={e => { dirty(); setPositionsReviewed(e.target.checked); }} />راجعت جميع المراكز؛ القائمة كاملة (فارغة تعني لا مراكز)</label>
          </div>
          <div data-testid="order-entry" className="space-y-3">
            <h3>الأوامر المعلقة ({orders.length})</h3>
            {orders.map((o, index) => <div key={index} className="border border-white/15 rounded-lg p-3 grid md:grid-cols-3 gap-2">
              {([['order_id', 'معرّف الأمر'], ['instrument_id', 'رمز الأمر'], ['contract', 'عقد الأمر'], ['contracts', 'كمية الأمر']] as const).map(([key, label]) => <label key={key} className="text-sm">{label}<input className={input} value={o[key]} onChange={e => updateOrder(index, key, e.target.value)} /></label>)}
              <label>اتجاه الأمر<select className={input} value={o.side} onChange={e => updateOrder(index, 'side', e.target.value)}><option>BUY</option><option>SELL</option></select></label>
              <button type="button" className="text-red-300 text-sm" onClick={() => { dirty(); setOrdersReviewed(false); setOrders(rows => rows.filter((_, i) => i !== index)); }}>حذف صف الأمر من التقرير</button>
            </div>)}
            <button type="button" className="text-indigo-300 text-sm" disabled={orders.length >= 200} onClick={() => { dirty(); setOrdersReviewed(false); setOrders(rows => [...rows, { order_id: '', instrument_id: '', contract: '', side: 'BUY', contracts: '' }]); }}>إضافة صف أمر</button>
            <label className="flex gap-2 text-sm"><input type="checkbox" checked={ordersReviewed} onChange={e => { dirty(); setOrdersReviewed(e.target.checked); }} />راجعت جميع الأوامر؛ القائمة كاملة (فارغة تعني لا أوامر)</label>
          </div>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={costsIncluded} onChange={e => { dirty(); setCostsIncluded(e.target.checked); }} />القيم تشمل جميع العمولات والرسوم</label>
          <label className="block text-sm">مرجع الكشف أو الملاحظة<input className={input} maxLength={500} value={accountSource} onChange={e => { dirty(); setAccountSource(e.target.value); }} /></label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={accountConfirmed} onChange={e => { onDirty(); setAccountConfirmed(e.target.checked); }} />أؤكد الملاحظة في وقتها: القيم مطابقة للكشف وجميع المراكز والأوامر والرسوم مغطاة</label>
          <p role="status" className="text-xs text-amber-200">{status.account_state.health === 'KNOWN' ? 'الملاحظة المحفوظة مكتملة حسابيًا؛ مصدرها تقرير مُدخل، وليست مصادقة من الوسيط أو إذنًا للتداول.' : 'حالة الحساب المحفوظة غير مكتملة أو قديمة؛ التخطيط محجوب حتى حفظ ملاحظة صحيحة.'}</p>
        </fieldset>
        <label className="block text-sm mt-3">الخطة، سبب الدخول، المراجعة<textarea className={input} maxLength={2000} value={session.notes} onChange={e => { dirty(); setSession({ ...session, notes: e.target.value }); }} /></label>
        <div className="flex flex-wrap gap-4 text-sm my-3"><label><input type="checkbox" checked={session.traded} onChange={e => { dirty(); setSession({ ...session, traded: e.target.checked }); }} /> جرى تداول في الجلسة</label><label><input type="checkbox" checked={session.closed} onChange={e => { dirty(); setSession({ ...session, closed: e.target.checked }); }} /> إنهاء الجلسة بعد 16:00 شيكاغو — المراكز والأوامر مغلقة</label></div>
        <button disabled={busy} className="px-4 py-2 rounded-lg bg-indigo-600 disabled:opacity-40" onClick={() => void save()}>حفظ ملاحظة الجلسة</button>
      </fieldset></details>
      <details><summary className="text-sm cursor-pointer">الجلسات المحفوظة ({status.sessions.length})</summary><div className="overflow-x-auto"><table className="w-full text-sm mt-3 text-right"><thead><tr><th>الجلسة</th><th>الصافي</th><th>الأدنى</th><th>الحالة</th><th>المراجعة</th></tr></thead><tbody>{status.sessions.map(s => <tr key={s.session_date} className="border-t border-white/10"><td className="py-3">{s.session_date}</td><td>{s.net_pnl}</td><td>{s.lowest_pnl}</td><td>{s.closed ? 'نهائية' : 'مفتوحة'}</td><td className="max-w-sm break-words">{s.notes}</td></tr>)}</tbody></table></div></details>
      <p className="text-xs text-white/40 leading-6">{status.note}</p>
    </>}
    {rules && <details><summary className="text-xs text-indigo-300 cursor-pointer">المراجع الرسمية · مراجعة {rules.reviewed_on}</summary><div className="flex flex-wrap gap-3 mt-3">{Object.entries(rules.sources).map(([name, url]) => <a key={name} href={url} target="_blank" rel="noreferrer" className="text-xs text-indigo-200 underline">{name.replaceAll('_', ' ')}</a>)}</div></details>}
  </section>;
}
