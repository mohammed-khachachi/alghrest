import { z } from 'zod';
import { buildObservation, datedMicro, integerQuantity, type Snapshot } from './userPolicy';

export const policyId = 'tcp25-mes-mnq-ten-micro-v1' as const;
const revision = z.string().regex(/^[a-f0-9]{64}$/);
const instant = z.string().datetime({ offset: true });
const money = z.string().regex(/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/);
const nonnegative = z.string().regex(/^\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/);
const safety = {
  firm_compliance: z.literal('NOT_ASSESSED'), firm_eligibility: z.literal('BLOCKED'),
  qualified_contracts: z.literal(0), firm_reasons: z.array(z.string()).min(1),
  passing_probability: z.literal('UNKNOWN'), trade_permitted: z.literal(false), execution_enabled: z.literal(false),
};
const profileSchema = z.object({ id: z.string(), program: z.string(), phase: z.string(),
  starting_balance: money, profit_target: money, daily_loss_limit: money, maximum_drawdown: money,
  minimum_trading_days: z.number().int(), consistency_percent: z.number(), source: z.string(), verified_on: z.string(),
}).passthrough();
const accountSchema = z.object({
  source:z.enum(['manual_report','replay','read_only_report']),source_reference:z.string(),cash_balance:money,unrealized_pnl:money,equity:money,
  account_id: z.string(), currency: z.string(), observed_at: instant, human_confirmed: z.boolean(), costs_included: z.boolean(),
  positions: z.array(z.object({ position_id:z.string(), side:z.enum(['BUY','SELL']),unrealized_pnl:money,instrument_id: z.string(), contract: z.string(), contracts: z.number().int().positive().safe() }).passthrough()).nullable(),
  working_orders: z.array(z.object({order_id:z.string(),instrument_id:z.string(),contract:z.string(),side:z.enum(['BUY','SELL']),contracts:z.number().int().positive().safe()}).passthrough()).nullable(),
}).passthrough();
const accountState = z.object({ health: z.enum(['KNOWN', 'UNKNOWN', 'INVALID']), reasons: z.array(z.string()), observation: accountSchema.nullable() });
const statusSchema = z.object({ ...safety, profile: profileSchema,
  sessions: z.array(z.object({ session_date: z.string(), as_of: instant, closed: z.boolean(), traded: z.boolean(), net_pnl: money, lowest_pnl: money, notes: z.string(), account: accountSchema.nullable().optional() }).passthrough()),
  account_revision: revision, personal_terms_match: z.boolean(), read_only_legacy: z.boolean(), personal_targets_met: z.boolean(),
  balance: money, total_pnl: money, minimum_balance: money, drawdown_remaining: nonnegative, daily_loss_remaining: nonnegative,
  best_day: money, trading_days: z.number(), profit_remaining: money, consistency_met: z.boolean(), consistency_total_required: money,
  breaches: z.array(z.string()), fresh_observation: z.boolean(), rules_current: z.boolean(), recorded_targets_met: z.boolean(), note: z.string(),
  account_state: accountState, clock: z.object({session_date:z.string(), chicago_time:z.string(), regular_hours_closed:z.boolean(), note:z.string()}).passthrough(),
}).passthrough();
const envelope = z.object({ schema_version: z.literal(2), policy_id: z.literal(policyId), policy_revision: revision,
  algorithm_version: z.enum(['tcp25-personal-rules-v1','tcp25-personal-status-v1','tcp25-personal-micro-cap-v1','tcp25-personal-plan-v1']),
  generated_at: instant, profile: profileSchema.nullable(), sessions:z.array(z.record(z.unknown())), request:z.record(z.unknown()).nullable(),
  source_hashes:z.record(revision), result:z.record(z.unknown()),
}).strict();
type Envelope = z.infer<typeof envelope>;
const sourceNames = ['tcp25_personal.py','user_policy.py','user_risk.py','account.py','evaluation.py','analysis.py','models.py','policy.py'].map(n=>'src/core/advisory/'+n).sort();
export type TCP25Snapshot = Snapshot & { account_revision:string; policy_revision?:string; schema_version?:number; personal_terms_match?:boolean; read_only_legacy?:boolean };
function stable(v:unknown):string { return JSON.stringify(v, (_key,row:unknown)=>row && typeof row==='object' && !Array.isArray(row) ? Object.fromEntries(Object.entries(row).sort(([a],[b])=>a.localeCompare(b))) : row); }
function checked(raw:unknown, algorithm:Envelope['algorithm_version']):Envelope {
  const e=envelope.parse(raw);
  if(e.algorithm_version!==algorithm || stable(Object.keys(e.source_hashes).sort())!==stable(sourceNames)) throw new Error('TCP25 evidence identity mismatch');
  return e;
}
export function validateTCP25Status(raw:unknown) {
  const e=checked(raw,'tcp25-personal-status-v1'); const value=statusSchema.parse(e.result);
  if(stable(e.profile)!==stable(value.profile)||stable(e.sessions)!==stable(value.sessions)||e.request!==null||value.read_only_legacy===value.personal_terms_match) throw new Error('TCP25 snapshot mismatch');
  return {...value,schema_version:2 as const,policy_revision:e.policy_revision};
}
export function creationPayload(form:Record<string,string>) {
  return profileSchema.parse({id:form.id,program:form.program,phase:'evaluation_eod',starting_balance:form.starting_balance,
    profit_target:form.profit_target,daily_loss_limit:form.daily_loss_limit,maximum_drawdown:form.maximum_drawdown,
    minimum_trading_days:Number(form.minimum_trading_days),consistency_percent:30,source:form.source,verified_on:form.verified_on});
}
function identity(snapshot:TCP25Snapshot) {
  if(snapshot.schema_version!==2||!snapshot.personal_terms_match||snapshot.read_only_legacy||!snapshot.policy_revision) throw new Error('اختر سجل TCP25 متوافقًا؛ السجل القديم للقراءة فقط.');
  return {schema_version:2 as const,policy_id:policyId,expected_policy_revision:revision.parse(snapshot.policy_revision),expected_account_revision:revision.parse(snapshot.account_revision)};
}
export function personalRequest(root:string,contract:string,count:string,snapshot:TCP25Snapshot) {
  if(!datedMicro(root,contract)) throw new Error('Dated MES/MNQ required');
  return {...identity(snapshot),instrument_id:root as 'MES'|'MNQ',contract,additional_contracts:integerQuantity(count,10)};
}
const requestSchema=z.object({schema_version:z.literal(2),policy_id:z.literal(policyId),expected_policy_revision:revision,expected_account_revision:revision,
  instrument_id:z.enum(['MES','MNQ']),contract:z.string(),entry:nonnegative,stop:nonnegative,risk_percent:nonnegative,
  fees_per_unit:nonnegative,slippage_points:nonnegative,safety_buffer:nonnegative,cost_source:z.enum(['user_declared','synthetic']),cost_reference:z.string().trim().min(1).max(500),costs_reviewed:z.literal(true),
}).strict().refine(v=>datedMicro(v.instrument_id,v.contract)&&Number(v.entry)>0&&Number(v.stop)>0&&Number(v.risk_percent)>0&&Number(v.risk_percent)<=1&&Number(v.safety_buffer)>0);
export type TCP25PlanRequest=z.infer<typeof requestSchema>;
export function personalRiskRequest(raw:unknown,snapshot:TCP25Snapshot):TCP25PlanRequest { return requestSchema.parse({...raw as Record<string,unknown>,...identity(snapshot)}); }
const common={...safety,account_id:z.string(),account_revision:revision,journal_equity_usd:money,account_state:accountState,maximum_micro_contracts:z.literal(10),expires_at:instant,reasons:z.array(z.string())};
const capSchema=z.object({...common,state:z.enum(['WITHIN_CAP','BLOCKED','UNKNOWN']),gross_micro_contracts:z.number().int().nonnegative().safe().nullable(),remaining_micro_contracts:z.number().int().min(0).max(10).nullable()}).strict();
const planSchema=z.object({...common,state:z.enum(['CALCULATED','BLOCKED','UNKNOWN']),risk_budget:nonnegative,loss_per_unit:nonnegative,personal_contracts:z.number().int().min(0).max(10),estimated_loss_at_stop:nonnegative,daily_loss_remaining:nonnegative,drawdown_remaining:nonnegative,minimum_balance:money,consistency_met:z.boolean(),personal_targets_met:z.boolean()}).strict();
type CurrentResult={generated_at:string;expires_at:string};
export function personalRiskCurrent(value:CurrentResult,now:number):boolean {
  return Number.isFinite(now)&&Date.parse(value.generated_at)<=now&&now<Date.parse(value.expires_at)&&now<Date.parse(value.generated_at)+1800000&&new Date(now).getUTCHours()>=7&&new Date(now).getUTCHours()<14;
}
function join(e:Envelope,snapshot:TCP25Snapshot,request:unknown) {
  identity(snapshot);
  if(e.policy_revision!==snapshot.policy_revision||stable(e.profile)!==stable(snapshot.profile)||stable(e.sessions)!==stable(snapshot.sessions)) throw new Error('TCP25 snapshot changed');
  // Compare numeric request spellings by exact decimal coefficient/exponent, never floating point.
  const normalize=(v:unknown):unknown=>{
    if(!v||typeof v!=='object'||Array.isArray(v)) return v;
    return Object.fromEntries(Object.entries(v).map(([k,x])=>{
      if(!['entry','stop','risk_percent','fees_per_unit','slippage_points','safety_buffer'].includes(k)||typeof x!=='string') return [k,x];
      const [m,ex='0']=x.toLowerCase().split('e'),[w,f='']=m.split('.');const n=w+f;const sig=n.replace(/^0+/,'').replace(/0+$/,'');
      return [k,sig?`${sig}e${BigInt(ex)-BigInt(f.length)+BigInt(n.length-n.replace(/0+$/,'').length)}`:'0'];
    }));
  };
  if(stable(normalize(e.request))!==stable(normalize(request))) throw new Error('TCP25 request changed');
}
function freshAccount(e:Envelope,result:z.infer<typeof capSchema>|z.infer<typeof planSchema>,snapshot:TCP25Snapshot,now:number,flat:boolean) {
  const a=result.account_state.observation,last=snapshot.sessions.at(-1);
  if(!personalRiskCurrent({generated_at:e.generated_at,expires_at:result.expires_at},now)||!a||!last||last.closed||!a.human_confirmed||!a.costs_included||a.currency!=='USD'||a.account_id!==snapshot.profile.id||result.account_id!==snapshot.profile.id||result.account_revision!==snapshot.account_revision||result.account_state.health!=='KNOWN'||result.account_state.reasons.length||!a.positions||!a.working_orders||a.working_orders.length||stable(a)!==stable(last.account)||Date.parse(a.observed_at)!==Date.parse(last.as_of)||Date.parse(a.observed_at)>Date.parse(e.generated_at)||now>=Date.parse(a.observed_at)+1800000||Date.parse(result.expires_at)>Date.parse(a.observed_at)+1800000||result.reasons.length||a.positions.some(p=>!datedMicro(p.instrument_id,p.contract))||(flat&&a.positions.length)) throw new Error('TCP25 account is incomplete or stale');
  return a.positions.reduce((sum,p)=>sum+p.contracts,0);
}
export function validateUserResult(raw:unknown,snapshot:TCP25Snapshot,request:ReturnType<typeof personalRequest>,now:number) {
  const e=checked(raw,'tcp25-personal-micro-cap-v1');join(e,snapshot,request);const result=capSchema.parse(e.result);
  if(result.state==='WITHIN_CAP') {
    const gross=freshAccount(e,result,snapshot,now,false);
    if(!Number.isSafeInteger(gross)||gross>10||result.gross_micro_contracts!==gross||result.remaining_micro_contracts!==10-gross||gross+request.additional_contracts>10) throw new Error('TCP25 capacity mismatch');
  } else if(!result.reasons.length||result.remaining_micro_contracts!==(result.state==='BLOCKED'?0:null)) throw new Error('Unsafe TCP25 capacity');
  return {...result,generated_at:e.generated_at};
}
export type TCP25Capacity=ReturnType<typeof validateUserResult>;
export type TCP25Plan=z.infer<typeof planSchema>&{generated_at:string;request:TCP25PlanRequest};
export function validatePersonalRisk(raw:unknown,snapshot:TCP25Snapshot,request:TCP25PlanRequest,now:number):TCP25Plan {
  const e=checked(raw,'tcp25-personal-plan-v1');join(e,snapshot,request);const result=planSchema.parse(e.result);
  if(result.state==='CALCULATED') freshAccount(e,result,snapshot,now,true);
  else if(!result.reasons.length||result.personal_contracts!==0||Number(result.estimated_loss_at_stop)!==0) throw new Error('Unsafe TCP25 sizing');
  return {...result,generated_at:e.generated_at,request:requestSchema.parse(e.request)};
}
export {buildObservation};
export {requestGate} from './userPolicy';
export const resultCurrent=personalRiskCurrent;
