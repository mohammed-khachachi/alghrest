import { useLanguage, tr } from "../../i18n";
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Bot,
  TrendingUp,
  Activity,
  Shield,
  X,
  Zap,
  ShieldCheck,
  BarChart2,
  Presentation,
  BookOpen,
  type LucideIcon,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useDashboardStore } from '@/store/useStore';
import { navigationForScope, type NavigationId } from '@/lib/navigation';

const ICONS: Record<NavigationId, LucideIcon> = {
  assistant: BookOpen, research: BarChart2, overview: LayoutDashboard, agents: Bot,
  positions: TrendingUp, kafka: Activity, risk: Shield,
  investor: Presentation, auditor: ShieldCheck, backtest: BarChart2,
};

interface SidebarProps {
  open: boolean;
  onClose: () => void;
  researchOnly?: boolean;
}

export function Sidebar({ open, onClose, researchOnly = false }: SidebarProps) {
  useLanguage();
  const wsStatus = useDashboardStore((s) => s.wsStatus);
  const activeAgents = useDashboardStore((s) => s.activeAgentCount);
  const riskAlerts = useDashboardStore((s) => s.riskAlerts);
  const criticalCount = riskAlerts.filter((a) => a.severity === 'CRITICAL').length;

  return (
    <aside
      className={clsx(
        'fixed inset-y-0 start-0 z-30 w-60 flex-shrink-0 flex flex-col',
        'bg-bg-surface border-e border-border',
        'transform transition-transform duration-300 ease-in-out',
        'lg:relative lg:translate-x-0 rtl:lg:translate-x-0',
        open ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full',
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Zap size={14} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-widest text-white">{tr("ALGHREST")}</div>
            <div className="text-[10px] text-white/40 font-mono">{tr(researchOnly ? 'مساعد التقييم · قرار بشري' : 'v0.3 · 32 AGENTS')}</div>
          </div>
        </div>
        <button
          onClick={onClose}
          className="lg:hidden text-white/40 hover:text-white transition-colors"
        >
          <X size={18} />
        </button>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navigationForScope(researchOnly ? 'advisory' : 'api').map(({ id, path, label }) => {
          const Icon = ICONS[id];
          return (
          <NavLink
            key={id}
            to={path}
            onClick={onClose}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
                isActive
                  ? 'bg-indigo-500/15 text-indigo-300 border border-indigo-500/20'
                  : 'text-white/50 hover:text-white hover:bg-white/5',
              )
            }
          >
            {({ isActive }) => (
              <>
                <Icon size={16} className={isActive ? 'text-indigo-400' : ''} />
                {tr(label)}
                {label === 'Risk' && criticalCount > 0 && (
                  <span className="ms-auto flex h-4 w-4 items-center justify-center rounded-full bg-loss text-[10px] font-bold text-white">
                    {tr(criticalCount > 9 ? '9+' : criticalCount)}
                  </span>
                )}
                {label === 'Agents' && (
                  <span className="ms-auto text-[10px] font-mono text-white/30">
                    {tr(activeAgents)}/32
                  </span>
                )}
              </>
            )}
          </NavLink>
        );})}
      </nav>

      {/* WS Status */}
      <div className="px-4 py-3 border-t border-border">
        {researchOnly ? <p className="text-xs text-white/50">{tr("بحث استشاري · دون تنفيذ آلي")}</p> : <div className="flex items-center gap-2 text-xs font-mono">
          <span
            className={clsx('w-1.5 h-1.5 rounded-full', {
              'bg-profit animate-pulse': wsStatus === 'connected',
              'bg-warning animate-pulse': wsStatus === 'connecting',
              'bg-loss': wsStatus === 'disconnected' || wsStatus === 'error',
            })}
          />
          <span className="text-white/40 capitalize">{tr(wsStatus)}</span>
        </div>}
      </div>
    </aside>
  );
}
