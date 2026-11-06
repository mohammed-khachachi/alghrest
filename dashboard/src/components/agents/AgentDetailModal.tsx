import { useLanguage, tr } from "../../i18n";
import * as Dialog from '@radix-ui/react-dialog';
import { X, RotateCw, Pause } from 'lucide-react';
import { MiniSparkline } from '@/components/charts/MiniSparkline';
import { TIER_COLORS, type AgentHeartbeat } from '@/types/ws';
import { clsx } from 'clsx';

interface AgentDetailModalProps {
  beat: AgentHeartbeat;
  onClose: () => void;
}

export function AgentDetailModal({ beat, onClose }: AgentDetailModalProps) {
  useLanguage();
  const tierColor = TIER_COLORS[beat.tier] ?? '#64748b';

  // Build fake sparkline data from current error_rate so the UI has something to show
  const sparkData = beat.logs.slice(-20).map(() =>
    Math.max(0, beat.error_rate_pct + (Math.random() - 0.5) * 2),
  );

  return (
    <Dialog.Root open onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/70 backdrop-blur-sm z-40" />
        <Dialog.Content
          className={clsx(
            'fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50',
            'w-full max-w-lg bg-bg-surface border border-white/10 rounded-2xl',
            'shadow-2xl p-6 space-y-5 max-h-[90vh] overflow-y-auto',
          )}
        >
          {/* Header */}
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs text-text-muted">{tr("AGT-")}{tr(String(beat.agent_id).padStart(2, '0'))}
                </span>
                <span
                  className="text-xs px-2 py-0.5 rounded font-mono"
                  style={{ backgroundColor: `${tierColor}20`, color: tierColor }}
                >{tr("Tier ")}{tr(beat.tier)}
                </span>
              </div>
              <Dialog.Title className="text-lg font-bold text-white">
                {tr(beat.agent_name)}
              </Dialog.Title>
            </div>
            <Dialog.Close asChild>
              <button className="text-text-muted hover:text-white transition-colors">
                <X size={20} />
              </button>
            </Dialog.Close>
          </div>

          {/* Metrics grid */}
          <div className="grid grid-cols-2 gap-3 text-sm">
            {[
              { label: 'Status', value: beat.status },
              { label: 'Messages', value: beat.messages_processed.toLocaleString() },
              { label: 'Last Heartbeat', value: `${beat.last_heartbeat_secs}s ago` },
              { label: 'Memory', value: `${beat.memory_mb.toFixed(0)} MB` },
              { label: 'Error Rate', value: `${beat.error_rate_pct.toFixed(2)}%` },
              { label: 'P99 Latency', value: `${beat.latency_p99_ms.toFixed(0)} ms` },
            ].map(({ label, value }) => (
              <div key={label} className="bg-white/4 rounded-lg px-3 py-2">
                <div className="text-xs text-text-muted mb-0.5">{tr(label)}</div>
                <div className="font-mono text-white">{tr(value)}</div>
              </div>
            ))}
          </div>

          {/* Sparkline */}
          <div className="bg-white/4 rounded-lg p-3">
            <div className="text-xs text-text-muted mb-2">{tr("Error Rate History")}</div>
            <MiniSparkline
              data={sparkData.length > 0 ? sparkData : [0]}
              color={beat.error_rate_pct > 5 ? '#f87171' : '#4ade80'}
              height={48}
            />
          </div>

          {/* Logs */}
          <div>
            <div className="text-xs text-text-muted uppercase tracking-wider mb-2">{tr("Last Log Entries")}</div>
            <div className="space-y-1 max-h-48 overflow-y-auto">
              {beat.logs.length === 0 ? (
                <div className="text-xs text-text-muted italic">{tr("No logs available")}</div>
              ) : (
                beat.logs.slice(-10).reverse().map((log, i) => (
                  <div
                    key={i}
                    className="font-mono text-xs bg-black/40 rounded px-3 py-1.5 text-slate-300"
                  >
                    {tr(log)}
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2 border-t border-white/8">
            <button
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
                'bg-indigo-600 hover:bg-indigo-700 text-white transition-colors',
              )}
            >
              <RotateCw size={14} />{tr("Restart Agent")}</button>
            <button
              className={clsx(
                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
                'bg-white/8 hover:bg-white/12 text-white transition-colors',
              )}
            >
              <Pause size={14} />{tr("Pause Agent")}</button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
