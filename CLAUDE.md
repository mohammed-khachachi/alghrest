# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Stack

- **Python 3.12 + Poetry**, Pydantic v2, asyncio everywhere
- **Apache Kafka 7.6** (3-broker cluster) for inter-agent messaging via `aiokafka`
- **Redis 7** for shared state, kill switch, heartbeats
- **TimescaleDB (PG 16)** for time-series persistence
- **Anthropic Claude** — Opus for the CIO agent, Sonnet for analyst agents (NLP). Prompt caching is enabled in `cio_agent` (1h TTL) and `news_analyst` (5m TTL).
- **Dashboard**: React 18 + Vite + Tailwind + Zustand (in `dashboard/`)

## Common commands

```bash
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
cd dashboard && npm install && npm run dev    # http://localhost:5173
```

Note: pytest's coverage gate (`--cov-fail-under=70`) is **intentionally disabled** in `pyproject.toml` until full suite lands. Don't re-enable casually.

## Architecture

ALGHREST is a 32-agent autonomous trading system organised in 7 tiers. Agents communicate **only** through Kafka topics and shared Redis state — there are no direct calls between agents.

```
Tier 1 — Executive (CIO Opus, Risk Governor, ProposalApprover)
Tier 2 — Intelligence (market data, news, sentiment, macro, geopolitics, on-chain, price publisher)
Tier 3 — Quant (technical analyst, GARCH volatility, correlation engine)
Tier 4 — Strategies (trend, mean-rev, momentum, stat-arb, breakout, macro rotator, cross-ex arb; ml_predictor + options_strategist pending)
Tier 5 — Execution (order router, slippage minimizer, hedge mgr, fee optimizer, liquidation guard, exchange executor; position_sizer is a helper, not a runtime agent)
Tier 6 — DeFi (yield, dex_arb, mev, bridge — all pending v0.3)
Tier 7 — Monitoring (portfolio tracker, alert manager, compliance)
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
2. Inherit `BaseAgent` (or `BaseStrategy` for Tier 4). Set unique `AGENT_ID` 1–32.
3. Implement `initialize() / run() / shutdown()`. Always include the kill-switch guard in `run()`.
4. Add a service to `docker-compose.yml` using the `python run_agent.py <module> <Class>` pattern.
5. Expose Prometheus port = `9200 + AGENT_ID` (handled automatically by `BaseAgent.start()`).

### Known agent ID collisions (pre-existing, NOT from recent work)

- ID **14** — `volatility_forecaster` vs `momentum`
- ID **15** — `correlation_engine` vs `stat_arb`
- ID **18** — `arb_cross_exchange` vs `macro_rotator`

These cause Prometheus port clashes and Redis health-key overwrites. A renumbering pass is pending; flag rather than silently work around when touching these agents.

## Risk rails (hard limits — don't soften)

- Max risk per trade: **1%** of capital (enforced in `BaseStrategy.__init__` via `min(risk_per_trade, 0.01)`).
- Auto-pause strategy after **5 consecutive losses**.
- Max portfolio drawdown: **25%** (Risk Governor circuit breaker).
- Hot wallet ≤ **5%** of capital.
- The system **refuses real orders unless** `ENVIRONMENT=live` is set explicitly. Default is `paper_trading`.

## Backtest validation thresholds (Tier 4)

Strategies must pass all of these in `backtesting/engine.py::BacktestEngine.validate_all` before going live: ≥5y data, ≥50 trades/yr, IS Sharpe ≥1.0, walk-forward OOS Sharpe ≥0.8, max DD <25%, profit factor ≥1.3, walk-forward efficiency ≥60%, Monte Carlo ruin <1%, MC 95% VaR <15%.

## Environment & secrets

- All settings flow through `core/config.py::Settings` (pydantic-settings, loads `.env`). Use `from core.config import settings`.
- `ENVIRONMENT` ∈ `development | paper_trading | live` — gates live order placement.
- `ANTHROPIC_API_KEY` required for CIO + news analyst.
- Per-exchange testnet keys (`BINANCE_TESTNET_*`, etc.) are preferred during development.
- Never commit `.env`. Hot-wallet private key and Flashbots auth key live in env, not code.

## Tooling configuration (in `pyproject.toml`)

- ruff: py312, line-length 100, rules `E,F,W,I,N,UP,B,SIM,RUF` (E501/B008/RUF012 ignored)
- black + isort: line-length 100, black profile for isort
- mypy: strict, excludes `tests/` and `ml/training/`
- pytest: `asyncio_mode=auto`, markers `unit | integration | backtest | live`

## Pending work (v0.3)

1. Tier 6 DeFi agents (yield_farmer, dex_arb, mev_hunter, bridge_strategist) — **all 4 missing**.
2. Agent 16 `ml_predictor.py` (CNN chart + RL sizing).
3. Agent 17 `options_strategist.py` (Deribit delta-neutral).
4. Open issues: I4 (replace dead Reuters RSS feed in `news_analyst`), I10 (PortfolioTracker Sharpe formula).
5. Renumber the colliding AGENT_IDs (14/15/18) listed above.
