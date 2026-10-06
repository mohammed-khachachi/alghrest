"""Exercise the production ASGI routes with isolated state and no live services."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from api import main
from connectors.data_providers.router import default_router
from core.config import settings
from tests.factories import health, portfolio, position, risk

pytestmark = pytest.mark.integration


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setattr(settings, "api_access_token", SecretStr("a" * 48))
    state = AsyncMock()
    state.is_kill_switch_active.return_value = False
    state.get_portfolio.return_value = portfolio(positions=[position()])
    state.get_risk_metrics.return_value = risk()
    state.get_all_agent_healths.return_value = [health()]
    state.get_agent_health.return_value = health()
    state.get_cached_signal.return_value = None
    monkeypatch.setattr(main, "state_manager", state)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + "a" * 48},
    ) as client:
        yield client


async def test_health_readiness_and_dependency_failure(client):
    assert (await client.get("/health")).json()["status"] == "ok"
    assert (await client.get("/health/ready")).json() == {"ready": True}
    main.state_manager.is_kill_switch_active.return_value = True
    assert (await client.get("/health")).json()["status"] == "degraded"
    main.state_manager.redis.ping.side_effect = OSError("offline")
    assert (await client.get("/health/ready")).status_code == 503


async def test_portfolio_risk_and_agent_contracts(client):
    snapshot = (await client.get("/api/v1/portfolio")).json()
    assert snapshot["total_capital"] == "10000"
    positions = (await client.get("/api/v1/portfolio/positions")).json()
    assert positions["count"] == 1 and positions["total_exposure_usd"] == 105
    assert (await client.get("/api/v1/risk")).json()["daily_drawdown_pct"] == 0
    assert (await client.get("/api/v1/risk/kill-switch")).json() == {
        "active": False,
        "reason": None,
    }
    main.state_manager.is_kill_switch_active.return_value = True
    main.state_manager.get_kill_switch_reason.return_value = "manual test"
    assert (await client.get("/api/v1/risk/kill-switch")).json()["reason"] == "manual test"
    agents = (await client.get("/api/v1/agents")).json()
    assert agents["total"] == agents["running"] == 1 and agents["errors"] == 0
    assert (await client.get("/api/v1/agents/14")).json()["agent_id"] == 14
    main.state_manager.get_agent_health.return_value = None
    assert (await client.get("/api/v1/agents/999")).status_code == 404


async def test_missing_state_is_reported_without_invented_balances(client):
    main.state_manager.get_portfolio.return_value = None
    main.state_manager.get_risk_metrics.return_value = None
    assert "total_capital" not in (await client.get("/api/v1/portfolio")).json()
    assert (await client.get("/api/v1/portfolio/positions")).json() == {"positions": []}
    assert "message" in (await client.get("/api/v1/risk")).json()
    assert "message" in (await client.get("/api/v1/signals/sentiment/BTC")).json()
    assert "message" in (await client.get("/api/v1/signals/macro")).json()
    main.state_manager.get_cached_signal.return_value = {"direction": "BULLISH"}
    assert (await client.get("/api/v1/signals/sentiment/btc")).json()["direction"] == "BULLISH"
    main.state_manager.get_cached_signal.assert_awaited_with("BTC", "sentiment")
    assert (await client.get("/api/v1/signals/macro")).json() == {"direction": "BULLISH"}


async def test_cors_metrics_and_invalid_route(client):
    response = await client.options(
        "/api/v1/portfolio",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert (await client.get("/missing")).status_code == 404
    assert "text/plain" in (await client.get("/metrics")).headers["content-type"]


async def test_catalog_quotes_and_holdings_join_by_symbol(client):
    catalog = (await client.get("/api/symbols")).json()["symbols"]
    assert len(catalog) == 24
    assert {item["asset_class"] for item in catalog} == {"crypto", "forex", "equity"}
    quotes = (
        await client.get("/api/quotes", params={"symbols": " btc,EUR/USD,AAPL,unknown, "})
    ).json()["quotes"]
    assert [q["symbol"] for q in quotes] == ["BTC", "EUR/USD", "AAPL"]
    for quote in quotes:
        assert 0 < quote["bid"] <= quote["price"] <= quote["ask"]
        assert quote["low"] <= quote["open"] <= quote["high"]
    holdings = (await client.get("/api/holdings")).json()["holdings"]
    assert len(holdings) == 8
    assert all(h["entry_price"] > 0 and h["volume"] > 0 for h in holdings)
    assert (await client.get("/api/holdings")).json()["holdings"] == holdings


@pytest.mark.parametrize("symbol", ["btc", "EUR/USD", "AAPL"])
async def test_history_is_deterministic_ordered_and_valid(client, symbol):
    response = await client.get("/api/history", params={"symbol": symbol, "days": 30})
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == symbol.upper() and len(data["bars"]) == 30
    assert data == (await client.get("/api/history", params={"symbol": symbol, "days": 30})).json()
    assert [b["date"] for b in data["bars"]] == sorted(b["date"] for b in data["bars"])
    assert all(
        b["low"] <= min(b["close"], b["open"]) <= max(b["close"], b["open"]) <= b["high"]
        for b in data["bars"]
    )


@pytest.mark.parametrize(
    "symbol,days,status", [("unknown", 30, 404), ("BTC", 1, 422), ("BTC", 366, 422)]
)
async def test_history_rejects_unknown_symbols_and_invalid_windows(client, symbol, days, status):
    assert (
        await client.get("/api/history", params={"symbol": symbol, "days": days})
    ).status_code == status


async def test_provider_batch_interface():
    for provider in default_router._providers.values():
        symbol = next(
            entry.symbol
            for entry in default_router.catalog
            if entry.asset_class == provider.asset_class
        )
        assert len(await provider.quote_many([symbol, symbol])) == 2


async def test_websocket_broadcast_removes_failed_peers():
    manager = main.ConnectionManager()
    healthy, failed = AsyncMock(), AsyncMock()
    failed.send_json.side_effect = WebSocketDisconnect()
    await manager.connect(healthy)
    await manager.connect(failed)
    await manager.broadcast({"price": 100})
    healthy.send_json.assert_awaited_once_with({"price": 100})
    assert manager._connections == [healthy]
    manager.disconnect(healthy)
    assert not manager._connections


async def test_lifespan_cancels_and_awaits_background_tasks(monkeypatch):
    state = AsyncMock()
    bot = MagicMock(start=AsyncMock(), stop=AsyncMock())
    tasks = []

    async def start_loops():
        tasks.append(asyncio.create_task(asyncio.Event().wait()))
        return tasks

    monkeypatch.setattr(main, "state_manager", state)
    monkeypatch.setattr(main, "telegram_bot", bot)
    monkeypatch.setattr(main, "start_background_loops", start_loops)
    monkeypatch.setattr(main, "_KAFKA_AVAILABLE", False)
    async with main.lifespan(main.app):
        assert not tasks[0].done()
    assert all(task.done() for task in tasks)
    state.shutdown.assert_awaited_once()
    bot.stop.assert_awaited_once()
