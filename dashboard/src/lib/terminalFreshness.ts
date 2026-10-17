import type { TerminalResearch } from './terminalResearch';

const states: Record<string,string> = {REGULAR:'open',OPEN:'open',CLOSED:'closed',PRE:'pre','PRE-MARKET':'pre','PRE MARKET':'pre',POST:'post','AFTER-HOURS':'post','AFTER HOURS':'post'};
const names: Record<string,string> = {open:'مفتوحة',closed:'مغلقة',pre:'قبل الافتتاح',post:'بعد الإغلاق',unknown:'غير معلومة'};

/** Display thresholds only; provider declarations are dated observations, not calendars. */
export function quoteFreshness(report: TerminalResearch, now = Date.parse(report.assessed_at)) {
  const q=report.quote;
  if(!q) return {status:'unavailable',session:'unknown',message:'السعر غير متاح.',sessionNote:''};
  const o=q.observation;
  const reported=o?.market_state_basis==='provider';
  const session=reported ? states[(q.market_state??'').trim().toUpperCase()]??'unknown' : 'unknown';
  const currentState=!!o && now-Date.parse(o.fetched_at)>=0 && now-Date.parse(o.fetched_at)<90000 && o.cache_state!=='stale';
  let status: string, message: string;
  if(o?.cache_state==='stale') {status='stale_cache';message='فشل تحديث السعر؛ هذه نسخة سابقة بوقت جلبها الأصلي.';}
  else if(!q.market_time) {status='unknown';message='وقت السعر غير معلن؛ لا نثبت حداثته من وقت الجلب.';}
  else if(now-Date.parse(q.market_time)<=900000) {status='within_display_window';message='وقت السعر ضمن حد العرض البالغ 15 دقيقة؛ لا يثبت أنه مباشر.';}
  else if(session==='closed' && currentState) {status='closed_reported';message='وقت السعر قديم والمصدر أعلن إغلاق السوق عند الجلب؛ هذا لا يثبت تأخر المزوّد.';}
  else if(session==='open' && currentState) {status='old_while_open_reported';message='وقت السعر أقدم من 15 دقيقة والمصدر أعلن جلسة مفتوحة عند الجلب؛ يحتاج مراجعة.';}
  else {status='old_observation';message='وقت السعر أقدم من 15 دقيقة؛ سبب العمر غير متحقق.';}
  let sessionNote=reported ? `الحالة المعلنة عند الجلب: ${names[session]}.` : 'حالة جلسة المصدر غير متحققة؛ لا نعتمد افتراض المحوّل بأن السوق مفتوح.';
  if(reported && !currentState) sessionNote+=' إعلان الحالة قديم أو من نسخة تعثر تحديثها؛ لا يصف حالة السوق الآن.';
  return {status,session,message,sessionNote};
}
