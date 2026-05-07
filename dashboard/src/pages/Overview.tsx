import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { PnlChart } from '@/components/charts/PnlChart';
import { DrawdownGauge } from '@/components/charts/DrawdownGauge';
import { ExposureBar } from '@/components/charts/ExposureBar';
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
    <div className="bg-bg-surface border border-white/8 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-text-muted text-xs font-medium uppercase tracking-wider">
          {label}
        </span>
        <span className="text-text-muted">{icon}</span>
      </div>
      <div
        className={clsx(
          'text-2xl font-bold font-mono',
          positive === true && 'text-green-400',
          positive === false && 'text-red-400',
          positive === null && 'text-white',
        )}
      >
        {value}
      </div>
      {sub && <div className="text-text-muted text-xs">{sub}</div>}
    </div>
  );
}

export function Overview() {
  const portfolio = useDashboardStore((s) => s.portfolioSnapshot);
  const activeAgentCount = useDashboardStore((s) => s.activeAgentCount);
  const openPositions = useDashboardStore((s) => s.openPositions);
  const longExposure = useDashboardStore((s) => s.longExposure);
  const shortExposure = useDashboardStore((s) => s.shortExposure);
  const riskLimits = useDashboardStore((s) => s.riskLimits);

  const drawdownLimit = riskLimits.find((l) => l.name === 'Max Daily Drawdown');
  const varLimit = riskLimits.find((l) => l.name === 'Daily VaR');

  return (
    <div className="p-6 space-y-6">
      {/* KPI Row */}
      <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
        {portfolio ? (
          <>
            <KpiCard
              label="Total PnL Today"
              value={fmtUsd(portfolio.daily_pnl_usd)}
              sub={`${portfolio.daily_pnl_pct >= 0 ? '+' : ''}${fmt(portfolio.daily_pnl_pct)}%`}
              icon={<DollarSign size={16} />}
              positive={portfolio.daily_pnl_usd >= 0}
            />
            <KpiCard
              label="Portfolio Value"
              value={fmtUsd(portfolio.portfolio_value)}
              sub={`Leverage ${fmt(portfolio.leverage, 1)}×`}
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
          label="Open Positions"
          value={String(openPositions.length)}
          sub="active trades"
          icon={<TrendingUp size={16} />}
          positive={null}
        />

        <KpiCard
          label="Active Agents"
          value={`${activeAgentCount} / 32`}
          sub="online now"
          icon={<Cpu size={16} />}
          positive={activeAgentCount >= 28}
        />
      </div>

      {/* PnL Chart */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">
            Cumulative PnL — Intraday
          </h2>
          <PnlChart />
        </div>
      </ErrorBoundary>

      {/* Risk Gauges Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <ErrorBoundary>
          <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">
              Drawdown
            </h3>
            <DrawdownGauge
              value={drawdownLimit?.current ?? 0}
              max={25}
              warnAt={20}
            />
          </div>
        </ErrorBoundary>

        <ErrorBoundary>
          <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">
              Daily VaR
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
          <div className="bg-bg-surface border border-white/8 rounded-xl p-4">
            <h3 className="text-xs text-text-muted uppercase tracking-wider mb-3">
              Exposure
            </h3>
            <ExposureBar long={longExposure} short={shortExposure} />
          </div>
        </ErrorBoundary>
      </div>
    </div>
  );
}
