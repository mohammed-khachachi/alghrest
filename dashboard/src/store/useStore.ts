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

  // Actions
  setWsStatus: (status: WsStatus) => void;
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

  setWsStatus: (status) => set({ wsStatus: status }),

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
