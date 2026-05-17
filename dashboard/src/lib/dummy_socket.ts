import { useDashboardStore } from '@/store/useStore';
import { AGENT_ROSTER } from '@/types/ws';

// Simulated Backend for UI Demonstration Purposes
class DummyWebSocketClient {
  private timer: ReturnType<typeof setInterval> | null = null;
  private pnl = 1000;
  private history: { time: string; value: number }[] = [];

  connect(): void {
    const store = useDashboardStore.getState();
    store.setWsStatus('connected');
    
    // Simulate real-time updates every 1.5 seconds
    this.timer = setInterval(() => {
      const now = new Date().toISOString();
      const storeState = useDashboardStore.getState();
      
      // 1. Portfolio
      this.pnl += (Math.random() - 0.45) * 15;
      this.history.push({ time: now, value: this.pnl });
      if (this.history.length > 50) this.history.shift();

      storeState.updatePortfolioSnapshot({
        daily_pnl_usd: this.pnl - 1000,
        daily_pnl_pct: (this.pnl - 1000) / 10,
        portfolio_value: this.pnl,
        open_positions: Math.floor(Math.random() * 10) + 5,
        unrealized_pnl: (Math.random() - 0.5) * 2000,
        leverage: 1.0 + Math.random() * 1.5,
        pnl_history: [...this.history]
      });

      // 2. Agents
      const agents = AGENT_ROSTER.map(a => {
        const isRunning = Math.random() > 0.1;
        return {
          agent_id: a.id,
          agent_name: a.name,
          tier: a.tier,
          status: isRunning ? 'RUNNING' : (Math.random() > 0.5 ? 'DEGRADED' : 'ERROR'),
          messages_processed: Math.floor(Math.random() * 50000),
          last_heartbeat_secs: Math.floor(Math.random() * 3),
          memory_mb: 50 + Math.random() * 200,
          error_rate_pct: isRunning ? Math.random() : 5 + Math.random() * 15,
          latency_p99_ms: 10 + Math.random() * 90,
          logs: []
        };
      });
      
      storeState.updateAgentsPayload({
        agents: agents as any,
        active_count: agents.filter(a => a.status === 'RUNNING').length,
        total_count: 32
      });

      // 3. Positions Update
      storeState.updatePositions({
        open_positions: [],
        closed_trades: [],
        long_exposure: 400 + Math.random() * 200,
        short_exposure: 200 + Math.random() * 150,
        net_delta: 100 + Math.random() * 150
      });

      // 4. System Status
      storeState.updateSystemStatus({
        status: 'PAPER',
        kill_switch_active: false,
        kill_switch_reason: null,
        environment: 'paper_trading',
        uptime_seconds: 3600
      });

      // 5. Risk limits
      storeState.updateRiskLimits([
        { name: "Max Daily Drawdown", current: 2 + Math.random() * 3, threshold: 7.0, unit: "%", status: "OK", pct: 30 + Math.random() * 20 },
        { name: "Daily VaR", current: 1.5 + Math.random() * 2, threshold: 5.0, unit: "USD", status: "OK", pct: 40 + Math.random() * 30 }
      ] as any);

    }, 1500);
  }

  disconnect(): void {
    if (this.timer) clearInterval(this.timer);
    useDashboardStore.getState().setWsStatus('disconnected');
  }
}

export const wsClient = new DummyWebSocketClient();
