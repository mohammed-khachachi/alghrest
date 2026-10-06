import { useEffect, useState } from 'react';
import { advisoryApi as api } from '../../lib/advisoryApi';

type Profile = { id: string; program: string; starting_balance: string; profit_target: string; daily_loss_limit: string; maximum_drawdown: string; minimum_trading_days: number; source: string; verified_on: string };
export type Evaluation = {
  profile: Profile; balance: string; total_pnl: string; minimum_balance: string;
  drawdown_remaining: string; daily_loss_remaining: string; best_day: string;
  trading_days: number; profit_remaining: string; consistency_met: boolean;
  consistency_total_required: string; breaches: string[]; fresh_observation: boolean;
  account_state: { health: "KNOWN" | "UNKNOWN" | "INVALID"; reasons: string[]; observation: { source: string } | null };
  rules_current: boolean; recorded_targets_met: boolean; note: string;
  clock: { session_date: string; chicago_time: string; regular_hours_closed: boolean; note: string };
  sessions: { session_date: string; as_of: string; net_pnl: string; lowest_pnl: string; closed: boolean; traded: boolean; notes: string; account?: { cash_balance: string; source_reference: string } | null }[];
};
const input = 'rounded-lg border border-white/15 bg-bg-dark px-3 py-2 text-sm w-full mt-1';
const blank = { id: '', program: 'gauntlet_mini', starting_balance: '', profit_target: '', daily_loss_limit: '', maximum_drawdown: '', minimum_trading_days: '', source: '', verified_on: '' };
const labels: Record<string, string> = { id: 'اسم للسجل (حروف لاتينية)', starting_balance: 'رصيد التقييم الاسمي USD', profit_target: 'هدف الربح USD', daily_loss_limit: 'حد الخسارة اليومية USD', maximum_drawdown: 'السحب الأقصى EOD بالدولار', minimum_trading_days: 'الحد الأدنى لأيام التداول', source: 'رابط قواعد برنامجك', verified_on: 'تاريخ مراجعتك للقواعد YYYY-MM-DD' };

export function EvaluationPanel({ onChange, onDirty }: { onChange: (v: Evaluation | null) => void; onDirty: () => void }) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [form, setForm] = useState(blank);
  const [selected, setSelected] = useState('');
  const [status, setStatus] = useState<Evaluation | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [session, setSession] = useState({ session_date: '', as_of: '', net_pnl: '', lowest_pnl: '', closed: false, traded: true, notes: '' });
  const [accountCash, setAccountCash] = useState('');
  const [accountSource, setAccountSource] = useState('');
  const [accountConfirmed, setAccountConfirmed] = useState(false);
  const [rules, setRules] = useState<{ reviewed_on: string; sources: Record<string, string> } | null>(null);
  useEffect(() => {
    let active = true;
    Promise.all([api<Profile[]>('evaluations'), api<typeof rules>('evaluation-rules')])
      .then(([p, r]) => { if (active) { setProfiles(p); setRules(r); } })
      .catch(() => { if (active) setError('تعذر الاتصال بسجل التقييم المستقل.'); });
    return () => { active = false; };
  }, []);
  function accept(value: Evaluation) {
    setStatus(value); onChange(value);
    setAccountConfirmed(false);
    const last = value.sessions[value.sessions.length - 1];
    const same = last && !last.closed && last.session_date === value.clock.session_date;
    setAccountCash(same && last.account ? last.account.cash_balance : '');
    setAccountSource(same && last.account ? last.account.source_reference : '');
    setSession({ session_date: value.clock.session_date, as_of: new Date().toISOString(), net_pnl: same ? last.net_pnl : '', lowest_pnl: same ? last.lowest_pnl : '', closed: false, traded: same ? last.traded : true, notes: same ? last.notes : '' });
  }
  async function load(id: string) {
    setSelected(id); setStatus(null); onChange(null); setError('');
    if (!id) return;
    setBusy(true);
    try { accept(await api<Evaluation>(`evaluations/${id}`)); }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function create() {
    setBusy(true); setError('');
    try {
      if (Object.values(form).some(v => !v.trim())) throw new Error('املأ جميع حقول القواعد من حساب التقييم الذي اخترته.');
      const p = await api<Profile>('evaluations', { method: 'POST', body: JSON.stringify({ ...form, minimum_trading_days: Number(form.minimum_trading_days) }) });
      setProfiles(await api<Profile[]>('evaluations')); setSelected(p.id);
      accept(await api<Evaluation>(`evaluations/${p.id}`));
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function verifyRules() {
    if (!status) return;
    setBusy(true); setError('');
    try {
      await api('evaluations', { method: 'POST', body: JSON.stringify({ ...status.profile, verified_on: new Date().toISOString().slice(0, 10) }) });
      accept(await api<Evaluation>(`evaluations/${selected}`));
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function save() {
    setBusy(true); setError('');
    try {
      if (accountConfirmed && (!accountCash.trim() || !accountSource.trim())) throw new Error('أدخل الرصيد النقدي ومصدر الملاحظة قبل تأكيدها.');
      const account = accountConfirmed ? {
        account_id: selected, source: 'manual_report', source_reference: accountSource,
        observed_at: session.as_of, human_confirmed: true, costs_included: true, currency: 'USD',
        cash_balance: accountCash, unrealized_pnl: '0', equity: accountCash,
        positions: [], working_orders: [],
      } : null;
      accept(await api<Evaluation>(`evaluations/${selected}/session`, { method: 'PUT', body: JSON.stringify({ ...session, account }) }));
    }
    catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  return <section className="rounded-xl border border-indigo-400/20 bg-bg-surface p-5 space-y-4">
    <div><h2 className="text-xl font-semibold text-indigo-200">دفتر تقييم شركة التمويل</h2><p className="text-sm text-white/50 mt-2 leading-7">Earn2Trade · مرحلة التقييم بسحب نهاية اليوم. أدخل قواعد حسابك كما تظهر في لوحة الشركة. الحساب الممول يحتاج نموذج قواعد مختلفًا؛ لا تستخدمه هنا.</p></div>
    {error && <p role="alert" className="text-red-300 text-sm">{error}</p>}
    <label className="block text-sm">سجل التقييم<select disabled={busy} className={input} value={selected} onChange={e => void load(e.target.value)}><option value="">لم أضبط حساب تقييم بعد</option>{profiles.map(p => <option key={p.id} value={p.id}>{p.id} · {p.program} · ${p.starting_balance}</option>)}</select></label>
    <details><summary className="cursor-pointer text-indigo-300 text-sm">إضافة حساب تقييم وقواعده</summary><div className="grid md:grid-cols-3 gap-3 mt-4">
      <label className="text-sm">البرنامج<select className={input} value={form.program} onChange={e => setForm({ ...form, program: e.target.value })}><option value="gauntlet_mini">Gauntlet Mini</option><option value="trader_career_path">Trader Career Path</option></select></label>
      {Object.entries(labels).map(([key, label]) => <label key={key} className="text-sm text-white/60">{label}<input className={input} value={form[key as keyof typeof form]} onChange={e => setForm({ ...form, [key]: e.target.value })} /></label>)}
    </div><p className="text-xs text-white/40 mt-3">القواعد محفوظة لكل سجل ولا تُعدّل بأثر رجعي. لتغييرها أنشئ سجلًا جديدًا. الاتساق أقل من 30%، وليس مساويًا لها.</p><button disabled={busy} onClick={() => void create()} className="px-4 py-2 rounded-lg bg-indigo-600 mt-3 disabled:opacity-40">حفظ قواعد التقييم</button></details>
    {status && <>
      <div className="text-xs text-white/50 flex flex-wrap gap-3"><a href={status.profile.source} target="_blank" rel="noreferrer" className="text-indigo-300 underline">قواعد هذا السجل</a><span>آخر مراجعة منك: {status.profile.verified_on}</span><button disabled={busy} onClick={() => void verifyRules()} className="text-indigo-300 underline">تأكيد مراجعة القواعد نفسها اليوم</button></div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">{[['صافي قيمة الحساب', status.balance], ['الحد الأدنى للحساب', status.minimum_balance], ['المتبقي للخسارة اليومية', status.daily_loss_remaining], ['المتبقي للسحب', status.drawdown_remaining], ['المتبقي لهدف الربح', status.profit_remaining], ['أفضل يوم', status.best_day], ['أيام التداول المسجلة', String(status.trading_days)], ['الربح الكلي المطلوب للاتساق', status.consistency_total_required]].map(([label, value]) => <div key={label} className="bg-white/[.03] rounded-lg p-3"><div className="text-xs text-white/40">{label}</div><div className="font-mono mt-2" dir="ltr">{value}</div></div>)}</div>
      <p className="text-xs text-white/50">وقت شيكاغو عند التحديث: {status.clock.chicago_time} · {status.clock.note}</p>
      <div className="text-sm text-amber-200 space-y-2">{status.breaches.length > 0 && <p>تجاوزات مسجلة: {status.breaches.join(', ')} — تخطيط الحجم محجوب.</p>}{!status.fresh_observation && <p>يلزم تحديث جلسة مفتوحة خلال آخر 30 دقيقة لتخطيط الحجم المقيد.</p>}{!status.rules_current && <p>تجاوزت مراجعة قواعد هذا السجل 30 يومًا. راجع البرنامج قبل التخطيط.</p>}<p>{status.consistency_met ? 'الاتساق محقق في السجل.' : 'الاتساق غير محقق بعد؛ لا يُعد وحده فشلًا في التقييم.'}</p>{status.recorded_targets_met && <p>الأهداف المسجلة مكتملة حسابيًا؛ التأكيد النهائي من شركة التمويل بعد مراجعة بقية القواعد.</p>}</div>
      <details open><summary className="cursor-pointer">تحديث الجلسة / سجل القرار</summary><p className="text-xs text-white/40 mt-3 leading-6">صافي الربح والخسارة يشمل العمولات والمراكز المفتوحة. أدخل أدنى قيمة وصل إليها خلال الجلسة، حتى لو تعافى لاحقًا. الجلسة تبدأ 17:00 شيكاغو وتحمل تاريخ اليوم التالي. أضف الجلسات السابقة بالترتيب.</p>
        <div className="grid md:grid-cols-2 gap-3 mt-3">{[['session_date', 'تاريخ الجلسة YYYY-MM-DD'], ['as_of', 'وقت الملاحظة ISO مع المنطقة الزمنية'], ['net_pnl', 'صافي ربح/خسارة الجلسة USD'], ['lowest_pnl', 'أدنى ربح/خسارة خلال الجلسة USD']].map(([key, label]) => <label key={key} className="text-sm text-white/60">{label}<input className={input} value={String(session[key as keyof typeof session])} onChange={e => { onDirty(); setAccountConfirmed(false); setSession({ ...session, [key]: e.target.value }); }} /></label>)}</div>
        <button className="text-xs text-indigo-300 mt-2" onClick={() => { onDirty(); setAccountConfirmed(false); setSession({ ...session, as_of: new Date().toISOString() }); }}>استخدام الوقت الحالي للملاحظة</button>
        <fieldset className="border border-indigo-400/20 rounded-lg p-3 mt-3 space-y-3">
          <legend className="text-sm text-indigo-200">ملاحظة الحساب من كشف المنصة</legend>
          <p className="text-xs text-white/50 leading-6">التخطيط يتطلب رصيدًا مطابقًا للسجل ومراجعة المراكز والأوامر والرسوم. هذه المرحلة تخطط للحساب الخالي من المراكز والأوامر فقط؛ سجّل الملاحظة دون تأكيد إذا كانت التغطية غير مكتملة.</p>
          <label className="block text-sm">الرصيد النقدي بعد الرسوم USD<input className={input} inputMode="decimal" value={accountCash} onChange={e => { onDirty(); setAccountConfirmed(false); setAccountCash(e.target.value); }} /></label>
          <label className="block text-sm">مرجع الكشف أو الملاحظة<input className={input} maxLength={500} value={accountSource} onChange={e => { onDirty(); setAccountConfirmed(false); setAccountSource(e.target.value); }} /></label>
          <label className="flex gap-2 text-sm"><input type="checkbox" checked={accountConfirmed} onChange={e => { onDirty(); setAccountConfirmed(e.target.checked); }} />راجعت الحساب في وقت الملاحظة: لا توجد مراكز أو أوامر معلقة، والرصيد وصافي PnL يشملان جميع الرسوم</label>
          <p role="status" className="text-xs text-amber-200">{status.account_state.health === 'KNOWN' ? 'الملاحظة المحفوظة مكتملة حسابيًا؛ مصدرها تقرير مُدخل، وليست مصادقة من الوسيط أو إذنًا للتداول.' : 'حالة الحساب المحفوظة غير مكتملة أو قديمة؛ التخطيط محجوب حتى حفظ ملاحظة صحيحة.'}</p>
        </fieldset>
        <label className="block text-sm mt-3">الخطة، سبب الدخول، المراجعة<textarea className={input} maxLength={2000} value={session.notes} onChange={e => setSession({ ...session, notes: e.target.value })} /></label>
        <div className="flex flex-wrap gap-4 text-sm my-3"><label><input type="checkbox" checked={session.traded} onChange={e => { onDirty(); setSession({ ...session, traded: e.target.checked }); }} /> جرى تداول في الجلسة</label><label><input type="checkbox" checked={session.closed} onChange={e => { onDirty(); setSession({ ...session, closed: e.target.checked }); }} /> إنهاء الجلسة بعد 16:00 شيكاغو — المراكز والأوامر مغلقة</label></div>
        <button disabled={busy} className="px-4 py-2 rounded-lg bg-indigo-600 disabled:opacity-40" onClick={() => void save()}>حفظ ملاحظة الجلسة</button>
      </details>
      <details><summary className="text-sm cursor-pointer">الجلسات المحفوظة ({status.sessions.length})</summary><div className="overflow-x-auto"><table className="w-full text-sm mt-3 text-right"><thead><tr><th>الجلسة</th><th>الصافي</th><th>الأدنى</th><th>الحالة</th><th>المراجعة</th></tr></thead><tbody>{status.sessions.map(s => <tr key={s.session_date} className="border-t border-white/10"><td className="py-3">{s.session_date}</td><td>{s.net_pnl}</td><td>{s.lowest_pnl}</td><td>{s.closed ? 'نهائية' : 'مفتوحة'}</td><td className="max-w-sm break-words">{s.notes}</td></tr>)}</tbody></table></div></details>
      <p className="text-xs text-white/40 leading-6">{status.note}</p>
    </>}
    {rules && <details><summary className="text-xs text-indigo-300 cursor-pointer">المراجع الرسمية · مراجعة {rules.reviewed_on}</summary><div className="flex flex-wrap gap-3 mt-3">{Object.entries(rules.sources).map(([name, url]) => <a key={name} href={url} target="_blank" rel="noreferrer" className="text-xs text-indigo-200 underline">{name.replaceAll('_', ' ')}</a>)}</div></details>}
  </section>;
}
