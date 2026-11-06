import { currentLocale, tr } from '../i18n/core';
import type { TerminalResearch } from './terminalResearch';
import { quoteFreshness } from './terminalFreshness';

export type DataStatusCard = {
  kind: 'quotes' | 'history' | 'news'; title: string; status: string;
  tone: 'neutral' | 'warning' | 'error'; details: Array<[string, string]>;
};
const names = {quotes:'السعر',history:'الشموع',news:'الأخبار'};
const intervals: Record<string,string> = {
  '5m':'5 دقائق','15m':'15 دقيقة','1h':'ساعة','4h':'4 ساعات','1d':'يومي',
  '1wk':'أسبوعي','1w':'أسبوعي','1mo':'شهري','1M':'شهري',UNVERIFIED:'غير معلن',
};
export function sourceTime(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString(currentLocale(), {timeZone:'Africa/Casablanca'}) + ' ' + tr('(المغرب)') : 'غير معلن';
}
export function dataAge(value: string | null | undefined, now: number) {
  if (!value) return 'غير معلوم';
  const seconds = Math.max(0, Math.floor((now-Date.parse(value))/1000));
  if (seconds < 60) return `${seconds} ثانية`;
  if (seconds < 3600) return `${Math.floor(seconds/60)} دقيقة`;
  if (seconds < 86400) return `${Math.floor(seconds/3600)} ساعة`;
  return `${Math.floor(seconds/86400)} يوم`;
}

/** Age is an observation; only a reported refresh failure proves stale-cache delivery. */
export function terminalDataStatus(report: TerminalResearch, now: number): DataStatusCard[] {
  return (['quotes','history','news'] as const).map(kind => {
    const source = report.sources.find(s=>s.kind===kind)!;
    const card: DataStatusCard = {kind,title:names[kind],status:'متاح',tone:'neutral',details:[]};
    if (source.state !== 'available') {
      card.status = source.state === 'invalid' ? 'بيانات مرفوضة' : 'غير متاح';
      card.tone = source.state === 'invalid' ? 'error' : 'warning';
      card.details.push(['الحالة',source.state === 'invalid' ? 'لم تجتز الاستجابة فحص البيانات.' : 'تعذر الحصول على استجابة من OpenTerminal.']);
    }
    if (kind === 'history') {
      const a = report.analysis;
      card.details.push(['مزوّد الشموع',a && a.history_provider !== 'UNKNOWN' ? a.history_provider : 'غير معلن'],
        ['الإطار الزمني',a ? intervals[a.interval] : 'غير معلن']);
      if (a?.interval_basis === 'provider_request') card.details.push(['مصدر الإطار','الإطار المطلوب من مزوّد الشموع؛ قد توجد فجوات بين الشموع.']);
      if (a?.history_cache_state === 'stale') {
        card.status = 'تحديث متعثر · نسخة سابقة'; card.tone = 'warning';
        card.details.push(['التأخير','فشل تحديث المصدر؛ أُعيدت آخر نسخة محفوظة.']);
      } else if (a?.history_cache_state === 'cached') card.details.push(['النسخة','نسخة من ذاكرة OpenTerminal المؤقتة']);
      else if (a?.history_cache_state === 'fetched') card.details.push(['النسخة','جُلِبت من المزوّد في هذه القراءة']);
      else card.details.push(['حالة النسخة','غير معلنة']);
      card.details.push(['آخر جلب ناجح في OpenTerminal',sourceTime(a?.history_fetched_at)],
        ['آخر شمعة',sourceTime(a?.last_time)],['عمر آخر شمعة',dataAge(a?.last_time,now)]);
      if (!a && source.state === 'available') {card.status='الشموع غير متاحة';card.tone='warning';}
      if (a?.interval === 'UNVERIFIED') {card.tone='warning';card.details.push(['الإطار غير متاح','لا نستنتجه من نطاق 6 أشهر أو من المسافة بين الشموع.']);}
    } else if (kind === 'quotes') {
      const q = report.quote;
      const context=quoteFreshness(report,now);
      card.details.push(['المزوّد',q?.provider ?? 'غير معلن'], ['وقت السعر لدى المصدر',sourceTime(q?.market_time)], ['عمر السعر',dataAge(q?.market_time,now)]);
      if (q && !q.market_time) {card.status='متاح · حداثته غير معلومة';card.tone='warning';}
      else if (q?.market_time && now-Date.parse(q.market_time)>15*60_000) {
        card.status='وقت السعر أقدم من 15 دقيقة';card.tone='warning';
        card.details.push(['تنبيه العمر','حد عرض فقط؛ لا يتحقق من جلسة التداول أو يثبت تأخير المزوّد.']);
      }
      if (!q && source.state === 'available') {card.status='السعر غير متاح';card.tone='warning';}
      if(q) {
        card.details.push(['تفسير حداثة السعر',context.message],['حالة الجلسة لدى المصدر',context.sessionNote],
          ['الحالة كما وردت',q.market_state??'غير معلنة'],
          ['وقت إعلان الحالة وجلب السعر',sourceTime(q.observation?.fetched_at)],
          ['حالة نسخة السعر',q.observation?.cache_state ?? 'غير معلنة']);
        if(context.status==='stale_cache') {card.status='تحديث السعر متعثر · نسخة سابقة';card.tone='warning';}
        else if(context.status==='closed_reported') {card.status='سعر سابق · إغلاق معلن عند الجلب';card.tone='warning';}
        else if(context.status==='old_while_open_reported') {card.status='وقت قديم · جلسة مفتوحة معلنة';card.tone='warning';}
      }
    } else {
      const newest = report.headlines.reduce<string|null>((best,h)=>h.published_at && (!best || Date.parse(h.published_at)>Date.parse(best)) ? h.published_at : best,null);
      card.details.push(['العناوين الصالحة',String(report.headlines.length)],['أحدث خبر منشور',sourceTime(newest)], ['عمر أحدث خبر',dataAge(newest,now)]);
      if (!report.headlines.length && source.state === 'available') {card.status='لا عناوين صالحة';card.tone='warning';}
    }
    card.details.push([source.state === 'available' ? 'استلام ALGHREST' : 'آخر فحص ALGHREST',sourceTime(source.received_at)]);
    return card;
  });
}
