"""Cache behavior against an explicitly supplied disposable Redis database."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from core.accounting.models import BookState, CashBalance, OpeningBalances
from core.accounting.valuation import MissingValuationError, Valuation
from core.orchestrator.state_manager import StateManager
from tests.factories import with_performance

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def state():
    url = os.getenv("ACCOUNTING_TEST_REDIS_URL")
    if not url:
        pytest.skip("Set ACCOUNTING_TEST_REDIS_URL to a disposable test Redis database")
    state = StateManager()
    state._redis = Redis.from_url(url)
    try:
        yield state
    finally:
        await state._redis.aclose()


@pytest.mark.asyncio
async def test_mark_order_precision_venue_isolation_and_staleness(state):
    symbol = f"TEST{uuid4().hex.upper()}/USD"
    now = datetime.now(UTC)
    old = now - timedelta(minutes=10)
    try:
        await state.set_accounting_mark(
            "binance",
            symbol,
            "100.123456789123456789",
            now.isoformat(),
            int(now.timestamp() * 1000),
        )
        await state.set_accounting_mark(
            "binance", symbol, "1", old.isoformat(), int(old.timestamp() * 1000)
        )
        await state.set_accounting_mark(
            "kraken", symbol, "99", old.isoformat(), int(old.timestamp() * 1000)
        )
        valuation = Valuation(state, now, [])
        assert await valuation.mark("binance", symbol) == Decimal("100.123456789123456789")
        with pytest.raises(MissingValuationError):
            await valuation.mark("kraken", symbol)
    finally:
        await state.redis.delete(
            f"accounting:mark:binance:{symbol}", f"accounting:mark:kraken:{symbol}"
        )


@pytest.mark.asyncio
async def test_snapshot_cache_is_recreatable_and_short_lived(state):
    now = datetime.now(UTC)
    book = BookState.from_opening(
        OpeningBalances(
            as_of=now,
            reference="test",
            cash=[
                CashBalance(exchange="binance", currency="USD", amount=Decimal("1234.56")),
            ],
        )
    )
    portfolio = await Valuation(state, now, []).portfolio(state.book_id, book, [])
    try:
        await state.set_accounting_portfolio(portfolio)
        assert 0 < await state.redis.ttl(state.book_key("alghrest:portfolio:current")) <= 15
        assert await state.get_portfolio() == portfolio
        await state.invalidate_portfolio()
        assert await state.get_portfolio() is None
        # The durable projection restores the cache without funding or reapplying fills.
        await state.set_accounting_portfolio(portfolio)
        assert (await state.get_portfolio()).total_capital == Decimal("1234.56")
    finally:
        await state.invalidate_portfolio()


async def test_trade_gate_requires_fresh_matching_revision_and_book(state, monkeypatch):
    book_id = state.book_id
    now = datetime.now(UTC)
    book = BookState.from_opening(
        OpeningBalances(
            as_of=now,
            reference="explicit test",
            cash=[CashBalance(exchange="binance", currency="USD", amount=Decimal(1000))],
        )
    )
    portfolio = await Valuation(state, now, []).portfolio(book_id, book, [])
    portfolio = with_performance(portfolio)
    report = {
        "book_id": book_id,
        "ready": True,
        "revision": 0,
        "checked_at": now.isoformat(),
    }
    cache_key = f"alghrest:reconciliation:{book_id}"
    try:
        await state.set_accounting_portfolio(portfolio)
        assert not await state.trading_ready()
        await state.set_reconciliation(report)
        assert await state.trading_ready()
        for change in (
            {"ready": False},
            {"revision": 1},
            {"checked_at": (now - timedelta(minutes=1)).isoformat()},
            {"checked_at": "invalid"},
            {"checked_at": (now + timedelta(minutes=1)).isoformat()},
        ):
            await state.set_reconciliation(report | change)
            assert not await state.trading_ready()
        await state.set_reconciliation(report)
        assert not await state.trading_ready(
            portfolio.model_copy(update={"accounting_book_id": "foreign"})
        )
        assert not await state.trading_ready(
            portfolio.model_copy(update={"snapshot_time": now - timedelta(seconds=16)})
        )
        await state.redis.delete(cache_key)
        assert not await state.trading_ready()
    finally:
        await state.redis.delete(cache_key)
        await state.invalidate_portfolio()
