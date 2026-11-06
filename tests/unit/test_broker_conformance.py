"""External broker sandbox conformance tests for TWAP, emergency flatten, and synthetic book parity."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from connectors.exchanges.conformance import (
    BrokerConformanceSuite,
    build_sandbox_adapter,
)
from core.data.models import Exchange, Order, OrderSide, OrderStatus, OrderType
from core.execution.contracts import (
    AccountScope,
    InstrumentRules,
    OrderConflictError,
    RecoveryBlockedError,
)

pytestmark = pytest.mark.unit

SUPPORTED_VENUES = (
    Exchange.BINANCE,
    Exchange.BYBIT,
    Exchange.COINBASE,
    Exchange.KRAKEN,
)


def _scope(exchange: Exchange) -> AccountScope:
    return AccountScope(
        exchange=exchange,
        account_id="default",
        symbols=["BTC/USDT"],
        market_rules={
            "BTC/USDT": InstrumentRules(
                tick_size=Decimal("0.01"),
                quantity_step=Decimal("0.01"),
                min_quantity=Decimal("0.01"),
                min_notional=Decimal("10"),
            )
        },
    )


@pytest.mark.parametrize("exchange", SUPPORTED_VENUES)
async def test_external_sandbox_twap_and_flatten_matches_synthetic_book(
    exchange: Exchange,
) -> None:
    initial = {"USDT": Decimal("10000"), "BTC": Decimal("0")}
    mark = Decimal("50000")
    adapter, _sandbox = build_sandbox_adapter(
        exchange,
        initial_balances=initial,
        mark_prices={"BTC/USDT": mark},
        fee_bps=Decimal("10"),
    )
    scope = _scope(exchange)
    suite = BrokerConformanceSuite(
        adapter,
        scope=scope,
        opening_balances=initial,
    )

    twap_parent = Order(
        accounting_book_id=suite.book_id,
        authorization_id=uuid4(),
        symbol="BTC/USDT",
        exchange=exchange,
        account_id="default",
        side=OrderSide.BUY,
        order_type=OrderType.TWAP,
        size=Decimal("0.12"),
        price=Decimal("50000"),
        strategy_id="twap_conformance",
        agent_id=22,
        algo_params={"num_slices": 3, "slice_interval_seconds": 1},
    )
    resting_limit = Order(
        accounting_book_id=suite.book_id,
        authorization_id=uuid4(),
        symbol="BTC/USDT",
        exchange=exchange,
        account_id="default",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.02"),
        price=Decimal("40000"),  # Below mark -> rests OPEN on the book
        strategy_id="resting_limit",
        agent_id=12,
    )
    flatten_op_id = uuid4()

    report = await suite.run_full_conformance(
        twap_parent=twap_parent,
        mark_price=mark,
        resting_limit_order=resting_limit,
        flatten_operation_id=flatten_op_id,
    )

    assert report.twap_slices_executed == 3
    assert report.twap_total_filled == Decimal("0.12")
    assert report.resting_orders_cancelled == 1
    assert report.flatten_orders_executed == 1
    assert report.fills_reconciled == 4  # 3 TWAP slice fills + 1 emergency flatten fill
    assert report.flat is True
    assert report.balance_differences == {}
    assert report.broker_balances["BTC"] == Decimal("0")
    # 0.12 BTC @ 50,000 = 6,000 USDT notional; 10 bps fee on buy (6 USDT) + 10 bps fee on sell (6 USDT) = 9,988 USDT
    assert report.broker_balances["USDT"] == Decimal("9988")
    assert report.synthetic_book_balances["USDT"] == Decimal("9988")


@pytest.mark.parametrize("exchange", SUPPORTED_VENUES)
async def test_external_sandbox_duplicate_flatten_and_client_id_idempotency(
    exchange: Exchange,
) -> None:
    initial = {"USDT": Decimal("5000"), "BTC": Decimal("0.05")}
    mark = Decimal("50000")
    adapter, _sandbox = build_sandbox_adapter(
        exchange,
        initial_balances=initial,
        mark_prices={"BTC/USDT": mark},
        fee_bps=Decimal("10"),
    )
    scope = _scope(exchange)
    op_id = uuid4()

    first = await adapter.flatten(
        op_id,
        symbols=["BTC/USDT"],
        market_rules=scope.market_rules,
        reference_prices={"BTC/USDT": mark},
        halted=True,
        book_id="paper_trading:conformance",
    )
    assert first["flat"] is True
    assert len(first["orders"]) == 1

    # Repeating flatten with the same operation_id must be idempotent and never oversell
    second = await adapter.flatten(
        op_id,
        symbols=["BTC/USDT"],
        market_rules=scope.market_rules,
        reference_prices={"BTC/USDT": mark},
        halted=True,
        book_id="paper_trading:conformance",
    )
    assert second["flat"] is True
    assert second["orders"] == first["orders"]
    assert (await adapter.balances())["BTC"] == Decimal("0")

    # Reusing a client_order_id with altered size must raise OrderConflictError
    fixed_id = uuid4()
    order_a = Order(
        client_order_id=fixed_id,
        symbol="BTC/USDT",
        exchange=exchange,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        strategy_id="idempotency_test",
        agent_id=12,
    )
    placed_a = await adapter.place(order_a)
    assert placed_a.status == OrderStatus.FILLED

    order_b = order_a.model_copy(update={"size": Decimal("0.02")})
    with pytest.raises(OrderConflictError):
        await adapter.place(order_b)


async def test_external_sandbox_flatten_safety_gates() -> None:
    initial = {"USDT": Decimal("5000"), "BTC": Decimal("0.05")}
    mark = Decimal("50000")
    adapter, sandbox = build_sandbox_adapter(
        Exchange.BINANCE,
        initial_balances=initial,
        mark_prices={"BTC/USDT": mark},
    )
    scope = _scope(Exchange.BINANCE)

    # 1. Flatten without active halt is blocked
    with pytest.raises(RecoveryBlockedError, match="persistent halt"):
        await adapter.flatten(
            uuid4(),
            symbols=["BTC/USDT"],
            market_rules=scope.market_rules,
            halted=False,
        )

    # 2. Unconfirmed pending order cancellation blocks flatten before touching inventory
    resting = Order(
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.01"),
        price=Decimal("40000"),
        strategy_id="resting",
        agent_id=12,
    )
    await adapter.place(resting)
    sandbox.block_cancellation = True
    with pytest.raises(RecoveryBlockedError, match="cancellation is not confirmed"):
        await adapter.flatten(
            uuid4(),
            symbols=["BTC/USDT"],
            market_rules=scope.market_rules,
            halted=True,
        )
    assert (await adapter.balances())["BTC"] == Decimal("0.05")
