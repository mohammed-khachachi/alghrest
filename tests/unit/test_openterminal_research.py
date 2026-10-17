"""Synthetic source/indicator and authenticated read-only integration regressions."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from api.advisor import app
from api.routes import openterminal_context as route
from connectors.advisory import openterminal as shared, openterminal_research as adapter
from core.advisory.openterminal_research import TerminalResearch, analyze_candles
from core.config import settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def bars(count=60, reverse=False):
    values = [
        {
            "time": int((NOW - timedelta(days=count - i)).timestamp()),
            "open": i + 1,
            "high": i + 2,
            "low": max(0.5, i),
            "close": i + 1,
            "volume": 10,
        }
        for i in range(count)
    ]
    return list(reversed(values)) if reverse else values


def quote(symbol="AAPL", **updates):
    return [
        {
            "symbol": symbol,
            "price": "100.10",
            "changePercent": "0.5",
            "currency": "USD",
            "source": "nasdaq",
            "time": None,
            **updates,
        }
    ]


@pytest.fixture(autouse=True)
def clocks(monkeypatch):
    monkeypatch.setattr(adapter, "utcnow", lambda: NOW)
    monkeypatch.setattr(shared, "utcnow", lambda: NOW)


async def collect(symbol="AAPL", history=None, quotes=None, history_status=200):
    requests = []

    def transport(request):
        requests.append(request)
        if "/history/" in request.url.path:
            return httpx.Response(history_status, json=bars() if history is None else history)
        return httpx.Response(
            200,
            json=(
                (quote(symbol) if quotes is None else quotes)
                if request.url.path.endswith("quotes")
                else []
            ),
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        result = await adapter.collect_terminal_research(client, symbol)
    return result, requests


async def test_selected_terminal_symbol_is_the_analysis_instrument_without_futures_substitution():
    result, requests = await collect()
    assert result.symbol == "AAPL" and result.quote.symbol == "AAPL"
    assert result.quote.price == Decimal("100.10")
    assert len(requests) == 3
    assert {r.url.path for r in requests} == {"/api/quotes", "/api/news", "/api/history/AAPL"}
    assert all(
        r.url.host == "127.0.0.1"
        and r.url.port == 4001
        and r.method == "GET"
        and "authorization" not in r.headers
        for r in requests
    )
    assert requests[2].url.params["range"] == "6M"
    assert (
        result.analysis.history_provider == "UNKNOWN" and result.analysis.interval == "UNVERIFIED"
    )
    assert result.freshness == result.event_risk == "UNKNOWN"
    assert not result.trade_permitted and not result.execution_enabled


def test_indicator_arithmetic_uses_actual_bar_counts_not_assumed_futures_or_daily_data():
    analysis = analyze_candles(adapter.parse_candles(bars(), NOW), NOW)
    assert analysis.sma20 == Decimal("50.5") and analysis.sma50 == Decimal("35.5")
    assert analysis.rsi14_simple == 100 and analysis.atr14_simple == 2
    assert analysis.recent20_low == 40 and analysis.recent20_high == 61
    assert analysis.last_close == 60 and analysis.trend == "above_averages"


def test_flat_series_has_neutral_rsi_and_zero_range():
    values = [{**b, "open": 10, "high": 10, "low": 10, "close": 10} for b in bars()]
    analysis = analyze_candles(adapter.parse_candles(values, NOW), NOW)
    assert analysis.rsi14_simple == 50 and analysis.atr14_simple == 0
    assert analysis.trend == "mixed"


def test_downtrend_rsi_is_zero_and_missing_samples_remain_missing():
    values = [
        {**b, "open": 100 - i, "close": 100 - i, "high": 101 - i, "low": 99 - i}
        for i, b in enumerate(bars())
    ]
    analysis = analyze_candles(adapter.parse_candles(values, NOW), NOW)
    assert analysis.rsi14_simple == 0 and analysis.trend == "below_averages"
    short = analyze_candles(adapter.parse_candles(bars(10), NOW), NOW)
    assert short.sma20 is short.sma50 is short.rsi14_simple is short.atr14_simple is None
    assert short.recent20_low is None and short.trend == "insufficient"


@pytest.mark.parametrize(
    "bad",
    [
        [],
        bars(reverse=True),
        [bars()[0], bars()[0]],
        [{**bars()[0], "high": 0}],
        [{**bars()[0], "volume": None}],
        [{**bars()[0], "close": "NaN"}],
        [{**bars()[0], "time": int((NOW + timedelta(days=1)).timestamp())}],
    ],
)
async def test_invalid_history_does_not_generate_indicators_or_hide_valid_quote(bad):
    result, _ = await collect(history=bad)
    assert result.analysis is None and result.quote is not None
    assert next(s for s in result.sources if s.kind == "history").state == "invalid"


async def test_unavailable_history_keeps_quote_available_without_fake_candles():
    result, _ = await collect(history_status=502)
    assert result.analysis is None and result.quote is not None
    assert next(s for s in result.sources if s.kind == "history").state == "unavailable"


async def test_non_usd_currency_and_crypto_declared_provider_are_preserved():
    result, _ = await collect(
        "0700.HK", quotes=quote("0700.HK", currency="HKD", source="yahoo-chart")
    )
    assert result.quote.currency == "HKD"
    result, _ = await collect("VOD.L", quotes=quote("VOD.L", currency="GBp", source="yahoo"))
    assert result.quote.currency == "GBp"
    result, _ = await collect("BTC-USD", quotes=quote("BTC-USD", source="binance"))
    assert result.quote.symbol == "BTC-USD" and result.quote.provider == "binance"


async def test_wrong_quote_identity_is_rejected_while_history_remains_available():
    result, _ = await collect(quotes=quote("SPY"))
    assert result.quote is None and result.analysis is not None


@pytest.mark.parametrize(
    "symbol", ["..", "", "AAPL,SPY", "../AAPL", "https://example.org", "A" * 21]
)
async def test_arbitrary_urls_path_traversal_or_multi_symbol_requests_are_refused(symbol):
    with pytest.raises(ValueError):
        await collect(symbol)


async def test_symbol_special_characters_are_encoded_without_changing_identity():
    result, requests = await collect("M&M.NS")
    assert result.symbol == "M&M.NS"
    assert requests[0].url.params["symbols"] == "M&M.NS"
    assert requests[2].url.path == "/api/history/M&M.NS"
    assert str(requests[2].url).endswith("M%26M.NS?range=6M&metadata=1")


async def test_content_hashes_and_permission_flags_are_validated():
    result, _ = await collect()
    assert all(s.response_sha256 and len(s.response_sha256) == 64 for s in result.sources)
    for key in ("trade_permitted", "execution_enabled"):
        with pytest.raises(ValidationError):
            TerminalResearch.model_validate({**result.model_dump(), key: True})


async def test_request_deadline_returns_explicitly_unavailable_sources(monkeypatch):
    async def timed_out(*args, **kwargs):
        raise TimeoutError

    monkeypatch.setattr(adapter, "_read", timed_out)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200))
    ) as client:
        result = await adapter.collect_terminal_research(client, "AAPL")
    assert result.quote is result.analysis is None and not result.headlines
    assert all(s.state == "unavailable" for s in result.sources)
    assert not result.trade_permitted and not result.execution_enabled


async def test_new_research_endpoint_is_authenticated_and_only_reads(monkeypatch):
    result, _ = await collect()
    monkeypatch.setattr(
        settings, "advisory_access_token", SecretStr("synthetic_research_" + "x" * 32)
    )
    mocked = AsyncMock(return_value=result)
    monkeypatch.setattr(route, "collect_terminal_research", mocked)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/assistant-api/openterminal-research/AAPL")
        assert response.status_code == 401
        assert not mocked.called
        headers = {"Authorization": "Bearer synthetic_research_" + "x" * 32}
        response = await client.get("/assistant-api/openterminal-research/AAPL", headers=headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["symbol"] == "AAPL"
        response = await client.get(
            "/assistant-api/openterminal-research/AAPL,SPY", headers=headers
        )
        assert response.status_code == 422
        response = await client.post(
            "/assistant-api/openterminal-research/AAPL",
            headers={**headers, "X-Advisory-Client": "dashboard"},
        )
        assert response.status_code == 405


def history_envelope(**updates):
    return {
        "candles": bars(),
        "metadata": {
            "schema_version": "openterminal-history-v1",
            "symbol": "AAPL",
            "requested_range": "6M",
            "provider": "yahoo",
            "interval": "1d",
            "interval_basis": "provider_request",
            "fetched_at": (NOW - timedelta(minutes=20)).isoformat(),
            "cache_state": "stale",
            **updates,
        },
    }


@pytest.mark.parametrize("state", ["fetched", "cached", "stale"])
async def test_history_metadata_preserves_provider_timeframe_and_original_fetch_time(state):
    result, requests = await collect(history=history_envelope(cache_state=state))
    a = result.analysis
    assert a.history_provider == "yahoo" and a.interval == "1d"
    assert a.interval_basis == "provider_request" and a.history_cache_state == state
    assert a.history_fetched_at == NOW - timedelta(minutes=20)
    assert a.last_time == NOW - timedelta(days=1)
    assert next(s for s in result.sources if s.kind == "history").received_at == NOW
    assert requests[2].url.params["metadata"] == "1"
    assert result.freshness == "UNKNOWN" and not result.trade_permitted


async def test_nasdaq_history_provider_is_known_without_inventing_timeframe():
    result, _ = await collect(
        history=history_envelope(provider="nasdaq", interval=None, interval_basis="UNVERIFIED")
    )
    assert result.analysis.history_provider == "nasdaq"
    assert result.analysis.interval == result.analysis.interval_basis == "UNVERIFIED"


@pytest.mark.parametrize(
    "updates",
    [
        {"symbol": "SPY"},
        {"requested_range": "1Y"},
        {"provider": "invented"},
        {"interval": "2s"},
        {"cache_state": "live"},
        {"interval": None},
        {"interval_basis": "UNVERIFIED"},
        {"fetched_at": (NOW + timedelta(seconds=1)).isoformat()},
        {"fetched_at": (NOW - timedelta(days=2)).isoformat()},
    ],
)
async def test_bad_history_metadata_is_rejected_without_losing_other_feeds(updates):
    result, _ = await collect(history=history_envelope(**updates))
    assert result.analysis is None and result.quote is not None
    assert next(s for s in result.sources if s.kind == "history").state == "invalid"
