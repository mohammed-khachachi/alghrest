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
    InstrumentRules,
    OrderConflictError,
    RecoveryBlockedError,
    TradePage,
)
from core.execution.recovery import RecoveryCoordinator
from core.execution.store import ExecutionStore, order_fingerprint
from tests.execution_authorization import authorized_order
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
async def recovery(monkeypatch):
    dsn = os.getenv("ACCOUNTING_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set ACCOUNTING_TEST_DATABASE_URL to a disposable test database")
    from core.config import settings

    monkeypatch.setattr(settings, "accounting_book", f"execution-test-{uuid4()}")
    ledger = await Ledger.connect(dsn, settings.accounting_book_id)
    root = Path(__file__).resolve().parents[2]
    for migration in (
        "001_accounting.sql",
        "002_execution_recovery.sql",
        "003_funding_performance.sql",
        "005_risk_halts.sql",
        "006_twap_plans.sql",
        "007_execution_authorizations.sql",
        "008_global_risk_halt.sql",
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
    account = AccountScope(
        exchange=Exchange.BINANCE,
        symbols=["BTC/USD"],
        market_rules={
            "BTC/USD": InstrumentRules(
                tick_size="0.01",
                quantity_step="0.000001",
                min_quantity="0.000001",
                min_notional="0.01",
            )
        },
    )
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
            "authorization_denials",
            "authorizations",
            "slices",
            "plans",
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


async def test_replayed_approval_concurrently_claims_one_durable_intent_after_restart(
    recovery, monkeypatch
):
    from core.config import settings
    from core.data.models import TradeProposalStatus
    from tests.factories import proposal
    from tests.unit.test_execution_intent_identity import route_approval

    r = recovery
    monkeypatch.setattr(settings, "execution_accounts", [r.account])
    approved = proposal(
        symbol="BTC/USD", size="1", size_usd="100", status=TradeProposalStatus.APPROVED
    )
    await ready(r)
    from core.data.models import TradeProposalReview
    from core.execution.authorization import ApprovalStore

    approvals = ApprovalStore(r.ledger)
    await approvals.decide(
        approved,
        TradeProposalReview(
            accounting_book_id=r.store.book_id,
            proposal_id=approved.proposal_id,
            reviewer_agent_id=3,
            decision=TradeProposalStatus.APPROVED,
            reason="explicit concurrent approval fixture",
            risk_score=0.1,
        ),
        revision=0,
    )
    # Independent router objects model concurrent delivery and router restart.
    copies = await asyncio.gather(*(route_approval(approved, approvals) for _ in range(8)))
    await ready(r)
    assert sum(await asyncio.gather(*(r.store.prepare(o) for o in copies))) == 1
    placed = await r.paper.place(copies[0])
    await r.store.observe(copies[0], placed)
    await r.coordinator.run_once()
    await ready(r)
    restarted = ExecutionStore(
        await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], r.ledger.book_id)
    )
    try:
        assert await restarted.seen(copies[-1])
        assert not await restarted.prepare(copies[-1])
        page = await r.paper.history_page("BTC/USD", 0, 9999999999999, None)
        assert len(page.fills) == 1
    finally:
        await restarted.close()


async def test_historical_random_id_blocks_replayed_proposal_without_rewriting_history(recovery):
    from core.execution.twap import TwapScheduler

    r = recovery
    await ready(r)
    original = order(proposal_id=uuid4())
    # Preserve an actual pre-authorization journal shape rather than using the
    # new admission interface to fabricate a legacy permission.
    await r.store.pool.execute(
        """INSERT INTO execution.orders
           (book_id,client_order_id,exchange,account_id,fingerprint,request,current_order,phase)
           VALUES($1,$2,$3,$4,$5,$6::jsonb,$6::jsonb,'submitting')""",
        r.store.book_id,
        original.client_order_id,
        original.exchange.value,
        original.account_id,
        order_fingerprint(original),
        original.model_dump_json(),
    )
    await r.store.observe(original, await r.paper.place(original))
    await r.coordinator.run_once()
    await ready(r)
    replay = await authorized_order(r.store, original)
    with pytest.raises(RecoveryBlockedError, match="proposal.*historical"):
        await r.store.prepare(replay)
    parent = replay.model_copy(update={"order_type": OrderType.TWAP})
    with pytest.raises(RecoveryBlockedError, match="authorization"):
        await TwapScheduler(r.store, r.state).start(parent)
    assert await r.store.seen(original)
    assert not await r.store.seen(replay)
    retained = await r.store.pool.fetchval(
        "SELECT request FROM execution.orders WHERE book_id=$1 AND client_order_id=$2",
        r.store.book_id,
        original.client_order_id,
    )
    assert Order.model_validate_json(retained) == original
    page = await r.paper.history_page("BTC/USD", 0, 9999999999999, None)
    assert len(page.fills) == 1


async def test_durable_halt_blocks_new_risk_and_reconciliation_until_authorized_reset(
    recovery, monkeypatch
):
    from pydantic import SecretStr

    from core.config import settings
    from core.risk.halt import RiskHaltStore

    r = recovery
    await ready(r)
    waiting = await authorized_order(r.store, order())
    halt = RiskHaltStore(r.store.pool, r.ledger.book_id)
    await halt.activate("weekly_drawdown_halt", actor="RiskGovernor")
    restarted = await Ledger.connect(os.environ["ACCOUNTING_TEST_DATABASE_URL"], r.ledger.book_id)
    try:
        fresh = RiskHaltStore(restarted.pool, r.ledger.book_id)
        status = await fresh.status()
        assert status["active"]
        with pytest.raises(RecoveryBlockedError, match="halt"):
            await r.paper.place(order())
        with pytest.raises(RecoveryBlockedError, match="halt"):
            await r.store.prepare(waiting)
        assert not (await r.coordinator.run_once())["ready"]
        monkeypatch.setattr(settings, "risk_reset_token", SecretStr("isolated-test-operator"))
        with pytest.raises(PermissionError):
            await fresh.reset(
                actor="operator",
                reason="reviewed",
                authorization="wrong",
                expected_generation=status["generation"],
            )
        await halt.activate("newer emergency")
        with pytest.raises(RuntimeError, match="generation"):
            await fresh.reset(
                actor="operator",
                reason="stale review",
                authorization="isolated-test-operator",
                expected_generation=status["generation"],
            )
        current = await fresh.status()
        await fresh.reset(
            actor="operator",
            reason="reconciled paper book",
            authorization="isolated-test-operator",
            expected_generation=current["generation"],
        )
        assert not (await fresh.status())["active"]
        assert (
            await r.store.pool.fetchval(
                "SELECT count(*) FROM safety.halt_events WHERE book_id=$1 AND active=false",
                r.ledger.book_id,
            )
            == 1
        )
        await ready(r)
    finally:
        await restarted.close()


async def test_paper_entry_installs_protection_and_stop_closes_without_reversal(recovery):
    r = recovery
    protected = order(stop_price=Decimal("90"))
    await r.paper.place(protected)
    stops = [o for o in await r.paper.open_orders() if o.order_type == OrderType.STOP]
    assert len(stops) == 1
    assert stops[0].size == Decimal(1)
    r.state.get_json.side_effect = lambda _: {
        "price": "89",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await r.paper.maintain_protection()
    assert (await r.paper.balances())["BTC"] == 0
    assert not await r.paper.open_orders()
    await r.paper.maintain_protection()
    assert (await r.paper.balances())["BTC"] == 0


async def test_partial_entry_resizes_protection_atomically_and_survives_broker_restart(recovery):
    r = recovery
    paper = PaperVenue(r.store, r.account, r.state, max_fill_size=Decimal("0.4"))
    await paper.initialize()
    entry = order(stop_price=Decimal("90"))
    first = await paper.place(entry)
    assert first.status == OrderStatus.OPEN and first.filled_size == Decimal("0.4")
    stops = await paper.open_orders()
    protective = [o for o in stops if o.order_type == OrderType.STOP]
    assert len(protective) == 1 and protective[0].size == first.filled_size
    second = await paper.lookup(entry)
    assert second.status == OrderStatus.OPEN and second.filled_size == Decimal("0.8")
    protective = [o for o in await paper.open_orders() if o.order_type == OrderType.STOP]
    assert len(protective) == 1 and protective[0].size == second.filled_size

    restarted = PaperVenue(r.store, r.account, r.state, max_fill_size=Decimal("0.4"))
    await restarted.initialize()
    final = await restarted.lookup(entry)
    assert final.status == OrderStatus.FILLED and final.filled_size == entry.size
    protective = [o for o in await restarted.open_orders() if o.order_type == OrderType.STOP]
    assert len(protective) == 1 and protective[0].size == entry.size
    page = await restarted.history_page("BTC/USD", 0, 9999999999999, None)
    assert [f.fill_size for f in page.fills] == [Decimal("0.4"), Decimal("0.4"), Decimal("0.2")]
    assert len({f.exchange_trade_id for f in page.fills}) == 3
    assert final.fees == sum(f.fee for f in page.fills)
    assert (await restarted.balances())["BTC"] == entry.size


@pytest.mark.parametrize("entry_lookup_first", [True, False])
async def test_stop_during_partial_entry_cancels_unfilled_remainder_without_reopening(
    recovery, entry_lookup_first
):
    r = recovery
    paper = PaperVenue(r.store, r.account, r.state, max_fill_size=Decimal("0.4"))
    await paper.initialize()
    entry = order(stop_price=Decimal("90"))
    assert (await paper.place(entry)).filled_size == Decimal("0.4")
    r.state.get_json.side_effect = lambda _: {
        "price": "89",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    if entry_lookup_first:
        assert (await paper.lookup(entry)).status == OrderStatus.CANCELLED
    await paper.maintain_protection()
    observed = await paper.lookup(entry)
    assert observed.status == OrderStatus.CANCELLED
    assert observed.filled_size == Decimal("0.4")
    assert (await paper.balances())["BTC"] == 0
    assert not await paper.open_orders()
    await paper.maintain_protection()
    assert (await paper.lookup(entry)).filled_size == Decimal("0.4")
    page = await paper.history_page("BTC/USD", 0, 9999999999999, None)
    assert [(f.side, f.fill_size) for f in page.fills] == [
        (OrderSide.BUY, Decimal("0.4")),
        (OrderSide.SELL, Decimal("0.4")),
    ]


async def test_cancel_is_not_flat_and_concurrent_emergency_closes_cannot_reverse(recovery):
    from core.risk.halt import RiskHaltStore

    r = recovery
    await r.paper.place(order(stop_price=Decimal("90")))
    await r.paper.cancel_pending()
    assert (await r.paper.balances())["BTC"] == 1
    halt = RiskHaltStore(r.store.pool, r.ledger.book_id)
    await halt.activate("emergency")
    operation = uuid4()
    reports = await asyncio.gather(*(r.paper.flatten(operation) for _ in range(4)))
    assert all(report["flat"] for report in reports)
    assert (await r.paper.balances())["BTC"] == 0
    assert (await r.paper.flatten(operation))["flat"]
    page = await r.paper.history_page("BTC/USD", 0, 9999999999999, None)
    assert len(page.fills) == 2


async def test_cancelling_protection_with_partial_exposure_persists_halt(recovery):
    from core.risk.halt import RiskHaltStore

    r = recovery
    await ready(r)
    waiting = await authorized_order(r.store, order())
    paper = PaperVenue(r.store, r.account, r.state, max_fill_size=Decimal("0.4"))
    await paper.initialize()
    entry = order(stop_price=Decimal("90"))
    await paper.place(entry)
    stop = next(o for o in await paper.open_orders() if o.order_type == OrderType.STOP)
    await paper.cancel(stop)
    assert (await RiskHaltStore(r.store.pool, r.store.book_id).status())["active"]
    assert (await paper.lookup(entry)).status == OrderStatus.CANCELLED
    assert (await paper.balances())["BTC"] == Decimal("0.4")
    with pytest.raises(RecoveryBlockedError, match="Persistent risk halt"):
        await r.store.prepare(waiting)


async def test_partial_stop_fills_cannot_reverse_inventory_under_concurrent_matching(recovery):
    r = recovery
    paper = PaperVenue(r.store, r.account, r.state, max_fill_size=Decimal("0.4"))
    await paper.initialize()
    entry = order(stop_price=Decimal("90"))
    await paper.place(entry)
    await paper.lookup(entry)
    await paper.lookup(entry)
    r.state.get_json.side_effect = lambda _: {
        "price": "89",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    await paper.maintain_protection()
    stop = next(o for o in await paper.open_orders() if o.order_type == OrderType.STOP)
    assert stop.filled_size == Decimal("0.4") and stop.size == Decimal(1)
    await asyncio.gather(*(paper.maintain_protection() for _ in range(4)))
    assert (await paper.balances())["BTC"] == 0
    assert not await paper.open_orders()
    page = await paper.history_page("BTC/USD", 0, 9999999999999, None)
    assert sum(f.fill_size for f in page.fills if f.side == OrderSide.SELL) == Decimal(1)
    assert len({f.exchange_trade_id for f in page.fills}) == len(page.fills) == 6


@pytest.mark.parametrize("callers", [1, 4])
async def test_emergency_flatten_reconciles_partial_close_fills_before_reporting_flat(
    recovery, callers
):
    from core.risk.halt import RiskHaltStore

    r = recovery
    paper = PaperVenue(r.store, r.account, r.state, max_fill_size=Decimal("0.4"))
    await paper.initialize()
    entry = order(stop_price=Decimal("90"))
    await paper.place(entry)
    await paper.lookup(entry)
    await paper.lookup(entry)
    await RiskHaltStore(r.store.pool, r.store.book_id).activate("partial close proof")
    operation = uuid4()
    reports = await asyncio.gather(*(paper.flatten(operation) for _ in range(callers)))
    assert all(report["flat"] for report in reports)
    assert (await paper.balances())["BTC"] == 0
    assert (await paper.flatten(operation))["flat"]
    page = await paper.history_page("BTC/USD", 0, 9999999999999, None)
    sells = [f for f in page.fills if f.side == OrderSide.SELL]
    assert [f.fill_size for f in sells] == [Decimal("0.4"), Decimal("0.4"), Decimal("0.2")]
    assert len({f.order_id for f in sells}) == 1


@pytest.mark.parametrize("stop", ["100.001", "110", "0"])
async def test_invalid_protection_never_opens_a_paper_position(recovery, stop):
    with pytest.raises(RecoveryBlockedError):
        await recovery.paper.place(order(stop_price=Decimal(stop)))
    assert (await recovery.paper.balances()).get("BTC", 0) == 0


async def test_halt_cancels_marketable_buy_before_recovery_lookup_can_fill(recovery):
    from core.risk.halt import RiskHaltStore

    r = recovery
    resting = order().model_copy(update={"order_type": OrderType.LIMIT, "price": Decimal(90)})
    assert (await r.paper.place(resting)).status == OrderStatus.OPEN
    await RiskHaltStore(r.store.pool, r.ledger.book_id).activate("weekly")
    r.state.get_json.side_effect = lambda _: {
        "price": "89",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    assert (await r.paper.lookup(resting)).status == OrderStatus.CANCELLED
    assert (await r.paper.balances()).get("BTC", 0) == 0


async def test_twap_serial_priced_children_survive_replay_and_halt(recovery):
    from core.execution.twap import TwapScheduler
    from core.risk.halt import RiskHaltStore

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store,
        order().model_copy(
            update={
                "order_type": OrderType.TWAP,
                "algo_params": {
                    "num_slices": 2,
                    "slice_interval_seconds": 0,
                },
            }
        ),
    )
    scheduler = TwapScheduler(r.store, r.state)
    await asyncio.gather(*(scheduler.start(parent) for _ in range(4)))
    children = await asyncio.gather(*(scheduler.step(parent.client_order_id) for _ in range(4)))
    child = next(c for c in children if c is not None)
    assert sum(c is not None for c in children) == 1
    assert child.price == Decimal(100) and child.size == Decimal("0.5")
    assert await scheduler.step(parent.client_order_id) is None
    assert await r.store.prepare(child)
    await r.store.observe(child, await r.paper.place(child))
    await r.coordinator.run_once()
    await ready(r)
    # Recreated scheduler reads committed plan/slice state, not RAM counters.
    restarted = TwapScheduler(r.store, r.state)
    await restarted.start(parent)
    await RiskHaltStore(r.store.pool, r.ledger.book_id).activate("weekly")
    assert await restarted.step(parent.client_order_id) is None
    assert (await r.paper.balances())["BTC"] == Decimal("0.5")


async def test_twap_completed_quantity_is_bounded_by_parent(recovery):
    from core.execution.twap import TwapScheduler

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store,
        order().model_copy(
            update={
                "order_type": OrderType.TWAP,
                "algo_params": {
                    "num_slices": 3,
                    "slice_interval_seconds": 0,
                },
            }
        ),
    )
    scheduler = TwapScheduler(r.store, r.state)
    await scheduler.start(parent)
    sizes = []
    for _ in range(3):
        child = await scheduler.step(parent.client_order_id)
        assert child is not None
        assert child.price % r.account.market_rules[parent.symbol].tick_size == 0
        sizes.append(child.size)
        assert await r.store.prepare(child)
        await r.store.observe(child, await r.paper.place(child))
        await r.coordinator.run_once()
        await ready(r)
    assert sum(sizes) == parent.size
    assert await scheduler.step(parent.client_order_id) is None
    assert (await r.paper.balances())["BTC"] == parent.size


async def test_twap_rejected_child_stops_plan_without_replacement(recovery):
    from core.execution.twap import TwapScheduler

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store,
        order().model_copy(update={"order_type": OrderType.TWAP, "algo_params": {"num_slices": 2}}),
    )
    scheduler = TwapScheduler(r.store, r.state)
    await scheduler.start(parent)
    child = await scheduler.step(parent.client_order_id)
    await r.store.reject(child, "paper constraint rejection")
    assert await scheduler.step(parent.client_order_id) is None
    assert parent.client_order_id not in await scheduler.active()
    assert (await r.paper.balances()).get("BTC", 0) == 0


@pytest.mark.parametrize("halted", [False, True])
async def test_twap_outbox_waits_for_reconciliation_before_child_delivery(recovery, halted):
    from core.execution.twap import TwapScheduler
    from core.risk.halt import RiskHaltStore

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store,
        order().model_copy(update={"order_type": OrderType.TWAP, "algo_params": {"num_slices": 2}}),
    )
    scheduler = TwapScheduler(r.store, r.state)
    await scheduler.start(parent)
    child = await scheduler.step(parent.client_order_id)
    published = []
    projection = {"ready": False}

    async def cache(report, *_args):
        projection.update(report)

    original_publish = r.coordinator.publish

    async def publish(topic, *, payload, message_type):
        if message_type == "ChildOrder":
            assert projection["ready"], "Child delivered while reconciliation was unavailable"
            delivered = Order.model_validate(payload)
            # Real journal admission must pass, not a bypassed/mocked risk gate.
            assert await r.store.prepare(delivered)
            await r.store.observe(delivered, await r.paper.place(delivered))
            published.append(delivered)
        else:
            await original_publish(topic, payload=payload, message_type=message_type)

    r.state.set_reconciliation.side_effect = cache
    r.coordinator.publish = publish
    if halted:
        await RiskHaltStore(r.store.pool, r.store.book_id).activate("hold queued child")
        r.state.is_kill_switch_active.return_value = True
    await r.coordinator.run_once()
    if halted:
        assert not published
        assert (await r.paper.balances()).get("BTC", 0) == 0
        assert any(e["message_type"] == "ChildOrder" for e in await r.store.outbox())
    else:
        assert [o.client_order_id for o in published] == [child.client_order_id]
        assert (await r.paper.balances())["BTC"] == child.size


async def test_halted_twap_outbox_still_delivers_recovered_fills(recovery):
    from core.execution.twap import TwapScheduler
    from core.risk.halt import RiskHaltStore

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store, order().model_copy(update={"order_type": OrderType.TWAP})
    )
    scheduler = TwapScheduler(r.store, r.state)
    await scheduler.start(parent)
    await scheduler.step(parent.client_order_id)
    saved = await r.store.checkpoint(r.account, "BTC/USD")
    await r.store.capture_page(
        r.account, "BTC/USD", saved["version"], None, saved["through_ms"], [fill()]
    )
    await RiskHaltStore(r.store.pool, r.store.book_id).activate("late fill during halt")
    r.state.is_kill_switch_active.return_value = True
    report = await r.coordinator.run_once()
    assert not report["ready"]
    assert (await r.ledger.load()).revision == 1
    pending = await r.store.outbox()
    assert len(pending) == 1 and pending[0]["message_type"] == "ChildOrder"
    assert pending[0]["delivered_at"] is None


async def test_twap_uncertain_child_reserves_quantity_until_reconciled(recovery):
    from core.execution.twap import TwapScheduler

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store,
        order().model_copy(update={"order_type": OrderType.TWAP, "algo_params": {"num_slices": 2}}),
    )
    scheduler = TwapScheduler(r.store, r.state)
    await scheduler.start(parent)
    child = await scheduler.step(parent.client_order_id)
    assert await r.store.prepare(child)
    await r.store.uncertain(child, "response lost")
    restarted = TwapScheduler(r.store, r.state)
    for _ in range(5):
        assert await restarted.step(parent.client_order_id) is None
    assert not await r.store.prepare(child)
    retained = Order.model_validate_json((await r.store.orders())[0]["current_order"])
    assert retained == child


@pytest.mark.parametrize("partial", [False, True])
async def test_twap_timeout_requests_cancel_and_never_replaces_reserved_child(recovery, partial):
    from core.execution.twap import TwapScheduler

    r = recovery
    await ready(r)
    parent = await authorized_order(
        r.store,
        order().model_copy(update={"order_type": OrderType.TWAP, "algo_params": {"num_slices": 2}}),
    )
    scheduler = TwapScheduler(r.store, r.state)
    await scheduler.start(parent)
    child = await scheduler.step(parent.client_order_id)
    assert child is not None
    assert await r.store.prepare(child)
    if partial:
        await r.store.observe(
            child,
            child.model_copy(
                update={
                    "status": OrderStatus.OPEN,
                    "filled_size": Decimal("0.2"),
                    "exchange_order_id": "partial-timeout-observation",
                }
            ),
        )
    else:
        await r.store.uncertain(child, "broker response unavailable")
    await r.store.pool.execute(
        "UPDATE execution.plans SET next_at=now()-interval '121 seconds' WHERE book_id=$1 AND parent_id=$2",
        r.store.book_id,
        parent.client_order_id,
    )
    assert await scheduler.step(parent.client_order_id) is None
    plan = await r.store.pool.fetchrow(
        "SELECT * FROM execution.plans WHERE book_id=$1 AND parent_id=$2",
        r.store.book_id,
        parent.client_order_id,
    )
    assert plan["state"] == "blocked"
    assert plan["allocated"] == child.size
    assert plan["next_slice"] == 1
    assert (await r.store.orders())[0]["cancel_requested"]
    restarted = TwapScheduler(r.store, r.state)
    for _ in range(3):
        assert await restarted.step(parent.client_order_id) is None
    assert not await r.store.prepare(child)


async def test_lost_response_recovers_without_second_placement_after_restart(recovery):
    r = recovery
    await ready(r)
    intent = await authorized_order(r.store, order())
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
    intent = await authorized_order(r.store, order())
    waiting = await authorized_order(r.store, order())
    assert await r.store.prepare(intent)
    report = await r.coordinator.run_once()
    assert not report["ready"] and any("unresolved submission" in s for s in report["reasons"])
    assert not await r.store.prepare(intent)
    assert await r.paper.lookup(intent) is None
    with pytest.raises(RecoveryBlockedError):
        await r.store.prepare(waiting)


async def test_concurrent_identity_and_atomic_gate(recovery):
    r = recovery
    await ready(r)
    intent = await authorized_order(r.store, order())
    waiting = await authorized_order(r.store, order())
    assert sum(await asyncio.gather(*(r.store.prepare(intent) for _ in range(8)))) == 1
    with pytest.raises(OrderConflictError):
        await r.store.prepare(intent.model_copy(update={"size": Decimal(2)}))
    with pytest.raises(RecoveryBlockedError):
        await r.store.prepare(waiting)
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
    intent = await authorized_order(r.store, order())
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
    intent = await authorized_order(
        r.store, order().model_copy(update={"order_type": OrderType.LIMIT, "price": Decimal(90)})
    )
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
    waiting = await authorized_order(r.store, order())
    await r.ledger.record(fill())
    with pytest.raises(RecoveryBlockedError, match="changed"):
        await r.store.prepare(waiting)


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
    with pytest.raises(RecoveryBlockedError, match="not configured"):
        await authorized_order(r.store, order().model_copy(update={"symbol": "ETH/USD"}))
    waiting = await authorized_order(r.store, order())
    await r.store.pool.execute(
        "UPDATE execution.books SET verified_until=now()-interval '1 second' WHERE book_id=$1",
        r.store.book_id,
    )
    with pytest.raises(RecoveryBlockedError, match="stale"):
        await r.store.prepare(waiting)
    await ready(r)
    intent = await authorized_order(r.store, order())
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
