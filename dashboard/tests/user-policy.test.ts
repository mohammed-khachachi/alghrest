import test from 'node:test';
import assert from 'node:assert/strict';
import { buildObservation, datedMicro, integerQuantity, personalRequest, requestGate, resultCurrent, resultExpiry, validateUserResult, type Snapshot, type UserResult } from '../src/lib/userPolicy';

const now = Date.parse('2026-10-08T10:00:00Z');
const request = personalRequest('MES', 'MESZ26', '1');
const draft = { accountId: 'synthetic', observedAt: '2026-10-08T10:00:00Z', source: 'SYNTHETIC MECHANICS ONLY', cash: '50000.000000000000000001', unrealized: '0', equity: '50000.000000000000000001', positions: [], orders: [], positionsReviewed: true, ordersReviewed: true, confirmed: true, costsIncluded: true };
function example(gross = 0) {
  const account = buildObservation(draft)!;
  if (gross) account.positions = [{ position_id: 'p1', instrument_id: 'MES', contract: 'MESZ26', side: 'BUY', contracts: gross, unrealized_pnl: '0' }];
  const snapshot: Snapshot = { profile: { id: 'synthetic' }, sessions: [{ as_of: draft.observedAt, closed: false, account }] };
  const raw = { schema_version: 1, algorithm_version: 'user-micro-cap-v1', scope: 'user_policy_exposure_check', label: 'USER POLICY', origin: 'user_defined', source_reference: 'User-approved MES/MNQ-only cap: 20 gross Micro contracts', maximum_micro_contracts: 20, entry_start_utc: '07:00', entry_end_utc_exclusive: '14:00', max_account_age_seconds: 1800, generated_at: draft.observedAt, profile: snapshot.profile, sessions: snapshot.sessions, request, account_id: 'synthetic', account_revision: 'a'.repeat(64), journal_equity_usd: draft.equity, account_state: { health: 'KNOWN', reasons: [], observation: account }, gross_micro_contracts: gross, remaining_micro_contracts: 20 - gross, state: 'WITHIN_CAP', reasons: [], firm_compliance: 'NOT_ASSESSED', passing_probability: 'UNKNOWN', trade_permitted: false, execution_enabled: false };
  return { raw, snapshot };
}
test('fixed shared capacity for reviewed flat account', () => {
  const { raw, snapshot } = example(); const result = validateUserResult(raw, snapshot, request, now);
  assert.equal(result.remaining_micro_contracts, 20); assert.equal(result.trade_permitted, false); assert.equal(result.execution_enabled, false);
});
test('10 MES plus 9 MNQ orders count gross even opposite side', () => {
  const { raw, snapshot } = example(10);
  raw.account_state.observation.working_orders = [{ order_id: 'o1', instrument_id: 'MNQ', contract: 'MNQH27', side: 'SELL', contracts: 9 }];
  raw.gross_micro_contracts = 19; raw.remaining_micro_contracts = 1;
  assert.equal(validateUserResult(raw, snapshot, request, now).remaining_micro_contracts, 1);
});
for (const gross of [20, 21]) test(`existing ${gross} blocks additions`, () => {
  const { raw, snapshot } = example(gross);
  assert.throws(() => validateUserResult(raw, snapshot, request, now));
  Object.assign(raw, { state: 'BLOCKED', reasons: ['proposed_addition_exceeds_user_micro_cap'], remaining_micro_contracts: 0 });
  assert.equal(validateUserResult(raw, snapshot, request, now).remaining_micro_contracts, 0);
});
for (const key of ['trade_permitted', 'execution_enabled']) test(`${key} true rejected`, () => {
  const { raw, snapshot } = example(); assert.throws(() => validateUserResult({ ...raw, [key]: true }, snapshot, request, now));
});
for (const [key, value] of [['maximum_micro_contracts', 21], ['scope', 'firm_permission'], ['firm_compliance', 'VERIFIED'], ['origin', 'official'], ['passing_probability', '95%']]) test(`reject altered ${key}`, () => {
  const { raw, snapshot } = example(); assert.throws(() => validateUserResult({ ...raw, [key as string]: value }, snapshot, request, now));
});
test('Mini and malformed dated contract cannot qualify', () => {
  assert.equal(datedMicro('ES', 'ESZ26'), false); assert.equal(datedMicro('MES', 'MES1!'), false);
  const { raw, snapshot } = example(1); raw.account_state.observation.positions![0].instrument_id = 'ES';
  raw.account_state.observation.positions![0].contract = 'ESZ26';
  assert.throws(() => validateUserResult(raw, snapshot, request, now));
});
for (const count of ['0', '-1', '1.2', '1e1', '', ' 1', '9007199254740992', '01']) test(`invalid quantity ${JSON.stringify(count)}`, () => assert.throws(() => integerQuantity(count)));
test('request validates root, dated contract and quantity without Mini conversion', () => {
  assert.throws(() => personalRequest('ES', 'ESZ26', '1')); assert.throws(() => personalRequest('MES', 'MNQZ26', '1'));
  assert.throws(() => personalRequest('MES', 'MESZ26', '1001')); assert.equal(integerQuantity('20'), 20);
});
test('exact decimal strings retained with no floating point monetary sum', () => {
  const value = buildObservation(draft)!; assert.equal(value.cash_balance, draft.cash); assert.equal(value.equity, draft.equity);
  assert.throws(() => buildObservation({ ...draft, equity: 'NaN' }));
});
test('unknown coverage differs from explicit reviewed empty arrays', () => {
  const missing = buildObservation({ ...draft, confirmed: false, positionsReviewed: false, ordersReviewed: false })!;
  assert.equal(missing.positions, null); assert.equal(missing.working_orders, null);
  assert.deepEqual(buildObservation(draft)!.positions, []);
  assert.throws(() => buildObservation({ ...draft, positionsReviewed: false }));
});
test('unreviewed entered rows cannot silently disappear during save', () => {
  assert.throws(() => buildObservation({ ...draft, confirmed: false, positionsReviewed: false, positions: [{ position_id: 'mini', instrument_id: 'ES', contract: 'ESZ26', side: 'BUY', contracts: '1', unrealized_pnl: '0' }] }));
  const a = buildObservation({ ...draft, positions: [{ position_id: 'mini', instrument_id: 'ES', contract: 'ESZ26', side: 'BUY', contracts: '1', unrealized_pnl: '0' }] })!;
  assert.equal(a.positions![0].instrument_id, 'ES');
});
test('missing and malformed observations never produce a positive result', () => {
  const { raw, snapshot } = example();
  for (const observation of [null, { ...raw.account_state.observation, positions: null }, { ...raw.account_state.observation, human_confirmed: false }, { ...raw.account_state.observation, costs_included: false }]) assert.throws(() => validateUserResult({ ...raw, account_state: { ...raw.account_state, observation } }, snapshot, request, now));
  assert.throws(() => validateUserResult({}, snapshot, request, now));
});
test('UNKNOWN and BLOCKED expose no positive capacity and require reasons', () => {
  const { raw, snapshot } = example();
  assert.throws(() => validateUserResult({ ...raw, state: 'UNKNOWN' }, snapshot, request, now));
  const result = validateUserResult({ ...raw, state: 'UNKNOWN', reasons: ['positions_unknown'], remaining_micro_contracts: null }, snapshot, request, now);
  assert.equal(result.remaining_micro_contracts, null);
});
test('account, request and journal change invalidate captured results', () => {
  const { raw, snapshot } = example();
  assert.throws(() => validateUserResult(raw, { ...snapshot, profile: { id: 'other' } }, request, now));
  assert.throws(() => validateUserResult(raw, { ...snapshot, sessions: [] }, request, now));
  assert.throws(() => validateUserResult(raw, snapshot, { ...request, additional_contracts: 2 }, now));
  assert.throws(() => validateUserResult({ ...raw, account_id: 'other' }, snapshot, request, now));
});
test('expiry earlier of observation freshness and UTC window; never renew on read', () => {
  const { raw, snapshot } = example(); const result = validateUserResult(raw, snapshot, request, now);
  assert.equal(resultExpiry(result), now + 1800000); assert.equal(resultCurrent(result, now + 1800000), false);
  assert.equal(resultCurrent(result, Date.parse('2026-10-08T14:00:00Z')), false);
  assert.equal(resultCurrent(result, Date.parse('2026-10-08T06:59:59Z')), false);
  const nearEnd = { ...result, generated_at: '2026-10-08T13:55:00Z', sessions: [{ ...result.sessions[0], as_of: '2026-10-08T13:55:00Z' }], account_state: { ...result.account_state, observation: { ...result.account_state.observation!, observed_at: '2026-10-08T13:55:00Z' } } };
  assert.equal(resultExpiry(nearEnd as UserResult), Date.parse('2026-10-08T14:00:00Z'));
});
test('future or stale snapshots cannot be shown as positive', () => {
  const { raw, snapshot } = example(); assert.throws(() => validateUserResult(raw, snapshot, request, now - 60000));
  assert.throws(() => validateUserResult(raw, snapshot, request, now + 1800001));
});
test('generation guard discards delayed account/request replies after dirty change or failure', async () => {
  const gate = requestGate(); const old = gate.next(); const later = gate.next();
  await Promise.resolve(); assert.equal(gate.current(old), false); assert.equal(gate.current(later), true);
  gate.next(); assert.equal(gate.current(later), false);
});
