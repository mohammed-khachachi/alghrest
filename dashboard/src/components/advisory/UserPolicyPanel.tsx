import { useEffect, useRef, useState } from 'react';
import { advisoryApi as api } from '../../lib/advisoryApi';
import { personalRequest, requestGate, resultCurrent, validateUserResult, type UserResult } from '../../lib/userPolicy';
import type { Evaluation } from './EvaluationPanel';

const input = 'rounded-lg border border-white/15 bg-bg-dark px-3 py-2 text-sm w-full mt-1';
const reasons: Record<string, string> = {
  unsupported_user_policy_exposure: 'يوجد تعرض غير مدعوم؛ لا تُحوّل عقود Mini ولا تتجاهلها.',
  user_micro_cap_exceeded: 'التعرض الحالي يتجاوز سقف 20 Micro.',
  proposed_addition_exceeds_user_micro_cap: 'الإضافة المقترحة تتجاوز السقف المشترك.',
  outside_user_entry_window: 'خارج نافذة الدخول الشخصية 07:00–14:00 UTC.',
  missing_account_observation: 'لا توجد ملاحظة حساب محفوظة.',
  missing_fresh_open_session: 'يلزم سجل جلسة مفتوحة وحديثة.',
  positions_unknown: 'تغطية المراكز غير مؤكدة.', working_orders_unknown: 'تغطية الأوامر غير مؤكدة.',
  stale_or_future_account_observation: 'الملاحظة قديمة أو مؤرخة في المستقبل.',
  unconfirmed_account_observation: 'الملاحظة غير مؤكدة منك.', account_costs_unknown: 'الرسوم غير مؤكدة.',
};
export function UserPolicyPanel({ evaluation, dirty }: { evaluation: Evaluation | null; dirty: boolean }) {
  const [root, setRoot] = useState('MES');
  const [contract, setContract] = useState('');
  const [count, setCount] = useState('1');
  const [result, setResult] = useState<UserResult | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [now, setNow] = useState(Date.now());
  const gate = useRef(requestGate());
  // Render-time identity prevents an old positive value appearing before effects run.
  const key = JSON.stringify([evaluation, dirty, root, contract, count]);
  const currentKey = useRef(key); currentKey.current = key;
  const [resultKey, setResultKey] = useState('');
  useEffect(() => {
    gate.current.next(); setResult(null); setError(''); setBusy(false);
    return () => { gate.current.next(); };
  }, [key]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, []);
  async function check() {
    const ticket = gate.current.next(); const capturedKey = key;
    setResult(null); setError(''); setBusy(true);
    try {
      if (!evaluation || dirty) throw new Error('اختر حسابًا واحفظ جميع التعديلات أولًا.');
      const request = personalRequest(root, contract, count);
      const raw = await api<unknown>(`evaluations/${evaluation.profile.id}/user-policy-check`, { method: 'POST', body: JSON.stringify(request) });
      if (!gate.current.current(ticket) || currentKey.current !== capturedKey) return;
      const value = validateUserResult(raw, evaluation, request, Date.now());
      setNow(Date.now()); setResultKey(capturedKey); setResult(value);
    } catch (reason) {
      if (gate.current.current(ticket) && currentKey.current === capturedKey) setError(reason instanceof Error ? reason.message : 'تعذر الفحص؛ لا توجد سعة مؤهلة.');
    } finally { if (gate.current.current(ticket) && currentKey.current === capturedKey) setBusy(false); }
  }
  const visible = !dirty && evaluation && resultKey === key ? result : null;
  const expired = visible?.state === 'WITHIN_CAP' && !resultCurrent(visible, now);
  useEffect(() => {
    if (result?.state === 'WITHIN_CAP' && !resultCurrent(result, now)) {
      setResult(null); setError('انتهت صلاحية النتيجة أو نافذة الدخول؛ لا توجد سعة معروضة. احفظ ملاحظة حديثة ثم أعد الفحص.');
    }
  }, [result, now]);
  return <section dir="rtl" data-testid="user-policy" className="rounded-xl border border-teal-400/30 bg-bg-surface p-5 space-y-4">
    <h2 className="text-xl text-teal-200">سياسة المستخدم · USER POLICY</h2>
    <p className="text-sm leading-7 text-white/70">MES وMNQ فقط. سقف مشترك ثابت: <strong>20 عقد Micro</strong> للمراكز والأوامر المعلقة معًا، دون مقاصة. الدخول 07:00 شاملًا إلى 14:00 حصريًا UTC/GMT.</p>
    <p className="text-sm text-amber-200">فحص تعرض شخصي للاستشارة والمراجعة البشرية. ليس إذن تداول، ولا اعتمادًا لقواعد الشركة أو الاستراتيجية. احتمال النجاح UNKNOWN. قواعد المستخدم مستقلة عن اعتماد الشركات.</p>
    <p className="text-sm text-white/60">الرصيد الأولي $50,000 · الهدف $3,000 · الخسارة اليومية $1,100 · السحب EOD $2,000 · أفضل يوم أقل من 30% من صافي الربح الكلي. حساب حجم جديد يتطلب ملاحظة مؤكدة لحساب خالٍ؛ هذا الفحص للسقف فقط.</p>
    {!evaluation && <p role="status">اختر سجل الحساب أولًا.</p>}
    {dirty && <p role="status">تعديلات غير محفوظة؛ النتيجة السابقة محجوبة حتى الحفظ وإعادة الفحص.</p>}
    <div className="grid md:grid-cols-3 gap-3">
      <label>Micro المطلوب<select className={input} value={root} onChange={e => { setRoot(e.target.value); setContract(''); }}><option>MES</option><option>MNQ</option></select></label>
      <label>العقد المؤرخ<input dir="ltr" className={input} maxLength={40} placeholder="MESZ26" value={contract} onChange={e => setContract(e.target.value)} /></label>
      <label>كمية الإضافة<input className={input} inputMode="numeric" value={count} onChange={e => setCount(e.target.value)} /></label>
    </div>
    <button disabled={!evaluation || dirty || busy} className="rounded-lg bg-teal-800 px-4 py-2 disabled:opacity-40" onClick={() => void check()}>{busy ? 'جارٍ فحص السجل…' : 'فحص السقف الشخصي'}</button>
    {error && <p role="alert" className="text-red-300">{error}</p>}
    {expired && <p role="status" className="text-amber-200">انتهت صلاحية النتيجة أو نافذة الدخول؛ لا توجد سعة معروضة. احفظ ملاحظة حديثة ثم أعد الفحص.</p>}
    {visible && !expired && <div data-testid="user-policy-result" role="status" className="space-y-2 text-sm">
      <p>الحالة: <strong dir="ltr">{visible.state}</strong> {visible.state === 'WITHIN_CAP' && '— الإضافة داخل السقف الشخصي فقط'}</p>
      <p>التعرض المسجل: <span data-testid="gross">{visible.gross_micro_contracts ?? 'غير معلوم'}</span> Micro · المتبقي المشترك قبل الإضافة: <span data-testid="remaining">{visible.remaining_micro_contracts ?? 'غير معلوم'}</span> Micro</p>
      <p className="break-all">الحساب: {visible.account_id} · وقت الفحص UTC: {visible.generated_at} · وقت الملاحظة: {visible.account_state.observation?.observed_at ?? 'غير متاح'}</p>
      {visible.reasons.map(reason => <p key={reason}>{reasons[reason] ?? reason}</p>)}
      <p>trade_permitted=false · execution_enabled=false · firm_compliance=NOT_ASSESSED</p>
    </div>}
  </section>;
}
