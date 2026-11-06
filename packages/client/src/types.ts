/**
 * ALGHREST Client SDK — Data Contracts & Types
 */

export interface ClientOptions {
  /**
   * Base URL of the ALGHREST backend.
   * @default "http://127.0.0.1:8000"
   */
  baseUrl?: string;

  /**
   * Access token (Bearer authentication) for protected endpoints.
   */
  accessToken?: string;

  /**
   * Request timeout in milliseconds.
   * @default 10000
   */
  timeoutMs?: number;

  /**
   * Custom fetch implementation (optional, defaults to global fetch).
   */
  fetch?: typeof fetch;

  /**
   * WebSocket implementation (optional, defaults to global WebSocket).
   */
  WebSocket?: typeof WebSocket;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  timestamp: string;
  kill_switch_active: boolean;
  environment: "development" | "paper_trading" | "live";
  version: string;
}

export type AssetClass = "equity" | "crypto" | "forex" | "commodity" | "index";

export interface SymbolInfo {
  symbol: string;
  name: string;
  asset_class: AssetClass;
}

export interface Quote {
  symbol: string;
  price: number;
  bid: number;
  ask: number;
  timestamp: string;
  change_24h_percent?: number;
  volume_24h?: number;
  asset_class: AssetClass;
}

export interface OHLCVBar {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoricalDataResponse {
  symbol: string;
  as_of: string;
  bars: OHLCVBar[];
}

export interface Holding {
  symbol: string;
  asset_class: AssetClass;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
}

export interface OpenBBProviderInfo {
  enabled: boolean;
  sdk_available: boolean;
  registered_providers: string[];
  default_providers: Record<string, string>;
  active_credentials: string[];
  missing_credentials: string[];
}

export interface OpenBBHistoricalOptions {
  symbol: string;
  assetClass: AssetClass;
  timeframe?: "1m" | "5m" | "15m" | "1h" | "1d";
  startDate?: string;
  endDate?: string;
  provider?: string;
}

export interface Position {
  symbol: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  pnl_usd: number;
  pnl_percent: number;
  leverage: number;
}

export interface PortfolioState {
  cash_usd: number;
  equity_usd: number;
  total_exposure_usd: number;
  daily_pnl_usd: number;
  daily_pnl_percent: number;
  positions: Position[];
  snapshot_time: string;
}

export interface RiskMetrics {
  current_drawdown_percent: number;
  max_drawdown_percent: number;
  var_95_percent: number;
  var_99_percent: number;
  daily_loss_percent: number;
  circuit_breaker_tripped: boolean;
  consecutive_losses: number;
}

export interface KillSwitchStatus {
  active: boolean;
  reason?: string | null;
}

export type AgentStatus = "RUNNING" | "PAUSED" | "HALTED" | "ERROR" | "STARTING";

export interface AgentHealth {
  agent_id: number;
  name: string;
  status: AgentStatus;
  last_heartbeat: string;
  error_message?: string | null;
  metrics_port: number;
}

export interface AgentsSummary {
  agents: AgentHealth[];
  total: number;
  running: number;
  errors: number;
}

export interface SignalData {
  symbol: string;
  signal_type: string;
  value: number;
  direction?: "BUY" | "SELL" | "NEUTRAL";
  timestamp: string;
  confidence?: number;
}

export interface WebSocketMessage<T = unknown> {
  type: string;
  timestamp: string;
  payload: T;
}

export interface WebSocketSubscriptionOptions {
  onMessage?: (message: WebSocketMessage) => void;
  onError?: (error: Event) => void;
  onClose?: (event: CloseEvent) => void;
  onOpen?: () => void;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
}
