# ALGHREST 🤖📈

> **Production-grade autonomous multi-agent trading system — 32 agents, 7 tiers**

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Kafka](https://img.shields.io/badge/Kafka-7.6.1-black?logo=apachekafka)](https://kafka.apache.org)
[![Redis](https://img.shields.io/badge/Redis-7-red?logo=redis)](https://redis.io)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue?logo=docker)](https://docker.com)
[![License](https://img.shields.io/badge/License-Proprietary-red)](#)

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Architecture — 7-Tier Agent System](#-architecture--7-tier-agent-system)
- [Agent Roster](#-agent-roster)
- [Technology Stack](#-technology-stack)
- [Infrastructure](#-infrastructure)
- [Project Structure](#-project-structure)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Backtesting Engine](#-backtesting-engine)
- [Risk Management](#-risk-management)
- [Monitoring & Observability](#-monitoring--observability)
- [Development](#-development)
- [Roadmap](#-roadmap)

---

## 🌐 Overview

**ALGHREST** is a fully autonomous, event-driven algorithmic trading platform built on a hierarchical multi-agent architecture. Thirty-two specialized AI agents communicate via Apache Kafka, share real-time state through Redis, and persist time-series data in TimescaleDB.

### Key Capabilities

| Capability | Detail |
|---|---|
| **Markets** | Crypto (spot + perps + options), US Equities, DeFi on-chain |
| **Exchanges** | Binance, Bybit, Coinbase, Kraken, Alpaca, OKX, Deribit, IBKR |
| **AI Brain** | Anthropic Claude (Opus for reasoning, Sonnet for analysis) |
| **Strategies** | Trend-following, mean-reversion, arbitrage, RL, DeFi yield |
| **Data Feeds** | RSS news, Twitter/X, Reddit, Glassnode, Nansen, FRED, on-chain RPCs |
| **Environments** | `development` → `paper_trading` → `live` |

> ⚠️ **DISCLAIMER**: This software is for educational purposes. Algorithmic trading involves substantial financial risk. Always start with paper trading.

---

## 🏗 Architecture — 7-Tier Agent System

```
┌─────────────────────────────────────────────────────────────────┐
│  TIER 1 — Executive Layer (CIO + Risk Governor)                 │
│  Strategic decisions, capital allocation, kill switch           │
├─────────────────────────────────────────────────────────────────┤
│  TIER 2 — Intelligence Layer (6 agents)                         │
│  Market data, news NLP, sentiment, macro, geopolitics, on-chain │
├─────────────────────────────────────────────────────────────────┤
│  TIER 3 — Quant Analysis Layer (3 agents)                       │
│  Technical analysis, volatility forecasting, correlation engine │
├─────────────────────────────────────────────────────────────────┤
│  TIER 4 — Strategy Layer (8 agents)                             │
│  Independent capital sleeves — each strategy fully isolated     │
├─────────────────────────────────────────────────────────────────┤
│  TIER 5 — Execution Layer (6 agents)                            │
│  Smart order routing, slippage minimization, multi-exchange     │
├─────────────────────────────────────────────────────────────────┤
│  TIER 6 — DeFi Layer (4 agents)                                 │
│  Yield farming, DEX arbitrage, MEV, cross-chain bridging        │
├─────────────────────────────────────────────────────────────────┤
│  TIER 7 — Monitoring Layer (4 agents)                           │
│  Portfolio tracker, Telegram alerts, compliance, reporting      │
└─────────────────────────────────────────────────────────────────┘
         ↕ All agents communicate via Apache Kafka topics ↕
```

### Message Flow

```
Market Data → Intelligence → Quant Analysis → Strategies
                                                   ↓
                              Risk Check → Execution → Exchange
                                                   ↓
                              Monitoring ← Portfolio State
```

---

## 🤖 Agent Roster

### Tier 1 — Executive
| ID | Agent | Role |
|---|---|---|
| 01 | **CIO Agent** | Strategic oversight, Claude Opus reasoning, capital allocation |
| 02 | **Risk Governor** | Portfolio-level risk limits, kill switch, drawdown circuit breakers |

### Tier 2 — Intelligence
| ID | Agent | Role |
|---|---|---|
| 03 | **Market Data Hub** | Real-time OHLCV aggregation from all exchanges via CCXT |
| 04 | **Macro Economist** | FRED data, interest rates, CPI, yield curve analysis |
| 05 | **Sentiment Analyst** | Twitter/X + Reddit social sentiment scoring |
| 06 | **News Analyst** | RSS polling, Claude Sonnet NLP classification, FinBERT sentiment |
| 07 | **Geopolitical Watcher** | Country risk scoring, geopolitical event detection |
| 08 | **On-Chain Sleuth** | Glassnode + Nansen whale tracking, exchange flows, NVT ratio |

### Tier 3 — Quant
| ID | Agent | Role |
|---|---|---|
| 09 | **Technical Analyst** | 50+ indicators via pandas-ta, multi-timeframe confluence |
| 10 | **Volatility Forecaster** | GARCH/EGARCH models, realized vol, IV surface |
| 11 | **Correlation Engine** | Cross-asset correlation matrices, regime detection |

### Tier 4 — Strategies (Capital Sleeves)
| ID | Agent | Approach |
|---|---|---|
| 12 | **Trend Follower** | EMA crossovers, ADX filter, ATR trailing stops |
| 13 | **Mean Reversion** | Bollinger Band squeeze, RSI extremes |
| 14 | **Momentum** | Relative strength, cross-sectional momentum |
| 15 | **Stat Arb** | Pairs trading, cointegration (ADF test) |
| 16 | **ML Predictor** | CNN chart pattern recognition + RL position sizing |
| 17 | **Options Strategist** | Delta-neutral, volatility arbitrage via Deribit |
| 18 | **Macro Rotator** | Risk-on/risk-off regime-based asset rotation |
| 19 | **Breakout Hunter** | Volume-confirmed breakouts, range expansion |

### Tier 5 — Execution
| ID | Agent | Role |
|---|---|---|
| 20 | **Order Router** | Smart order routing across 8 exchanges, best-price selection |
| 21 | **Position Sizer** | Kelly criterion, risk-per-trade limits (max 1%) |
| 22 | **Slippage Minimizer** | TWAP/VWAP execution for large orders |
| 23 | **Hedge Manager** | Portfolio delta hedging, correlation-based hedges |
| 24 | **Fee Optimizer** | Maker/taker routing, rebate optimization |
| 25 | **Liquidation Guard** | Margin monitoring, auto-deleveraging prevention |

### Tier 6 — DeFi
| ID | Agent | Role |
|---|---|---|
| 26 | **Yield Farmer** | Aave, Compound, Curve optimal yield routing |
| 27 | **DEX Arbitrageur** | Uniswap/Curve price discrepancy capture |
| 28 | **MEV Hunter** | Flashbots bundle submission, sandwich detection |
| 29 | **Bridge Strategist** | Cross-chain capital allocation (ETH, ARB, OP, BASE, SOL) |

### Tier 7 — Monitoring
| ID | Agent | Role |
|---|---|---|
| 30 | **Portfolio Tracker** | Real-time PnL, Sharpe, drawdown dashboard |
| 31 | **Alert Manager** | Telegram bot, PagerDuty critical alerts |
| 32 | **Compliance Agent** | Trade logging, position limits, regulatory reporting |

---

## 🛠 Technology Stack

### Core Framework
```
Python 3.12+          — Runtime
FastAPI 0.115         — REST API + WebSocket
Pydantic v2           — Data validation & settings
asyncio               — Async I/O throughout
```

### AI & Agents
```
Anthropic Claude      — CIO (Opus), analysts (Sonnet)
LangGraph 0.2         — Agent orchestration graphs
CrewAI 0.76           — Multi-agent collaboration
spaCy 3.8             — Named entity recognition
transformers 4.45     — FinBERT sentiment models
```

### Trading & Market Data
```
CCXT 4.4 (async)      — 100+ exchange unified API
alpaca-py 0.30        — US equities (Alpaca)
ib-insync 0.9         — Interactive Brokers
web3 6.20             — EVM blockchain interaction
```

### Quantitative Analysis
```
pandas 2.2 / polars 1.0   — Data manipulation
pandas-ta 0.3              — 150+ technical indicators
vectorbt 0.26              — Vectorized backtesting
arch 7.1                   — GARCH/EGARCH volatility models
py-vollib                  — Options pricing (Black-Scholes)
scikit-learn 1.5           — Classical ML models
PyTorch 2.4                — Deep learning (CNN patterns)
stable-baselines3 2.3      — Reinforcement learning (RL)
ray[rllib] 2.35            — Distributed RL training
```

### Infrastructure
```
Apache Kafka 7.6      — Event streaming (3-broker cluster)
Redis 7               — Cache, state, Pub/Sub, Celery broker
TimescaleDB (PG 16)   — Time-series trade & market data
Qdrant 1.11           — Vector DB for semantic memory
Celery 5.4            — Async task queue
```

### Observability
```
Prometheus 2.52       — Metrics collection (30d retention)
Grafana 10.4          — Dashboards & alerting
Sentry 2.16           — Error tracking (FastAPI + Celery)
structlog 24.4        — Structured JSON logging
```

---

## 🏭 Infrastructure

### Docker Services (docker-compose.yml)

| Service | Image | Port | Purpose |
|---|---|---|---|
| `timescaledb` | timescale/timescaledb:pg16 | 5432 | Primary time-series database |
| `redis` | redis:7-alpine | 6379 | Cache + state + task queue |
| `kafka-1/2/3` | confluentinc/cp-kafka:7.6.1 | 9092-9094 | 3-broker Kafka cluster |
| `zookeeper` | cp-zookeeper:7.6.1 | 2181 | Kafka coordination |
| `schema-registry` | cp-schema-registry:7.6.1 | 8081 | Avro schema management |
| `kafka-ui` | provectuslabs/kafka-ui | 8080 | Kafka monitoring UI |
| `prometheus` | prom/prometheus:2.52 | 9090 | Metrics scraping |
| `grafana` | grafana/grafana:10.4 | 3000 | Dashboards |
| `node-exporter` | prom/node-exporter | 9100 | Host system metrics |

### Kafka Topics (16 topics)

```
market.data          — Real-time OHLCV ticks
market.orderbook     — Level 2 order book snapshots
news.raw             — Unprocessed RSS articles
news.tagged          — Claude-classified news signals
sentiment.social     — Twitter/Reddit sentiment scores
analysis.technical   — TA indicator confluence signals
analysis.volatility  — GARCH volatility forecasts
strategy.signals     — Trade proposals from Tier 4
risk.assessments     — Risk governor approvals/rejections
orders.pending       — Orders awaiting execution
orders.filled        — Confirmed fills from exchanges
positions.updates    — Real-time position changes
portfolio.state      — Aggregate portfolio snapshot
alerts.critical      — Kill switch & emergency alerts
onchain.signals      — On-chain whale/flow signals
defi.opportunities   — DeFi yield & arbitrage signals
```

### Network Layout

All services run on the `172.20.0.0/16` bridge network with static IPs for deterministic service discovery.

---

## 📁 Project Structure

```
alghrest/
├── agents/                          # All 32 trading agents
│   ├── base_agent.py                # BaseAgent + BaseStrategy abstractions
│   ├── tier1_executive/             # CIO + Risk Governor
│   ├── tier2_intelligence/          # 6 intelligence agents
│   │   ├── market_data_hub.py
│   │   ├── macro_economist.py
│   │   ├── sentiment_analyst.py
│   │   ├── news_analyst.py          # Claude Sonnet NLP + RSS
│   │   ├── geopolitical_watcher.py
│   │   └── onchain_sleuth.py
│   ├── tier3_quant/                 # 3 quant agents
│   │   ├── technical_analyst.py
│   │   ├── volatility_forecaster.py
│   │   └── correlation_engine.py
│   ├── tier4_strategies/            # 8 strategy agents (capital sleeves)
│   │   └── trend_follower.py
│   ├── tier5_execution/             # 6 execution agents
│   │   └── position_sizer.py
│   ├── tier6_defi/                  # 4 DeFi agents
│   └── tier7_monitoring/            # 4 monitoring agents
│
├── core/                            # Shared core modules
│   ├── config.py                    # Central settings (pydantic-settings)
│   ├── data/
│   │   └── models.py                # All Pydantic data models
│   ├── orchestrator/
│   │   ├── message_bus.py           # Kafka producer/consumer wrappers
│   │   └── state_manager.py        # Redis state management
│   ├── risk/                        # Portfolio risk calculations
│   └── utils/
│       ├── logging.py               # structlog configuration
│       └── metrics.py               # Prometheus metrics registry
│
├── api/                             # FastAPI REST + WebSocket
│   ├── main.py                      # App entry point
│   ├── routes/                      # API route handlers
│   └── websockets/                  # Real-time WS feeds
│
├── connectors/                      # Exchange & data connectors
│   ├── exchanges/                   # CCXT, Alpaca, IBKR wrappers
│   ├── data_providers/              # Glassnode, Nansen, FRED
│   └── chains/                      # EVM + Solana RPC clients
│
├── ml/                              # Machine learning pipeline
│   ├── models/                      # CNN, RL model definitions
│   ├── training/                    # Training scripts
│   └── inference/                   # Real-time inference servers
│
├── backtesting/
│   └── engine.py                    # VectorBT backtesting + validation
│
├── dashboard/                       # Frontend monitoring dashboard
│   ├── app/
│   ├── components/
│   └── lib/
│
├── infra/                           # Infrastructure config
│   ├── init/                        # DB + Kafka initialization scripts
│   ├── prometheus/                  # Prometheus config + alerting rules
│   ├── grafana/                     # Dashboard JSON provisioning
│   ├── k8s/                         # Kubernetes manifests
│   └── terraform/                   # Cloud infrastructure (IaC)
│
├── tests/                           # Test suite
├── docker-compose.yml               # Full infrastructure stack
├── pyproject.toml                   # Dependencies + tool config
└── .env.example                     # Environment variables template
```

---

## 🚀 Quick Start

### Prerequisites

- Docker Desktop + Docker Compose v2
- Python 3.12+
- Poetry (`pip install poetry`)
- 16 GB RAM recommended (Kafka cluster + ML models)

### 1 — Clone & Configure

```bash
git clone https://github.com/your-org/alghrest.git
cd alghrest

# Copy environment template
cp .env.example .env
# Edit .env with your API keys (see Configuration section)
```

### 2 — Start Infrastructure

```bash
# Start all infrastructure services
docker compose up -d

# Verify all services are healthy
docker compose ps

# Check Kafka topics were created
docker compose logs kafka-init
```

### 3 — Install Python Dependencies

```bash
poetry install

# For backtesting extras
poetry install --with backtesting

# Activate virtual environment
poetry shell
```

### 4 — Initialize Database

```bash
# Run Alembic migrations
alembic upgrade head
```

### 5 — Start in Paper Trading Mode

```bash
# Ensure ENVIRONMENT=paper_trading in .env
# Start Tier 2 intelligence agents first
python -m agents.tier2_intelligence.market_data_hub &
python -m agents.tier2_intelligence.news_analyst &

# Start a Tier 4 strategy agent
python -m agents.tier4_strategies.trend_follower &
```

### Service URLs

| Service | URL |
|---|---|
| **API** | http://localhost:8000 |
| **API Docs** | http://localhost:8000/docs |
| **Grafana** | http://localhost:3000 |
| **Kafka UI** | http://localhost:8080 |
| **Prometheus** | http://localhost:9090 |

---

## ⚙️ Configuration

All configuration is managed via environment variables loaded from `.env`. See `.env.example` for the full reference.

### Critical Settings

```bash
# Operating mode — ALWAYS start with paper_trading
ENVIRONMENT=paper_trading          # development | paper_trading | live

# Starting capital
SYSTEM_CAPITAL_USD=10000

# AI — Required for news classification and CIO reasoning
ANTHROPIC_API_KEY=sk-ant-...

# At minimum, configure ONE exchange testnet
BINANCE_TESTNET=true
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_SECRET=...
```

### Environment Progression

```
development      → Local testing, no real orders, mock data allowed
paper_trading    → Real market data, simulated order fills
live             → Real money — requires explicit ENVIRONMENT=live
```

> ⛔ The system will **refuse** to place real orders unless `ENVIRONMENT=live` is set explicitly.

### Risk Limits (Hardcoded)

| Limit | Value |
|---|---|
| Max risk per trade | 1% of capital |
| Max consecutive losses before pause | 5 |
| Max portfolio drawdown | 25% |
| Hot wallet allocation | ≤ 5% of capital |

---

## 📊 Backtesting Engine

Every Tier 4 strategy **must pass** the backtesting gauntlet before going live.

### Validation Thresholds

| Metric | Requirement |
|---|---|
| Historical data | ≥ 5 years |
| Trade frequency | ≥ 50 trades/year |
| Sharpe Ratio (in-sample) | ≥ 1.0 |
| Sharpe Ratio (walk-forward OOS) | ≥ 0.8 |
| Max Drawdown | < 25% |
| Profit Factor | ≥ 1.3 |
| Walk-Forward Efficiency | ≥ 60% |
| Monte Carlo ruin probability | < 1% |
| Monte Carlo 95% VaR | < 15% |

### Usage

```python
from backtesting.engine import BacktestEngine
from core.data.models import Timeframe

engine = BacktestEngine(
    strategy_id="trend_follower",
    strategy_name="EMA Crossover Trend Follower",
    symbol="BTC/USDT",
    timeframe=Timeframe.D1,
    initial_capital=100_000,
)

# Run backtest
result = engine.run(ohlcv_df, entry_signals, exit_signals)

# Walk-forward analysis (8 windows)
wf_result = engine.walk_forward(ohlcv_df, strategy_fn, params)

# Monte Carlo (10,000 simulations)
mc_result = engine.monte_carlo(result)

# Final go/no-go
passed, failures = engine.validate_all(result, wf_result, mc_result)
```

---

## 🛡 Risk Management

### Agent-Level Controls

Every agent inherits **kill switch awareness** — checking Redis before processing:

```python
async def run(self) -> None:
    while True:
        if await self.is_halted():   # Checks Redis kill switch
            await asyncio.sleep(30)
            continue
        # ... normal processing
```

### Strategy-Level Controls

`BaseStrategy` tracks consecutive losses and auto-pauses:

```python
# After 5 consecutive losses → strategy paused automatically
strategy.record_loss()   # Increments counter
strategy.record_win()    # Resets counter to 0
strategy.resume()        # Manual resume after review
```

### Portfolio-Level Controls

- **Kill Switch**: Halt all agents instantly via Redis key
- **Drawdown Circuit Breaker**: Auto-halt at 25% portfolio drawdown
- **Position Limits**: Max positions per strategy sleeve configurable
- **Heartbeat Monitoring**: Agents publish health to Redis every 30s; missing heartbeat = alert

---

## 📈 Monitoring & Observability

### Prometheus Metrics

Each agent exposes metrics on port `9200 + agent_id`:

| Metric | Type | Description |
|---|---|---|
| `agent_status` | Gauge | 1=running, 0=stopped |
| `agent_messages_processed_total` | Counter | Total messages processed |
| `agent_messages_failed_total` | Counter | Processing failures by error type |
| `agent_processing_latency_seconds` | Histogram | Per-message processing time |
| `agent_memory_mb` | Gauge | RSS memory usage |

### Grafana Dashboards

Pre-provisioned dashboards:
- **Portfolio PnL** — Real-time P&L, drawdown, Sharpe
- **Agent Health** — All 32 agent status, heartbeats, error rates
- **Risk Metrics** — Exposure, VaR, correlation heatmap
- **Market Data** — Feed latency, tick rates
- **Kafka Lag** — Consumer group lag per topic

### Alerting

- **Telegram Bot**: Trade signals, daily PnL summary, drawdown alerts
- **PagerDuty**: Critical alerts — kill switch triggered, agent crash, exchange connectivity loss
- **Sentry**: Exception tracking for all agents + API

---

## 🧪 Development

### Running Tests

```bash
# Unit tests (fast, no external services)
pytest -m unit

# Integration tests (requires Docker infrastructure)
pytest -m integration

# Backtesting tests (slow)
pytest -m backtest

# Full suite with coverage
pytest --cov=agents --cov=core --cov-report=html
```

### Code Quality

```bash
# Lint
ruff check .

# Format
black .
isort .

# Type checking
mypy agents/ core/

# All checks (pre-commit)
pre-commit run --all-files
```

### Adding a New Agent

1. Create file in the appropriate tier directory
2. Inherit from `BaseAgent` (or `BaseStrategy` for Tier 4)
3. Implement `initialize()`, `run()`, `shutdown()`
4. Register agent ID (must be unique 1–32)
5. Add to `docker-compose.yml` as a service
6. Write unit tests in `tests/`

```python
from agents.base_agent import BaseAgent

class MyNewAgent(BaseAgent):
    AGENT_ID = 33   # Next available ID

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="my_new_agent")

    async def initialize(self) -> None:
        self.logger.info("initialized")

    async def run(self) -> None:
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue
            # Agent logic here
            await asyncio.sleep(60)

    async def shutdown(self) -> None:
        self.logger.info("shutdown")
```

### Tool Configuration

| Tool | Config Location | Key Settings |
|---|---|---|
| **Ruff** | `pyproject.toml` | Python 3.12, line-length 100 |
| **Black** | `pyproject.toml` | line-length 100 |
| **mypy** | `pyproject.toml` | strict mode |
| **pytest** | `pyproject.toml` | asyncio auto mode, 70% coverage minimum |
| **isort** | `pyproject.toml` | black profile |

---

## 🗺 Roadmap

### v0.1.0 (Done)
- [x] Base agent architecture (BaseAgent + BaseStrategy)
- [x] Kafka message bus with producer/consumer wrappers
- [x] Redis state manager
- [x] Prometheus metrics per agent
- [x] Backtesting engine (VectorBT + walk-forward + Monte Carlo)
- [x] Tier 2 intelligence agents (news, macro, sentiment, on-chain, geopolitical)
- [x] Tier 3 quant agents (TA, volatility, correlation)
- [x] Docker Compose full infrastructure stack

### v0.2.0 (Current — In Progress)
- [x] Tier 1 executive agents (CIO with Claude Opus + Risk Governor)
- [x] Complete Tier 4 strategy agents (momentum, stat-arb, breakout hunter, macro rotator)
- [x] Tier 5 execution agents (order router, slippage minimizer TWAP/VWAP, hedge manager, fee optimizer, liquidation guard)
- [x] Tier 7 monitoring agents (portfolio tracker, alert manager Telegram/PagerDuty, compliance)
- [x] FastAPI REST endpoints + WebSocket feeds
- [x] Docker Compose agent services
- [ ] Dockerfile for Python agents
- [ ] Grafana dashboard provisioning (enhanced)

### v0.3.0
- [ ] Tier 6 DeFi agents (yield farming, DEX arb, MEV)
- [ ] Agent 16 ML Predictor (CNN chart pattern + RL)
- [ ] Agent 17 Options Strategist (Deribit delta-neutral)
- [ ] Telegram copy-signal channel
- [ ] RL position sizing agent (Ray RLlib)

### v0.3.0
- [ ] Tier 6 DeFi agents (yield farming, MEV)
- [ ] Tier 7 monitoring agents (Telegram bot, compliance)
- [ ] CNN chart pattern model training pipeline
- [ ] RL position sizing agent (Ray RLlib)

### v1.0.0
- [ ] Kubernetes deployment manifests
- [ ] Terraform cloud infrastructure (AWS/GCP)
- [ ] Copy trading signal channel
- [ ] Full audit trail & compliance reporting

---

## 🔒 Security

- **Never commit `.env`** — it's gitignored
- Hot wallet holds ≤ 5% of capital; cold storage for the rest
- Use Hashicorp Vault for production secret management (`VAULT_ADDR`)
- Flashbots auth key is separate from trading wallet
- All exchange API keys should be **read + trade only** (no withdrawals)
- Paper trading testnet keys before any live credentials

---

## 📜 License

Proprietary — All rights reserved. Contact the ALGHREST Team for licensing inquiries.

---

<div align="center">

**Built with ⚡ by the ALGHREST Team**

*32 agents. 7 tiers. One mission.*

</div>
