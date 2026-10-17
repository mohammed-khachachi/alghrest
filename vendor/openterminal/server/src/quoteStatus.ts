import type { Quote } from "./providers/yahoo.js";

export type ObservedQuote = Quote & { observation?: {
  schema_version: "quote-observation-v1";
  fetched_at: string;
  cache_state: "fetched" | "cached" | "stale";
  market_state_basis: "provider" | "UNVERIFIED";
} };

/** Capture once with the successful quote; cache hits never advance its clock. */
export function observedQuote(quote: Quote, now = new Date()): ObservedQuote {
  return {...quote, observation:{schema_version:"quote-observation-v1",
    fetched_at:now.toISOString(), cache_state:"fetched",
    // Binance's adapter hardcodes Open; chart/Stooq/FRED have no source state.
    market_state_basis:["nasdaq","yahoo"].includes(quote.source) && !!quote.marketState ? "provider" : "UNVERIFIED"}};
}
export function servedQuote(quote: ObservedQuote, state: "cached" | "stale"): ObservedQuote {
  return quote.observation ? {...quote, observation:{...quote.observation,cache_state:state}} : quote;
}
export function plainQuote({observation: _observation, ...quote}: ObservedQuote): Quote {
  return quote;
}
