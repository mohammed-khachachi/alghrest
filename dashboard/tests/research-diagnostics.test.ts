import test from 'node:test';
import assert from 'node:assert/strict';
import {researchDiagnostics} from '../src/lib/researchDiagnostics';
const now=Date.parse('2026-10-16T12:00:00Z');
function payload(){return {symbol:'BTC',checked_at:'2026-10-16T12:00:00Z',state:'available',diagnostics:{schema_version:'research-diagnostics-v1',symbol:'BTC',assessed_at:'2026-10-16T12:00:00Z',started_at:'2026-10-16T08:00:00Z',scope:'process_memory',observations:[{symbol:'BTC',feed:'quotes',provider:'binance',state:'available',last_attempt:'2026-10-16T11:59:00Z',last_success:'2026-10-16T11:59:01Z',last_failure:null,failure:null,http_status:null,clock:{value:'2026-10-16T11:59:00Z',basis:'ticker_window_close'}}]}};}
test('accepts correctly labelled clock with original successful request time',()=>{assert.equal(researchDiagnostics(payload(),'BTC',now).diagnostics!.observations[0].clock!.basis,'ticker_window_close');});
test('identity, stale/future readings, unlabelled failures and forged clocks are rejected',()=>{
 const changes=[(p:any)=>p.symbol='ETH',(p:any)=>p.checked_at='2026-10-16T11:00:00Z',(p:any)=>p.checked_at='2099-01-01T00:00:00Z',(p:any)=>p.diagnostics.symbol='ETH',(p:any)=>p.diagnostics.observations.push({...p.diagnostics.observations[0]}),(p:any)=>p.diagnostics.observations[0].clock.basis='provider_text_unconverted',(p:any)=>p.diagnostics.observations[0].last_success=null,(p:any)=>p.diagnostics.observations[0].last_failure=p.checked_at,(p:any)=>p.diagnostics.observations[0].last_success='2099-01-01T00:00:00Z',(p:any)=>p.diagnostics.observations[0].failure='token=SECRET'];
 for(const change of changes){const p=payload();change(p);assert.throws(()=>researchDiagnostics(p,'BTC',now));}
});
test('unavailability remains explicit, while a recovered source retains its last failure',()=>{
 assert.equal(researchDiagnostics({symbol:'BTC',checked_at:payload().checked_at,state:'unavailable',diagnostics:null},'BTC',now).diagnostics,null);
 const p:any=payload();Object.assign(p.diagnostics.observations[0],{last_failure:'2026-10-16T11:00:00Z',failure:'timeout'});assert.equal(researchDiagnostics(p,'BTC',now).diagnostics!.observations[0].failure,'timeout');
});
