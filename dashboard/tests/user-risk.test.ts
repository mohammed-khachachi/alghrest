import test from 'node:test';
import assert from 'node:assert/strict';
import { personalRiskCurrent, personalRiskRequest, validatePersonalRisk } from '../src/lib/userRisk';
import { buildObservation, requestGate } from '../src/lib/userPolicy';

const now = Date.parse('2026-10-08T10:00:00Z');
const account = buildObservation({ accountId: 'synthetic', observedAt: '2026-10-08T10:00:00Z', source: 'SYNTHETIC MECHANICS ONLY', cash: '50000', unrealized: '0', equity: '50000', positions: [], orders: [], positionsReviewed: true, ordersReviewed: true, confirmed: true, costsIncluded: true })!;
const snapshot = { profile: { id: 'synthetic' }, sessions: [{ as_of: account.observed_at, closed: false, account }], account_revision: 'a'.repeat(64) };
const request = personalRiskRequest({ instrument_id: 'MES', contract: 'MESZ26', entry: '5000', stop: '4990', risk_percent: '0.5', fees_per_unit: '2', slippage_points: '0.25', safety_buffer: '10', cost_source: 'synthetic', cost_reference: 'SYNTHETIC MECHANICS ONLY', costs_reviewed: true, expected_account_revision: snapshot.account_revision });
const raw = { schema_version: 1, algorithm_version: 'user-personal-plan-v1', scope: 'user_personal_risk_plan', label: 'USER POLICY', origin: 'user_defined', generated_at: account.observed_at, expires_at: '2026-10-08T10:30:00Z', profile: snapshot.profile, sessions: snapshot.sessions, request, source_hashes: Object.fromEntries(['user_risk.py','user_policy.py','account.py','evaluation.py','analysis.py','models.py'].map(s => ['src/core/advisory/' + s, 'b'.repeat(64)])), account_revision: snapshot.account_revision, journal_equity_usd: '50000', state: 'CALCULATED', reasons: [], risk_budget: '250', loss_per_unit: '53.25', contracts: 4, estimated_loss_at_stop: '213', daily_loss_remaining: '1100', drawdown_remaining: '2000', minimum_balance: '48000', consistency_met: false, recorded_targets_met: false, firm_compliance: 'NOT_ASSESSED', passing_probability: 'UNKNOWN', trade_permitted: false, execution_enabled: false };
test('literal MES worked example retains money strings and false permissions', () => {
  const r = validatePersonalRisk(raw, snapshot, request, now);
  assert.equal(r.contracts, 4); assert.equal(r.loss_per_unit, '53.25'); assert.equal(r.execution_enabled, false);
});
test('equivalent decimal spellings do not look like a changed request', () => {
  const entered = personalRiskRequest({ ...request, entry: '05000', stop: '004990.00',
    risk_percent: '00.500', fees_per_unit: '02.00', slippage_points: '00.2500', safety_buffer: '010' });
  assert.equal(validatePersonalRisk(raw, snapshot, entered, now).contracts, 4);
});
test('server Decimal exponent notation retains exact request identity', () => {
  const echoed = { ...raw, request: { ...request, entry: '5E+3', risk_percent: '5E-1',
    fees_per_unit: '2E+0', slippage_points: '2.5E-1', safety_buffer: '1E+1' } };
  const result = validatePersonalRisk(echoed, snapshot, request, now);
  assert.equal(result.contracts, 4);
  assert.equal(result.request.entry, '5E+3'); // Preserve the response's serialized fields.
});
test('decimal comparison never merges distinct values lost by Number rounding', () => {
  const entered = personalRiskRequest({ ...request, fees_per_unit: '2.0000000000000001' });
  assert.throws(() => validatePersonalRisk(raw, snapshot, entered, now));
});
test('zero spellings are equivalent but nonnumeric identities remain exact', () => {
  const entered = personalRiskRequest({ ...request, fees_per_unit: '00.000' });
  const echoed = { ...raw, request: { ...request, fees_per_unit: '0E-12' },
    loss_per_unit: '51.25', estimated_loss_at_stop: '205.00' };
  assert.equal(validatePersonalRisk(echoed, snapshot, entered, now).contracts, 4);
  assert.throws(() => validatePersonalRisk({ ...echoed, request: { ...echoed.request, cost_reference: 'changed' } }, snapshot, entered, now));
});
for (const key of ['fees_per_unit', 'slippage_points', 'cost_reference', 'costs_reviewed', 'expected_account_revision']) test('missing ' + key + ' is not defaulted', () => {
  const r = { ...request } as Record<string, unknown>; delete r[key]; assert.throws(() => personalRiskRequest(r));
});
for (const changes of [{ instrument_id: 'ES', contract: 'ESZ26' }, { contract: 'MES1!' }, { risk_percent: '1.01' }, { fees_per_unit: 'NaN' }, { costs_reviewed: false }, { safety_buffer: '0' }]) test('invalid personal request ' + JSON.stringify(changes), () => assert.throws(() => personalRiskRequest({ ...request, ...changes })));
for (const changes of [{ contracts: 21 }, { source_hashes: {} }, { trade_permitted: true }, { execution_enabled: true }, { passing_probability: '95%' }, { scope: 'firm_permission' }, { journal_equity_usd: 50000 }]) test('reject malformed result ' + JSON.stringify(changes), () => assert.throws(() => validatePersonalRisk({ ...raw, ...changes }, snapshot, request, now)));
test('request, snapshot and revision races rejected', () => {
  assert.throws(() => validatePersonalRisk(raw, { ...snapshot, account_revision: 'c'.repeat(64) }, request, now));
  assert.throws(() => validatePersonalRisk(raw, { ...snapshot, sessions: [] }, request, now));
  assert.throws(() => validatePersonalRisk(raw, snapshot, { ...request, stop: '4991' }, now));
  const gate = requestGate(); const old = gate.next(); gate.next(); assert.equal(gate.current(old), false);
});
test('expiry, future and clock rollback do not restore eligibility', () => {
  const r = validatePersonalRisk(raw, snapshot, request, now);
  for (const time of [now - 1, now + 1800000, Date.parse('2026-10-08T14:00:00Z')]) assert.equal(personalRiskCurrent(r, time), false);
  assert.throws(() => validatePersonalRisk(raw, snapshot, request, now - 1));
});
test('unknown exposure cannot display a calculated size', () => {
  const a = { ...account, positions: null };
  const s = { ...snapshot, sessions: [{ ...snapshot.sessions[0], account: a }] };
  assert.throws(() => validatePersonalRisk({ ...raw, sessions: s.sessions }, s, request, now));
  for (const state of ['UNKNOWN','BLOCKED']) {
    assert.throws(() => validatePersonalRisk({ ...raw, state, reasons: ['missing'] }, snapshot, request, now));
    assert.equal(validatePersonalRisk({ ...raw, state, reasons: ['missing'], contracts: 0, estimated_loss_at_stop: '0' }, snapshot, request, now).contracts, 0);
  }
});
