"""Dated source declarations, cache failure and display-window boundaries."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from connectors.advisory import openterminal as shared, openterminal_research as adapter
from core.advisory.openterminal_context import TerminalSource
from core.advisory.openterminal_research import QuoteObservation, ResearchQuote, TerminalResearch
from core.advisory.research_freshness import quote_freshness

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def report(
    state="Closed", *, age=1200, fetched_age=1, cache="fetched", provider="nasdaq", basis="provider"
):
    return TerminalResearch(
        symbol="AAPL",
        assessed_at=NOW,
        quote=ResearchQuote(
            symbol="AAPL",
            price=Decimal(100),
            currency="USD",
            provider=provider,
            market_time=NOW - timedelta(seconds=age) if age is not None else None,
            market_state=state,
            observation=QuoteObservation(
                schema_version="quote-observation-v1",
                fetched_at=NOW - timedelta(seconds=fetched_age),
                cache_state=cache,
                market_state_basis=basis,
            ),
        ),
        sources=tuple(
            TerminalSource(
                kind=kind,
                state="available" if kind == "quotes" else "unavailable",
                received_at=NOW,
                response_sha256="a" * 64 if kind == "quotes" else None,
            )
            for kind in ("quotes", "history", "news")
        ),
    )


@pytest.mark.parametrize(
    "state,status,session",
    [
        ("Open", "old_while_open_reported", "open"),
        ("REGULAR", "old_while_open_reported", "open"),
        ("Closed", "closed_reported", "closed"),
        ("CLOSED", "closed_reported", "closed"),
        ("PRE", "old_observation", "pre"),
        ("After-Hours", "old_observation", "post"),
        ("unexpected", "old_observation", "unknown"),
    ],
)
def test_provider_state_is_reported_without_inventing_a_calendar(state, status, session):
    r = report(state)
    context = quote_freshness(r)
    assert context["status"] == status and context["session"] == session
    assert r.freshness == "UNKNOWN" and not r.execution_enabled


def test_unknown_price_clock_cannot_become_fresh_because_the_source_was_just_fetched():
    context = quote_freshness(report(age=None))
    assert context["status"] == "unknown" and "وقت السعر غير معلن" in context["message"]
    assert "مغلقة" in context["session_note"]


def test_stale_cache_and_old_session_declarations_cannot_describe_current_session():
    assert quote_freshness(report(cache="stale"))["status"] == "stale_cache"
    for age in (90, 91, 3600):
        context = quote_freshness(report(fetched_age=age, age=7200))
        assert context["status"] == "old_observation"
        assert "لا يصف حالة السوق الآن" in context["session_note"]
    assert quote_freshness(report(fetched_age=89))["status"] == "closed_reported"


def test_display_threshold_does_not_certify_realtime_or_source_latency():
    context = quote_freshness(report(age=900))
    assert (
        context["status"] == "within_display_window" and "لا يثبت أنه مباشر" in context["message"]
    )
    assert quote_freshness(report(age=901))["status"] == "closed_reported"


def test_adapter_assumption_and_legacy_snapshots_cannot_become_provider_reports():
    context = quote_freshness(report("Open", provider="binance", basis="UNVERIFIED"))
    assert context["session"] == "unknown" and context["status"] == "old_observation"
    with pytest.raises(ValidationError):
        report("Open", provider="binance")
    old = report().model_dump(mode="json")
    old["quote"].pop("observation")
    old["quote"].pop("market_state")
    restored = TerminalResearch.model_validate(old)
    assert quote_freshness(restored)["session"] == "unknown"


async def test_adapter_preserves_quote_observation_and_rejects_future_fetch_clock_independently(
    monkeypatch,
):
    monkeypatch.setattr(adapter, "utcnow", lambda: NOW)
    monkeypatch.setattr(shared, "utcnow", lambda: NOW)
    data = {
        "symbol": "AAPL",
        "price": 100,
        "currency": "USD",
        "source": "nasdaq",
        "marketState": "Closed",
        "observation": {
            "schema_version": "quote-observation-v1",
            "fetched_at": NOW.isoformat(),
            "cache_state": "cached",
            "market_state_basis": "provider",
        },
    }
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=[data] if request.url.path.endswith("quotes") else [])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        r = await adapter.collect_terminal_research(client, "AAPL")
        assert r.quote.observation.cache_state == "cached" and r.quote.market_state == "Closed"
        assert requests[0].url.params["metadata"] == "1"
        data["observation"]["fetched_at"] = (NOW + timedelta(seconds=1)).isoformat()
        invalid = await adapter.collect_terminal_research(client, "AAPL")
    assert (
        invalid.quote is None
        and next(s for s in invalid.sources if s.kind == "quotes").state == "invalid"
    )
