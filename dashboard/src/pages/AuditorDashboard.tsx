import { useLanguage, tr } from "../i18n";
import { useEffect, useState } from 'react';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { clsx } from 'clsx';
import { Activity, ShieldCheck } from 'lucide-react';

interface AgentAudit {
  agent_id: number;
  sharpe: number;
  sortino: number;
  mdd: number;
  win_loss: number;
  profit_factor: number;
  latency_ms: number;
  volatility_pct: number;
  health_score: number;
  last_audit_timestamp: string;
}

// Dummy data generator to mimic Redis fetch
const generateDummyAudits = (): AgentAudit[] => {
  return Array.from({ length: 32 }, (_, i) => ({
    agent_id: i + 1,
    sharpe: 0.5 + Math.random() * 2.5,
    sortino: 0.8 + Math.random() * 3.0,
    mdd: -(Math.random() * 25),
    win_loss: 0.8 + Math.random() * 1.5,
    profit_factor: 0.9 + Math.random() * 2.0,
    latency_ms: 5 + Math.random() * 45,
    volatility_pct: 10 + Math.random() * 30,
    health_score: Math.floor(40 + Math.random() * 60),
    last_audit_timestamp: new Date().toISOString()
  })).sort((a, b) => b.health_score - a.health_score);
};

export function AuditorDashboard() {
  useLanguage();
  const [audits, setAudits] = useState<AgentAudit[]>([]);
  const [isAuditing, setIsAuditing] = useState(false);

  useEffect(() => {
    // In production, this would subscribe to the WS or fetch from FastAPI
    setAudits(generateDummyAudits());
    const interval = setInterval(() => setAudits(generateDummyAudits()), 5000);
    return () => clearInterval(interval);
  }, []);

  const handleRunAudit = () => {
    setIsAuditing(true);
    // Simulate Kafka system.audit.request trigger
    setTimeout(() => {
      setAudits(generateDummyAudits());
      setIsAuditing(false);
    }, 1500);
  };

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <ShieldCheck className="text-indigo-400" size={28} />{tr("System Audit & Validation")}</h1>
          <p className="text-sm text-text-muted mt-1">{tr("2026 YTD Multi-Agent Performance Leaderboard by Agent #33 (Auditor)")}{audits.length > 0 && (
              <span className="ml-3 pl-3 border-l border-white/20 text-indigo-300">{tr("Last YTD Test Completed: ")}{tr(new Date(audits[0].last_audit_timestamp).toLocaleTimeString())}
              </span>
            )}
          </p>
        </div>
        <button 
          onClick={handleRunAudit}
          disabled={isAuditing}
          className={clsx(
            "text-white px-4 py-2 rounded-lg text-sm font-medium flex items-center gap-2 transition-colors",
            isAuditing ? "bg-indigo-500/50 cursor-not-allowed" : "bg-indigo-600 hover:bg-indigo-700"
          )}
        >
          <Activity size={16} className={isAuditing ? "animate-spin" : ""} />
          {tr(isAuditing ? 'Running Walk-Forward...' : 'Run Manual Audit')}
        </button>
      </div>

      <ErrorBoundary>
        <div className="bg-bg-surface border border-white/8 rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm text-start">
              <thead className="text-xs text-text-muted uppercase bg-black/20 border-b border-white/8">
                <tr>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Agent ID")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Health Score")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Sharpe / Sortino")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Profit Factor")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Volatility (YTD)")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Dynamic Max Drawdown")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("W/L Ratio")}</th>
                  <th className="px-6 py-4 font-semibold tracking-wider">{tr("Latency")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/4">
                {audits.map((audit) => (
                  <tr key={audit.agent_id} className="hover:bg-white/4 transition-colors">
                    <td className="px-6 py-4 font-mono text-white">{tr("AGT-")}{tr(String(audit.agent_id).padStart(2, '0'))}
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-2">
                        <div className="w-16 h-1.5 bg-gray-800 rounded-full overflow-hidden">
                          <div 
                            className={clsx(
                              "h-full rounded-full",
                              audit.health_score >= 80 ? "bg-green-400" : audit.health_score >= 60 ? "bg-amber-400" : "bg-red-400"
                            )}
                            style={{ width: `${audit.health_score}%` }}
                          />
                        </div>
                        <span className="font-mono text-xs text-text-muted">{tr(audit.health_score)}%</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 font-mono">
                      <span className={clsx(audit.sharpe >= 1.5 ? "text-green-400" : "text-white")}>
                        {tr(audit.sharpe.toFixed(2))}
                      </span>
                      <span className="text-text-muted mx-1">/</span>
                      <span className={clsx(audit.sortino >= 2.0 ? "text-green-400" : "text-white")}>
                        {tr(audit.sortino.toFixed(2))}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className={clsx(
                        "font-mono px-2 py-1 rounded text-xs",
                        audit.profit_factor >= 1.2 ? "bg-green-900/30 text-green-400" : "bg-red-900/30 text-red-400 animate-pulse"
                      )}>
                        {tr(audit.profit_factor.toFixed(2))}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono text-text-muted">
                      {tr(audit.volatility_pct.toFixed(1))}%
                    </td>
                    <td className="px-6 py-4 font-mono text-red-400">
                      {tr(audit.mdd.toFixed(1))}%
                    </td>
                    <td className="px-6 py-4 font-mono text-text-muted">
                      {tr(audit.win_loss.toFixed(2))}
                    </td>
                    <td className="px-6 py-4 font-mono text-text-muted">
                      {tr(audit.latency_ms.toFixed(1))}{tr(" ms")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </ErrorBoundary>
    </div>
  );
}
