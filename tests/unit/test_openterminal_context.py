"""Synthetic integration mechanics; public ETF context cannot authorize futures."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from api.advisor import app
from api.routes import openterminal_context as route
from connectors.advisory import openterminal as adapter
from core.advisory.openterminal_context import OpenTerminalContext, build_terminal_context
from core.config import settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)


def quote(symbol="QQQ", **changes):
    return [
        {
            "symbol": symbol,
            "name": "Synthetic proxy",
            "price": "100.10",
            "changePercent": "0.5",
            "currency": "USD",
            "source": "nasdaq",
            "time": None,
            **changes,
        }
    ]


def headlines(**changes):
    return [
        {
            "title": "<b>Synthetic</b> index news",
            "link": "https://example.org/article",
            "publisher": "Fixture",
            "publishedAt": NOW.isoformat(),
            "symbol": "QQQ",
            **changes,
        }
    ]


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr(adapter, "utcnow", lambda: NOW)


async def collect(instrument="MNQ", quote_body=None, news_body=None, status=200):
    def transport(request):
        body = (
            (quote() if quote_body is None else quote_body)
            if request.url.path.endswith("quotes")
            else (headlines() if news_body is None else news_body)
        )
        return httpx.Response(status, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        return await adapter.collect_terminal_context(client, instrument)


async def test_public_context_is_consumed_without_becoming_a_futures_quote():
    context = await collect()
    assert context.quote.price == Decimal("100.10")
    assert context.proxy_symbol == "QQQ" and context.instrument_id == "MNQ"
    assert context.direction == "proxy_up"
    assert context.headlines[0].title == "Synthetic index news"
    assert context.quote.market_time is None and context.freshness == "UNKNOWN"
    assert context.event_risk == "UNKNOWN"
    assert not context.quote_usable_for_risk and not context.trade_permitted
    assert not context.execution_enabled
    assert all(len(row.response_sha256) == 64 for row in context.sources)


async def test_mes_uses_spy_and_never_requests_a_broker_or_arbitrary_url():
    requests = []

    def transport(request):
        requests.append(request)
        return httpx.Response(200, json=quote("SPY") if request.url.path.endswith("quotes") else [])

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        context = await adapter.collect_terminal_context(client, "MES")
    assert context.quote.symbol == "SPY"
    assert len(requests) == 2
    assert all(str(row.url).startswith("http://127.0.0.1:4001/api/") for row in requests)
    assert {row.url.path for row in requests} == {"/api/quotes", "/api/news"}
    assert all(row.method == "GET" and "authorization" not in row.headers for row in requests)


@pytest.mark.parametrize(
    "change",
    [
        {"symbol": "MNQZ26"},
        {"symbol": "SPY"},
        {"currency": "EUR"},
        {"price": 0},
        {"price": -1},
        {"price": True},
        {"price": "NaN"},
        {"price": "Infinity"},
        {"price": "1e31"},
        {"source": "invented"},
        {"time": (NOW + timedelta(seconds=1)).timestamp()},
        {"time": "2026-10-14T12:00:00"},
    ],
)
async def test_invalid_quote_cannot_supply_positive_context(change):
    context = await collect(quote_body=quote(**change))
    assert context.quote is None and context.direction == "unknown"
    assert context.sources[0].state == "invalid"
    assert not context.quote_usable_for_risk and not context.trade_permitted


@pytest.mark.parametrize(
    "changes",
    [
        {"link": "javascript:alert(1)"},
        {"link": "https://user:password@example.org/a"},
        {"link": "https://127.0.0.1/a"},
        {"link": "https://localhost/a"},
        {"publishedAt": (NOW + timedelta(seconds=1)).isoformat()},
        {"publishedAt": (NOW - timedelta(days=8)).isoformat()},
        {"symbol": "AAPL"},
    ],
)
async def test_unsafe_future_old_or_unrelated_headlines_are_not_shared(changes):
    context = await collect(news_body=headlines(**changes))
    assert not context.headlines and context.event_risk == "UNKNOWN"


async def test_empty_news_does_not_clear_events_and_duplicates_are_collapsed():
    assert (await collect(news_body=[])).event_risk == "UNKNOWN"
    assert len((await collect(news_body=headlines() * 2)).headlines) == 1


@pytest.mark.parametrize("status", [302, 401, 429, 500])
async def test_failed_or_redirected_sources_remain_unknown(status):
    context = await collect(status=status)
    assert context.quote is None and not context.headlines
    assert all(row.state == "unavailable" for row in context.sources)
    assert context.freshness == "UNKNOWN" and not context.execution_enabled


async def test_invalid_json_and_oversized_response_are_bounded():
    for body in [b"not json", b"x" * (adapter.MAX_BODY_BYTES + 1)]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, body=body: httpx.Response(200, content=body))
        ) as client:
            context = await adapter.collect_terminal_context(client, "MNQ")
        assert all(row.state == "invalid" for row in context.sources)


async def test_envelope_rejects_identity_changes_and_execution_flags():
    context = await collect()
    data = context.model_dump()
    for changes in [
        {"proxy_symbol": "SPY"},
        {"execution_enabled": True},
        {"trade_permitted": True},
        {"quote_usable_for_risk": True},
    ]:
        with pytest.raises(ValidationError):
            OpenTerminalContext.model_validate(data | changes)
    with pytest.raises(ValueError):
        build_terminal_context("MES", context.quote, (), (), now=NOW)


async def test_endpoint_retains_existing_authentication_and_no_store(monkeypatch):
    value = await collect()
    reader = AsyncMock(return_value=value)
    monkeypatch.setattr(route, "collect_terminal_context", reader)
    monkeypatch.setattr(
        settings, "advisory_access_token", SecretStr("synthetic_context_token_" + "x" * 32)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        denied = await client.get("/assistant-api/openterminal-context/MNQ")
        assert denied.status_code == 401 and reader.await_count == 0
        accepted = await client.get(
            "/assistant-api/openterminal-context/MNQ",
            headers={"Authorization": "Bearer synthetic_context_token_" + "x" * 32},
        )
        assert accepted.status_code == 200
        assert accepted.headers["cache-control"] == "no-store"
        assert accepted.json()["execution_enabled"] is False
        bad = await client.get(
            "/assistant-api/openterminal-context/AAPL",
            headers={"Authorization": "Bearer synthetic_context_token_" + "x" * 32},
        )
        assert bad.status_code == 422
