"""Unit tests for ExchangeExecutor kill-switch cancellation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agents.tier5_execution.exchange_executor import ExchangeExecutor
from core.data.models import (
    Exchange,
    KafkaTopic,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


def _open_order(exchange: Exchange = Exchange.BINANCE, ex_id: str = "EX-1") -> Order:
    return Order(
        order_id=uuid4(),
        client_order_id=uuid4(),
        exchange_order_id=ex_id,
        symbol="BTC/USDT",
        exchange=exchange,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.01"),
        price=Decimal("45000"),
        status=OrderStatus.OPEN,
        strategy_id="test",
        agent_id=12,
    )


def _build_executor() -> ExchangeExecutor:
    ex = ExchangeExecutor()
    ex.publish = AsyncMock()
    ex.state = MagicMock()
    return ex


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_all_no_tracked_orders_is_noop():
    ex = _build_executor()
    ex._connector = MagicMock()
    await ex._cancel_all_tracked_orders(reason="test")
    # Nothing to cancel → no publishes, no connector calls.
    ex.publish.assert_not_awaited()
    assert ex._cancelled_by_kill_switch == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_all_calls_connector_for_each_tracked():
    ex = _build_executor()

    fake_connector = MagicMock()
    fake_connector.cancel_order = AsyncMock(return_value=True)
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_connector)

    o1 = _open_order(ex_id="EX-A")
    o2 = _open_order(ex_id="EX-B")
    ex._tracked_orders = {
        "EX-A": (o1, datetime.utcnow()),
        "EX-B": (o2, datetime.utcnow()),
    }

    await ex._cancel_all_tracked_orders(reason="weekly_drawdown_halt")

    assert fake_connector.cancel_order.await_count == 2
    fake_connector.cancel_order.assert_any_await("EX-A", "BTC/USDT")
    fake_connector.cancel_order.assert_any_await("EX-B", "BTC/USDT")
    # Both successful → tracked dict empty, two cancellation events published.
    assert ex._cancelled_by_kill_switch == 2
    assert ex._tracked_orders == {}
    assert ex.publish.await_count == 2
    # Each publish targets ORDERS_EXECUTED with the kill-switch message type.
    for call in ex.publish.await_args_list:
        kwargs = call.kwargs
        assert (kwargs.get("topic") or call.args[0]) == KafkaTopic.ORDERS_EXECUTED
        assert kwargs["message_type"] == "OrderCancelledByKillSwitch"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_all_keeps_tracked_when_cancel_fails():
    """If cancel_order returns False, the order stays tracked for later retry."""
    ex = _build_executor()

    fake_connector = MagicMock()
    fake_connector.cancel_order = AsyncMock(return_value=False)
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_connector)

    o = _open_order(ex_id="EX-FAIL")
    ex._tracked_orders = {"EX-FAIL": (o, datetime.utcnow())}

    await ex._cancel_all_tracked_orders(reason="test")

    assert ex._cancelled_by_kill_switch == 0
    assert "EX-FAIL" in ex._tracked_orders
    ex.publish.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_all_handles_connector_exception():
    ex = _build_executor()

    fake_connector = MagicMock()
    fake_connector.cancel_order = AsyncMock(side_effect=RuntimeError("network down"))
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_connector)

    o = _open_order(ex_id="EX-NET")
    ex._tracked_orders = {"EX-NET": (o, datetime.utcnow())}

    # Must not raise
    await ex._cancel_all_tracked_orders(reason="test")

    # Order remains tracked since cancel raised.
    assert "EX-NET" in ex._tracked_orders
    assert ex._cancelled_by_kill_switch == 0


@pytest.mark.unit
def test_kill_event_types_set_includes_both_signals():
    ex = ExchangeExecutor()
    assert "KillSwitchEvent" in ex._kill_event_types
    assert "HaltAllStrategies" in ex._kill_event_types
    # Plain RiskAlerts must NOT trigger cancellation.
    assert "RiskAlert" not in ex._kill_event_types
    assert "ExecutionRejected" not in ex._kill_event_types
