# ALGHREST

Production-oriented autonomous multi-agent trading system built with Python,
Kafka, Redis, TimescaleDB, Anthropic Claude, and a React/Vite dashboard.

This README is a self-contained project guide for local development, testing,
operations, and safe progression from development to paper trading and live use.

## Table of Contents

- [Overview](#overview)
- [Safety Notice](#safety-notice)
- [Technology Stack](#technology-stack)
- [Architecture](#architecture)
- [Execution Pipeline](#execution-pipeline)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Common Commands](#common-commands)
- [Configuration](#configuration)
- [Dashboard Development](#dashboard-development)
- [ML Inference Subsystem](#ml-inference-subsystem)
- [Testing and Quality Gates](#testing-and-quality-gates)
- [Risk Controls](#risk-controls)
- [Kafka Topics](#kafka-topics)
- [Adding an Agent](#adding-an-agent)
- [Deployment Notes](#deployment-notes)
- [Troubleshooting](#troubleshooting)
- [Current Status](#current-status)

## Overview

ALGHREST is an event-driven autonomous trading platform organized as a
hierarchical multi-agent system. Agents communicate through Apache Kafka topics
and shared Redis state. Time-series data is persisted in TimescaleDB, while the
dashboard uses FastAPI REST/WebSocket APIs plus a React 18 frontend.

The system contains roughly 20 trading and intelligence agents across seven
tiers, plus API, dashboard, monitoring, infrastructure, and ML inference
components.

Primary design rules:

- Agents communicate through Kafka and shared Redis state, not direct calls.
- Every runtime agent inherits from `agents/base_agent.py::BaseAgent`.
- Tier 4 strategy agents inherit from `agents/base_agent.py::BaseStrategy`.
- Risk limits are hard rails and must not be softened.
- Real orders are refused unless `ENVIRONMENT=live` is set explicitly.
- Tier 6 DeFi agents are skeleton implementations and must remain disabled in
  production until real integrations and testnet validation are complete.

## Safety Notice

Algorithmic trading can cause financial loss. Start in development mode, then
paper trading, then live only after full validation.

Important safety defaults:

- `ENVIRONMENT=development` or `ENVIRONMENT=paper_trading` for normal work.
- `ENABLE_DEFI_AGENTS=false`.
- Use exchange testnet or paper credentials during development.
- Never commit `.env` or private keys.
- Never grant withdrawal permissions to exchange API keys.
- Hot wallet exposure must remain at or below 5 percent of capital.

Tier 6 DeFi agents are not production-ready. The files exist for architectural
completeness, but protocol integrations for Aave, Curve, Flashbots, bridges,
and chain-specific execution are not complete.

## Technology Stack

Backend:

- Python 3.12
- Poetry
- Pydantic v2
- asyncio
- FastAPI
- aiokafka
- Redis 7
- PostgreSQL 16 / TimescaleDB
- Alembic

Messaging and state:

- Apache Kafka 7.6, three-broker cluster
- Redis for shared state, kill switch, prices, and heartbeats
- Kafka topics defined in `core/data/models.py::KafkaTopic`

AI and ML:

- Anthropic Claude Opus for CIO reasoning
- Anthropic Claude Sonnet for analyst agents
- Prompt caching in `cio_agent` and `news_analyst`
- Separate FastAPI ML inference server in `ml/inference/server.py`

Frontend:

- React 18
- Vite
- Tailwind CSS
- Zustand
- TanStack Query

Infrastructure:

- Docker Compose
- Prometheus
- Grafana
- Nginx
- Scaffolded Kubernetes and Terraform directories

## Architecture

ALGHREST is organized into seven tiers.

```text
Tier 1 - Executive
  CIO Agent, Risk Governor, Proposal Approver

Tier 2 - Intelligence
  Market data, news, sentiment, macro, geopolitics, on-chain, price publisher

Tier 3 - Quant
  Technical analysis, GARCH volatility, correlation engine

Tier 4 - Strategies
  Trend, mean reversion, momentum, statistical arbitrage, breakout,
  macro rotation, cross-exchange arbitrage, ML predictor

Tier 5 - Execution
  Order router, slippage minimizer, hedge manager, fee optimizer,
  liquidation guard, exchange executor

Tier 6 - DeFi
  Yield farmer, DEX arbitrageur, MEV hunter, bridge strategist
  These are skeleton implementations only.

Tier 7 - Monitoring
  Portfolio tracker, alert manager, compliance, auditor, copy-trading channel
```

Agent process pattern:

```python
async def run(self) -> None:
    while True:
        if await self.is_halted():
            await asyncio.sleep(30)
            continue

        # agent work
```

Base classes:

- `BaseAgent` provides Kafka producer, Redis state, logging, lifecycle,
  heartbeat loop, kill-switch guard, and Prometheus metrics.
- `BaseStrategy` adds signal generation, exits, backtesting hooks, and
  automatic strategy pause after five consecutive losses.

## Execution Pipeline

The trading pipeline spans multiple agents and Kafka topics:

```text
strategy
  -> PROPOSALS_BUS
  -> ProposalApprover
  -> PROPOSALS_APPROVED
  -> OrderRouter
  -> ORDERS_PENDING
  -> FeeOptimizer
  -> SlippageMinimizer
  -> ExchangeExecutor
  -> ORDERS_EXECUTED + FILLS_CONFIRMED
```

Two internal flags are used on `ORDERS_PENDING` messages:

- `_optimised=True`: produced by `FeeOptimizer` so it does not reprocess its
  own optimized messages.
- `_child=True`: produced by `SlippageMinimizer` for TWAP/VWAP child orders so
  they are not split again.

Kill switch path:

```text
RISK_ALERTS
  -> KillSwitchEvent / HaltAllStrategies
  -> ExchangeExecutor
  -> connector.cancel_order for tracked orders
```

If a cancel fails, the order remains tracked so the executor can continue fill
polling and retry handling.

## Project Structure

```text
.
|-- agents/                  Runtime agents by tier
|-- api/                     FastAPI production app and mock server
|-- backtesting/             Strategy backtesting engine and validation
|-- connectors/              Market data and exchange/provider connectors
|-- core/                    Models, config, state, risk, messaging
|-- dashboard/               React/Vite dashboard
|-- docs/                    Project documentation
|-- infra/                   Docker, Kubernetes, Terraform, init scripts
|-- ml/                      ML models, training, inference server
|-- scripts/                 Demo, validation, stress-test, deployment helpers
|-- tests/                   Unit, integration, and backtest tests
|-- docker-compose.yml       Full local infrastructure and agent stack
|-- pyproject.toml           Python tooling, pytest, ruff, mypy config
|-- run_agent.py             Universal runtime entrypoint for agents
```

## Quick Start

Prerequisites:

- Windows 11 with PowerShell
- Python 3.12
- Poetry
- Docker Desktop with WSL2 backend
- Node.js and npm for dashboard work

Install Python dependencies:

```powershell
poetry install
```

Install optional backtesting dependencies:

```powershell
poetry install --with backtesting
```

Start infrastructure and agent containers:

```powershell
docker compose up -d
docker compose ps
docker compose logs kafka-init
```

Run database migrations:

```powershell
alembic upgrade head
```

Run a single agent locally:

```powershell
python run_agent.py agents.tier1_executive.cio_agent CIOAgent
python run_agent.py agents.tier2_intelligence.market_data_hub MarketDataHub
```

Start the dashboard for local development:

```powershell
Set-Location dashboard
npm install
npm run dev
```

Dashboard URL:

```text
http://localhost:5173
```

## Common Commands

Infrastructure:

```powershell
docker compose up -d
docker compose ps
docker compose logs kafka-init
docker compose logs -f
docker compose down
```

Tests:

```powershell
pytest -m unit
pytest -m integration
pytest tests/unit/test_models.py::TestX -v
pytest --cov=agents --cov=core --cov-report=html
```

Code quality:

```powershell
ruff check .
black .
isort .
mypy agents/ core/
pre-commit run --all-files
```

Dashboard:

```powershell
Set-Location dashboard
npm install
npm run dev
npm run build
```

Mock API server for dashboard-only work:

```powershell
python api/mock_server.py
```

Mock API URL:

```text
http://localhost:8000
```

ML inference server:

```powershell
Set-Location ml
python inference/server.py
```

ML prediction URL:

```text
http://localhost:8080/predict
```

Kill switch utilities:

```powershell
python scripts/demo_kill_switch.py
python scripts/run_kill_switch_stress_test.py
```

Universal agent runner:

```powershell
python run_agent.py <module_path> <ClassName>
```

Example:

```powershell
python run_agent.py agents.tier1_executive.cio_agent CIOAgent
```

## Configuration

All settings flow through `core/config.py::Settings`, which loads `.env`.

Minimum local configuration:

```powershell
ENVIRONMENT=development
SYSTEM_CAPITAL_USD=10000
ENABLE_DEFI_AGENTS=false
ANTHROPIC_API_KEY=sk-ant-...
```

Exchange configuration should start with testnet or paper trading:

```powershell
BINANCE_TESTNET=true
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_SECRET=...

ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_API_KEY=...
ALPACA_SECRET=...

DERIBIT_TESTNET=true
DERIBIT_API_KEY=...
DERIBIT_SECRET=...
```

Environment progression:

```text
development -> paper_trading -> live
```

The system refuses real orders unless:

```powershell
ENVIRONMENT=live
```

is set explicitly.

## Dashboard Development

For dashboard-only work, use the mock API server instead of the full
infrastructure stack.

Terminal 1:

```powershell
python api/mock_server.py
```

Terminal 2:

```powershell
Set-Location dashboard
npm run dev
```

Important dashboard conventions:

- Dashboard routes live in `dashboard/src/pages/`.
- Sidebar routing source of truth is `dashboard/src/components/layout/Sidebar.tsx`.
- Market quote polling source of truth is
  `dashboard/src/lib/useLiveQuotes.ts`.
- Do not add per-panel polling to `/api/quotes`.
- `PortfolioOverview`, `HoldingsPanel`, and `MarketDataPanel` should subscribe
  to the shared live quote hook.
- `api/main.py` is the production FastAPI app.
- `api/mock_server.py` is a separate development mock.
- Both apps mount market-data routes from `api/routes/quotes.py`.

## ML Inference Subsystem

Agent 16, `agents/tier4_strategies/ml_predictor.py`, does not load models
in-process. It is an HTTP client that posts a 64-period OHLCV window to the ML
inference server.

ML server:

```text
ml/inference/server.py
```

Prediction endpoint:

```text
POST http://localhost:8080/predict
```

Model files:

```text
ml/models/cnn_pattern.py
ml/models/rl_position_sizer.py
ml/weights/cnn_btc_usdt.pth
ml/weights/ppo_position_sizer.zip
```

Training entrypoint:

```text
ml/training/train.py
```

Deployment note: the inference server is a separate process and should not be
added to the standard `run_agent.py` agent flow.

## Testing and Quality Gates

Pytest markers:

- `unit`
- `integration`
- `backtest`
- `live`

Coverage:

- Coverage gate is enabled in `pyproject.toml`.
- Minimum project coverage target is 70 percent across `agents/` and `core/`.

Tooling:

- Ruff target: Python 3.12
- Ruff line length: 100
- Black line length: 100
- isort profile: Black
- mypy strict mode for `agents/` and `core/`

Backtest validation thresholds before a strategy can go live:

- At least five years of data.
- At least 50 trades per year.
- In-sample Sharpe ratio at least 1.0.
- Walk-forward out-of-sample Sharpe ratio at least 0.8.
- Maximum drawdown below 25 percent.
- Profit factor at least 1.3.
- Walk-forward efficiency at least 60 percent.
- Monte Carlo risk of ruin below 1 percent.
- Monte Carlo 95 percent VaR below 15 percent.

## Risk Controls

Hard limits:

- Max risk per trade: 1 percent of capital.
- Auto-pause strategy after five consecutive losses.
- Max portfolio drawdown: 25 percent.
- Hot wallet maximum: 5 percent of capital.
- Real orders require explicit `ENVIRONMENT=live`.
- DeFi agents must remain disabled unless protocol integrations are complete.

Risk modules:

```text
core/risk/kill_switch.py
core/risk/position_limits.py
core/risk/risk_engine.py
```

Risk agents:

- Risk Governor
- Proposal Approver
- Compliance Agent
- Alert Manager
- Auditor Agent

## Kafka Topics

Kafka topic names are centralized in:

```text
core/data/models.py::KafkaTopic
```

Topics are created by:

```text
infra/init/kafka-init.sh
```

Auto-create is off. When adding a topic, update both the enum and the init
script.

The stack currently expects 18 topics, including the legacy
`orders.approved` alias.

## Adding an Agent

1. Create the file under the correct `agents/tierN_*` directory.
2. Inherit `BaseAgent`, or `BaseStrategy` for Tier 4 strategy agents.
3. Set a unique `AGENT_ID`.
4. Implement `initialize()`, `run()`, and `shutdown()`.
5. Include the kill-switch guard in the run loop.
6. Publish via `BaseAgent.publish(topic, payload)`.
7. Consume via `self.make_consumer([topics])`.
8. Add a Docker Compose service using the `run_agent.py` pattern.
9. Test locally with the universal runner.

Example:

```powershell
python run_agent.py agents.tierN_category.agent_file AgentClass
```

Prometheus metrics are exposed automatically by `BaseAgent.start()` on:

```text
9200 + AGENT_ID
```

Known recent ID assignments:

- `momentum`: 17
- `stat_arb`: 21
- `macro_rotator`: 34
- `yield_farmer`: 35
- `copy_trading_channel`: 36
- `auditor_agent.py`: 33

## Deployment Notes

Local full stack:

```powershell
docker compose up -d
```

Validate Kafka topics:

```powershell
docker compose logs kafka-init
```

Production caution:

- Verify `.env` has no development secrets.
- Use paper trading before live.
- Keep `ENABLE_DEFI_AGENTS=false` until DeFi agents are implemented properly.
- Validate strategy backtests before enabling strategy capital allocation.
- Confirm exchange credentials have no withdrawal permissions.
- Confirm monitoring, alerting, and kill switch behavior before live execution.

Infrastructure directories:

```text
infra/k8s/
infra/terraform/
```

These are scaffold-only and should not be treated as production-ready without
additional work.

## Troubleshooting

Kafka topics missing:

```powershell
docker compose logs kafka-init
docker compose ps
```

Dashboard has no live quotes:

- Start `api/mock_server.py` for dashboard-only development.
- Confirm the dashboard points at `http://localhost:8000`.
- Confirm consumers use `dashboard/src/lib/useLiveQuotes.ts`.

ML predictor cannot call `/predict`:

- Start `ml/inference/server.py`.
- Confirm port `8080` is available.
- Confirm trained weights exist in `ml/weights/`.

Integration tests fail:

- Confirm Docker Compose services are up.
- Confirm Kafka, Redis, and TimescaleDB are healthy.
- Run unit tests first to isolate pure Python failures.

TA-Lib install issues:

- Ubuntu: `apt-get install ta-lib`
- macOS: `brew install ta-lib`
- Windows: install the appropriate wheel or binary build for your Python
  version.

## Current Status

Completed:

- Agent ID collisions resolved.
- Agent 16 ML predictor implemented as an inference-server client.
- Compliance agent duplicate removed.
- Infrastructure stack validation completed.
- Dashboard mock server supports agent and market data development.

Pending:

- Tier 6 DeFi protocol integrations.
- Agent 17 `options_strategist.py` for Deribit delta-neutral strategy.
- ML inference server startup automation.
- Deployment automation improvements.
- Reuters RSS replacement.
- PortfolioTracker Sharpe calculation fixes.

## License and Disclaimer

This repository appears to be proprietary/private project code. Do not expose
credentials, API keys, exchange secrets, wallet keys, or private infrastructure
details in commits, logs, screenshots, or public artifacts.

This software is not financial advice. Use at your own risk and validate every
strategy in development and paper trading before any live use.
