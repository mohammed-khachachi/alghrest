import {
  HistoryResponseSchema,
  HoldingsResponseSchema,
  QuotesResponseSchema,
  SymbolsResponseSchema,
  type HistoricalBar,
  type Holding,
  type Quote,
  type SymbolEntry,
} from '@/types/quotes';

async function jsonFetch<T>(url: string, parse: (raw: unknown) => T): Promise<T> {
  const res = await fetch(url, { headers: { Accept: 'application/json' } });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText} — ${url}`);
  }
  return parse(await res.json());
}

export async function fetchSymbols(): Promise<SymbolEntry[]> {
  return jsonFetch('/api/symbols', (raw) => SymbolsResponseSchema.parse(raw).symbols);
}

export interface QuotesResult {
  asOf: string;
  quotes: Quote[];
}

export async function fetchQuotes(symbols: string[]): Promise<QuotesResult> {
  if (symbols.length === 0) return { asOf: '', quotes: [] };
  const qs = encodeURIComponent(symbols.join(','));
  return jsonFetch(`/api/quotes?symbols=${qs}`, (raw) => {
    const parsed = QuotesResponseSchema.parse(raw);
    return { asOf: parsed.as_of, quotes: parsed.quotes };
  });
}

export async function fetchHistory(
  symbol: string,
  days: number,
): Promise<HistoricalBar[]> {
  return jsonFetch(
    `/api/history?symbol=${encodeURIComponent(symbol)}&days=${days}`,
    (raw) => HistoryResponseSchema.parse(raw).bars,
  );
}

export async function fetchHoldings(): Promise<Holding[]> {
  return jsonFetch('/api/holdings', (raw) => HoldingsResponseSchema.parse(raw).holdings);
}
