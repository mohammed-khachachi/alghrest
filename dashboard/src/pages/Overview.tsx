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
  return (
    <div className="glass hover:bg-bg-elevated/30 hover:border-white/12 transition-all duration-300 rounded-xl p-5 flex flex-col gap-3 group relative overflow-hidden">
      {/* Decorative gradient radial glow */}
      <div className="absolute -right-4 -top-4 w-20 h-20 bg-white/2 rounded-full blur-xl group-hover:bg-white/5 transition-all duration-500 pointer-events-none" />
      <div className="flex items-center justify-between z-10">
        <span className="text-white/50 text-[10px] font-bold uppercase tracking-wider font-sans">
          {label}
        </span>
        <span className="text-white/40 group-hover:text-white/80 transition-colors duration-300">{icon}</span>
      </div>
      <div
        className={clsx(
          'text-2xl font-bold font-mono tracking-tight z-10 transition-transform duration-300 group-hover:translate-x-1',
          positive === true && 'text-profit',
          positive === false && 'text-loss',
          positive === null && 'text-white',
        )}
      >
        {value}
      </div>
      {sub && <div className="text-white/40 text-[11px] z-10 font-sans tracking-wide leading-none">{sub}</div>}
    </div>
  );
}

export function Overview() {
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
      {/* Premium Glassmorphic Welcome Header Banner */}
      <div className="relative overflow-hidden rounded-2xl glass p-6 flex flex-col md:flex-row md:items-center justify-between gap-6 bg-gradient-to-r from-bg-card to-bg-surface/90 border border-white/6">
        <div className="absolute top-0 right-0 w-64 h-64 bg-white/2 rounded-full blur-3xl pointer-events-none" />
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="bg-profit/10 text-profit text-[10px] font-bold px-2 py-0.5 rounded-full border border-profit/20 flex items-center gap-1 font-mono uppercase">
              <span className="w-1.5 h-1.5 rounded-full bg-profit animate-pulse" />
              Live Feed
            </span>
            <span className="text-white/40 font-mono text-xs">v0.2.1 Stable</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight bg-gradient-to-r from-white to-white/70 bg-clip-text text-transparent">
            System Overview
          </h1>
          <p className="text-xs text-white/50 max-w-xl font-sans tracking-wide">
            {isFiltered
              ? `Filtering positions and sleeve exposures by ${selectedSymbols.length} active symbols. Dynamic quotes updating live.`
              : 'Autonomous multi-agent portfolio dashboard. Monitor real-time performance, active strategy sleeves, and integrated risk guards.'}
          </p>
        </div>
        
        <div className="flex items-center gap-3">
          <SymbolSelector value={selectedSymbols} onChange={setSelectedSymbols} />
          {isFiltered && (
            <button
              onClick={resetSelectedSymbols}
              className="text-xs px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 text-white/80 border border-white/10 transition-colors font-mono"
            >
              Reset
            </button>
          )}
        </div>
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
              label="Total PnL Today"
              value={fmtUsd(portfolio.daily_pnl_usd)}
              sub={`${portfolio.daily_pnl_pct >= 0 ? '+' : ''}${fmt(portfolio.daily_pnl_pct)}% · portfolio-wide`}
              icon={<DollarSign size={16} />}
              positive={portfolio.daily_pnl_usd >= 0}
            />
            <KpiCard
              label="Portfolio Value"
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
          label={isFiltered ? 'Filtered Positions' : 'Open Positions'}
          value={String(filteredPositions.length)}
          sub={isFiltered ? `of ${openPositions.length} total` : 'active trades'}
          icon={<TrendingUp size={16} />}
          positive={null}
        />

        <KpiCard
          label="Active Agents"
          value={`${activeAgentCount} / 32`}
          sub="Executive, Quant & Execution active"
          icon={<Cpu size={16} />}
          positive={activeAgentCount >= 28}
        />
      </div>

      {/* PnL Chart */}
      <ErrorBoundary>
        <div className="glass border border-white/6 rounded-xl p-5 bg-bg-card/45 relative overflow-hidden">
          <div className="absolute top-0 left-0 w-full h-[1px] bg-gradient-to-r from-transparent via-white/10 to-transparent" />
          <h2 className="text-xs font-bold text-white/50 uppercase tracking-widest mb-4 font-sans">
            YTD Cumulative PnL Curve
          </h2>
          <PnlChart />
        </div>
      </ErrorBoundary>

      {/* Risk Gauges Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ErrorBoundary>
          <div className="glass border border-white/6 rounded-xl p-5 bg-bg-card/45">
            <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-wider mb-3">
              Dynamic Max Drawdown
            </h3>
            <DrawdownGauge
              value={drawdownLimit?.current ?? 0}
              max={25}
              warnAt={20}
            />
          </div>
        </ErrorBoundary>

        <ErrorBoundary>
          <div className="glass border border-white/6 rounded-xl p-5 bg-bg-card/45">
            <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-wider mb-3">
              Daily Value at Risk (VaR)
            </h3>
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
          <div className="glass border border-white/6 rounded-xl p-5 bg-bg-card/45">
            <h3 className="text-[10px] font-bold text-white/50 uppercase tracking-wider mb-3">
              Asset Class Exposure{isFiltered ? ' (filtered)' : ''}
            </h3>
            <ExposureBar long={longExposure} short={shortExposure} />
          </div>
        </ErrorBoundary>
      </div>
    </div>
  );
}

