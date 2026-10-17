/** Deterministic descriptive rules. No I/O, timers, execution or trading recommendations. */
import type {TerminalResearch} from './terminalResearch';
import type {ResearchSnapshot} from './researchJournal';
import {summaryNumber} from './terminalSummary';
import {fixedIntervalSeconds} from './terminalQuality';

export type ResearchAlert = {id:string;kind:'trend'|'momentum'|'volatility';title:string;evidence:string};
const trendNames = {above_averages:'ترتيب صاعد',below_averages:'ترتيب هابط',mixed:'ترتيب مختلط',insufficient:'غير كافٍ'};
const n=(value:number|string)=>summaryNumber(value);
export function researchAlerts(current:TerminalResearch, previous:ResearchSnapshot|null, importedCurrent=false) {
  const blocked=(reason:string)=>({alerts:[] as ResearchAlert[],reason});
  if(!previous) return blocked('تحتاج التنبيهات إلى لقطة سابقة من الرمز نفسه.');
  if(importedCurrent||previous.restored_from_backup) return blocked('لا تُنشأ تنبيهات من لقطات مستعادة من ملف؛ بصمة الملف لا تثبت أصالة مصدره.');
  const before=previous.report, a=current.analysis,b=before.analysis;
  if(current.symbol!==before.symbol || Date.parse(current.assessed_at)<=Date.parse(before.assessed_at)) return blocked('الرمز أو ترتيب أوقات القراءتين غير متسق.');
  if(!a||!b||!current.data_quality||!before.data_quality) return blocked('الشموع أو فحص جودتها غير متاح في إحدى القراءتين.');
  if([current,before].some(r=>r.sources.find(s=>s.kind==='history')?.state!=='available'||!r.sources.find(s=>s.kind==='history')?.response_sha256)
    || a.history_provider==='UNKNOWN'||a.history_provider!==b.history_provider
    || a.interval==='UNVERIFIED'||a.interval!==b.interval||a.interval_basis!=='provider_request'||b.interval_basis!=='provider_request')
    return blocked('يلزم مصدر شموع وإطار معلنان ومتطابقان مع بصمتي الاستجابتين.');
  if(!['fetched','cached'].includes(a.history_cache_state)||!['fetched','cached'].includes(b.history_cache_state)
    || !a.history_fetched_at||!b.history_fetched_at
    || Date.parse(a.history_fetched_at)<=Date.parse(b.history_fetched_at)
    || Date.parse(a.history_fetched_at)>Date.parse(current.assessed_at)||Date.parse(b.history_fetched_at)>Date.parse(before.assessed_at))
    return blocked('لم يتقدم جلب الشموع بنجاح أو توجد نسخة قديمة أو أوقات غير متسقة.');
  if(Date.parse(a.last_time)<=Date.parse(b.last_time)) return blocked('لم تبدأ شمعة أحدث؛ تغيّر القراءة داخل الشمعة نفسها لا ينشئ تنبيهًا جديدًا.');
  // Do not infer exchange sessions or monthly durations. Current bars may be incomplete.
  const seconds=fixedIntervalSeconds[a.interval];
  if(!seconds) return blocked('الإطار تقويمي غير ثابت؛ المقارنة الزمنية المطلوبة غير متحققة.');
  if([current,before].some(r=>!r.data_quality||r.data_quality.status==='unavailable'
    || r.data_quality.reasons.some(reason=>reason!=='session_calendar_unverified'&&reason!=='insufficient_samples')
    || Date.parse(r.assessed_at)-Date.parse(r.analysis!.history_fetched_at!)>90000
    || Date.parse(r.assessed_at)-Date.parse(r.analysis!.last_time)>seconds*2000
    || Date.parse(r.analysis!.last_time)>Date.parse(r.analysis!.history_fetched_at!)))
    return blocked('جودة السلسلة أو عمرها لا يسمحان بتنبيهات قابلة للمقارنة؛ لا نستنتج جلسة من التقويم.');
  const alerts:ResearchAlert[]=[];
  function add(kind:ResearchAlert['kind'],title:string,evidence:string) {
    alerts.push({id:`${current.symbol}:${a!.history_provider}:${a!.interval}:${b!.last_time}:${a!.last_time}:${kind}`,kind,title,evidence});
  }
  if(current.data_quality.trend.allowed&&before.data_quality.trend.allowed&&a.trend!==b.trend
    && a.trend!=='insufficient'&&b.trend!=='insufficient'
    && [a.sma20,a.sma50,b.sma20,b.sma50].every(v=>v!==null))
    add('trend',`تغير ترتيب الاتجاه: ${trendNames[b.trend]} ← ${trendNames[a.trend]}`,
      `الإغلاق ${n(b.last_close)} ← ${n(a.last_close)}؛ SMA20 ${n(b.sma20!)} ← ${n(a.sma20!)}؛ SMA50 ${n(b.sma50!)} ← ${n(a.sma50!)}.`);
  if(current.data_quality.momentum.allowed&&before.data_quality.momentum.allowed&&a.rsi14_simple!==null&&b.rsi14_simple!==null) {
    const old=Number(b.rsi14_simple),next=Number(a.rsi14_simple);
    const crossed=[30,70].filter(t=>(old<t&&next>=t)||(old>t&&next<=t));
    if(crossed.length) add('momentum',`عبر RSI مستوى ${crossed.join(' و ')} ${next>old?'صعودًا':'هبوطًا'}`,
      `RSI14 البسيط ${n(old)} ← ${n(next)}؛ فرق ${n(next-old)} نقطة. عبور وصفي لا يتنبأ بانعكاس السعر.`);
  }
  if(current.data_quality.volatility.allowed&&before.data_quality.volatility.allowed&&a.atr14_simple!==null&&b.atr14_simple!==null) {
    const old=100*Number(b.atr14_simple)/Number(b.last_close),next=100*Number(a.atr14_simple)/Number(a.last_close);
    const relative=old>0?100*(next-old)/old:null;
    if(relative!==null&&Math.abs(relative)>=25&&Math.abs(next-old)>=0.25)
      add('volatility',`تغير التذبذب النسبي ${next>old?'بالارتفاع':'بالانخفاض'}`,
        `ATR14/الإغلاق ${n(old)}% ← ${n(next)}%؛ فرق ${n(next-old)} نقطة مئوية (${n(relative)}% نسبيًا). ATR ${n(b.atr14_simple)} ← ${n(a.atr14_simple)}.`);
  }
  return {alerts,reason:alerts.length?null:'لم تتحقق عتبات التنبيه في هذه المقارنة الصالحة؛ لا يعني ذلك غياب مخاطر أو أحداث.'};
}
