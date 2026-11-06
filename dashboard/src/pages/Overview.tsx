import { useLanguage, tr } from "../i18n";
import { useMemo } from 'react';
import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { SymbolSelector } from '@/components/common/SymbolSelector';
import { PnlChart } from '@/components/charts/PnlChart';
import { DrawdownGauge } from '@/components/charts/DrawdownGauge';
import { ExposureBar } from '@/components/charts/ExposureBar';
import { MarketDataPanel } from '@/components/charts/MarketDataPanel';
import { HoldingsPanel } from '@/components/charts/HoldingsPanel';
import { PortfolioOverview } from '@/components/charts/PortfolioOverview';
import {
  DollarSign,
  TrendingUp,
  Briefcase,
  Cpu,
} from 'lucide-react';
import { clsx } from 'clsx';

function fmt(n: number, decimals = 2): string {
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtUsd(n: number): string {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${fmt(n / 1_000_000)}M`;
  if (abs >= 1_000) return `$${fmt(n / 1_000)}K`;
  return `$${fmt(n)}`;
}

interface KpiCardProps {
  label: string;
  value: string;
  sub?: string;
  icon: React.ReactNode;
  positive?: boolean | null;
}

function KpiCard({ label, value, sub, icon, positive }: KpiCardProps) {
  useLanguage();
  return (
    <div className="bg-bg-surface border border-white/8 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-text-muted text-xs font-medium uppercase tracking-wider">
          {tr(label)}
        </span>
        <span className="text-text-muted">{tr(icon)}</span>
      </div>
      <div
        className={clsx(
          'text-2xl font-bold font-mono',
          positive === true && 'text-green-400',
          positive === false && 'text-red-400',
          positive === null && 'text-white',
        )}
      >
        {tr(value)}
      </div>
      {sub && <div className="text-text-muted text-xs">{tr(sub)}</div>}
    </div>
  );
}

export function Overview() {
  useLanguage();
  const portfolio = useDashboardStore((s) => s.portfolioSnapshot);
  const activeAgentCount = useDashboardStore((s) => s.activeAgentCount);
  const openPositions = useDashboardStore((s) => s.openPositions);
  const longExposureGlobal = useDashboardStore((s) => s.longExposure);
  const shortExposureGlobal = useDashboardStore((s) => s.shortExposure);
  const riskLimits = useDashboardStore((s) => s.riskLimits);
  const selectedSymbols = useDashboardStore((s) => s.selectedSymbols);
  const setSelectedSymbols = useDashboardStore((s) => s.setSelectedSymbols);
  const resetSelectedSymbols = useDashboardStore((s) => s.resetSelectedSymbols);

  const drawdownLimit = riskLimits.find((l) => l.name === 'Max Daily Drawdown');
  const varLimit = riskLimits.find((l) => l.name === 'Daily VaR');

  const isFiltered = selectedSymbols.length > 0;

  // When the user has picked symbols, filter positions to those + recompute
  // long/short exposure from the filtered set. Portfolio Value / PnL stay
  // global — the backend doesn't currently expose a per-symbol breakdown.
  const { filteredPositions, longExposure, shortExposure } = useMemo(() => {
    if (!isFiltered) {
      return {
        filteredPositions: openPositions,
        longExposure: longExposureGlobal,
        shortExposure: shortExposureGlobal,
      };
    }
    const picked = new Set(selectedSymbols.map((s) => s.toUpperCase()));
    const filtered = openPositions.filter((p) => picked.has(p.symbol.toUpperCase()));
    let lng = 0;
    let shrt = 0;
    for (const p of filtered) {
      const notional = p.size * p.current_price;
      if (p.side === 'BUY') lng += notional;
      else shrt += notional;
    }
    return { filteredPositions: filtered, longExposure: lng, shortExposure: shrt };
  }, [isFiltered, selectedSymbols, openPositions, longExposureGlobal, shortExposureGlobal]);

  return (
    <div className="p-6 space-y-6">
      {/* Symbol selector */}
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex flex-col">
          <h1 className="text-lg font-semibold">{tr("Overview")}</h1>
          <span className="text-xs text-text-muted">
            {tr(isFiltered
              ? `Filtering positions & exposure by ${selectedSymbols.length} symbol${selectedSymbols.length > 1 ? 's' : ''}.`
              : 'Showing portfolio-wide metrics. Pick symbols to filter and watch live quotes.')}
          </span>
        </div>
        <SymbolSelector value={selectedSymbols} onChange={setSelectedSymbols} />
      </div>

      {/* Portfolio totals — always unfiltered */}
      <ErrorBoundary>
        <PortfolioOverview />
      </ErrorBoundary>

      {/* Holdings grouped by broker — filtered by selection */}
      <ErrorBoundary>
        <HoldingsPanel
          selectedSymbols={selectedSymbols}
          onClearFilter={resetSelectedSymbols}
        />
      </ErrorBoundary>

      {/* Market data panel */}
      <ErrorBoundary>
        <MarketDataPanel symbols={selectedSymbols} />
      </ErrorBoundary>

      {/* KPI Row */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {portfolio ? (
          <>
            <KpiCard
              label={tr("Total PnL Today")}
              value={fmtUsd(portfolio.daily_pnl_usd)}
              sub={`${portfolio.daily_pnl_pct >= 0 ? '+' : ''}${fmt(portfolio.daily_pnl_pct)}% · portfolio-wide`}
              icon={<DollarSign size={16} />}
              positive={portfolio.daily_pnl_usd >= 0}
            />
            <KpiCard
              label={tr("Portfolio Value")}
              value={fmtUsd(portfolio.portfolio_value)}
              sub={`Leverage ${fmt(portfolio.leverage, 1)}× · portfolio-wide`}
              icon={<Briefcase size={16} />}
              positive={null}
            />
          </>
        ) : (
          <>
            <Skeleton className="h-28 rounded-xl" />
            <Skeleton className="h-28 rounded-xl" />
          </>
        )}

        <KpiCard
          label={tr(isFiltered ? 'Filtered Positions' : 'Open Positions')}
          value={String(filteredPositions.length)}
          sub={isFiltered ? `of ${openPositions.length} total` : 'active trades'}
          icon={<TrendingUp size={16} />}
          positive={null}
        />

        <KpiCard
          label={tr("Active Agents")}
          value={`${activeAgentCount} / 32`}
          sub="EMA & ICT logic active"
          icon={<Cpu size={16} />}
          positive={activeAgentCount >= 28}
        />
      </div>

      {/* PnL Chart */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">{tr("YTD Cumulative PnL")}</h2>
          <PnlChart />
        </div>
      </ErrorBoundary>

      {/* Risk Gauges Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ErrorBoundary>
          <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">{tr("Dynamic Max Drawdown")}</h3>
            <DrawdownGauge
              value={drawdownLimit?.current ?? 0}
              max={25}
              warnAt={20}
            />
          </div>
        </ErrorBoundary>

        <ErrorBoundary>
          <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">{tr("Daily VaR")}</h3>
            <DrawdownGauge
              value={varLimit?.current ?? 0}
              max={varLimit?.threshold ?? 5}
              warnAt={(varLimit?.threshold ?? 5) * 0.8}
              unit="%"
              color="#f59e0b"
            />
          </div>
        </ErrorBoundary>

        <ErrorBoundary>
          <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">{tr("Exposure")}{tr(isFiltered ? ' (filtered)' : '')}
            </h3>
            <ExposureBar long={longExposure} short={shortExposure} />
          </div>
        </ErrorBoundary>
      </div>
    </div>
  );
}
