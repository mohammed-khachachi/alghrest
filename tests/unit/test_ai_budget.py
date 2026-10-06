"""Bounded paid calls, fail-closed reservations and stable-input decision controls."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agents.tier1_executive.cio_agent import CIOAgent
from agents.tier2_intelligence.news_analyst import NewsAnalyst
from core.ai.budget import BudgetUnavailableError, estimate_cost, reserve
from core.config import settings

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("model", ["claude-opus-4-7", "claude-sonnet-4-6"])
def test_conservative_reservation_and_input_limits(monkeypatch, model):
    assert estimate_cost(model, "system", "مرحبا", 512) > 0
    with pytest.raises(BudgetUnavailableError):
        estimate_cost("unknown", "system", "user", 512)
    monkeypatch.setattr(settings, "ai_max_prompt_bytes", 1024)
    with pytest.raises(BudgetUnavailableError):
        estimate_cost(model, "s" * 1025, "u", 512)


async def test_budget_unavailable_never_calls_paid_api(monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_budget_usd", Decimal(0))
    for agent, method, args in (
        (CIOAgent(), "_ask_claude", ("data",)),
        (NewsAnalyst(), "_classify_with_claude", ("BTC news", "data")),
    ):
        agent._claude = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock()))
        try:
            assert await getattr(agent, method)(*args) is None
        except BudgetUnavailableError:
            assert isinstance(agent, NewsAnalyst)
        agent._claude.messages.create.assert_not_awaited()


async def test_driver_failure_is_redacted_and_fail_closed(monkeypatch):
    monkeypatch.setattr("core.ai.budget.asyncpg.connect", AsyncMock(side_effect=OSError("secret")))
    with pytest.raises(BudgetUnavailableError, match="Durable AI budget unavailable") as exc:
        await reserve("claude-opus-4-7", "s", "u", 512)
    assert "secret" not in str(exc.value)


async def test_rejected_atomic_reservation_still_closes_connection(monkeypatch):
    connection = AsyncMock()
    connection.fetchval.return_value = None
    monkeypatch.setattr("core.ai.budget.asyncpg.connect", AsyncMock(return_value=connection))
    with pytest.raises(BudgetUnavailableError, match="exhausted"):
        await reserve("claude-opus-4-7", "s", "u", 512)
    connection.close.assert_awaited_once()


async def test_unchanged_context_skips_call_but_changed_and_expired_inputs_do_not(monkeypatch):
    agent = CIOAgent()
    agent.state = AsyncMock()
    agent.state.get_portfolio.return_value = None
    agent.state.get_risk_metrics.return_value = None
    agent._signal_cache = [
        {"ts": datetime.utcnow().isoformat(), "topic": "news", "payload": {"direction": "BULLISH"}}
    ]
    agent._ask_claude = AsyncMock(return_value=dict(agent._current_weights))
    await agent._make_decision()
    await agent._make_decision()
    assert agent._ask_claude.await_count == 1
    agent._signal_cache[0]["payload"]["direction"] = "BEARISH"
    await agent._make_decision()
    assert agent._ask_claude.await_count == 2
    agent._last_decision_at -= timedelta(seconds=settings.ai_decision_refresh_seconds)
    await agent._make_decision()
    assert agent._ask_claude.await_count == 3
    agent._signal_cache[0]["ts"] = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    await agent._make_decision()
    assert agent._ask_claude.await_count == 3


@pytest.mark.parametrize(
    "response",
    [
        "[]",
        "{}",
        '{"unknown": 0.1}',
        '{"trend_follower_donchian": -0.1}',
        '{"trend_follower_donchian": NaN}',
        '{"trend_follower_donchian": true}',
        '{"trend_follower_donchian": 0.3}',
    ],
)
async def test_invalid_allocations_are_not_repaired_into_decisions(monkeypatch, response):
    monkeypatch.setattr("agents.tier1_executive.cio_agent.reserve", AsyncMock())
    agent = CIOAgent()
    agent._claude = SimpleNamespace(
        messages=SimpleNamespace(
            create=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(text=response)]))
        )
    )
    assert await agent._ask_claude("context") is None


async def test_timeout_has_one_reservation_one_request_and_keeps_weights(monkeypatch):
    reservation = AsyncMock()
    monkeypatch.setattr("agents.tier1_executive.cio_agent.reserve", reservation)
    monkeypatch.setattr(settings, "ai_request_timeout_seconds", 0.01)
    agent = CIOAgent()
    before = dict(agent._current_weights)

    async def slow(**kwargs):
        await asyncio.sleep(1)

    agent._claude = SimpleNamespace(messages=SimpleNamespace(create=AsyncMock(side_effect=slow)))
    assert await agent._ask_claude("context") is None
    assert agent._current_weights == before
    reservation.assert_awaited_once()
    agent._claude.messages.create.assert_awaited_once()
