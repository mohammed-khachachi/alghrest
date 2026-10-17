import { cacheGet, cacheStore, staleGet } from "./cache.js";
import type { Candle } from "./providers/yahoo.js";

export type HistorySeries = {
  candles: Candle[];
  provider: "nasdaq" | "yahoo" | "stooq" | "binance" | "fred";
  interval: string | null;
};
type Snapshot = HistorySeries & { fetched_at: string };

/** Cache provenance together with the exact series; refresh failures keep its original clock. */
export async function historyResponse(symbol: string, range: string, ttl: number, load: () => Promise<HistorySeries>) {
  const key = `history-status:${symbol}:${range}`;
  let snapshot = cacheGet<Snapshot>(key);
  let cache_state: "fetched" | "cached" | "stale" = "cached";
  if (!snapshot) {
    try {
      const series = await load();
      if (!Array.isArray(series.candles) || !series.candles.length) throw new Error("empty history");
      snapshot = { ...series, fetched_at: new Date().toISOString() };
      cacheStore(key, snapshot, ttl);
      cache_state = "fetched";
    } catch (error) {
      snapshot = staleGet<Snapshot>(key);
      if (!snapshot) throw error;
      cache_state = "stale";
    }
  }
  return {
    candles: snapshot.candles,
    metadata: {
      schema_version: "openterminal-history-v1" as const,
      symbol, requested_range: range, provider: snapshot.provider,
      interval: snapshot.interval,
      interval_basis: snapshot.interval ? "provider_request" : "UNVERIFIED",
      fetched_at: snapshot.fetched_at, cache_state,
    },
  };
}

/** Empty provider responses must allow the next fallback to run. */
export async function historySeries(provider: HistorySeries["provider"], interval: string | null, load: () => Promise<Candle[]>): Promise<HistorySeries> {
  const candles = await load();
  if (!Array.isArray(candles) || !candles.length) throw new Error(`${provider}: empty history`);
  return { candles, provider, interval };
}
