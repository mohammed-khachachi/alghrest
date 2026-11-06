import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';

const supervisorUrl = new URL('../scripts/run_research.mjs', import.meta.url).href;
const standaloneUrl = new URL('../scripts/openterminal.mjs', import.meta.url).href;

async function fixture({ source, externalSignal = false, repeatSignal = false }) {
  const supervisor = spawn(process.execPath, ['--input-type=module', '-e', source], {
    env: {}, stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stdout = '';
  let stderr = '';
  let signalled = false;
  let repeated = false;
  const timeout = setTimeout(() => supervisor.kill('SIGKILL'), 10000);
  supervisor.stdout.on('data', chunk => {
    stdout += chunk;
    if (externalSignal && !signalled && stdout.includes('FIXTURE_READY')) {
      signalled = true;
      supervisor.kill(externalSignal);
    }
  });
  supervisor.stderr.on('data', chunk => {
    stderr += chunk;
    if (repeatSignal && !repeated && stderr.includes('"event":"signal_sent"')) {
      repeated = true;
      supervisor.kill(externalSignal);
    }
  });
  const result = await new Promise((accept, reject) => {
    supervisor.once('error', reject);
    supervisor.once('exit', (code, signal) => accept({ code, signal }));
  }).finally(() => clearTimeout(timeout));
  return { ...result, stderr, events: stderr.split('\n')
    .filter(line => line.startsWith('[research-lifecycle] '))
    .map(line => JSON.parse(line.slice('[research-lifecycle] '.length))) };
}

function sourceFor(childSource, standalone = false, overrides = {}) {
  const service = { name: 'signal fixture', command: process.execPath,
    args: ['--input-type=module', '-e', childSource], env: {}, shell: false, ...overrides };
  const callable = standalone ? 'runOpenTerminal' : 'runServices';
  return `import {${callable}} from ${JSON.stringify(standalone ? standaloneUrl : supervisorUrl)};
    try {await ${callable}(${JSON.stringify(standalone ? service : [service])});}
    catch(error) {console.error(error.message);process.exitCode=1;}`;
}

for (const standalone of [false, true]) {
const label = standalone ? 'OpenTerminal' : 'integrated supervisor';
test(`${label}: unexpected real child SIGTERM retains signal and failure cause`, { skip: process.platform === 'win32' }, async () => {
  const result = await fixture({ source: sourceFor("process.kill(process.pid, 'SIGTERM')", standalone) });
  assert.equal(result.code, 1);
  assert.match(result.stderr, /SIGTERM/);
  const exit = result.events.find(event => event.event === 'child_exit');
  assert.equal(exit.signal, 'SIGTERM');
  assert.equal(exit.code, null);
  assert.equal(exit.reason, 'unexpected_child_exit');
  assert.equal(exit.sender_pid, null);
  assert.equal(exit.sender, 'unknown');
  assert.match(exit.timestamp, /^\d{4}-\d{2}-\d{2}T.*Z$/);
  for (const key of ['launcher_pid', 'launcher_ppid', 'child_pid']) assert(exit[key] > 0);
  if (!standalone) assert.equal(result.events.find(event => event.event === 'shutdown_requested').reason, 'unexpected_child_exit');
  assert.equal(result.events.find(event => event.event === 'cleanup_started').reason, 'unexpected_child_exit');
});

test(`${label}: incoming supervisor SIGTERM is recorded separately from unexpected child failure`, { skip: process.platform === 'win32' }, async () => {
  const result = await fixture({
    source: sourceFor("console.log('FIXTURE_READY');setInterval(()=>{},1000)", standalone),
    externalSignal: 'SIGTERM',
  });
  assert.equal(result.code, 0);
  const received = result.events.find(event => event.event === 'signal_received');
  assert(received, 'supervisor must record receiving SIGTERM');
  assert.equal(received.signal, 'SIGTERM');
  assert.equal(received.sender, 'unknown');
  const exit = result.events.find(event => event.event === 'child_exit');
  assert.equal(exit.reason, 'supervisor_signal');
  const sent = result.events.find(event => event.event === 'signal_sent');
  assert.equal(sent.signal, 'SIGTERM');
  assert.equal(sent.sender_pid, sent.launcher_pid);
  assert.equal(sent.reason, 'supervisor_signal');
});

test(`${label}: repeated SIGINT preserves cleanup and original shutdown reason`, { skip: process.platform === 'win32' }, async () => {
  const result = await fixture({
    source: sourceFor("process.on('SIGTERM',()=>setTimeout(()=>process.exit(0),150));process.on('SIGINT',()=>setTimeout(()=>process.exit(0),150));console.log('FIXTURE_READY');setInterval(()=>{},1000)", standalone),
    externalSignal: 'SIGINT', repeatSignal: true,
  });
  assert.equal(result.code, 0);
  assert.equal(result.events.filter(event => event.event === 'signal_received').length, 2);
  assert.equal(result.events.filter(event => event.event === 'shutdown_requested').length, 1);
  assert(result.events.some(event => event.event === 'cleanup_finished'));
  assert(result.events.filter(event => event.event === 'child_exit').every(event => event.reason === 'supervisor_signal'));
});

test(`${label}: spawn failures report a safe OS error without argv or environment`, async () => {
  const result = await fixture({ source: sourceFor('', standalone, {
    command: '/nonexistent/research-fixture-command',
    args: ['synthetic-private-argument'], env: { API_KEY: 'synthetic-private-key' },
  }) });
  assert.equal(result.code, 1);
  const error = result.events.find(event => event.event === 'child_error');
  assert.equal(error.error_code, 'ENOENT');
  assert.equal(error.reason, 'child_start_error');
  assert(!result.events.some(event => event.event === 'child_started'));
  assert.doesNotMatch(result.stderr, /synthetic-private/);
  assert(result.events.some(event => event.event === 'cleanup_finished'));
});
}
