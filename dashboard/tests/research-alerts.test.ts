import test from 'node:test';
import assert from 'node:assert/strict';
import {researchAlerts} from '../src/lib/researchAlerts';
import type {TerminalResearch} from '../src/lib/terminalResearch';
import type {ResearchSnapshot} from '../src/lib/researchJournal';
const report=(next=false):TerminalResearch=>{
 const time=next?'2026-10-16T12:00:00Z':'2026-10-16T08:00:00Z';
 return {schema_version:'openterminal-research-v1',symbol:'BTC',requested_range:'6M',assessed_at:time,
 quote:null,analysis:{count:100,first_time:'2026-10-01T00:00:00Z',last_time:time,last_close:'100',sma20:next?'90':'110',sma50:next?'80':'120',rsi14_simple:next?'75':'65',atr14_simple:next?'3':'2',recent20_low:'50',recent20_high:'130',trend:next?'above_averages':'below_averages',history_provider:'binance',interval:'4h',interval_basis:'provider_request',history_fetched_at:time,history_cache_state:'fetched'},
 data_quality:{schema_version:'candle-quality-v1',status:'usable',received_candles:100,invalid_candles:0,invalid_timestamps:0,duplicate_timestamps:0,out_of_order_pairs:0,future_timestamps:0,interval_seconds:14400,gap_count:0,missing_intervals:0,irregular_intervals:0,largest_gap_seconds:14400,continuity_basis:'continuous',reasons:[],trend:{allowed:true,reasons:[]},momentum:{allowed:true,reasons:[]},volatility:{allowed:true,reasons:[]}},
 headlines:[],sources:(['quotes','history','news'] as const).map(kind=>({kind,state:'available',received_at:time,response_sha256:next?'b'.repeat(64):'a'.repeat(64),reasons:[]})),freshness:'UNKNOWN',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false};
};
const snapshot=():ResearchSnapshot=>({schema_version:'research-snapshot-v1',id:'a'.repeat(32),saved_at:'2026-10-16T08:00:00Z',report:report()});
test('three meaningful changes include the actual supporting numbers and stable identities',()=>{
 const result=researchAlerts(report(true),snapshot());
 assert.equal(result.reason,null);assert.deepEqual(result.alerts.map(a=>a.kind),['trend','momentum','volatility']);
 assert.match(result.alerts[0].evidence,/SMA20 110/);assert.match(result.alerts[1].evidence,/65.*75/);assert.match(result.alerts[2].evidence,/50%/);
 assert.deepEqual(researchAlerts(report(true),snapshot()),result);
});
test('unchanged thresholds and tiny ATR percent movement produce no alert',()=>{
 const next=report(true);Object.assign(next.analysis!,{trend:'below_averages',rsi14_simple:'66',atr14_simple:'2.1'});
 assert.equal(researchAlerts(next,snapshot()).alerts.length,0);
});
test('ATR percent is normalized to close: a price-scale change is not a volatility alert',()=>{
 const next=report(true);next.analysis!.atr14_simple='4';next.analysis!.last_close='200';
 assert(!researchAlerts(next,snapshot()).alerts.some(a=>a.kind==='volatility'));
});
test('zero previous ATR and sub-0.25 point changes do not invent large relative significance',()=>{
 for(const pair of [['0','1'],['0.1','0.2']]) {const old=snapshot(),next=report(true);old.report.analysis!.atr14_simple=pair[0];next.analysis!.atr14_simple=pair[1];assert(!researchAlerts(next,old).alerts.some(a=>a.kind==='volatility'));}
});
test('quality guards can suppress just momentum without hiding valid trend changes',()=>{
 const next=report(true);next.data_quality!.momentum={allowed:false,reasons:['insufficient_samples']};next.analysis!.rsi14_simple=null;next.data_quality!.reasons=['insufficient_samples'];next.data_quality!.status='limited';
 assert.deepEqual(researchAlerts(next,snapshot()).alerts.map(a=>a.kind),['trend','volatility']);
});
test('RSI thresholds include arrival at 30/70 and describe both directions',()=>{
 for(const [old,value] of [['29','30'],['69','70'],['71','70'],['31','30']]) {const before=snapshot(),next=report(true);before.report.analysis!.rsi14_simple=old;next.analysis!.rsi14_simple=value;assert(researchAlerts(next,before).alerts.some(a=>a.kind==='momentum'));}
});
test('missing history, source digest or quality and mismatched provenance all suppress alerts',()=>{
 const cases:Array<(r:TerminalResearch)=>void>=[r=>{r.analysis=null},r=>{r.data_quality=null},r=>{r.sources[1].state='unavailable'},r=>{r.sources[1].response_sha256=null},r=>{r.analysis!.history_provider='yahoo'},r=>{r.analysis!.interval='1h'},r=>{r.analysis!.interval='UNVERIFIED'},r=>{r.analysis!.interval_basis='UNVERIFIED'},r=>{r.analysis!.history_cache_state='stale'},r=>{r.analysis!.history_fetched_at=null},r=>{r.analysis!.history_fetched_at='2026-10-16T08:00:00Z'},r=>{r.analysis!.history_fetched_at='2026-10-16T13:00:00Z'},r=>{r.data_quality!.reasons=['missing_intervals']},r=>{r.data_quality!.status='unavailable'},r=>{r.symbol='ETH'},r=>{r.assessed_at='2026-10-16T07:00:00Z'}];
 for(const change of cases){const next=report(true);change(next);const result=researchAlerts(next,snapshot());assert.equal(result.alerts.length,0);assert(result.reason);}
});
test('same bar, backward bar, stale fetch, old bars and imported snapshots are explicitly suppressed',()=>{
 for(const time of ['2026-10-16T08:00:00Z','2026-10-16T04:00:00Z']){const next=report(true);next.analysis!.last_time=time;assert.equal(researchAlerts(next,snapshot()).alerts.length,0);}
 const oldFetch=report(true);oldFetch.analysis!.history_fetched_at='2026-10-16T10:00:00Z';assert.equal(researchAlerts(oldFetch,snapshot()).alerts.length,0);
 const imported=snapshot();imported.restored_from_backup='f'.repeat(64);assert.equal(researchAlerts(report(true),imported).alerts.length,0);
 assert.equal(researchAlerts(report(true),snapshot(),true).alerts.length,0);assert.equal(researchAlerts(report(true),null).alerts.length,0);
});
test('unknown calendar interval and stale bars cannot be treated as fresh events',()=>{
 const old=snapshot(),next=report(true);for(const r of [old.report,next]){r.analysis!.interval='1mo';}
 assert.equal(researchAlerts(next,old).alerts.length,0);
 const stale=snapshot();stale.report.analysis!.last_time='2026-09-01T00:00:00Z';assert.equal(researchAlerts(report(true),stale).alerts.length,0);
});
test('session-unverified source stays explicit but no session is inferred',()=>{
 const old=snapshot(),next=report(true);
 for(const r of [old.report,next]){r.analysis!.history_provider='yahoo';r.analysis!.interval='1d';r.data_quality!.status='limited';r.data_quality!.continuity_basis='session_unverified';r.data_quality!.reasons=['session_calendar_unverified'];}
 assert.equal(researchAlerts(next,old).alerts.length,3);
});
