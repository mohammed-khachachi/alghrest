import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_ROUTE, accessScopeForPath, navigationForScope } from '../src/lib/navigation';

test('cold entry uses the assistant access gate before its redirect', () => {
  assert.equal(DEFAULT_ROUTE, '/assistant');
  assert.equal(accessScopeForPath('/'), 'advisory');
  assert.equal(accessScopeForPath(DEFAULT_ROUTE), 'advisory');
});

for (const path of ['/assistant', '/assistant/', '/assistant///', '/research', '/research/']) {
  test(`assistant path keeps its separate credential scope: ${path}`, () => {
    assert.equal(accessScopeForPath(path), 'advisory');
  });
}

for (const path of ['/overview', '/agents', '/positions', '/kafka', '/risk', '/investor', '/auditor', '/backtest']) {
  test(`legacy deep link retains the API access gate: ${path}`, () => {
    assert.equal(accessScopeForPath(path), 'api');
  });
}

for (const path of ['/assistant-other', '/assistant/unknown', '/unknown']) {
  test(`unknown path cannot inherit research credentials by prefix: ${path}`, () => {
    assert.equal(accessScopeForPath(path), 'api');
  });
}

test('research navigation has no legacy execution dashboard destinations', () => {
  assert.deepEqual(navigationForScope('advisory').map(item => item.path), ['/assistant', '/research']);
});

test('explicit legacy navigation preserves all deep links and return to assistant', () => {
  const paths = navigationForScope('api').map(item => item.path);
  assert.equal(paths.length, 10);
  assert.equal(new Set(paths).size, paths.length);
  assert(paths.includes('/assistant'));
  assert(paths.includes('/overview'));
  assert(paths.includes('/positions'));
});
