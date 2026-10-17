import { lazy, Suspense, useEffect, useState } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { ToastContainer } from '@/components/common/Toast';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { AccessGate } from '@/components/common/AccessGate';
import { wsClient } from '@/lib/websocket';
import { useDashboardStore } from '@/store/useStore';
import { DEFAULT_ROUTE, accessScopeForPath } from '@/lib/navigation';

const Overview = lazy(() => import('@/pages/Overview').then(m => ({ default: m.Overview })));
const Agents = lazy(() => import('@/pages/Agents').then(m => ({ default: m.Agents })));
const Positions = lazy(() => import('@/pages/Positions').then(m => ({ default: m.Positions })));
const Kafka = lazy(() => import('@/pages/Kafka').then(m => ({ default: m.Kafka })));
const Risk = lazy(() => import('@/pages/Risk').then(m => ({ default: m.Risk })));
const AuditorDashboard = lazy(() => import('@/pages/AuditorDashboard').then(m => ({ default: m.AuditorDashboard })));
const BacktestSimulation = lazy(() => import('@/pages/BacktestSimulation').then(m => ({ default: m.BacktestSimulation })));
const InvestorPitch = lazy(() => import('@/pages/InvestorPitch').then(m => ({ default: m.InvestorPitch })));
const ManualAssistant = lazy(() => import('@/pages/ManualAssistant').then(m => ({ default: m.ManualAssistant })));
const ResearchTerminal = lazy(() => import('@/pages/ResearchTerminal').then(m => ({ default: m.ResearchTerminal })));


export default function App() {
  const [authorized, setAuthorized] = useState({ api: false, advisory: false });
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const scope = accessScopeForPath(useLocation().pathname);
  const assistantPage = scope === 'advisory';
  const ready = authorized[scope];
  const wsStatus = useDashboardStore((s) => s.wsStatus);
  const demoMode = useDashboardStore((s) => s.systemStatus?.status === 'DEMO');

  useEffect(() => {
    if (ready && !assistantPage) wsClient.connect();

    return () => wsClient.disconnect();
  }, [assistantPage, ready]);

    if (!ready) return <AccessGate key={scope} scope={scope} onReady={() => setAuthorized(current => ({ ...current, [scope]: true }))} />;

  return (
    <div className="flex h-screen overflow-hidden bg-bg-dark text-white">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <Sidebar researchOnly={assistantPage} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-1 flex-col min-w-0">
        <Header researchOnly={assistantPage} onMenuClick={() => setSidebarOpen((o) => !o)} />

        {!assistantPage && demoMode && (
          <div role="status" className="bg-indigo-500/10 border-b border-indigo-500/20 px-4 py-3 text-sm text-indigo-200">
            <strong>Demo data — paper account not connected.</strong>{' '}
            Agent activity and portfolio values are simulated. This feed has no account positions or trade history.
          </div>
        )}

        {/* Reconnecting banner */}
        {!assistantPage && wsStatus !== 'connected' && (
          <div className="flex items-center gap-2 bg-warning/10 border-b border-warning/20 px-4 py-2 text-sm text-warning font-mono">
            <span className="inline-block w-2 h-2 rounded-full bg-warning animate-pulse" />
            {wsStatus === 'connecting' ? 'Connecting to data stream...' : 'Reconnecting...'}
          </div>
        )}

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Suspense fallback={<p role="status">تحميل الصفحة…</p>}>
            <Routes>
              <Route path="/assistant" element={<ErrorBoundary><ManualAssistant /></ErrorBoundary>} />
              <Route path="/research" element={<ErrorBoundary><ResearchTerminal /></ErrorBoundary>} />
              <Route path="/" element={<Navigate to={DEFAULT_ROUTE} replace />} />
              <Route
                path="/overview"
                element={
                  <ErrorBoundary>
                    <Overview />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/agents"
                element={
                  <ErrorBoundary>
                    <Agents />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/positions"
                element={
                  <ErrorBoundary>
                    <Positions />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/kafka"
                element={
                  <ErrorBoundary>
                    <Kafka />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/risk"
                element={
                  <ErrorBoundary>
                    <Risk />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/auditor"
                element={
                  <ErrorBoundary>
                    <AuditorDashboard />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/investor"
                element={
                  <ErrorBoundary>
                    <InvestorPitch />
                  </ErrorBoundary>
                }
              />
              <Route
                path="/backtest"
                element={
                  <ErrorBoundary>
                    <BacktestSimulation />
                  </ErrorBoundary>
                }
              />
            </Routes>
          </Suspense>
        </main>
      </div>

      <ToastContainer />
    </div>
  );
}
