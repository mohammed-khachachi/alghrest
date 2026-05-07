import { z } from 'zod';

// ── BASE MESSAGE ─────────────────────────────────────────────────────────────

export const WsMessageSchema = z.object({
  channel: z.string(),
  data: z.unknown(),
  timestamp: z.string(),
});
export type WsMessage = z.infer<typeof WsMessageSchema>;

// ── PORTFOLIO SNAPSHOT ────────────────────────────────────────────────────────

export const PnlPointSchema = z.object({
  time: z.string(),
  value: z.number(),
});

export const PortfolioSnapshotSchema = z.object({
  daily_pnl_usd: z.number(),
  daily_pnl_pct: z.number(),
  portfolio_value: z.number(),
  open_positions: z.number(),
  unrealized_pnl: z.number(),
  leverage: z.number(),
  pnl_history: z.array(PnlPointSchema),
});
export type PortfolioSnapshot = z.infer<typeof PortfolioSnapshotSchema>;
export type PnlPoint = z.infer<typeof PnlPointSchema>;

// ── AGENTS HEARTBEATS ─────────────────────────────────────────────────────────

export const AgentStatusSchema = z.enum([
  'RUNNING', 'DEGRADED', 'ERROR', 'PAUSED', 'INITIALIZING', 'SHUTDOWN',
]);
export type AgentStatus = z.infer<typeof AgentStatusSchema>;

export const AgentHeartbeatSchema = z.object({
  agent_id: z.number(),
  agent_name: z.string(),
  tier: z.number(),
  status: AgentStatusSchema,
  messages_processed: z.number(),
  last_heartbeat_secs: z.number(),
  memory_mb: z.number(),
  error_rate_pct: z.number(),
  latency_p99_ms: z.number(),
  logs: z.array(z.string()),
});
export type AgentHeartbeat = z.infer<typeof AgentHeartbeatSchema>;

export const AgentsPayloadSchema = z.object({
  agents: z.array(AgentHeartbeatSchema),
  active_count: z.number(),
  total_count: z.number(),
});
export type AgentsPayload = z.infer<typeof AgentsPayloadSchema>;

// ── POSITIONS ─────────────────────────────────────────────────────────────────

export const OpenPositionSchema = z.object({
  symbol: z.string(),
  side: z.enum(['BUY', 'SELL']),
  size: z.number(),
  entry_price: z.number(),
  current_price: z.number(),
  unrealized_pnl: z.number(),
  unrealized_pnl_pct: z.number(),
  strategy: z.string(),
  exchange: z.string(),
  opened_at: z.string(),
  age_seconds: z.number(),
});
export type OpenPosition = z.infer<typeof OpenPositionSchema>;

export const ClosedTradeSchema = z.object({
  symbol: z.string(),
  side: z.enum(['BUY', 'SELL']),
  size: z.number(),
  entry_price: z.number(),
  exit_price: z.number(),
  realized_pnl: z.number(),
  pnl_pct: z.number(),
  strategy: z.string(),
  closed_at: z.string(),
});
export type ClosedTrade = z.infer<typeof ClosedTradeSchema>;

export const PositionsPayloadSchema = z.object({
  open_positions: z.array(OpenPositionSchema),
  closed_trades: z.array(ClosedTradeSchema),
  long_exposure: z.number(),
  short_exposure: z.number(),
  net_delta: z.number(),
});
export type PositionsPayload = z.infer<typeof PositionsPayloadSchema>;

// ── KAFKA METRICS ─────────────────────────────────────────────────────────────

export const KafkaTopicMetricsSchema = z.object({
  name: z.string(),
  messages_per_sec: z.number(),
  consumer_lag_ms: z.number(),
  last_message_ts: z.string(),
  partition_count: z.number(),
  total_messages: z.number(),
});
export type KafkaTopicMetrics = z.infer<typeof KafkaTopicMetricsSchema>;

export const KafkaPayloadSchema = z.object({
  topics: z.array(KafkaTopicMetricsSchema),
});
export type KafkaPayload = z.infer<typeof KafkaPayloadSchema>;

// ── RISK ALERTS ───────────────────────────────────────────────────────────────

export const AlertSeveritySchema = z.enum(['CRITICAL', 'WARNING', 'INFO']);
export type AlertSeverity = z.infer<typeof AlertSeveritySchema>;

export const RiskAlertSchema = z.object({
  alert_id: z.string(),
  severity: AlertSeveritySchema,
  timestamp: z.string(),
  message: z.string(),
  affected_agent: z.string(),
  alert_type: z.string(),
  triggered_value: z.number(),
  threshold_value: z.number(),
});
export type RiskAlert = z.infer<typeof RiskAlertSchema>;

export const RiskAlertPayloadSchema = z.object({
  alert: RiskAlertSchema,
});

// ── SYSTEM STATUS ─────────────────────────────────────────────────────────────

export const SystemStatusValueSchema = z.enum(['LIVE', 'PAPER', 'HALTED']);
export type SystemStatusValue = z.infer<typeof SystemStatusValueSchema>;

export const SystemStatusSchema = z.object({
  status: SystemStatusValueSchema,
  kill_switch_active: z.boolean(),
  kill_switch_reason: z.string().nullable(),
  environment: z.string(),
  uptime_seconds: z.number(),
});
export type SystemStatus = z.infer<typeof SystemStatusSchema>;

// ── RISK LIMITS ───────────────────────────────────────────────────────────────

export const RiskLimitStatusSchema = z.enum(['OK', 'WARNING', 'BREACHED']);

export const RiskLimitSchema = z.object({
  name: z.string(),
  current: z.number(),
  threshold: z.number(),
  unit: z.string(),
  status: RiskLimitStatusSchema,
  pct: z.number(),
});
export type RiskLimit = z.infer<typeof RiskLimitSchema>;

export const RiskLimitsPayloadSchema = z.object({
  limits: z.array(RiskLimitSchema),
});

// ── AGENT ROSTER (static) ─────────────────────────────────────────────────────

export interface AgentDef {
  id: number;
  name: string;
  tier: number;
}

export const AGENT_ROSTER: AgentDef[] = [
  { id: 1,  name: 'CIO Agent',            tier: 1 },
  { id: 2,  name: 'Risk Governor',         tier: 1 },
  { id: 3,  name: 'Market Data Hub',       tier: 2 },
  { id: 4,  name: 'News Analyst',          tier: 2 },
  { id: 5,  name: 'Sentiment Analyst',     tier: 2 },
  { id: 6,  name: 'Macro Economist',       tier: 2 },
  { id: 7,  name: 'Geopolitical Watcher',  tier: 2 },
  { id: 8,  name: 'On-Chain Sleuth',       tier: 2 },
  { id: 9,  name: 'Technical Analyst',     tier: 3 },
  { id: 10, name: 'Volatility Forecaster', tier: 3 },
  { id: 11, name: 'Correlation Engine',    tier: 3 },
  { id: 12, name: 'Trend Follower',        tier: 4 },
  { id: 13, name: 'Mean Reversion',        tier: 4 },
  { id: 14, name: 'Momentum',              tier: 4 },
  { id: 15, name: 'Stat Arb',              tier: 4 },
  { id: 16, name: 'ML Predictor',          tier: 4 },
  { id: 17, name: 'Options Strategist',    tier: 4 },
  { id: 18, name: 'Macro Rotator',         tier: 4 },
  { id: 19, name: 'Breakout Hunter',       tier: 4 },
  { id: 20, name: 'Order Router',          tier: 5 },
  { id: 21, name: 'Position Sizer',        tier: 5 },
  { id: 22, name: 'Slippage Minimizer',    tier: 5 },
  { id: 23, name: 'Hedge Manager',         tier: 5 },
  { id: 24, name: 'Fee Optimizer',         tier: 5 },
  { id: 25, name: 'Liquidation Guard',     tier: 5 },
  { id: 26, name: 'Yield Farmer',          tier: 6 },
  { id: 27, name: 'DEX Arbitrageur',       tier: 6 },
  { id: 28, name: 'MEV Hunter',            tier: 6 },
  { id: 29, name: 'Bridge Strategist',     tier: 6 },
  { id: 30, name: 'Portfolio Tracker',     tier: 7 },
  { id: 31, name: 'Alert Manager',         tier: 7 },
  { id: 32, name: 'Compliance Agent',      tier: 7 },
];

export const TIER_COLORS: Record<number, string> = {
  1: '#ff3366',
  2: '#00f0ff',
  3: '#bd00ff',
  4: '#ff0055',
  5: '#ffaa00',
  6: '#00ffaa',
  7: '#4d4dff',
};

export const KAFKA_TOPICS = [
  'prices.realtime', 'news.tagged', 'sentiment.scored', 'onchain.signals',
  'macro.regime', 'indicators.computed', 'patterns.detected', 'volatility.forecast',
  'correlation.matrix', 'proposals.bus', 'orders.approved', 'orders.executed',
  'fills.confirmed', 'portfolio.state', 'risk.alerts', 'rl.param.updates',
] as const;
