import { useEffect } from 'react';
import { X, AlertTriangle, Info } from 'lucide-react';
import { clsx } from 'clsx';
import { useDashboardStore, type ToastItem } from '@/store/useStore';

function Toast({ toast }: { toast: ToastItem }) {
  const removeToast = useDashboardStore((s) => s.removeToast);

  useEffect(() => {
    if (toast.dismissAfterMs === null) return;
    const timer = setTimeout(() => removeToast(toast.id), toast.dismissAfterMs);
    return () => clearTimeout(timer);
  }, [toast.id, toast.dismissAfterMs, removeToast]);

  const Icon = toast.severity === 'INFO' ? Info : AlertTriangle;

  return (
    <div
      className={clsx(
        'flex items-start gap-3 p-4 rounded-xl border shadow-2xl max-w-sm w-full animate-slide-in',
        {
          'bg-loss/10 border-loss/30 text-loss': toast.severity === 'CRITICAL',
          'bg-warning/10 border-warning/30 text-warning': toast.severity === 'WARNING',
          'bg-profit/10 border-profit/30 text-profit': toast.severity === 'INFO',
        },
      )}
    >
      <Icon size={16} className="flex-shrink-0 mt-0.5" />
      <p className="flex-1 text-sm font-medium text-white">{toast.message}</p>
      {toast.dismissAfterMs !== null && (
        <button onClick={() => removeToast(toast.id)} className="text-white/40 hover:text-white transition-colors">
          <X size={14} />
        </button>
      )}
    </div>
  );
}

function KillSwitchOverlay({ toast }: { toast: ToastItem }) {
  const removeToast = useDashboardStore((s) => s.removeToast);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-loss/20 backdrop-blur-sm animate-fade-in">
      <div className="text-center space-y-6 p-12 rounded-2xl bg-bg-dark border-2 border-loss shadow-[0_0_80px_rgba(239,68,68,0.4)]">
        <div className="text-6xl font-mono font-black text-loss tracking-tight animate-pulse">
          KILL SWITCH
        </div>
        <div className="text-xl text-white/80">{toast.message}</div>
        <div className="text-sm text-white/40 font-mono">All trading activity has been halted</div>
        <button
          onClick={() => removeToast(toast.id)}
          className="px-8 py-3 rounded-lg border border-white/20 text-white/60 hover:text-white hover:border-white/40 transition-all text-sm font-mono"
        >
          DISMISS
        </button>
      </div>
    </div>
  );
}

export function ToastContainer() {
  const toasts = useDashboardStore((s) => s.toasts);

  const fullScreenToast = toasts.find((t) => t.fullScreen);
  if (fullScreenToast) return <KillSwitchOverlay toast={fullScreenToast} />;

  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast toast={toast} />
        </div>
      ))}
    </div>
  );
}
