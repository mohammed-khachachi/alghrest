# ALGHREST

An event-driven trading platform built with Python 3.12, Kafka, Redis, PostgreSQL/TimescaleDB, FastAPI, and a React dashboard. Agents communicate through messages and shared state. Durable accounting records fills, positions, and cash; opening balances must be imported explicitly.

The project is under development. DeFi agents, market-data demo providers, and parts of ML inference remain experimental. Keep `ENABLE_DEFI_AGENTS=false`; live trading requires a separate readiness review. Historical audits are in [docs/archive](docs/archive/).

## Repository map

```text
src/                 Installable Python application packages
  agents/            Agent lifecycle and seven trading tiers
  core/              Contracts, accounting, execution state, risk, messaging
  connectors/        Exchange and market-data adapters
  api/               FastAPI REST, WebSocket, and development mock service
  backtesting/       Strategy validation and simulation
  ml/                Model definitions, training, inference service
dashboard/          Independent React/Vite application
infra/              SQL migrations, service initialization, monitoring, scaffolds
scripts/            Operator and developer commands
tests/              Application unit and integration tests
research/           Independent HMM studies and their own dependencies/tests
examples/           Static website and dashboard previews
artifacts/          Local model weights/checkpoints; excluded from builds
docs/               Architecture, runbooks, current guides, historical evidence
mcp/                Optional model-manager integration
```

See [architecture and boundaries](docs/architecture.md), [development workflow](docs/monorepo-workflow.md), and the [documentation index](docs/README.md). Import names stay unchanged: `from core.config import settings`, not `from src.core...`.

## Development setup

Run from the repository root. Poetry installs the packages from `src/` in editable mode.

```powershell
poetry env use 3.12
poetry install
# Create a local configuration only when .env does not already exist.
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

For an existing pip-managed environment whose dependencies are already installed:

```powershell
python -m pip install --no-deps -e .
```

Run the dashboard without trading infrastructure:

```powershell
poetry run python -m api.mock_server
# In a second terminal:
Set-Location dashboard
npm ci
npm run dev
```

A smaller Python environment is described in [lightweight development](docs/LIGHTWEIGHT_DEV.md). The mock backend listens on port 8000 and Vite on 5173. Production and mock APIs share a port; start only the service you intend to use.

## Manual Nasdaq research

The independent [manual assistant](docs/manual-assistant.md) adds NQ/MNQ scenarios,
sourced news, an Earn2Trade EOD evaluation journal and contract-risk planning.
Run `poetry run python -m api.advisor` alongside Vite and open `/assistant`.
It has its own SQLite store and no order execution path. CME data requires your
explicit dated-contract import; no account size or licensed feed is assumed.

## Application commands

```powershell
# Full development infrastructure and configured agent services
# Review .env and the service configuration before starting.
docker compose up -d

# Individual agent (infrastructure must already be available)
poetry run python run_agent.py agents.tier2_intelligence.market_data_hub MarketDataHub

# API and separate ML inference service
poetry run uvicorn api.main:app --host 127.0.0.1 --port 8000
poetry run python -m ml.inference.server

# Architecture and tests
poetry run python scripts/check_architecture.py
poetry run pytest -m unit --no-cov        # focused diagnostics
poetry run python -m scripts.test_with_services # full gate; isolated paper stack required
poetry run mypy src/agents/ src/core/ src/backtesting/
```

`pyproject.toml` is the application tooling configuration. The default test coverage gate remains **70%**, with branch coverage enabled. See [quality checks](docs/maintenance/quality-checks.md) for complete dependencies, local services, and the full-suite command. Root tests do not discover research tests. See [accounting](docs/accounting.md) and [execution recovery](docs/execution-recovery.md) for ledger migrations, isolated paper infrastructure, explicit opening balances, and replay checks. `SYSTEM_CAPITAL_USD` never initializes ledger cash. New USDT paper contributions use the [explicit deposit command](docs/accounting.md#explicit-paper-deposits); unitized performance keeps deposits separate from returns and drawdown.

## Research and contributions

For invited collaborators, see [private repository development](docs/private-collaboration.md) for access, setup, included model assets, and a branch/pull-request workflow.

[HMM research](research/README.md) has separate environments and test commands. Static examples are documented [here](examples/README.md). Neither belongs in the runtime wheel or Docker image.

Place new modules in the package that owns their responsibility. Update contracts, migrations, tests, and documentation together when a message or persistence contract changes. Read [CLAUDE.md](CLAUDE.md) and [AGENTS.md](AGENTS.md) for agent conventions and hard risk limits. The [layout migration record](docs/maintenance/structure-migration.md) lists moved and removed files.
