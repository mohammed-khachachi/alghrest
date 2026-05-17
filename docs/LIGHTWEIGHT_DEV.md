# ALGHREST Lightweight Development Mode

This mode is for Windows PowerShell development on a low-resource machine. It
runs only the mock FastAPI backend and the React dashboard, so you can work on
the dashboard and mock market-data routes without starting the full trading
stack.

## Why Use It

The full ALGHREST stack starts Docker services, Kafka, Redis, TimescaleDB,
agent containers, and the ML inference server. That is useful for integration
work, but it is too heavy for many laptops.

Lightweight mode starts only:

- `api/mock_server.py`
- `api/routes/quotes.py`
- `connectors/data_providers`
- the dashboard Vite dev server

It does not start Docker, Kafka, Redis, TimescaleDB, agents, or the ML server.

## Create `venv-lite`

Run these commands from the repository root:

```powershell
py -3.12 -m venv venv-lite
.\venv-lite\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation scripts, allow scripts for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then activate the environment again:

```powershell
.\venv-lite\Scripts\Activate.ps1
```

## Install Python Requirements

Install only the lightweight backend dependencies and lightweight test tools:

```powershell
python -m pip install -r requirements-lite.txt
```

For dashboard development, install Node dependencies once:

```powershell
Set-Location dashboard
npm install
Set-Location ..
```

`requirements-lite.txt` intentionally excludes heavy trading, ML, Kafka, Redis,
database, migration, and exchange dependencies. Do not add `torch`, `ray`,
`ccxt`, `aiokafka`, `tensorflow`, `redis`, `sqlalchemy`, or `alembic` to this
file.

## Run Lightweight Development

From the repository root, with `venv-lite` activated:

```powershell
.\scripts\run_lite.ps1
```

The script sets:

- `ENVIRONMENT=development`
- `ENABLE_DEFI_AGENTS=false`

It starts:

- mock backend: `http://localhost:8000`
- dashboard: `http://localhost:5173`

Use `Ctrl+C` to stop the lightweight processes.

## Run Lightweight Checks

From the repository root:

```powershell
.\scripts\test_lite.ps1
```

The script runs only:

```powershell
ruff check .
pytest -m unit
```

It does not run integration tests, backtest tests, Docker, Kafka, Redis,
TimescaleDB, agents, or the ML server.

## Do Not Start These On A Weak Machine

Avoid these commands while using lightweight mode:

```powershell
docker compose up -d
pytest -m integration
pytest -m backtest
python run_agent.py agents.tier1_executive.cio_agent CIOAgent
Set-Location ml; python inference/server.py
```

Also avoid enabling DeFi agents. Keep this setting unchanged:

```env
ENABLE_DEFI_AGENTS=false
```

Never use lightweight mode to test live trading. Keep the environment in
development mode:

```env
ENVIRONMENT=development
```

Do not set:

```env
ENVIRONMENT=live
```
