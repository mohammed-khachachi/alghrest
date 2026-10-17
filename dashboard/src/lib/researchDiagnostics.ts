import {z} from 'zod';
import {stamp, TERMINAL_SYMBOL_PATTERN} from './terminalBridge';
const provider = z.enum(['nasdaq','yahoo','yahoo-chart','stooq','binance','fred','yahoo-rss','google-rss']);
const clock = z.object({value:z.string().min(1).max(160),basis:z.enum(['provider_text_unconverted','ticker_window_close','daily_close_date'])}).strict();
const observation = z.object({symbol:z.string().regex(TERMINAL_SYMBOL_PATTERN),feed:z.enum(['quotes','history','news']),provider,
  state:z.enum(['available','unavailable']),last_attempt:stamp,last_success:stamp.nullable(),last_failure:stamp.nullable(),
  failure:z.enum(['timeout','upstream_http','empty_response','provider_error']).nullable(),http_status:z.number().int().min(400).max(599).nullable(),clock:clock.nullable()}).strict();
const result = z.object({symbol:z.string(),checked_at:stamp,state:z.enum(['available','unavailable','invalid']),
  diagnostics:z.object({schema_version:z.literal('research-diagnostics-v1'),symbol:z.string(),assessed_at:stamp,
    started_at:stamp,scope:z.literal('process_memory'),observations:z.array(observation).max(14)}).strict().nullable()}).strict();
export type DiagnosticResult = z.infer<typeof result>;
export function researchDiagnostics(value:unknown,symbol:string,now=Date.now()):DiagnosticResult {
  const r=result.parse(value), d=r.diagnostics;
  if(r.symbol!==symbol || Date.parse(r.checked_at)>now+5000 || now-Date.parse(r.checked_at)>=90000
    || (r.state==='available')!==!!d) throw new Error('استجابة تشخيص غير صالحة أو قديمة.');
  if(d && (d.symbol!==symbol || Date.parse(d.assessed_at)>Date.parse(r.checked_at)
    || Date.parse(d.started_at)>Date.parse(d.assessed_at)
    || new Set(d.observations.map(o=>`${o.feed}:${o.provider}`)).size!==d.observations.length
    || d.observations.some(o=>o.symbol!==symbol
      || [o.last_attempt,o.last_success,o.last_failure].some(t=>t!==null&&(Date.parse(t)<Date.parse(d.started_at)||Date.parse(t)>Date.parse(d.assessed_at)))
      || (o.feed==='news')!==['yahoo-rss','google-rss'].includes(o.provider)
      || (o.failure===null)!==(o.last_failure===null) || (o.failure==='upstream_http')!==(o.http_status!==null)
      || (o.state==='available' ? !o.last_success||Date.parse(o.last_success)<Date.parse(o.last_attempt) : !o.last_failure||Date.parse(o.last_failure)<Date.parse(o.last_attempt))
      || (o.clock && (o.feed!=='quotes'||o.clock.basis!==({nasdaq:'provider_text_unconverted',binance:'ticker_window_close',fred:'daily_close_date'} as Record<string,string>)[o.provider])))))
    throw new Error('هوية المصدر أو أوقات التشخيص غير متسقة.');
  return r;
}
export const diagnosticFailure = {timeout:'انتهت مهلة المزوّد',upstream_http:'رفض المزوّد الطلب',empty_response:'استجابة بلا بيانات صالحة',provider_error:'تعذر قراءة استجابة المزوّد'};
export const diagnosticClock = {provider_text_unconverted:'توقيت المزوّد كما ورد؛ لم يتحول إلى UTC',ticker_window_close:'نهاية نافذة إحصاء السعر؛ ليست وقت آخر صفقة',daily_close_date:'تاريخ الإغلاق اليومي؛ ليس توقيت سعر مباشر'};
