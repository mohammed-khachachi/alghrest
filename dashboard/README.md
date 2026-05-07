# ALGHREST Dashboard

Real-time monitoring dashboard for the ALGHREST 32-agent trading system.

## Tech Stack

- React 18 + TypeScript (strict mode)
- Vite 5
- TailwindCSS + shadcn/ui primitives (Radix UI)
- Recharts
- Zustand (state)
- Zod (WebSocket message validation)
- React Router v6

## Pages

| Route | Description |
|-------|-------------|
| `/overview` | KPI cards, cumulative PnL chart, risk gauges |
| `/agents` | 32-agent grid with tier/status filter + detail modal |
| `/positions` | Open positions table + closed trades |
| `/kafka` | 16 topic cards with sparklines + flow diagram |
| `/risk` | Alert feed, risk limits table, correlation heatmap |

## Quick Start (local dev)

```bash
cd dashboard
npm install
npm run dev
```

Dashboard at http://localhost:5173 — connects to `ws://localhost:8000/ws/dashboard`.

Set `VITE_WS_URL` to override the WebSocket URL:

```bash
VITE_WS_URL=ws://my-server:8000/ws/dashboard npm run dev
```

## Docker (dev server with hot reload)

```bash
# From repo root
docker compose up dashboard nginx
```

- Dashboard: http://localhost:5173 (direct Vite)
- Via Nginx: http://localhost:80 (proxied, WebSocket-aware)

## Production Build

```bash
cd dashboard
npm run build          # outputs to dist/
```

Or via Docker multi-stage:

```bash
docker build --target production -t alghrest-dashboard .
```

## WebSocket Protocol

All messages use the shape `{ channel, data, timestamp }`.

| Channel | Payload | Update rate |
|---------|---------|-------------|
| `portfolio.snapshot` | Portfolio KPIs + PnL history | 1 s |
| `agents.heartbeats` | 32 agent status objects | 1 s |
| `positions.updates` | Open/closed positions | 2 s |
| `kafka.metrics` | 16 topic metrics | 2 s |
| `risk.alerts` | Single alert (pub/sub) | real-time |
| `system.status` | Status, kill switch | 1 s |
| `risk.limits` | Limit thresholds | 5 s |

On disconnect the banner "Reconnecting..." appears and the client retries every 3 s.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_WS_URL` | `ws://localhost:8000/ws/dashboard` | WebSocket endpoint |
| `VITE_API_URL` | `http://localhost:8000` | REST API base URL |
