import { useLanguage, tr } from "../../i18n";
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { clsx } from 'clsx';
import { AlertCircle, ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { Line, LineChart, ResponsiveContainer, Tooltip } from 'recharts';
import { fetchHistory } from '@/lib/api';
import { useLiveQuotes } from '@/lib/useLiveQuotes';
import {
  ASSET_CLASS_LABEL,
  MARKET_DATA_ANCHOR_DATE,
  type HistoricalBar,
  type Quote,
} from '@/types/quotes';
import { Skeleton } from '@/components/common/Skeleton';

interface Props {
  symbols: string[];
}

const HISTORY_DAYS = 30;

function priceDecimals(q: Quote): number {
  if (q.asset_class === 'forex') return q.symbol.startsWith('XAU') ? 2 : 5;
  if (q.asset_class === 'equity') return 2;
  return q.price < 1 ? 4 : 2;
}

function fmtPrice(value: number, q: Quote): string {
  const d = priceDecimals(q);
  const fixed = value.toFixed(d);
  if (q.asset_class === 'equity') return `$${fixed}`;
  if (q.asset_class === 'forex') return fixed;
  return `$${Number(fixed).toLocaleString('en-US', { maximumFractionDigits: d })}`;
}

function fmtVolume(v: number | null): string {
  if (v == null) return '—';
  if (v >= 1e9) return `${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return v.toFixed(0);
}

function fmtAnchorDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00Z`);
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

function Sparkline({ bars, up }: { bars: HistoricalBar[]; up: boolean }) {
  useLanguage();
  const color = up ? '#4ade80' : '#f87171';
  return (
    <div className="h-14 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={bars} margin={{ top: 2, right: 2, bottom: 2, left: 2 }}>
          <Tooltip
            contentStyle={{
              background: 'rgba(15,18,28,0.95)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 6,
              fontSize: 11,
              padding: '4px 8px',
            }}
            labelStyle={{ color: '#94a3b8', fontSize: 10 }}
            formatter={(value: number) => [value.toFixed(4), 'Close']}
          />
          <Line
            type="monotone"
            dataKey="close"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function QuoteCard({ q }: { q: Quote }) {
  useLanguage();
  const up = q.change_24h_pct > 0;
  const flat = q.change_24h_pct === 0;
  const Icon = flat ? Minus : up ? ArrowUp : ArrowDown;

  const { data: bars } = useQuery({
    queryKey: ['history', q.symbol, HISTORY_DAYS],
    queryFn: () => fetchHistory(q.symbol, HISTORY_DAYS),
    staleTime: 24 * 60 * 60 * 1000, // historical data is deterministic
  });

  return (
    <div className="rounded-xl border border-white/8 bg-bg-surface p-4">
      <div className="flex items-start justify-between">
        <div className="min-w-0">
          <div className="font-mono text-base font-semibold">{q.symbol}</div>
          <div className="text-[10px] uppercase tracking-wider text-text-muted">
            {tr(ASSET_CLASS_LABEL[q.asset_class])}
          </div>
        </div>
        <span
          className={clsx(
            'flex items-center gap-1 rounded-md px-2 py-0.5 font-mono text-xs',
            flat && 'bg-white/5 text-text-muted',
            up && 'bg-green-500/10 text-green-400',
            !flat && !up && 'bg-red-500/10 text-red-400',
          )}
        >
          <Icon size={12} />
          {tr(q.change_24h_pct > 0 ? '+' : '')}
          {tr(q.change_24h_pct.toFixed(2))}%
        </span>
      </div>

      <div className="mt-3 font-mono text-2xl font-bold">{tr(fmtPrice(q.price, q))}</div>

      <div className="mt-3 grid grid-cols-3 gap-x-2 gap-y-1 font-mono text-[11px]">
        <div className="flex flex-col">
          <span className="text-text-muted">{tr("Open")}</span>
          <span>{tr(fmtPrice(q.open, q))}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-text-muted">{tr("High")}</span>
          <span className="text-green-300">{tr(fmtPrice(q.high, q))}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-text-muted">{tr("Low")}</span>
          <span className="text-red-300">{tr(fmtPrice(q.low, q))}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-text-muted">{tr("Bid")}</span>
          <span>{tr(fmtPrice(q.bid, q))}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-text-muted">{tr("Ask")}</span>
          <span>{tr(fmtPrice(q.ask, q))}</span>
        </div>
        <div className="flex flex-col">
          <span className="text-text-muted">{tr("Vol")}</span>
          <span>{tr(fmtVolume(q.volume_24h))}</span>
        </div>
      </div>

      <div className="mt-3 border-t border-white/8 pt-2">
        {bars && bars.length > 0 ? (
          <Sparkline bars={bars} up={up} />
        ) : (
          <Skeleton className="h-14 rounded" />
        )}
        <div className="mt-1 text-center text-[10px] text-text-muted">
          {tr(HISTORY_DAYS)}{tr("d trend")}</div>
      </div>
    </div>
  );
}

export function MarketDataPanel({ symbols }: Props) {
  useLanguage();
  const { quotesBySymbol, asOf, quotesLoading, quotesFetching, quotesError } =
    useLiveQuotes();

  const quotes = useMemo(() => {
    const out: Quote[] = [];
    for (const s of symbols) {
      const q = quotesBySymbol.get(s.toUpperCase());
      if (q) out.push(q);
    }
    return out;
  }, [symbols, quotesBySymbol]);

  if (symbols.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/8 bg-bg-surface p-8 text-center text-sm text-text-muted">{tr("Select one or more symbols above to see live market data.")}</div>
    );
  }

  const asOfLabel = fmtAnchorDate(asOf || MARKET_DATA_ANCHOR_DATE);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <h2 className="text-sm font-medium uppercase tracking-wider text-text-muted">{tr("Market Data")}</h2>
          <span className="text-[11px] text-text-muted">{tr("As of ")}{tr(asOfLabel)}</span>
        </div>
        {quotesFetching && !quotesError && (
          <span className="font-mono text-[10px] text-text-muted">{tr("refreshing…")}</span>
        )}
      </div>

      {quotesError && (
        <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-xs text-amber-300">
          <AlertCircle size={14} className="mt-0.5 shrink-0" />
          <div>{tr("Live quotes unavailable. Start the mock API with")}{tr(' ')}
            <code className="font-mono">{tr("python api/mock_server.py")}</code>{tr(" (or check that it's listening on port 8000).")}<div className="mt-1 text-text-muted">{tr(quotesError.message)}</div>
          </div>
        </div>
      )}

      {!quotesError && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {quotesLoading &&
            quotes.length === 0 &&
            symbols.map((s) => <Skeleton key={s} className="h-72 rounded-xl" />)}
          {quotes.map((q) => <QuoteCard key={q.symbol} q={q} />)}
        </div>
      )}
    </div>
  );
}
