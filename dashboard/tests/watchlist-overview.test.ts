import test from 'node:test';
import assert from 'node:assert/strict';
import type { TerminalResearch } from '../src/lib/terminalResearch';
import { researchSnapshot } from '../src/lib/researchJournal';
import { emptyOverviewEntry, overviewReading, watchlistBatch, type BatchEvent } from '../src/lib/watchlistOverview';

const now = Date.parse('2026-10-15T12:00:00Z');
function report(offset = 0, symbol = 'AAPL'): TerminalResearch {
  const stamp = new Date(now + offset).toISOString();
  return {
    schema_version:'openterminal-research-v1', symbol, requested_range:'6M', assessed_at:stamp,
    quote:null, analysis:{count:60,first_time:'2026-08-01T00:00:00Z',last_time:'2026-10-14T00:00:00Z',last_close:'100',sma20:'90',sma50:'80',rsi14_simple:'60',atr14_simple:'2',recent20_low:'70',recent20_high:'105',trend:'above_averages',history_provider:'yahoo',interval:'1d',interval_basis:'provider_request',history_fetched_at:stamp,history_cache_state:'fetched'},
    headlines:[],sources:(['quotes','history','news'] as const).map(kind=>({kind,state:'available',received_at:stamp,response_sha256:'a'.repeat(64),reasons:[]})),
    freshness:'UNKNOWN',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false,
  };
}
function saved(offset = -100000, id = 1) {
  return researchSnapshot({schema_version:'research-snapshot-v1',id:id.toString(16).padStart(32,'0'),saved_at:new Date(now+offset).toISOString(),report:report(offset)},'AAPL',now);
}

test('initial overview uses saved snapshots and compares with the preceding one',()=>{
  const latest=saved(),older=saved(-200000,2);older.report.analysis!.rsi14_simple='55';
  const row=overviewReading('AAPL',{...emptyOverviewEntry(),history:[latest,older]},now);
  assert.equal(row.origin,'لقطة محفوظة');assert.equal(row.momentum,'60');
  assert.equal(row.previous!.id,older.id);assert.equal(row.changed,1);
});
test('fresh manual reading compares with the latest saved snapshot',()=>{
  const row=overviewReading('AAPL',{...emptyOverviewEntry(),history:[saved()],reading:report()},now);
  assert.equal(row.origin,'قراءة حالية');assert.equal(row.previous!.id,saved().id);
  assert.equal(row.volatility,'2 (2%)');
});
test('live expiry falls back to labelled historical data without rewriting its clock',()=>{
  const entry={...emptyOverviewEntry(),history:[saved()],reading:report()};
  const row=overviewReading('AAPL',entry,now+90000);
  assert(row.expired);assert.equal(row.origin,'لقطة محفوظة');
  assert.equal(row.report!.assessed_at,saved().report.assessed_at);
  assert.equal(entry.reading.assessed_at,report().assessed_at);
});
test('expired live reading without an archive cannot display stale indicators as current',()=>{
  const row=overviewReading('AAPL',{...emptyOverviewEntry(),history:[],reading:report()},now+90000);
  assert.equal(row.report,null);assert.equal(row.momentum,'غير متاح');assert(row.expired);
});
test('wrong-symbol reading cannot leak into another symbol row',()=>{
  const row=overviewReading('MSFT',{...emptyOverviewEntry(),history:[saved()],reading:report()},now);
  assert.equal(row.report,null);assert.equal(row.previous,null);
});
test('missing baseline is unknown, not zero changed indicators or headlines',()=>{
  const row=overviewReading('AAPL',{...emptyOverviewEntry(),reading:report(),historyError:'offline'},now);
  assert.equal(row.changed,null);assert.equal(row.newHeadlines,null);
});
test('missing feed and stale cache warnings remain visible in the overview',()=>{
  const r=report();r.analysis!.history_cache_state='stale';r.sources[2].state='unavailable';r.sources[2].response_sha256=null;
  const row=overviewReading('AAPL',{...emptyOverviewEntry(),history:[saved()],reading:r},now);
  assert(row.status.some(s=>s.kind==='history'&&s.status.includes('متعثر')));
  assert(row.status.some(s=>s.kind==='news'&&s.status==='غير متاح'));
  assert.equal(row.newHeadlines,null);
});
test('new headline count is based on returned URLs and volatility preserves zero',()=>{
  const r=report();r.analysis!.atr14_simple='0';
  r.headlines=[{title:'Fixture headline',url:'https://example.org/new',publisher:'Fixture',published_at:null}];
  const row=overviewReading('AAPL',{...emptyOverviewEntry(),history:[saved()],reading:r},now);
  assert.equal(row.newHeadlines,1);assert.equal(row.volatility,'0 (0%)');
});
test('failed refresh keeps the previous successful reading clock and explicit error state',()=>{
  const entry={...emptyOverviewEntry(),reading:report(-10000),phase:'error' as const,error:'offline'};
  const row=overviewReading('AAPL',entry,now);
  assert.equal(row.report!.assessed_at,report(-10000).assessed_at);assert.equal(entry.phase,'error');
});
test('refresh is bounded to two in-flight symbols and every item receives one terminal event',async()=>{
  let active=0,max=0;
  const events:BatchEvent<string>[]=[];
  await watchlistBatch(['A','B','C','D'],async symbol=>{
    active++;max=Math.max(max,active);await Promise.resolve();active--;return symbol;
  },e=>events.push(e));
  assert.equal(max,2);assert.equal(events.filter(e=>e.phase==='done').length,4);
  assert.deepEqual(events.filter(e=>e.phase==='done').map(e=>e.symbol).sort(),['A','B','C','D']);
});
test('one failed symbol does not prevent other symbols from finishing',async()=>{
  const events:BatchEvent<string>[]=[];
  await watchlistBatch(['A','B','C'],async symbol=>{if(symbol==='A')throw new Error('private internal detail');return symbol;},e=>events.push(e));
  assert.equal(events.filter(e=>e.phase==='error').length,1);
  assert.equal(events.filter(e=>e.phase==='done').length,2);
  assert(!JSON.stringify(events).includes('private internal detail'));
});
test('stop skips queued symbols but drains the two running requests',async()=>{
  let stop=false;const resolvers:Array<()=>void>=[];const fetched:string[]=[];const events:BatchEvent<string>[]=[];
  const running=watchlistBatch(['A','B','C','D'],async symbol=>{
    fetched.push(symbol);await new Promise<void>(resolve=>resolvers.push(resolve));return symbol;
  },e=>events.push(e),()=>stop);
  assert.deepEqual(fetched,['A','B']);stop=true;resolvers.forEach(resolve=>resolve());await running;
  assert.equal(events.filter(e=>e.phase==='done').length,2);
  assert.deepEqual(events.filter(e=>e.phase==='skipped').map(e=>e.symbol).sort(),['C','D']);
});
test('empty batch makes no request, and invalid/duplicate/oversized lists are rejected',async()=>{
  let calls=0;const load=async()=>{calls++;return '';};
  await watchlistBatch([],load,()=>{});assert.equal(calls,0);
  for(const symbols of [['AAPL','AAPL'],['../x'],Array.from({length:51},(_,i)=>`SYM${i}`)])
    await assert.rejects(watchlistBatch(symbols,load,()=>{}));
  assert.equal(calls,0);
});
