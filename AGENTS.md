# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Stack

- **Python 3.12 + Poetry**, Pydantic v2, asyncio everywhere
- **Apache Kafka 7.6** (3-broker cluster) for inter-agent messaging via `aiokafka`
- **Redis 7** for shared state, kill switch, heartbeats
- **TimescaleDB (PG 16)** for time-series persistence
- **Anthropic Claude** — Opus for the CIO agent, Sonnet for analyst agents (NLP). Prompt caching is enabled in `cio_agent` (1h TTL) and `news_analyst` (5m TTL).
- **Dashboard**: React 18 + Vite + Tailwind + Zustand (in `dashboard/`)

## Common commands

```powershell
# Install (Poetry; project uses Python 3.12)
poetry install
poetry install --with backtesting    # add quantstats / pyfolio-reloaded

# Run the full infra stack + agent containers
docker compose up -d
docker compose ps
docker compose logs kafka-init       # confirm 18 topics created

# Run a single agent locally — uses run_agent.py as universal entry
python run_agent.py agents.tier1_executive.cio_agent CIOAgent
python run_agent.py agents.tier2_intelligence.market_data_hub MarketDataHub

# DB migrations
alembic upgrade head

# Tests (markers: unit | integration | backtest | live)
pytest -m unit
pytest -m integration               # needs docker compose stack up
pytest tests/unit/test_models.py::TestX -v   # single test
pytest --cov=agents --cov=core --cov-report=html

# Lint / format / type-check
ruff check .
black .
isort .
mypy agents/ core/                  # strict mode
pre-commit run --all-files

# Dashboard (React/Vite)
Set-Location dashboard; npm install; npm run dev    # http://localhost:5173

# ML inference server (required for Agent 16 ml_predictor)
Set-Location ml; python inference/server.py          # http://localhost:8080/predict

# Mock server (for dashboard development without real backend)
python api/mock_server.py                    # http://localhost:8000 (fakes all agents)

# Demo and testing utilities
python scripts/demo_kill_switch.py           # Interactive kill switch demo (Arabic UI)
python scripts/run_kill_switch_stress_test.py  # Stress test kill switch system

# Additional utilities (in scripts/)
# - Deployment automation and infrastructure validation scripts available

# Universal agent runner (used by Docker services)
python run_agent.py <module_path> <ClassName>  # Universal entry point for all agents
python run_agent.py agents.tier1_executive.cio_agent CIOAgent
```

**Ta-lib dependency note:** pandas-ta requires separate ta-lib binary installation:
- Ubuntu: `apt-get install ta-lib`  
- macOS: `brew install ta-lib`
- Windows: Download from https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib

**Windows development note:** Use PowerShell for all commands below. Docker Desktop with WSL2 backend recommended for best performance.

Note: pytest's coverage gate (`--cov-fail-under=70`) is **enabled** in `pyproject.toml` (the integration suite now covers the core pipeline). Target 70% minimum across `agents/` and `core/`.

## Architecture

ALGHREST is a 37-service autonomous trading system with ~20 trading agents organised in 7 tiers. Agents communicate **only** through Kafka topics and shared Redis state — there are no direct calls between agents.

```
Tier 1 — Executive (CIO Opus, Risk Governor, ProposalApprover)
Tier 2 — Intelligence (market data, news, sentiment, macro, geopolitics, on-chain, price publisher)
Tier 3 — Quant (technical analyst, GARCH volatility, correlation engine)
Tier 4 — Strategies (trend, mean-rev, momentum, stat-arb, breakout, macro rotator, cross-ex arb, ml_predictor, **hmm_regime** [Agent 37]; options_strategist still pending)
Tier 5 — Execution (order router, slippage minimizer, hedge mgr, fee optimizer, liquidation guard, exchange executor; position_sizer is a helper, not a runtime agent)
Tier 6 — DeFi (yield_farmer, dex_arbitrageur, mev_hunter, bridge_strategist — ⚠️ SKELETON IMPLEMENTATIONS ONLY, NOT PRODUCTION-READY)
Tier 7 — Monitoring (portfolio tracker, alert manager, compliance, auditor, copy-trading channel)
```

### The trade execution pipeline (memorise this — it spans many files)

```
strategy → PROPOSALS_BUS
        → ProposalApprover (PositionLimitChecker gate)
        → PROPOSALS_APPROVED
        → OrderRouter (picks exchange + algo)
        → ORDERS_PENDING
        → FeeOptimizer (post-only upgrade, in-place; sets _optimised=True)
        → SlippageMinimizer (TWAP/VWAP child split; sets _child=True)
        → ExchangeExecutor → ORDERS_EXECUTED + FILLS_CONFIRMED
```

Two non-obvious flags piggyback on `ORDERS_PENDING` messages:
- `_optimised=True` — FeeOptimizer skips messages it has already produced (avoids re-entry).
- `_child=True` — SlippageMinimizer marks its TWAP/VWAP child orders so it won't re-split them.

Kill switch path: `RISK_ALERTS` carries `KillSwitchEvent` / `HaltAllStrategies`. `ExchangeExecutor` listens and calls `connector.cancel_order` for every tracked order; failed cancels stay tracked for fill-poll retry.

## ⚠️ CRITICAL: Tier 6 DeFi Safety Warning

**DO NOT ENABLE DeFi AGENTS IN PRODUCTION**

Tier 6 DeFi agents (`yield_farmer`, `dex_arbitrageur`, `mev_hunter`, `bridge_strategist`) contain **SKELETON IMPLEMENTATIONS** with **MOCK LOGIC**. They are **HIGH RISK** and **NOT PRODUCTION-READY**.

- Set `ENABLE_DEFI_AGENTS=false` in `.env` (this is the default)
- These agents exist for architectural completeness but lack proper protocol integrations
- Aave, Curve, Flashbots, and bridge SDKs are not yet implemented
- **Using these agents with real funds WILL result in loss of capital**

Only enable after implementing proper DeFi protocol integrations and extensive testing on testnets.

### Base classes (always inherit, never duplicate)

- `agents/base_agent.py::BaseAgent` — every agent inherits this. Provides `self.producer` (Kafka), `self.state` (Redis), `self.logger`, lifecycle (`initialize/run/shutdown`), heartbeat loop, kill-switch guard (`await self.is_halted()`), and Prometheus metrics on port `9200 + agent_id`.
- `agents/base_agent.py::BaseStrategy` — Tier 4 only. Adds `generate_signal`, `should_exit`, `backtest`, plus `record_loss/record_win/resume` (auto-pauses after 5 consecutive losses).

Standard agent run loop:
```python
async def run(self) -> None:
    while True:
        if await self.is_halted():
            await asyncio.sleep(30)
            continue
        # ... agent logic
```

### Topics

All Kafka topic names are centralised in `core/data/models.py::KafkaTopic` (string enum). Kafka topics are created up front by `infra/init/kafka-init.sh` (18 topics including the legacy `orders.approved` alias) — auto-create is **off**. If you add a topic, update both the enum and the init script.

### State & messaging primitives

- `core/orchestrator/message_bus.py::AlghrestProducer` / `AlghrestConsumer` wrap aiokafka. Use `BaseAgent.publish(topic, payload)` and `self.make_consumer([topics])` rather than instantiating these directly.
- `core/orchestrator/state_manager.py::StateManager` is the singleton Redis client (`self.state` on every agent). Carries kill switch, agent health, and `prices:{symbol}` JSON (60s TTL, written by `PricePublisher`).
- `core/risk/kill_switch.py`, `core/risk/position_limits.py`, `core/risk/risk_engine.py` — risk plumbing used by Risk Governor and ProposalApprover.

### Adding a new agent

1. File under the correct `agents/tierN_*/` directory.
2. Inherit `BaseAgent` (or `BaseStrategy` for Tier 4). Set unique `AGENT_ID` (range now 1–36+).
3. Implement `initialize() / run() / shutdown()`. Always include the kill-switch guard in `run()`.
4. Test locally: `python run_agent.py agents.tierN_category.agent_file AgentClass`
5. Add a service to `docker-compose.yml` using the same `run_agent.py` pattern.
6. Expose Prometheus port = `9200 + AGENT_ID` (handled automatically by `BaseAgent.start()`).

### Agent ID assignments (recently resolved)

**Resolved collisions:** Agent ID conflicts have been fixed with the following reassignments:
- `momentum`: 14 → **17**
- `stat_arb`: 15 → **21**  
- `macro_rotator`: 18 → **34**
- `yield_farmer`: 26 → **35**
- `copy_trading_channel`: 33 → **36**

**Remaining issues:**
- ID **33** — `auditor_agent.py` (outside 1–32 range, but acceptable)

The system now supports 36+ agents with proper Prometheus port isolation.

**New agent:**
- ID **37** — `agents/tier4_strategies/hmm_agent.py` → `HMMAgent` (HMM Regime Detection, Tier 4, paper-only)

### ML inference subsystem (`ml/` + Agent 16)

The ML predictor strategy does **not** load models in-process. Instead:

- `ml/models/cnn_pattern.py::CandlestickCNN` and `ml/models/rl_position_sizer.py` are loaded by `ml/inference/server.py` (FastAPI) which serves `POST /predict` on **port 8080**.
- `agents/tier4_strategies/ml_predictor.py` (Agent 16) is just an HTTP client — it builds a 64-period OHLCV window and POSTs to `http://localhost:8080/predict`.
- Trained weights live in `ml/weights/` (`cnn_btc_usdt.pth`, `ppo_position_sizer.zip`); training entry is `ml/training/train.py`.

When deploying, the inference server is a **separate process** from the agent. Don't add it to the standard `run_agent.py` flow.

### Other moving parts worth knowing

- `api/main.py` is the production FastAPI app (REST + WebSocket dashboard feed). `api/mock_server.py` is a **separate dev-only mock** that fakes all 36+ agents and live data — use this for dashboard development when you don't want to spin up the full infrastructure stack. They both bind a FastAPI app named `app`; don't run them on the same port. The market-data routes in `api/routes/quotes.py` (`/api/symbols`, `/api/quotes`, `/api/history`, `/api/holdings`) are mounted on **both** apps.
- `core/telegram/bot.py` + `bot_manager.py` back the Tier 7 alert manager and copy-trading channel. Telegram credentials (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`) come from `core/config.py` settings. The bot broadcasts formatted trade signals with Arabic UI support.
- `infra/k8s/` and `infra/terraform/` exist but are scaffold-only (a few manifests / `main.tf` + `variables.tf`). Don't treat them as production-ready deploy targets without filling them in.
- `connectors/data_providers/` is the dashboard-facing market-data layer (separate from the Kafka agent fabric). `base.py` defines the `QuoteProvider` ABC + `ANCHOR_DATE` (currently `2025-05-11`); `{crypto,forex,equity}_provider.py` ship as deterministic mocks designed to be swapped for ccxt/CoinGecko, Alpha Vantage/ExchangeRate-API, and Alpaca/Finnhub. Replace only the `quote()` / `history()` bodies — router, catalog (24 symbols), and the 8-position mock ledger in `holdings.py` stay untouched.
- `dashboard/src/lib/useLiveQuotes.ts` is the **single source of truth for dashboard quote polling** — one TanStack Query call every 3s, shared across `PortfolioOverview`, `HoldingsPanel`, and `MarketDataPanel`. Do not add per-panel polling to `/api/quotes`; subscribe to this hook instead so all panels stay in lockstep and the backend only sees one request.
- Dashboard pages live in `dashboard/src/pages/`: `Overview` (default), `Agents`, `Positions`, `Risk`, `Kafka`, plus three newer surfaces — `AuditorDashboard`, `BacktestSimulation`, `InvestorPitch`. `components/layout/Sidebar.tsx` is the routing source of truth.
- `CLAUDE.md` is the canonical sibling of this file. When the two drift, prefer CLAUDE.md.

## Risk rails (hard limits — don't soften)

- Max risk per trade: **1%** of capital (enforced in `BaseStrategy.__init__` via `min(risk_per_trade, 0.01)`).
- Auto-pause strategy after **5 consecutive losses**.
- Max portfolio drawdown: **25%** (Risk Governor circuit breaker).
- Hot wallet ≤ **5%** of capital.
- The system **refuses real orders unless** `ENVIRONMENT=live` is set explicitly. Default is `paper_trading`.

## Backtest validation thresholds (Tier 4)

Strategies must pass all of these in `backtesting/engine.py::BacktestEngine.validate_all` before going live: ≥5y data, ≥50 trades/yr, IS Sharpe ≥1.0, walk-forward OOS Sharpe ≥0.8, max DD <25%, profit factor ≥1.3, walk-forward efficiency ≥60%, Monte Carlo ruin <1%, MC 95% VaR <15%.

## Environment & secrets

All settings flow through `core/config.py::Settings` (pydantic-settings, loads `.env`). Use `from core.config import settings`.

### Critical Environment Variables

```powershell
# Operating environment (ALWAYS start with development or paper_trading)
ENVIRONMENT=development          # development | paper_trading | live
SYSTEM_CAPITAL_USD=10000         # Starting capital in USD

# DeFi Safety Override (CRITICAL - keep false until protocol integrations complete)
ENABLE_DEFI_AGENTS=false         # Force disable DeFi agents for safety

# AI (required for CIO Opus reasoning and news analysis)
ANTHROPIC_API_KEY=sk-ant-...
```

### Exchange Configuration

Start with **testnet/paper trading** only:

```powershell
# Binance (prefer testnet during development)
BINANCE_TESTNET=true
BINANCE_TESTNET_API_KEY=...
BINANCE_TESTNET_SECRET=...

# Alpaca US Equities (ALWAYS start with paper)
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ALPACA_API_KEY=...
ALPACA_SECRET=...

# Deribit Options (testnet available)
DERIBIT_TESTNET=true
DERIBIT_API_KEY=...
DERIBIT_SECRET=...
```

### Security Guidelines

- **Never commit `.env`** to git — it's gitignored for security
- Use **testnet keys** (`BINANCE_TESTNET_*`, `DERIBIT_TESTNET=true`) during development
- Hot wallet ≤ 5% of capital (`PRIVATE_KEY_HOT_WALLET`, `SOLANA_PRIVATE_KEY`)
- Separate `FLASHBOTS_AUTH_KEY` for MEV bundles (different from trading wallet)
- All exchange API keys should be **read + trade only** (no withdrawal permissions)

### Environment Progression

```
development      → Local testing, mock data allowed, no real orders
paper_trading    → Real market data, simulated fills, no real money
live             → Real money — requires explicit ENVIRONMENT=live
```

⛔ **The system will refuse real orders unless `ENVIRONMENT=live` is set explicitly.**

## Development workflow

**For dashboard-only work**: Use `python api/mock_server.py` + `Set-Location dashboard; npm run dev` — no infrastructure needed.

**For agent development**: Start with `docker compose up -d` → `poetry install` → test your agent with `python run_agent.py <module> <Class>`.

**For strategy development**: Always start in `ENVIRONMENT=development`, validate with backtesting engine, then progress to `paper_trading` → `live`.

**Platform context**: This codebase runs on Windows 11. Use PowerShell for CLI commands. Docker Desktop with WSL2 backend provides the best container performance.

### Dashboard subproject skill set

`dashboard/.agents/skills/` contains a Matt-Pocock-style skill bundle (`diagnose`, `tdd`, `prototype`, `triage`, `zoom-out`, `to-prd`, `to-issues`, `improve-codebase-architecture`, etc.) — these are **dashboard-scoped** and only relevant when working inside `dashboard/`. They are **not** registered as global skills at the repo root; do not try to invoke them as `/skill-name` from here.

## Tooling configuration (in `pyproject.toml`)

- ruff: py312, line-length 100, rules `E,F,W,I,N,UP,B,SIM,RUF` (E501/B008/RUF012 ignored)
- black + isort: line-length 100, black profile for isort
- mypy: strict, excludes `tests/` and `ml/training/`
- pytest: `asyncio_mode=auto`, markers `unit | integration | backtest | live`

## Recent completions (v0.2+)

✅ **Agent ID collisions resolved** — All critical collisions fixed with reassignments (momentum→17, stat_arb→21, macro_rotator→34, yield_farmer→35, copy_trading_channel→36).

✅ **Agent 16 `ml_predictor.py`** — **Fully implemented**! Real-time OHLCV processing, 64-period windowing, ML inference server integration, intelligent signal caching, and sophisticated exit logic.

✅ **Compliance agent duplicates resolved** — Removed redundant `compliance.py`, kept the comprehensive `compliance_agent.py` (Agent ID 32) with wash trade detection, position limits, and sanctions screening.

✅ **Infrastructure stack validation complete** — Validated all 37 services in docker-compose.yml, confirmed 18 Kafka topics, TimescaleDB schemas, Redis configuration, and agent dependencies. Stack includes full monitoring (Prometheus, Grafana), reverse proxy (Nginx), and React dashboard.

## Pending work (v0.3)

1. **Tier 6 DeFi agents** — skeletons exist (`yield_farmer`, `dex_arbitrageur`, `mev_hunter`, `bridge_strategist`) but need real protocol integration (Aave/Curve/Flashbots/bridge SDKs).
2. **Agent 17 `options_strategist.py`** (Deribit delta-neutral) — not yet implemented.
3. **Infrastructure automation** — ML infe