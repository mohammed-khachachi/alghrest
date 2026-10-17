# ALGHREST

Multi-market trading research and decision support, with an advisory-only
Earn2Trade/TCP25 profile. Deterministic data, account, risk and evaluation-policy
checks govern the advice path. AI proposals cannot override those checks.

The project is under development. Strategy edge, complete rule-exact TCP25
simulation, pass/fail Monte Carlo and real-account readiness remain unproven.
Existing agent/execution code is retained for separate general profiles; the
`earn2trade_tcp25` profile blocks order submission, modification, cancellation,
liquidation and copying. Keep `ENABLE_DEFI_AGENTS=false`.

## Repository and development access

[GitHub repository](https://github.com/mohammed-khachachi/alghrest) is private.
Invited collaborators can clone it after accepting access. See
[private collaboration](docs/private-collaboration.md) for setup and the
branch/pull-request workflow. Never commit or share owner credentials.

`main` is the current development tree. Retired reports, recovery dumps and the
older HMM implementation are preserved in the private archive branch
`archive/pre-current-project-cleanup-20261006`, outside `main`. See the
[current file inventory](docs/maintenance/current-project-files.md).

## Repository map

The application uses Python 3.12, asyncio, Pydantic and FastAPI. The general
agent runtime uses Kafka, Redis and PostgreSQL/TimescaleDB; the independent
advisory journal uses SQLite. The dashboard uses React 18, TypeScript and Vite 5.

| Path | Purpose |
| --- | --- |
| `src/core/advisory/` | Market/account models, data guards, selection, risk, policies, strategy registry and advice contracts |
| `src/connectors/advisory/` | Replay, durable local research storage and advisory data adapters |
| `src/backtesting/` | Futures fills/costs, edge metrics, path risk, bootstrap, fixed-rule walk-forward and evaluation-event research |
| `src/api/` | Separate advisory API, general API and development mock |
| `src/agents/`, other core/connectors packages | Existing general-profile agents, accounting, messaging and execution/reconciliation |
| `src/ml/` | Experimental model definitions, training and inference service |
| `dashboard/` | React/TypeScript UI with Vite, npm manifest and lockfile |
| `tests/`, `scripts/` | Application tests and developer/operator commands |
| `infra/`, root Compose/Docker files | Schemas, infrastructure definitions, isolated profiles and documented scaffolds |
| `research/hmm_trading/` | Current independent educational HMM study and its own tests/dependencies |
| `artifacts/` | Included model assets and selected synthetic verification records; generated local state is ignored |
| `docs/`, `examples/`, `mcp/` | Guides, standalone Next.js presentation site/static examples and optional model-manager scaffold |

The six Python application packages are installed from `src/`. Import
`core.config`, `api.advisor`, etc.; do not prefix application imports with `src.`.
Research environments and their local `src` package are separate.

## Install the application

Use Python **3.12**. Poetry dependency declarations and `poetry.lock` are the
application dependency source; dashboard dependencies use `npm ci` and the
committed npm lockfile. Docker is needed for service integration work, not for
the local mock/advisory UI.

Windows PowerShell, from the repository root:

```powershell
git clone https://github.com/mohammed-khachachi/alghrest.git
Set-Location alghrest
poetry env use 3.12
poetry install
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

For every dependency group, use `poetry sync --all-groups`; optional NLP uses
`poetry install --with nlp`. See [quality checks](docs/maintenance/quality-checks.md)
for the full environment and native dependency requirements, and
[lightweight development](docs/LIGHTWEIGHT_DEV.md) for dashboard-only setup.
An existing pip environment with all dependencies installed can install the
application with `python -m pip install --no-deps -e .`.

## Run the advisory assistant

The advisory API listens on **127.0.0.1:8011**. Vite serves the UI on
**127.0.0.1:5173** and proxies `/assistant-api` to it.

Configure a separate local `ADVISORY_ACCESS_TOKEN` before opening the protected
assistant. The access helper, `poetry run python -m scripts.configure_access`,
requires Linux/WSL, preserves existing keys and never prints them. Native Windows
users must follow the local access requirements in
[access setup](docs/maintenance/access-and-ai-limits.md); do not put tokens in
Vite variables, URLs or committed files.

```powershell
$env:OPERATING_PROFILE = "earn2trade_tcp25"
$env:ENABLE_DEFI_AGENTS = "false"
$env:ADVISORY_KAFKA_SERVERS = ""
poetry run python -m api.advisor
# In a second terminal, from the repository root:
Set-Location dashboard
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/assistant` and enter the advisory token locally.
This page uses the independent SQLite research journal and does not open the
trading dashboard WebSocket. See [manual assistant](docs/manual-assistant.md).

Research/domain modules cover MES, MYM, MNQ, MGC, M2K, MCL, M6E, M6B, MHG and NQ.
The manual UI prioritizes NQ/MNQ. Dated contracts, licensed market data and
confirmed account/policy evidence must be supplied explicitly. Missing or
unhealthy inputs remain UNKNOWN/NO TRADE. No broker feed/API entitlement or
account capital is assumed.

## Check the integrated research workspace

With the local research services stopped, run this from the repository root:

```powershell
node scripts/check_research.mjs
```

The check runs focused regressions, starts all four research services with an
isolated temporary journal, verifies snapshots and PDF export during a market
service outage, then restarts the workspace and checks that saved records are
unchanged. It stops its own processes and saves a dated verification receipt
under `artifacts/research-check-*/`. Occupied ports are rejected without stopping
their owners. A pass verifies application behavior; it does not certify public
market-data freshness or trading readiness.

See [OpenTerminal integration](docs/maintenance/openterminal-integration.md)
for dependency setup, normal startup and manual browser verification.

## Run the dashboard demo

For ordinary UI development, start the mock backend on loopback port **8000**:

```powershell
poetry run uvicorn api.mock_server:app --host 127.0.0.1 --port 8000
# In another terminal:
Set-Location dashboard
npm ci
npm run dev
```

Open `http://127.0.0.1:5173/overview`; the mock accepts a blank access key and
supplies demo data. General API and mock share port 8000, so choose one. The
advisory API uses its separate port 8011. See [dashboard README](dashboard/README.md)
for routes, proxies and build commands. Demo quotes/holdings are not actual
licensed market or portfolio evidence.

## Verify changes

Focused application diagnostics, without the full coverage gate:

```powershell
poetry run python scripts/check_architecture.py
poetry run python -m pytest -m unit --no-cov
poetry run ruff check .
```

The default pytest configuration has a **70%** statement/branch coverage gate.
The complete service-backed run uses a disposable local paper/test configuration:

```powershell
# After configuring the isolated endpoints and credentials in the linked guide:
docker compose -f docker-compose.paper.yml up -d --wait --wait-timeout 180
poetry run python -m scripts.paper provision
poetry run python -m scripts.test_with_services -q
```

Follow [quality checks](docs/maintenance/quality-checks.md) and
[isolated execution recovery](docs/execution-recovery.md#isolated-local-infrastructure)
before that command. Do not replace a real account's configuration with test
settings. Provisioning creates schemas/topics, not opening cash balances.

The sanitized local upload snapshot on 2026-10-06 passed **2,112 tests**, with
**53 external-service opt-ins skipped** and **82.16%** combined coverage when
advisory service/backtesting sources were also measured. This is local evidence,
not a hosted CI or live-trading pass. GitHub Actions is configured in
`.github/workflows/tests.yml`; inspect its actual run result. Research tests run
inside their separate HMM directory/environment.

## Research, models and remaining work

Futures research includes explicit fees/slippage, guarded shared strategy rules,
net edge statistics, loss-streak/path analysis, paired block-bootstrap uncertainty,
frozen walk-forward experiments and event-by-event evaluation replay. Synthetic
examples remain EXPERIMENT; they do not certify positive out-of-sample edge or
an official TCP25 pass. Real policy bands, calendar/margin evidence, intraday
extrema coverage, licensed history and calibrated evaluation distributions are
still required. See [migration evidence](docs/maintenance/tcp25-migration.md).

Both existing CNN/PPO assets are included under `artifacts/models/`; the
experimental inference server does not automatically load them. Model presence
is not validation. DeFi and infrastructure scaffolds retain their documented
limitations. Financial opening balances are explicit durable imports;
`SYSTEM_CAPITAL_USD` does not initialize ledger cash.

Start with [documentation](docs/README.md), [architecture](docs/architecture.md),
[development workflow](docs/monorepo-workflow.md), [accounting](docs/accounting.md),
[current HMM research](research/README.md) and [artifact notes](artifacts/README.md).
Read `CLAUDE.md`, `AGENTS.md` and scoped instructions before editing. Keep changes
small, preserve deterministic safety boundaries, add meaningful tests for changed
behavior and submit pull requests for review.
