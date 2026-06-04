# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout — two projects under one root

This monorepo contains **two independent projects**. Know which one you are in before editing:

1. **ALGHREST** (the root) — the 37-service autonomous trading platform documented in the rest of this file. Lives directly under the repo root (`agents/`, `api/`, `core/`, `dashboard/`, `ml/`, `connectors/`, etc.).
2. **HMM_Trading** at `HMM_Trading/` — a **self-contained educational** Hidden Markov Model research pipeline with its own `pyproject.toml`, `requirements.txt`, `main.py`, tests, and its own `CLAUDE.md`. It is **not** part of the ALGHREST agent fabric and does not share code, dependencies, or runtime with it.

When working on HMM_Trading, treat `HMM_Trading/CLAUDE.md` as authoritative — it sets a hard scope boundary forbidding edits to the parent ALGHREST project, bans installing `pandas_ta`/`statsmodels` into that env, and forbids changing the HMM math or wrapper structure. See `docs/monorepo-workflow.md` for how the two projects are intended to coexist.

**One runtime bridge exists:** the Tier 4 `hmm_regime` agent (Agent 37, `agents/tier4_strategies/hmm/agent.py::HMMAgent`) consumes the HMM_Trading research code at runtime — it lazy-loads the GaussianHMM helpers and reads `HMM_Trading/configs/default.json` through an adapter to emit regime-aware proposals. It is paper/simulation-only (no connector calls, no API keys). This is the single point where the two projects touch; everywhere else the boundary holds.

## Stack

- **Python 3.12 + Poetry**, Pydantic v2, asyncio everywhere
- **Apache Kafka 7.6** (3-broker cluster) for inter-agent messaging via `aiokafka`
- **Redis 7** for shared state, kill switch, heartbeats
- **TimescaleDB (PG 16)** for time-series persistence
- **Anthropic Claude** — Opus for the CIO agent, Sonnet for analyst agents (NLP). Prompt caching is enabled in `cio_agent` (1h TTL) and `news_analyst` (5m TTL).
- **Dashboard**: React 18 + Vite + Tailwind + Zustand (in `dashboard/`)

## Common commands

A root `Makefile` wraps the most common targets — `make install`, `make docker-up`, `make test`, `make format`, `make lint`, `make mock-server`, `make dashboard-dev`, `make clean`, plus `make run-cio` / `run-risk` / `run-proposal` shortcuts for the Tier 1 agents. The raw commands below are still the source of truth; reach for `make` when you want the short form.

```powershell
# Install (Poetry; project uses Python 3.12.x, pinned <3.13)
poetry install
poetry install --with backtesting    # add quantstats / pyfolio-reloaded
poetry install --with nlp            # add spaCy for news_analyst NER (optional; see ABI note below)

# Run the full infra stack + agent containers
docker compose up -d
docker compose ps
docker compose logs kafka-init       # confirm 24 topics created (incl. 6 *.dlq)

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
# Integration suite (tests/integration/) covers the full pipeline:
#   execution_pipeline, kafka_messaging, redis_state_management,
#   agent_coordination, market_crash_kill_switch, ml_failover,
#   api_dashboard_integration, backtesting_validation

# Lint / format / type-check
ruff check .
black .
isort .
mypy agents/ core/                  # strict mode
pre-commit run --all-files

# Dashboard (React/Vite)
Set-Location dashboard; npm install; npm run dev    # http://localhost:5173
# The Overview page's market-data panel + holdings/P&L need /api/* on :8000.
# Run api/mock_server.py (below) in a separate terminal first. If it's down,
# Vite proxy returns 500 and SymbolSelector falls back to FALLBACK_SYMBOL_CATALOG.

# ML inference server (required for Agent 16 ml_predictor)
Set-Location ml; python inference/server.py          # http://localhost:8080/predict

# Mock server (for dashboard development without real backend)
python api/mock_server.py                    # http://localhost:8000 (fakes all agents + /api/{symbols,quotes,history,holdings})

# Demo and testing utilities (scripts/)
python scripts/demo_kill_switch.py             # Interactive kill switch demo (Arabic UI)
python scripts/run_kill_switch_stress_test.py  # Stress test kill switch system
python scripts/seed_redis.py                   # Seed Redis with initial state for local dev
python scripts/mock_ml_server.py               # Lightweight stand-in for ml/inference/server.py
python scripts/validate_agent_ids.py           # Detect AGENT_ID collisions across agents/**
python scripts/validate_news_feeds.py          # Probe news_analyst RSS feeds (catches dead URLs)
python scripts/run_tests.py                    # Convenience wrapper for the pytest suite
python scripts/clean_workspace.py              # Purge __pycache__/.pytest_cache/.mypy_cache/*.log etc. across the repo (skips .venv)

# Universal agent runner (used by Docker services)
python run_agent.py <module_path> <ClassName>  # Universal entry point for all agents
python run_agent.py agents.tier1_executive.cio_agent CIOAgent

# Lightweight dev mode (low-resource Windows boxes — no Docker/Kafka/Redis/agents/ML)
py -3.12 -m venv venv-lite; .\venv-lite\Scripts\Activate.ps1
python -m pip install -r requirements-lite.txt
.\scripts\run_lite.ps1            # starts api/mock_server.py + dashboard only
.\scripts\test_lite.ps1           # lite test runner (skips integration markers)
# Full docs: docs/LIGHTWEIGHT_DEV.md
```

**Ta-lib dependency note:** pandas-ta requires separate ta-lib binary installation:
- Ubuntu: `apt-get install ta-lib`  
- macOS: `brew install ta-lib`
- Windows: Download from https://www.lfd.uci.edu/~gohlke/pythonlibs/#ta-lib

**spaCy / numpy 2.x ABI note:** spaCy is in the optional `nlp` poetry group, not the main deps. The main env runs `numpy 2.x` (required by `pandas-ta 0.4`), but spaCy 3.8.x pins `thinc<8.4` → `numpy<2.1`, and the spaCy 4.0 dev releases pin `thinc<9.1` (compiled against the numpy 1.x ABI — `dtype size changed` at import). Installing `--with nlp` into the main env will break imports; if you need NER, use a separate venv or wait for spaCy 4.0 stable with `thinc>=9.1`. `news_analyst._extract_entities` already returns `[]` when spaCy is absent.

**Windows development note:** Use PowerShell for all commands below. Docker Desktop with WSL2 backend recommended for best performance.

Note: pytest's coverage gate (`--cov-fail-under=70`) is **enabled** with comprehensive integration tests covering the core pipeline. Target 70% minimum coverage across agents and core modules.

## Architecture

ALGHREST is a 37-service autonomous trading system with ~20 trading agents organised in 7 tiers. Agents communicate **only** through Kafka topics and shared Redis state — there are no direct calls between agents.

```
Tier 1 — Executive (CIO Opus, Risk Governor, ProposalApprover)
Tier 2 — Intelligence (market data, news, sentiment, macro, geopolitics, on-chain, price publisher)
Tier 3 — Quant (technical analyst, GARCH volatility, correlation engine)
Tier 4 — Strategies (trend, mean-rev, momentum, stat-arb, breakout, macro rotator, cross-ex arb, ml_predictor, hmm_regime; options_strategist still pending)
Tier 5 — Execution (order router, slippage minimizer, hedge mgr, fee optimizer, liquidation guard, exchange executor; position_sizer is a helper, not a runtime agent)
Tier 6 — DeFi (yield_farmer, dex_arbitrageur, mev_hunter, bridge_strategist — ⚠️ SKELETON IMPLEMENTATIONS ONLY, NOT PRODUCTION-READY)
Tier 7 — Monitoring (portfolio tracker, alert manager, compliance, auditor, copy-trading channel, persistence writer)
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

`ExchangeExecutor` order tracking is restart- and replica-safe via Redis: tracked orders persist in Redis (survive restarts), and fill polling is guarded by a Redis ownership **lease** so only one replica polls a given order at a time. Don't reintroduce in-memory-only order tracking.

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

All Kafka topic names are centralised in `core/data/models.py::KafkaTopic` (string enum). Kafka topics are created up front by `infra/init/kafka-init.sh` (24 topics including the legacy `orders.approved` alias and 6 `*.dlq` dead-letter topics, e.g. `proposals.bus.dlq`) — auto-create is **off**. If you add a topic, update both the enum and the init script.

### State & messaging primitives

- `core/orchestrator/message_bus.py::AlghrestProducer` / `AlghrestConsumer` wrap aiokafka. Use `BaseAgent.publish(topic, payload)` and `self.make_consumer([topics])` rather than instantiating these directly. The consumer retries transient errors (`tenacity.AsyncRetrying`) and routes poison messages to a dead-letter topic via `DLQ_TOPIC_BY_SOURCE` (`<topic>` → `<topic>.dlq`); DLQ is on by default (`dlq_enabled=True`).
- `core/orchestrator/state_manager.py::StateManager` is the singleton Redis client (`self.state` on every agent). Carries kill switch, agent health, and `prices:{symbol}` JSON (60s TTL, written by `PricePublisher`).
- `core/risk/kill_switch.py`, `core/risk/position_limits.py`, `core/risk/risk_engine.py` — risk plumbing used by Risk Governor and ProposalApprover.

### Adding a new agent

1. File under the correct `agents/tierN_*/` directory.
2. Inherit `BaseAgent` (or `BaseStrategy` for Tier 4). Set unique `AGENT_ID` (range now 1–37+; `hmm_regime` is Agent 37).
3. Implement `initialize() / run() / shutdown()`. Always include the kill-switch guard in `run()`.
4. Test locally: `python run_agent.py agents.tierN_category.agent_file AgentClass`
5. Add a service to `docker-compose.yml` using the same `run_agent.py` pattern.
6. Expose Prometheus port = `9200 + AGENT_ID` (handled automatically by `BaseAgent.start()`).

### Agent ID assignments (recently resolved)

Reassigned IDs (previously collided):
- `momentum`: 14 → **17**
- `stat_arb`: 15 → **21**
- `macro_rotator`: 18 → **34**
- `yield_farmer`: 26 → **35**
- `copy_trading_channel`: 33 → **36**

`auditor_agent.py` uses ID **33** by design. The 1–32 range is no longer authoritative — Prometheus ports (`9200 + AGENT_ID`) just need to stay unique. `scripts/validate_agent_ids.py` is the source of truth; run it before merging a new agent.

### ML inference subsystem (`ml/` + Agent 16)

The ML predictor strategy does **not** load models in-process. Instead:

- `ml/models/cnn_pattern.py::CandlestickCNN` and `ml/models/rl_position_sizer.py` are loaded by `ml/inference/server.py` (FastAPI) which serves `POST /predict` on **port 8080**.
- `agents/tier4_strategies/ml_predictor.py` (Agent 16) is just an HTTP client — it builds a 64-period OHLCV window and POSTs to `http://localhost:8080/predict`.
- Trained weights live in `ml/weights/` (`cnn_btc_usdt.pth`, `ppo_position_sizer.zip`); training entry is `ml/training/train.py`.

When deploying, the inference server is a **separate process** from the agent. Don't add it to the standard `run_agent.py` flow.

### Other moving parts worth knowing

- `api/main.py` is the production FastAPI app (REST + WebSocket dashboard feed). `api/mock_server.py` is a **separate dev-only mock** that fakes all 36+ agents and live data — use this for dashboard development when you don't want to spin up the full infrastructure stack. They both bind a FastAPI app named `app`; don't run them on the same port.
- **API-key auth** lives in `api/auth.py`. Sensitive REST endpoints depend on `require_api_key` (header `X-API-Key`); the WebSocket feed uses `require_websocket_api_key` (header `X-API-Key` or `?api_key=` query param). Auth is **enforced automatically** whenever `ENVIRONMENT` is `paper_trading` or `live`, or when `api_auth_enabled=True` (default). The expected key is `ALGHREST_API_KEY` (`core/config.py`); its default `"change-me"` is **rejected** outside `development`, so set a real key before paper/live.
- **Persistence sink** (`core/persistence/` + Agent 38 `agents/tier7_monitoring/persistence_writer.py::PersistenceWriter`) is the Kafka → TimescaleDB writer. It subscribes to `PERSISTED_TOPICS` (defined in `core/persistence/events.py`), normalises each `AgentMessage` envelope (`build_persistence_statements`), and writes one transaction per event via `TimescalePersistenceRepository` into tables already provisioned by `infra/init/timescale-init.sql` (`market_data.*`, `trading.*`, `risk.*`, `intelligence.*`, `performance.portfolio_snapshots`). The mapper depends on the consumer yielding the full `AgentMessage` dict (top-level `topic`/`payload`/`message_type`) — `tests/unit/test_persistence_events.py::test_real_agent_message_envelope_maps_through_persistence` locks that contract. Unknown topics are ignored; invalid payloads on known topics raise `PersistenceMappingError` (the offset is not committed). Prometheus port `9238`; compose service `agent-persistence-writer`. Note: `kafka_offset` is not carried in the envelope so it persists as `NULL`. End-to-end verification needs the stack: `docker compose up -d timescaledb kafka-1 redis` then `pytest -m integration` (unit tests use a fake session and never touch a real DB).
- `core/telegram/bot.py` + `bot_manager.py` back the Tier 7 alert manager and copy-trading channel. Telegram credentials (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHANNEL_ID`) come from `core/config.py` settings. The bot broadcasts formatted trade signals with Arabic UI support.
- `infra/k8s/` and `infra/terraform/` exist but are scaffold-only (a few manifests / `main.tf` + `variables.tf`). Don't treat them as production-ready deploy targets without filling them in.
- `connectors/` holds the I/O adapter layer used by execution and intelligence agents — `exchanges/` (per-venue REST/WS clients consumed by `ExchangeExecutor`), `chains/` (on-chain RPC wrappers for Tier 6), `data_providers/` (market-data quote/history/holdings layer used by the dashboard — see below). Agents never call exchange/RPC SDKs directly; they go through these adapters.
- `mcp/claude_model_manager/` is a Model Context Protocol server scaffold for routing Claude model selection — not part of the runtime agent flow.
- `AGENTS.md` is the Codex-targeted sibling of this file. It overlaps heavily and may lag CLAUDE.md on some details; treat CLAUDE.md as canonical for Claude Code sessions.
- `docs/` holds non-CLAUDE.md reference material: `LIGHTWEIGHT_DEV.md` (the venv-lite path), `kill_switch_testing_guide.md` (Arabic-language QA scenarios for `scripts/run_kill_switch_stress_test.py`), `monorepo-workflow.md` (how ALGHREST and the HMM_Trading subproject coexist), and `integration-roadmap.md`. Historic point-in-time reports (security audits, integration-test summaries, infrastructure validation, completion audit) were moved to `docs/archive/` in commit a553363 — treat them as snapshots, not current state.
- `.github/workflows/tests.yml` runs lint → unit → integration on every push/PR to `main`/`develop` and nightly at 02:00 UTC. Backtest and performance jobs are **opt-in**: include `[full-test]` or `[perf-test]` in the commit message to trigger them. Coverage uploads to Codecov; CI invokes `scripts/run_tests.py` (the same wrapper used locally), so keep that script working.
- `dashboard/src/lib/useLiveQuotes.ts` is the **single source of truth for dashboard quote polling** — one TanStack Query call every 3s, shared across `PortfolioOverview`, `HoldingsPanel`, and `MarketDataPanel`. Do not add per-panel polling to `/api/quotes`; subscribe to this hook instead so all panels stay in lockstep and the backend only sees one request.
- Dashboard pages live in `dashboard/src/pages/`: `Overview` (default — symbol selector + portfolio + holdings + market data), `Agents`, `Positions`, `Risk`, `Kafka`, plus three newer surfaces — `AuditorDashboard`, `BacktestSimulation`, `InvestorPitch`. The sidebar in `components/layout/Sidebar.tsx` is the routing source of truth.

### Test layout

`tests/` mirrors the pytest markers:
- `tests/unit/` — fast, no external services (`pytest -m unit`). Examples: `test_kill_switch_cancel.py`, `test_prompt_caching.py`, `test_risk_engine.py`.
- `tests/integration/` — requires `docker compose up -d` (Kafka + Redis + TimescaleDB). Covers the full pipeline: `test_execution_pipeline.py`, `test_kafka_messaging.py`, `test_market_crash_kill_switch.py`, `test_ml_failover.py`, `test_api_dashboard_integration.py`, `test_backtesting_validation.py`, etc.
- `tests/backtests/` — backtest-marker tests (slow); currently empty.

### Market-data REST surface (`connectors/data_providers/` + `api/routes/quotes.py`)

A separate, dashboard-facing market-data layer — independent of the Kafka agent fabric. Used by the React Overview page (symbol selector, market-data panel, holdings + P&L).

- `connectors/data_providers/base.py` — `QuoteProvider` ABC, `Quote` and `HistoricalBar` dataclasses, `random_walk_history()` helper, and `ANCHOR_DATE` (currently `2025-05-11`). All demo data is anchored to this date so historical series, sparklines, and `holdings.entry_price` line up exactly.
- `connectors/data_providers/{crypto,forex,equity}_provider.py` — mock implementations with realistic base prices. **Designed to be swapped** for ccxt/CoinGecko (crypto), Alpha Vantage/ExchangeRate-API (forex), and Alpaca/Finnhub (equities) by replacing the class body — `QuoteProvider` interface and the router are not affected.
- `connectors/data_providers/router.py` — `QuoteRouter` + static `_CATALOG` (24 symbols). Routes a symbol to the right provider via its `AssetClass`. Unknown symbols are silently dropped in batch calls, 404 on the single-symbol `/history` path.
- `connectors/data_providers/holdings.py` — 8 static mock holdings with broker mapping (`crypto→Binance`, `forex→OANDA`, `equity→Alpaca`). Entry prices are computed from the *same* deterministic historical bars the sparkline renders, so they match exactly. Cached after first build.
- `api/routes/quotes.py` exposes four endpoints, mounted on **both** `api/main.py` and `api/mock_server.py`:
  - `GET /api/symbols` — catalog
  - `GET /api/quotes?symbols=BTC,EUR/USD,AAPL` — live OHLC + bid/ask + 24h change + volume (jitters per call to simulate real-time)
  - `GET /api/history?symbol=X&days=N` — deterministic OHLC bars ending on `ANCHOR_DATE`
  - `GET /api/holdings` — static holdings ledger; P&L is computed **client-side** by joining with quotes (no double polling)

When swapping the mocks for real providers: keep `_BASE_PRICES`/`_BASE_RATES` as a fallback for development, replace the body of `quote()` and `history()` with real API calls, leave everything else alone.

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

`dashboard/.agents/skills/` contains a Matt-Pocock-style skill bundle (`diagnose`, `tdd`, `prototype`, `triage`, `zoom-out`, `to-prd`, `to-issues`, `improve-codebase-architecture`, etc.) — these are dashboard-scoped and only relevant when working inside `dashboard/`. They are **not** registered as Claude Code skills at the repo root; do not try to invoke them as `/skill-name` from here.

## Tooling configuration (in `pyproject.toml`)

- ruff: py312, line-length 100, rules `E,F,W,I,N,UP,B,SIM,RUF` (E501/B008/RUF012 ignored)
- black + isort: line-length 100, black profile for isort
- mypy: strict, excludes `tests/` and `ml/training/`
- pytest: `asyncio_mode=auto`, markers `unit | integration | backtest | live`

## Known unfinished pieces

- Tier 6 DeFi agents (`yield_farmer`, `dex_arbitrageur`, `mev_hunter`, `bridge_strategist`) are skeletons — see the DeFi safety warning above.
- `options_strategist` (Deribit delta-neutral) is not yet implemented.
- `infra/k8s/` and `infra/terraform/` are scaffold-only.
- `connectors/data_providers/{crypto,forex,equity}_provider.py` ship as **mocks** with deterministic random walks. Real integrations (ccxt/CoinGecko, Alpha Vantage/ExchangeRate-API, Alpaca/Finnhub) replace the body of `quote()` and `history()` only — `QuoteProvider` interface, router, and catalog stay untouched.
- `/api/holdings` is a static mock ledger (8 holdings, all `BUY`). No persistence, no order ↔ holding wiring back to the agent fabric.
