"""Fill adapters, cache readiness, and accounting lifecycle boundaries."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agents.tier2_intelligence.price_publisher import PricePublisher
from agents.tier7_monitoring.portfolio_accountant import PortfolioAccountant
from connectors.exchanges.ccxt_connector import ExchangeConnector
from core.accounting.engine import apply_fill
from core.accounting.models import BookState, CashBalance, OpeningBalances
from core.accounting.valuation import MissingValuationError
from core.data.models import Exchange, Fill, OrderSide
from core.orchestrator.message_bus import AlghrestConsumer
from core.orchestrator.state_manager import StateManager

pytestmark = pytest.mark.unit


def trade(**changes):
    return {
        "id": "venue-trade-123",
        "order": "venue-order-1",
        "side": "buy",
        "amount": "0.1",
        "price": "100.123456789",
        "timestamp": 1767614400000,
        "fee": {"currency": "USD", "cost": "0.01"},
        **changes,
    }


@pytest.mark.asyncio
async def test_connector_preserves_stable_identity_and_all_fees():
    connector = ExchangeConnector(Exchange.BINANCE, account_id="desk-2")
    connector._client = SimpleNamespace(
        fetch_my_trades=AsyncMock(
            return_value=[
                trade(
                    fees=[
                        {"currency": "USD", "cost": "0.01"},
                        {"currency": "BNB", "cost": "-0.0001"},
                    ]
                )
            ]
        )
    )
    first = (await connector.fetch_trades("BTC/USD"))[0]
    second = (await connector.fetch_trades("BTC/USD"))[0]
    assert first.fill_id == second.fill_id
    assert first.order_id != second.order_id
    assert first.exchange_trade_id == "venue-trade-123"
    assert first.account_id == "desk-2"
    assert first.fill_price == Decimal("100.123456789")
    assert [(fee.currency, fee.amount) for fee in first.fees] == [
        ("USD", Decimal("0.01")),
        ("BNB", Decimal("-0.0001")),
    ]
    other_market = (await connector.fetch_trades("ETH/USD"))[0]
    assert first.fill_id != other_market.fill_id


@pytest.mark.parametrize(
    "changes", [{"id": None}, {"timestamp": None}, {"fee": None}, {"fee": None, "fees": []}]
)
@pytest.mark.asyncio
async def test_connector_does_not_silently_drop_an_unbookable_fill(changes):
    connector = ExchangeConnector(Exchange.BINANCE)
    connector._client = SimpleNamespace(fetch_my_trades=AsyncMock(return_value=[trade(**changes)]))
    with pytest.raises(ValueError, match="normalize exchange fill"):
        await connector.fetch_trades("BTC/USD")


@pytest.mark.asyncio
async def test_empty_ccxt_fee_list_does_not_discard_known_primary_fee():
    connector = ExchangeConnector(Exchange.BINANCE)
    connector._client = SimpleNamespace(fetch_my_trades=AsyncMock(return_value=[trade(fees=[])]))
    fills = await connector.fetch_trades("BTC/USD")
    assert fills[0].fees[0].amount == Decimal("0.01")


def accountant():
    agent = PortfolioAccountant()
    opening = OpeningBalances(
        as_of=datetime.now(UTC) - timedelta(days=1),
        reference="test",
        cash=[CashBalance(exchange=Exchange.BINANCE, currency="USD", amount=Decimal(1000))],
    )
    book = BookState.from_opening(opening)

    @asynccontextmanager
    async def locked_state():
        yield SimpleNamespace(
            fetchval=AsyncMock(return_value=None), execute=AsyncMock()
        ), book, opening

    agent.ledger = SimpleNamespace(
        book_id="test",
        check_writer=AsyncMock(),
        locked_state=locked_state,
        pnl_since=AsyncMock(return_value=[]),
        record=AsyncMock(),
    )
    agent.consumer = SimpleNamespace(caught_up=AsyncMock(return_value=True), process=AsyncMock())
    agent.state = SimpleNamespace(
        invalidate_portfolio=AsyncMock(),
        set_accounting_portfolio=AsyncMock(),
        get_json=AsyncMock(return_value=None),
        is_kill_switch_active=AsyncMock(return_value=True),
    )
    agent.publish = AsyncMock()
    return agent, book


@pytest.mark.asyncio
async def test_startup_replay_withholds_cache_until_caught_up():
    agent, _ = accountant()
    agent.consumer.caught_up.return_value = False
    assert not await agent.snapshot()
    agent.state.invalidate_portfolio.assert_awaited_once()
    agent.state.set_accounting_portfolio.assert_not_awaited()
    agent.consumer.caught_up.return_value = True
    assert await agent.snapshot()
    assert agent.state.set_accounting_portfolio.await_args.args[0].total_capital == 1000


@pytest.mark.asyncio
async def test_initialize_requires_opening_then_starts_earliest_consumer(monkeypatch):
    from core.accounting.repository import Ledger

    agent, _ = accountant()
    ledger = SimpleNamespace(claim_writer=AsyncMock(), load=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(Ledger, "connect", AsyncMock(return_value=ledger))
    consumer = SimpleNamespace(group_id="test", initialize=AsyncMock(), shutdown=AsyncMock())
    agent.make_consumer = MagicMock(return_value=consumer)
    await agent.initialize()
    ledger.load.assert_awaited_once()
    assert agent.make_consumer.call_args.kwargs["auto_offset_reset"] == "earliest"
    consumer.initialize.assert_awaited_once()
    await agent.shutdown()
    ledger.close.assert_awaited_once()
    consumer.shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_writer_claim_does_not_clear_another_accountants_cache(monkeypatch):
    from core.accounting.repository import Ledger

    agent, _ = accountant()
    ledger = SimpleNamespace(
        claim_writer=AsyncMock(side_effect=RuntimeError("already owned")), close=AsyncMock()
    )
    monkeypatch.setattr(Ledger, "connect", AsyncMock(return_value=ledger))
    agent.consumer = None
    with pytest.raises(RuntimeError, match="already owned"):
        await agent.initialize()
    await agent.shutdown()
    agent.state.invalidate_portfolio.assert_not_awaited()
    ledger.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_fill_accounting_continues_while_trading_is_halted():
    agent, _ = accountant()
    fill = Fill(
        accounting_book_id="test",
        exchange_trade_id="one",
        order_id=uuid4(),
        exchange_order_id="o",
        symbol="BTC/USD",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        fill_size=Decimal(1),
        fill_price=Decimal(100),
        timestamp=datetime.now(UTC),
        fees=[],
    )
    await agent.handle_fill({"message_type": "Fill", "payload": fill.model_dump(mode="json")})
    agent.ledger.record.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_mark_invalidates_old_portfolio_and_redis_failure_propagates():
    agent, book = accountant()
    apply_fill(
        book,
        Fill(
            exchange_trade_id="one",
            order_id=uuid4(),
            exchange_order_id="o",
            symbol="BTC/USD",
            exchange=Exchange.BINANCE,
            side=OrderSide.BUY,
            fill_size=Decimal(1),
            fill_price=Decimal(100),
            timestamp=datetime.now(UTC),
            fees=[],
        ),
    )
    with pytest.raises(MissingValuationError):
        await agent.snapshot()
    agent.state.set_accounting_portfolio.assert_not_awaited()
    agent.state.get_json.return_value = {"price": "110", "timestamp": datetime.now(UTC).isoformat()}
    agent.state.set_accounting_portfolio.side_effect = RuntimeError("Redis unavailable")
    with pytest.raises(RuntimeError, match="Redis unavailable"):
        await agent.snapshot()
    agent.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_snapshot_loop_clears_cache_on_stale_valuation(monkeypatch):
    agent, _ = accountant()
    agent.snapshot = AsyncMock(side_effect=MissingValuationError("stale"))
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        await agent._snapshots()
    agent.state.invalidate_portfolio.assert_awaited_once()


@pytest.mark.asyncio
async def test_processing_failure_cancels_snapshots_and_invalidates_cache():
    agent, _ = accountant()
    agent.consumer.process.side_effect = RuntimeError("conflicting fill")

    # Use a real blocking coroutine so TaskGroup cancellation is exercised.
    async def wait():
        await asyncio.Event().wait()

    agent._snapshots = wait
    with pytest.raises(ExceptionGroup):
        await agent.run()
    agent.state.invalidate_portfolio.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_expires_quickly_if_process_dies():
    agent, _ = accountant()
    await agent.snapshot()
    portfolio = agent.state.set_accounting_portfolio.await_args.args[0]
    state = StateManager()
    state._redis = SimpleNamespace(set=AsyncMock())
    await state.set_accounting_portfolio(portfolio)
    assert state._redis.set.await_args.kwargs["ex"] == 15


@pytest.mark.asyncio
async def test_accounting_marks_do_not_merge_venues_or_refresh_old_price_time():
    publisher = PricePublisher()
    publisher.state = SimpleNamespace(set_accounting_mark=AsyncMock())
    moment = datetime.now(UTC)
    await publisher._write_accounting_mark("binance", "BTC/USD", Decimal("100.000000001"), moment)
    await publisher._write_accounting_mark("kraken", "BTC/USD", Decimal("99.123456789"), moment)
    calls = publisher.state.set_accounting_mark.await_args_list
    assert calls[0].args[:4] == ("binance", "BTC/USD", "100.000000001", moment.isoformat())
    assert calls[1].args[:3] == ("kraken", "BTC/USD", "99.123456789")


@pytest.mark.asyncio
async def test_readiness_requires_assignment_and_durable_offsets():
    consumer = AlghrestConsumer("accountant", [])
    partition = "partition"
    consumer._consumer = SimpleNamespace(
        assignment=MagicMock(return_value=set()),
        end_offsets=AsyncMock(return_value={partition: 10}),
        committed=AsyncMock(return_value=9),
    )
    assert not await consumer.caught_up()
    consumer._consumer.assignment.return_value = {partition}
    assert not await consumer.caught_up()
    consumer._consumer.committed.return_value = 10
    assert await consumer.caught_up()
    consumer._consumer.end_offsets.side_effect = RuntimeError("broker down")
    with pytest.raises(RuntimeError, match="broker down"):
        await consumer.caught_up()
