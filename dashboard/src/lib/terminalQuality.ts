import { z } from 'zod';
import type { TerminalResearch } from './terminalResearch';

export const fixedIntervalSeconds: Record<string, number> = {'5m':300,'15m':900,'1h':3600,'4h':14400,'1d':86400,'1wk':604800,'1w':604800};

const reason = z.enum(['history_unavailable', 'invalid_response', 'invalid_metadata', 'no_candles',
  'invalid_candles', 'invalid_timestamps', 'duplicate_timestamps', 'out_of_order_timestamps',
  'future_timestamps', 'inconsistent_fetch_time', 'missing_intervals', 'irregular_intervals',
  'stale_cache', 'provider_unverified', 'interval_unverified', 'session_calendar_unverified',
  'calendar_interval_unverified', 'insufficient_samples']);
const conclusion = z.object({allowed: z.boolean(), reasons: z.array(reason)}).strict()
  .refine(c => c.allowed === (c.reasons.length === 0));
const count = z.number().int().min(0).max(2000).nullable();
export const CandleQualitySchema = z.object({
  schema_version: z.literal('candle-quality-v1'), status: z.enum(['usable', 'limited', 'unavailable']),
  received_candles: z.number().int().min(0).max(256000).nullable(),
  invalid_candles: count, invalid_timestamps: count, duplicate_timestamps: count,
  out_of_order_pairs: count, future_timestamps: count,
  interval_seconds: z.number().int().positive().nullable(), gap_count: count,
  missing_intervals: z.number().int().nonnegative().nullable(), irregular_intervals: count,
  largest_gap_seconds: z.number().finite().nonnegative().nullable(),
  continuity_basis: z.enum(['continuous', 'session_unverified', 'unverified']),
  reasons: z.array(reason), trend: conclusion, momentum: conclusion, volatility: conclusion,
}).strict().superRefine((q, ctx) => {
  const checks = [q.trend, q.momentum, q.volatility];
  const fatalCounts = [q.invalid_candles, q.invalid_timestamps, q.duplicate_timestamps,
    q.out_of_order_pairs, q.future_timestamps];
  if ((q.status === 'usable') !== (q.reasons.length === 0)
    || (q.status === 'usable' && checks.some(c => !c.allowed))
    || (q.status === 'unavailable' && checks.some(c => c.allowed))
    || checks.some(c => c.reasons.some(r => !q.reasons.includes(r)))
    || (fatalCounts.some(n => n !== null && n > 0) && q.status !== 'unavailable')
    || (q.status !== 'unavailable' && (q.received_candles === null || q.received_candles < 1
      || (q.received_candles < 50 && q.trend.allowed)
      || (q.received_candles < 15 && (q.momentum.allowed || q.volatility.allowed))))
    || (q.status === 'usable' && q.continuity_basis !== 'continuous')
    || (q.reasons.includes('stale_cache') && checks.some(c => c.allowed)))
    ctx.addIssue({code: z.ZodIssueCode.custom, message: 'Inconsistent quality assessment'});
});
export type CandleQuality = z.infer<typeof CandleQualitySchema>;

export const qualityReasonText: Record<z.infer<typeof reason>, string> = {
  history_unavailable: 'تعذر الحصول على الشموع من OpenTerminal.',
  invalid_response: 'استجابة الشموع غير صالحة أو تتجاوز الحد المسموح.',
  invalid_metadata: 'هوية المصدر أو توقيت الجلب أو الإطار المعلن غير متسق.',
  no_candles: 'أعاد المصدر سلسلة بلا شموع.',
  invalid_candles: 'توجد شموع ناقصة أو قيم لا تجتاز فحص السعر والحجم.',
  invalid_timestamps: 'توجد أوقات شموع مفقودة أو غير صالحة.',
  duplicate_timestamps: 'توجد أوقات شموع مكررة؛ لم نحذفها أو ندمجها.',
  out_of_order_timestamps: 'توجد شموع بترتيب زمني معكوس؛ لم نعد ترتيب المصدر.',
  future_timestamps: 'توجد شموع مؤرخة بعد وقت قراءة البيانات.',
  inconsistent_fetch_time: 'وقت شمعة يتجاوز وقت الجلب، أو وقت الجلب في المستقبل.',
  missing_intervals: 'توجد فترات مفقودة في سلسلة ذات إطار مستمر معلن.',
  irregular_intervals: 'بعض الفواصل لا تطابق شبكة الإطار المستمر المعلن.',
  stale_cache: 'فشل تحديث المصدر؛ حُجبت الاستنتاجات لهذه النسخة السابقة.',
  provider_unverified: 'مزوّد الشموع غير معلن؛ الحسابات وصفية ومحدودة.',
  interval_unverified: 'الإطار غير معلن؛ لم نستنتجه من المسافة بين الشموع.',
  session_calendar_unverified: 'تقويم الجلسات والعطل غير متحقق؛ الفواصل الطويلة لا تثبت فقد شموع.',
  calendar_interval_unverified: 'الإطار تقويمي؛ لم نحوله إلى عدد ثابت من الثواني.',
  insufficient_samples: 'عدد الشموع غير كافٍ لبعض المؤشرات: الاتجاه 50، والزخم والتذبذب 15.',
};
export function qualityLabel(q: CandleQuality | null | undefined) {
  return q ? {usable: 'قابلة للاستخدام', limited: 'محدودة', unavailable: 'غير متاحة'}[q.status]
    : 'محدودة · لم تُفحص جودة هذه اللقطة';
}
export function qualityReasons(q: CandleQuality | null | undefined): string[] {
  return q ? q.reasons.map(r => qualityReasonText[r]) : ['لقطة سابقة بلا فحص جودة؛ لم نعد تقييمها أو نغيّر بياناتها المحفوظة.'];
}
export function qualityEvidence(q: CandleQuality): Array<[string, string]> {
  const n = (value: number | null) => value === null ? 'غير معلوم' : value.toLocaleString('ar-MA');
  return [
    ['الشموع المستلمة', n(q.received_candles)], ['شموع غير صالحة', n(q.invalid_candles)],
    ['أوقات غير صالحة', n(q.invalid_timestamps)], ['أوقات مكررة', n(q.duplicate_timestamps)],
    ['أزواج معكوسة', n(q.out_of_order_pairs)], ['أوقات مستقبلية', n(q.future_timestamps)],
    ['فواصل أطول من الإطار', n(q.gap_count)], ['فترات مفقودة مؤكدة وفق الإطار المستمر', n(q.missing_intervals)],
    ['فواصل غير منتظمة في الإطار المستمر', n(q.irregular_intervals)],
    ['أكبر فاصل بالثواني', n(q.largest_gap_seconds)],
  ];
}

/** Keep all summary/overview/comparison consumers consistent without mutating saved reports. */
export function qualityAnalysis(report: Pick<TerminalResearch, 'analysis' | 'data_quality'>) {
  const a = report.analysis, q = report.data_quality;
  if (!a || q?.status === 'unavailable') return null;
  if (!q) return a;
  return {...a,
    sma20: q.trend.allowed ? a.sma20 : null, sma50: q.trend.allowed ? a.sma50 : null,
    trend: q.trend.allowed ? a.trend : 'insufficient' as const,
    rsi14_simple: q.momentum.allowed ? a.rsi14_simple : null,
    atr14_simple: q.volatility.allowed ? a.atr14_simple : null,
  };
}
