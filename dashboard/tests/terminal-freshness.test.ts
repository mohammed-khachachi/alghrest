import test from 'node:test';
import assert from 'node:assert/strict';
import { terminalResearch, type TerminalResearch } from '../src/lib/terminalResearch';
import { quoteFreshness } from '../src/lib/terminalFreshness';
const now=Date.parse('2026-10-16T12:00:00Z');const stamp=new Date(now).toISOString();
function report(state='Closed',age=1200,fetchedAge=1): TerminalResearch {
 return {schema_version:'openterminal-research-v1',symbol:'AAPL',requested_range:'6M',assessed_at:stamp,
 quote:{symbol:'AAPL',name:null,price:'100',change_percent:null,currency:'USD',provider:'nasdaq',market_time:new Date(now-age*1000).toISOString(),market_state:state,
 observation:{schema_version:'quote-observation-v1',fetched_at:new Date(now-fetchedAge*1000).toISOString(),cache_state:'fetched',market_state_basis:'provider'}},
 analysis:null,headlines:[],sources:[{kind:'quotes',state:'available',received_at:stamp,response_sha256:'a'.repeat(64),reasons:[]},...(['history','news'] as const).map(kind=>({kind,state:'unavailable' as const,received_at:stamp,response_sha256:null,reasons:[]}))],freshness:'UNKNOWN',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false};
}
test('reported closed, open and extended sessions describe the source observation without a calendar',()=>{
 for(const [state,status] of [['Closed','closed_reported'],['REGULAR','old_while_open_reported'],['PRE','old_observation'],['POST','old_observation'],['other','old_observation']]) assert.equal(quoteFreshness(report(state),now).status,status);
 assert(terminalResearch(report(),'AAPL',now));
});
test('state expires at 90 seconds and old timestamps remain old despite a new fetch',()=>{
 assert.equal(quoteFreshness(report('Closed',1200,89),now).status,'closed_reported');
 assert.equal(quoteFreshness(report('Closed',1200,90),now).status,'old_observation');
 assert(quoteFreshness(report('Closed',7200,3600),now).sessionNote.includes('لا يصف حالة السوق الآن'));
});
test('unknown source time and stale cache do not become fresh',()=>{
 const r=report();r.quote!.market_time=null;assert.equal(quoteFreshness(r,now).status,'unknown');
 r.quote!.observation!.cache_state='stale';assert.equal(quoteFreshness(r,now).status,'stale_cache');
 assert.equal(quoteFreshness(report('Closed',900),now).status,'within_display_window');
 assert(quoteFreshness(report('Closed',900),now).message.includes('لا يثبت أنه مباشر'));
});
test('unverified and old observations cannot gain a provider-backed state by parsing',()=>{
 const r=report('Open');r.quote!.provider='binance';r.quote!.observation!.market_state_basis='UNVERIFIED';
 assert.equal(quoteFreshness(r,now).session,'unknown');
 r.quote!.observation!.market_state_basis='provider';assert.equal(terminalResearch(r,'AAPL',now),null);
 const old=report();delete old.quote!.observation;delete old.quote!.market_state;
 assert(terminalResearch(old,'AAPL',now));assert.equal(quoteFreshness(old,now).session,'unknown');
});
test('future quote fetch and market timestamps cannot hide behind correct receipt identity',()=>{
 const r=report();r.quote!.observation!.fetched_at=new Date(now+1000).toISOString();assert.equal(terminalResearch(r,'AAPL',now),null);
 const other=report();other.quote!.market_time=stamp;assert.equal(terminalResearch(other,'AAPL',now),null);
});
