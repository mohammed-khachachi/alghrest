/** Linux session-local supervision. No installation, boot enablement, or trading services. */
import { execFileSync } from 'node:child_process';
import { appendFileSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
import { researchEnvironment, requireFreePort, WEB_URL, API_URL } from './openterminal.mjs';

export const UNIT = 'alghrest-openterminal.service';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const properties = ['Id', 'LoadState', 'ActiveState', 'SubState', 'MainPID', 'InvocationID',
  'NRestarts', 'Result', 'ExecMainCode', 'ExecMainStatus', 'ControlGroup'];
function execute(command, args, timeout = 5000) {
  try { return execFileSync(command, args, {encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout}); }
  catch (error) { throw new Error(`${command} failed (exit ${error.status ?? 'unknown'}); check user-manager access.`); }
}
export function serviceArguments({node = process.execPath, directory = root, parent = process.env} = {}) {
  // env -i also removes credentials/NODE_OPTIONS inherited from the user manager itself.
  const environment = researchEnvironment(parent, resolve(directory, 'vendor/openterminal'));
  return ['--user', `--unit=${UNIT}`, '--description=ALGHREST isolated OpenTerminal research',
    '--service-type=exec', '--expand-environment=no',
    '--property=Restart=always', '--property=RestartSec=3s',
    '--property=StartLimitIntervalSec=60s', '--property=StartLimitBurst=3',
    '--property=KillMode=control-group', '--property=TimeoutStopSec=15s',
    '--property=StandardOutput=journal', '--property=StandardError=journal',
    `--working-directory=${directory}`, '/usr/bin/env', '-i',
    ...Object.entries(environment).map(([key, value]) => `${key}=${value}`),
    node, resolve(directory, 'scripts/openterminal.mjs')];
}
export function serviceStatus() {
  return Object.fromEntries(execute('/usr/bin/systemctl', ['--user', 'show', UNIT,
    ...properties.map(property => `--property=${property}`)]).trim().split('\n')
    .filter(Boolean).map(line => { const index = line.indexOf('='); return [line.slice(0, index), line.slice(index + 1)]; }));
}
export function parseProcessStat(pid, contents) {
  const fields = contents.slice(contents.lastIndexOf(')') + 2).trim().split(/\s+/);
  return {pid: Number(pid), ppid: Number(fields[1]), startTicks: fields[19], state: fields[0]};
}
function cgroupProcesses(group) {
  if (!group?.startsWith('/') || group.includes('..')) throw new Error('Missing or invalid service cgroup.');
  const found = [];
  const visit = directory => {
    for (const pid of readFileSync(resolve(directory, 'cgroup.procs'), 'utf8').trim().split('\n').filter(Boolean)) {
      try { found.push(parseProcessStat(pid, readFileSync(`/proc/${pid}/stat`, 'utf8'))); }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
    }
    for (const entry of readdirSync(directory, {withFileTypes: true})) if (entry.isDirectory()) visit(resolve(directory, entry.name));
  };
  visit(`/sys/fs/cgroup${group}`);
  return found.sort((a, b) => a.pid - b.pid);
}
export function listenerIdentities(output) {
  return output.trim().split('\n').filter(Boolean).map(line => {
    const fields = line.trim().split(/\s+/);
    return {address: fields[3], pids: [...line.matchAll(/pid=(\d+)/g)].map(match => Number(match[1])).sort((a,b) => a-b)};
  }).sort((a,b) => a.address.localeCompare(b.address));
}
async function httpChecks() {
  const api = await fetch(`${API_URL}/api/status`, {signal: AbortSignal.timeout(5000)});
  const status = await api.json();
  const web = await fetch(WEB_URL, {signal: AbortSignal.timeout(5000)});
  await web.body?.cancel();
  return {apiStatus: api.status, webStatus: web.status,
    apiIdentity: status.integration, ok: status.ok, ai: status.ai, execution_enabled: status.execution_enabled};
}
export function validateSample(sample) {
  const {service, processes, listeners, http} = sample;
  if (service.ActiveState !== 'active' || service.SubState !== 'running' || !service.InvocationID)
    throw new Error('Service is not running with an invocation identity.');
  if (!processes.some(item => item.pid === Number(service.MainPID))) throw new Error('Service main PID missing.');
  const owned = new Set(processes.map(item => item.pid));
  for (const port of [3001, 4001]) {
    const matches = listeners.filter(item => item.address === `127.0.0.1:${port}`);
    if (matches.length !== 1 || !matches[0].pids.length || matches[0].pids.some(pid => !owned.has(pid)))
      throw new Error(`Listener ${port} is missing or outside the service cgroup.`);
  }
  if (http.apiStatus !== 200 || http.webStatus !== 200 || http.apiIdentity !== 'alghrest-research'
      || http.ok !== true || http.ai !== false || http.execution_enabled !== false)
    throw new Error('OpenTerminal HTTP identity or health check failed.');
}
export function stabilityIdentity(sample) {
  return JSON.stringify({invocation: sample.service.InvocationID, pid: sample.service.MainPID,
    restarts: sample.service.NRestarts, group: sample.service.ControlGroup,
    processes: sample.processes.map(({pid, ppid, startTicks}) => ({pid, ppid, startTicks})), listeners: sample.listeners});
}
export function observationCoverage({seconds, interval, samples, observedSeconds, longestGapSeconds}) {
  const minimumSamples = Math.ceil(seconds / (interval + 15)) + 1;
  return {minimumSamples, pass: samples >= minimumSamples && observedSeconds >= seconds
    && longestGapSeconds <= interval + 15};
}
export async function observe({seconds = 600, interval = 15, output}) {
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 86400 || !Number.isInteger(interval)
      || interval < 1 || interval > 60 || !output) throw new Error('Observe needs output, seconds 1..86400, interval 1..60.');
  writeFileSync(output, '', {flag: 'wx', mode: 0o600});
  const start = performance.now();
  const wallStart = Date.now();
  let baseline;
  let samples = 0;
  let failures = 0;
  let previousElapsed = 0;
  let previousWallElapsed = 0;
  let longestGapSeconds = 0;
  while (true) {
    let sample = {time: new Date().toISOString(), elapsedSeconds: (performance.now() - start) / 1000};
    const wallElapsed = (Date.now() - wallStart) / 1000;
    const gap = Math.max(sample.elapsedSeconds - previousElapsed, wallElapsed - previousWallElapsed);
    previousWallElapsed = wallElapsed;
    longestGapSeconds = Math.max(longestGapSeconds, gap);
    previousElapsed = sample.elapsedSeconds;
    try {
      if (gap > interval + 15) throw new Error('Observation gap exceeded interval plus 15 seconds.');
      sample.service = serviceStatus();
      sample.processes = cgroupProcesses(sample.service.ControlGroup);
      sample.listeners = listenerIdentities(execute('/usr/bin/ss', ['-H', '-ltnp', '( sport = :3001 or sport = :4001 )']));
      sample.http = await httpChecks();
      validateSample(sample);
      const identity = stabilityIdentity(sample);
      if (baseline === undefined) baseline = identity;
      else if (identity !== baseline) throw new Error('Process, invocation, restart count, or listener identity changed.');
      sample.pass = true;
    } catch (error) { sample.pass = false; sample.error = error.message; failures++; }
    samples++;
    appendFileSync(output, `${JSON.stringify(sample)}\n`);
    const elapsed = (performance.now() - start) / 1000;
    if (sample.elapsedSeconds >= seconds) break;
    await new Promise(accept => setTimeout(accept, Math.max(0, Math.min(interval, seconds - elapsed)) * 1000));
  }
  const coverage = observationCoverage({seconds, interval, samples, observedSeconds: previousElapsed, longestGapSeconds});
  if (!coverage.pass) failures++;
  const summary = {coverage, type: 'summary', time: new Date().toISOString(), requestedSeconds: seconds,
    observedSeconds: previousElapsed, longestGapSeconds, samples, failures, pass: failures === 0,
    meaning: 'Sampled observation only; any recovery or identity change fails uninterrupted stability.'};
  appendFileSync(output, `${JSON.stringify(summary)}\n`);
  console.log(JSON.stringify(summary));
  if (failures) process.exitCode = 1;
  return summary;
}
export function lifecycleEntries(journal) {
  const allowed = ['timestamp', 'launcher', 'launcher_pid', 'launcher_ppid', 'event', 'service',
    'child_pid', 'reason', 'signal', 'code', 'sender', 'sender_pid', 'error_code'];
  return journal.split('\n').flatMap(line => {
    try {
      const entry = JSON.parse(line);
      if (!entry.MESSAGE?.startsWith('[research-lifecycle] ')) return [];
      const record = JSON.parse(entry.MESSAGE.slice('[research-lifecycle] '.length));
      return [Object.fromEntries(allowed.filter(key => Object.hasOwn(record, key)).map(key => [key, record[key]]))];
    } catch { return []; }
  });
}
export async function main(args = process.argv.slice(2)) {
  if (process.platform !== 'linux') throw new Error('This helper requires Linux with a systemd user manager.');
  const [action, ...options] = args;
  if (action === 'observe') {
    const config = {};
    for (let i = 0; i < options.length; i += 2) {
      if (!['--seconds', '--interval', '--output'].includes(options[i]) || options[i+1] === undefined)
        throw new Error('Use observe --seconds 600 --interval 15 --output /path/new-samples.jsonl');
      config[options[i].slice(2)] = options[i] === '--output' ? options[i+1] : Number(options[i+1]);
    }
    return observe(config);
  }
  if (options.length) throw new Error('Unexpected arguments.');
  if (action === 'logs') {
    const journal = execute('/usr/bin/journalctl', ['--user', `--unit=${UNIT}`, '--no-pager', '-n', '500', '-o', 'json']);
    for (const entry of lifecycleEntries(journal)) console.log(JSON.stringify(entry));
    return;
  }
  if (action === 'plan') return console.log(JSON.stringify({command: '/usr/bin/systemd-run', args: serviceArguments()}, null, 2));
  if (action === 'status') return console.log(JSON.stringify(serviceStatus(), null, 2));
  if (action === 'start') {
    const status = serviceStatus();
    if (status.ActiveState === 'active') { console.log(JSON.stringify(status)); return; }
    if (status.LoadState !== 'not-found') throw new Error('A unit already exists. Inspect status/logs, then stop it before starting again.');
    await requireFreePort(3001); await requireFreePort(4001);
    execute('/usr/bin/systemd-run', serviceArguments());
    console.log(JSON.stringify(serviceStatus(), null, 2));
    return;
  }
  if (action === 'stop') {
    execute('/usr/bin/systemctl', ['--user', 'stop', UNIT], 20000);
    console.log(JSON.stringify(serviceStatus(), null, 2));
    return;
  }
  throw new Error('Use: node scripts/openterminal-service.mjs plan|start|stop|status|logs|observe');
}
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url))
  main().catch(error => {console.error(error.message); process.exitCode = 1;});
