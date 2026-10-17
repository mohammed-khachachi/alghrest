import { z } from 'zod';
import { observationView } from './observations';
import { newsContext } from './newsEvents';

const id = z.string().regex(/^[a-zA-Z0-9_-]{1,64}$/), hash = z.string().regex(/^[a-f0-9]{64}$/), time = z.string().datetime({offset:true});
export const briefingRequestSchema = z.object({observation_id:id, observation_revision:hash, evaluation_id:id, account_revision:hash}).strict();
export type BriefingRequest = z.infer<typeof briefingRequestSchema>;
const schema = z.object({
  record:z.object({schema_version:z.literal('evaluation-briefing-v1'),id:z.string().regex(/^[a-f0-9]{32}$/),
    inputs:z.object({assessed_at:time,observation:z.unknown(),profile:z.object({id}).passthrough(),sessions:z.array(z.unknown()).max(2000),context:z.unknown(),interests:z.array(z.string()).max(50),agent_tap_enabled:z.boolean(),agent_records:z.array(z.record(z.string())).max(20)}).strict(),
    source_hashes:z.record(hash),result:z.object({state:z.enum(['REVIEWABLE','INCOMPLETE']),decision:z.enum(['WAIT','NO_TRADE']),reasons:z.array(z.string()),observation_warnings:z.array(z.string()),frame_comparison:z.enum(['SAME_TIME_SAME_LAST','SAME_TIME_CONFLICT','NOT_COMPARABLE']),account_status:z.record(z.unknown()),
      cap:z.object({trade_permitted:z.literal(false),execution_enabled:z.literal(false)}).passthrough().nullable(),context:z.unknown(),capabilities:z.array(z.object({name:z.string(),state:z.enum(['AVAILABLE','PARTIAL','MISSING','DISABLED']),reasons:z.array(z.string()),evidence_ids:z.array(z.string())}).strict()),agent_context:z.array(z.record(z.string())).max(20),firm_compliance:z.literal('NOT_ASSESSED'),passing_probability:z.literal('UNKNOWN'),trade_permitted:z.literal(false),execution_enabled:z.literal(false)}).strict()}).strict(),
  reopened_at:time,current_warnings:z.array(z.string()),historical_context:z.literal(true),trade_permitted:z.literal(false),execution_enabled:z.literal(false),
}).strict();
export function briefingView(raw:unknown,expected?:BriefingRequest) {
  const value=schema.parse(raw),record=value.record;
  const observation=observationView(record.inputs.observation),root=observation.record.packet.instrument_id;
  const captured=newsContext(record.inputs.context,root),context=newsContext(record.result.context,root);
  if(Date.parse(record.inputs.assessed_at)>Date.parse(value.reopened_at)||Date.parse(captured.assessed_at)>Date.parse(record.inputs.assessed_at)||context.assessed_at!==record.inputs.assessed_at)throw new Error('توقيت التقرير غير متسق.');
  if(expected&&(expected.observation_id!==observation.record.id||expected.observation_revision!==observation.record.revision||expected.evaluation_id!==record.inputs.profile.id||expected.account_revision!==record.result.account_status.account_revision))throw new Error('التقرير لا يطابق النسخة والحساب المختارين.');
  return {...value,record:{...record,inputs:{...record.inputs,observation,context:captured},result:{...record.result,context}}};
}
export type BriefingView = ReturnType<typeof briefingView>;
export function briefingGate(){let revision=0;return {next:()=>++revision,current:(n:number)=>n===revision};}
export const capabilityLabel:Record<string,string>={observations:'الملاحظات المراجعة',published_context:'الأخبار والأحداث',account_and_exposure:'الحساب والتعرض',strategy:'استراتيجية الفريمات',agent_news:'سياق وكيل الأخبار',agent_technical:'سياق التحليل الفني',agent_macro:'السياق الاقتصادي',agent_sentiment:'سياق المعنويات',agent_volatility:'سياق التقلب',execution:'تنفيذ الأوامر',defi:'DeFi',copy_trading:'نسخ التداول'};
export const capabilityState:Record<string,string>={AVAILABLE:'مدخل متاح للمراجعة',PARTIAL:'مساهمة جزئية معلنة',MISSING:'تحتاج مدخلات أو ربطًا',DISABLED:'غير مفعلة في هذا المسار'};
export function briefingAge(at:string,now:number){return now<Date.parse(at)?'توقيت غير متسق':now-Date.parse(at)>=300000?'تقرير محفوظ قديم؛ لا يصف الحالة الحالية':'سياق محفوظ عند إنشاء التقرير؛ راجع عمر كل مصدر';}

export function briefingReason(value:string):string {
 const labels:Record<string,string>={research_only:'تقرير للمراجعة فقط؛ لا توصية دخول مؤهلة',event_risk_unknown:'مخاطر الأحداث غير معلومة',strategy_not_integrated:'استراتيجية الفريمات لم تُدمج وتُختبر بعد',observation_not_current_and_reviewed:'النسخة غير مراجعة أو استُبدلت',dated_contract_missing:'العقد المؤرخ غير معلوم',same_time_price_conflict:'أسعار متعارضة في اللحظة نفسها',partial_or_unavailable_sources:'بعض المصادر قديمة أو متعذرة؛ التغطية جزئية',personal_terms_mismatch:'قواعد السجل لا تطابق القواعد الشخصية الحالية',account_evidence_incomplete:'ملاحظة الحساب قديمة أو غير مؤكدة أو ناقصة',invalid_agent_record:'مخرج وكيل غير سليم؛ لم يُستخدم',user_reported_not_independently_verified:'معلومات نقلها المستخدم؛ لم تُتحقق من السوق مستقلًا',not_a_candle_dataset:'الملاحظات ليست سلسلة شموع',incomplete_timeframes:'بعض الفريمات غير موجودة',historical_context_not_current:'السياق المحفوظ قديم؛ أعد جمع الأدلة',current_inputs_changed:'تغيرت الملاحظة أو الحساب منذ حفظ التقرير',tap_not_connected:'جسر الوكلاء غير موصول',no_current_related_context:'لا توجد مخرجات حديثة ذات صلة',reported_context_not_verified_signal:'سياق معلن؛ ليس إشارة متحققة',outside_advisory_workflow:'خارج مسار المساعد الاستشاري',coverage_partial:'التغطية جزئية',user_reported_account:'الحساب من سجلك المعلن',new_size_requires_flat_account_and_reviewed_costs:'الحجم الجديد يحتاج حسابًا خاليًا وتكاليف مراجعة',no_qualified_5m_15m_strategy_in_this_brief:'لا توجد استراتيجية مؤهلة لفريم5/15دقيقة في هذا التقرير',outside_user_entry_window:'خارج نافذة الدخول07:00–14:00UTC',missing_fresh_open_session:'لا توجد جلسة حساب مفتوحة حديثة',missing_account_observation:'ملاحظة الحساب غير موجودة',positions_unknown:'المراكز غير معلومة',working_orders_unknown:'الأوامر غير معلومة',account_costs_unknown:'رسوم الحساب غير مؤكدة',unconfirmed_account_observation:'ملاحظة الحساب لم تُؤكد',stale_or_future_account_observation:'وقت الحساب قديم أو غير سليم'};
 const [prefix,reason]=value.split(':');
 const frame:Record<string,string>={missing_captured_at:'وقت الالتقاط غير معلوم',missing_observed_at:'وقت السعر غير معلوم',missing_last_closed_bar_at:'آخر إغلاق غير معلوم',missing_last:'آخر سعر غير معلوم',stale_price:'السعر قديم',unknown_delay:'تأخير المصدر غير معلوم',delayed_delay:'المصدر متأخر'};
 return labels[value]??(frame[reason]?`${prefix}: ${frame[reason]}`:value.startsWith('recorded_breach:')?'تجاوز خسارة أو تراجع مسجل؛ راجع السجل':value);
}
