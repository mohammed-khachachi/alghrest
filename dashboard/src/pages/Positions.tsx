import { useState } from 'react';
import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';
import type { OpenPosition, ClosedTrade } from '@/types/ws';

function fmt(n: number, d = 2): string {
  return n.toLocaleString('en-US', {
    minimumFractionDigits: d,
    maximumFractionDigits: d,
  });
}

function fmtUsd(n: number): string {
  const abs = Math.abs(n);
  const s = n < 0 ? '-' : '';
  if (abs >= 1_000_000) return `${s}$${fmt(abs / 1_000_000)}M`;
  if (abs >= 1_000) return `${s}$${fmt(abs / 1_000)}K`;
  return `${s}$${fmt(abs)}`;
}

function formatAge(secs: number): string {
  if (secs < 60) return `${secs}s`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m`;
  return `${Math.floor(secs / 3600)}h ${Math.floor((secs % 3600) / 60)}m`;
}

function SummaryBar({
  long,
  short,
  net,
}: {
  long: number;
  short: number;
  net: number;
}) {
  return (
    <div className="bg-bg-surface border border-white/8 rounded-xl px-5 py-3 flex flex-wrap gap-6 text-sm font-mono">
      <div>
        <span className="text-text-muted text-xs uppercase tracking-wider mr-2">Long</span>
        <span className="text-green-400">{fmtUsd(long)}</span>
      </div>
      <div>
        <span className="text-text-muted text-xs uppercase tracking-wider mr-2">Short</span>
        <span className="text-red-400">{fmtUsd(short)}</span>
      </div>
      <div>
        <span className="text-text-muted text-xs uppercase tracking-wider mr-2">Net Δ</span>
        <span className={net >= 0 ? 'text-green-400' : 'text-red-400'}>{fmtUsd(net)}</span>
      </div>
    </div>
  );
}

function OpenPositionsTable({ positions }: { positions: OpenPosition[] }) {
  const cols = [
    'Symbol', 'Side', 'Size', 'Entry', 'Current', 'Unr. PnL', 'PnL %',
    'Strategy', 'Exchange', 'Age',
  ];

  if (positions.length === 0) {
    return (
      <div className="text-center py-12 text-text-muted text-sm">
        No open positions
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/8">
            {cols.map((c) => (
              <th
                key={c}
                className="px-3 py-2 text-left text-xs font-medium text-text-muted uppercase tracking-wider whitespace-nowrap"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {positions.map((p, i) => (
            <tr
              key={i}
              className={clsx(
                'border-b border-white/4 transition-colors',
                p.unrealized_pnl >= 0
                  ? 'hover:bg-green-950/30'
                  : 'hover:bg-red-950/30',
              )}
            >
              <td className="px-3 py-2 font-mono font-semibold text-white">
                {p.symbol}
              </td>
              <td className="px-3 py-2">
                <span
                  className={clsx(
                    'text-xs px-2 py-0.5 rounded font-mono',
                    p.side === 'BUY'
                      ? 'bg-green-900/50 text-green-400'
                      : 'bg-red-900/50 text-red-400',
                  )}
                >
                  {p.side}
                </span>
              </td>
              <td className="px-3 py-2 font-mono text-right">{fmt(p.size, 4)}</td>
              <td className="px-3 py-2 font-mono text-right">{fmtUsd(p.entry_price)}</td>
              <td className="px-3 py-2 font-mono text-right">{fmtUsd(p.current_price)}</td>
              <td
                className={clsx(
                  'px-3 py-2 font-mono font-semibold text-right',
                  p.unrealized_pnl >= 0 ? 'text-green-400' : 'text-red-400',
                )}
              >
                {p.unrealized_pnl >= 0 ? '+' : ''}
                {fmtUsd(p.unrealized_pnl)}
              </td>
              <td
                className={clsx(
                  'px-3 py-2 font-mono text-right',
                  p.unrealized_pnl_pct >= 0 ? 'text-green-400' : 'text-red-400',
                )}
              >
                {p.unrealized_pnl_pct >= 0 ? '+' : ''}
                {fmt(p.unrealized_pnl_pct)}%
              </td>
              <td className="px-3 py-2 text-text-muted text-xs">{p.strategy}</td>
              <td className="px-3 py-2 text-text-muted text-xs">{p.exchange}</td>
              <td className="px-3 py-2 font-mono text-text-muted text-xs">
                {formatAge(p.age_seconds)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClosedTradesTable({ trades }: { trades: ClosedTrade[] }) {
  const cols = ['Symbol', 'Side', 'Size', 'Entry', 'Exit', 'Realized PnL', 'PnL %', 'Strategy', 'Closed At'];

  if (trades.length === 0) {
    return (
      <div className="text-center py-8 text-text-muted text-sm">No closed trades today</div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-white/8">
            {cols.map((c) => (
              <th
                key={c}
                className="px-3 py-2 text-left text-xs font-medium text-text-muted uppercase tracking-wider whitespace-nowrap"
              >
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {trades.map((t, i) => (
            <tr
              key={i}
              className="border-b border-white/4 hover:bg-white/2 transition-colors opacity-80"
            >
              <td className="px-3 py-2 font-mono text-white">{t.symbol}</td>
              <td className="px-3 py-2">
                <span
                  className={clsx(
                    'text-xs px-2 py-0.5 rounded font-mono',
                    t.side === 'BUY'
                      ? 'bg-green-900/40 text-green-400'
                      : 'bg-red-900/40 text-red-400',
                  )}
                >
                  {t.side}
                </span>
              </td>
              <td className="px-3 py-2 font-mono text-right">{fmt(t.size, 4)}</td>
              <td className="px-3 py-2 font-mono text-right">{fmtUsd(t.entry_price)}</td>
              <td className="px-3 py-2 font-mono text-right">{fmtUsd(t.exit_price)}</td>
              <td
                className={clsx(
                  'px-3 py-2 font-mono font-semibold text-right',
                  t.realized_pnl >= 0 ? 'text-green-400' : 'text-red-400',
                )}
              >
                {t.realized_pnl >= 0 ? '+' : ''}
                {fmtUsd(t.realized_pnl)}
              </td>
              <td
                className={clsx(
                  'px-3 py-2 font-mono text-right',
                  t.pnl_pct >= 0 ? 'text-green-400' : 'text-red-400',
                )}
              >
                {t.pnl_pct >= 0 ? '+' : ''}
                {fmt(t.pnl_pct)}%
              </td>
              <td className="px-3 py-2 text-text-muted text-xs">{t.strategy}</td>
              <td className="px-3 py-2 font-mono text-text-muted text-xs">
                {new Date(t.closed_at).toLocaleTimeString('en-US', { hour12: false })}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Positions() {
  const openPositions = useDashboardStore((s) => s.openPositions);
  const closedTrades = useDashboardStore((s) => s.closedTrades);
  const longExposure = useDashboardStore((s) => s.longExposure);
  const shortExposure = useDashboardStore((s) => s.shortExposure);
  const netDelta = useDashboardStore((s) => s.netDelta);
  const wsStatus = useDashboardStore((s) => s.wsStatus);

  const [closedExpanded, setClosedExpanded] = useState(false);

  return (
    <div className="p-6 space-y-4">
      {/* Summary bar */}
      <SummaryBar long={longExposure} short={shortExposure} net={netDelta} />

      {/* Open positions */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/8 flex items-center justify-between">
            <h2 className="text-sm font-medium text-white">
              Open Positions
              <span className="ml-2 text-xs text-text-muted font-mono">
                ({openPositions.length})
              </span>
            </h2>
          </div>
          {wsStatus === 'connecting' && openPositions.length === 0 ? (
            <div className="p-4 space-y-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-8 rounded" />
              ))}
            </div>
          ) : (
            <OpenPositionsTable positions={openPositions} />
          )}
        </div>
      </ErrorBoundary>

      {/* Closed trades (collapsible) */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl overflow-hidden">
          <button
            onClick={() => setClosedExpanded((v) => !v)}
            className="w-full px-5 py-3 border-b border-white/8 flex items-center justify-between hover:bg-white/2 transition-colors"
          >
            <h2 className="text-sm font-medium text-white">
              Closed Trades Today
              <span className="ml-2 text-xs text-text-muted font-mono">
                ({closedTrades.length})
              </span>
            </h2>
            {closedExpanded ? (
              <ChevronDown size={16} className="text-text-muted" />
            ) : (
              <ChevronRight size={16} className="text-text-muted" />
            )}
          </button>
          {closedExpanded && <ClosedTradesTable trades={closedTrades} />}
        </div>
      </ErrorBoundary>
    </div>
  );
}
