import test from 'node:test';
import assert from 'node:assert/strict';
import {observationCoverage, lifecycleEntries, serviceArguments, parseProcessStat, listenerIdentities, validateSample, stabilityIdentity} from '../scripts/openterminal-service.mjs';

test('transient service starts clean and stays outside invoking desktop scope', () => {
  const args = serviceArguments({node: '/usr/bin/node', directory: '/tmp/project space',
    parent: {PATH: '/usr/bin:/bin', HOME: '/tmp', NODE_OPTIONS: '--require evil', ANTHROPIC_API_KEY: 'secret', API_KEY: 'secret'}});
  assert.equal(args.includes('--scope'), false);
  assert.equal(args.includes('--property=Restart=always'), true);
  assert.equal(args.includes('--property=StartLimitBurst=3'), true);
  assert.equal(args.includes('--property=StartLimitIntervalSec=60s'), true);
  assert.equal(args.includes('--property=KillMode=control-group'), true);
  assert.equal(args.includes('--expand-environment=no'), true);
  const envIndex = args.indexOf('/usr/bin/env');
  assert.equal(args[envIndex + 1], '-i');
  assert.equal(args.some(arg => arg.includes('secret') || arg.includes('NODE_OPTIONS')), false);
  assert.deepEqual(args.slice(-2), ['/usr/bin/node', '/tmp/project space/scripts/openterminal.mjs']);
});
function sample() {
  return {service: {ActiveState: 'active', SubState: 'running', MainPID: '100', InvocationID: 'abc', NRestarts: '0', ControlGroup: '/example'},
    processes: [{pid: 100, ppid: 1, startTicks: '123'}, {pid: 101, ppid: 100, startTicks: '124'}],
    listeners: [{address: '127.0.0.1:3001', pids: [100]}, {address: '127.0.0.1:4001', pids: [101]}],
    http: {apiStatus: 200, webStatus: 200, apiIdentity: 'alghrest-research', ok: true, ai: false, execution_enabled: false}};
}
test('probe requires API identity, disabled execution and service-owned listeners', () => {
  const good = sample(); validateSample(good);
  for (const mutation of [s => s.http.execution_enabled = true, s => s.http.apiIdentity = 'other',
    s => s.http.webStatus = 500, s => s.listeners[0].pids = [999], s => s.service.ActiveState = 'failed',
    s => s.processes = []]) { const changed = sample(); mutation(changed); assert.throws(() => validateSample(changed)); }
});
test('recovery, PID reuse and invocation changes cannot pass uninterrupted stability', () => {
  const baseline = stabilityIdentity(sample());
  for (const mutation of [s => s.service.NRestarts = '1', s => s.service.InvocationID = 'new',
    s => s.processes[0].startTicks = '999', s => s.listeners[0].pids = [102]]) {
    const changed = sample(); mutation(changed); assert.notEqual(stabilityIdentity(changed), baseline);
  }
});
test('proc identity handles command names with spaces and parentheses', () => {
  const fields = Array(50).fill('0'); fields[0] = 'S'; fields[1] = '3'; fields[19] = '456';
  assert.deepEqual(parseProcessStat(100, `100 (name (with spaces)) ${fields.join(' ')}`),
    {pid: 100, ppid: 3, startTicks: '456', state: 'S'});
});
test('ss parser captures ownership without process arguments or command names', () => {
  assert.deepEqual(listenerIdentities('LISTEN 0 511 127.0.0.1:3001 0.0.0.0:* users:(("next-server",pid=253177,fd=22))'),
    [{address: '127.0.0.1:3001', pids: [253177]}]);
});

test('coverage rejects sparse samples, long gaps and a partial observation window', () => {
  const good = {seconds: 600, interval: 15, samples: 41, observedSeconds: 600, longestGapSeconds: 16};
  assert.equal(observationCoverage(good).pass, true);
  for (const changes of [{samples: 1}, {observedSeconds: 599}, {longestGapSeconds: 61}])
    assert.equal(observationCoverage({...good, ...changes}).pass, false);
});
test('journal output omits vendor messages and unexpected lifecycle fields', () => {
  const lines = [JSON.stringify({MESSAGE: 'API_KEY=secret'}), JSON.stringify({MESSAGE:
    '[research-lifecycle] '+JSON.stringify({event: 'child_exit', code: 1, credential: 'secret'})})];
  assert.deepEqual(lifecycleEntries(lines.join('\n')), [{event: 'child_exit', code: 1}]);
});
