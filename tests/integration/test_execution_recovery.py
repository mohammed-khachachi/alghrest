"""Transactional recovery tests against an explicitly disposable PostgreSQL DB."""

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio

from connectors.exchanges.paper import PaperVenue
from core.accounting.models import CashBalance, OpeningBalances
from core.accounting.repository import FillConflictError, Ledger
from core.data.models import Exchange, Fill, Order, OrderSide, OrderStatus, OrderType
from core.execution.contracts import (
    AccountScope,
    OrderConflictError,
    RecoveryBlockedError,
    TradePage,
)
from core.execution.recovery import RecoveryCoordinator
from core.execution.store import ExecutionStore
from tests.factories import persist_snapshot

pytestmark = pytest.mark.integration


def order(**changes):
    return Order(
        symbol="BTC/USD",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal(1),
        strategy_id="test",
        agent_id=12,
        **changes,
    )


def fill(trade_id="one", **changes):
    fields = dict(
        order_id=uuid4(),
        exchange_order_id="external",
        exchange_trade_id=trade_id,
        exchange=Exchange.BINANCE,
        symbol="BTC/USD",
        side=OrderSide.BUY,
        fill_size=Decimal(1),
        fill_price=Decimal(100),
        fees=[],
        timestamp=datetime.now(UTC) - timedelta(seconds=1),
    )
    return Fill(**(fields | changes))


@pytest_asyncio.fixture
async def recovery():
    dsn = os.getenv("ACCOUNTING_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ACCOUNTING_TEST_DATABASE_URL to a disposable test database")
    ledger = await Ledger.connect(dsn, f"test:{uuid4()}")
    root = Path(__file__).resolve().parents[2]
    for migration in (
        "001_accounting.sql",
        "002_execution_recovery.sql",
        "003_funding_performance.sql",
    ):
        await ledger.pool.execute((root / "infra/migrations" / migration).read_text())
    await ledger.open_book(
        OpeningBalances(
            as_of=datetime.now(UTC) - timedelta(minutes=5),
            reference="explicit synthetic test opening",
            cash=[CashBalance(exchange=Exchange.BINANCE, currency="USD", amount=Decimal(1000))],
        )
    )
    store = ExecutionStore(ledger)
    await store.claim_writer()
    account = AccountScope(exchange=Exchange.BINANCE, symbols=["BTC/USD"])
    await store.configure([account])
    state = SimpleNamespace(
        set_reconciliation=AsyncMock(),
        is_kill_switch_active=AsyncMock(return_value=False),
        get_json=AsyncMock(
            side_effect=lambda _: {"price": "100", "timestamp": datetime.now(UTC).isoformat()}
        ),
    )
    paper = PaperVenue(store, account, state)
    await paper.initialize()

    async def publish(_topic, *, payload, message_type):
        if message_type == "Fill":
            await ledger.record(Fill.model_validate(payload))
            await persist_snapshot(ledger, state)

    await persist_snapshot(ledger, state)
    coordinator = RecoveryCoordinator(store, [account], {account.key: paper}, state, publish)
    try:
        yield SimpleNamespace(
            store=store,
            ledger=ledger,
            account=account,
            paper=paper,
            state=state,
            coordinator=coordinator,
        )
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


async def ready(r):
    await persist_snapshot(r.ledger, r.state)
    report = await r.coordinator.run_once()
    assert report["ready"], report


async def test_lost_response_recovers_without_second_placement_after_restart(recovery):
    r = recovery
    await ready(r)
    intent = order()
    assert await r.store.prepare(intent)
    await r.paper.place(intent)  # exchange accepted; process dies before recording response
    await r.store.uncertain(intent, "response lost")
    # A fresh pool/store observes durable intent and simulated venue state.
    restarted = ExecutionStore(
        await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], r.ledger.book_id)
    )
    try:
        assert not await restarted.prepare(intent)
        paper = PaperVenue(restarted, r.account, r.state)
        await paper.initialize()  # never reset changing balances to the opening
        assert (await paper.balances())["USD"] == Decimal("899.9")
        r.coordinator.venues[r.account.key] = paper
        first = await r.coordinator.run_once()
        assert not first["ready"]  # terminal quantity not yet backed by recovered fills
        await ready(r)
        assert (await r.ledger.load()).revision == 1
        assert (
            await r.ledger.pool.fetchval(
                "SELECT count(*) FROM execution.paper_orders WHERE book_id=$1", r.ledger.book_id
            )
            == 1
        )
        assert (
            await r.ledger.pool.fetchval(
                "SELECT count(*) FROM execution.paper_fills WHERE book_id=$1", r.ledger.book_id
            )
            == 1
        )
    finally:
        await restarted.close()


async def test_crash_before_network_call_remains_unresolved_never_resubmitted(recovery):
    r = recovery
    await ready(r)
    intent = order()
    assert await r.store.prepare(intent)
    report = await r.coordinator.run_once()
    assert not report["ready"] and any("unresolved submission" in s for s in report["reasons"])
    assert not await r.store.prepare(intent)
    assert await r.paper.lookup(intent) is None
    with pytest.raises(RecoveryBlockedError):
        await r.store.prepare(order())


async def test_concurrent_identity_and_atomic_gate(recovery):
    r = recovery
    await ready(r)
    intent = order()
    assert sum(await asyncio.gather(*(r.store.prepare(intent) for _ in range(8)))) == 1
    with pytest.raises(OrderConflictError):
        await r.store.prepare(intent.model_copy(update={"size": Decimal(2)}))
    with pytest.raises(RecoveryBlockedError):
        await r.store.prepare(order())
    with pytest.raises(RecoveryBlockedError, match="owns"):
        other = ExecutionStore(
            await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], r.ledger.book_id)
        )
        try:
            await other.claim_writer()
        finally:
            await other.close()


async def test_page_rollback_retains_cursor_and_no_partial_outbox(recovery, monkeypatch):
    r = recovery
    checkpoint = await r.store.checkpoint(r.account, "BTC/USD")
    original = r.store._event
    monkeypatch.setattr(
        r.store, "_event", AsyncMock(side_effect=RuntimeError("crash after insert"))
    )
    with pytest.raises(RuntimeError):
        await r.store.capture_page(r.account, "BTC/USD", checkpoint["version"], None, 10, [fill()])
    assert not await r.store.outbox()
    assert (await r.store.checkpoint(r.account, "BTC/USD"))["version"] == 0
    assert (
        await r.ledger.pool.fetchval(
            "SELECT count(*) FROM execution.fills WHERE book_id=$1", r.ledger.book_id
        )
        == 0
    )
    monkeypatch.setattr(r.store, "_event", original)
    await r.store.capture_page(r.account, "BTC/USD", 0, None, 10, [fill()])
    assert len(await r.store.outbox()) == 1


async def test_delivery_retry_and_missing_ledger_redelivery(recovery):
    r = recovery
    trade = fill()
    await r.store.checkpoint(r.account, "BTC/USD")
    await r.store.capture_page(r.account, "BTC/USD", 0, None, 10, [trade])
    settle = r.coordinator.publish
    r.coordinator.publish = AsyncMock(side_effect=RuntimeError("Kafka unavailable"))
    with pytest.raises(RuntimeError):
        await r.coordinator.flush()
    assert (await r.store.outbox())[0]["delivered_at"] is None
    r.coordinator.publish = AsyncMock()  # Kafka ack alone is not ledger settlement
    await r.coordinator.flush()
    assert len(await r.store.outbox()) == 1
    r.coordinator.publish = settle
    await r.coordinator.flush()
    assert not await r.store.outbox()
    assert (await r.ledger.load()).revision == 1
    await r.store.capture_page(r.account, "BTC/USD", 1, None, 20, [trade])
    assert not await r.store.outbox()
    with pytest.raises(FillConflictError):
        await r.store.capture_page(
            r.account, "BTC/USD", 2, None, 20, [trade.model_copy(update={"fill_size": Decimal(2)})]
        )


async def test_cancelled_partial_order_waits_for_delayed_fill(recovery):
    r = recovery
    await ready(r)
    intent = order()
    await r.store.prepare(intent)
    cancelled = intent.model_copy(
        update={
            "exchange_order_id": "partial",
            "status": OrderStatus.CANCELLED,
            "filled_size": Decimal("0.4"),
        }
    )
    await r.store.observe(intent, cancelled)
    assert len(await r.store.orders()) == 1
    checkpoint = await r.store.checkpoint(r.account, "BTC/USD")
    await r.store.capture_page(
        r.account,
        "BTC/USD",
        checkpoint["version"],
        None,
        10,
        [fill(exchange_order_id="partial", fill_size=Decimal("0.4"))],
    )
    await r.store.observe(intent, cancelled)
    assert not await r.store.orders()
    report = await r.store.verify([r.account], {r.account.key: {"USD": Decimal(1000)}}, [], {}, 30)
    assert not report["ready"] and any("not settled" in x for x in report["reasons"])


async def test_halt_cancels_persistent_limit_and_recovers_after_cancel_failure(recovery):
    r = recovery
    await ready(r)
    intent = order().model_copy(update={"order_type": OrderType.LIMIT, "price": Decimal(90)})
    await r.store.prepare(intent)
    await r.store.observe(intent, await r.paper.place(intent))
    cancel = r.paper.cancel
    r.paper.cancel = AsyncMock(side_effect=RuntimeError("outage"))
    r.state.is_kill_switch_active.return_value = True
    report = await r.coordinator.run_once()
    assert not report["ready"]
    assert (await r.store.orders())[0]["cancel_requested"]
    r.paper.cancel = cancel
    await r.coordinator.run_once()
    await ready(r)
    assert not await r.paper.open_orders()


async def test_balance_drift_and_unknown_open_orders_block(recovery):
    r = recovery
    await ready(r)
    r.paper.balances = AsyncMock(return_value={"USD": Decimal(1000), "ETH": Decimal("-0.01")})
    report = await r.coordinator.run_once()
    assert not report["ready"] and "ETH" in report["differences"][r.account.key]
    r.paper.balances.return_value = {"USD": Decimal(1000)}
    r.paper.open_orders = AsyncMock(return_value=[order()])
    assert not (await r.coordinator.run_once())["ready"]


async def test_cursor_budget_restart_cycle_and_full_scan(recovery):
    r = recovery
    r.coordinator.page_budget = 1
    target = int(datetime.now(UTC).timestamp() * 1000)
    r.paper.history_page = AsyncMock(
        side_effect=[
            TradePage([], {"token": "a"}),
            TradePage([], {"token": "b"}),
            TradePage([], {"token": "a"}),
        ]
    )
    assert not await r.coordinator.history(r.account, "BTC/USD", target)
    assert not await r.coordinator.history(r.account, "BTC/USD", target)
    with pytest.raises(RecoveryBlockedError, match="repeated"):
        await r.coordinator.history(r.account, "BTC/USD", target)
    assert r.paper.history_page.await_args.args[3] == {"token": "b"}
    r.paper.history_page.side_effect = None
    r.paper.history_page.return_value = TradePage([], None)
    assert await r.coordinator.history(r.account, "BTC/USD", target)
    async with r.ledger.locked_state() as (_, _, opening):
        initial = int(opening.as_of.timestamp() * 1000)
    r.coordinator.overlap_ms = 1000
    await r.coordinator.history(r.account, "BTC/USD", target + 1000)
    assert r.paper.history_page.await_args.args[1] == target - 1000
    r.coordinator.full_scan_ms = 1
    await r.coordinator.history(r.account, "BTC/USD", target + 2000)
    assert r.paper.history_page.await_args.args[1] == initial


async def test_changed_ledger_revision_blocks_previously_verified_gate(recovery):
    r = recovery
    await ready(r)
    await r.ledger.record(fill())
    with pytest.raises(RecoveryBlockedError, match="changed"):
        await r.store.prepare(order())


async def test_paper_duplicate_orders_fee_cash_and_restart(recovery):
    r = recovery
    intent = order()
    results = await asyncio.gather(*(r.paper.place(intent) for _ in range(4)))
    assert all(o.status == OrderStatus.FILLED for o in results)
    assert await r.paper.balances() == {"USD": Decimal("899.9"), "BTC": Decimal(1)}
    await r.paper.initialize()
    assert (await r.paper.balances())["USD"] == Decimal("899.9")
    with pytest.raises(OrderConflictError):
        await r.paper.place(intent.model_copy(update={"size": Decimal(2)}))
    await r.paper.cancel(results[0])
    assert (await r.paper.lookup(intent)).status == OrderStatus.FILLED
    rejected = await r.paper.place(
        order().model_copy(update={"side": OrderSide.SELL, "size": Decimal(2)})
    )
    assert rejected.status == OrderStatus.REJECTED


async def test_paper_history_over_page_limit_replays_all(recovery):
    r = recovery
    for i in range(205):
        payload = fill(str(i), fill_size=Decimal("0.001")).model_dump_json()
        await r.store.pool.execute(
            "INSERT INTO execution.paper_fills(book_id,exchange,account_id,symbol,payload) VALUES($1,'binance','default','BTC/USD',$2::jsonb)",
            r.store.book_id,
            payload,
        )
    target = int(datetime.now(UTC).timestamp() * 1000)
    assert await r.coordinator.history(r.account, "BTC/USD", target)
    events = await r.store.outbox()
    assert len(events) == 205
    assert len({json.loads(e["payload"])["exchange_trade_id"] for e in events}) == 205
    await r.coordinator.flush()
    assert (await r.ledger.load()).revision == 205


async def test_delayed_fill_outside_overlap_is_found_by_full_rescan(recovery):
    r = recovery
    await ready(r)
    r.coordinator.overlap_ms = 1
    late = fill("delayed", timestamp=datetime.now(UTC) - timedelta(minutes=2))

    async def history(symbol, start, end, cursor):
        stamp = int(late.timestamp.timestamp() * 1000)
        return TradePage([late] if start <= stamp <= end else [], None)

    r.paper.history_page = history
    r.paper.balances = AsyncMock(return_value={"USD": Decimal(900), "BTC": Decimal(1)})
    assert not (await r.coordinator.run_once())["ready"]
    assert (await r.ledger.load()).revision == 0
    r.coordinator.full_scan_ms = 1
    await ready(r)
    assert (await r.ledger.load()).revision == 1


async def test_expired_scope_and_aborted_claim_cannot_reopen_risk(recovery):
    r = recovery
    await ready(r)
    with pytest.raises(RecoveryBlockedError, match="scope"):
        await r.store.prepare(order().model_copy(update={"symbol": "ETH/USD"}))
    await r.store.pool.execute(
        "UPDATE execution.books SET verified_until=now()-interval '1 second' WHERE book_id=$1",
        r.store.book_id,
    )
    with pytest.raises(RecoveryBlockedError, match="stale"):
        await r.store.prepare(order())
    await ready(r)
    intent = order()
    await r.store.prepare(intent)
    await r.store.abort_prepared(intent, "halt before HTTP")
    assert not await r.store.orders()
    assert not await r.store.prepare(intent)
    assert await r.paper.lookup(intent) is None
    with pytest.raises(RecoveryBlockedError):
        await r.store.abort_prepared(intent, "cannot abort twice")


async def test_paper_prepare_is_repeatable_but_never_reseeds(recovery, tmp_path, monkeypatch):
    from core.config import settings
    from scripts.paper import run

    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(settings, "accounting_book", f"setup-{uuid4()}")
    monkeypatch.setattr(settings, "database_url", os.environ["ACCOUNTING_TEST_DATABASE_URL"])
    opening, accounts = tmp_path / "opening.json", tmp_path / "accounts.json"
    async with recovery.ledger.locked_state() as (_, _, statement):
        opening.write_text(statement.model_dump_json())
    accounts.write_text(json.dumps([recovery.account.model_dump(mode="json")]))
    args = SimpleNamespace(command="prepare", opening=opening, accounts=accounts, apply=True)
    pool = recovery.store.pool
    try:
        await run(args)
        await pool.execute(
            "UPDATE execution.paper_accounts SET balances='{}'::jsonb WHERE book_id=$1",
            settings.accounting_book_id,
        )
        await run(args)
        assert (
            json.loads(
                await pool.fetchval(
                    "SELECT balances FROM execution.paper_accounts WHERE book_id=$1",
                    settings.accounting_book_id,
                )
            )
            == {}
        )
        await run(SimpleNamespace(command="status"))
        statement.cash[0].amount = Decimal(999)
        opening.write_text(statement.model_dump_json())
        with pytest.raises(ValueError, match="never reseeds"):
            await run(args)
    finally:
        for table in ("paper_accounts", "books"):
            await pool.execute(
                f"DELETE FROM execution.{table} WHERE book_id=$1", settings.accounting_book_id
            )
        await pool.execute(
            "DELETE FROM accounting.books WHERE book_id=$1", settings.accounting_book_id
        )
