import { useEffect, useState, useCallback } from 'react';
import { Menu, Power, Clock } from 'lucide-react';
import { clsx } from 'clsx';
import * as Dialog from '@radix-ui/react-dialog';
import { useDashboardStore } from '@/store/useStore';

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function useUtcClock() {
  const [utc, setUtc] = useState(() => new Date().toUTCString().slice(17, 25));
  useEffect(() => {
    const id = setInterval(() => setUtc(new Date().toUTCString().slice(17, 25)), 1000);
    return () => clearInterval(id);
  }, []);
  return utc;
}

interface HeaderProps {
  onMenuClick: () => void;
}

export function Header({ onMenuClick }: HeaderProps) {
  const utc = useUtcClock();
  const systemStatus = useDashboardStore((s) => s.systemStatus);
  const addToast = useDashboardStore((s) => s.addToast);
  const [killDialogOpen, setKillDialogOpen] = useState(false);
  const [sessionSeconds, setSessionSeconds] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setSessionSeconds((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const handleKillSwitch = useCallback(async () => {
    setKillDialogOpen(false);
    try {
      const resp = await fetch(
        `${import.meta.env['VITE_API_URL'] ?? 'http://localhost:8000'}/api/v1/risk/kill-switch`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' } },
      );
      if (!resp.ok) throw new Error(await resp.text());
      addToast({ id: 'kill-switch', severity: 'CRITICAL', message: 'KILL SWITCH ACTIVATED', dismissAfterMs: null, fullScreen: true });
    } catch (err) {
      addToast({ id: `ks-err-${Date.now()}`, severity: 'WARNING', message: `Kill switch failed: ${String(err)}`, dismissAfterMs: 8000 });
    }
  }, [addToast]);

  const status = systemStatus?.status ?? 'PAPER';

  return (
    <header className="flex items-center gap-3 px-4 py-3 bg-bg-surface border-b border-border flex-shrink-0">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="lg:hidden text-white/50 hover:text-white transition-colors"
      >
        <Menu size={20} />
      </button>

      {/* Status badge */}
      <div
        className={clsx(
          'flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-mono font-bold border',
          {
            'bg-profit/10 border-profit/30 text-profit': status === 'LIVE',
            'bg-warning/10 border-warning/30 text-warning': status === 'PAPER',
            'bg-loss/10 border-loss/30 text-loss': status === 'HALTED',
          },
        )}
      >
        <span
          className={clsx('w-1.5 h-1.5 rounded-full', {
            'bg-profit animate-pulse': status === 'LIVE',
            'bg-warning': status === 'PAPER',
            'bg-loss animate-pulse': status === 'HALTED',
          })}
        />
        {status}
      </div>

      <div className="flex-1" />

      {/* UTC clock */}
      <div className="flex items-center gap-1.5 text-xs font-mono text-white/40">
        <Clock size={12} />
        <span>{utc} UTC</span>
      </div>

      {/* Session timer */}
      <div className="hidden sm:block text-xs font-mono text-white/30 border-l border-border pl-3">
        {formatUptime(systemStatus?.uptime_seconds ?? sessionSeconds)}
      </div>

      {/* Kill switch */}
      <Dialog.Root open={killDialogOpen} onOpenChange={setKillDialogOpen}>
        <Dialog.Trigger asChild>
          <button
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-loss/10 border border-loss/30 text-loss text-xs font-mono font-bold hover:bg-loss/20 transition-colors"
          >
            <Power size={12} />
            KILL
          </button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/80 z-50 animate-fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl bg-bg-elevated border border-loss/30 p-6 shadow-2xl animate-fade-in">
            <Dialog.Title className="text-lg font-bold text-loss mb-2">
              Activate Kill Switch
            </Dialog.Title>
            <Dialog.Description className="text-sm text-white/60 mb-6">
              This will immediately halt all 32 agents, close all open positions, and suspend all
              trading activity. This action requires manual reset.
            </Dialog.Description>
            <div className="flex gap-3 justify-end">
              <Dialog.Close asChild>
                <button className="px-4 py-2 rounded-lg bg-white/5 border border-border text-sm text-white/60 hover:text-white hover:bg-white/10 transition-colors">
                  Cancel
                </button>
              </Dialog.Close>
              <button
                onClick={handleKillSwitch}
                className="px-4 py-2 rounded-lg bg-loss border border-loss text-sm font-bold text-white hover:bg-loss/80 transition-colors"
              >
                CONFIRM KILL SWITCH
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </header>
  );
}
