import {
  WsMessageSchema,
  PortfolioSnapshotSchema,
  AgentsPayloadSchema,
  PositionsPayloadSchema,
  KafkaPayloadSchema,
  RiskAlertPayloadSchema,
  SystemStatusSchema,
  RiskLimitsPayloadSchema,
} from '@/types/ws';
import { useDashboardStore } from '@/store/useStore';

const WS_URL = import.meta.env['VITE_WS_URL'] ?? 'ws://localhost:8000/ws/dashboard';
const RECONNECT_DELAY_MS = 3000;

class DashboardWebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private intentionalClose = false;

  connect(): void {
    if (
      this.ws?.readyState === WebSocket.OPEN ||
      this.ws?.readyState === WebSocket.CONNECTING
    ) {
      return;
    }

    this.intentionalClose = false;
    this._open();
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.ws?.close();
    this.ws = null;
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }

  private _open(): void {
    const store = useDashboardStore.getState();
    store.setWsStatus('connecting');
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }

    try {
      const ws = new WebSocket(WS_URL);
      ws.binaryType = 'arraybuffer';
      this.ws = ws;
    } catch {
      store.setWsStatus('error');
      this._scheduleReconnect();
      return;
    }

    const currentWs = this.ws;

    currentWs.onopen = () => {
      if (this.ws !== currentWs) return;
      store.setWsStatus('connected');
    };

    currentWs.onclose = () => {
      if (this.ws !== currentWs) return;
      this.ws = null;
      if (this.intentionalClose) return;
      store.setWsStatus('disconnected');
      this._scheduleReconnect();
    };

    currentWs.onerror = () => {
      if (this.ws !== currentWs) return;
      store.setWsStatus('error');
    };

    currentWs.onmessage = (event: MessageEvent) => {
      if (this.ws !== currentWs) return;
      try {
        let raw: unknown;
        if (event.data instanceof ArrayBuffer) {
          raw = JSON.parse(new TextDecoder().decode(event.data));
        } else {
          raw = JSON.parse(event.data as string);
        }

        const parsed = WsMessageSchema.safeParse(raw);
        if (!parsed.success) return;

        this._dispatch(parsed.data.channel, parsed.data.data);
      } catch {
        // Malformed message — ignore
      }
    };
  }

  private _dispatch(channel: string, data: unknown): void {
    const store = useDashboardStore.getState();
    switch (channel) {
      case 'portfolio.snapshot': {
        const result = PortfolioSnapshotSchema.safeParse(data);
        if (result.success) store.updatePortfolioSnapshot(result.data);
        break;
      }
      case 'agents.heartbeats': {
        const result = AgentsPayloadSchema.safeParse(data);
        if (result.success) store.updateAgentsPayload(result.data);
        break;
      }
      case 'positions.updates': {
        const result = PositionsPayloadSchema.safeParse(data);
        if (result.success) store.updatePositions(result.data);
        break;
      }
      case 'kafka.metrics': {
        const result = KafkaPayloadSchema.safeParse(data);
        if (result.success) store.updateKafkaMetrics(result.data);
        break;
      }
      case 'risk.alerts': {
        const result = RiskAlertPayloadSchema.safeParse(data);
        if (result.success) {
          store.addRiskAlert(result.data.alert);
          store.addToast({
            id: result.data.alert.alert_id,
            severity: result.data.alert.severity,
            message: result.data.alert.message,
            dismissAfterMs: result.data.alert.severity === 'CRITICAL' ? null : 8000,
          });
        }
        break;
      }
      case 'system.status': {
        const result = SystemStatusSchema.safeParse(data);
        if (result.success) {
          store.updateSystemStatus(result.data);
          if (result.data.kill_switch_active) {
            store.addToast({
              id: 'kill-switch',
              severity: 'CRITICAL',
              message: `KILL SWITCH ACTIVATED: ${result.data.kill_switch_reason ?? 'Manual trigger'}`,
              dismissAfterMs: null,
              fullScreen: true,
            });
          }
        }
        break;
      }
      case 'risk.limits': {
        const result = RiskLimitsPayloadSchema.safeParse(data);
        if (result.success) store.updateRiskLimits(result.data.limits);
        break;
      }
    }
  }

  private _scheduleReconnect(): void {
    if (this.intentionalClose || this.reconnectTimer) return;
    this.reconnectTimer = setTimeout(() => this._open(), RECONNECT_DELAY_MS);
  }
}

export const wsClient = new DashboardWebSocketClient();
