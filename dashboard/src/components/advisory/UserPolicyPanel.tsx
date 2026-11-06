import { useLanguage, languageDirection, tr } from "../../i18n";
import { useEffect, useRef, useState } from 'react';
import { advisoryApi as api } from '../../lib/advisoryApi';
import { personalRequest, requestGate, resultCurrent, validateUserResult, type TCP25Capacity as UserResult } from '../../lib/tcp25Personal';
import type { Evaluation } from './EvaluationPanel';

const input = 'rounded-lg border border-white/15 bg-bg-dark px-3 py-2 text-sm w-full mt-1';
const reasons: Record<string, string> = {
  mini_mixed_or_unsupported_exposure: 'يوجد تعرض غير مدعوم؛ لا تُحوّل عقود Mini ولا تتجاهلها.',
  personal_micro_cap_exceeded: 'الإضافة المقترحة تتجاوز السقف المشترك.',
  proposed_addition_exceeds_personal_cap: 'الإضافة المقترحة تتجاوز السقف المشترك.',
  outside_personal_entry_window: 'خارج نافذة الدخول الشخصية 07:00–14:00 UTC.',
  missing_account_observation: 'لا توجد ملاحظة حساب محفوظة.',
  missing_fresh_open_session: 'يلزم سجل جلسة مفتوحة وحديثة.',
  positions_unknown: 'تغطية المراكز غير مؤكدة.', working_orders_unknown: 'تغطية الأوامر غير مؤكدة.',
  stale_or_future_account_observation: 'الملاحظة قديمة أو مؤرخة في المستقبل.',
  unconfirmed_account_observation: 'الملاحظة غير مؤكدة منك.', account_costs_unknown: 'الرسوم غير مؤكدة.',
};
export function UserPolicyPanel({ evaluation, dirty }: { evaluation: Evaluation | null; dirty: boolean }) {
  useLanguage();
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
      const request = personalRequest(root, contract, count, evaluation as Parameters<typeof personalRequest>[3]);
      const raw = await api<unknown>(`tcp25/personal/evaluations/${evaluation.profile.id}/capacity`, { method: 'POST', body: JSON.stringify(request) });
      if (!gate.current.current(ticket) || currentKey.current !== capturedKey) return;
      const value = validateUserResult(raw, evaluation as Parameters<typeof validateUserResult>[1], request, Date.now());
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
  return <section dir={languageDirection()} data-testid="user-policy" className="rounded-xl border border-teal-400/30 bg-bg-surface p-5 space-y-4">
    <h2 className="text-xl text-teal-200">{tr("سياسة المستخدم · USER POLICY")}</h2>
    <p className="text-sm leading-7 text-white/70">{tr("MES وMNQ فقط. سقف مشترك ثابت: ")}<strong>{tr("10 عقد Micro")}</strong>{tr(" aggregate MES/MNQ open contracts, without netting. Any Mini, mixed or unsupported exposure blocks new Micros. Working orders or unknown coverage provide no capacity. Full Mini support is deferred.")}</p>
    <p className="text-sm text-amber-200">{tr("فحص تعرض شخصي للاستشارة والمراجعة البشرية. ليس إذن تداول، ولا اعتمادًا لقواعد الشركة أو الاستراتيجية. احتمال النجاح UNKNOWN. قواعد المستخدم مستقلة عن اعتماد الشركات.")}</p>
    <p className="text-sm text-white/60">{tr("TCP25: $25,000 / $1,750 / $550 daily / $1,500 EOD. One Mini OR ten Micros, never both; this branch supports Micros only. Firm eligibility BLOCKED; qualified contracts 0.")}</p>
    {!evaluation && <p role="status">{tr("اختر سجل الحساب أولًا.")}</p>}
    {dirty && <p role="status">{tr("تعديلات غير محفوظة؛ النتيجة السابقة محجوبة حتى الحفظ وإعادة الفحص.")}</p>}
    <div className="grid md:grid-cols-3 gap-3">
      <label>{tr("Micro المطلوب")}<select className={input} value={root} onChange={e => { setRoot(e.target.value); setContract(''); }}><option value="MES">{tr("MES")}</option><option value="MNQ">{tr("MNQ")}</option></select></label>
      <label>{tr("العقد المؤرخ")}<input dir="ltr" className={input} maxLength={40} placeholder={tr("MESZ26")} value={contract} onChange={e => setContract(e.target.value)} /></label>
      <label>{tr("كمية الإضافة")}<input className={input} inputMode="numeric" value={count} onChange={e => setCount(e.target.value)} /></label>
    </div>
    <button disabled={!evaluation || dirty || busy || evaluation.read_only_legacy} className="rounded-lg bg-teal-800 px-4 py-2 disabled:opacity-40" onClick={() => void check()}>{tr(busy ? 'جارٍ فحص السجل…' : 'فحص السقف الشخصي')}</button>
    {error && <p role="alert" className="text-red-300">{tr(error)}</p>}
    {expired && <p role="status" className="text-amber-200">{tr("انتهت صلاحية النتيجة أو نافذة الدخول؛ لا توجد سعة معروضة. احفظ ملاحظة حديثة ثم أعد الفحص.")}</p>}
    {visible && !expired && <div data-testid="user-policy-result" role="status" className="space-y-2 text-sm">
      <p>{tr("الحالة: ")}<strong dir="ltr">{tr(visible.state)}</strong> {tr(visible.state === 'WITHIN_CAP' && '— الإضافة داخل السقف الشخصي فقط')}</p>
      <p>{tr("التعرض المسجل: ")}<span data-testid="gross">{tr(visible.gross_micro_contracts ?? 'غير معلوم')}</span>{tr(" Micro · المتبقي المشترك قبل الإضافة: ")}<span data-testid="remaining">{tr(visible.remaining_micro_contracts ?? 'غير معلوم')}</span>{tr(" Micro")}</p>
      <p className="break-all">{tr("الحساب: ")}{tr(visible.account_id)}{tr(" · وقت الفحص UTC: ")}{tr(visible.generated_at)}{tr(" · وقت الملاحظة: ")}{tr(visible.account_state.observation?.observed_at ?? 'غير متاح')}</p>
      {visible.reasons.map(reason => <p key={reason}>{tr(reasons[reason] ?? reason)}</p>)}
      <p>{tr("trade_permitted=false · execution_enabled=false · firm_compliance=NOT_ASSESSED")}</p>
    </div>}
  </section>;
}
