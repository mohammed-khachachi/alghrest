import type { AccessScope } from './access';

export const DEFAULT_ROUTE = '/assistant';

export const NAVIGATION_ROUTES = [
  { id: 'assistant', path: '/assistant', label: 'مساعد التداول اليدوي', scope: 'advisory' },
  { id: 'research', path: '/research', label: 'OpenTerminal Research', scope: 'advisory' },
  { id: 'overview', path: '/overview', label: 'Overview', scope: 'api' },
  { id: 'chat', path: '/chat', label: 'Gemini AI Analyst', scope: 'api' },
  { id: 'agents', path: '/agents', label: 'Agents', scope: 'api' },
  { id: 'positions', path: '/positions', label: 'Positions', scope: 'api' },
  { id: 'kafka', path: '/kafka', label: 'Kafka', scope: 'api' },
  { id: 'risk', path: '/risk', label: 'Risk', scope: 'api' },
  { id: 'investor', path: '/investor', label: 'Investor Pitch', scope: 'api' },
  { id: 'auditor', path: '/auditor', label: 'Auditor', scope: 'api' },
  { id: 'backtest', path: '/backtest', label: 'Backtest', scope: 'api' },
];

export type NavigationId = (typeof NAVIGATION_ROUTES)[number]['id'];

export function accessScopeForPath(pathname: string): AccessScope {
  const normalized = pathname.replace(/\/+$/, '') || '/';
  if (normalized === '/') return 'advisory';
  return NAVIGATION_ROUTES.find(route => route.path === normalized)?.scope ?? 'api';
}

export function navigationForScope(scope: AccessScope) {
  return scope === 'advisory'
    ? NAVIGATION_ROUTES.filter(route => route.scope === 'advisory')
    : NAVIGATION_ROUTES;
}
