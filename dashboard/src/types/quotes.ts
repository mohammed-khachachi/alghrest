import { z } from 'zod';

export const AssetClassSchema = z.enum(['crypto', 'forex', 'equity']);
export type AssetClass = z.infer<typeof AssetClassSchema>;

export const SymbolEntrySchema = z.object({
  symbol: z.string(),
  name: z.string(),
  asset_class: AssetClassSchema,
});
export type SymbolEntry = z.infer<typeof SymbolEntrySchema>;

export const SymbolsResponseSchema = z.object({
  symbols: z.array(SymbolEntrySchema),
});

export const QuoteSchema = z.object({
  symbol: z.string(),
  asset_class: AssetClassSchema,
  price: z.number(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  change_24h_pct: z.number(),
  bid: z.number(),
  ask: z.number(),
  volume_24h: z.number().nullable(),
  ts: z.string(),
});
export type Quote = z.infer<typeof QuoteSchema>;

export const QuotesResponseSchema = z.object({
  as_of: z.string(),
  quotes: z.array(QuoteSchema),
});

export const HistoricalBarSchema = z.object({
  date: z.string(),
  open: z.number(),
  high: z.number(),
  low: z.number(),
  close: z.number(),
  volume: z.number().nullable(),
});
export type HistoricalBar = z.infer<typeof HistoricalBarSchema>;

export const HistoryResponseSchema = z.object({
  symbol: z.string(),
  as_of: z.string(),
  bars: z.array(HistoricalBarSchema),
});

export const MARKET_DATA_ANCHOR_DATE = '2025-05-11';

export const HoldingSchema = z.object({
  symbol: z.string(),
  broker: z.string(),
  asset_class: AssetClassSchema,
  side: z.enum(['BUY', 'SELL']),
  volume: z.number(),
  entry_price: z.number(),
  opened_at: z.string(),
});
export type Holding = z.infer<typeof HoldingSchema>;

export const HoldingsResponseSchema = z.object({
  as_of: z.string(),
  holdings: z.array(HoldingSchema),
});

export const ASSET_CLASS_LABEL: Record<AssetClass, string> = {
  crypto: 'Crypto',
  forex: 'Forex',
  equity: 'Equities',
};

// Mirrors connectors/data_providers/router.py::_CATALOG. Used as a fallback
// when /api/symbols is unreachable so the dropdown stays usable in offline
// dashboard development. Keep in sync if you add symbols on the backend.
export const FALLBACK_SYMBOL_CATALOG: SymbolEntry[] = [
  { symbol: 'BTC', name: 'Bitcoin', asset_class: 'crypto' },
  { symbol: 'ETH', name: 'Ethereum', asset_class: 'crypto' },
  { symbol: 'SOL', name: 'Solana', asset_class: 'crypto' },
  { symbol: 'BNB', name: 'Binance Coin', asset_class: 'crypto' },
  { symbol: 'XRP', name: 'Ripple', asset_class: 'crypto' },
  { symbol: 'ADA', name: 'Cardano', asset_class: 'crypto' },
  { symbol: 'DOGE', name: 'Dogecoin', asset_class: 'crypto' },
  { symbol: 'AVAX', name: 'Avalanche', asset_class: 'crypto' },
  { symbol: 'EUR/USD', name: 'Euro / US Dollar', asset_class: 'forex' },
  { symbol: 'GBP/USD', name: 'British Pound / US Dollar', asset_class: 'forex' },
  { symbol: 'USD/JPY', name: 'US Dollar / Japanese Yen', asset_class: 'forex' },
  { symbol: 'USD/CHF', name: 'US Dollar / Swiss Franc', asset_class: 'forex' },
  { symbol: 'AUD/USD', name: 'Australian Dollar / US Dollar', asset_class: 'forex' },
  { symbol: 'USD/CAD', name: 'US Dollar / Canadian Dollar', asset_class: 'forex' },
  { symbol: 'XAU/USD', name: 'Gold (Spot)', asset_class: 'forex' },
  { symbol: 'XAG/USD', name: 'Silver (Spot)', asset_class: 'forex' },
  { symbol: 'AAPL', name: 'Apple Inc.', asset_class: 'equity' },
  { symbol: 'MSFT', name: 'Microsoft Corp.', asset_class: 'equity' },
  { symbol: 'GOOGL', name: 'Alphabet Inc. Class A', asset_class: 'equity' },
  { symbol: 'AMZN', name: 'Amazon.com Inc.', asset_class: 'equity' },
  { symbol: 'META', name: 'Meta Platforms Inc.', asset_class: 'equity' },
  { symbol: 'TSLA', name: 'Tesla Inc.', asset_class: 'equity' },
  { symbol: 'NVDA', name: 'NVIDIA Corp.', asset_class: 'equity' },
  { symbol: 'JPM', name: 'JPMorgan Chase & Co.', asset_class: 'equity' },
];
