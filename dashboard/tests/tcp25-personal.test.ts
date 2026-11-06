import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { creationPayload, personalRequest, personalRiskRequest, personalRiskCurrent, validateTCP25Status, validateUserResult, validatePersonalRisk } from '../src/lib/tcp25Personal';

const directory = resolve('artifacts/earn2trade-tcp25-readiness/personal-worksheet-v2');
const read = (name: string) => JSON.parse(readFileSync(resolve(directory, name), 'utf8'));
const statusEvidence = read('synthetic-tcp25-status-v2.json');
const capEvidence = read('synthetic-tcp25-cap-v2.json');
const planEvidence = read('synthetic-tcp25-plan-v2.json');
const now = Date.parse(statusEvidence.generated_at);
const snapshot = () => validateTCP25Status(structuredClone(statusEvidence));

test('real serialized backend schema-2 fixtures display personal arithmetic with firm qualification blocked', () => {
  const s = snapshot();
  const capacity = validateUserResult(capEvidence, s, capEvidence.request, now);
  const plan = validatePersonalRisk(planEvidence, s, planEvidence.request, now);
  assert.equal(s.profile.starting_balance, '25000');
  assert.equal(s.profile.profit_target, '1750');
  assert.equal(s.profile.daily_loss_limit, '550');
  assert.equal(s.profile.maximum_drawdown, '1500');
  assert.equal(capacity.remaining_micro_contracts, 10);
  assert.equal(plan.personal_contracts, 2);
  assert.equal(plan.risk_budget, '125.0');
  assert.equal(plan.loss_per_unit, '53.25');
  assert.equal(plan.qualified_contracts, 0);
  assert.equal(plan.firm_eligibility, 'BLOCKED');
  assert.equal(plan.passing_probability, 'UNKNOWN');
  assert.equal(plan.trade_permitted, false);
  assert.equal(plan.execution_enabled, false);
});

test('creation uses the canonical minimum_trading_days field and explicit TCP25 terms', () => {
  const form = {id:'new-tcp25',program:'trader_career_path',starting_balance:'25000',profit_target:'1750',daily_loss_limit:'550',maximum_drawdown:'1500',minimum_trading_days:'0',source:'https://example.test/rules',verified_on:'2026-10-08'};
  const payload = creationPayload(form);
  assert.equal(payload.minimum_trading_days, 0);
  assert.equal(payload.phase, 'evaluation_eod');
  assert.equal('minimumtrading_days' in payload, false);
  assert.throws(() => creationPayload({...form,minimum_trading_days:undefined!}));
});

test('ten-Micro request cannot fall back to legacy, Mini, unsupported or oversized input', () => {
  const s = snapshot();
  assert.equal(personalRequest('MNQ','MNQZ26','10',s).schema_version,2);
  for(const [root,contract,count] of [['MES','MESZ26','11'],['ES','ESZ26','1'],['MES','MES1!','1'],['MES','MNQZ26','1']])
    assert.throws(()=>personalRequest(root,contract,count,s));
  for(const changes of [{schema_version:1},{read_only_legacy:true},{personal_terms_match:false},{policy_revision:undefined}])
    assert.throws(()=>personalRequest('MES','MESZ26','1',{...s,...changes}));
});

for (const key of ['schema_version','algorithm_version','policy_id','policy_revision','source_hashes']) test(`reject foreign envelope identity: ${key}`,()=>{
  const bad=structuredClone(planEvidence);
  bad[key]=key==='schema_version'?1:key==='source_hashes'?{}:'legacy';
  assert.throws(()=>validatePersonalRisk(bad,snapshot(),planEvidence.request,now));
});

for (const [key,value] of [['trade_permitted',true],['execution_enabled',true],['passing_probability','80%'],['firm_eligibility','READY'],['qualified_contracts',1],['maximum_micro_contracts',20],['personal_contracts',11]])
  test(`reject unsafe response field ${key}`,()=>{
    const bad=structuredClone(planEvidence);bad.result[key]=value;
    assert.throws(()=>validatePersonalRisk(bad,snapshot(),planEvidence.request,now));
  });

test('account, policy and request revisions bind results to the current snapshot',()=>{
  const s=snapshot();
  assert.throws(()=>validatePersonalRisk(planEvidence,{...s,account_revision:'0'.repeat(64)},planEvidence.request,now));
  assert.throws(()=>validatePersonalRisk(planEvidence,{...s,policy_revision:'0'.repeat(64)},planEvidence.request,now));
  assert.throws(()=>validatePersonalRisk(planEvidence,s,{...planEvidence.request,entry:'5001'},now));
  assert.equal(validatePersonalRisk(planEvidence,s,{...planEvidence.request,entry:'5e3'},now).personal_contracts,2);
  assert.throws(()=>personalRiskRequest({...planEvidence.request,costs_reviewed:false},s));
  assert.throws(()=>personalRiskRequest({...planEvidence.request,cost_reference:''},s));
});

test('expiry, future generation, unknown coverage, working orders and Mini exposure cannot display positive capacity',()=>{
  const s=snapshot();
  for(const instant of [now-1,now+1800000,Date.parse('2026-10-08T14:00:00Z')]) {
    assert.throws(()=>validateUserResult(capEvidence,s,capEvidence.request,instant));
    assert.equal(personalRiskCurrent({generated_at:planEvidence.generated_at,expires_at:planEvidence.result.expires_at},instant),false);
  }
  for(const change of [a=>{a.positions=null;},a=>{a.working_orders=null;},a=>{a.working_orders=[{order_id:'working',instrument_id:'MES',contract:'MESZ26',side:'SELL',contracts:1}];},a=>{a.positions=[{position_id:'mini',instrument_id:'ES',contract:'ESZ26',side:'BUY',contracts:1,unrealized_pnl:'0'}];} ] as ((a: any)=>void)[]) {
    const bad=structuredClone(capEvidence);const current=snapshot();
    change(bad.result.account_state.observation);current.sessions.at(-1)!.account=bad.result.account_state.observation;
    bad.sessions=current.sessions;
    assert.throws(()=>validateUserResult(bad,current,capEvidence.request,now));
  }
});

test('backend blocked evidence is visible without inventing capacity',()=>{
  const raw=read('synthetic-tcp25-blocked-v2.json');
  const current=validateTCP25Status(raw.status);
  const result=validateUserResult(raw.capacity,current,raw.capacity.request,now);
  assert.equal(result.state,'BLOCKED');
  assert.equal(result.remaining_micro_contracts,0);
  assert(result.reasons.includes('mini_mixed_or_unsupported_exposure'));
});

test('personal UI targets only versioned routes and retains historical briefing reads',()=>{
  const source=(name:string)=>readFileSync(resolve('dashboard/src',name),'utf8');
  const worksheet=source('components/advisory/EvaluationPanel.tsx');
  const capacity=source('components/advisory/UserPolicyPanel.tsx');
  const page=source('pages/ManualAssistant.tsx');
  assert.match(worksheet,/tcp25\/personal\/evaluations/);
  assert.doesNotMatch(worksheet,/minimumtrading_days/);
  assert.match(worksheet,/read_only_legacy/);
  assert.match(capacity,/tcp25\/personal\/evaluations/);
  assert.doesNotMatch(capacity,/user-policy-check/);
  assert.match(page,/tcp25\/personal\/evaluations/);
  assert.doesNotMatch(page,/\/personal-plan/);
  assert.match(page,/<BriefingPanel evaluation=\{null\}/);
  assert.match(source('components/advisory/BriefingPanel.tsx'),/api<unknown>\('briefings'\)/);
});

for (const age of [1799, 1800, 1801]) test(`frontend expiry boundary at ${age} seconds cannot display expired positive capacity`, () => {
  const generated = now + age * 1000;
  const cap = structuredClone(capEvidence);
  const plan = structuredClone(planEvidence);
  cap.generated_at = plan.generated_at = new Date(generated).toISOString();
  const current = { generated_at:cap.generated_at, expires_at:cap.result.expires_at };
  assert.equal(personalRiskCurrent(current, generated), age < 1800);
  if (age < 1800) {
    assert.equal(validateUserResult(cap, snapshot(), cap.request, generated).state, 'WITHIN_CAP');
    assert.equal(validatePersonalRisk(plan, snapshot(), plan.request, generated).state, 'CALCULATED');
  } else {
    assert.throws(() => validateUserResult(cap, snapshot(), cap.request, generated));
    assert.throws(() => validatePersonalRisk(plan, snapshot(), plan.request, generated));
  }
});

test('fractional and timezone timestamps preserve the exclusive display deadline', () => {
  const generated_at = '2026-10-08T15:59:59.123456+05:30';
  const expires_at = '2026-10-08T04:30:00.123456-06:00';
  const deadline = Date.parse(expires_at);
  assert.equal(personalRiskCurrent({generated_at, expires_at}, deadline - 1), true);
  assert.equal(personalRiskCurrent({generated_at, expires_at}, deadline), false);
  assert.equal(personalRiskCurrent({generated_at, expires_at}, deadline + 1), false);
  // Date.parse has millisecond resolution: a sub-ms interval may be discarded,
  // never widened into a usable interval after the true deadline.
  assert.equal(personalRiskCurrent({generated_at:'2026-10-08T10:30:00.123455Z', expires_at:'2026-10-08T10:30:00.123456Z'}, deadline), false);
  assert.equal(personalRiskCurrent({generated_at, expires_at:generated_at}, Date.parse(generated_at)), false);
  assert.equal(personalRiskCurrent({generated_at, expires_at:'invalid'}, deadline - 1), false);
});

test('post-fix backend envelopes agree with frontend boundary classifications', () => {
  const evidence = JSON.parse(readFileSync(resolve('artifacts/earn2trade-tcp25-readiness/capacity-expiry-boundary-v1/boundary-cases.json'), 'utf8'));
  for (const row of evidence.cases) {
    const s = validateTCP25Status(row.status);
    const generated = Date.parse(row.capacity.generated_at);
    const cap = validateUserResult(row.capacity, s, row.capacity.request, generated);
    const plan = validatePersonalRisk(row.plan, s, row.plan.request, generated);
    assert.equal(cap.state, row.age_seconds < 1800 ? 'WITHIN_CAP' : 'UNKNOWN');
    assert.equal(plan.state, row.age_seconds < 1800 ? 'CALCULATED' : 'UNKNOWN');
    assert.equal(plan.qualified_contracts, 0);
    assert.equal(cap.firm_eligibility, 'BLOCKED');
    if (row.age_seconds >= 1800) {
      assert.equal(cap.remaining_micro_contracts, null);
      assert.equal(plan.personal_contracts, 0);
    }
  }
});
