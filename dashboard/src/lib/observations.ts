import { z } from 'zod';

const decimal = z.string().regex(/^-?(0|[1-9]\d{0,11})(\.\d{1,8})?$/);
const stamp = z.string().datetime({ offset: true }).nullable();
const printed = z.object({ label: z.string().min(1).max(100), value: decimal.nullable(), evidence: z.string().min(1).max(500) }).strict();
const frameSchema = z.object({
  image_id: z.string().regex(/^[a-zA-Z0-9_-]{1,64}$/), contract: z.string().max(40).nullable(),
  interval: z.enum(['5m', '15m', '1h']), captured_at: stamp, observed_at: stamp,
  last_closed_bar_at: stamp, delay_status: z.enum(['real_time_reported', 'delayed', 'unknown']),
  last: decimal.nullable(), bid: decimal.nullable(), ask: decimal.nullable(),
  price_evidence: z.string().min(1).max(500), indicators: z.array(printed).max(20),
  printed_levels: z.array(printed).max(20), hypotheses: z.array(z.string().min(1).max(500)).max(10),
}).strict();
export const packetSchema = z.object({
  schema_version: z.literal('user-observation-v1'), instrument_id: z.enum(['MES', 'MNQ']),
  contract: z.string().max(40).nullable(), source_kind: z.enum(['manual', 'screenshot_transcription']),
  source_reference: z.string().min(1).max(500), frames: z.array(frameSchema).min(1).max(3),
}).strict();
export type ObservationPacket = z.infer<typeof packetSchema>;
const hash = z.string().regex(/^[a-f0-9]{64}$/);
const time = z.string().datetime({ offset: true });
const viewSchema = z.object({
  record: z.object({ id: z.string().regex(/^[a-zA-Z0-9_-]{1,64}$/), revision: hash,
    parent_revision: hash.nullable(), created_at: time, raw_json: z.string().min(1).max(100000),
    packet: packetSchema, source_hashes: z.record(hash) }).strict(),
  latest_revision: hash, reviewed_at: stamp, assessed_at: time, warnings: z.array(z.string()),
  origin: z.literal('user_reported'), trade_permitted: z.literal(false), execution_enabled: z.literal(false),
}).strict();
export type ObservationView = z.infer<typeof viewSchema>;

export function observationView(raw: unknown): ObservationView {
  const value = viewSchema.parse(raw);
  if (Date.parse(value.record.created_at) > Date.parse(value.assessed_at) ||
      (value.reviewed_at !== null && (Date.parse(value.reviewed_at) < Date.parse(value.record.created_at) || Date.parse(value.reviewed_at) > Date.parse(value.assessed_at)))) {
    throw new Error('توقيت النسخة أو المراجعة غير متسق.');
  }
  return value;
}

export function observationTemplate(): ObservationPacket {
  return { schema_version: 'user-observation-v1', instrument_id: 'MES', contract: null,
    source_kind: 'manual', source_reference: 'إدخال المستخدم — أكمل وصف المصدر',
    frames: [{ image_id: 'frame-1', contract: null, interval: '5m', captured_at: null,
      observed_at: null, last_closed_bar_at: null, delay_status: 'unknown', last: null, bid: null,
      ask: null, price_evidence: 'أكمل موضع قراءة الأسعار أو اتركها مجهولة', indicators: [], printed_levels: [], hypotheses: [] }] };
}

export function responseGate() {
  let revision = 0;
  return { next: () => ++revision, current: (value: number) => value === revision };
}

export function canReview(value: ObservationView | null, dirty: boolean): boolean {
  return Boolean(value && !dirty && value.record.revision === value.latest_revision && value.reviewed_at === null);
}

export function priceAge(packet: ObservationPacket, now: number): string {
  const times = packet.frames.map(f => f.observed_at === null ? NaN : Date.parse(f.observed_at));
  if (times.some(t => !Number.isFinite(t))) return 'وقت بعض الأسعار غير معلوم';
  if (times.some(t => t > now)) return 'وقت سعر في المستقبل؛ أعد التحقق';
  const minutes = Math.floor((now - Math.min(...times)) / 60000);
  return `${minutes >= 15 ? 'أسعار قديمة · ' : ''}عمر أقدم سعر: ${minutes} دقيقة · صحة النقل غير متحققة مستقلًا`;
}

export function warningLabel(reason: string): string {
  const labels: Record<string, string> = { user_reported_not_independently_verified: 'بيانات صرّح بها المستخدم؛ لم تتحقق من السوق مستقلًا',
    not_a_candle_dataset: 'هذه الملاحظة ليست سجل شموع', missing_contract: 'رمز العقد المؤرخ غير معلوم', incomplete_timeframes: 'بعض الفريمات غير موجودة',
    missing_captured_at: 'وقت الالتقاط غير معلوم', missing_observed_at: 'وقت السعر غير معلوم', missing_last_closed_bar_at: 'آخر إغلاق مؤكد غير معلوم',
    stale_price: 'السعر قديم', unknown_delay: 'تأخير المصدر غير معلوم', delayed_delay: 'المصدر متأخر', missing_last: 'آخر سعر غير معلوم' };
  const parts = reason.split(':');
  return parts.length === 2 ? `${parts[0]}: ${labels[parts[1]] ?? parts[1]}` : labels[reason] ?? reason;
}
