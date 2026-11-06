import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { researchEnvironment, requireFreePort, signalOwnedProcess, finishOwnedProcessGroups } from './openterminal.mjs';
import { lifecycleLogger, exitDescription } from './research-lifecycle.mjs';

export const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
export const PORTS = [8011, 5173, 3001, 4001];

export function researchPlan(parent = process.env, platform = process.platform) {
  const environment = researchEnvironment(parent);
  for (const key of ['API_HOST', 'API_PORT', 'API_URL', 'WEB_ORIGIN', 'DATA_DIR', 'API_KEY_FILE', 'TRUST_PROXY']) delete environment[key];
  const windows = platform === 'win32';
  return [
    { name: 'ALGHREST assistant', command: resolve(ROOT, windows ? '.venv/Scripts/python.exe' : '.venv/bin/python'), args: ['-m', 'api.advisor'], cwd: ROOT, shell: false,
      env: {...environment, ENVIRONMENT: 'development', OPERATING_PROFILE: 'earn2trade_tcp50', ENABLE_DEFI_AGENTS: 'false', ADVISORY_KAFKA_SERVERS: ''} },
    { name: 'ALGHREST dashboard', command: windows ? 'npm.cmd' : 'npm', args: ['run', 'dev', '--', '--strictPort'], cwd: resolve(ROOT, 'dashboard'), shell: windows, env: {...environment} },
    { name: 'OpenTerminal', command: process.execPath, args: [resolve(ROOT, 'scripts/openterminal.mjs')], cwd: ROOT, shell: false, env: {...environment} },
  ];
}

export async function main(args = process.argv.slice(2)) {
  if (args.includes('--help')) {
    console.log('Start the integrated workspace: node scripts/run_research.mjs\nCheck dependencies and ports: node scripts/run_research.mjs --check\nCtrl+C stops only the processes launched here.'); return;
  }
  if (args.some(arg => arg !== '--check')) throw new Error('Unknown option. Use --help.');
  const plan = researchPlan();
  if (!existsSync(plan[0].command)) throw new Error('Project Python environment is missing. Install the application into .venv first.');
  for (const folder of ['dashboard', 'vendor/openterminal']) {
    if (!existsSync(resolve(ROOT, folder, 'node_modules/.package-lock.json'))) throw new Error(`Run npm ci inside ${folder} first.`);
  }
  for (const port of PORTS) await requireFreePort(port);
  if (args.includes('--check')) {console.log('Dependencies present; integrated workspace ports are free.'); return;}
  console.log('Integrated research workspace: http://127.0.0.1:5173/research\nUse your existing local assistant access token. Research only; no trading agents or Docker. Ctrl+C to stop.');
  return runServices(plan);
}

/** Shared supervisor; test harnesses can provide explicitly isolated fixtures. */
export async function runServices(plan = researchPlan()) {
  const children = [];
  const services = new Map();
  const log = lifecycleLogger('run_research');
  let stopping = false;
  let reason = null;
  let failure = null;
  let timer;
  const record = (child, event, details) => log(event, {
    service: services.get(child), child_pid: child.pid ?? null, ...details,
  });
  function signalChild(child, signal, signalReason = reason) {
    try {
      signalOwnedProcess(child, signal,
        (event, details) => record(child, event, { reason: signalReason, ...details }));
    } catch {console.error('Unable to stop a research child process group.');}
  }
  function stop(cause, signal = null, child = null) {
    if (stopping) return;
    stopping = true;
    reason = cause;
    log('shutdown_requested', { reason, signal, service: services.get(child) ?? null,
      child_pid: child?.pid ?? null });
    for (const child of children) signalChild(child, 'SIGTERM');
    timer = setTimeout(() => {for (const child of children) signalChild(child, 'SIGKILL', 'shutdown_timeout');}, 6000);
    timer.unref();
  }
  function receive(signal) {
    log('signal_received', { signal, reason: 'supervisor_signal' });
    stop('supervisor_signal', signal);
  }
  const interrupt = () => receive('SIGINT');
  const terminate = () => receive('SIGTERM');
  process.on('SIGINT', interrupt); process.on('SIGTERM', terminate);
  const pending = plan.map(service => {
    const child = spawn(service.command, service.args, {cwd: service.cwd, env: service.env, shell: service.shell, stdio: 'inherit', detached: process.platform !== 'win32'});
    children.push(child);
    services.set(child, service.name);
    child.once('spawn', () => record(child, 'child_started', { reason: 'launch' }));
    return new Promise(accept => {
      child.once('error', error => {
        record(child, 'child_error', { reason: 'child_start_error', error_code: error.code });
        if (!stopping) {
          failure = `${service.name} could not start (${error.code ?? 'unknown'}).`;
          stop('child_start_error', null, child);
        }
        accept();
      });
      child.once('exit', (code, signal) => {
        record(child, 'child_exit', { code, signal, reason: stopping ? reason : 'unexpected_child_exit' });
        if (!stopping) {
          failure = `${service.name} exited (${exitDescription(code, signal)}); stopping this workspace.`;
          stop('unexpected_child_exit', signal, child);
        }
        accept();
      });
    });
  });
  try {
    await Promise.all(pending);
    log('cleanup_started', { reason });
    await finishOwnedProcessGroups(children, 6000,
      (child, event, details) => record(child, event, { reason: 'owned_group_cleanup', ...details }));
    log('cleanup_finished', { reason });
  } finally {
    clearTimeout(timer);
    process.removeListener('SIGINT', interrupt); process.removeListener('SIGTERM', terminate);
  }
  if (failure) throw new Error(failure);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {console.error(error.message); process.exitCode = 1;});
}
