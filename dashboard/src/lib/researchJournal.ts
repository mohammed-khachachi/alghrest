import { z } from 'zod';
import { stamp, TERMINAL_SYMBOL_PATTERN } from './terminalBridge';
import { terminalResearch, type TerminalResearch } from './terminalResearch';
import { summaryNumber } from './terminalSummary';
import { qualityAnalysis, qualityLabel } from './terminalQuality';

const Watchlist = z.array(z.object({
  symbol: z.string().regex(TERMINAL_SYMBOL_PATTERN), snapshots: z.number().int().min(0).max(100),
  latest_saved_at: stamp.nullable(),
}).strict()).max(50);
export type ResearchWatchEntry = z.infer<typeof Watchlist>[number];
export function researchWatchlist(value: unknown): ResearchWatchEntry[] {
  const entries = Watchlist.parse(value);
  if (new Set(entries.map(e => e.symbol)).size !== entries.length) throw new Error('قائمة متابعة غير صالحة.');
  return entries;
}
const Envelope = z.object({
  schema_version: z.literal('research-snapshot-v1'), id: z.string().regex(/^[a-f0-9]{32}$/),
  saved_at: stamp, report: z.unknown(),
  restored_from_backup: z.string().regex(/^[a-f0-9]{64}$/).nullable().optional(),
}).strict();
export type ResearchSnapshot = { schema_version: 'research-snapshot-v1'; id: string; saved_at: string; report: TerminalResearch; restored_from_backup?:string|null };
export function researchSnapshot(value: unknown, symbol: string, now = Date.now()): ResearchSnapshot {
  const envelope = Envelope.parse(value);
  const saved = Date.parse(envelope.saved_at);
  // Validate against the original save clock, not today's live-display expiry.
  const report = terminalResearch(envelope.report, symbol, saved);
  if (!report || saved > now + 5000 || Date.parse(report.assessed_at) > saved)
    throw new Error('هوية اللقطة أو توقيتها غير صالحين.');
  return { ...envelope, report };
}
export function researchHistory(value: unknown, symbol: string, now = Date.now()): ResearchSnapshot[] {
  if (!Array.isArray(value) || value.length > 100) throw new Error('سجل البحث غير صالح.');
  const records = value.map(row => researchSnapshot(row, symbol, now));
  if (new Set(records.map(r => r.id)).size !== records.length
    || records.some((r, i) => i > 0 && Date.parse(records[i - 1].saved_at) < Date.parse(r.saved_at)))
    throw new Error('ترتيب سجل البحث غير صالح.');
  return records;
}

export type ResearchChange = { label: string; before: string; after: string; changed: boolean; note?: string };
const trendNames = { above_averages: 'ترتيب صاعد', below_averages: 'ترتيب هابط', mixed: 'مختلط', insufficient: 'بيانات غير كافية' };
const stateNames = { available: 'متاح', unavailable: 'غير متاح', invalid: 'مرفوض' };
const cacheNames = { fetched: 'جلب ناجح', cached: 'نسخة مؤقتة', stale: 'تعثر التحديث · نسخة سابقة', UNKNOWN: 'غير معلن' };
const timeframeNames = {'5m':'5 دقائق','15m':'15 دقيقة','1h':'ساعة','4h':'4 ساعات','1d':'يومي','1wk':'أسبوعي','1w':'أسبوعي','1mo':'شهري','1M':'شهري',UNVERIFIED:'غير معلن'};
const display = (value: string | null | undefined) => value == null ? 'غير متاح' : summaryNumber(value);

export function compareResearch(current: TerminalResearch, previous: TerminalResearch) {
  if (current.symbol !== previous.symbol || Date.parse(current.assessed_at) < Date.parse(previous.assessed_at))
    throw new Error('لا يمكن مقارنة رمزين مختلفين أو قراءة أقدم بوصفها الحالية.');
  const a = qualityAnalysis(current), b = qualityAnalysis(previous);
  const comparable = !!a && !!b && a.history_provider !== 'UNKNOWN'
    && a.history_provider === b.history_provider && a.interval !== 'UNVERIFIED'
    && a.interval === b.interval && a.interval_basis === b.interval_basis;
  const rows: ResearchChange[] = [];
  function add(label: string, before: string, after: string, note?: string, changed = before !== after) {
    rows.push({ label, before, after, changed, note });
  }
  add('الاتجاه', b ? trendNames[b.trend] : 'غير متاح', a ? trendNames[a.trend] : 'غير متاح');
  for (const [key, label] of [['last_close', 'الإغلاق التاريخي'], ['sma20', 'متوسط 20'], ['sma50', 'متوسط 50'], ['rsi14_simple', 'الزخم · RSI 14'], ['atr14_simple', 'التذبذب · ATR 14']] as const) {
    const before = b?.[key] ?? null, after = a?.[key] ?? null;
    const changed = before === null || after === null ? before !== after : Number(before) !== Number(after);
    const note = comparable && before !== null && after !== null
      ? `الفرق: ${summaryNumber(Number(after) - Number(before))}${key === 'rsi14_simple' ? ' نقطة RSI' : ' بوحدة المؤشر'}`
      : 'لا نحسب فرقًا عند فقد القيمة أو اختلاف/غياب المزوّد أو الإطار.';
    add(label, display(before), display(after), note, changed);
  }
  add('مزوّد الشموع', b && b.history_provider !== 'UNKNOWN' ? b.history_provider : 'غير معلن', a && a.history_provider !== 'UNKNOWN' ? a.history_provider : 'غير معلن');
  add('الإطار الزمني', timeframeNames[b?.interval ?? 'UNVERIFIED'], timeframeNames[a?.interval ?? 'UNVERIFIED']);
  add('حالة نسخة الشموع', cacheNames[b?.history_cache_state ?? 'UNKNOWN'], cacheNames[a?.history_cache_state ?? 'UNKNOWN']);
  add('جودة الشموع', qualityLabel(previous.data_quality), qualityLabel(current.data_quality));
  for (const kind of ['quotes', 'history', 'news'] as const) {
    const label = {quotes: 'توفر السعر', history: 'توفر الشموع', news: 'توفر الأخبار'}[kind];
    add(label, stateNames[previous.sources.find(s => s.kind === kind)!.state], stateNames[current.sources.find(s => s.kind === kind)!.state]);
  }
  const newsAvailable = [current, previous].every(r => r.sources.find(s => s.kind === 'news')!.state === 'available');
  const old = new Map(previous.headlines.map(h => [h.url, h]));
  const next = new Map(current.headlines.map(h => [h.url, h]));
  return {
    rows, comparable, newsAvailable,
    added: newsAvailable ? current.headlines.filter(h => !old.has(h.url)) : [],
    removed: newsAvailable ? previous.headlines.filter(h => !next.has(h.url)) : [],
    updated: newsAvailable ? current.headlines.filter(h => {
      const prior = old.get(h.url);
      return prior && (prior.title !== h.title || prior.publisher !== h.publisher || prior.published_at !== h.published_at);
    }) : [],
  };
}

/** The latest snapshot strictly older than the live assessment is the baseline. */
export function priorSnapshot(records: ResearchSnapshot[], report: TerminalResearch) {
  return records.find(r => r.report.symbol === report.symbol && Date.parse(r.report.assessed_at) < Date.parse(report.assessed_at)) ?? null;
}
