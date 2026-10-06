"""Production state contracts with mocked network I/O; real Redis in accounting tests."""

from datetime import UTC, datetime, timedelta
from importlib import import_module
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest
from pydantic import ValidationError

from core.config import settings
from core.data.models import AgentStatus
from core.orchestrator.state_manager import StateManager
from tests.factories import health, portfolio, risk

module = import_module("core.orchestrator.state_manager")
pytestmark = pytest.mark.integration


@pytest.fixture
def state():
    sm = StateManager()
    sm._redis = AsyncMock()
    return sm


async def test_initialize_and_shutdown_release_connections(monkeypatch):
    pool = MagicMock(disconnect=AsyncMock())
    client = AsyncMock()
    monkeypatch.setattr(module.ConnectionPool, "from_url", MagicMock(return_value=pool))
    monkeypatch.setattr(module, "Redis", MagicMock(return_value=client))
    sm = StateManager()
    with pytest.raises(RuntimeError):
        _ = sm.redis
    await sm.initialize()
    client.ping.assert_awaited_once()
    assert module.ConnectionPool.from_url.call_args.kwargs["decode_responses"] is False
    await sm.shutdown()
    client.aclose.assert_awaited_once()
    pool.disconnect.assert_awaited_once()
    await StateManager().shutdown()


async def test_health_roundtrip_expiry_and_missing_records(state):
    item = health()
    await state.set_agent_health(item, ttl_seconds=90)
    args = state.redis.setex.await_args.args
    assert args[:2] == ("alghrest:agent:health:14", 90)
    state.redis.get.return_value = args[2]
    assert await state.get_agent_health(14) == item
    state.redis.keys.return_value = ["first", "expired"]
    state.redis.mget.return_value = [args[2], None]
    assert await state.get_all_agent_healths() == [item]
    state.redis.keys.return_value = []
    assert await state.get_all_agent_healths() == []
    state.redis.get.return_value = None
    assert await state.get_agent_health(14) is None
    await state.set_agent_status(14, AgentStatus.PAUSED)
    state.redis.set.assert_awaited_with("alghrest:agent:status:14", "PAUSED", ex=120)


@pytest.mark.parametrize(
    "factory,setter,getter,ttl",
    [
        (portfolio, "set_portfolio", "get_portfolio", 300),
        (risk, "set_risk_metrics", "get_risk_metrics", 120),
    ],
)
async def test_domain_snapshots_roundtrip_and_reject_corruption(
    state, factory, setter, getter, ttl
):
    item = factory()
    await getattr(state, setter)(item)
    call = state.redis.set.await_args
    assert call.kwargs["ex"] == ttl
    state.redis.get.return_value = call.args[1]
    assert await getattr(state, getter)() == item
    state.redis.get.return_value = None
    assert await getattr(state, getter)() is None
    state.redis.get.return_value = b"{}"
    with pytest.raises(ValidationError):
        await getattr(state, getter)()
    state.redis.get.return_value = b"invalid-json"
    with pytest.raises(orjson.JSONDecodeError):
        await getattr(state, getter)()


async def test_kill_switch_reason_and_atomic_dedup(state):
    await state.activate_kill_switch("drawdown", ttl_seconds=100)
    state.redis.setex.assert_awaited_with("alghrest:kill_switch:active", 100, b"drawdown")
    state.redis.exists.return_value = 1
    assert await state.is_kill_switch_active()
    state.redis.get.return_value = b"drawdown"
    assert await state.get_kill_switch_reason() == "drawdown"
    await state.deactivate_kill_switch()
    state.redis.delete.assert_awaited_with("alghrest:kill_switch:active")
    state.redis.exists.return_value = 0
    state.redis.get.return_value = None
    assert not await state.is_kill_switch_active()
    assert await state.get_kill_switch_reason() is None
    state.redis.set.side_effect = [True, None]
    assert not await state.is_already_processed("fill:1", 60)
    assert await state.is_already_processed("fill:1", 60)
    state.redis.set.assert_awaited_with("alghrest:dedup:fill:1", b"1", ex=60, nx=True)


@pytest.mark.parametrize("acquired,release_error", [(True, False), (True, True), (False, False)])
async def test_lock_releases_on_failure_and_fails_if_contended(state, acquired, release_error):
    lock = AsyncMock()
    lock.acquire.return_value = acquired
    if release_error:
        lock.release.side_effect = RuntimeError("lease expired")
    state.redis.lock = MagicMock(return_value=lock)
    if not acquired:
        with pytest.raises(TimeoutError):
            async with state.lock("orders", timeout=1):
                pytest.fail("lock was not acquired")
        lock.release.assert_not_awaited()
    else:
        with pytest.raises(ValueError, match="handler"):
            async with state.lock("orders", timeout=1) as held:
                assert held is lock
                raise ValueError("handler")
        lock.release.assert_awaited_once()


async def test_signals_json_and_pubsub_preserve_payloads(state):
    value = {"price": "1.00000000000001", "enabled": True}
    await state.cache_signal("BTC", "technical", value, ttl=5)
    state.redis.setex.assert_awaited_with(
        "alghrest:signal:latest:BTC:technical", 5, orjson.dumps(value)
    )
    state.redis.get.return_value = orjson.dumps(value)
    assert await state.get_cached_signal("BTC", "technical") == value
    assert await state.get_json("key") == value
    state.redis.get.return_value = None
    assert await state.get_cached_signal("BTC", "technical") is None
    assert await state.get_json("key") is None
    await state.set_json("key", value)
    state.redis.set.assert_awaited_with("key", orjson.dumps(value))
    await state.set_json("key", value, ttl=3)
    state.redis.setex.assert_awaited_with("key", 3, orjson.dumps(value))
    await state.publish("events", value)
    state.redis.publish.assert_awaited_with("events", orjson.dumps(value))
    await state.set_reconciliation({"book_id": "test", "ready": False})
    assert state.redis.setex.await_args.args[:2] == ("alghrest:reconciliation:test", 30)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "book",
        "stale",
        "future",
        "report_missing",
        "not_ready",
        "revision",
        "report_book",
        "report_stale",
        "report_future",
        "report_date",
        "report_key",
        "valid",
    ],
)
async def test_trading_gate_requires_matching_fresh_evidence(state, fault):
    now = datetime.now(UTC)
    snapshot = portfolio(accounting_book_id=settings.accounting_book_id, accounting_revision=3)
    from tests.factories import with_performance

    snapshot = with_performance(snapshot)
    report = dict(
        book_id=settings.accounting_book_id, ready=True, revision=3, checked_at=now.isoformat()
    )
    if fault == "missing":
        snapshot = None
    if fault == "book":
        snapshot.accounting_book_id = "foreign"
    if fault == "stale":
        snapshot.snapshot_time = now - timedelta(seconds=30)
    if fault == "future":
        snapshot.snapshot_time = now + timedelta(seconds=30)
    if fault == "report_missing":
        report = None
    if fault == "not_ready":
        report["ready"] = False
    if fault == "revision":
        report["revision"] = 2
    if fault == "report_book":
        report["book_id"] = "foreign"
    if fault == "report_stale":
        report["checked_at"] = (now - timedelta(days=1)).isoformat()
    if fault == "report_future":
        report["checked_at"] = (now + timedelta(days=1)).isoformat()
    if fault == "report_date":
        report["checked_at"] = "invalid"
    if fault == "report_key":
        del report["checked_at"]
    state.get_portfolio = AsyncMock(return_value=snapshot)
    state.get_json = AsyncMock(return_value=report)
    assert await state.trading_ready() is (fault == "valid")
