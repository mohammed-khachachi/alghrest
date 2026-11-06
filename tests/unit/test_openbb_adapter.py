"""Unit and pipeline tests for the OpenBB financial data adapter and ingestion layer.

Covers:
- Adapter initialization & provider configuration
- Symbol normalization across EQUITY, CRYPTO, and FOREX providers
- Historical OHLCV retrieval & normalization into `OHLCVBar`, `HistoricalBar`,
  `TerminalCandle`, and `MarketSnapshot`
- Data quality validation: missing fields, NaN/Inf, non-positive prices,
  negative volume, inverted OHLC envelopes, future timestamps, duplicate
  timestamp deduplication, and timezone normalization to UTC
- Provider capability checks, timeouts, and error handling
- `OpenBBQuoteProvider` & `QuoteRouter` integration with safe mock fallback
- `OpenBBIngestionPipeline` integration with TimescaleDB, Kafka, and Redis
- FastAPI `/api/openbb/providers` and `/api/openbb/historical` routes
- `MacroEconomist` FRED series retrieval via OpenBB
"""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from agents.tier2_intelligence.macro_economist import MacroEconomist
from api.routes.quotes import router as quotes_router
from connectors.data_providers.base import AssetClass as ProviderAssetClass
from connectors.data_providers.openbb_adapter import (
    OpenBBAdapter,
    OpenBBDataValidationError,
    OpenBBProviderError,
    OpenBBQuoteProvider,
    OpenBBUnavailableError,
    normalize_provider_symbol,
)
from connectors.data_providers.openbb_ingestion import OpenBBIngestionPipeline
from connectors.data_providers.router import build_router
from core.config import Settings
from core.data.models import Exchange, KafkaTopic, OHLCVBar, Timeframe


def _make_fake_obb(
    *,
    historical_rows: list[dict[str, Any]] | None = None,
    quote_rows: list[dict[str, Any]] | None = None,
    macro_rows: list[dict[str, Any]] | None = None,
    raise_exc: Exception | None = None,
    sleep_seconds: float = 0.0,
) -> SimpleNamespace:
    """Construct a deterministic fake OpenBB SDK client with call tracking."""
    calls: list[tuple[str, dict[str, Any]]] = []
    creds = SimpleNamespace(
        fmp_api_key="",
        polygon_api_key="",
        tiingo_token="",
        intrinio_api_key="",
        alpha_vantage_api_key="",
        fred_api_key="",
    )

    def _make_endpoint(name: str, rows: list[dict[str, Any]] | None) -> Any:
        def _fn(**kwargs: Any) -> Any:
            calls.append((name, kwargs))
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            if raise_exc is not None:
                raise raise_exc
            return SimpleNamespace(results=rows if rows is not None else [])

        return _fn

    return SimpleNamespace(
        calls=calls,
        user=SimpleNamespace(credentials=creds),
        account=SimpleNamespace(login=MagicMock()),
        equity=SimpleNamespace(
            price=SimpleNamespace(
                historical=_make_endpoint("equity.price.historical", historical_rows),
                quote=_make_endpoint("equity.price.quote", quote_rows),
            )
        ),
        crypto=SimpleNamespace(
            price=SimpleNamespace(
                historical=_make_endpoint("crypto.price.historical", historical_rows),
            )
        ),
        currency=SimpleNamespace(
            price=SimpleNamespace(
                historical=_make_endpoint("currency.price.historical", historical_rows),
            )
        ),
        economy=SimpleNamespace(
            fred_series=_make_endpoint("economy.fred_series", macro_rows),
        ),
    )


@pytest.mark.unit
class TestOpenBBAdapterConfiguration:
    def test_adapter_initialization_and_provider_defaults(self) -> None:
        cfg = Settings(
            openbb_enabled=True,
            openbb_default_equity_provider="fmp",
            openbb_default_crypto_provider="tiingo",
            openbb_default_forex_provider="polygon",
            openbb_default_macro_provider="fred",
            openbb_timeout_seconds=12.5,
            openbb_fmp_api_key=SecretStr("secret-fmp-key"),
            fred_api_key="secret-fred-key",
        )
        fake_obb = _make_fake_obb(
            historical_rows=[
                {
                    "date": "2025-05-01",
                    "open": 100.0,
                    "high": 105.0,
                    "low": 99.0,
                    "close": 104.0,
                    "volume": 1000,
                }
            ]
        )
        adapter = OpenBBAdapter(config=cfg, obb_client=fake_obb)
        assert adapter.is_available is True
        assert adapter.timeout_seconds == 12.5
        assert adapter.default_provider_for(ProviderAssetClass.EQUITY) == "fmp"
        assert adapter.default_provider_for(ProviderAssetClass.CRYPTO) == "tiingo"
        assert adapter.default_provider_for(ProviderAssetClass.FOREX) == "polygon"
        assert adapter.default_provider_for("macro") == "fred"
        assert "yfinance" in adapter.supported_providers("equity.historical")
        assert "fred" in adapter.supported_providers("macro.fred_series")

    @pytest.mark.asyncio
    async def test_credentials_injected_into_obb_client_on_first_call(self) -> None:
        cfg = Settings(
            openbb_enabled=True,
            openbb_fmp_api_key=SecretStr("test-fmp-token"),
            openbb_polygon_api_key=SecretStr("test-poly-token"),
            openbb_pat=SecretStr("test-pat-token"),
            fred_api_key="test-fred-token",
        )
        fake_obb = _make_fake_obb(
            historical_rows=[
                {
                    "date": "2025-05-01",
                    "open": 200.0,
                    "high": 210.0,
                    "low": 195.0,
                    "close": 205.0,
                    "volume": 50000,
                }
            ]
        )
        adapter = OpenBBAdapter(config=cfg, obb_client=fake_obb)
        bars = await adapter.fetch_historical_ohlcv("AAPL", provider="fmp")
        assert len(bars) == 1
        assert fake_obb.user.credentials.fmp_api_key == "test-fmp-token"
        assert fake_obb.user.credentials.polygon_api_key == "test-poly-token"
        assert fake_obb.user.credentials.fred_api_key == "test-fred-token"
        fake_obb.account.login.assert_called_once_with(pat="test-pat-token")

    @pytest.mark.asyncio
    async def test_unavailable_sdk_raises_typed_error(self) -> None:
        adapter = OpenBBAdapter(obb_client=None)
        adapter._obb = None
        assert adapter.is_available is False
        with pytest.raises(OpenBBUnavailableError, match="not installed"):
            await adapter.fetch_historical_ohlcv("AAPL")

    def test_symbol_normalization_across_asset_classes(self) -> None:
        assert normalize_provider_symbol("btc/usdt", ProviderAssetClass.CRYPTO, "yfinance") == "BTC-USD"
        assert normalize_provider_symbol("BTC/USDT", ProviderAssetClass.CRYPTO, "fmp") == "BTCUSD"
        assert normalize_provider_symbol("eur/usd", ProviderAssetClass.FOREX, "yfinance") == "EURUSD=X"
        assert normalize_provider_symbol("EUR/USD", ProviderAssetClass.FOREX, "polygon") == "EURUSD"
        assert normalize_provider_symbol("aapl", ProviderAssetClass.EQUITY, "yfinance") == "AAPL"
        with pytest.raises(OpenBBDataValidationError):
            normalize_provider_symbol("   ", ProviderAssetClass.EQUITY, "yfinance")


@pytest.mark.unit
class TestOpenBBHistoricalAndNormalization:
    @pytest.mark.asyncio
    async def test_fetch_historical_ohlcv_normalizes_sorts_and_deduplicates(self) -> None:
        ny_tz = timezone(timedelta(hours=-4))
        raw_rows = [
            # Out of order + timezone-aware timestamp
            {
                "date": datetime(2025, 5, 2, 16, 0, tzinfo=ny_tz),
                "open": "212.50",
                "high": "215.00",
                "low": "210.25",
                "close": "214.10",
                "volume": 1200000,
                "vwap": "213.40",
                "transactions": 4500,
            },
            # Earlier timestamp (initial duplicate that should be overwritten by the next entry)
            {
                "date": "2025-05-01T00:00:00Z",
                "open": 208.0,
                "high": 211.0,
                "low": 207.0,
                "close": 209.0,
                "volume": 900000,
            },
            # Duplicate timestamp for 2025-05-01 with updated close
            {
                "date": "2025-05-01T00:00:00+00:00",
                "open": 208.0,
                "high": 212.0,
                "low": 207.0,
                "close": 210.5,
                "volume": 950000,
            },
        ]
        fake_obb = _make_fake_obb(historical_rows=raw_rows)
        adapter = OpenBBAdapter(obb_client=fake_obb)

        bars = await adapter.fetch_historical_ohlcv(
            "aapl",
            asset_class=ProviderAssetClass.EQUITY,
            timeframe=Timeframe.D1,
            start_date=date(2025, 5, 1),
            end_date=date(2025, 5, 3),
            provider="yfinance",
        )
        assert len(bars) == 2
        assert bars[0].symbol == "AAPL"
        assert bars[0].exchange == Exchange.OPENBB
        assert bars[0].timeframe == Timeframe.D1
        assert bars[0].time == datetime(2025, 5, 1, 0, 0, tzinfo=UTC)
        assert bars[0].close == Decimal("210.5")
        assert bars[0].volume == Decimal("950000")

        # Second bar converted from EDT (-04:00) to UTC (20:00)
        assert bars[1].time == datetime(2025, 5, 2, 20, 0, tzinfo=UTC)
        assert bars[1].close == Decimal("214.10")
        assert bars[1].vwap == Decimal("213.40")
        assert bars[1].trade_count == 4500

        # Verify conversions to HistoricalBar, TerminalCandle, and MarketSnapshot
        hist_bars = adapter.to_historical_bars(bars, price_decimals=2)
        assert len(hist_bars) == 2
        assert hist_bars[0].date == "2025-05-01"
        assert hist_bars[1].close == 214.10

        term_candles = adapter.to_terminal_candles(bars)
        assert len(term_candles) == 2
        assert term_candles[0].close == Decimal("210.5")

        snapshot = adapter.to_advisory_snapshot(
            bars,
            instrument_id="BTCUSDT-PERP",
            interval="1d",
            provider="yfinance",
        )
        assert snapshot.instrument_id == "BTCUSDT-PERP"
        assert len(snapshot.candles) == 2
        assert snapshot.quality is not None
        assert snapshot.quality.provider_id == "openbb-yfinance"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "bad_row,expected_msg",
        [
            (
                {"date": "2025-05-01", "open": None, "high": 105, "low": 95, "close": 100},
                "Missing or invalid open",
            ),
            (
                {"date": "2025-05-01", "open": "NaN", "high": 105, "low": 95, "close": 100},
                "Non-finite open",
            ),
            (
                {"date": "2025-05-01", "open": -10, "high": 105, "low": 95, "close": 100},
                "Non-positive open",
            ),
            (
                # High < Close (invalid OHLC envelope)
                {"date": "2025-05-01", "open": 100, "high": 102, "low": 95, "close": 105},
                "Invalid OHLC envelope",
            ),
            (
                # Low > Open (invalid OHLC envelope)
                {"date": "2025-05-01", "open": 90, "high": 105, "low": 95, "close": 100},
                "Invalid OHLC envelope",
            ),
            (
                {"date": "2025-05-01", "open": 100, "high": 105, "low": 95, "close": 100, "volume": -5},
                "Negative volume",
            ),
            (
                {
                    "date": (datetime.now(UTC) + timedelta(days=30)).isoformat(),
                    "open": 100,
                    "high": 105,
                    "low": 95,
                    "close": 100,
                },
                "Future timestamp",
            ),
            (
                {"date": "not-a-timestamp", "open": 100, "high": 105, "low": 95, "close": 100},
                "Malformed timestamp",
            ),
        ],
    )
    async def test_malformed_ohlcv_records_rejected(
        self, bad_row: dict[str, Any], expected_msg: str
    ) -> None:
        fake_obb = _make_fake_obb(historical_rows=[bad_row])
        adapter = OpenBBAdapter(obb_client=fake_obb)
        with pytest.raises(OpenBBDataValidationError, match=expected_msg):
            await adapter.fetch_historical_ohlcv("AAPL")

    @pytest.mark.asyncio
    async def test_empty_provider_response_rejected(self) -> None:
        fake_obb = _make_fake_obb(historical_rows=[])
        adapter = OpenBBAdapter(obb_client=fake_obb)
        with pytest.raises(OpenBBDataValidationError, match="0 historical records"):
            await adapter.fetch_historical_ohlcv("AAPL")


@pytest.mark.unit
class TestOpenBBProviderCapabilitiesAndErrors:
    @pytest.mark.asyncio
    async def test_unsupported_provider_or_capability_raises_provider_error(self) -> None:
        fake_obb = _make_fake_obb()
        adapter = OpenBBAdapter(obb_client=fake_obb)

        with pytest.raises(OpenBBProviderError, match="Unsupported OpenBB provider"):
            await adapter.fetch_historical_ohlcv("AAPL", provider="nonexistent_provider")

        # Intrinio does not support crypto.historical in PROVIDER_CAPABILITIES
        with pytest.raises(OpenBBProviderError, match="does not support 'crypto.historical'"):
            await adapter.fetch_historical_ohlcv(
                "BTC/USDT",
                asset_class=ProviderAssetClass.CRYPTO,
                provider="intrinio",
            )

    @pytest.mark.asyncio
    async def test_provider_timeout_and_runtime_exceptions_wrapped(self) -> None:
        cfg = Settings(openbb_timeout_seconds=0.05)
        slow_obb = _make_fake_obb(sleep_seconds=0.25)
        adapter = OpenBBAdapter(config=cfg, obb_client=slow_obb)
        with pytest.raises(OpenBBProviderError, match="timed out"):
            await adapter.fetch_historical_ohlcv("AAPL")

        failing_obb = _make_fake_obb(raise_exc=RuntimeError("Upstream HTTP 429 rate limit"))
        adapter2 = OpenBBAdapter(obb_client=failing_obb)
        with pytest.raises(OpenBBProviderError, match="Upstream HTTP 429 rate limit"):
            await adapter.fetch_historical_ohlcv("AAPL") if False else await adapter2.fetch_historical_ohlcv("AAPL")


@pytest.mark.unit
class TestQuoteRouterAndIngestionPipeline:
    @pytest.mark.asyncio
    async def test_quote_router_with_openbb_and_fallback_to_mock(self) -> None:
        fake_obb = _make_fake_obb(
            quote_rows=[
                {
                    "last_price": 230.50,
                    "open": 225.00,
                    "high": 232.00,
                    "low": 224.50,
                    "prev_close": 226.00,
                    "bid": 230.45,
                    "ask": 230.55,
                    "volume": 42000000,
                    "last_timestamp": "2025-05-02T19:59:00Z",
                }
            ]
        )
        cfg = Settings(openbb_enabled=True, openbb_fallback_to_mock=True)
        adapter = OpenBBAdapter(config=cfg, obb_client=fake_obb)
        router = build_router(config=cfg, adapter=adapter, use_openbb=True)

        q = await router.quote("AAPL")
        assert q.symbol == "AAPL"
        assert q.price == 230.50
        assert q.bid == 230.45
        assert q.ask == 230.55

        # When OpenBB fails and fallback_to_mock=True, router seamlessly falls back to MockProvider
        failing_obb = _make_fake_obb(raise_exc=RuntimeError("upstream offline"))
        failing_adapter = OpenBBAdapter(config=cfg, obb_client=failing_obb)
        fallback_router = build_router(config=cfg, adapter=failing_adapter, use_openbb=True)
        fallback_quote = await fallback_router.quote("BTC")
        assert fallback_quote.symbol == "BTC"
        assert fallback_quote.price > 0

        # When fallback_to_mock=False, error propagates
        strict_provider = OpenBBQuoteProvider(
            ProviderAssetClass.EQUITY,
            adapter=failing_adapter,
            fallback_to_mock=False,
        )
        with pytest.raises(OpenBBProviderError):
            await strict_provider.quote("AAPL")

    @pytest.mark.asyncio
    async def test_ingestion_pipeline_timescaledb_kafka_and_redis(self) -> None:
        fake_obb = _make_fake_obb(
            historical_rows=[
                {
                    "date": "2025-05-01T00:00:00Z",
                    "open": 64000.0,
                    "high": 65500.0,
                    "low": 63800.0,
                    "close": 65000.0,
                    "volume": 1250.5,
                },
                {
                    "date": "2025-05-02T00:00:00Z",
                    "open": 65000.0,
                    "high": 66200.0,
                    "low": 64700.0,
                    "close": 65800.0,
                    "volume": 1420.0,
                },
            ]
        )
        adapter = OpenBBAdapter(obb_client=fake_obb)

        # Mock asyncpg Pool + Connection + Transaction
        mock_conn = AsyncMock()
        mock_tx = AsyncMock()
        mock_tx.__aenter__.return_value = mock_tx
        mock_tx.__aexit__.return_value = False
        mock_conn.transaction = MagicMock(return_value=mock_tx)

        mock_acquire = AsyncMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = False
        mock_pool = MagicMock()
        mock_pool.acquire.return_value = mock_acquire

        # Mock Kafka AlghrestProducer
        mock_producer = AsyncMock()

        # Mock Redis StateManager
        redis_store: dict[str, str] = {}

        async def _fake_setex(key: str, ttl: int, val: str) -> None:
            redis_store[key] = val

        async def _fake_get(key: str) -> str | None:
            return redis_store.get(key)

        mock_redis = AsyncMock()
        mock_redis.setex.side_effect = _fake_setex
        mock_redis.get.side_effect = _fake_get
        mock_state = SimpleNamespace(redis=mock_redis)

        pipeline = OpenBBIngestionPipeline(
            adapter=adapter,
            db_pool=mock_pool,
            producer=mock_producer,
            state=mock_state,  # type: ignore[arg-type]
        )

        summary = await pipeline.fetch_and_ingest(
            "BTC/USDT",
            asset_class=ProviderAssetClass.CRYPTO,
            timeframe=Timeframe.D1,
            provider="yfinance",
            persist_db=True,
            publish_kafka=True,
            cache_redis=True,
        )

        assert summary.symbol == "BTC/USDT"
        assert summary.bars_fetched == 2
        assert summary.db_rows_upserted == 2
        assert summary.kafka_messages_published == 2
        assert summary.redis_cached is True

        # Verify TimescaleDB executemany call
        mock_conn.executemany.assert_awaited_once()
        sql_arg, records_arg = mock_conn.executemany.call_args.args
        assert "INSERT INTO market_data.ohlcv_bars" in sql_arg
        assert len(records_arg) == 2
        assert records_arg[1][1] == "BTC/USDT"
        assert records_arg[1][2] == "openbb"
        assert records_arg[1][7] == Decimal("65800.0")

        # Verify Kafka messages published to prices.realtime
        assert mock_producer.send.await_count == 2
        first_call = mock_producer.send.call_args_list[0]
        assert first_call.args[0] == KafkaTopic.PRICES_REALTIME
        assert first_call.kwargs["key"] == "openbb:BTC/USDT"
        assert first_call.args[1].message_type == "ohlcv"

        # Verify Redis ticker cache and historical cache round-trip
        assert "prices:BTC/USDT" in redis_store
        price_cached = json.loads(redis_store["prices:BTC/USDT"])
        assert price_cached["last"] == 65800.0
        assert price_cached["source"] == "openbb:yfinance"

        cached_bars = await pipeline.get_cached_history(
            "BTC/USDT",
            asset_class=ProviderAssetClass.CRYPTO,
            timeframe=Timeframe.D1,
            provider="yfinance",
        )
        assert cached_bars is not None
        assert len(cached_bars) == 2
        assert isinstance(cached_bars[0], OHLCVBar)
        assert cached_bars[1].close == Decimal("65800.0")


@pytest.mark.unit
class TestFastAPIOpenBBRoutesAndMacroIntegration:
    def test_fastapi_openbb_endpoints(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_obb = _make_fake_obb(
            historical_rows=[
                {
                    "date": "2025-05-01",
                    "open": 410.0,
                    "high": 418.0,
                    "low": 408.0,
                    "close": 415.5,
                    "volume": 18000000,
                }
            ]
        )
        test_adapter = OpenBBAdapter(obb_client=fake_obb)
        monkeypatch.setattr("api.routes.quotes._openbb", lambda: test_adapter)

        app = FastAPI()
        app.include_router(quotes_router)
        client = TestClient(app)

        prov_resp = client.get("/api/openbb/providers")
        assert prov_resp.status_code == 200
        prov_data = prov_resp.json()
        assert prov_data["sdk_available"] is True
        assert "yfinance" in prov_data["providers"]

        hist_resp = client.get(
            "/api/openbb/historical",
            params={
                "symbol": "MSFT",
                "asset_class": "equity",
                "timeframe": "1d",
                "start_date": "2025-05-01",
                "provider": "yfinance",
            },
        )
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert hist_data["symbol"] == "MSFT"
        assert hist_data["count"] == 1
        assert hist_data["bars"][0]["close"] == "415.5"

        # Invalid provider returns 502
        err_resp = client.get(
            "/api/openbb/historical",
            params={"symbol": "MSFT", "provider": "invalid_prov"},
        )
        assert err_resp.status_code == 502

    @pytest.mark.asyncio
    async def test_macro_economist_uses_openbb_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fake_obb = _make_fake_obb(
            macro_rows=[
                {"date": "2025-04-01", "value": 4.50},
                {"date": "2025-05-01", "value": 4.25},
            ]
        )
        monkeypatch.setattr("core.config.settings.openbb_enabled", True)
        agent = MacroEconomist()
        agent._openbb_adapter = OpenBBAdapter(obb_client=fake_obb)

        result = await agent._fetch_fred_series("FEDFUNDS")
        assert result is not None
        assert result["value"] == 4.25
        assert result["previous"] == 4.50
        assert result["change"] == pytest.approx(-0.25)
        assert result["date"] == "2025-05-01"


@pytest.mark.unit
class TestOpenBBCommandRunnerAndExecutionSafety:
    def test_command_runner_route_namespace_partitions_flat_kwargs(self) -> None:
        """Verify `_RouteNamespace` partitions flat kwargs into `provider_choices`, `standard_params`, and `extra_params`."""
        from dataclasses import dataclass

        from connectors.data_providers.openbb_adapter import _CommandRunnerOBBClient

        @dataclass
        class _FakeStandardParams:
            symbol: str
            start_date: str | None = None
            end_date: str | None = None

        def _fake_historical(
            provider_choices: Any,
            standard_params: _FakeStandardParams,
            extra_params: Any,
        ) -> Any:
            return None

        _fake_historical.__annotations__ = {
            "provider_choices": Any,
            "standard_params": _FakeStandardParams,
            "extra_params": Any,
            "return": Any,
        }

        recorded_calls: list[tuple[str, dict[str, Any]]] = []

        class _FakeRunner:
            def __init__(self) -> None:
                self.user_settings = SimpleNamespace(credentials=SimpleNamespace())
                self.command_map = SimpleNamespace(
                    get_command=lambda route: (
                        _fake_historical if route == "/equity/price/historical" else None
                    )
                )

            def sync_run(self, route: str, **kwargs: Any) -> Any:
                recorded_calls.append((route, kwargs))
                return SimpleNamespace(
                    results=[
                        {
                            "date": "2025-05-01",
                            "open": 200.0,
                            "high": 205.0,
                            "low": 199.0,
                            "close": 202.0,
                            "volume": 1000,
                        }
                    ]
                )

        client = _CommandRunnerOBBClient(_FakeRunner())
        res = client.equity.price.historical(
            symbol="AAPL",
            provider="yfinance",
            start_date="2025-04-15",
            end_date="2025-05-01",
            interval="1d",
        )
        assert len(res.results) == 1
        assert len(recorded_calls) == 1
        route, call_kwargs = recorded_calls[0]
        assert route == "/equity/price/historical"
        assert call_kwargs["provider_choices"] == {"provider": "yfinance"}
        assert call_kwargs["standard_params"] == {
            "symbol": "AAPL",
            "start_date": "2025-04-15",
            "end_date": "2025-05-01",
        }
        assert call_kwargs["extra_params"] == {"interval": "1d"}

    @pytest.mark.asyncio
    async def test_empty_data_error_maps_to_validation_error(self) -> None:
        """OpenBB `EmptyDataError` (e.g. invalid ticker on yfinance) maps to `OpenBBDataValidationError`."""

        class EmptyDataError(Exception):
            pass

        fake_obb = _make_fake_obb(raise_exc=EmptyDataError("No results found for ZZZ_INVALID"))
        adapter = OpenBBAdapter(obb_client=fake_obb)
        with pytest.raises(OpenBBDataValidationError, match="0 historical records"):
            await adapter.fetch_historical_ohlcv("ZZZ_INVALID")

    @pytest.mark.asyncio
    async def test_equity_quote_handles_zero_bid_ask_outside_market_hours(self) -> None:
        """When yfinance returns bid=0.0/ask=0.0 outside market hours, quote falls back to synthetic spread."""
        fake_obb = _make_fake_obb(
            quote_rows=[
                {
                    "last_price": 205.35,
                    "open": 206.00,
                    "high": 207.00,
                    "low": 202.16,
                    "prev_close": 213.32,
                    "bid": 0.0,
                    "ask": 0.0,
                    "volume": 101010600,
                    "last_timestamp": "2025-05-02T20:00:00Z",
                }
            ]
        )
        adapter = OpenBBAdapter(obb_client=fake_obb)
        q = await adapter.fetch_quote("AAPL", asset_class=ProviderAssetClass.EQUITY, provider="yfinance")
        assert q.symbol == "AAPL"
        assert q.price == 205.35
        assert q.bid > 0
        assert q.ask >= q.bid

    def test_openbb_modules_cannot_bypass_execution_or_risk_gates(self) -> None:
        """Verify `openbb_adapter` and `openbb_ingestion` have no imports or references to order/execution topics."""
        import ast
        from pathlib import Path

        forbidden_topics = {
            "PROPOSALS_BUS",
            "PROPOSALS_APPROVED",
            "ORDERS_PENDING",
            "ORDERS_APPROVED",
            "ORDERS_EXECUTED",
            "FILLS_CONFIRMED",
        }
        forbidden_modules = {
            "agents.tier1_executive",
            "agents.tier5_execution",
            "connectors.exchanges",
        }

        for rel_path in (
            "src/connectors/data_providers/openbb_adapter.py",
            "src/connectors/data_providers/openbb_ingestion.py",
        ):
            source = Path(rel_path).read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel_path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in forbidden_topics:
                    pytest.fail(f"{rel_path} references forbidden execution topic {node.attr}")
                if isinstance(node, ast.ImportFrom) and node.module:
                    for mod in forbidden_modules:
                        if node.module.startswith(mod):
                            pytest.fail(f"{rel_path} imports forbidden module {node.module}")
