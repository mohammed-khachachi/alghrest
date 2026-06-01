"""Unit tests for Phase 5 execution state-safety changes.

These cover the move of correctness-critical execution state out of process
memory and into Redis (via StateManager), so that the execution layer is:

  * restart-safe        — tracked open orders survive a process restart
  * duplicate-safe      — the same order is never placed twice
  * multi-replica-safe  — two executors sharing Redis cannot both place/cancel
                          the same order, and the router produces identical
                          identifiers for the same proposal on every replica
  * fail-closed         — if Redis is unavailable during placement, the order
                          is NOT silently placed twice

A small in-memory ``FakeState`` stands in for Redis so the tests need no real
Redis, exchange, or live trading.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import orjson
import pytest

from agents.tier5_execution.exchange_executor import _TRACKED_PATTERN, ExchangeExecutor
from agents.tier5_execution.order_router import OrderRouter
from core.data.models import (
    Exchange,
    KafkaTopic,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    TradeProposal,
    TradeProposalStatus,
)

# ── Fake Redis-backed StateManager ──────────────────────────────────────────


class FakeState:
    """Minimal in-memory stand-in for StateManager, shared across instances to
    simulate a single Redis seen by multiple executor/router replicas."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self._dedup: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}
        self.fail_lock = False  # flip on to simulate Redis being unavailable

    async def set_json(self, key, value, ttl=None) -> None:
        self.store[key] = orjson.dumps(value)

    async def get_json(self, key):
        raw = self.store.get(key)
        return orjson.loads(raw) if raw is not None else None

    async def set_json_nx(self, key, value, ttl=None) -> bool:
        if key in self.store:
            return False
        self.store[key] = orjson.dumps(value)
        return True

    async def delete_key(self, key) -> None:
        self.store.pop(key, None)

    async def scan_keys(self, pattern) -> list[str]:
        prefix = pattern.rstrip("*")
        return [k for k in self.store if k.startswith(prefix)]

    async def is_already_processed(self, key, ttl_seconds=3600) -> bool:
        if key in self._dedup:
            return True
        self._dedup.add(key)
        return False

    @asynccontextmanager
    async def lock(self, name, timeout=30.0):
        if self.fail_lock:
            raise ConnectionError("redis unavailable")
        lk = self._locks.setdefault(name, asyncio.Lock())
        acquired = await asyncio.wait_for(lk.acquire(), timeout)
        if not acquired:
            raise TimeoutError(name)
        try:
            yield lk
        finally:
            lk.release()


# ── Builders ────────────────────────────────────────────────────────────────


def _make_executor(state: FakeState, returned_order: Order | None = None):
    ex = ExchangeExecutor()
    ex.producer = MagicMock()
    ex.producer.send = AsyncMock()
    ex.publish = AsyncMock()
    ex.state = state

    fake_conn = MagicMock()

    async def _place(*args, **kwargs):
        return returned_order

    fake_conn.place_market_order = AsyncMock(side_effect=_place)
    fake_conn.place_limit_order = AsyncMock(side_effect=_place)
    fake_conn.fetch_trades = AsyncMock(return_value=[])
    fake_conn.cancel_order = AsyncMock(return_value=True)
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_conn)
    return ex, fake_conn


def _open_limit_order(ex_id: str = "EX-OPEN-1") -> Order:
    """The Order the connector returns after placing an OPEN limit order."""
    return Order(
        order_id=uuid4(),
        client_order_id=uuid4(),
        exchange_order_id=ex_id,
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.01"),
        price=Decimal("45000"),
        filled_size=Decimal("0"),
        status=OrderStatus.OPEN,
        strategy_id="test",
        agent_id=12,
    )


def _incoming_limit_order() -> Order:
    """The Order arriving on ORDERS_PENDING (pre-placement)."""
    return Order(
        order_id=uuid4(),
        client_order_id=uuid4(),
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.01"),
        price=Decimal("45000"),
        status=OrderStatus.PENDING,
        strategy_id="test",
        agent_id=12,
    )


def _make_router(state: FakeState):
    r = OrderRouter()
    r.publish = AsyncMock()
    r.state = state
    r._connector = MagicMock()
    # No tickers → router falls back to the default exchange (BINANCE).
    r._connector.fetch_all_tickers = AsyncMock(return_value={})
    return r


def _approved_proposal() -> TradeProposal:
    return TradeProposal(
        strategy_id="trend",
        agent_id=11,
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.01"),
        size_usd=Decimal("450"),
        limit_price=Decimal("45000"),
        status=TradeProposalStatus.APPROVED,
        created_at=datetime.utcnow(),
    )


def _published_order(router_publish_mock) -> dict:
    """Extract the Order payload dict from a router publish() call."""
    call = router_publish_mock.await_args
    # _route calls self.publish(topic, payload_dict, "Order") positionally.
    assert call.args[0] == KafkaTopic.ORDERS_PENDING
    return call.args[1]


# ── 1. Restart recovery ─────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_order_persisted_and_recovered_after_restart():
    state = FakeState()
    placed = _open_limit_order(ex_id="EX-OPEN-1")
    ex_a, _ = _make_executor(state, returned_order=placed)

    await ex_a._place_order(_incoming_limit_order())

    # Durable record exists in (shared) Redis.
    keys = await state.scan_keys(_TRACKED_PATTERN)
    assert keys == ["alghrest:exec:tracked:EX-OPEN-1"]

    # A brand-new executor instance (restart / second replica) recovers it.
    ex_b, _ = _make_executor(state, returned_order=placed)
    assert ex_b._tracked_orders == {}
    await ex_b._recover_tracked_orders()
    assert "EX-OPEN-1" in ex_b._tracked_orders
    recovered, _ts = ex_b._tracked_orders["EX-OPEN-1"]
    assert recovered.symbol == "BTC/USDT"
    assert recovered.status == OrderStatus.OPEN
    assert recovered.exchange == Exchange.BINANCE


# ── 2. Duplicate placement prevention ───────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_duplicate_placement_is_prevented():
    state = FakeState()
    placed = _open_limit_order(ex_id="EX-DUP")
    ex, conn = _make_executor(state, returned_order=placed)

    order = _incoming_limit_order()
    await ex._place_with_lock(order)
    await ex._place_with_lock(order)  # same client_order_id → must be skipped

    assert conn.place_limit_order.await_count == 1


# ── 3. Replica safety (shared Redis) ────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_two_replicas_cannot_place_same_order():
    state = FakeState()  # one shared "Redis"
    placed = _open_limit_order(ex_id="EX-REPLICA")
    ex_a, conn_a = _make_executor(state, returned_order=placed)
    ex_b, conn_b = _make_executor(state, returned_order=placed)

    order = _incoming_limit_order()
    # Both replicas race on the same client_order_id.
    await asyncio.gather(ex_a._place_with_lock(order), ex_b._place_with_lock(order))

    total = conn_a.place_limit_order.await_count + conn_b.place_limit_order.await_count
    assert total == 1


# ── 4. Fill polling resumes from recovered state ────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_polling_can_resume_after_recovery():
    state = FakeState()
    placed = _open_limit_order(ex_id="EX-POLL")
    ex_a, _ = _make_executor(state, returned_order=placed)
    await ex_a._place_order(_incoming_limit_order())

    # New instance recovers, then a terminal poll clears the order.
    ex_b, conn_b = _make_executor(state, returned_order=placed)
    await ex_b._recover_tracked_orders()
    recovered, _ = ex_b._tracked_orders["EX-POLL"]

    filled = recovered.model_copy(update={
        "status": OrderStatus.FILLED,
        "filled_size": Decimal("0.01"),
    })
    conn_b.fetch_order = AsyncMock(return_value=filled)

    await ex_b._poll_one("EX-POLL", recovered)

    # Terminal status → durable record and local cache both cleared.
    assert "EX-POLL" not in ex_b._tracked_orders
    assert await state.scan_keys(_TRACKED_PATTERN) == []


# ── 5. OrderRouter idempotency ──────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_same_proposal_yields_same_identifiers_across_replicas():
    state = FakeState()
    proposal = _approved_proposal()
    msg = proposal.model_dump(mode="json")

    r1 = _make_router(state)
    await r1._route(dict(msg))
    order1 = _published_order(r1.publish)

    # Different replica, same proposal redelivered.
    r2 = _make_router(state)
    await r2._route(dict(msg))
    order2 = _published_order(r2.publish)

    assert order1["client_order_id"] == order2["client_order_id"]
    assert order1["order_id"] == order2["order_id"]
    # Decision record persisted for audit / recovery.
    decision = await state.get_json(
        f"routing:order:{proposal.proposal_id}:decision"
    )
    assert decision is not None
    assert decision["exchange"] == order1["exchange"]


# ── 6. Cache safety (local cache is not the source of truth) ────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clearing_executor_cache_does_not_lose_tracking():
    state = FakeState()
    placed = _open_limit_order(ex_id="EX-CACHE")
    ex, _ = _make_executor(state, returned_order=placed)
    await ex._place_order(_incoming_limit_order())

    # Simulate cache loss (restart) by wiping the local mirror only.
    ex._tracked_orders.clear()
    await ex._recover_tracked_orders()
    assert "EX-CACHE" in ex._tracked_orders


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clearing_router_cache_still_routes():
    state = FakeState()
    proposal = _approved_proposal()
    r = _make_router(state)
    await r._route(proposal.model_dump(mode="json"))
    order1 = _published_order(r.publish)

    # Dropping the symbol perf-cache must not change correctness.
    r._routing_cache.clear()
    r.publish.reset_mock()
    await r._route(proposal.model_dump(mode="json"))
    order2 = _published_order(r.publish)
    assert order1["client_order_id"] == order2["client_order_id"]


# ── 7. Fail-closed on Redis failure ─────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.asyncio
async def test_placement_fails_closed_when_redis_lock_unavailable():
    state = FakeState()
    state.fail_lock = True  # Redis down → lock cannot be acquired
    placed = _open_limit_order(ex_id="EX-NOREDIS")
    ex, conn = _make_executor(state, returned_order=placed)

    with pytest.raises(ConnectionError):
        await ex._place_with_lock(_incoming_limit_order())

    # Critically: the order was NOT placed (no silent duplicate execution).
    conn.place_limit_order.assert_not_awaited()
