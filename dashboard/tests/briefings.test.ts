import test from 'node:test';
import assert from 'node:assert/strict';
import { briefingAge,briefingGate,briefingRequestSchema,briefingView } from '../src/lib/briefings';
import { observationTemplate } from '../src/lib/observations';
const at='2026-10-08T10:00:00Z',hash='a'.repeat(64),account='b'.repeat(64);
const request={observation_id:'obs1',observation_revision:hash,evaluation_id:'account1',account_revision:account};
function fixture(){
 const context={schema_version:'news-events-v1',instrument_id:'MES',assessed_at:at,headlines:[],events:[],sources:[],returned_date_start:null,returned_date_end:null,coverage:'partial',event_risk:'UNKNOWN',trade_permitted:false,execution_enabled:false};
 const observation={record:{id:'obs1',revision:hash,parent_revision:null,created_at:at,raw_json:'{}',packet:observationTemplate(),source_hashes:{'observations.py':hash}},latest_revision:hash,reviewed_at:at,assessed_at:at,warnings:[],origin:'user_reported',trade_permitted:false,execution_enabled:false};
 return {record:{schema_version:'evaluation-briefing-v1',id:'c'.repeat(32),inputs:{assessed_at:at,observation,profile:{id:'account1'},sessions:[],context,interests:[],agent_tap_enabled:false,agent_records:[]},source_hashes:{'briefing.py':hash},result:{state:'INCOMPLETE',decision:'WAIT',reasons:['research_only'],observation_warnings:[],frame_comparison:'NOT_COMPARABLE',account_status:{account_revision:account,balance:'50000'},cap:null,context,capabilities:[],agent_context:[],firm_compliance:'NOT_ASSESSED',passing_probability:'UNKNOWN',trade_permitted:false,execution_enabled:false}},reopened_at:at,current_warnings:[],historical_context:true,trade_permitted:false,execution_enabled:false};
}
test('joined response retains closed flags and explicit identities',()=>assert.equal(briefingView(fixture(),request).record.result.decision,'WAIT'));
for(const [key,value] of [['decision','BUY'],['decision','SELL'],['trade_permitted',true],['execution_enabled',true],['passing_probability','99%'],['firm_compliance','VERIFIED']])test(`reject forged result ${key}:${value}`,()=>{const raw=fixture();Object.assign(raw.record.result,{[key]:value});assert.throws(()=>briefingView(raw,request));});
for(const key of ['observation_id','observation_revision','evaluation_id','account_revision'])test(`late or mixed ${key} cannot match selection`,()=>assert.throws(()=>briefingView(fixture(),{...request,[key]:key.includes('revision')?'d'.repeat(64):'different'})));
test('future report or wrong context instrument rejected',()=>{const raw=fixture();raw.reopened_at='2026-10-08T09:59:59Z';assert.throws(()=>briefingView(raw));raw.reopened_at=at;raw.record.inputs.context.instrument_id='MNQ';assert.throws(()=>briefingView(raw));});
test('extra permission claims in request rejected',()=>assert.throws(()=>briefingRequestSchema.parse({...request,confirmed:true})));
test('input identity or unmount invalidates delayed success and error',()=>{const g=briefingGate(),old=g.next(),next=g.next();assert.equal(g.current(old),false);assert.equal(g.current(next),true);g.next();assert.equal(g.current(next),false);});
test('reopening does not renew historical source age',()=>{assert.match(briefingAge(at,Date.parse(at)+300000),/قديم/);assert.match(briefingAge(at,Date.parse(at)-1),/غير متسق/);});
