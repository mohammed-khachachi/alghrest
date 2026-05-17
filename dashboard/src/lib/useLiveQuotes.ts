import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchHoldings, fetchQuotes } from '@/lib/api';
import type { Holding, Quote } from '@/types/quotes';
import { useDashboardStore } from '@/store/useStore';

export interface LiveQuotes {
  holdings: Holding[] | undefined;
  quotesBySymbol: Map<string, Quote>;
  asOf: string | undefined;
  holdingsLoading: boolean;
  holdingsError: Error | null;
  quotesLoading: boolean;
  quotesFetching: boolean;
  quotesError: Error | null;
}

/**
 * Shared TanStack Query layer for every Overview panel.
 *
 * - `holdings`: static mock ledger, long staleTime.
 * - `quotes`: one query for the union of (selectedSymbols ∪ holding symbols).
 *   Refetches every 3s. MarketDataPanel, HoldingsPanel, and PortfolioOverview
 *   all share this cache, so a single fetch updates all three panels in lock-step.
 */
export function useLiveQuotes(): LiveQuotes {
  const selectedSymbols = useDashboardStore((s) => s.selectedSymbols);

  const holdingsQ = useQuery({
    queryKey: ['holdings'],
    queryFn: fetchHoldings,
    staleTime: 60 * 60 * 1000,
  });

  const unionSymbols = useMemo(() => {
    const all = new Set<string>();
    holdingsQ.data?.forEach((h) => all.add(h.symbol.toUpperCase()));
    selectedSymbols.forEach((s) => all.add(s.toUpperCase()));
    return Array.from(all).sort();
  }, [holdingsQ.data, selectedSymbols]);

  const quotesQ = useQuery({
    queryKey: ['live-quotes', unionSymbols],
    queryFn: () => fetchQuotes(unionSymbols),
    enabled: unionSymbols.length > 0,
    refetchInterval: 3000,
  });

  const quotesBySymbol = useMemo(() => {
    const m = new Map<string, Quote>();
    quotesQ.data?.quotes.forEach((q) => m.set(q.symbol.toUpperCase(), q));
    return m;
  }, [quotesQ.data]);

  return {
    holdings: holdingsQ.data,
    quotesBySymbol,
    asOf: quotesQ.data?.asOf,
    holdingsLoading: holdingsQ.isLoading,
    holdingsError: (holdingsQ.error as Error | null) ?? null,
    quotesLoading: quotesQ.isLoading,
    quotesFetching: quotesQ.isFetching,
    quotesError: (quotesQ.error as Error | null) ?? null,
  };
}
