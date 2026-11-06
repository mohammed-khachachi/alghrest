/**
 * ALGHREST Client SDK — Core API Client
 */

import {
  AlghrestAuthError,
  AlghrestError,
  AlghrestNetworkError,
  AlghrestNotFoundError,
  AlghrestTimeoutError,
  AlghrestValidationError,
} from "./errors.js";
import type {
  AgentHealth,
  AgentsSummary,
  ClientOptions,
  HealthResponse,
  HistoricalDataResponse,
  Holding,
  KillSwitchStatus,
  OHLCVBar,
  OpenBBHistoricalOptions,
  OpenBBProviderInfo,
  PortfolioState,
  Position,
  Quote,
  RiskMetrics,
  SignalData,
  SymbolInfo,
  WebSocketMessage,
  WebSocketSubscriptionOptions,
} from "./types.js";

export class AlghrestClient {
  private readonly baseUrl: string;
  private readonly accessToken?: string;
  private readonly timeoutMs: number;
  private readonly customFetch: typeof fetch;
  private readonly customWebSocket?: typeof WebSocket;

  constructor(options: ClientOptions = {}) {
    this.baseUrl = (options.baseUrl ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
    this.accessToken = options.accessToken;
    this.timeoutMs = options.timeoutMs ?? 10000;
    this.customFetch = options.fetch ?? globalThis.fetch;
    this.customWebSocket = options.WebSocket ?? globalThis.WebSocket;

    if (!this.customFetch) {
      throw new Error("Fetch implementation is not available. Please provide options.fetch.");
    }
  }

  /**
   * Internal HTTP request handler with authentication, timeout, and error mapping.
   */
  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const url = `${this.baseUrl}${path.startsWith("/") ? "" : "/"}${path}`;
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.accessToken) {
      headers.Authorization = `Bearer ${this.accessToken}`;
    }

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeoutMs);

    try {
      const response = await this.customFetch(url, {
        ...options,
        headers,
        signal: controller.signal,
      });

      if (response.ok) {
        if (response.status === 204) {
          return undefined as T;
        }
        return (await response.json()) as T;
      }

      let errorBody: unknown;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = await response.text();
      }

      if (response.status === 401) {
        throw new AlghrestAuthError("Unauthorized: Invalid API access token", errorBody);
      }
      if (response.status === 404) {
        throw new AlghrestNotFoundError(`Resource not found at ${path}`, errorBody);
      }
      if (response.status === 422) {
        throw new AlghrestValidationError("Data validation error", errorBody);
      }

      throw new AlghrestError(
        `ALGHREST API error (${response.status}): ${response.statusText}`,
        response.status,
        errorBody,
      );
    } catch (error: unknown) {
      if (error instanceof AlghrestError) {
        throw error;
      }
      if (error instanceof Error && error.name === "AbortError") {
        throw new AlghrestTimeoutError(`Request to ${path} timed out after ${this.timeoutMs}ms`);
      }
      throw new AlghrestNetworkError(
        error instanceof Error ? error.message : "Unknown network connection failure",
      );
    } finally {
      clearTimeout(timeoutId);
    }
  }

  // ── System Health ─────────────────────────────────────────────────────────

  /**
   * Get overall backend health and kill switch status.
   */
  public async getHealth(): Promise<HealthResponse> {
    return this.request<HealthResponse>("/health");
  }

  // ── Market Data ───────────────────────────────────────────────────────────

  /**
   * List all configured tradeable symbols in the catalog.
   */
  public async getSymbols(): Promise<SymbolInfo[]> {
    const res = await this.request<{ symbols: SymbolInfo[] }>("/api/symbols");
    return res.symbols;
  }

  /**
   * Fetch live quotes for one or more symbols (e.g. ["BTC", "AAPL", "EUR/USD"]).
   */
  public async getQuotes(symbols: string[]): Promise<Quote[]> {
    const query = encodeURIComponent(symbols.join(","));
    const res = await this.request<{ as_of: string; quotes: Quote[] }>(`/api/quotes?symbols=${query}`);
    return res.quotes;
  }

  /**
   * Fetch historical daily bars for a given symbol.
   */
  public async getHistory(symbol: string, days = 30): Promise<HistoricalDataResponse> {
    const sym = encodeURIComponent(symbol);
    return this.request<HistoricalDataResponse>(`/api/history?symbol=${sym}&days=${days}`);
  }

  /**
   * Fetch mock/simulated portfolio holdings ledger.
   */
  public async getHoldings(): Promise<Holding[]> {
    const res = await this.request<{ as_of: string; holdings: Holding[] }>("/api/holdings");
    return res.holdings;
  }

  // ── OpenBB Integration ────────────────────────────────────────────────────

  /**
   * Get status of OpenBB platform providers and credentials.
   */
  public async getOpenBBProviders(): Promise<OpenBBProviderInfo> {
    return this.request<OpenBBProviderInfo>("/api/openbb/providers");
  }

  /**
   * Query historical data through the OpenBB multi-provider adapter.
   */
  public async getOpenBBHistorical(options: OpenBBHistoricalOptions): Promise<{
    symbol: string;
    asset_class: string;
    timeframe: string;
    bars: OHLCVBar[];
  }> {
    const params = new URLSearchParams({
      symbol: options.symbol,
      asset_class: options.assetClass,
      timeframe: options.timeframe ?? "1d",
    });

    if (options.startDate) params.set("start_date", options.startDate);
    if (options.endDate) params.set("end_date", options.endDate);
    if (options.provider) params.set("provider", options.provider);

    return this.request(`/api/openbb/historical?${params.toString()}`);
  }

  // ── Portfolio & Positions ─────────────────────────────────────────────────

  /**
   * Get current portfolio capital, exposure, and PnL metrics.
   */
  public async getPortfolio(): Promise<PortfolioState> {
    return this.request<PortfolioState>("/api/v1/portfolio");
  }

  /**
   * Get all active positions.
   */
  public async getPositions(): Promise<Position[]> {
    const res = await this.request<{ positions: Position[]; count: number }>("/api/v1/portfolio/positions");
    return res.positions;
  }

  // ── Risk & Safety ─────────────────────────────────────────────────────────

  /**
   * Get real-time risk metrics from the Risk Governor.
   */
  public async getRiskMetrics(): Promise<RiskMetrics> {
    return this.request<RiskMetrics>("/api/v1/risk");
  }

  /**
   * Get distributed kill switch state.
   */
  public async getKillSwitchStatus(): Promise<KillSwitchStatus> {
    return this.request<KillSwitchStatus>("/api/v1/risk/kill-switch");
  }

  // ── Autonomous Agents ─────────────────────────────────────────────────────

  /**
   * Get status of all autonomous trading agents.
   */
  public async getAgents(): Promise<AgentsSummary> {
    return this.request<AgentsSummary>("/api/v1/agents");
  }

  /**
   * Get status and metrics of a single agent by ID.
   */
  public async getAgent(agentId: number): Promise<AgentHealth> {
    return this.request<AgentHealth>(`/api/v1/agents/${agentId}`);
  }

  // ── Alpha Signals ─────────────────────────────────────────────────────────

  /**
   * Get latest NLP sentiment signal for a symbol.
   */
  public async getSentiment(symbol: string): Promise<SignalData> {
    const sym = encodeURIComponent(symbol);
    return this.request<SignalData>(`/api/v1/signals/sentiment/${sym}`);
  }

  /**
   * Get current macroeconomic regime classification.
   */
  public async getMacroRegime(): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("/api/v1/signals/macro");
  }

  // ── Real-Time WebSocket Streaming ─────────────────────────────────────────

  /**
   * Connect to the live dashboard WebSocket stream with automatic reconnection.
   */
  public subscribeDashboard(options: WebSocketSubscriptionOptions = {}): {
    close: () => void;
    send: (data: unknown) => void;
  } {
    if (!this.customWebSocket) {
      throw new Error("WebSocket implementation is not available. Please provide options.WebSocket.");
    }

    const wsUrl = this.baseUrl.replace(/^http(s)?:\/\//, "ws$1://") + "/ws/dashboard";
    let ws: WebSocket | null = null;
    let shouldReconnect = true;
    let reconnectAttempts = 0;
    const maxAttempts = options.maxReconnectAttempts ?? 10;
    const reconnectInterval = options.reconnectIntervalMs ?? 3000;

    const connect = () => {
      try {
        ws = new this.customWebSocket!(wsUrl);

        ws.onopen = () => {
          reconnectAttempts = 0;
          options.onOpen?.();
        };

        ws.onmessage = (event: MessageEvent) => {
          try {
            const data = JSON.parse(event.data) as WebSocketMessage;
            options.onMessage?.(data);
          } catch {
            // raw string data fallback
            options.onMessage?.({
              type: "raw",
              timestamp: new Date().toISOString(),
              payload: event.data,
            });
          }
        };

        ws.onerror = (event: Event) => {
          options.onError?.(event);
        };

        ws.onclose = (event: CloseEvent) => {
          options.onClose?.(event);
          if (shouldReconnect && reconnectAttempts < maxAttempts) {
            reconnectAttempts++;
            setTimeout(connect, reconnectInterval);
          }
        };
      } catch (err) {
        if (shouldReconnect && reconnectAttempts < maxAttempts) {
          reconnectAttempts++;
          setTimeout(connect, reconnectInterval);
        }
      }
    };

    connect();

    return {
      close: () => {
        shouldReconnect = false;
        ws?.close();
      },
      send: (data: unknown) => {
        if (ws && ws.readyState === 1 /* OPEN */) {
          ws.send(typeof data === "string" ? data : JSON.stringify(data));
        }
      },
    };
  }
}
