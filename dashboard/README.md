# ALGHREST Dashboard

React 18/TypeScript dashboard and an independent Arabic advisory-assistant page.
The maintained routes are defined in `src/App.tsx`; navigation is in
`src/components/layout/Sidebar.tsx`. Agent/topic counts depend on backend data;
legacy counts displayed by some demo/UI labels are not an inventory of deployed
services.

## Stack and routes

The package manifest/lockfile define React 18, Vite 5, Tailwind CSS, Radix UI,
React Router, TanStack Query, Zustand, Zod and Recharts.

| Route | Purpose |
| --- | --- |
| `/` | Redirects to `/overview` |
| `/overview` | Portfolio overview, holdings and market-data panels |
| `/agents` | Agent status and details |
| `/positions` | Position/trade views |
| `/risk` | Risk limits and alerts |
| `/kafka` | Kafka/topic monitoring |
| `/auditor` | Auditor dashboard |
| `/backtest` | Backtest/simulation view |
| `/investor` | Investor presentation |
| `/assistant` | Separate manual research/evaluation assistant |

## Local development

Use Node.js/npm; the Dockerfile uses Node 20. Install from the committed lockfile.
PowerShell, with terminals starting at the repository root:

```powershell
# Terminal 1: loopback-only demo backend on 8000
poetry run uvicorn api.mock_server:app --host 127.0.0.1 --port 8000
# Terminal 2:
Set-Location dashboard
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/overview`. The mock accepts a blank access key and
returns demo values. Use it for UI work; it does not prove actual account or
market-data health. The general backend also uses 8000, so choose one backend
on that port.

For the protected advisory page, configure its separate local access token and
run `poetry run python -m api.advisor` from the root with
`OPERATING_PROFILE=earn2trade_tcp25`. It binds **8011**. Open
`http://127.0.0.1:5173/assistant`. This page does not connect the trading
WebSocket. See [assistant setup](../docs/manual-assistant.md) and
[local access](../docs/maintenance/access-and-ai-limits.md).

## Connections and access

The Vite dev server binds `127.0.0.1:5173`. Its current proxies are:

| Path | Default target |
| --- | --- |
| `/api` and `/ws` | `http://localhost:8000`, configurable through `VITE_API_URL` |
| `/assistant-api` | `http://127.0.0.1:8011` |
| `/yahoo-api` | Existing Yahoo Finance proxy for the demo UI; not a licensed CME feed |

The WebSocket defaults to the page's same-origin `/ws/dashboard`, using `ws`
or `wss` to match the page protocol. `VITE_WS_URL` can override the full endpoint.
`VITE_API_URL` configures the dev proxy target and is also a Docker build argument;
market-data requests in `src/lib/api.ts` use relative `/api` paths.

Protected general pages use `API_ACCESS_TOKEN`; `/assistant` uses
`ADVISORY_ACCESS_TOKEN`. Tokens are entered in the access gate and retained only
in page memory. Do not put them in Vite variables, browser storage, URLs or Git.
The WebSocket client retries after 3 seconds on disconnect; message channels and
payloads are validated by the schemas in `src/types/ws.ts`. Timing depends on
the connected backend, not a universal update-rate guarantee.

`src/lib/useLiveQuotes.ts` owns shared quote polling every 3 seconds. Subscribe
panels to this hook instead of creating independent `/api/quotes` polling.

## Build and deployment

From `dashboard/`:

```powershell
npm run build
npm run preview
```

`build` runs TypeScript checking then Vite and writes `dist/`. Production hosting
needs SPA routing, correct API/WebSocket reverse proxies and access configuration;
`preview` is a local preview server.

A production image can be built from the dashboard directory:

```powershell
docker build --target production -t alghrest-dashboard .
```

This README's update does not certify an image deployment. Runtime Docker modes
require their documented access/network configuration. See
[root setup](../README.md), [private collaboration](../docs/private-collaboration.md)
and [development workflow](../docs/monorepo-workflow.md) before cross-project work.
The skills under `.agents/skills/` apply only to this dashboard subproject.
