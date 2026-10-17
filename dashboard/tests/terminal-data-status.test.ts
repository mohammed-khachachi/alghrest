import test from 'node:test';
import assert from 'node:assert/strict';
import { terminalResearch } from '../src/lib/terminalResearch';
import { terminalDataStatus, dataAge, sourceTime } from '../src/lib/terminalDataStatus';
const now=Date.parse('2026-10-15T12:00:00Z');
const stamp=new Date(now).toISOString();
function raw() {return {
  schema_version:'openterminal-research-v1',symbol:'AAPL',requested_range:'6M',assessed_at:stamp,
  quote:{symbol:'AAPL',name:'Fixture',price:'10',change_percent:'1',currency:'USD',provider:'nasdaq',market_time:null},
  analysis:{count:60,first_time:'2026-08-15T12:00:00Z',last_time:'2026-10-14T12:00:00Z',last_close:'10',sma20:'9',sma50:'8',rsi14_simple:'50',atr14_simple:'1',recent20_low:'7',recent20_high:'11',trend:'above_averages',history_provider:'yahoo',interval:'1d',interval_basis:'provider_request',history_fetched_at:'2026-10-15T11:40:00Z',history_cache_state:'stale'},
  headlines:[],sources:['quotes','news','history'].map(kind=>({kind,state:'available',received_at:stamp,response_sha256:'a'.repeat(64),reasons:[]})),
  freshness:'UNKNOWN',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false,
};}
function cards(value=raw()) {const report=terminalResearch(value,'AAPL',now);assert(report);return terminalDataStatus(report,now);}
test('stale cache is explicit and does not replace the original fetch clock with receipt time',()=>{
  const c=cards().find(c=>c.kind==='history')!;
  assert.equal(c.status,'تحديث متعثر · نسخة سابقة');assert.equal(c.tone,'warning');
  assert(c.details.some(([key,value])=>key==='آخر جلب ناجح في OpenTerminal'&&value===sourceTime('2026-10-15T11:40:00Z')));
  assert(c.details.some(([key,value])=>key==='استلام ALGHREST'&&value===sourceTime(stamp)));
  assert(c.details.some(([key,value])=>key==='مزوّد الشموع'&&value==='yahoo'));
  assert(c.details.some(([key,value])=>key==='الإطار الزمني'&&value==='يومي'));
});
test('missing quote timestamp never becomes a fresh or zero-age quote',()=>{
  const c=cards().find(c=>c.kind==='quotes')!;
  assert.equal(c.status,'متاح · حداثته غير معلومة');
  assert(c.details.some(([key,value])=>key==='عمر السعر'&&value==='غير معلوم'));
});
test('old quote time is an age warning rather than a claim about exchange opening hours',()=>{
  const value={...raw(),quote:{...raw().quote,market_time:'2026-10-15T11:00:00Z'}};
  const report=terminalResearch(value,'AAPL',now);assert(report);
  const c=terminalDataStatus(report,now).find(c=>c.kind==='quotes')!;
  assert.equal(c.status,'وقت السعر أقدم من 15 دقيقة');
  assert(c.details.some(([key,value])=>key==='تنبيه العمر'&&value.includes('جلسة التداول')));
});
test('legacy arrays expose unknown timeframe and cache state, not inferred daily data',()=>{
  const value={...raw(),analysis:{...raw().analysis,history_provider:'UNKNOWN',interval:'UNVERIFIED',interval_basis:'UNVERIFIED',history_fetched_at:null,history_cache_state:'UNKNOWN'}};
  const report=terminalResearch(value,'AAPL',now);assert(report);
  const c=terminalDataStatus(report,now).find(c=>c.kind==='history')!;
  assert(c.details.some(([key,value])=>key==='الإطار الزمني'&&value==='غير معلن'));
  assert(!c.status.includes('متعثّر'));
});
test('a successful cache read is not mislabeled as a failed refresh or live market feed',()=>{
  const value=raw();value.analysis.history_cache_state='cached';
  const c=cards(value).find(c=>c.kind==='history')!;
  assert.equal(c.status,'متاح');
  assert(c.details.some(([key,value])=>key==='النسخة'&&value.includes('المؤقتة')));
});
test('unavailable history and an empty news response remain distinct',()=>{
  const value={...raw(),analysis:null,sources:raw().sources.map(s=>s.kind==='history'?{...s,state:'unavailable',response_sha256:null}:s)};
  const report=terminalResearch(value,'AAPL',now);assert(report);
  const rows=terminalDataStatus(report,now);
  assert.equal(rows.find(c=>c.kind==='history')!.status,'غير متاح');
  assert.equal(rows.find(c=>c.kind==='news')!.status,'لا عناوين صالحة');
});
test('forged future fetch clock, incomplete provenance and inconsistent interval basis are refused',()=>{
  for(const changes of [
    {history_fetched_at:'2026-10-15T13:00:00Z'}, {history_fetched_at:'2026-10-13T12:00:00Z'},
    {history_fetched_at:null}, {history_provider:'UNKNOWN'}, {interval_basis:'UNVERIFIED'},
  ]) assert.equal(terminalResearch({...raw(),analysis:{...raw().analysis,...changes}},'AAPL',now),null);
});
test('age distinguishes missing timestamps, minutes, hours and days',()=>{
  assert.equal(dataAge(null,now),'غير معلوم');
  assert.equal(dataAge('2026-10-15T11:40:00Z',now),'20 دقيقة');
  assert.equal(dataAge('2026-10-15T10:00:00Z',now),'2 ساعة');
  assert.equal(dataAge('2026-10-13T12:00:00Z',now),'2 يوم');
});
