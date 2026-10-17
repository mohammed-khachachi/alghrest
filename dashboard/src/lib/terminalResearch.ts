import { z } from 'zod';
import { decimal, publicLink, stamp, TERMINAL_SYMBOL_PATTERN } from './terminalBridge';
import { CandleQualitySchema, fixedIntervalSeconds } from './terminalQuality';

const numeric = decimal.refine(v => Number.isFinite(Number(v)) && Math.abs(Number(v)) <= 1e30);
const positive = numeric.refine(v => Number(v) > 0);
const Research = z.object({
  schema_version: z.literal('openterminal-research-v1'), symbol: z.string().regex(TERMINAL_SYMBOL_PATTERN),
  requested_range: z.literal('6M'), assessed_at: stamp,
  quote: z.object({
    symbol: z.string().regex(TERMINAL_SYMBOL_PATTERN), name: z.string().max(200).nullable(),
    price: positive, change_percent: numeric.nullable(), currency: z.string().regex(/^[A-Za-z]{3,8}$/),
    provider: z.enum(['nasdaq', 'yahoo', 'yahoo-chart', 'stooq', 'tradingview', 'binance', 'fred']),
    market_time: stamp.nullable(),
    market_state: z.string().max(64).nullable().optional(),
    observation: z.object({schema_version:z.literal('quote-observation-v1'),fetched_at:stamp,
      cache_state:z.enum(['fetched','cached','stale']),market_state_basis:z.enum(['provider','UNVERIFIED'])}).strict().nullable().optional(),
  }).strict().nullable(),
  analysis: z.object({
    count: z.number().int().min(1).max(2000), first_time: stamp, last_time: stamp, last_close: positive,
    sma20: positive.nullable(), sma50: positive.nullable(),
    rsi14_simple: numeric.refine(v => Number(v) >= 0 && Number(v) <= 100).nullable(),
    atr14_simple: numeric.refine(v => Number(v) >= 0).nullable(),
    recent20_low: positive.nullable(), recent20_high: positive.nullable(),
    trend: z.enum(['above_averages', 'below_averages', 'mixed', 'insufficient']),
    history_provider: z.enum(['nasdaq','yahoo','stooq','binance','fred','UNKNOWN']),
    interval: z.enum(['5m','15m','1h','4h','1d','1wk','1mo','1w','1M','UNVERIFIED']),
    interval_basis: z.enum(['provider_request','UNVERIFIED']).default('UNVERIFIED'),
    history_fetched_at: stamp.nullable().default(null),
    history_cache_state: z.enum(['fetched','cached','stale','UNKNOWN']).default('UNKNOWN'),
  }).strict().nullable(),
  data_quality: CandleQualitySchema.nullable().optional(),
  headlines: z.array(z.object({
    title: z.string().min(1).max(400), url: z.string().max(2000).refine(publicLink),
    publisher: z.string().min(1).max(150), published_at: stamp.nullable(),
  }).strict()).max(8),
  sources: z.array(z.object({
    kind: z.enum(['quotes', 'news', 'history']), state: z.enum(['available', 'unavailable', 'invalid']),
    received_at: stamp, response_sha256: z.string().regex(/^[a-f0-9]{64}$/).nullable(), reasons: z.array(z.string()),
  }).strict()).length(3),
  freshness: z.literal('UNKNOWN'), event_risk: z.literal('UNKNOWN'),
  trade_permitted: z.literal(false), execution_enabled: z.literal(false),
}).strict();

export type TerminalResearch = z.infer<typeof Research>;
export function terminalResearch(value: unknown, symbol: string, now = Date.now()): TerminalResearch | null {
  const parsed = Research.safeParse(value);
  if (!parsed.success) return null;
  const report = parsed.data;
  const assessed = Date.parse(report.assessed_at);
  const states = new Map(report.sources.map(s => [s.kind, s.state]));
  if (report.symbol !== symbol || assessed > now + 5000 || now - assessed >= 90000
    || states.size !== 3 || report.sources.some(s => Date.parse(s.received_at) > assessed
      || (s.state === 'available' && !s.response_sha256))) return null;
  if (report.quote && (report.quote.symbol !== symbol || states.get('quotes') !== 'available'
    || (report.quote.market_time && Date.parse(report.quote.market_time) > assessed))) return null;
  const qo=report.quote?.observation;
  if(qo && (Date.parse(qo.fetched_at)>Date.parse(report.sources.find(s=>s.kind==='quotes')!.received_at)
    || (report.quote!.market_time && Date.parse(report.quote!.market_time!)>Date.parse(qo.fetched_at))
    || (qo.market_state_basis==='provider' && (!['yahoo','nasdaq'].includes(report.quote!.provider) || !report.quote!.market_state)))) return null;
  if (report.analysis && (states.get('history') !== 'available'
    || Date.parse(report.analysis.last_time) > assessed
    || Date.parse(report.analysis.first_time) > Date.parse(report.analysis.last_time)
    || (report.analysis.count < 20 && [report.analysis.sma20, report.analysis.recent20_low, report.analysis.recent20_high].some(v => v !== null))
    || (report.analysis.count < 50 && report.analysis.sma50 !== null)
    || (report.analysis.count < 15 && [report.analysis.rsi14_simple, report.analysis.atr14_simple].some(v => v !== null)))) return null;
  if (report.headlines.some(h => (h.published_at && Date.parse(h.published_at) > assessed))
    || (report.headlines.length > 0 && states.get('news') !== 'available')) return null;
  const a = report.analysis;
  const q = report.data_quality;
  if (q && ((q.status === 'unavailable') !== (a === null)
    || (a && (q.received_candles !== a.count || states.get('history') !== 'available'
      || q.interval_seconds !== (fixedIntervalSeconds[a.interval] ?? null)
      || (q.continuity_basis === 'continuous') !== (a.history_provider === 'binance' && a.interval in fixedIntervalSeconds)
      || (!q.trend.allowed && (a.sma20 !== null || a.sma50 !== null || a.trend !== 'insufficient'))
      || (!q.momentum.allowed && a.rsi14_simple !== null)
      || (!q.volatility.allowed && a.atr14_simple !== null))))) return null;
  if (a && ((a.interval !== 'UNVERIFIED') !== (a.interval_basis === 'provider_request')
    || (a.interval !== 'UNVERIFIED' && a.history_provider === 'UNKNOWN')
    || (a.history_fetched_at !== null && a.history_cache_state === 'UNKNOWN')
    || (a.history_cache_state !== 'UNKNOWN' && (!a.history_fetched_at || a.history_provider === 'UNKNOWN'))
    || (a.history_provider !== 'UNKNOWN' && (!a.history_fetched_at || a.history_cache_state === 'UNKNOWN'))
    || (a.history_fetched_at && (Date.parse(a.history_fetched_at) > Date.parse(report.sources.find(s => s.kind === 'history')!.received_at)
      || Date.parse(a.history_fetched_at) < Date.parse(a.last_time))))) return null;
  return report;
}
