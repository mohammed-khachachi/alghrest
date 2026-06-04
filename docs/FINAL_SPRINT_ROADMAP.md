# ALGHREST — Final Sprint Roadmap

Concise, value-ordered backlog for closing the highest-impact technical debt.
Scope: paper/development only. **Never** enable live trading or Tier 6 DeFi to
close any item here. All commands assume Poetry (`poetry run ...`) on Windows
PowerShell from the repo root.

Status legend: ⬜ todo · 🟦 partially done this session · ✅ done this session.

> **Tier 6 DeFi (`yield_farmer`, `dex_arbitrageur`, `mev_hunter`, `bridge_strategist`)
> is explicitly EXCLUDED from all production work.** They are skeleton/mock
> implementations. Keep `ENABLE_DEFI_AGENTS=false`. Do not invest sprint effort
> in making them live — only in keeping them safely disabled.

---

## 1. ✅ Pytest marker config drift (CI reliability) — **P0**
- **Files:** `pyproject.toml` (`[tool.pytest.ini_options]`), ~~`tests/pytest.ini`~~ (deleted).
- **Root cause (fixed):** `tests/pytest.ini` used the `[tool:pytest]` header (only valid in `setup.cfg`); as a `pytest.ini` it was a no-op that still shadowed `pyproject.toml` as rootdir config, so markers/`filterwarnings`/`asyncio_mode` were dropped when running `pytest tests/...`.
- **Acceptance:** `poetry run pytest tests/unit --no-cov -q` shows **0** `PytestUnknownMarkWarning` and `180 passed`; rootdir resolves to the repo root.
- **Test:** `poetry run pytest tests/unit --no-cov -q`
- **Risk:** Low. `asyncio_mode=auto` (pyproject) is a superset of the prior strict behavior.

## 2. 🟦 Persistence end-to-end integration verification — **P0**
- **Files:** `core/persistence/{events,repository,database}.py`, `agents/tier7_monitoring/persistence_writer.py`, `infra/init/timescale-init.sql`, `tests/integration/`.
- **Done this session:** Confirmed the wire contract (consumer yields the full `AgentMessage` envelope with top-level `topic`), added a contract-lock test, registered the `agent-persistence-writer` compose service (Agent 38, port 9238), documented the subsystem in `CLAUDE.md`.
- **Remaining:** Column-level schema validation only surfaces against a real DB. Add an integration test that publishes one message per `PERSISTED_TOPICS` entry and asserts a row is written to each target table.
- **Acceptance:** Each of the 10 mapped tables receives a row; invalid payloads do not commit offsets; `kafka_offset` NULL behavior documented or wired (see item 4).
- **Test:** `docker compose up -d timescaledb kafka-1 kafka-2 kafka-3 redis` → `poetry run pytest -m integration -k persist`
- **Risk:** Medium — `ON CONFLICT` keys and column lists are unverified against live DDL; unit tests use a fake session.

## 3. ⬜ Real market-data providers with deterministic fallback — **P1**
- **Files:** `connectors/data_providers/{crypto,forex,equity}_provider.py`, `connectors/data_providers/{base,router}.py`, `api/routes/quotes.py`.
- **Acceptance:** Real API path is gated behind an env flag and a present API key; when the key is absent or the call errors, the provider falls back to the existing deterministic mock (anchored to `ANCHOR_DATE`). `QuoteProvider` interface, `QuoteRouter`, and `_CATALOG` unchanged. Dashboard mock mode (`api/mock_server.py`) still works with no keys.
- **Test:** `poetry run pytest tests/unit -k "provider or quotes" --no-cov`
- **Risk:** Medium — must not break dashboard mock mode or require live keys in CI.

## 4. ⬜ Propagate `kafka_offset` into the consumer envelope — **P1**
- **Files:** `core/orchestrator/message_bus.py` (`AlghrestConsumer.stream` / `_decode_record_value`), `core/persistence/events.py` (`normalize_kafka_message`).
- **Acceptance:** Persisted `trading.orders` / `trading.trade_proposals` rows carry the real Kafka offset instead of `NULL`; existing tests still pass.
- **Test:** `poetry run pytest tests/unit -k persistence --no-cov`
- **Risk:** Low–Medium — touches the shared consumer path used by every agent; keep the envelope shape backward-compatible.

## 5. ⬜ Paper-trading safety guardrail tests — **P1**
- **Files:** `core/config.py` (`ENVIRONMENT` gating), `agents/tier5_execution/exchange_executor.py`, connectors.
- **Acceptance:** A unit test proves real orders are refused unless `ENVIRONMENT=live` is set explicitly, and that `paper_trading`/`development` route to simulated fills. Default remains `paper_trading`.
- **Test:** `poetry run pytest tests/unit -k "safety or executor or config" --no-cov`
- **Risk:** High if regressed — this is the capital-protection rail. Add tests before any execution refactor.

## 6. ⬜ `options_strategist` (Deribit delta-neutral) design — **P2**
- **Files:** `agents/tier4_strategies/` (new), `connectors/exchanges/` (Deribit testnet client), `backtesting/engine.py`.
- **Acceptance:** A design doc + paper-only skeleton inheriting `BaseStrategy`, with the kill-switch guard and a backtest-validation stub against the Tier 4 thresholds. No live keys; `DERIBIT_TESTNET=true`.
- **Test:** `poetry run pytest tests/unit -k options --no-cov` (once skeleton + tests exist)
- **Risk:** Medium — options math + venue integration; keep simulation-only until backtests pass.

## 7. ⬜ `datetime.utcnow()` deprecation sweep — **P2**
- **Files:** broad — `agents/**`, `core/**`, `tests/**` (351 `DeprecationWarning`s remain after the marker fix).
- **Acceptance:** Replace naive `datetime.utcnow()` with timezone-aware `datetime.now(UTC)` where serialized/compared; warning count materially reduced without changing stored formats.
- **Test:** `poetry run pytest tests/unit --no-cov -q` (inspect warnings summary)
- **Risk:** Low per change but broad surface; do it in reviewable batches to avoid tz-format regressions.

## 8. ⬜ `scripts/run_tests.py` changed-only lint in CI — **P2**
- **Files:** `scripts/run_tests.py`, `.github/workflows/tests.yml` (already sets `fetch-depth: 0`).
- **Acceptance:** `lint --changed-only` resolves a PR base via `merge-base` and lints only changed Python files in CI; full-repo lint still available via `--all-files`.
- **Test:** `poetry run python scripts/run_tests.py lint --skip-mypy --changed-only`
- **Risk:** Low — affects CI ergonomics only, not test correctness.

## 9. ⬜ Coverage gate for `core/persistence` and `connectors` — **P3**
- **Files:** `pyproject.toml` (`[tool.coverage.run]`, `--cov-fail-under`), persistence + provider tests.
- **Acceptance:** Persistence and provider modules are inside the 70% gate with meaningful tests (not just import coverage).
- **Test:** `poetry run pytest --cov=core --cov=connectors --cov-report=term-missing`
- **Risk:** Low — may surface currently-untested branches; raise coverage with real assertions, not `# pragma: no cover`.

## 10. ⬜ Persistence observability (DLQ + error metrics) — **P3**
- **Files:** `agents/tier7_monitoring/persistence_writer.py`, `core/orchestrator/message_bus.py` (DLQ), dashboard `Kafka` page.
- **Acceptance:** `events_skipped` / `persist_failed` are exported as Prometheus counters and visible; poison persistence messages route to a DLQ rather than being silently skipped.
- **Test:** `poetry run pytest tests/unit -k persistence_writer --no-cov`
- **Risk:** Low–Medium — ensure metric cardinality stays bounded (label by topic, not by message id).

---

### Next 3 best tasks (recommended order)
1. **Item 2** — integration-verify persistence against a real Timescale container (the only unproven layer).
2. **Item 4** — propagate `kafka_offset` so audit rows are complete (small, contained).
3. **Item 3** — real market-data providers behind a fallback flag (highest external/value signal, dashboard-visible).
