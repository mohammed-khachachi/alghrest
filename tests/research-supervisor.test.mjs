import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { runServices } from '../scripts/run_research.mjs';
import { requireFreePort } from '../scripts/openterminal.mjs';

test('an exited service leader cannot leave its child server listening', {skip:process.platform==='win32'}, async()=>{
  const directory=await mkdtemp(resolve(tmpdir(),'research-supervisor-test-'));
  const marker=resolve(directory,'owned-process.json');
  const server=`import {createServer} from 'node:net';import {writeFileSync} from 'node:fs';const s=createServer();s.listen(0,'127.0.0.1',()=>{writeFileSync(process.argv[1],JSON.stringify({port:s.address().port,group:process.ppid}));process.send('ready');});`;
  const leader=`import {fork} from 'node:child_process';const c=fork('-e',[${JSON.stringify(server)},${JSON.stringify(marker)}],{execArgv:[],stdio:['ignore','ignore','ignore','ipc']});c.on('message',()=>process.exit(0));`;
  let record;
  try {
    await assert.rejects(runServices([{name:'owned leader fixture',command:process.execPath,args:['--input-type=module','-e',leader],cwd:directory,env:{},shell:false}]),/exited/);
    record=JSON.parse(await readFile(marker,'utf8'));
    await requireFreePort(record.port);
  } finally {
    if(record) {try{process.kill(-record.group,'SIGKILL');}catch(error){if(error.code!=='ESRCH')throw error;}}
    await rm(directory,{recursive:true,force:true});
  }
});
