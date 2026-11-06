import { useLanguage, tr } from "../i18n";
import { useState, useMemo } from 'react';
import { useDashboardStore } from '@/store/useStore';
import { Skeleton } from '@/components/common/Skeleton';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { AgentDetailModal } from '@/components/agents/AgentDetailModal';
import { AGENT_ROSTER, TIER_COLORS, type AgentHeartbeat } from '@/types/ws';
import { clsx } from 'clsx';
import { Clock, MemoryStick, Activity } from 'lucide-react';

type FilterTier = 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7;
type FilterStatus = 'ALL' | 'RUNNING' | 'DEGRADED' | 'ERROR' | 'PAUSED';

function StatusDot({ status }: { status: string }) {
  useLanguage();
  return (
    <span
      className={clsx(
        'inline-block w-2 h-2 rounded-full flex-shrink-0',
        status === 'RUNNING' && 'bg-green-400 shadow-[0_0_6px_#4ade80]',
        status === 'DEGRADED' && 'bg-amber-400 shadow-[0_0_6px_#fbbf24]',
        (status === 'ERROR' || status === 'SHUTDOWN') && 'bg-red-400 shadow-[0_0_6px_#f87171]',
        (status === 'PAUSED' || status === 'INITIALIZING') && 'bg-slate-400',
      )}
    />
  );
}

function AgentCard({
  beat,
  onClick,
}: {
  beat: AgentHeartbeat;
  onClick: () => void;
}) {
  useLanguage();
  const tierColor = TIER_COLORS[beat.tier] ?? '#64748b';

  return (
    <button
      onClick={onClick}
      className={clsx(
        'bg-bg-surface border border-white/8 rounded-xl p-4 text-start',
        'hover:border-white/20 hover:bg-white/4 transition-all duration-200',
        'focus:outline-none focus:ring-2 focus:ring-indigo-500/50',
        'relative overflow-hidden',
      )}
    >
      {/* Tier color accent */}
      <div
        className="absolute top-0 left-0 w-full h-0.5 rounded-t-xl"
        style={{ backgroundColor: tierColor }}
      />

      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <StatusDot status={beat.status} />
            <span className="font-mono text-xs text-text-muted">{tr("AGT-")}{tr(String(beat.agent_id).padStart(2, '0'))}
            </span>
            <span
              className="text-xs px-1.5 py-0.5 rounded font-mono"
              style={{ backgroundColor: `${tierColor}20`, color: tierColor }}
            >{tr("T")}{tr(beat.tier)}
            </span>
          </div>
          <h3 className="text-sm font-semibold text-white truncate">
            {tr(beat.agent_name)}
          </h3>
        </div>
        <span
          className={clsx(
            'text-xs font-mono px-2 py-0.5 rounded flex-shrink-0',
            beat.status === 'RUNNING' && 'bg-green-900/50 text-green-400',
            beat.status === 'DEGRADED' && 'bg-amber-900/50 text-amber-400',
            beat.status === 'ERROR' && 'bg-red-900/50 text-red-400',
            beat.status === 'PAUSED' && 'bg-slate-700/50 text-slate-400',
            beat.status === 'INITIALIZING' && 'bg-indigo-900/50 text-indigo-400',
            beat.status === 'SHUTDOWN' && 'bg-red-900/50 text-red-400',
          )}
        >
          {tr(beat.status)}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
        <div className="flex items-center gap-1.5 text-text-muted">
          <Activity size={11} />
          <span className="font-mono">{tr(beat.messages_processed.toLocaleString())}</span>
          <span>{tr("msgs")}</span>
        </div>
        <div className="flex items-center gap-1.5 text-text-muted">
          <Clock size={11} />
          <span className="font-mono">{tr(beat.last_heartbeat_secs)}{tr("s")}</span>
          <span>{tr("ago")}</span>
        </div>
        <div className="flex items-center gap-1.5 text-text-muted">
          <MemoryStick size={11} />
          <span className="font-mono">{tr(beat.memory_mb.toFixed(0))}{tr(" MB")}</span>
        </div>
        <div
          className={clsx(
            'flex items-center gap-1.5',
            beat.error_rate_pct > 5 ? 'text-red-400' : 'text-text-muted',
          )}
        >
          <span className="font-mono">{tr(beat.error_rate_pct.toFixed(1))}%</span>
          <span>{tr("err")}</span>
        </div>
      </div>
    </button>
  );
}

function AgentCardSkeleton() {
  useLanguage();
  return (
    <div className="bg-bg-surface border border-white/8 rounded-xl p-4 space-y-3">
      <Skeleton className="h-4 w-2/3 rounded" />
      <Skeleton className="h-3 w-full rounded" />
      <Skeleton className="h-3 w-4/5 rounded" />
    </div>
  );
}

export function Agents() {
  useLanguage();
  const heartbeats = useDashboardStore((s) => s.agentHeartbeats);
  const [filterTier, setFilterTier] = useState<FilterTier>(0);
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('ALL');
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null);

  const agentMap = useMemo(() => {
    const m = new Map<number, AgentHeartbeat>();
    heartbeats.forEach((b) => m.set(b.agent_id, b));
    return m;
  }, [heartbeats]);

  const displayList = useMemo(() => {
    return AGENT_ROSTER.filter((def) => {
      if (filterTier !== 0 && def.tier !== filterTier) return false;
      const beat = agentMap.get(def.id);
      if (filterStatus !== 'ALL' && beat?.status !== filterStatus) return false;
      return true;
    });
  }, [filterTier, filterStatus, agentMap]);

  const selectedBeat = selectedAgentId != null ? agentMap.get(selectedAgentId) : null;

  return (
    <div className="p-6 space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        <span className="text-xs text-text-muted uppercase tracking-wider mr-1">{tr("Tier:")}</span>
        {([0, 1, 2, 3, 4, 5, 6, 7] as FilterTier[]).map((t) => (
          <button
            key={t}
            onClick={() => setFilterTier(t)}
            className={clsx(
              'text-xs px-3 py-1 rounded font-mono transition-colors',
              filterTier === t
                ? 'bg-indigo-600 text-white'
                : 'bg-white/5 text-text-muted hover:bg-white/10',
            )}
          >
            {tr(t === 0 ? 'All' : `T${t}`)}
          </button>
        ))}

        <span className="text-xs text-text-muted uppercase tracking-wider ml-4 mr-1">{tr("Status:")}</span>
        {(['ALL', 'RUNNING', 'DEGRADED', 'ERROR', 'PAUSED'] as FilterStatus[]).map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={clsx(
              'text-xs px-3 py-1 rounded font-mono transition-colors',
              filterStatus === s
                ? 'bg-indigo-600 text-white'
                : 'bg-white/5 text-text-muted hover:bg-white/10',
            )}
          >
            {tr(s)}
          </button>
        ))}
      </div>

      {/* Agent grid */}
      <ErrorBoundary>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
          {heartbeats.length === 0
            ? Array.from({ length: 32 }).map((_, i) => <AgentCardSkeleton key={i} />)
            : displayList.map((def) => {
                const beat = agentMap.get(def.id);
                if (!beat) {
                  return (
                    <div
                      key={def.id}
                      className="bg-bg-surface border border-white/8 rounded-xl p-4 opacity-40"
                    >
                      <div className="font-mono text-xs text-text-muted mb-1">{tr("AGT-")}{tr(String(def.id).padStart(2, '0'))}
                      </div>
                      <div className="text-sm text-white">{tr(def.name)}</div>
                      <div className="text-xs text-text-muted mt-2">{tr("Offline")}</div>
                    </div>
                  );
                }
                return (
                  <AgentCard
                    key={def.id}
                    beat={beat}
                    onClick={() => setSelectedAgentId(def.id)}
                  />
                );
              })}
        </div>
      </ErrorBoundary>

      {/* Detail modal */}
      {selectedBeat && (
        <AgentDetailModal
          beat={selectedBeat}
          onClose={() => setSelectedAgentId(null)}
        />
      )}
    </div>
  );
}
