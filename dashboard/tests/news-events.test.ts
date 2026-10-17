import test from 'node:test';
import assert from 'node:assert/strict';
import { ageLabel, contextRequests, newsContext, refreshDue, sourceState } from '../src/lib/newsEvents';
const time = '2026-10-12T12:00:00Z';
const fixture = () => ({schema_version: 'news-events-v1', instrument_id: 'MES', assessed_at: time, headlines: [], events: [],
  sources: [{name: 'FOMC', url: 'https://www.federalreserve.gov/calendar', kind: 'calendar', attempted_at: time, fetched_at: time, state: 'ok', http_status: 200,
    content_sha256: 'a'.repeat(64), parsed_count: 1, usable_count: 1, reasons: ['partial_schedule']}], returned_date_start: null, returned_date_end: null,
  coverage: 'partial', event_risk: 'UNKNOWN', trade_permitted: false, execution_enabled: false});

test('partial context retains closed permissions and failure states', () => {
  const raw = fixture(); raw.sources[0].state = 'unavailable';
  assert.equal(newsContext(raw, 'MES').event_risk, 'UNKNOWN');
});
for (const [key, value] of [['trade_permitted', true], ['execution_enabled', true], ['coverage', 'complete'], ['event_risk', 'CLEAR'], ['instrument_id', 'MNQ']]) {
  test(`reject changed ${key}`, () => assert.throws(() => newsContext({...fixture(), [key as string]: value}, 'MES')));
}
test('unsafe and credential-bearing links rejected', () => {
  for (const url of ['javascript:alert(1)', 'http://example.org', 'https://user:secret@example.org']) {
    const raw = fixture(); raw.sources[0].url = url; assert.throws(() => newsContext(raw, 'MES'));
  }
});
test('source freshness ages without changing fetch or price identity', () => {
  const value = newsContext(fixture(), 'MES'); const s = value.sources[0]; const n = Date.parse(time);
  assert.equal(sourceState(s, n + 299999), 'ok'); assert.equal(sourceState(s, n + 300000), 'stale');
  assert.equal(sourceState(s, n - 1), 'invalid'); assert.equal(s.fetched_at, time);
  assert.equal(ageLabel(time, n + 15 * 60000), '15 دقيقة');
});
test('bad clocks and counts are rejected', () => {
  const raw = fixture(); raw.sources[0].usable_count = 2; assert.throws(() => newsContext(raw, 'MES'));
  raw.sources[0].usable_count = 1; raw.assessed_at = '2026-10-12T12:05:00Z'; assert.throws(() => newsContext(raw, 'MES'));
});
test('newer selection or unmount invalidates late success and failure', () => {
  const gate = contextRequests(); const old = gate.next(); const next = gate.next();
  assert.equal(gate.current(old), false); assert.equal(gate.current(next), true);
  gate.next(); assert.equal(gate.current(next), false);
});
test('refresh is opt-in, visible, idle, and only after selected 5 or 15 minutes', () => {
  assert.equal(refreshDue(0, true, false, 9999999), false);
  assert.equal(refreshDue(5, false, false, 9999999), false);
  assert.equal(refreshDue(5, true, true, 9999999), false);
  assert.equal(refreshDue(5, true, false, 299999), false);
  assert.equal(refreshDue(5, true, false, 300000), true);
  assert.equal(refreshDue(15, true, false, 899999), false);
  assert.equal(refreshDue(15, true, false, 900000), true);
});
test('future, old or detached headline cannot pass response validation', () => {
  for (const published_at of ['2026-10-12T13:00:00Z', '2026-09-01T00:00:00Z', time]) {
    const raw = {...fixture(), headlines: [{item: {id: 'x', title: 'Fed', url: 'https://example.org/x', source: 'missing', published_at, category: 'macro'}, relevance: ['central_bank']}]};
    assert.throws(() => newsContext(raw, 'MES'));
  }
});
