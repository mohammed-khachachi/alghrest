"""Run only against an explicitly provided disposable PostgreSQL database."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import asyncpg
import pytest
import pytest_asyncio

from core.accounting.models import BookState, CashBalance, OpeningBalances, key
from core.accounting.repository import FillConflictError, Ledger
from core.data.models import Exchange, Fill, OrderSide
from core.orchestrator.message_bus import AlghrestConsumer

pytestmark = pytest.mark.integration
NOW = datetime(2026, 1, 5, 12, tzinfo=UTC)


def fill(trade_id, side="BUY", price="100", minutes=0):
    return Fill(
        order_id=uuid4(),
        exchange_order_id="order",
        exchange_trade_id=trade_id,
        exchange=Exchange.BINANCE,
        symbol="BTC/USD",
        side=OrderSide(side),
        fill_size=Decimal(1),
        fill_price=Decimal(price),
        timestamp=NOW + timedelta(minutes=minutes),
        fees=[],
    )


@pytest_asyncio.fixture
async def ledger():
    dsn = os.getenv("ACCOUNTING_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ACCOUNTING_TEST_DATABASE_URL to a disposable test database")
    book = await Ledger.connect(dsn, f"test:{uuid4()}")
    from scripts.paper_runtime import migrate

    await migrate(book)
    opening = OpeningBalances(
        as_of=NOW - timedelta(days=1),
        reference="test",
        cash=[
            CashBalance(exchange=Exchange.BINANCE, currency="USD", amount=Decimal(1000)),
        ],
    )
    await book.open_book(opening)
    try:
        yield book
    finally:
        await book.pool.execute(
            "DELETE FROM accounting.opening_covered_messages WHERE book_id=$1", book.book_id
        )
        await book.pool.execute("DELETE FROM accounting.fills WHERE book_id=$1", book.book_id)
        await book.pool.execute("DELETE FROM accounting.books WHERE book_id=$1", book.book_id)
        await book.close()


@pytest.mark.asyncio
async def test_concurrent_duplicates_and_reconnect(ledger):
    trade = fill("one")
    results = await asyncio.gather(*(ledger.record(trade) for _ in range(12)))
    assert sum(results) == 1
    # A fresh connection has no Python/Redis cache and still rejects a replay.
    restart = await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], ledger.book_id)
    try:
        assert not await restart.record(trade.model_copy(update={"fill_id": uuid4()}))
        state = await restart.load()
        assert state.revision == 1
        assert state.cash[key("binance", "default", "USD")].amount == 900
        assert state.positions[key("binance", "default", "BTC/USD")].quantity == 1
    finally:
        await restart.close()


@pytest.mark.asyncio
async def test_conflicting_identity_and_reseed_cannot_change_book(ledger):
    trade = fill("one")
    await ledger.record(trade)
    before = await ledger.load()
    with pytest.raises(FillConflictError):
        await ledger.record(trade.model_copy(update={"fill_price": Decimal(900)}))
    assert await ledger.load() == before
    with pytest.raises(asyncpg.UniqueViolationError):
        await ledger.open_book(OpeningBalances(as_of=NOW, reference="reseed", cash=[]))
    assert await ledger.load() == before


@pytest.mark.asyncio
async def test_failure_after_journal_insert_rolls_back_everything(ledger, monkeypatch):
    original = BookState.model_dump_json

    def fail_projection(self, *args, **kwargs):
        if self.revision:
            raise RuntimeError("simulated crash before projection write")
        return original(self, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(BookState, "model_dump_json", fail_projection)
        with pytest.raises(RuntimeError, match="simulated crash"):
            await ledger.record(fill("one"))
    assert (
        await ledger.pool.fetchval(
            "SELECT count(*) FROM accounting.fills WHERE book_id=$1", ledger.book_id
        )
        == 0
    )
    assert (await ledger.load()).revision == 0
    assert await ledger.record(fill("one"))


@pytest.mark.asyncio
async def test_late_fill_rebuilds_cost_basis_and_realized_pnl(ledger):
    await ledger.record(fill("a", price="100"))
    await ledger.record(fill("c", "SELL", price="180", minutes=2))
    await ledger.record(fill("b", price="140", minutes=1))
    state = await ledger.load()
    position = state.positions[key("binance", "default", "BTC/USD")]
    assert position.quantity == 1
    assert position.average_cost == 120
    assert state.cash[key("binance", "default", "USD")].amount == 940
    assert (
        await ledger.pool.fetchval(
            "SELECT (realized->>'USD')::numeric FROM accounting.fills WHERE book_id=$1 AND trade_id='c'",
            ledger.book_id,
        )
        == 60
    )


@pytest.mark.asyncio
async def test_cutoff_accounts_for_replay_without_booking_opening_twice(ledger):
    old = fill("historical").model_copy(update={"timestamp": NOW - timedelta(days=1)})
    assert await ledger.record(old)
    assert not (await ledger.load()).positions
    assert (
        await ledger.pool.fetchval(
            "SELECT status FROM accounting.fills WHERE book_id=$1",
            ledger.book_id,
        )
        == "before_opening"
    )


@pytest.mark.asyncio
async def test_writer_lease_prevents_two_publishers(ledger):
    await ledger.claim_writer()
    other = await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], ledger.book_id)
    try:
        with pytest.raises(RuntimeError, match="Another accountant"):
            await other.claim_writer()
        await ledger.check_writer()
    finally:
        await other.close()


@pytest.mark.asyncio
async def test_distinct_concurrent_partial_fills_are_not_lost(ledger):
    results = await asyncio.gather(*(ledger.record(fill(str(i))) for i in range(10)))
    assert all(results)
    state = await ledger.load()
    assert state.revision == 10
    assert state.cash[key("binance", "default", "USD")].amount == 0
    assert state.positions[key("binance", "default", "BTC/USD")].quantity == 10


@pytest.mark.asyncio
async def test_failure_after_database_commit_before_kafka_ack_replays_safely(ledger):
    trade = fill("committed-before-crash")

    class Records:
        def __init__(self):
            self.commit = AsyncMock(side_effect=RuntimeError("commit response lost"))

        def __aiter__(self):
            async def records():
                yield SimpleNamespace(topic="fills.confirmed", partition=0, offset=0, value=trade)

            return records()

    consumer = AlghrestConsumer("test", [])
    consumer._consumer = Records()

    async def handle(payload):
        await ledger.record(payload)

    with pytest.raises(RuntimeError, match="commit response lost"):
        await consumer.process(handle)
    assert (await ledger.load()).revision == 1
    consumer._consumer.commit.side_effect = None
    await consumer.process(handle)
    assert (await ledger.load()).revision == 1
    assert (await ledger.load()).cash[key("binance", "default", "USD")].amount == 900


@pytest.mark.asyncio
async def test_future_fill_and_missing_opening_fail_without_funding(ledger):
    with pytest.raises(ValueError, match="future"):
        await ledger.record(
            fill("future").model_copy(update={"timestamp": datetime.now(UTC) + timedelta(days=1)})
        )
    assert (await ledger.load()).revision == 0
    missing = Ledger(ledger.pool, f"missing:{uuid4()}")
    with pytest.raises(RuntimeError, match="explicitly import"):
        await missing.record(fill("no-opening"))


@pytest.mark.asyncio
async def test_legacy_messages_are_archived_only_when_opening_covers_them(ledger):
    old = fill("legacy").model_copy(
        update={
            "exchange_trade_id": None,
            "timestamp": NOW - timedelta(days=1),
        }
    )
    message = {
        "message_id": str(uuid4()),
        "message_type": "Fill",
        "payload": old.model_dump(mode="json"),
    }
    await ledger.archive_opening_covered_message(message, old)
    await ledger.archive_opening_covered_message(message, old)
    assert (
        await ledger.pool.fetchval(
            "SELECT count(*) FROM accounting.opening_covered_messages WHERE book_id=$1",
            ledger.book_id,
        )
        == 1
    )
    assert (await ledger.load()).revision == 0
    with pytest.raises(ValueError, match="Post-opening"):
        await ledger.archive_opening_covered_message(
            message, old.model_copy(update={"timestamp": NOW})
        )


@pytest.mark.asyncio
async def test_pnl_aggregation_uses_corrected_journal_and_utc_boundaries(ledger):
    await ledger.record(fill("a", price="100"))
    await ledger.record(fill("b", "SELL", price="120", minutes=1))
    async with ledger.locked_state() as (conn, _, _opening):
        rows = await ledger.pnl_since(conn, NOW.replace(hour=0))
    assert len(rows) == 1
    assert rows[0]["occurred_at"] == NOW.replace(hour=0)
    assert rows[0]["realized"] == '{"USD": "20"}'
