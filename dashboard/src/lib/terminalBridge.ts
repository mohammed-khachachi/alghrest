import { z } from 'zod';

export const TERMINAL_ORIGIN = 'http://127.0.0.1:3001';
export const TERMINAL_SYMBOL_PATTERN = /^(?=.*[A-Z0-9])[A-Z0-9.\-^=&]{1,20}$/;
export function terminalSymbol(value: string): string | null {
  const symbol = value.trim().toUpperCase();
  return TERMINAL_SYMBOL_PATTERN.test(symbol) ? symbol : null;
}
export function selectTerminalSymbol(value: string) {
  const symbol = terminalSymbol(value);
  return symbol ? { type: 'alghrest:select-symbol', symbol } as const : null;
}
export const TERMINAL_PROXIES = { MES: 'SPY', MNQ: 'QQQ' } as const;
export type LinkedInstrument = keyof typeof TERMINAL_PROXIES;

export function linkedInstrument(value: string): LinkedInstrument | null {
  return value === 'MES' || value === 'MNQ' ? value : null;
}

export function instrumentForProxy(value: string): LinkedInstrument | null {
  return value === 'SPY' ? 'MES' : value === 'QQQ' ? 'MNQ' : null;
}

const SymbolMessage = z.object({
  type: z.enum(['openterminal:ready', 'openterminal:symbol']),
  symbol: z.string().regex(TERMINAL_SYMBOL_PATTERN),
}).strict();

/** Caller must also require event.source === the mounted frame's contentWindow. */
export function terminalMessage(origin: string, data: unknown) {
  if (origin !== TERMINAL_ORIGIN) return null;
  const value = SymbolMessage.safeParse(data);
  return value.success ? value.data : null;
}

export function selectProxy(instrument: LinkedInstrument) {
  return { type: 'alghrest:select-symbol', symbol: TERMINAL_PROXIES[instrument] } as const;
}

export const stamp = z.string().refine(value => /(Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value)));
export const decimal = z.string().max(64).regex(/^-?\d+(?:\.\d+)?(?:e[+-]?\d+)?$/i);
function sign(value: string): number {
  const coefficient = value.split(/[eE]/)[0];
  if (!/[1-9]/.test(coefficient)) return 0;
  return coefficient.startsWith('-') ? -1 : 1;
}
export function publicLink(value: string) {
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !url.username && !url.password
      && !['localhost', 'testserver'].includes(url.hostname)
      && !url.hostname.endsWith('.local') && !url.hostname.endsWith('.localhost')
      && !/^[\d.]+$/.test(url.hostname) && !url.hostname.startsWith('[');
  } catch { return false; }
}

const Context = z.object({
  schema_version: z.literal('openterminal-context-v1'),
  instrument_id: z.enum(['MES', 'MNQ']), proxy_symbol: z.enum(['SPY', 'QQQ']), assessed_at: stamp,
  quote: z.object({
    symbol: z.enum(['SPY', 'QQQ']), name: z.string().max(200).nullable(),
    price: decimal.refine(value => sign(value) > 0), change_percent: decimal.nullable(),
    provider: z.enum(['nasdaq', 'yahoo', 'stooq', 'tradingview']),
    currency: z.literal('USD'), market_time: stamp.nullable(),
  }).strict().nullable(),
  headlines: z.array(z.object({
    title: z.string().min(1).max(400), url: z.string().max(2000).refine(publicLink),
    publisher: z.string().min(1).max(150), published_at: stamp.nullable(),
  }).strict()).max(8),
  sources: z.array(z.object({
    kind: z.enum(['quotes', 'news']), state: z.enum(['available', 'unavailable', 'invalid']),
    received_at: stamp, response_sha256: z.string().regex(/^[a-f0-9]{64}$/).nullable(),
    reasons: z.array(z.string()),
  }).strict()).length(2),
  direction: z.enum(['proxy_up', 'proxy_down', 'proxy_unchanged', 'unknown']),
  scope: z.literal('public_etf_context'), freshness: z.literal('UNKNOWN'), event_risk: z.literal('UNKNOWN'),
  quote_usable_for_risk: z.literal(false), trade_permitted: z.literal(false), execution_enabled: z.literal(false),
}).strict();

export type TerminalContext = z.infer<typeof Context>;

export function terminalContext(value: unknown, instrument: LinkedInstrument, now = Date.now()): TerminalContext | null {
  const parsed = Context.safeParse(value);
  if (!parsed.success) return null;
  const context = parsed.data;
  const assessed = Date.parse(context.assessed_at);
  if (context.instrument_id !== instrument || context.proxy_symbol !== TERMINAL_PROXIES[instrument]
    || assessed > now + 5000 || now - assessed >= 90000
    || new Set(context.sources.map(row => row.kind)).size !== 2
    || context.sources.some(row => Date.parse(row.received_at) > assessed
      || (row.state === 'available' && !row.response_sha256))
    || context.headlines.some(row => row.published_at && Date.parse(row.published_at) > assessed)) return null;
  if (context.quote && (context.quote.symbol !== context.proxy_symbol
    || context.sources.find(row => row.kind === 'quotes')?.state !== 'available'
    || (context.quote.market_time && Date.parse(context.quote.market_time) > assessed))) return null;
  const direction = context.quote?.change_percent == null ? 'unknown'
    : sign(context.quote.change_percent) > 0 ? 'proxy_up'
    : sign(context.quote.change_percent) < 0 ? 'proxy_down' : 'proxy_unchanged';
  return context.direction === direction ? context : null;
}
