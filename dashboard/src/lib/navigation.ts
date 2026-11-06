import type { AccessScope } from './access';

export const DEFAULT_ROUTE = '/overview';

export const NAVIGATION_ROUTES = [
  { id: 'assistant', path: '/assistant', label: 'مساعد التداول اليدوي', scope: 'advisory' },
  { id: 'research', path: '/research', label: 'OpenTerminal Research', scope: 'advisory' },
  { id: 'overview', path: '/overview', label: 'Overview', scope: 'api' },
  { id: 'chat', path: '/chat', label: 'Gemini AI Analyst', scope: 'api' },
  { id: 'agents', path: '/agents', label: 'Agents', scope: 'api' },
  { id: 'positions', path: '/positions', label: 'Positions', scope: 'api' },
  { id: 'kafka', path: '/kafka', label: 'Kafka', scope: 'api' },
  { id: 'risk', path: '/risk', label: 'Risk', scope: 'api' },
  { id: 'investor', path: '/investor', label: 'Investor', scope: 'api' },
  { id: 'auditor', path: '/auditor', label: 'Auditor', scope: 'api' },
  { id: 'backtest', path: '/backtest', label: 'Backtest', scope: 'api' },
] as const;

export type NavigationId = (typeof NAVIGATION_ROUTES)[number]['id'];

/** Routing chooses a service's existing access gate, never grants permission. */
export function accessScopeForPath(pathname: string): AccessScope {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (normalized === '/') return 'api';
  return NAVIGATION_ROUTES.find(route => route.path === normalized)?.scope ?? 'api';
}

export function navigationForScope(_scope: AccessScope) {
  return NAVIGATION_ROUTES;
}
