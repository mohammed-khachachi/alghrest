import { z } from 'zod';

const quantity = z.number().int().positive().safe();
const money = z.string().regex(/^-?\d+(?:\.\d+)?$/);
const instant = z.string().datetime({ offset: true });
const exposure = z.object({ instrument_id: z.string(), contract: z.string(), side: z.enum(['BUY', 'SELL']), contracts: quantity });
const position = exposure.extend({ position_id: z.string().min(1), unrealized_pnl: money });
const order = exposure.extend({ order_id: z.string().min(1) });
const observation = z.object({
  account_id: z.string(), source: z.enum(['manual_report', 'replay', 'read_only_report']),
  source_reference: z.string().min(1), observed_at: instant, human_confirmed: z.boolean(),
  costs_included: z.boolean(), currency: z.string(), cash_balance: money,
  unrealized_pnl: money, equity: money, positions: position.array().nullable(), working_orders: order.array().nullable(),
}).passthrough();
export type AccountObservation = z.infer<typeof observation>;
export type PositionDraft = { position_id: string; instrument_id: string; contract: string; side: 'BUY' | 'SELL'; contracts: string; unrealized_pnl: string };
export type OrderDraft = { order_id: string; instrument_id: string; contract: string; side: 'BUY' | 'SELL'; contracts: string };
export type UserRequest = { instrument_id: 'MES' | 'MNQ'; contract: string; additional_contracts: number };
export type Snapshot = { profile: { id: string }; sessions: { as_of: string; closed: boolean; account?: AccountObservation | null }[] };

export function integerQuantity(value: string, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!/^[1-9]\d*$/.test(value)) throw new Error('الكمية عدد صحيح موجب؛ لا كسور أو صيغ علمية.');
  const count = Number(value);
  if (!Number.isSafeInteger(count) || count > maximum) throw new Error('الكمية خارج الحدود.');
  return count;
}
export function datedMicro(root: string, contract: string): boolean {
  return (root === 'MES' || root === 'MNQ') && new RegExp(`^${root}[HMUZ]\\d{2}$`).test(contract);
}
export function personalRequest(root: string, contract: string, count: string): UserRequest {
  if (!datedMicro(root, contract)) throw new Error('أدخل عقد MES أو MNQ مؤرخًا، مثل MESZ26.');
  return { instrument_id: root as 'MES' | 'MNQ', contract, additional_contracts: integerQuantity(count, 1000) };
}
export function buildObservation(input: {
  accountId: string; observedAt: string; source: string; cash: string; unrealized: string; equity: string;
  positions: PositionDraft[]; orders: OrderDraft[]; positionsReviewed: boolean; ordersReviewed: boolean;
  confirmed: boolean; costsIncluded: boolean;
}): AccountObservation | null {
  if (!input.cash && !input.unrealized && !input.equity && !input.source && !input.positions.length && !input.orders.length && !input.confirmed) return null;
  if ((input.positions.length && !input.positionsReviewed) || (input.orders.length && !input.ordersReviewed)) throw new Error('راجع الصفوف المدخلة قبل الحفظ؛ لن تُحذف صفوف التعرض غير المؤكدة.');
  if (input.confirmed && (!input.positionsReviewed || !input.ordersReviewed || !input.costsIncluded)) throw new Error('راجع تغطية المراكز والأوامر وجميع الرسوم قبل التأكيد.');
  // Preserve decimal text; only the existing Decimal backend reconciles monetary sums.
  return observation.parse({ account_id: input.accountId, source: 'manual_report', source_reference: input.source,
    observed_at: input.observedAt, human_confirmed: input.confirmed, costs_included: input.costsIncluded,
    currency: 'USD', cash_balance: input.cash, unrealized_pnl: input.unrealized, equity: input.equity,
    positions: input.positionsReviewed ? input.positions.map(p => ({ ...p, contracts: integerQuantity(p.contracts) })) : null,
    working_orders: input.ordersReviewed ? input.orders.map(o => ({ ...o, contracts: integerQuantity(o.contracts) })) : null,
  });
}

const resultSchema = z.object({
  schema_version: z.literal(1), algorithm_version: z.literal('user-micro-cap-v1'),
  scope: z.literal('user_policy_exposure_check'), label: z.literal('USER POLICY'), origin: z.literal('user_defined'),
  source_reference: z.literal('User-approved MES/MNQ-only cap: 20 gross Micro contracts'),
  maximum_micro_contracts: z.literal(20), entry_start_utc: z.literal('07:00'), entry_end_utc_exclusive: z.literal('14:00'),
  max_account_age_seconds: z.literal(1800), generated_at: instant,
  profile: z.object({ id: z.string() }).passthrough(),
  sessions: z.object({ as_of: instant, closed: z.boolean(), account: observation.nullable().optional() }).passthrough().array(),
  request: z.object({ instrument_id: z.enum(['MES', 'MNQ']), contract: z.string(), additional_contracts: quantity, expected_account_revision: z.string().regex(/^[0-9a-f]{64}$/).nullable().optional() }),
  account_id: z.string(), account_revision: z.string().regex(/^[0-9a-f]{64}$/), journal_equity_usd: money,
  account_state: z.object({ health: z.enum(['KNOWN', 'UNKNOWN', 'INVALID']), reasons: z.string().array(), observation: observation.nullable() }),
  gross_micro_contracts: z.number().int().nonnegative().safe().nullable(),
  remaining_micro_contracts: z.number().int().min(0).max(20).nullable(),
  state: z.enum(['WITHIN_CAP', 'BLOCKED', 'UNKNOWN']), reasons: z.string().array(),
  firm_compliance: z.literal('NOT_ASSESSED'), passing_probability: z.literal('UNKNOWN'),
  trade_permitted: z.literal(false), execution_enabled: z.literal(false),
});
export type UserResult = z.infer<typeof resultSchema>;
function stable(value: unknown): string {
  return JSON.stringify(value, (_key, row: unknown) => row && typeof row === 'object' && !Array.isArray(row)
    ? Object.fromEntries(Object.entries(row).sort(([a], [b]) => a.localeCompare(b))) : row);
}
export function resultExpiry(value: UserResult): number {
  const generated = new Date(value.generated_at);
  const end = Date.UTC(generated.getUTCFullYear(), generated.getUTCMonth(), generated.getUTCDate(), 14);
  const last = value.sessions.at(-1);
  const observed = value.account_state.observation?.observed_at;
  return Math.min(end, last ? Date.parse(last.as_of) + 1800000 : -Infinity, observed ? Date.parse(observed) + 1800000 : -Infinity);
}
export function resultCurrent(value: UserResult, now: number): boolean {
  const generated = Date.parse(value.generated_at);
  const hour = new Date(now).getUTCHours();
  return Number.isFinite(now) && hour >= 7 && hour < 14 && generated <= now + 5000 && now < resultExpiry(value);
}
export function validateUserResult(raw: unknown, snapshot: Snapshot, request: UserRequest, now: number): UserResult {
  const result = resultSchema.parse(raw);
  if (result.account_id !== snapshot.profile.id || stable(result.profile) !== stable(snapshot.profile) || stable(result.sessions) !== stable(snapshot.sessions)
    || result.request.instrument_id !== request.instrument_id || result.request.contract !== request.contract || result.request.additional_contracts !== request.additional_contracts) throw new Error('تغير الحساب أو الطلب؛ أعد تحميل السجل ثم افحصه.');
  if (result.state === 'WITHIN_CAP') {
    const a = result.account_state.observation;
    const last = result.sessions.at(-1);
    if (!a || a.account_id !== result.account_id || a.currency !== 'USD' || !a.human_confirmed || !a.costs_included || !a.positions || !a.working_orders || result.account_state.health !== 'KNOWN' || result.account_state.reasons.length || !last || last.closed || stable(last.account) !== stable(a) || result.reasons.length || !resultCurrent(result, now)) throw new Error('الملاحظة غير مكتملة أو انتهت صلاحيتها.');
    const rows = [...a.positions, ...a.working_orders];
    const gross = rows.reduce((sum, row) => sum + row.contracts, 0);
    if (rows.some(row => !datedMicro(row.instrument_id, row.contract)) || gross !== result.gross_micro_contracts || gross > 20 || result.remaining_micro_contracts !== 20 - gross || gross + request.additional_contracts > 20) throw new Error('نتيجة السقف غير متسقة مع التعرض المسجل.');
    const hour = new Date(result.generated_at).getUTCHours();
    if (hour < 7 || hour >= 14 || Date.parse(a.observed_at) > Date.parse(result.generated_at) || Date.parse(last.as_of) > Date.parse(result.generated_at)) throw new Error('توقيت النتيجة غير صالح.');
  } else if (!result.reasons.length || (result.state === 'BLOCKED' ? result.remaining_micro_contracts !== 0 : result.remaining_micro_contracts !== null)) throw new Error('حالة غير مؤهلة تعرض سعة غير صالحة.');
  return result;
}

// A new input/snapshot invalidates every earlier asynchronous operation.
export function requestGate() {
  let generation = 0;
  return { next: () => ++generation, current: (ticket: number) => ticket === generation };
}
