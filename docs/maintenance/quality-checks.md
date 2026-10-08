# Quality validation — 2026-09-28

Current project inventory and GitHub publication are documented in [current project files](current-project-files.md). Dated verification sections below describe their original snapshots; historical statements about missing Git/hosted CI do not describe the current private GitHub repository.

## Latest follow-up — 2026-09-29

The runtime-efficiency follow-up passes **660 tests** with no failures or skips
and **76.6393%** combined statement/branch coverage. The 70% gate and measured
sources remain unchanged. Ruff, Black (187 files), isort, architecture checks,
strict MyPy (99 files), and the dashboard production build pass. This run reports
471 non-failing warnings. See [runtime-efficiency results](runtime-efficiency.md)
and `artifacts/performance/{full-tests.txt,tests.xml,coverage.json}` for evidence.
The results below describe the preceding September 28 baseline.

The complete Python suite passes its existing **70%** coverage gate. No coverage
source, exclusion, or threshold was relaxed. Coverage includes `agents`, `core`
and `connectors`, with branch measurement enabled.

| Check | Verified result |
| --- | --- |
| Full unit and integration suite | **600 passed, zero failed or skipped** |
| Combined statement/branch coverage used by the gate | **76.3933%** |
| Statement coverage | 6,744 / 8,460 (**79.72%**) |
| Branch coverage | 1,398 / 2,198 (**63.60%**) |
| Ruff | Passed repository-wide |
| Black / isort | Passed repository-wide; Black checked 182 files |
| Strict MyPy | Passed 99 files: agents/core/backtesting plus advisory adapters/API |
| Architecture boundaries | Passed all six application packages |
| Dependency consistency | All 411 installed packages compatible |
| Poetry lock | `poetry check --lock` passed |
| Optional NLP compatibility | spaCy 3.8.14 / thinc 8.3.13 / NumPy 2.2.6 import and tokenizer passed |

## Reproduce the full result

Use Python 3.12 and Poetry 2.4.1 from the repository root. Install every declared
group, including optional NLP and backtesting dependencies:

```powershell
poetry env use 3.12
poetry sync --all-groups
poetry check --lock
poetry run python scripts/check_architecture.py
poetry run ruff check .
poetry run black --check .
poetry run isort --check-only .
$env:MYPYPATH="src"
poetry run mypy --explicit-package-bases src/agents/ src/core/ src/backtesting/ src/connectors/advisory/ src/api/advisor.py src/api/services/advisory.py
```

Configure the isolated local profile described in
[execution recovery](../execution-recovery.md#isolated-local-infrastructure).
The service addresses must be local PostgreSQL `15432/alghrest_paper`, Redis
`16379`, and Kafka `19092`, with `ENVIRONMENT=paper_trading`. Preserve an existing
`.env`; never replace it with test configuration for another environment.

```powershell
docker compose -f docker-compose.paper.yml up -d --wait --wait-timeout 180
poetry run python -m scripts.paper provision
poetry run python -m scripts.test_with_services --timeout=60 --timeout-method=thread -q --tb=short --junitxml=artifacts/quality/tests.xml --cov-report=json:artifacts/quality/coverage.json --cov-report=xml:artifacts/quality/coverage.xml
```

The maintained runner creates a separate `alghrest_quality` database and selects
Redis DB 14 for persistence tests. Fixtures apply migrations and use unique test
books. The Kafka replay smoke uses a unique synthetic book/topic on the paper
stack and Redis DB 15, removing its own data afterward. Provisioning installs
schema/topics only. Runtime opening balances still require an explicit import.

For focused diagnostics without external services:

```powershell
poetry run pytest tests/unit --no-cov -q
```

That focused command does not certify coverage. The complete command above and
CI enforce the unchanged 70% gate. Without service opt-ins, persistence/replay
tests skip and the remaining suite does not reach the full coverage result.

The September 28 follow-up also corrects calendar-time/CAGR calculations, real
equity drawdown, and empirical Monte Carlo sampling. See [backtest conventions](../backtesting.md).
The real Kafka smoke now includes proposal approval, routing, execution,
crash/replay, closing the position, and exact fee reconciliation. The funding
follow-up adds atomic paper deposits and durable performance, with regression
tests for retries, concurrent requests, transaction rollback, cache outages,
unsettled fills, execution readiness, and UTC period boundaries.

## Repairs validated by these tests

- Declared missing runtime dependencies (`asyncpraw`, `psutil`) and test plugins,
  synchronized all dependency groups, and removed incompatible extraneous
  packages from the project environment.
- Resolved Ruff findings and strict type errors without disabling rules or
  strict checking. Aligned Black, Ruff and isort import formatting.
- Replaced obsolete integration doubles with tests of actual production
  contracts: Kafka envelopes, consumer initialization, durable execution state,
  Redis publication, HTTP routes, and cancellation/cleanup of background tasks.
- Corrected Kafka lag arithmetic, percentage-to-fraction volatility conversion,
  cross-venue concentration aggregation, and VectorBT metric compatibility.
  Added independent numerical and boundary assertions for these cases.
- Ensured monitoring still processes fills/critical alerts during a trading
  halt, and development audit simulations cannot trigger real kill-switch events.
  Unsupported DeFi/backtest paths fail explicitly instead of returning invented
  success metrics.
- Added regression coverage for intelligence/quant agents, strategy exits and
  sizing, risk thresholds, lifecycle failures, and Telegram behavior with mocked
  HTTP only.

## Continuous integration and evidence

`.github/workflows/tests.yml` runs the same checks and complete suite with isolated
paper services. It applies one aggregate coverage gate and uploads JUnit,
coverage JSON/XML and HTML. Empty backtest/benchmark selector jobs and the
unconditional deployment-readiness announcement were removed; implemented
backtest and latency checks are included in the complete suite. The separate
security scan is retained. Artifact upload uses v4, following the
[action's migration guidance](https://github.com/actions/upload-artifact#readme).

The workflow YAML and embedded setup code were checked locally. This workspace
has no initialized Git repository, so no GitHub Actions run or push was performed.
Local evidence is in the gitignored `artifacts/quality/` directory:
`advisory-final.txt`, `advisory-final.xml`, `advisory-final-coverage.json`,
`advisory-validation-summary.json` and individual lint/type/build logs.
The preceding funding/dependency evidence remains in `funding-*` artifacts. The HTML report is `htmlcov/index.html`.

The test run reports 464 warnings, principally deprecations; Poetry also reports
legacy metadata deprecations. These do not fail the configured checks. NLP's
separate language model, live exchange access, a production infrastructure
deployment, and the security scan were not validated by this quality run.

## Manual assistant and runtime follow-up

The independent assistant's core calculations, adapters and API now have tests
for dated contracts, stale/missing/malformed data, provenance, cache boundaries,
SQLite recovery, immutable closed sessions, intraday loss retention, EOD
drawdown, strict consistency thresholds, Chicago DST and constrained NQ/MNQ
sizing. Actual agent envelope tests cover legacy UTC signal timestamps and
market scoping; static isolation tests forbid trading/accounting I/O imports.

A real local startup exposed a missing RiskGovernor consumer initialization.
The fix initializes and closes the alert consumer, unwraps message payloads, and
cancels sibling loops on failure. Its regression tests pass. The isolated Kafka
smoke buys/closes 5 USDT of synthetic SOL, preserving account/venue and exact
fees across a crash/replay; runtime cash is never used for this test.

`npm run build` passes. The assistant is a separate lazy-loaded chunk. The
existing main dashboard bundle remains above Vite's 500 kB advisory threshold;
that non-failing warning was not suppressed. Browser checks verified the Arabic
research screen, real headlines from all five configured sources, unavailable
MNQ prices without invented scenarios, and a fee/slippage-aware size calculation.

The paper supervisor's stop/restart was checked against the real local stack.
Readiness blocks while stopped and recovers after sourced prices/reconciliation.
`artifacts/paper-setup/advisory-activation-readback.json` confirms 150 USDT,
revision 0, no positions, fills or deposits; [the archived paper status](https://github.com/mohammed-khachachi/alghrest/tree/f88e63be74c2f64ca68c5564c20863f97ca980c8/docs/paper-activation-status.json)
is a timestamped observation, not a continuing readiness guarantee.

No personal Earn2Trade profile or licensed CME stream is configured. The
optional assistant Docker configuration was parsed, not image-built/deployed.
CI now includes strict checks for the new advisory API/adapters. YAML is valid;
there is still no Git remote or hosted GitHub Actions result in this workspace.

## Access and AI control follow-up (2026-09-30)

The full isolated suite passed 696 tests with 77.3264% aggregate branch coverage;
the configured minimum remains 70%. The run included a disposable authenticated
Kafka broker, PostgreSQL AI-budget concurrency and synthetic paper crash/replay.
A final focused run passed 28 tests after the advisory startup guard and two
additional unauthorized-write cases. Ruff, Black, isort, strict MyPy (102 files),
architecture checks, Compose configuration and dashboard build passed. The CI
workflow enables the Kafka auth check; no hosted CI execution is claimed.

See [operation and limits](access-and-ai-limits.md) before starting services.
The full Confluent three-broker deployment was not run. Live trading, native
Windows credential ACL setup and prediction accuracy were not validated.
