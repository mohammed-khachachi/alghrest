import { z } from 'zod';
import { datedMicro, type Snapshot } from './userPolicy';

const money = z.string().regex(/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/);
const nonnegative = z.string().regex(/^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/);
const revision = z.string().regex(/^[0-9a-f]{64}$/);
const instant = z.string().datetime({ offset: true });
const requestSchema = z.object({
  instrument_id: z.enum(['MES', 'MNQ']), contract: z.string(), entry: nonnegative, stop: nonnegative,
  risk_percent: nonnegative, fees_per_unit: nonnegative, slippage_points: nonnegative,
  safety_buffer: nonnegative, cost_source: z.enum(['user_declared', 'synthetic']),
  cost_reference: z.string().trim().min(1).max(500), costs_reviewed: z.literal(true), expected_account_revision: revision,
}).strict().refine(r => datedMicro(r.instrument_id, r.contract) && Number(r.risk_percent) > 0 && Number(r.risk_percent) <= 1 && Number(r.safety_buffer) > 0 && Number(r.entry) > 0 && Number(r.stop) > 0 && r.entry !== r.stop, 'راجع العقد والسعر والخطر والتكاليف.');
export type UserRiskRequest = z.infer<typeof requestSchema>;
export type PersonalSnapshot = Snapshot & { account_revision: string };
export function personalRiskRequest(value: unknown): UserRiskRequest { return requestSchema.parse(value); }

const schema = z.object({
  schema_version: z.literal(1), algorithm_version: z.literal('user-personal-plan-v1'),
  scope: z.literal('user_personal_risk_plan'), label: z.literal('USER POLICY'), origin: z.literal('user_defined'),
  generated_at: instant, expires_at: instant, profile: z.object({ id: z.string() }).passthrough(),
  sessions: z.array(z.object({ as_of: instant, closed: z.boolean() }).passthrough()), request: requestSchema,
  source_hashes: z.record(revision), account_revision: revision, journal_equity_usd: money,
  state: z.enum(['CALCULATED', 'BLOCKED', 'UNKNOWN']), reasons: z.array(z.string()),
  risk_budget: nonnegative, loss_per_unit: nonnegative, contracts: z.number().int().min(0).max(20),
  estimated_loss_at_stop: nonnegative, daily_loss_remaining: nonnegative, drawdown_remaining: nonnegative,
  minimum_balance: money, consistency_met: z.boolean(), recorded_targets_met: z.boolean(),
  firm_compliance: z.literal('NOT_ASSESSED'), passing_probability: z.literal('UNKNOWN'),
  trade_permitted: z.literal(false), execution_enabled: z.literal(false),
}).strict();
export type UserRiskResult = z.infer<typeof schema>;
function stable(value: unknown): string {
  return JSON.stringify(value, (_key, row: unknown) => row && typeof row === 'object' && !Array.isArray(row)
    ? Object.fromEntries(Object.entries(row).sort(([a], [b]) => a.localeCompare(b))) : row);
}
// Canonical coefficient/exponent strings preserve decimal identity without Number rounding.
function decimalIdentity(value: string): string {
  const [mantissa, exponent = '0'] = value.toLowerCase().split('e');
  const [whole, fraction = ''] = mantissa.split('.');
  const combined = whole + fraction;
  const significant = combined.replace(/^0+/, '').replace(/0+$/, '');
  if (!significant) return '0';
  const trailing = combined.length - combined.replace(/0+$/, '').length;
  return `${significant}e${BigInt(exponent) - BigInt(fraction.length) + BigInt(trailing)}`;
}
function requestIdentity(request: UserRiskRequest): string {
  return stable({ ...request, ...Object.fromEntries(
    (['entry', 'stop', 'risk_percent', 'fees_per_unit', 'slippage_points', 'safety_buffer'] as const)
      .map(key => [key, decimalIdentity(request[key])]),
  ) });
}
export function personalRiskCurrent(result: UserRiskResult, now: number): boolean {
  const generated = Date.parse(result.generated_at), expires = Date.parse(result.expires_at);
  const hour = new Date(now).getUTCHours();
  const last = result.sessions.at(-1);
  const observed = last ? Date.parse(last.as_of) : -Infinity;
  return Number.isFinite(now) && generated <= now && now < expires && now < observed + 1800000
    && expires <= generated + 1800000 && hour >= 7 && hour < 14;
}
export function validatePersonalRisk(raw: unknown, snapshot: PersonalSnapshot, request: UserRiskRequest, now: number): UserRiskResult {
  const result = schema.parse(raw);
  if (stable(result.profile) !== stable(snapshot.profile) || stable(result.sessions) !== stable(snapshot.sessions)
    || requestIdentity(result.request) !== requestIdentity(request) || result.account_revision !== snapshot.account_revision
    || result.account_revision !== request.expected_account_revision) throw new Error('تغير الحساب أو الطلب؛ أعد تحميل السجل والحساب.');
  const sources = ['user_risk.py', 'user_policy.py', 'account.py', 'evaluation.py', 'analysis.py', 'models.py'].map(s => `src/core/advisory/${s}`).sort();
  if (stable(Object.keys(result.source_hashes).sort()) !== stable(sources)) throw new Error('بصمات مصدر النتيجة غير مكتملة.');
  if (result.state === 'CALCULATED') {
    const last = snapshot.sessions.at(-1), a = last?.account;
    if (!last || last.closed || !a || !a.human_confirmed || !a.costs_included || a.currency !== 'USD'
      || a.account_id !== snapshot.profile.id || !a.positions || !a.working_orders || a.positions.length || a.working_orders.length
      || Date.parse(a.observed_at) !== Date.parse(last.as_of) || result.reasons.length || !personalRiskCurrent(result, now)) throw new Error('الحساب غير خالٍ أو الملاحظة غير مكتملة أو انتهت صلاحيتها.');
  } else if (result.contracts !== 0 || result.estimated_loss_at_stop !== '0' || !result.reasons.length) throw new Error('حالة غير مؤهلة تعرض حجمًا غير صالح.');
  return result;
}
