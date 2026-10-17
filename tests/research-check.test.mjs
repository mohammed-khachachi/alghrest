import test from 'node:test';
import assert from 'node:assert/strict';
import { checkPlan, snapshotFingerprints, verifyPreservedSnapshots } from '../scripts/check_research.mjs';

test('reliability services isolate both databases and only the assistant receives its test credential',()=>{
  const plan=checkPlan('/tmp/synthetic-research-check','synthetic-fixture','linux',{
    PATH:'/bin',ADVISORY_ACCESS_TOKEN:'real-secret',BINANCE_SECRET:'real-secret',NODE_OPTIONS:'--inspect',ENVIRONMENT:'live',DATA_DIR:'/real-data',
  });
  assert.equal(plan.length,4);
  assert(plan[0].env.ADVISORY_DB_PATH.endsWith('synthetic-research-check/journal.sqlite3'));
  assert.equal(plan[0].env.ADVISORY_ACCESS_TOKEN,'synthetic-fixture');
  for(const child of plan) {
    assert.equal(child.env.BINANCE_SECRET,undefined);assert.equal(child.env.NODE_OPTIONS,undefined);
    assert.notEqual(child.env.ENVIRONMENT,'live');
  }
  for(const child of plan.slice(1)) assert.equal(child.env.ADVISORY_ACCESS_TOKEN,undefined);
  for(const child of plan.slice(2)) assert(child.env.DATA_DIR.endsWith('synthetic-research-check/terminal/data'));
});
test('restart verification fails when a source clock or any saved field changes',()=>{
  const original=[{id:'fixture',report:{assessed_at:'2026-10-16T12:00:00Z',analysis:{history_fetched_at:'2026-10-16T11:00:00Z'}}}];
  assert.equal(Object.keys(snapshotFingerprints(original)).length,1);
  verifyPreservedSnapshots(original,structuredClone(original));
  const changed=structuredClone(original);changed[0].report.analysis.history_fetched_at='2026-10-16T12:00:00Z';
  assert.throws(()=>verifyPreservedSnapshots(original,changed));
  assert.throws(()=>verifyPreservedSnapshots(original,[]));
});
test('Windows preview plan keeps native port/environment isolation and correct executables',()=>{
  const plan=checkPlan('/tmp/synthetic-check','synthetic','win32',{});
  assert.equal(plan[2].command,'npm.cmd');assert.equal(plan[3].shell,true);
  assert.equal(plan[2].env.API_PORT,'4001');
  assert.equal(plan[3].env.API_URL,'http://127.0.0.1:4001');
});
