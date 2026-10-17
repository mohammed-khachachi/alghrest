import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { randomBytes, createHash } from 'node:crypto';
import { createWriteStream, existsSync } from 'node:fs';
import { mkdir, mkdtemp, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { resolve } from 'node:path';
import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import { fileURLToPath } from 'node:url';
import { PORTS, ROOT, researchPlan } from './run_research.mjs';
import { requireFreePort, researchEnvironment } from './openterminal.mjs';

const API = 'http://127.0.0.1:8011/assistant-api';
const PREVIEW_TOKEN = 'synthetic_reliability_' + 'x'.repeat(32); // Disposable public-data fixture only.

export function checkPlan(directory, token, platform = process.platform, parent = process.env) {
  const normal = researchPlan(parent, platform);
  const terminal = researchEnvironment(parent, resolve(directory, 'terminal'));
  const windows = platform === 'win32';
  return [
    {...normal[0], name:'assistant', env:{...normal[0].env,
      ADVISORY_DB_PATH:resolve(directory, 'journal.sqlite3'), ADVISORY_ACCESS_TOKEN:token}},
    {...normal[1], name:'dashboard'},
    {name:'terminal-api', command:windows ? 'npm.cmd' : 'npm', args:['run','dev','-w','server'],
      cwd:resolve(ROOT,'vendor/openterminal'), shell:windows, env:{...terminal}},
    {name:'terminal-web', command:windows ? 'npm.cmd' : 'npm', args:['run','dev','-w','web'],
      cwd:resolve(ROOT,'vendor/openterminal'), shell:windows, env:{...terminal}},
  ];
}

export function snapshotFingerprints(records) {
  return Object.fromEntries(records.map(record => [record.id, createHash('sha256').update(JSON.stringify(record)).digest('hex')]));
}
export function verifyPreservedSnapshots(expected, actual) {
  assert.deepEqual(snapshotFingerprints(actual), snapshotFingerprints(expected), 'Saved snapshot content or original clocks changed');
}

const delay = ms => new Promise(accept => setTimeout(accept, ms));

export async function main(args = process.argv.slice(2)) {
  if (args.includes('--help')) {
    console.log('Check the complete research workspace: node scripts/check_research.mjs\nRun when ports 8011/5173/3001/4001 are free. Uses an isolated journal, stops its own services, and saves a dated receipt in artifacts/.\nOptional --preview pauses at three checkpoints; press Enter after browser verification.\nA pass verifies engineering behavior; public-data freshness remains unverified.');
    return;
  }
  if (args.some(arg => arg !== '--preview')) throw new Error('Unknown option. Use --help.');
  const preview = args.includes('--preview');
  const previewInput = preview ? createInterface({input:process.stdin,output:process.stdout,terminal:false}) : null;
  let inputClosed = false;
  previewInput?.once('close',()=>{inputClosed=true;});
  const token = preview ? PREVIEW_TOKEN : randomBytes(32).toString('hex');
  const started = new Date();
  const stamp = started.toISOString().replaceAll(':','-').replace(/\.\d+Z$/,'Z');
  const evidence = resolve(ROOT, 'artifacts', `research-check-${stamp}`);
  await mkdir(evidence, {recursive:true});
  const work = await mkdtemp(resolve(tmpdir(), 'alghrest-research-check-'));
  const owned = [];
  const checks = [];
  let cancelled = false;
  let unexpected = '';
  let sequence = 0;
  let sessionPortsChecked = false;
  const onInterrupt = () => { cancelled = true; previewInput?.close(); void stopAll().catch(()=>{}); };
  process.once('SIGINT', onInterrupt); process.once('SIGTERM', onInterrupt);
  const alive = () => {
    if (cancelled) throw new Error('Check interrupted; cleaning up owned processes.');
    if (unexpected) throw new Error(unexpected);
  };
  async function step(name, action) {
    alive();
    console.log(`Checking ${name}...`);
    const begin = Date.now();
    try {
      const result = await action();
      checks.push({name, status:'passed', elapsed_ms:Date.now()-begin, ...(result ?? {})});
      console.log(`Passed: ${name}`);
    } catch (error) {
      checks.push({name,status:'failed',elapsed_ms:Date.now()-begin});
      throw error;
    }
  }
  async function command(name, executable, argv, cwd = ROOT, timeout = 120000) {
    alive();
    const log = createWriteStream(resolve(evidence, `${name}.log`));
    const child = spawn(executable, argv, {cwd, env:researchEnvironment(), shell:false,
      detached:process.platform !== 'win32', stdio:['ignore','pipe','pipe']});
    const handle = {child, expected:true, log}; owned.push(handle);
    child.stdout.pipe(log, {end:false}); child.stderr.pipe(log, {end:false});
    try { await new Promise((accept,reject) => {
      const timer = setTimeout(() => { void stop(handle).then(() => reject(new Error(`${name} timed out; see its saved log.`))); },timeout);
      child.once('error', () => {clearTimeout(timer); reject(new Error(`${name} could not start.`));});
      child.once('exit', code => {clearTimeout(timer); log.end(); code===0 ? accept() : reject(new Error(`${name} failed; see its saved log.`));});
    }); } finally { await stop(handle); }
  }
  function start(spec) {
    alive();
    const log = createWriteStream(resolve(evidence, `${++sequence}-${spec.name}.log`));
    const child = spawn(spec.command,spec.args,{cwd:spec.cwd,env:spec.env,shell:spec.shell,
      detached:process.platform !== 'win32',stdio:['ignore','pipe','pipe']});
    const handle = {child,expected:false,log}; owned.push(handle);
    child.stdout.pipe(log,{end:false}); child.stderr.pipe(log,{end:false});
    child.once('error',()=>{if(!handle.expected) unexpected=`${spec.name} could not start.`;});
    child.once('exit',()=>{log.end();if(!handle.expected) unexpected=`${spec.name} exited unexpectedly; see its saved log.`;});
    return handle;
  }
  async function stop(handle) {
    if(handle.stopping) return handle.stopping;
    handle.expected = true;
    handle.stopping = (async()=>{
    const {child} = handle;
    if (!child.pid) return;
    if (process.platform === 'win32') {
      await new Promise(accept => {const kill=spawn('taskkill',['/pid',String(child.pid),'/T','/F'],{stdio:'ignore'});kill.once('exit',accept);kill.once('error',accept);});
    } else {
      const signal = value => {try {process.kill(-child.pid,value);} catch(error) {if(error.code!=='ESRCH') throw error;}};
      signal('SIGTERM');
      if (child.exitCode===null && child.signalCode===null)
        await Promise.race([new Promise(accept=>child.once('exit',accept)),delay(6000)]);
      // Descendants can outlive an exited npm leader. Clean its owned group too.
      signal('SIGKILL');
    }
    handle.log.end();
    const index=owned.indexOf(handle);if(index>=0) owned.splice(index,1);
    })();
    return handle.stopping;
  }
  async function stopAll() {
    for (const handle of [...owned].reverse()) await stop(handle);
    owned.length = 0;
  }
  async function response(path, {method='GET',body,auth=true} = {}) {
    alive();
    return fetch(API+path,{method,headers:{...(auth ? {Authorization:`Bearer ${token}`} : {}),
      ...(body ? {'Content-Type':'application/json','X-Advisory-Client':'dashboard'} : {})},
      ...(body ? {body:JSON.stringify(body)} : {}),signal:AbortSignal.timeout(35000)});
  }
  async function json(path, options) {
    const r=await response(path,options);
    if (!r.ok) throw new Error(`Local request failed (${r.status}); ${path.split('?')[0]}`);
    return r.json();
  }
  async function ready(url, verify = () => true) {
    const deadline=Date.now()+90000;
    while(Date.now()<deadline) {
      alive();
      try {
        const r=await fetch(url,{signal:AbortSignal.timeout(3000)});
        if(r.ok && await verify(r)) return;
      } catch { /* Compilation and service startup are bounded by the deadline. */ }
      await delay(400);
    }
    throw new Error(`Workspace did not become ready: ${new URL(url).port}`);
  }
  async function previewPause(phase) {
    await writeFile(resolve(evidence,'phase.json'),JSON.stringify({phase,at:new Date().toISOString()}));
    if(preview) {
      console.log(`Browser preview: ${phase}. Press Enter to continue; Ctrl+C stops owned services.`);
      if(inputClosed) throw new Error('Preview requires an open input terminal.');
      await new Promise((accept,reject)=>{
        const cleanup=()=>{previewInput.removeListener('line',next);previewInput.removeListener('close',closed);};
        const next=()=>{cleanup();accept();};
        const closed=()=>{cleanup();reject(new Error('Preview input closed; stopping the check.'));};
        previewInput.once('line',next);previewInput.once('close',closed);
      });
    }
  }
  const plan=checkPlan(work,token);
  let terminalApi;
  async function startAll() {
    for(const spec of plan) {const h=start(spec);if(spec.name==='terminal-api') terminalApi=h;}
    await Promise.all([
      ready('http://127.0.0.1:8011/health/live'), ready('http://127.0.0.1:5173/research'),
      ready('http://127.0.0.1:4001/api/status',async r=>{const s=await r.json();return s.integration==='alghrest-research' && s.ai===false && s.execution_enabled===false;}),
      ready('http://127.0.0.1:3001/'),
    ]);
  }
  let failure = null;
  try {
    await step('dependencies and free ports',async()=>{
      for(const path of [plan[0].command,'dashboard/node_modules/.package-lock.json','vendor/openterminal/node_modules/.package-lock.json'])
        assert(existsSync(resolve(ROOT,path)), 'Install the project and frontend dependencies first.');
      for(const port of PORTS) await requireFreePort(port);
      sessionPortsChecked = true;
      await command('pdf-dependencies',plan[0].command,['-c','import reportlab, arabic_reshaper, bidi']);
    });
    const bridge = resolve(work,'research-validators.cjs');
    const esbuild=resolve(ROOT,'dashboard/node_modules/esbuild/lib/main.js');
    const compile="require(process.argv[1]).buildSync({entryPoints:[process.argv[2]],bundle:true,platform:'node',format:'cjs',outfile:process.argv[3]})";
    await step('focused regression suites',async()=>{
      await command('launcher-tests',process.execPath,['--test','tests/openterminal-launcher.test.mjs','tests/research-launcher.test.mjs','tests/research-check.test.mjs','tests/research-supervisor.test.mjs']);
      await command('python-tests',plan[0].command,['-m','pytest','--no-cov','-q',
        'tests/unit/test_research_diagnostics.py','tests/unit/test_research_brief.py','tests/unit/test_research_journal.py','tests/unit/test_research_backup.py','tests/unit/test_research_quality.py','tests/unit/test_research_freshness.py','tests/unit/test_openterminal_research.py','tests/unit/test_openterminal_context.py','tests/unit/test_advisory_api.py']);
      const dashboardTests=resolve(work,'dashboard-tests');await mkdir(dashboardTests);
      for(const file of (await readdir(resolve(ROOT,'dashboard/tests'))).filter(f=>f.endsWith('.test.ts')).sort()) {
        const out=resolve(dashboardTests,file.replace(/\.ts$/,'.cjs'));
        await command(`compile-${file}`,process.execPath,['-e',compile,esbuild,resolve(ROOT,'dashboard/tests',file),out]);
        await command(`dashboard-${file}`,process.execPath,[out]);
      }
      await command('native-tests',process.execPath,[resolve(ROOT,'vendor/openterminal/node_modules/vitest/vitest.mjs'),'run'],resolve(ROOT,'vendor/openterminal/server'));
      await command('compile-validators',process.execPath,['-e',compile,esbuild,resolve(ROOT,'dashboard/src/lib/researchJournal.ts'),bridge]);
    });
    const {researchHistory,researchSnapshot}=createRequire(import.meta.url)(bridge);
    await step('four-service startup',startAll);
    await step('authentication and workspace boundaries',async()=>{
      assert.equal((await response('/research-watchlist',{auth:false})).status,401);
      const health=await json('/health');assert.equal(health.execution_enabled,false);assert.equal(health.agent_tap_enabled,false);
      const status=await (await fetch('http://127.0.0.1:3001/api/status')).json();assert.equal(status.ai,false);assert.equal(status.execution_enabled,false);
      const page=await fetch('http://127.0.0.1:5173/research');assert.equal(page.status,200);
    });
    const saved={};
    await step('symbol isolation, snapshots and safe retries',async()=>{
      const availability={};
      for(const symbol of ['AAPL','MSFT']) {
        await json(`/research-watchlist/${symbol}`,{method:'PUT',body:{watched:true}});
        const id=randomBytes(16).toString('hex');
        const snapshot=researchSnapshot(await json(`/research-snapshots/${symbol}`,{method:'POST',body:{id}}),symbol);
        assert.equal(snapshot.report.symbol,symbol);
        assert.equal(snapshot.report.trade_permitted,false);assert.equal(snapshot.report.execution_enabled,false);
        assert(snapshot.report.data_quality, 'New research snapshots must include candle quality');
        const retried=await json(`/research-snapshots/${symbol}`,{method:'POST',body:{id}});
        assert.deepEqual(retried,snapshot);
        saved[symbol]=researchHistory(await json(`/research-snapshots/${symbol}`),symbol);
        availability[symbol]=Object.fromEntries(snapshot.report.sources.map(s=>[s.kind,s.state]));
        assert.equal(saved[symbol].length,1);
      }
      // Provider failure is allowed; a dead market API is a workflow failure.
      const nativeHealth=await fetch('http://127.0.0.1:4001/api/status',{signal:AbortSignal.timeout(3000)});
      assert.equal(nativeHealth.status,200,'Market API died during overlapping symbol requests');
      const diagnostics=await json('/research-diagnostics/AAPL');
      assert.equal(diagnostics.state,'available','Authenticated diagnostics must remain available even when public feeds fail');
      assert.equal(diagnostics.diagnostics.symbol,'AAPL');
      await writeFile(resolve(evidence,'diagnostics-check.json'),JSON.stringify(diagnostics,null,2));
      await writeFile(resolve(evidence,'public-source-status.json'),JSON.stringify(availability,null,2));
      return {public_data_quality:'not certified; partial/unavailable feeds remain explicit'};
    });
    await step('research backup preview, exact restore and safe retries',async()=>{
      const download=await response('/research-backup');assert.equal(download.status,200);
      const raw=await download.text();const archive=JSON.parse(raw);
      const path=resolve(evidence,'isolated-research-backup.json');await writeFile(path,raw);
      const preview=await json('/research-backup/preview',{method:'POST',body:archive});
      assert.equal(preview.snapshots_added,0);assert.equal(preview.snapshots_unchanged,2);
      const retry=await json('/research-backup/restore',{method:'POST',body:archive});assert.deepEqual(retry,preview);
      const restored=resolve(work,'restored-journal.sqlite3');
      await command('backup-restore',plan[0].command,['scripts/research_backup.py','restore','--database',restored,'--file',path,'--apply']);
      await command('backup-exact-bytes',plan[0].command,['-c',
        "import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); q='SELECT id,symbol,saved,payload FROM research_snapshots ORDER BY id'; assert a.execute(q).fetchall()==b.execute(q).fetchall(); assert b.execute('SELECT COUNT(*) FROM research_restores').fetchone()[0]==2; print('Exact research payload restoration and restore provenance passed')",
        resolve(work,'journal.sqlite3'),restored]);
      for(const symbol of ['AAPL','MSFT']) verifyPreservedSnapshots(saved[symbol],researchHistory(await json(`/research-snapshots/${symbol}`),symbol));
    });
    await previewPause('normal');
    await step('market service outage with saved research and PDF intact',async()=>{
      await stop(terminalApi);await requireFreePort(4001);
      const outage=await json('/openterminal-research/AAPL');
      assert(outage.sources.every(s=>s.state==='unavailable'));assert.equal(outage.quote,null);assert.equal(outage.analysis,null);
      assert.equal(outage.data_quality.status,'unavailable');assert.equal(outage.data_quality.received_candles,null);
      assert.deepEqual(outage.headlines,[]);
      verifyPreservedSnapshots(saved.AAPL,researchHistory(await json('/research-snapshots/AAPL'),'AAPL'));
      const pdf=await response('/research-brief.pdf');assert.equal(pdf.status,200);assert.equal(pdf.headers.get('content-type'),'application/pdf');
      const bytes=Buffer.from(await pdf.arrayBuffer());assert(bytes.subarray(0,5).equals(Buffer.from('%PDF-')));assert(bytes.includes(Buffer.from('/FontFile2')));
      await writeFile(resolve(evidence,'pdf-check.json'),JSON.stringify({bytes:bytes.length,sha256:createHash('sha256').update(bytes).digest('hex'),market_service_down:true}));
    });
    await previewPause('market-unavailable');
    await step('market service recovery',async()=>{
      terminalApi=start(plan.find(s=>s.name==='terminal-api'));
      await ready('http://127.0.0.1:4001/api/status');
      const record=researchSnapshot(await json('/research-snapshots/AAPL',{method:'POST',body:{id:randomBytes(16).toString('hex')}}),'AAPL');
      assert.equal(record.report.symbol,'AAPL');
      saved.AAPL=researchHistory(await json('/research-snapshots/AAPL'),'AAPL');assert.equal(saved.AAPL.length,2);
    });
    await step('complete restart and durable history',async()=>{
      await stopAll();if(sessionPortsChecked) for(const port of PORTS) await requireFreePort(port);
      await startAll();
      assert.deepEqual((await json('/research-watchlist')).map(w=>w.symbol),['AAPL','MSFT']);
      for(const symbol of ['AAPL','MSFT']) verifyPreservedSnapshots(saved[symbol],researchHistory(await json(`/research-snapshots/${symbol}`),symbol));
      await json('/research-watchlist/MSFT',{method:'PUT',body:{watched:false}});
      verifyPreservedSnapshots(saved.MSFT,researchHistory(await json('/research-snapshots/MSFT'),'MSFT'));
      await json('/research-watchlist/MSFT',{method:'PUT',body:{watched:true}});
      assert.equal((await response('/research-brief.pdf')).status,200);
    });
    await previewPause('restarted');
    await writeFile(resolve(evidence,'snapshot-fingerprints.json'),JSON.stringify(Object.fromEntries(Object.entries(saved).map(([s,r])=>[s,snapshotFingerprints(r)])),null,2));
    await writeFile(resolve(evidence,'saved-research.json'),JSON.stringify(saved,null,2));
  } catch(error) {
    failure=error instanceof Error ? error.message : 'Research check failed.';
    console.error(failure);
  } finally {
    try {
      await stopAll();if(sessionPortsChecked) for(const port of PORTS) await requireFreePort(port);
      checks.push({name:sessionPortsChecked ? 'owned service shutdown and free ports' : 'existing port owners left untouched',status:'passed'});
    } catch {failure ||= 'Owned services did not fully stop; inspect the saved service logs.';checks.push({name:'owned service shutdown and free ports',status:'failed'});}
    process.removeListener('SIGINT',onInterrupt);process.removeListener('SIGTERM',onInterrupt);
    previewInput?.close();
    if(!failure) await rm(work,{recursive:true,force:true});
    await writeFile(resolve(evidence,'verification.json'),JSON.stringify({schema:'alghrest-research-workflow-check-v1',started_at:started.toISOString(),finished_at:new Date().toISOString(),status:failure?'failed':'passed',checks,
      isolation:'temporary synthetic local journal and terminal data; no user account database or credentials',
      limits:['public freshness and event coverage are not certified','browser interactions are verified separately; the command checks service/API behavior and frontend contracts','full infrastructure, coverage gate and real trading are outside this check'],failure},null,2)+'\n');
    console.log(`Verification receipt: ${resolve(evidence,'verification.json')}`);
  }
  if(failure) throw new Error('Research workspace check failed. Review the saved receipt and logs.');
  console.log('Research workspace check passed. Saved records survived restart; temporary services stopped.');
  return evidence;
}

if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url))
  main().catch(error=>{console.error(error.message);process.exitCode=1;});
