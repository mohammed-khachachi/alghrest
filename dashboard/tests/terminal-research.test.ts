import test from 'node:test';
import assert from 'node:assert/strict';
import { selectTerminalSymbol, terminalMessage, terminalSymbol } from '../src/lib/terminalBridge';
import { terminalResearch } from '../src/lib/terminalResearch';
const now = Date.parse('2026-10-15T12:00:00Z');
const stamp = new Date(now).toISOString();
function report() {
  return {
    schema_version: 'openterminal-research-v1', symbol: 'AAPL', requested_range: '6M', assessed_at: stamp,
    quote: {symbol:'AAPL',name:'Fixture',price:'100.10',change_percent:'0.5',currency:'USD',provider:'nasdaq',market_time:null},
    analysis: {count:60,first_time:'2026-08-15T12:00:00Z',last_time:'2026-10-14T12:00:00Z',last_close:'60',
      sma20:'50.5',sma50:'35.5',rsi14_simple:'100',atr14_simple:'2',recent20_low:'40',recent20_high:'61',
      trend:'above_averages',history_provider:'UNKNOWN',interval:'UNVERIFIED'},
    headlines: [],sources:['quotes','news','history'].map(kind=>({kind,state:'available',received_at:stamp,response_sha256:'a'.repeat(64),reasons:[]})),
    freshness:'UNKNOWN',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false,
  };
}
test('actual terminal symbols synchronize without mapping to futures',()=>{
  for (const symbol of ['AAPL','QQQ','BTC-USD','0700.HK','^VIX','M&M.NS','GC=F']) {
    assert.deepEqual(selectTerminalSymbol(symbol),{type:'alghrest:select-symbol',symbol});
    assert(terminalMessage('http://127.0.0.1:3001',{type:'openterminal:symbol',symbol}));
  }
  assert.equal(terminalSymbol(' aapl '),'AAPL');
});
test('symbols cannot become URLs, multi-symbol requests or traversal',()=>{
  for (const symbol of ['..','https://example.org','AAPL,SPY','../AAPL','A'.repeat(21)]) assert.equal(selectTerminalSymbol(symbol),null);
});
test('research requires the selected actual symbol and its three identified source results',()=>{
  assert(terminalResearch(report(),'AAPL',now));
  assert.equal(terminalResearch(report(),'MES',now),null);
  assert.equal(terminalResearch({...report(),quote:{...report().quote,symbol:'SPY'}},'AAPL',now),null);
  assert.equal(terminalResearch({...report(),sources:[report().sources[0],report().sources[0],report().sources[2]]},'AAPL',now),null);
});
test('stale, future or unauthorized research flags are rejected',()=>{
  assert.equal(terminalResearch(report(),'AAPL',now+90000),null);
  assert.equal(terminalResearch({...report(),assessed_at:new Date(now+10000).toISOString()},'AAPL',now),null);
  for (const key of ['trade_permitted','execution_enabled']) assert.equal(terminalResearch({...report(),[key]:true},'AAPL',now),null);
});
test('partial feeds can show quote and news without invented indicators',()=>{
  const partial={...report(),analysis:null,sources:report().sources.map(s=>s.kind==='history'?{...s,state:'unavailable',response_sha256:null}:s)};
  assert(terminalResearch(partial,'AAPL',now));
  assert.equal(terminalResearch({...partial,analysis:report().analysis},'AAPL',now),null);
});
test('quote currency and provider are preserved, without asserting a history provider',()=>{
  assert(terminalResearch({...report(),quote:{...report().quote,currency:'HKD',provider:'yahoo-chart'}},'AAPL',now));
  assert(terminalResearch({...report(),quote:{...report().quote,currency:'GBp',provider:'yahoo'}},'AAPL',now));
  assert.equal(terminalResearch({...report(),analysis:{...report().analysis,history_provider:'nasdaq'}},'AAPL',now),null);
});
test('invalid numbers and inadequate sample sizes are rejected',()=>{
  for (const price of ['NaN','0','-1','1e1000']) assert.equal(terminalResearch({...report(),quote:{...report().quote,price}},'AAPL',now),null);
  assert.equal(terminalResearch({...report(),analysis:{...report().analysis,count:10}},'AAPL',now),null);
  assert.equal(terminalResearch({...report(),analysis:{...report().analysis,rsi14_simple:'101'}},'AAPL',now),null);
});
