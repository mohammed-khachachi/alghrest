import { wsClient } from '@/lib/websocket';

export const socket = {
  get connected(): boolean {
    return wsClient.isConnected();
  },
  connect: (): void => wsClient.connect(),
  disconnect: (): void => wsClient.disconnect(),
};

export const initializeSocketListeners = (): void => {
  // Native WebSocket messages are dispatched inside DashboardWebSocketClient.
};

export const connectSocket = (): void => {
  wsClient.connect();
};

export const disconnectSocket = (): void => {
  wsClient.disconnect();
};
