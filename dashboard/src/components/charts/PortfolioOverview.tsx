import { useLanguage, tr } from "../../i18n";
import { useMemo } from 'react';
import { clsx } from 'clsx';
import {
  DollarSign,
  Percent,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react';
import { useLiveQuotes } from '@/lib/useLiveQuotes';
import { Skeleton } from '@/components/common/Skeleton';

function fmtUsd(n: number, signed = false): string {
  const sign = signed && n > 0 ? '+' : n < 0 ? '-' : '';
  return `${sign}$${Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

function fmtPct(n: number): string {
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
}

interface KpiProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  tone?: 'neutral' | 'positive' | 'negative';
}

function Kpi({ label, value, sub, icon, tone = 'neutral' }: KpiProps) {
  useLanguage();
  return (
    <div className="flex flex-col gap-3 rounded-xl border border-white/8 bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wider text-text-muted">
          {tr(label)}
        </span>
        <span className="text-text-muted">{tr(icon)}</span>
      </div>
      <div
        className={clsx(
          'font-mono text-2xl font-bold',
          tone === 'positive' && 'text-green-400',
          tone === 'negative' && 'text-red-400',
          tone === 'neutral' && 'text-white',
        )}
      >
        {tr(value)}
      </div>
      {sub && <div className="text-[11px] text-text-muted">{tr(sub)}</div>}
    </div>
  );
}

/**
 * Always-unfiltered roll-up of every holding.
 * Independent of the symbol selector so users always see the full picture.
 */
export function PortfolioOverview() {
  useLanguage();
  const { holdings, quotesBySymbol, holdingsLoading, quotesLoading } = useLiveQuotes();

  const totals = useMemo(() => {
    if (!holdings) return null;
    let invested = 0;
    let current = 0;
    let hasAll = true;
    for (const h of holdings) {
      invested += h.volume * h.entry_price;
      const q = quotesBySymbol.get(h.symbol.toUpperCase());
      if (!q) hasAll = false;
      else current += h.volume * q.price;
    }
    const pnl = current - invested;
    const pnlPct = invested > 0 ? (pnl / invested) * 100 : 0;
    return { invested, current, pnl, pnlPct, hasAll, count: holdings.length };
  }, [holdings, quotesBySymbol]);

  if (holdingsLoading || (quotesLoading && quotesBySymbol.size === 0) || !totals) {
    return (
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}
      </div>
    );
  }

  const tone =
    totals.pnl > 0 ? 'positive' : totals.pnl < 0 ? 'negative' : 'neutral';
  const PnlIcon = totals.pnl >= 0 ? TrendingUp : TrendingDown;
  const subAll = `Across all ${totals.count} holdings`;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium uppercase tracking-wider text-text-muted">{tr("Portfolio Overview")}</h2>
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        <Kpi
          label={tr("Total Invested")}
          value={fmtUsd(totals.invested)}
          sub={subAll}
          icon={<Wallet size={16} />}
        />
        <Kpi
          label={tr("Current Value")}
          value={totals.hasAll ? fmtUsd(totals.current) : '—'}
          sub={subAll}
          icon={<DollarSign size={16} />}
        />
        <Kpi
          label={tr("P&L (USD)")}
          value={totals.hasAll ? fmtUsd(totals.pnl, true) : '—'}
          sub={subAll}
          icon={<PnlIcon size={16} />}
          tone={tone}
        />
        <Kpi
          label={tr("P&L (%)")}
          value={totals.hasAll ? fmtPct(totals.pnlPct) : '—'}
          sub={subAll}
          icon={<Percent size={16} />}
          tone={tone}
        />
      </div>
    </div>
  );
}
