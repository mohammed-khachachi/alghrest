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

interface NavItem {
  to: string;
  label: string;
  Icon: LucideIcon;
}

const NAV_ITEMS: NavItem[] = [
  { to: '/assistant', label: 'مساعد التداول اليدوي', Icon: BookOpen },
  { to: '/overview',  label: 'Overview',  Icon: LayoutDashboard },
  { to: '/agents',    label: 'Agents',    Icon: Bot },
  { to: '/positions', label: 'Positions', Icon: TrendingUp },
  { to: '/kafka',     label: 'Kafka',     Icon: Activity },
  { to: '/risk',      label: 'Risk',      Icon: Shield },
  { to: '/investor',  label: 'Investor',  Icon: Presentation },
  { to: '/auditor',   label: 'Auditor',   Icon: ShieldCheck },
  { to: '/backtest',  label: 'Backtest',  Icon: BarChart2 },
];

interface SidebarProps {
  open: boolean;
  onClose: () => void;
}

export function Sidebar({ open, onClose }: SidebarProps) {
  const wsStatus = useDashboardStore((s) => s.wsStatus);
  const activeAgents = useDashboardStore((s) => s.activeAgentCount);
  const riskAlerts = useDashboardStore((s) => s.riskAlerts);
  const criticalCount = riskAlerts.filter((a) => a.severity === 'CRITICAL').length;

  return (
    <aside
      className={clsx(
        'fixed inset-y-0 left-0 z-30 w-60 flex-shrink-0 flex flex-col',
        'bg-bg-surface border-r border-border',
        'transform transition-transform duration-300 ease-in-out',
        'lg:relative lg:translate-x-0',
        open ? 'translate-x-0' : '-translate-x-full',
      )}
    >
      {/* Logo */}
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center">
            <Zap size={14} className="text-white" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-widest text-white">ALGHREST</div>
            <div className="text-[10px] text-white/40 font-mono">v0.3 · 32 AGENTS</div>
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
        {NAV_ITEMS.map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
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
                {label}
                {label === 'Risk' && criticalCount > 0 && (
                  <span className="ml-auto flex h-4 w-4 items-center justify-center rounded-full bg-loss text-[10px] font-bold text-white">
                    {criticalCount > 9 ? '9+' : criticalCount}
                  </span>
                )}
                {label === 'Agents' && (
                  <span className="ml-auto text-[10px] font-mono text-white/30">
                    {activeAgents}/32
                  </span>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* WS Status */}
      <div className="px-4 py-3 border-t border-border">
        <div className="flex items-center gap-2 text-xs font-mono">
          <span
            className={clsx('w-1.5 h-1.5 rounded-full', {
              'bg-profit animate-pulse': wsStatus === 'connected',
              'bg-warning animate-pulse': wsStatus === 'connecting',
              'bg-loss': wsStatus === 'disconnected' || wsStatus === 'error',
            })}
          />
          <span className="text-white/40 capitalize">{wsStatus}</span>
        </div>
      </div>
    </aside>
  );
}
