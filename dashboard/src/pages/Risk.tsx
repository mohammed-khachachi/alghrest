import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { CorrelationHeatmap } from '@/components/risk/CorrelationHeatmap';
import { AlertTriangle, Info, XOctagon } from 'lucide-react';
import { clsx } from 'clsx';
import type { RiskAlert, RiskLimit } from '@/types/ws';

function SeverityIcon({ severity }: { severity: string }) {
  if (severity === 'CRITICAL') return <XOctagon size={14} className="text-red-400 flex-shrink-0" />;
  if (severity === 'WARNING') return <AlertTriangle size={14} className="text-amber-400 flex-shrink-0" />;
  return <Info size={14} className="text-blue-400 flex-shrink-0" />;
}

function AlertRow({ alert }: { alert: RiskAlert }) {
  return (
    <div
      className={clsx(
        'flex items-start gap-3 px-4 py-3 border-b border-white/4 text-sm',
        alert.severity === 'CRITICAL' && 'bg-red-950/20',
        alert.severity === 'WARNING' && 'bg-amber-950/10',
      )}
    >
      <SeverityIcon severity={alert.severity} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-0.5 flex-wrap">
          <span
            className={clsx(
              'text-xs font-mono px-1.5 py-0.5 rounded',
              alert.severity === 'CRITICAL' && 'bg-red-900/50 text-red-400',
              alert.severity === 'WARNING' && 'bg-amber-900/50 text-amber-400',
              alert.severity === 'INFO' && 'bg-blue-900/50 text-blue-400',
            )}
          >
            {alert.severity}
          </span>
          <span className="text-xs text-text-muted font-mono">
            {new Date(alert.timestamp).toLocaleTimeString('en-US', { hour12: false })}
          </span>
          <span className="text-xs text-indigo-400">{alert.affected_agent}</span>
        </div>
        <p className="text-white leading-snug">{alert.message}</p>
        <div className="text-xs text-text-muted mt-0.5 font-mono">
          triggered: {alert.triggered_value.toFixed(2)} / threshold: {alert.threshold_value.toFixed(2)}
        </div>
      </div>
    </div>
  );
}

function RiskLimitsTable({ limits }: { limits: RiskLimit[] }) {
  if (limits.length === 0) {
    return (
      <div className="p-4 space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 rounded" />
        ))}
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-white/8">
          {['Limit', 'Current', 'Threshold', 'Usage', 'Status'].map((h) => (
            <th
              key={h}
              className="px-4 py-2 text-left text-xs font-medium text-text-muted uppercase tracking-wider"
            >
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {limits.map((limit) => (
          <tr key={limit.name} className="border-b border-white/4 hover:bg-white/2">
            <td className="px-4 py-2 text-white font-medium">{limit.name}</td>
            <td className="px-4 py-2 font-mono">
              {limit.current.toFixed(2)}{limit.unit}
            </td>
            <td className="px-4 py-2 font-mono text-text-muted">
              {limit.threshold.toFixed(2)}{limit.unit}
            </td>
            <td className="px-4 py-2 w-40">
              <div className="flex items-center gap-2">
                <div className="flex-1 h-2 bg-white/8 rounded-full overflow-hidden">
                  <div
                    className={clsx(
                      'h-full rounded-full transition-all duration-500',
                      limit.status === 'OK' && 'bg-green-500',
                      limit.status === 'WARNING' && 'bg-amber-500',
                      limit.status === 'BREACHED' && 'bg-red-500',
                    )}
                    style={{ width: `${Math.min(limit.pct, 100)}%` }}
                  />
                </div>
                <span className="font-mono text-xs text-text-muted w-10 text-right">
                  {limit.pct.toFixed(0)}%
                </span>
              </div>
            </td>
            <td className="px-4 py-2">
              <span
                className={clsx(
                  'text-xs px-2 py-0.5 rounded font-mono',
                  limit.status === 'OK' && 'bg-green-900/50 text-green-400',
                  limit.status === 'WARNING' && 'bg-amber-900/50 text-amber-400',
                  limit.status === 'BREACHED' && 'bg-red-900/50 text-red-400',
                )}
              >
                {limit.status}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Risk() {
  const riskAlerts = useDashboardStore((s) => s.riskAlerts);
  const riskLimits = useDashboardStore((s) => s.riskLimits);

  return (
    <div className="p-6 space-y-6">
      {/* Risk alerts feed */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/8 flex items-center justify-between">
            <h2 className="text-sm font-medium text-white">
              Risk Alerts
              <span className="ml-2 text-xs text-text-muted font-mono">
                (newest first)
              </span>
            </h2>
            {riskAlerts.some((a) => a.severity === 'CRITICAL') && (
              <span className="text-xs bg-red-900/70 text-red-300 px-2 py-0.5 rounded font-mono animate-pulse">
                CRITICAL ACTIVE
              </span>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {riskAlerts.length === 0 ? (
              <div className="text-center py-10 text-text-muted text-sm">
                No alerts — system nominal
              </div>
            ) : (
              riskAlerts.map((alert) => (
                <AlertRow key={alert.alert_id} alert={alert} />
              ))
            )}
          </div>
        </div>
      </ErrorBoundary>

      {/* Risk limits table */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl overflow-hidden">
          <div className="px-5 py-3 border-b border-white/8">
            <h2 className="text-sm font-medium text-white">Risk Limits</h2>
          </div>
          <div className="overflow-x-auto">
            <RiskLimitsTable limits={riskLimits} />
          </div>
        </div>
      </ErrorBoundary>

      {/* Correlation heatmap */}
      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl p-6">
          <h2 className="text-sm font-medium text-text-muted uppercase tracking-wider mb-4">
            Strategy Correlation Heatmap
          </h2>
          <CorrelationHeatmap />
        </div>
      </ErrorBoundary>
    </div>
  );
}
