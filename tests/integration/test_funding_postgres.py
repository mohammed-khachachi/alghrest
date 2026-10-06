"""Real PostgreSQL atomicity, locking and restart tests on disposable paper books."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from connectors.exchanges.paper import PaperVenue
from core.accounting import performance
from core.accounting.funding import Deposit, PaperDeposits
from core.accounting.models import CashBalance, OpeningBalances
from core.accounting.repository import Ledger
from core.accounting.valuation import MissingValuationError
from core.config import settings
from core.data.models import Order, OrderSide
from core.execution.contracts import AccountScope, RecoveryBlockedError
from core.execution.store import ExecutionStore
from scripts.paper_runtime import migrate
from tests.factories import persist_snapshot

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def funded(monkeypatch):
    dsn = os.getenv("ACCOUNTING_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ACCOUNTING_TEST_DATABASE_URL to a disposable test database")
    ledger = await Ledger.connect(dsn, f"paper_trading:funding-test-{uuid4()}")
    await migrate(ledger)
    account = AccountScope(exchange="binance", symbols=["SOL/USDT"])
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(settings, "execution_accounts", [account])
    monkeypatch.setattr(settings, "accounting_usd_pegs", [])
    await ledger.open_book(
        OpeningBalances(
            as_of=datetime.now(UTC) - timedelta(days=1),
            reference="synthetic opening",
            cash=[CashBalance(exchange="binance", currency="USDT", amount=Decimal(150))],
        )
    )
    store = ExecutionStore(ledger)
    await store.configure([account])
    state = SimpleNamespace(
        get_json=AsyncMock(
            side_effect=lambda k: {
                "price": "1" if k.endswith("USDT/USD") else "100",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        ),
        invalidate_portfolio=AsyncMock(),
        redis=SimpleNamespace(delete=AsyncMock()),
    )
    paper = PaperVenue(store, account, state)
    await paper.initialize()
    obj = SimpleNamespace(
        ledger=ledger,
        store=store,
        state=state,
        paper=paper,
        service=PaperDeposits(ledger, state),
        account=account,
    )
    try:
        yield obj
    finally:
        for table in (
            "paper_fills",
            "paper_orders",
            "paper_accounts",
            "outbox",
            "fills",
            "cursors",
            "orders",
            "books",
        ):
            await ledger.pool.execute(
                f"DELETE FROM execution.{table} WHERE book_id=$1", ledger.book_id
            )
        await ledger.pool.execute("DELETE FROM accounting.fills WHERE book_id=$1", ledger.book_id)
        await ledger.pool.execute("DELETE FROM accounting.books WHERE book_id=$1", ledger.book_id)
        await store.close()


def deposit(**changes):
    return Deposit.model_validate(
        {"exchange": "binance", "amount": "150", "reference": "monthly-2026-10", **changes}
    )


def order():
    return Order(
        symbol="SOL/USDT",
        exchange="binance",
        side="BUY",
        order_type="MARKET",
        size=Decimal("0.03"),
        strategy_id="test",
        agent_id=12,
    )


async def test_dry_run_then_atomic_cash_and_performance_with_no_pnl(funded):
    r = funded
    dry = await r.service.register(deposit())
    assert not dry.applied and dry.balance_after == 300
    assert (await r.ledger.load()).revision == 0
    assert (await r.paper.balances())["USDT"] == 150
    assert await performance.load(r.ledger.pool, r.ledger.book_id) is None
    receipt = await r.service.register(deposit(), apply=True)
    assert receipt.applied and receipt.revision == 1
    assert receipt.balance_before == receipt.value_usd == receipt.units_issued == 150
    assert (await r.paper.balances())["USDT"] == 300
    value = await persist_snapshot(r.ledger, r.state)
    assert value.total_capital == value.available_capital == 300
    assert value.emergency_reserve == 45
    assert value.daily_pnl == value.weekly_pnl == value.unrealized_pnl == 0
    assert value.performance.unit_price == 1 and value.performance.units == 300
    assert value.performance.drawdown() == 0
    assert (
        await r.ledger.pool.fetchval(
            "SELECT count(*) FROM accounting.fills WHERE book_id=$1", r.ledger.book_id
        )
        == 0
    )
    assert not await r.ledger.pool.fetchval(
        "SELECT ready FROM execution.books WHERE book_id=$1", r.ledger.book_id
    )
    r.state.invalidate_portfolio.assert_awaited_once()


async def test_concurrent_duplicate_receipts_and_conflicting_reference(funded):
    r = funded
    receipts = await asyncio.gather(
        *(r.service.register(deposit(amount="150.000"), apply=True) for _ in range(6))
    )
    assert all(x == receipts[0] for x in receipts)
    same = await r.service.register(deposit(amount="1.5E2"), apply=True)
    assert same == receipts[0] and (await r.ledger.load()).revision == 1
    with pytest.raises(ValueError, match="conflicts"):
        await r.service.register(deposit(amount="151"), apply=True)
    assert (await r.paper.balances())["USDT"] == 300


async def test_concurrent_distinct_deposits_add_without_lost_update(funded):
    r = funded
    receipts = await asyncio.gather(
        *(r.service.register(deposit(reference=f"d-{i}"), apply=True) for i in range(5))
    )
    assert sorted(x.revision for x in receipts) == [1, 2, 3, 4, 5]
    assert (await r.paper.balances())["USDT"] == 900
    assert (await persist_snapshot(r.ledger, r.state)).performance.unit_price == 1


async def test_loss_is_not_hidden_by_funding_or_restart(funded):
    r = funded
    await persist_snapshot(r.ledger, r.state)
    r.state.get_json.side_effect = lambda _: {
        "price": "0.9",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    receipt = await r.service.register(deposit(), apply=True)
    assert receipt.unit_price == Decimal("0.9") and receipt.value_usd == 135
    r.state.invalidate_portfolio.side_effect = RuntimeError("Redis unavailable")
    restarted = await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], r.ledger.book_id)
    try:
        # Simulates commit followed by lost CLI response and a cache outage.
        replay = await PaperDeposits(restarted, r.state).register(deposit(), apply=True)
        assert replay == receipt
        value = await persist_snapshot(restarted, r.state)
        assert value.performance.units == 300 and value.performance.peak == 1
        assert value.performance.drawdown() == 0.1
        assert value.performance.drawdown(value.performance.month.unit_price) == 0.1
        assert value.total_capital == 270 and (await restarted.load()).revision == 1
    finally:
        await restarted.close()


async def test_failure_rolls_back_journal_cash_venue_units_and_revision(funded, monkeypatch):
    r = funded
    await persist_snapshot(r.ledger, r.state)
    before = await performance.load(r.ledger.pool, r.ledger.book_id)
    monkeypatch.setattr(
        performance, "save", AsyncMock(side_effect=RuntimeError("simulated SQL failure"))
    )
    with pytest.raises(RuntimeError, match="SQL failure"):
        await r.service.register(deposit(), apply=True)
    assert (await r.ledger.load()).revision == 0 and (await r.paper.balances())["USDT"] == 150
    assert await performance.load(r.ledger.pool, r.ledger.book_id) == before
    assert (
        await r.ledger.pool.fetchval(
            "SELECT count(*) FROM accounting.deposits WHERE book_id=$1", r.ledger.book_id
        )
        == 0
    )
    r.state.invalidate_portfolio.assert_not_awaited()


@pytest.mark.parametrize(
    "fault", ["stale", "missing", "mismatch", "scope", "live", "legacy", "insolvent"]
)
async def test_unverified_book_never_accepts_funding(funded, monkeypatch, fault):
    r = funded
    if fault == "stale":
        r.state.get_json.side_effect = lambda _: {
            "price": "1",
            "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        }
    elif fault == "missing":
        r.state.get_json.side_effect = None
        r.state.get_json.return_value = None
    elif fault == "mismatch":
        await r.ledger.pool.execute(
            "UPDATE execution.paper_accounts SET balances='{}' WHERE book_id=$1", r.ledger.book_id
        )
    elif fault == "scope":
        monkeypatch.setattr(settings, "execution_accounts", [])
    elif fault == "live":
        monkeypatch.setattr(settings, "environment", "live")
    elif fault == "legacy":
        await r.ledger.pool.execute(
            "UPDATE accounting.books SET state=jsonb_set(state,'{revision}','1') WHERE book_id=$1",
            r.ledger.book_id,
        )
    else:
        await persist_snapshot(r.ledger, r.state)
        async with r.ledger.locked_state() as (conn, book, _):
            for cash in book.cash.values():
                cash.amount = Decimal(0)
            await conn.execute(
                "UPDATE accounting.books SET state=$2::jsonb WHERE book_id=$1",
                r.ledger.book_id,
                book.model_dump_json(),
            )
            await conn.execute(
                "UPDATE execution.paper_accounts SET balances='{}' WHERE book_id=$1",
                r.ledger.book_id,
            )
    with pytest.raises((ValueError, MissingValuationError)):
        await r.service.register(deposit(), apply=True)
    assert (
        await r.ledger.pool.fetchval(
            "SELECT count(*) FROM accounting.deposits WHERE book_id=$1", r.ledger.book_id
        )
        == 0
    )


async def make_ready(r):
    await persist_snapshot(r.ledger, r.state)
    await r.ledger.pool.execute(
        "UPDATE execution.books SET ready=true,verified_revision=0,verified_until=now()+interval '30 seconds' WHERE book_id=$1",
        r.ledger.book_id,
    )


async def test_pending_orders_block_funding_and_deposit_blocks_new_order(funded):
    r = funded
    await make_ready(r)
    intent = order()
    await r.store.prepare(intent)
    with pytest.raises(ValueError, match="Pending"):
        await r.service.register(deposit(), apply=True)
    await r.store.abort_prepared(intent, "test cancelled before submission")
    await r.service.register(deposit(), apply=True)
    with pytest.raises(RecoveryBlockedError):
        await r.store.prepare(order())


async def test_order_prepare_races_deposit_under_same_book_lock(funded):
    r = funded
    await make_ready(r)
    results = await asyncio.gather(
        r.store.prepare(order()), r.service.register(deposit(), apply=True), return_exceptions=True
    )
    assert sum(isinstance(x, Exception) for x in results) == 1
    if results[0] is True:
        assert isinstance(results[1], ValueError)
        assert (await r.paper.balances())["USDT"] == 150
    else:
        assert isinstance(results[0], RecoveryBlockedError)
        assert (await r.paper.balances())["USDT"] == 300


async def test_unaccounted_fill_blocks_deposit_then_later_fills_preserve_funding(funded):
    r = funded
    await persist_snapshot(r.ledger, r.state)
    intent = order()
    placed = await r.paper.place(intent)
    page = await r.paper.history_page(
        "SOL/USDT", 0, int(datetime.now(UTC).timestamp() * 1000) + 1000, None
    )
    # Paper state has moved but accounting has not; no credit is allowed.
    with pytest.raises(ValueError, match="balances"):
        await r.service.register(deposit(), apply=True)
    for fill in page.fills:
        await r.ledger.record(fill)
    receipt = await r.service.register(deposit(), apply=True)
    assert receipt.revision == 2
    assert (await r.paper.balances())["USDT"] == Decimal("296.997")
    value = await persist_snapshot(r.ledger, r.state)
    assert value.total_capital + value.unrealized_pnl == Decimal("299.997")
    assert value.performance.drawdown() == pytest.approx(0.003 / 150)
    # A subsequent sell updates cash and realized P&L, retaining the deposit.
    sell = order().model_copy(update={"side": OrderSide.SELL})
    await r.paper.place(sell)
    page = await r.paper.history_page(
        "SOL/USDT", 0, int(datetime.now(UTC).timestamp() * 1000) + 1000, None
    )
    for fill in page.fills:
        await r.ledger.record(fill)
    assert (await r.ledger.load()).revision == 3
    assert (await r.paper.balances())["USDT"] == Decimal("299.994")
    value = await persist_snapshot(r.ledger, r.state)
    assert value.total_capital == Decimal("299.994") and not value.positions
    assert placed.exchange_order_id


async def test_cache_failure_after_commit_keeps_receipt_and_durable_gate(funded):
    r = funded
    await make_ready(r)
    r.state.invalidate_portfolio.side_effect = ConnectionError("Redis unavailable")
    first = await r.service.register(deposit(), apply=True)
    assert first.applied
    assert (await r.paper.balances())["USDT"] == 300
    with pytest.raises(RecoveryBlockedError):
        await r.store.prepare(order())
    r.state.invalidate_portfolio.side_effect = None
    assert await r.service.register(deposit(), apply=True) == first
    restored = await persist_snapshot(r.ledger, r.state)
    assert restored.accounting_revision == 1
    assert restored.performance.units == restored.total_capital == 300
    assert restored.performance.unit_price == 1


async def test_unsettled_execution_fill_blocks_even_when_balances_match(funded):
    r = funded
    # A recovered fill may still be waiting for accounting even when native
    # inventory happens to match (for example offsetting executions).
    await r.ledger.pool.execute(
        """INSERT INTO execution.fills(book_id,exchange,account_id,symbol,trade_id,
        exchange_order_id,fingerprint,payload) VALUES($1,'binance','default',
        'SOL/USDT','pending-trade','pending-order','pending-fingerprint','{}')""",
        r.ledger.book_id,
    )
    with pytest.raises(ValueError, match="Unaccounted"):
        await r.service.register(deposit(), apply=True)
    assert (await r.ledger.load()).revision == 0
    assert (await r.paper.balances())["USDT"] == 150


async def test_independent_paper_open_order_blocks_deposit(funded):
    r = funded
    from core.data.models import OrderType

    limit = order().model_copy(update={"order_type": OrderType.LIMIT, "price": Decimal(50)})
    await r.paper.place(limit)  # does not cross the 100 USDT quote
    with pytest.raises(ValueError, match="Pending"):
        await r.service.register(deposit(), apply=True)
    assert (await r.paper.balances())["USDT"] == 150


async def test_execution_reconciliation_requires_matching_performance(funded):
    r = funded
    now = datetime.now(UTC)
    await r.ledger.pool.execute(
        """INSERT INTO execution.cursors(book_id,exchange,account_id,symbol,through_ms)
        VALUES($1,'binance','default','SOL/USDT',$2)""",
        r.ledger.book_id,
        int(now.timestamp() * 1000),
    )
    balances = {r.account.key: await r.paper.balances()}
    report = await r.store.verify([r.account], balances, [], {}, 30)
    assert not report["ready"]
    assert report["reasons"] == ["durable performance snapshot missing or changed"]
    await persist_snapshot(r.ledger, r.state)
    assert (await r.store.verify([r.account], balances, [], {}, 30))["ready"]
    await r.ledger.pool.execute(
        """UPDATE accounting.performance SET state=jsonb_set(state,'{observed_at}',to_jsonb($2::text))
        WHERE book_id=$1""",
        r.ledger.book_id,
        (now - timedelta(minutes=1)).isoformat(),
    )
    with pytest.raises(RecoveryBlockedError, match="performance"):
        await r.store.prepare(order())
    assert not (await r.store.verify([r.account], balances, [], {}, 30))["ready"]
