import test from 'node:test';
import assert from 'node:assert/strict';
import { terminalContext, terminalMessage, selectProxy, instrumentForProxy } from '../src/lib/terminalBridge';

const now = Date.parse('2026-10-14T12:00:00Z');
const stamp = new Date(now).toISOString();
function context() {
  return {
    schema_version: 'openterminal-context-v1', instrument_id: 'MNQ', proxy_symbol: 'QQQ', assessed_at: stamp,
    quote: {symbol: 'QQQ', name: 'Synthetic proxy', price: '100.10', change_percent: '0.5', provider: 'nasdaq', currency: 'USD', market_time: null},
    headlines: [{title: 'Synthetic news', url: 'https://example.org/article', publisher: 'Fixture', published_at: stamp}],
    sources: ['quotes', 'news'].map(kind => ({kind, state: 'available', received_at: stamp, response_sha256: 'a'.repeat(64), reasons: []})),
    direction: 'proxy_up', scope: 'public_etf_context', freshness: 'UNKNOWN', event_risk: 'UNKNOWN',
    quote_usable_for_risk: false, trade_permitted: false, execution_enabled: false,
  };
}

test('selection shares only a public proxy symbol, never account data or token', () => {
  assert.deepEqual(selectProxy('MES'), {type: 'alghrest:select-symbol', symbol: 'SPY'});
  assert.deepEqual(selectProxy('MNQ'), {type: 'alghrest:select-symbol', symbol: 'QQQ'});
  assert.equal(instrumentForProxy('AAPL'), null);
});

test('a symbol message must come from the fixed terminal origin', () => {
  const value = {type: 'openterminal:symbol', symbol: 'QQQ'};
  assert(terminalMessage('http://127.0.0.1:3001', value));
  for (const origin of ['https://example.org', 'http://127.0.0.1:4001', 'http://localhost:3001', 'null']) assert.equal(terminalMessage(origin, value), null);
});

test('window messages cannot import prices, credentials or execution permission', () => {
  for (const value of [null, [], {type: 'openterminal:symbol', symbol: 'QQQ', token: 'synthetic'}, {type: 'openterminal:symbol', symbol: 'QQQ', price: 100}, {type: 'execute', symbol: 'QQQ'}, {type: 'openterminal:symbol', symbol: 'https://example.org'}]) assert.equal(terminalMessage('http://127.0.0.1:3001', value), null);
});

test('a valid context stays separate from dated futures prices and risk', () => {
  const parsed = terminalContext(context(), 'MNQ', now);
  assert(parsed);
  assert.equal(parsed.quote_usable_for_risk, false);
  assert.equal(parsed.freshness, 'UNKNOWN');
  assert.equal(parsed.event_risk, 'UNKNOWN');
});

for (const property of ['execution_enabled', 'trade_permitted', 'quote_usable_for_risk']) {
  test(`context rejects a forged positive ${property}`, () => {
    assert.equal(terminalContext({...context(), [property]: true}, 'MNQ', now), null);
  });
}

test('context refuses mismatched identity, stale data and future source clocks', () => {
  assert.equal(terminalContext(context(), 'MES', now), null);
  assert.equal(terminalContext({...context(), proxy_symbol: 'SPY'}, 'MNQ', now), null);
  assert.equal(terminalContext(context(), 'MNQ', now + 90000), null);
  assert.equal(terminalContext({...context(), assessed_at: new Date(now + 10000).toISOString()}, 'MNQ', now), null);
  const value = context(); value.sources[0].received_at = new Date(now + 1000).toISOString();
  assert.equal(terminalContext(value, 'MNQ', now), null);
});

test('provider, currency, checksum, source identity and news links are validated', () => {
  for (const changed of [
    {...context(), quote: {...context().quote, provider: 'invented'}},
    {...context(), quote: {...context().quote, currency: 'EUR'}},
    {...context(), quote: {...context().quote, symbol: 'MNQZ26'}},
    {...context(), sources: [context().sources[0], context().sources[0]]},
    {...context(), sources: context().sources.map(row => ({...row, response_sha256: null}))},
    {...context(), headlines: [{...context().headlines[0], url: 'javascript:alert(1)'}]},
    {...context(), headlines: [{...context().headlines[0], url: 'https://user:password@example.org'}]},
  ]) assert.equal(terminalContext(changed, 'MNQ', now), null);
});

test('tiny decimal changes do not become a false zero through floating point', () => {
  assert(terminalContext({...context(), quote: {...context().quote, change_percent: '1e-999'}}, 'MNQ', now));
  assert.equal(terminalContext({...context(), direction: 'proxy_down'}, 'MNQ', now), null);
});
