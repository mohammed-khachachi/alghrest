import { create } from 'zustand';
import type {
  PortfolioSnapshot,
  AgentsPayload,
  AgentHeartbeat,
  PositionsPayload,
  OpenPosition,
  ClosedTrade,
  KafkaPayload,
  KafkaTopicMetrics,
  RiskAlert,
  SystemStatus,
  RiskLimit,
} from '@/types/ws';

export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

// Default symbols pre-selected on first load — matched to the most common
// holdings so Market Data / Holdings panels render immediately without
// requiring the user to pick anything. Exported so the "Show all" reset
// in HoldingsPanel can restore exactly this set.
export const DEFAULT_SELECTED_SYMBOLS: readonly string[] = [
  'BTC',
  'ETH',
  'SOL',
  'EUR/USD',
  'AAPL',
  'TSLA',
] as const;

export interface ToastItem {
  id: string;
  severity: 'CRITICAL' | 'WARNING' | 'INFO';
  message: string;
  dismissAfterMs: number | null;
  fullScreen?: boolean;
}

interface DashboardState {
  // Connection
  wsStatus: WsStatus;

  // Portfolio
  portfolioSnapshot: PortfolioSnapshot | null;

  // Agents
  agentHeartbeats: AgentHeartbeat[];
  activeAgentCount: number;

  // Positions
  openPositions: OpenPosition[];
  closedTrades: ClosedTrade[];
  longExposure: number;
  shortExposure: number;
  netDelta: number;

  // Kafka
  kafkaTopics: KafkaTopicMetrics[];

  // Risk
  riskAlerts: RiskAlert[];
  riskLimits: RiskLimit[];

  // System
  systemStatus: SystemStatus | null;

  // UI
  toasts: ToastItem[];

  // Symbol selection (Overview filter + market panel)
  selectedSymbols: string[];

  // Actions
  setWsStatus: (status: WsStatus) => void;
  setSelectedSymbols: (symbols: string[]) => void;
  resetSelectedSymbols: () => void;
  updatePortfolioSnapshot: (data: PortfolioSnapshot) => void;
  updateAgentsPayload: (data: AgentsPayload) => void;
  updatePositions: (data: PositionsPayload) => void;
  updateKafkaMetrics: (data: KafkaPayload) => void;
  addRiskAlert: (alert: RiskAlert) => void;
  updateSystemStatus: (status: SystemStatus) => void;
  updateRiskLimits: (limits: RiskLimit[]) => void;
  addToast: (toast: ToastItem) => void;
  removeToast: (id: string) => void;
}

export const useDashboardStore = create<DashboardState>((set) => ({
  wsStatus: 'connecting',
  portfolioSnapshot: null,
  agentHeartbeats: [],
  activeAgentCount: 0,
  openPositions: [],
  closedTrades: [],
  longExposure: 0,
  shortExposure: 0,
  netDelta: 0,
  kafkaTopics: [],
  riskAlerts: [],
  riskLimits: [],
  systemStatus: null,
  toasts: [],
  selectedSymbols: [...DEFAULT_SELECTED_SYMBOLS],

  setWsStatus: (status) => set({ wsStatus: status }),

  setSelectedSymbols: (symbols) => set({ selectedSymbols: symbols }),

  resetSelectedSymbols: () => set({ selectedSymbols: [...DEFAULT_SELECTED_SYMBOLS] }),

  updatePortfolioSnapshot: (data) => set({ portfolioSnapshot: data }),

  updateAgentsPayload: (data) =>
    set({ agentHeartbeats: data.agents, activeAgentCount: data.active_count }),

  updatePositions: (data) =>
    set({
      openPositions: data.open_positions,
      closedTrades: data.closed_trades,
      longExposure: data.long_exposure,
      shortExposure: data.short_exposure,
      netDelta: data.net_delta,
    }),

  updateKafkaMetrics: (data) => set({ kafkaTopics: data.topics }),

  addRiskAlert: (alert) =>
    set((state) => ({
      riskAlerts: [alert, ...state.riskAlerts].slice(0, 200),
    })),

  updateSystemStatus: (status) => set({ systemStatus: status }),

  updateRiskLimits: (limits) => set({ riskLimits: limits }),

  addToast: (toast) =>
    set((state) => ({
      toasts: state.toasts.some((t) => t.id === toast.id)
        ? state.toasts
        : [...state.toasts, toast],
    })),

  removeToast: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));
