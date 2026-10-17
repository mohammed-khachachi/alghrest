import assert from 'node:assert/strict';
import test from 'node:test';
import { canReview, observationTemplate, observationView, packetSchema, priceAge, responseGate } from '../src/lib/observations';
const now = Date.parse('2026-10-12T10:00:00Z');
function view() {
  const packet = observationTemplate();
  return { record: { id: 'synthetic', revision: 'a'.repeat(64), parent_revision: null, created_at: '2026-10-12T10:00:00Z', raw_json: JSON.stringify(packet), packet, source_hashes: { 'observations.py': 'b'.repeat(64) } }, latest_revision: 'a'.repeat(64), reviewed_at: null, assessed_at: '2026-10-12T10:00:00Z', warnings: [], origin: 'user_reported', trade_permitted: false, execution_enabled: false };
}
test('template explicitly leaves prices and times unknown', () => {
  const p = packetSchema.parse(observationTemplate());
  assert.equal(p.frames[0].last, null); assert.equal(p.frames[0].observed_at, null);
  assert.equal(priceAge(p, now), 'وقت بعض الأسعار غير معلوم');
});
test('only clean current unreviewed saved revision is reviewable', () => {
  const v = observationView(view());
  assert.equal(canReview(v, false), true); assert.equal(canReview(v, true), false);
  assert.equal(canReview(null, false), false);
  assert.equal(canReview({ ...v, reviewed_at: v.assessed_at }, false), false);
  assert.equal(canReview({ ...v, latest_revision: 'c'.repeat(64) }, false), false);
});
for (const [field, value] of [['trade_permitted', true], ['execution_enabled', true], ['origin', 'verified'], ['reviewed_at', '2030-01-01T00:00:00Z']]) {
  test(`reject forged ${field}`, () => assert.throws(() => observationView({ ...view(), [field as string]: value })));
}
test('unknown fields and invalid or coerced numeric types rejected', () => {
  assert.throws(() => packetSchema.parse({ ...observationTemplate(), confirmed: true }));
  for (const last of [true, 1.5, 'NaN', 'Infinity', '1e3', ' 1', '01', '']) {
    const p = observationTemplate();
    assert.throws(() => packetSchema.parse({ ...p, frames: [{ ...p.frames[0], last }] }));
  }
});
test('age advances without new price or review refresh', () => {
  const p = observationTemplate(); p.frames[0].observed_at = '2026-10-12T10:00:00Z';
  assert.match(priceAge(p, now), /0 دقيقة/);
  assert.match(priceAge(p, now + 900000), /أسعار قديمة/);
  assert.match(priceAge(p, now - 1), /المستقبل/);
  assert.equal(p.frames[0].observed_at, '2026-10-12T10:00:00Z');
});
test('slow responses invalidated after edits, navigation or newer requests', () => {
  const gate = responseGate(); const request = gate.next();
  assert.equal(gate.current(request), true); gate.next(); assert.equal(gate.current(request), false);
});
test('clock contradictions in saved response rejected', () => {
  const value = view();
  assert.throws(() => observationView({ ...value, record: { ...value.record, created_at: '2026-10-12T11:00:00Z' } }));
  assert.throws(() => observationView({ ...value, reviewed_at: '2026-10-12T09:00:00Z' }));
});
