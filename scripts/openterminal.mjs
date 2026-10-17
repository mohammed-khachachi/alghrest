import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { createServer } from 'node:net';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const WEB_URL = 'http://127.0.0.1:3001';
export const API_URL = 'http://127.0.0.1:4001';
export const workspace = resolve(dirname(fileURLToPath(import.meta.url)), '../vendor/openterminal');

/** Only OS/runtime essentials cross the boundary; never inherit ALGHREST credentials. */
export function researchEnvironment(parent = process.env, directory = workspace) {
  const allowed = new Set([
    'PATH', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'SYSTEMROOT', 'WINDIR',
    'COMSPEC', 'PATHEXT', 'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'TZ', 'TERM',
  ]);
  const environment = Object.fromEntries(
    Object.entries(parent).filter(([key]) => allowed.has(key.toUpperCase())),
  );
  return {
    ...environment,
    API_HOST: '127.0.0.1', API_PORT: '4001', API_URL, WEB_ORIGIN: WEB_URL,
    DATA_DIR: resolve(directory, 'data'), API_KEY_FILE: resolve(directory, 'data/.api-key'),
    TRUST_PROXY: '0', NEXT_TELEMETRY_DISABLED: '1',
  };
}

export async function requireFreePort(port) {
  await new Promise((accept, reject) => {
    const server = createServer();
    server.once('error', () => reject(new Error(`Port ${port} is unavailable. Stop its owner or use the existing workspace.`)));
    server.listen(port, '127.0.0.1', () => server.close(accept));
  });
}

/** A terminated npm/Node leader can still have live descendants in its process group. */
export function signalOwnedProcess(child, signal = 'SIGTERM') {
  if (!child.pid) return;
  if (process.platform === 'win32') {
    if (child.exitCode === null && child.signalCode === null)
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {stdio:'ignore'});
  } else {
    try {process.kill(-child.pid, signal);} catch (error) {if (error.code !== 'ESRCH') throw error;}
  }
}

export async function finishOwnedProcessGroups(children, graceMs = 6000) {
  for (const child of children) signalOwnedProcess(child);
  if (process.platform === 'win32') return;
  const alive = child => {
    if (!child.pid) return false;
    try {process.kill(-child.pid, 0);return true;} catch(error) {if(error.code==='ESRCH')return false;throw error;}
  };
  const deadline=Date.now()+graceMs;
  while (children.some(alive) && Date.now()<deadline) await new Promise(accept=>setTimeout(accept,50));
  for (const child of children) signalOwnedProcess(child,'SIGKILL');
}

export async function main(args = process.argv.slice(2)) {
  if (args.includes('--help')) {
    console.log('Start: node scripts/openterminal.mjs\nCheck: node scripts/openterminal.mjs --check\nInstall first: run npm ci from vendor/openterminal');
    return;
  }
  if (args.some(arg => arg !== '--check')) throw new Error('Unknown option. Use --help.');
  if (!existsSync(resolve(workspace, 'node_modules/.package-lock.json'))) {
    throw new Error('OpenTerminal dependencies are missing. Run npm ci in vendor/openterminal first.');
  }
  await requireFreePort(3001);
  await requireFreePort(4001);
  if (args.includes('--check')) {
    console.log('Dependencies present; research ports 3001 and 4001 are available.');
    return;
  }

  console.log(`ALGHREST research: ${WEB_URL}\nPublic/indicative data. Separate manual journal. AI disabled. Ctrl+C to stop.`);
  const windows = process.platform === 'win32';
  const child = spawn(windows ? 'npm.cmd' : 'npm', ['run', 'dev'], {
    cwd: workspace, env: researchEnvironment(), stdio: 'inherit',
    shell: windows, detached: !windows,
  });
  let stopping = false;
  let stopTimer;
  function stop(signal = 'SIGTERM') {
    if (stopping || !child.pid) return;
    stopping = true;
    if (windows) {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' });
    } else {
      try { process.kill(-child.pid, signal); } catch (error) {
        if (error.code !== 'ESRCH') throw error;
      }
      stopTimer = setTimeout(() => {
        try { process.kill(-child.pid, 'SIGKILL'); } catch (error) {
          if (error.code !== 'ESRCH') console.error('Unable to stop the research process group.');
        }
      }, 5000);
      stopTimer.unref();
    }
  }
  const interrupt = () => stop('SIGINT');
  const terminate = () => stop();
  process.once('SIGINT', interrupt);
  process.once('SIGTERM', terminate);
  await new Promise((accept, reject) => {
    child.once('error', reject);
    child.once('exit', (code) => {
      if (!stopping && code !== 0) reject(new Error(`Research workspace exited (${code}).`));
      else accept();
    });
  }).finally(async () => {
    await finishOwnedProcessGroups([child]);
    clearTimeout(stopTimer);
    process.removeListener('SIGINT', interrupt);
    process.removeListener('SIGTERM', terminate);
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
