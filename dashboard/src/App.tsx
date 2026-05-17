import { useEffect, useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { Sidebar } from '@/components/layout/Sidebar';
import { Header } from '@/components/layout/Header';
import { ToastContainer } from '@/components/common/Toast';
import { ErrorBoundary } from '@/components/common/ErrorBoundary';
import { Overview } from '@/pages/Overview';
import { Agents } from '@/pages/Agents';
import { Positions } from '@/pages/Positions';
import { Kafka } from '@/pages/Kafka';
import { Risk } from '@/pages/Risk';
import { AuditorDashboard } from '@/pages/AuditorDashboard';
import { BacktestSimulation } from '@/pages/BacktestSimulation';
import { InvestorPitch } from '@/pages/InvestorPitch';
import { wsClient } from '@/lib/websocket';
import { useDashboardStore } from '@/store/useStore';

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const wsStatus = useDashboardStore((s) => s.wsStatus);

  useEffect(() => {
    wsClient.connect();
    return () => wsClient.disconnect();
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-bg-dark text-white">
      {/* Mobile overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-20 bg-black/60 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex flex-1 flex-col min-w-0">
        <Header onMenuClick={() => setSidebarOpen((o) => !o)} />

        {/* Reconnecting banner */}
        {wsStatus !== 'connected' && (
          <div className="flex items-center gap-2 bg-warning/10 border-b border-warning/20 px-4 py-2 text-sm text-warning font-mono">
            <span className="inline-block w-2 h-2 rounded-full bg-warning animate-pulse" />
            {wsStatus === 'connecting' ? 'Connecting to data stream...' : 'Reconnecting...'}
          </div>
        )}

        <main className="flex-1 overflow-y-auto p-4 lg:p-6">
          <Routes>
            <Route path="/" element={<Navigate to="/overview" replace />} />
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
        </main>
      </div>

      <ToastContainer />
    </div>
  );
}
