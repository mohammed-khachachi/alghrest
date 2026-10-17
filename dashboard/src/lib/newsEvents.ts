import { z } from 'zod';

const time = z.string().datetime({ offset: true });
const date = z.string().date();
const url = z.string().url().refine(v => {
  const u = new URL(v); return u.protocol === 'https:' && !u.username && !u.password;
});
const source = z.object({
  name: z.string(), url, kind: z.enum(['news', 'calendar']), attempted_at: time,
  fetched_at: time.nullable(), state: z.enum(['ok', 'empty', 'stale', 'unavailable', 'invalid']),
  http_status: z.number().int().nullable(), content_sha256: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
  parsed_count: z.number().int().nonnegative(), usable_count: z.number().int().nonnegative(), reasons: z.array(z.string()),
}).strict();
const headline = z.object({ item: z.object({ id: z.string(), title: z.string(), url,
  source: z.string(), published_at: time, category: z.enum(['macro', 'crypto', 'regulation', 'equity']) }).strict(),
  relevance: z.array(z.string()).min(1), }).strict();
const event = z.object({ event: z.object({ id: z.string(), name: z.string(), known_at: time,
  scheduled_at: time.nullable(), source: url, affected_markets: z.array(z.string()),
  impact: z.literal('unknown'), status: z.enum(['scheduled', 'cancelled', 'unknown']) }).strict(),
  source_name: z.string(), date_start: date.nullable(), date_end: date.nullable(), printed_time: z.string().nullable(),
  timezone: z.enum(['America/New_York', 'UTC']).nullable(), relevance: z.array(z.string()).min(1), }).strict();
const schema = z.object({ schema_version: z.literal('news-events-v1'), instrument_id: z.enum(['MES', 'MNQ']),
  assessed_at: time, headlines: z.array(headline).max(25), events: z.array(event).max(100), sources: z.array(source).max(8),
  returned_date_start: date.nullable(), returned_date_end: date.nullable(), coverage: z.literal('partial'),
  event_risk: z.literal('UNKNOWN'), trade_permitted: z.literal(false), execution_enabled: z.literal(false), }).strict();
export type NewsContext = z.infer<typeof schema>;
export type ContextSource = NewsContext['sources'][number];

export function newsContext(raw: unknown, instrument: 'MES' | 'MNQ'): NewsContext {
  const v = schema.parse(raw); const now = Date.parse(v.assessed_at);
  if (v.instrument_id !== instrument || new Set(v.sources.map(s => s.name)).size !== v.sources.length) throw new Error('هوية الاستجابة غير مطابقة.');
  for (const s of v.sources) {
    if (s.usable_count > s.parsed_count || (s.fetched_at && Date.parse(s.fetched_at) < Date.parse(s.attempted_at)) ||
        (['ok', 'empty', 'stale'].includes(s.state) && (!s.fetched_at || !s.content_sha256)) ||
        (['ok', 'empty'].includes(s.state) && (Date.parse(s.fetched_at!) > now || now - Date.parse(s.fetched_at!) >= 300000))) throw new Error('توقيت المصدر غير متسق.');
  }
  const active = (name: string, kind: ContextSource['kind']) => v.sources.find(s => s.name === name && s.kind === kind && ['ok', 'empty'].includes(s.state));
  for (const h of v.headlines) {
    const age = now - Date.parse(h.item.published_at);
    if (!active(h.item.source, 'news') || age < 0 || age > 7 * 86400000) throw new Error('خبر خارج صلاحية المصدر.');
  }
  for (const e of v.events) {
    const s = active(e.source_name, 'calendar');
    if (!s || s.url !== e.event.source || Date.parse(e.event.known_at) > now ||
        (e.date_start === null) !== (e.date_end === null) || (e.date_start && e.date_end! < e.date_start) ||
        (e.event.scheduled_at !== null && !e.timezone)) throw new Error('حدث غير متسق مع مصدره.');
  }
  return v;
}

export function sourceState(source: ContextSource, now: number): ContextSource['state'] {
  if (['unavailable', 'invalid'].includes(source.state)) return source.state;
  const fetched = source.fetched_at === null ? NaN : Date.parse(source.fetched_at);
  if (!Number.isFinite(fetched) || fetched > now) return 'invalid';
  return now - fetched >= 300000 ? 'stale' : source.state;
}
export function ageLabel(stamp: string | null, now: number): string {
  if (!stamp) return 'غير معلوم';
  const delta = now - Date.parse(stamp);
  if (!Number.isFinite(delta) || delta < 0) return 'توقيت غير متسق';
  return `${Math.floor(delta / 60000)} دقيقة`;
}
export const stateLabel: Record<ContextSource['state'], string> = { ok: 'متاح جزئيًا', empty: 'جلب صحيح بلا عناصر صالحة', stale: 'قديم — يلزم تحديث', unavailable: 'غير متاح', invalid: 'تعذر التحقق من الصيغة أو الوقت' };
export function relevanceLabel(value: string): string {
  return ({ inflation: 'التضخم', central_bank: 'السياسة النقدية', labor: 'سوق العمل', growth: 'النمو الاقتصادي', equity_indexes: 'الأسهم والمؤشرات', user_interest: 'اهتمام أضفته', official_schedule_other: 'جدول اقتصادي رسمي' } as Record<string, string>)[value] ?? value;
}

// Shared by manual refresh, instrument changes and unmount: a late response cannot win.
export function contextRequests() {
  let generation = 0;
  return { next: () => ++generation, current: (value: number) => value === generation };
}
export function refreshDue(periodMinutes: number, visible: boolean, busy: boolean, elapsedMs: number): boolean {
  return [5, 15].includes(periodMinutes) && visible && !busy && elapsedMs >= periodMinutes * 60000;
}
