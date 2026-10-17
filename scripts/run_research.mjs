import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { researchEnvironment, requireFreePort, signalOwnedProcess, finishOwnedProcessGroups } from './openterminal.mjs';

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
  let stopping = false;
  let failure = null;
  let timer;
  function signalChild(child, signal) {
    try {signalOwnedProcess(child,signal);} catch {console.error('Unable to stop a research child process group.');}
  }
  function stop() {
    if (stopping) return;
    stopping = true;
    for (const child of children) signalChild(child, 'SIGTERM');
    timer = setTimeout(() => {for (const child of children) signalChild(child, 'SIGKILL');}, 6000);
    timer.unref();
  }
  process.once('SIGINT', stop); process.once('SIGTERM', stop);
  const pending = plan.map(service => {
    const child = spawn(service.command, service.args, {cwd: service.cwd, env: service.env, shell: service.shell, stdio: 'inherit', detached: process.platform !== 'win32'});
    children.push(child);
    return new Promise(accept => {
      child.once('error', () => {failure = `${service.name} could not start.`; stop(); accept();});
      child.once('exit', code => {if (!stopping) {failure = `${service.name} exited (${code}); stopping this workspace.`; stop();} accept();});
    });
  });
  await Promise.all(pending);
  await finishOwnedProcessGroups(children);
  clearTimeout(timer);
  process.removeListener('SIGINT', stop); process.removeListener('SIGTERM', stop);
  if (failure) throw new Error(failure);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {console.error(error.message); process.exitCode = 1;});
}
