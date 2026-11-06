# OpenBB Financial Data Acquisition & Research Layer

This document describes the modular integration of **OpenBB Platform** into the **Alghrest** multi-agent trading and research system.

---

## 1. Architecture Overview

OpenBB is integrated strictly as a **read-only financial data acquisition, normalization, and research layer** under `src/connectors/data_providers/`. It never executes trades or bypasses Alghrest's risk/execution gates.

```
OpenBB Data Providers (yfinance, fmp, polygon, tiingo, intrinio, alpha_vantage, fred)
        |
        |  asyncio.to_thread + bounded timeout (non-blocking)
        v
OpenBBAdapter / OpenBBQuoteProvider (src/connectors/data_providers/openbb_adapter.py)
        |
        |  Strict validation: UTC normalization, OHLC envelope checks,
        |  finite positive Decimals, duplicate timestamp deduplication
        v
Normalized Domain Models
  - OHLCVBar (src/core/data/models.py)
  - Quote & HistoricalBar (src/connectors/data_providers/base.py)
  - MarketSnapshot & Candle (src/core/advisory/models.py)
  - TerminalCandle (src/core/advisory/openterminal_research.py)
        |
        v
OpenBBIngestionPipeline (src/connectors/data_providers/openbb_ingestion.py)
        |
        +--> TimescaleDB (`market_data.ohlcv_bars` hypertable, idempotent upsert)
        |
        +--> Apache Kafka (`prices.realtime` topic, `message_type="ohlcv"`)
        |
        +--> Redis (`prices:{symbol}` 60s ticker cache & `openbb:history:*` cache)
        |
        v
FastAPI (`/api/quotes`, `/api/history`, `/api/openbb/*`), Tier 2 Agents (`MacroEconomist`), & Research
```

---

## 2. Required Dependencies

Dependencies are managed with Poetry in [`pyproject.toml`](../pyproject.toml) and locked in `poetry.lock` for Python 3.12 compatibility:

- `openbb-core == 1.3.6`
- `openbb-equity == 1.3.5`
- `openbb-crypto == 1.3.5`
- `openbb-currency == 1.3.5`
- `openbb-economy == 1.3.5`
- `openbb-yfinance == 1.3.6`
- `openbb-fred == 1.3.5`
- `openbb-fmp == 1.3.5`
- `openbb-polygon == 1.3.5`
- `openbb-tiingo == 1.3.5`

Install via Poetry:

```bash
poetry install
```

---

## 3. Environment Variables & Provider Configuration

All OpenBB settings are defined in [`src/core/config.py`](../src/core/config.py) (`Settings`) and documented in [`.env.example`](../.env.example). Credentials use Pydantic `SecretStr` so keys are never leaked in logs.

| Environment Variable | Default | Description |
|---|---|---|
| `OPENBB_ENABLED` | `false` | Enable OpenBB in `QuoteRouter` and Tier 2 `MacroEconomist`. |
| `OPENBB_FALLBACK_TO_MOCK` | `true` | Fall back to deterministic mock providers if an upstream provider fails. |
| `OPENBB_DEFAULT_EQUITY_PROVIDER` | `yfinance` | Default OpenBB provider for equity quotes and historical OHLCV. |
| `OPENBB_DEFAULT_CRYPTO_PROVIDER` | `yfinance` | Default OpenBB provider for crypto historical OHLCV. |
| `OPENBB_DEFAULT_FOREX_PROVIDER` | `yfinance` | Default OpenBB provider for forex historical OHLCV. |
| `OPENBB_DEFAULT_MACRO_PROVIDER` | `fred` | Default OpenBB provider for macroeconomic series (`fred_series`). |
| `OPENBB_TIMEOUT_SECONDS` | `15.0` | Per-request timeout (seconds) for async worker thread execution. |
| `OPENBB_CACHE_TTL_SECONDS` | `300` | Redis cache TTL (seconds) for historical OHLCV queries (`0` disables caching). |
| `OPENBB_PAT` | `""` | Optional OpenBB Hub Personal Access Token. |
| `OPENBB_FMP_API_KEY` | `""` | Financial Modeling Prep API key. |
| `OPENBB_POLYGON_API_KEY` | `""` | Polygon.io API key. |
| `OPENBB_TIINGO_API_KEY` | `""` | Tiingo API token. |
| `OPENBB_INTRINIO_API_KEY` | `""` | Intrinio API key. |
| `OPENBB_ALPHA_VANTAGE_API_KEY` | `""` | Alpha Vantage API key. |
| `FRED_API_KEY` | `""` | St. Louis Fed FRED API key (shared with `MacroEconomist`). |

---

## 4. Retrieving Historical Data & Pipeline Ingestion

### Working Code Example

```python
import asyncio
from datetime import date

from connectors.data_providers.base import AssetClass
from connectors.data_providers.openbb_adapter import OpenBBAdapter
from connectors.data_providers.openbb_ingestion import OpenBBIngestionPipeline
from core.data.models import Timeframe


async def main() -> None:
    adapter = OpenBBAdapter()

    # 1. Fetch normalized, validated OHLCVBar objects
    bars = await adapter.fetch_historical_ohlcv(
        "AAPL",
        asset_class=AssetClass.EQUITY,
        timeframe=Timeframe.D1,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 5, 1),
        provider="yfinance",
    )
    print(f"Fetched {len(bars)} validated bars; latest close={bars[-1].close}")

    # 2. Convert to advisory/research models
    terminal_candles = adapter.to_terminal_candles(bars)
    snapshot = adapter.to_advisory_snapshot(
        bars,
        instrument_id="BTCUSDT-PERP",
        interval="1d",
        provider="yfinance",
    )
    print(f"Snapshot candles={len(snapshot.candles)}, terminal_candles={len(terminal_candles)}")

    # 3. Ingest into TimescaleDB, Kafka (prices.realtime), and Redis (prices:{symbol})
    pipeline = OpenBBIngestionPipeline(adapter=adapter)
    try:
        summary = await pipeline.fetch_and_ingest(
            "AAPL",
            asset_class=AssetClass.EQUITY,
            timeframe=Timeframe.D1,
            start_date=date(2025, 1, 1),
            end_date=date(2025, 5, 1),
            provider="yfinance",
            persist_db=False,      # Set True when DATABASE_URL is running
            publish_kafka=False,   # Set True with initialized AlghrestProducer
            cache_redis=False,     # Set True with initialized StateManager
        )
        print("Ingestion summary:", summary.to_dict())
    finally:
        await pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### FastAPI Endpoints

- `GET /api/openbb/providers`: Inspect OpenBB status, configured default providers, and supported provider list.
- `GET /api/openbb/historical?symbol=AAPL&asset_class=equity&timeframe=1d&start_date=2025-01-01&provider=yfinance`: Retrieve validated `OHLCVBar` records in JSON format.
- `GET /api/quotes?symbols=AAPL,BTC,EUR/USD` and `GET /api/history?symbol=AAPL&days=30`: Automatically backed by `OpenBBQuoteProvider` when `OPENBB_ENABLED=true`.

---

## 5. How Data Enters the Existing Pipeline

1. **TimescaleDB (`market_data.ohlcv_bars`)**:
   - `OpenBBIngestionPipeline.persist_bars_to_timescaledb(bars)` performs an idempotent `INSERT ... ON CONFLICT (time, symbol, exchange, timeframe) DO UPDATE` inside an `asyncpg` transaction guarded by `DatabaseCircuitBreaker` and `with_exponential_backoff`.
2. **Apache Kafka (`prices.realtime`)**:
   - `OpenBBIngestionPipeline.publish_bars_to_kafka(bars)` wraps each `OHLCVBar` in an `AgentMessage(message_type="ohlcv")` with partition key `openbb:{symbol}` and publishes via `AlghrestProducer`.
3. **Redis (`StateManager`)**:
   - Updates `prices:{symbol}` (60s TTL) for fast last-price lookups and caches historical series at `openbb:history:{asset_class}:{symbol}:{timeframe}:{provider}` (`OPENBB_CACHE_TTL_SECONDS`).

---

## 6. Running Tests

Run unit tests (uses deterministic mocks; no API keys or internet access required):

```bash
PYTHONPATH=src .venv/bin/pytest tests/unit/test_openbb_adapter.py -v --no-cov
```

Run the full quality gate:

```bash
PYTHONPATH=src .venv/bin/pytest -m unit --no-cov
.venv/bin/ruff check src/connectors/data_providers/ src/api/routes/quotes.py tests/unit/test_openbb_adapter.py
PYTHONPATH=src .venv/bin/mypy --strict src/agents/ src/core/ src/connectors/ src/api/
.venv/bin/python scripts/check_architecture.py
```

---

## 7. Known Provider Limitations

- **Endpoint heterogeneity**: Not all OpenBB providers support every asset class. For example, `intrinio` supports `equity.historical` and `equity.quote`, but does not support `crypto.historical` or `forex.historical`. `PROVIDER_CAPABILITIES` in `openbb_adapter.py` enforces explicit capability checks before invoking a provider.
- **Intraday history windows**: Free tiers on `yfinance` restrict `1m` historical bars to recent windows (typically 7–30 days), whereas `1d` bars support multi-year history.
- **Rate limits & API keys**: Providers such as `fmp`, `polygon`, `tiingo`, `intrinio`, `alpha_vantage`, and `fred` require valid API keys in `.env` and enforce provider-specific rate limits.
