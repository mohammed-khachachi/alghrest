import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'node:net';
import { resolve } from 'node:path';
import { researchEnvironment, requireFreePort, API_URL, WEB_URL } from '../scripts/openterminal.mjs';

test('research launch excludes inherited keys and ALGHREST service addresses', () => {
  const fixture = resolve('research-fixture');
  const environment = researchEnvironment({
    PATH: '/bin', HOME: '/tmp/example', ANTHROPIC_API_KEY: 'test-only',
    ADVISORY_ACCESS_TOKEN: 'test-only', API_KEY: 'test-only', BINANCE_SECRET: 'test-only',
    DATABASE_URL: 'test-only', REDIS_URL: 'test-only', NODE_OPTIONS: '--inspect',
    API_HOST: '0.0.0.0', API_PORT: '8000', WEB_ORIGIN: 'https://example.invalid', TRUST_PROXY: '1',
  }, fixture);
  assert.equal(environment.PATH, '/bin');
  assert.equal(environment.API_HOST, '127.0.0.1');
  assert.equal(environment.API_PORT, '4001');
  assert.equal(environment.API_URL, API_URL);
  assert.equal(environment.WEB_ORIGIN, WEB_URL);
  assert.equal(environment.TRUST_PROXY, '0');
  assert.equal(environment.DATA_DIR, resolve(fixture, 'data'));
  assert.equal(environment.API_KEY_FILE, resolve(fixture, 'data/.api-key'));
  for (const key of ['ANTHROPIC_API_KEY', 'ADVISORY_ACCESS_TOKEN', 'API_KEY', 'BINANCE_SECRET', 'DATABASE_URL', 'REDIS_URL', 'NODE_OPTIONS']) {
    assert.equal(environment[key], undefined, key);
  }
});

test('Windows OS environment spelling is preserved while credentials are excluded', () => {
  const environment = researchEnvironment({ Path: 'C:\\Node', SystemRoot: 'C:\\Windows', anthropic_api_key: 'test-only' });
  assert.equal(environment.Path, 'C:\\Node');
  assert.equal(environment.SystemRoot, 'C:\\Windows');
  assert.equal(environment.anthropic_api_key, undefined);
});

test('a busy port is rejected without stopping its owner', async () => {
  const owner = createServer();
  await new Promise((accept, reject) => {
    owner.once('error', reject);
    owner.listen(0, '127.0.0.1', accept);
  });
  try {
    const port = owner.address().port;
    await assert.rejects(requireFreePort(port), /unavailable/);
    assert.equal(owner.listening, true);
  } finally {
    await new Promise(accept => owner.close(accept));
  }
});
