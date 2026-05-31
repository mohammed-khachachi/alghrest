# ALGHREST — Professional Architecture Review

> Scope: ALGHREST runtime platform only. HMM_Trading is treated as a separate educational subproject (its single read-only touchpoint is `agents/tier4_strategies/hmm/adapter.py`) and is **excluded** from this architectural judgment.
> Method: evidence-based inspection of real repository files. Every weakness cites a concrete file. Reviewed 2026-05-31 against branch `chore/project-organization`.
> Legend for feature maturity: **[IMPL]** implemented · **[MOCK]** deterministic mock · **[SCAFFOLD]** stub only · **[MISSING]** not present.

---

## A. Executive Summary

ALGHREST is an **ambitiously designed, event-driven multi-agent trading framework** whose *structural* design is genuinely strong — clean tier separation, a disciplined `BaseAgent`/`BaseStrategy` contract, an idempotent Kafka transport, a Redis-backed kill switch wired end-to-end, and a thoughtfully partitioned TimescaleDB schema. The skeleton reads like someone who has seen real institutional systems.

However, there is a **decisive gap between the documented system and the running system**: the entire post-trade persistence and audit layer is **declared but not wired**. `infra/init/timescale-init.sql` defines immutable audit hypertables for `trading.trade_proposals`, `trading.orders`, `trading.fills`, `trading.closed_trades`, `risk.alerts`, and `risk.kill_switch_events` — but **no agent writes to any of them**. Orders and fills live only on Kafka topics and in short-TTL Redis keys. The "immutable audit log" exists as DDL only. Combined with the absence of Alembic migrations (despite CLAUDE.md instructing `alembic upgrade head`), the lack of any authentication on the API, and several execution agents that cannot be horizontally scaled, the system is **not** at institutional production grade.

**It is currently a sophisticated paper-trading / research platform with production-shaped scaffolding — not a production institutional trading system.** The good news: the gaps are mostly *additive* (wire the writers, add auth, add a DLQ) rather than requiring redesign.

---

## B. Strengths (with evidence)

1. **Disciplined agent base contract.** `agents/base_agent.py` gives every agent identical lifecycle (`initialize → run → shutdown`), a heartbeat loop writing `AgentHealth` to Redis with TTL (`_heartbeat_loop`, 90s TTL), a uniform kill-switch guard (`is_halted()`), Prometheus metrics on `9200 + agent_id`, and structured logging bound with agent context. `BaseStrategy` adds the 1% risk cap (`min(risk_per_trade, 0.01)`, line 262) and the 5-consecutive-loss auto-pause (`record_loss`, line 288–295). These rails are enforced in code, not just docs.

2. **Kafka transport is built correctly for a trading system.** `core/orchestrator/message_bus.py`: idempotent producer (`enable_idempotence=True`, `acks="all"`), LZ4 compression, `orjson` serialization handling Decimal/UUID/datetime, tenacity exponential backoff on transient errors, and — critically — **manual offset commits** (`enable_auto_commit=False`) with commit-after-successful-yield (`stream()`, lines 209–221). Consumer groups are namespaced per agent (`{prefix}.{agent_name}`) for isolation.

3. **Kill switch is genuinely end-to-end.** `core/risk/kill_switch.py` implements graduated thresholds (3% alert → 5% pause → 7% halt → 12% full kill), sets the Redis flag (`state_manager.activate_kill_switch`), and `agents/tier5_execution/exchange_executor.py` runs a dedicated `_kill_switch_listener_loop` (lines 167–202) that cancels every tracked order on `KillSwitchEvent`/`HaltAllStrategies`, with failed cancels deliberately left tracked for fill-poll retry. The executor also guards new placements with `is_halted()` inside the consume loop (line 126).

4. **Idempotent order placement.** `exchange_executor._place_with_lock` (lines 270–298) takes a distributed Redis lock keyed on `client_order_id`, checks a `order_placed:{id}` marker, and passes `clientOrderId` to the connector — three layers of dedup against restarts/replicas. Fill dedup uses `state.is_already_processed("fill_seen:{ex}:{fill_id}")` (line 498).

5. **Re-entry protection on the shared `orders.pending` topic.** The fan-in design where `FeeOptimizer` and `SlippageMinimizer` both re-publish to `ORDERS_PENDING` is protected: `fee_optimizer.py` skips `payload.get("_optimised")` (line 69) and re-stamps `_optimised=True`; the executor skips TWAP/VWAP parents (`order_type in (TWAP, VWAP)`, line 136) so SlippageMinimizer's `_child` limit orders are placed but parents are not re-split.

6. **TimescaleDB schema is professional-grade *as a design*.** `infra/init/timescale-init.sql`: hypertables with sensible chunk intervals, compression policies, multi-year retention (7y on `fills`/`closed_trades` for tax/compliance), GIN indexes on JSONB payloads, and continuous aggregates (`ohlcv_1h`, `ohlcv_1d`) for dashboard rollups. Schema separation by domain (`market_data`, `trading`, `risk`, `agents`, `intelligence`, `performance`).

7. **Monitoring stack is real, not decorative.** `docker-compose.yml` ships Prometheus (30d/15GB retention), Grafana with provisioned dashboards (`infra/grafana/dashboards/*`), plus node/redis/postgres exporters. Per-agent metrics, alert rules (`infra/prometheus/rules/alghrest.yml`), and JMX on the Kafka brokers.

8. **Deployment hygiene basics present.** Healthchecks with `start_period` on every infra service, `depends_on: condition: service_healthy`, `service_completed_successfully` gating on `kafka-init`, per-service memory limits, log rotation, and a static IP plan on a dedicated bridge network.

---

## C. Weaknesses (architectural, with file references)

### C1. The audit/persistence layer is declared but unwired — **the headline defect**
- `infra/init/timescale-init.sql` defines `trading.orders`, `trading.fills`, `trading.trade_proposals`, `trading.closed_trades`, `risk.alerts`, `risk.kill_switch_events`. A repo-wide grep for DB-write patterns (`asyncpg`, `execute(`, `INSERT INTO`, `sessionmaker`) returns only `ml/training/data_loader.py`, `core/config.py` (the URL string), `scripts/seed_redis.py`, `core/kafka/pnl_history_writer.py`, `core/kafka/metrics_collector.py`.
- `core/kafka/pnl_history_writer.py` — despite the name — writes a rolling **Redis list** (`alghrest:portfolio:pnl_history`, line 25), **not** TimescaleDB.
- `exchange_executor.py` publishes fills to `FILLS_CONFIRMED` and caches nothing durable; `proposal_approver.py` caches a review to Redis with a 24h TTL (line 162–166). **No consumer drains `ORDERS_EXECUTED`/`FILLS_CONFIRMED`/`PROPOSALS_BUS` into the `trading.*` tables.** The regulatory tables are dead.

### C2. No database migrations exist
- There is **no `alembic/` directory and no `alembic.ini`** in the repo, yet `CLAUDE.md` lists `alembic upgrade head` as a standard command. Schema is created **only** via `docker-entrypoint-initdb.d` on first volume init (`docker-compose.yml` line 67). Any schema change requires destroying the TimescaleDB volume. There is no forward/rollback path.

### C3. API has zero authentication/authorization
- `api/main.py` exposes `/api/v1/portfolio`, `/risk`, `/risk/kill-switch`, `/agents`, and WebSocket feeds with **no auth dependency anywhere**. `CORSMiddleware` uses `allow_methods=["*"]`, `allow_headers=["*"]`, `allow_credentials=True` (lines 111–124). For a system that surfaces capital, positions, and kill-switch state this is a hard production blocker.

### C4. The `api` container installs dependencies at runtime
- `docker-compose.yml` line 1036: the `api` service command is `sh -c "pip install structlog uvicorn fastapi ... && python -m api.main"`. This bypasses the Docker image build, is non-reproducible, breaks on registry outages, and contradicts the `Dockerfile`. Production images must be self-contained.

### C5. No dead-letter strategy — poison-pill risk
- `message_bus.AlghrestConsumer.stream()` (lines 209–221) does the right thing by *not committing* on processing failure, but it **continues to the next record** and commits that one. Net effect: a permanently-failing message's offset is never committed, but later offsets are, so on rebalance/restart you get **reprocessing gaps and duplicates**, and there is **no DLQ topic** to quarantine poison messages. `kafka-init.sh` creates no `*.dlq` topics.

### C6. Schema Registry runs but is unused
- `docker-compose.yml` runs `schema-registry` (Confluent), and `.env` has `KAFKA_SCHEMA_REGISTRY_URL`, but `message_bus.py` serializes with raw `orjson` and no Avro/Protobuf schema enforcement. Messages are schema-on-read via Pydantic `model_validate` at each consumer. There is no contract enforcement at the broker — a producer bug silently breaks downstream agents.

### C7. Stateful execution agents cannot scale horizontally
- `exchange_executor.py` holds `self._tracked_orders` in process memory (line 99). `order_router.py` holds `self._routing_cache` in process memory (line 61). Running two replicas of either double-processes or splits state. The Redis lock prevents duplicate *placement*, but fill-tracking and status updates would be lost/duplicated across replicas. These are effectively singletons.

### C8. Heartbeat coupling can take down a healthy agent
- `base_agent.start()` runs `asyncio.gather(self.run(), self._heartbeat_loop(), return_exceptions=False)` (lines 122–126). If the heartbeat loop raises, `gather` cancels `run()` and the whole agent dies — monitoring failure becomes trading failure. The heartbeat already swallows internal exceptions (line 168), but the coupling is fragile.

### C9. Documentation drift undermines trust
- `base_agent.py` docstring says "All 32 agents" (line 3) and `api/main.py` says "32-agent" (line 104), while `CLAUDE.md` says 37 services / Agent 37 HMM. `kafka-init.sh` headers say "16 topics" (line 5) and "All 18" (line 210) while creating 18. `order_router.py` docstring (line 47) claims it consumes `risk.assessments` but the code consumes `PROPOSALS_APPROVED` (line 71). The `kill_switch.py` header references a "CRO agent" / "Agent 2" but Risk Governor is the actual owner. None are fatal, but they erode confidence in every other doc claim (e.g. the false `alembic` instruction).

### C10. CIO/strategy → proposal coupling is fragile on cold start
- `proposal_approver._process` rejects **every** proposal if `state.get_portfolio()` is `None` (lines 109–112). The portfolio snapshot is written by `PortfolioTracker` with a 300s TTL (`state_manager.set_portfolio`, line 98). On cold start, or if PortfolioTracker lags/dies, the entire trade pipeline silently rejects everything as "no portfolio snapshot available." There is no liveness contract between these agents.

### C11. FeeOptimizer logic is largely inert
- `fee_optimizer._optimise` only upgrades `OrderType.MARKET` orders, but returns the order unchanged if `order.price is None` (line 102) — and MARKET orders from `order_router.py` set `price=None` (line 111). So the maker-rebate upgrade almost never fires in the current routing. Dead-ish optimization path.

---

## D. Technical Debt (prioritized)

### 🔴 Critical (block any real-money path)
- **No trade/fill/proposal persistence** to TimescaleDB (C1). Without it: no audit trail, no post-trade reconciliation, no P&L source of truth, no regulatory record. Files: `agents/tier5_execution/exchange_executor.py`, `agents/tier7_monitoring/*`, `infra/init/timescale-init.sql`.
- **No API authentication** (C3). `api/main.py`.
- **No DB migration tooling** (C2) — schema is unmanageable in production.
- **Runtime `pip install` in the `api` container** (C4) — non-reproducible deploys. `docker-compose.yml:1036`.

### 🟠 High
- **No dead-letter queue / poison-pill handling** (C5). `core/orchestrator/message_bus.py`, `infra/init/kafka-init.sh`.
- **Stateful singletons block horizontal scale** (C7). `exchange_executor.py`, `order_router.py`.
- **Portfolio-snapshot single point of pipeline failure** (C10). `proposal_approver.py`.
- **Schema Registry unused** (C6) — no message contract enforcement.

### 🟡 Medium
- **Heartbeat/run coupling** via `return_exceptions=False` (C8). `base_agent.py:125`.
- **Default secrets baked into compose** (`POSTGRES_PASSWORD:-alghrest_secure_pass_2024`, `GRAFANA_ADMIN_PASSWORD:-...`) — fine for dev, dangerous if it reaches any shared env. `docker-compose.yml:45,544`.
- **CI integration uses a single-broker Kafka with RF=1** (`.github/workflows/tests.yml:125–138`) and a `sleep 30` readiness hack (line 175) — tests don't exercise the 3-broker / min-ISR=2 production topology.
- **FeeOptimizer effectively inert** (C11). `fee_optimizer.py`.

### 🟢 Low
- **Doc drift** (C9): 32-vs-37 agents, topic counts, `order_router` docstring topic, the false `alembic` command in CLAUDE.md.
- **`kafka-init.sh` keeps a legacy `orders.approved` alias** (line 129) that nothing consumes — harmless but confusing.
- **`XXsabo/README.md` deleted but staged**, `CLAUDE.md`/`adapter.py` modified-uncommitted in the working tree — housekeeping.

---

## E. Institutional Comparison

| Dimension | Hedge-fund / institutional baseline | ALGHREST today | Verdict |
|---|---|---|---|
| **Event-driven architecture** | Bus-based, replayable, schema-enforced | Kafka, idempotent producer, manual commits, partitioned by symbol | **Strong** — genuinely close. Missing: schema enforcement (C6), DLQ (C5). |
| **Risk management** | Pre-trade limits + real-time circuit breakers + post-trade | Pre-trade `PositionLimitChecker` gate, graduated kill switch, 1% cap, 5-loss pause | **Strong design**, but risk metrics are computed in-memory and **not persisted** (`risk.metrics_snapshots` unwired). |
| **Execution management (EMS)** | Smart routing, TWAP/VWAP, maker/taker, venue failover | Order router (spread+fee scoring), TWAP child-splitting, fee optimizer, idempotent placement | **Good bones**; FeeOptimizer inert (C11), no smart venue failover, executor is a singleton. |
| **Order lifecycle** | Full state machine persisted + reconciled | In-memory tracking + Kafka status events; fill polling every 5s | **Partial** — lifecycle exists in flight but **evaporates** (no DB). No reconciliation vs venue. |
| **Market-data architecture** | Real feeds, normalized, persisted to TSDB | `connectors/data_providers/*` are **[MOCK]** deterministic walks; `ohlcv_bars` hypertable exists but unwired | **Prototype** — no real feed integration, no persistence. |
| **Auditability** | Immutable, queryable, regulator-ready | Audit **tables designed** but **no writers** (C1); Kafka retains 90d–1y | **Missing in practice.** Biggest institutional gap. |
| **Compliance** | Trade reporting, surveillance, retention | `compliance_agent` exists; retention policies in DDL; **no persisted records to report on** | **Scaffold.** |
| **Observability** | Metrics + logs + traces + SLOs + on-call | Prometheus/Grafana + heartbeats **[IMPL]**; **no tracing, no log aggregation, no SLOs, no Alertmanager routing** | **Above-average metrics**, missing tracing/logs/SLOs. |
| **Disaster recovery** | Backups, replay, RPO/RTO, failover | Redis AOF + Kafka RF=3 + named volumes; **no documented backup/restore, no replay tooling, no RPO/RTO** | **Weak.** |
| **Production deployment** | Immutable images, IaC, staged rollouts | Compose with healthchecks **[IMPL]**; `infra/k8s` + `infra/terraform` **[SCAFFOLD]**; runtime pip-install (C4) | **Dev-grade.** |
| **Model governance** | Versioned models, eval gates, rollback | `ml/` inference server separated **[IMPL]**; backtest thresholds defined; **no model registry/versioning/lineage** | **Partial.** |
| **Portfolio accounting** | Authoritative ledger, reconciled | `Portfolio` in Redis (300s TTL); `/api/holdings` **[MOCK]** static; **no ledger, no double-entry, no reconciliation** | **Missing.** |
| **Secrets management** | Vault/KMS, rotation, no plaintext | `.env` (correctly gitignored — verified not tracked); `VAULT_ADDR`/`VAULT_TOKEN` declared but **unused**; default creds in compose | **Dev-grade.** |

**What ALGHREST already has that many prototypes don't:** a true event bus with idempotency, an enforced kill switch, capital sleeves with hard per-trade caps, a partitioned TSDB schema, and a real metrics stack. **What's missing for institutional grade:** the persistence/audit layer being *connected*, authentication, real market data, reconciliation/accounting, DR, and reproducible deploys.

---

## F. Architecture Score

| Area | Score | One-line justification |
|---|---|---|
| Agent architecture | **7.0 / 10** | Excellent base contract & lifecycle; weakened by manual ID management, no registry, heartbeat/run coupling. |
| Event flow | **6.0 / 10** | Pipeline well-modeled with re-entry guards & idempotent placement; fan-in on one topic is fragile, no outbox, no reconciliation. |
| Kafka / messaging | **6.0 / 10** | Idempotent producer + manual commits + RF=3 are right; **no DLQ**, unused Schema Registry, poison-pill gaps. |
| API / backend | **5.0 / 10** | Clean FastAPI with health/ready/metrics; **no auth**, permissive CORS, runtime pip-install container. |
| Database / state | **3.5 / 10** | Redis layer is strong; TSDB schema is excellent **but completely unwired** + no migrations. Design 9, reality 3. |
| Deployment | **5.0 / 10** | Solid compose with healthchecks; non-reproducible api image, k8s/terraform scaffold-only, default secrets. |
| Monitoring | **6.0 / 10** | Real Prometheus/Grafana/exporters/heartbeats; no tracing, no log aggregation, no SLOs, health_log unwired. |
| Scalability | **5.0 / 10** | Kafka partitioning helps; executor/router are in-memory singletons; single-node Redis; dashboard polling. |
| Maintainability | **6.5 / 10** | Good structure, strict mypy/ruff/black, real tests; doc drift and mock/real ambiguity cost trust. |
| **Overall** | **5.5 / 10** | Production-*shaped* architecture with one critical unwired layer and several hard blockers; strong foundation, not yet production. |

---

## G. Improvement Roadmap

For each item: **Problem · Why it matters · Inspect · Solution · Risk · Difficulty · Impact.**

### Phase 1 — Safety & Correctness
1. **Add API authentication & lock down CORS**
   - *Problem:* All REST/WS endpoints are unauthenticated (C3). *Why:* exposes capital, positions, and kill-switch control. *Inspect:* `api/main.py:102–124`, `api/routes/quotes.py`. *Solution:* FastAPI dependency (API key or JWT) on all `/api/v1/*` and WS routes; restrict CORS origins to known hosts; protect `/metrics` behind network policy. *Risk:* Low. *Difficulty:* Low. *Impact:* High.
2. **Make the `api` image self-contained**
   - *Problem:* runtime `pip install` (C4). *Inspect:* `docker-compose.yml:1036`, `Dockerfile`. *Solution:* bake deps into the image; command becomes `python -m api.main`. *Risk:* Low. *Difficulty:* Low. *Impact:* Medium-High.
3. **Decouple heartbeat from run loop**
   - *Problem:* `return_exceptions=False` lets a heartbeat error kill trading (C8). *Inspect:* `base_agent.py:122–126`. *Solution:* run heartbeat as a supervised background task with its own restart/backoff; never let it cancel `run()`. *Risk:* Low. *Difficulty:* Low. *Impact:* Medium.
4. **Fix the portfolio-snapshot pipeline dependency**
   - *Problem:* missing snapshot rejects all proposals (C10). *Inspect:* `proposal_approver.py:109–112`, `portfolio_tracker.py`. *Solution:* distinguish "no snapshot yet" (hold/retry) from "limit breach" (reject); add a startup readiness gate. *Risk:* Medium (don't loosen real limits). *Difficulty:* Medium. *Impact:* High.

### Phase 2 — Persistence & Auditability
5. **Wire the persistence layer (the critical fix)**
   - *Problem:* `trading.*`/`risk.*` tables have no writers (C1). *Why:* no audit trail, no P&L truth, no reconciliation, no compliance record. *Inspect:* `infra/init/timescale-init.sql`, `exchange_executor.py`, `proposal_approver.py`, `core/kafka/*`. *Solution:* add **persistence consumer agents** (or a transactional-outbox writer) that drain `PROPOSALS_BUS`, `ORDERS_EXECUTED`, `FILLS_CONFIRMED`, `RISK_ALERTS` into the hypertables using `asyncpg`; carry `kafka_offset` (already a column in `trade_proposals`) for replay idempotency. *Risk:* Medium. *Difficulty:* Medium-High. *Impact:* Critical.
6. **Introduce Alembic**
   - *Problem:* no migrations (C2). *Inspect:* repo root (absent), `core/config.py:106`. *Solution:* `alembic init`, baseline from `timescale-init.sql`, run `alembic upgrade head` in deploy; keep init SQL only for hypertable/policy bootstrap. *Risk:* Low. *Difficulty:* Medium. *Impact:* High.
7. **Add a portfolio/position ledger + venue reconciliation**
   - *Problem:* portfolio is ephemeral Redis; `/api/holdings` is mock. *Inspect:* `state_manager.py:96–104`, `connectors/data_providers/holdings.py`. *Solution:* authoritative positions table fed from fills; periodic reconciliation job comparing internal vs `fetch_positions`/`fetch_balance`. *Risk:* Medium. *Difficulty:* High. *Impact:* High.

### Phase 3 — Production-grade Messaging
8. **Dead-letter queue + poison-pill policy**
   - *Problem:* no DLQ; uncommitted offsets cause gaps/dupes (C5). *Inspect:* `message_bus.py:201–223`, `kafka-init.sh`. *Solution:* retry-with-bound then publish to `<topic>.dlq`; commit the original offset; alert on DLQ depth. *Risk:* Medium. *Difficulty:* Medium. *Impact:* High.
9. **Enforce schemas via the running Schema Registry**
   - *Problem:* registry runs but is unused (C6). *Inspect:* `docker-compose.yml:397`, `message_bus.py:46–63`. *Solution:* Avro/Protobuf (or JSON Schema) serializers tied to the registry; CI contract tests. *Risk:* Medium. *Difficulty:* Medium-High. *Impact:* Medium-High.

### Phase 4 — Monitoring & Reliability
10. **Add distributed tracing + log aggregation + SLOs**
    - *Problem:* metrics only; no traces/logs/SLOs. *Inspect:* `core/utils/logging.py`, `infra/prometheus/*`, `docker-compose.yml`. *Solution:* OpenTelemetry spans across the pipeline (proposal→fill), ship `structlog` JSON to Loki/ELK, wire Alertmanager, define SLOs (pipeline latency, fill-confirmation lag, consumer lag via existing `get_lag`). *Risk:* Low. *Difficulty:* Medium. *Impact:* High.
11. **Persist `agents.health_log` and add an executor reconciliation watchdog.**
    - *Inspect:* `base_agent._heartbeat_loop`, `timescale-init.sql` (`agents.health_log`). *Solution:* heartbeat writer to TSDB; watchdog comparing tracked orders vs venue state. *Risk:* Low. *Difficulty:* Medium. *Impact:* Medium.

### Phase 5 — Institutional Trading Features
12. **Real market-data + execution connectors** (replace **[MOCK]** providers)
    - *Inspect:* `connectors/data_providers/{crypto,forex,equity}_provider.py`, `connectors/exchanges/ccxt_connector.py`. *Solution:* implement `quote()/history()` against ccxt/CoinGecko/Alpha Vantage/Alpaca per the documented swap contract; persist `ohlcv_bars`. *Risk:* Medium. *Difficulty:* High. *Impact:* High.
13. **Model governance** for the ML predictor.
    - *Inspect:* `ml/inference/server.py`, `ml/weights/`, `ml/training/train.py`. *Solution:* model registry + versioned weights + eval gate before promotion + lineage. *Risk:* Medium. *Difficulty:* Medium-High. *Impact:* Medium. *(Do **not** enable Tier 6 DeFi — it remains skeleton/mock.)*

### Phase 6 — Cloud / Kubernetes Production Readiness
14. **Promote `infra/k8s` + `infra/terraform` from scaffold to real** (StatefulSets for Kafka/Redis/TSDB, secrets via Vault/KMS — `VAULT_ADDR` already declared, HPA only for *stateless* agents, network policies, staged rollouts). *Inspect:* `infra/k8s/deployments/*`, `infra/terraform/main.tf`. *Risk:* High. *Difficulty:* High. *Impact:* High. *(Prerequisite: fix C7 so stateful agents either shard or run as singletons with leader election.)*
15. **Disaster recovery**: documented backup/restore for TSDB + Redis, Kafka replay runbooks, RPO/RTO targets. *Risk:* Medium. *Difficulty:* Medium. *Impact:* High.

---

## Final Verdict

**ALGHREST is closer to an *advanced paper-trading platform* than to a production institutional trading system — and on the persistence/audit dimension specifically, it is still a research prototype.**

The architecture is designed *as if* for institutional use (event bus, kill switch, capital sleeves, audit schema, monitoring), and several pieces are implemented to a genuinely good standard. But the running system does not yet persist trades, has no authentication, has no migrations, cannot horizontally scale its execution agents, and consumes only mock market data. None of these are redesign problems — they are **connect-the-wiring** problems. Complete Phases 1–2 and ALGHREST becomes a credible advanced paper-trading platform; complete Phases 3–6 and it can plausibly approach institutional production grade. Until then, it must remain in `paper_trading`/`development`, exactly as its own safety rails enforce.
