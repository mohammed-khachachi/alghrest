"""Unscoped and foreign Kafka messages cannot touch the current execution book."""

from unittest.mock import AsyncMock

import pytest

from agents.tier5_execution.exchange_executor import ExchangeExecutor
from core.config import settings
from core.data.models import Exchange, Order, OrderSide, OrderType

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("book_id", [None, "paper_trading:another-book"])
async def test_foreign_or_unscoped_order_cannot_touch_execution_store(book_id):
    order = Order(
        exchange=Exchange.BINANCE,
        symbol="BTC/USD",
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size="1",
        price="100",
        strategy_id="isolated-input",
        agent_id=12,
    )
    payload = {**order.model_dump(mode="json"), "accounting_book_id": book_id}
    executor = ExchangeExecutor()
    executor.store = AsyncMock()
    await executor.handle_order({"payload": payload})
    executor.store.check_writer.assert_not_awaited()
    executor.store.seen.assert_not_awaited()
    executor.store.prepare.assert_not_awaited()
    executor.store.reject.assert_not_awaited()


@pytest.mark.parametrize("payload", [[], None, {"size": "invalid"}])
async def test_malformed_delivery_does_not_stop_order_consumer(payload):
    executor = ExchangeExecutor()
    executor.store = AsyncMock()
    if isinstance(payload, dict):
        payload["accounting_book_id"] = settings.accounting_book_id
    await executor.handle_order({"payload": payload})
    executor.store.prepare.assert_not_awaited()
    executor.store.reject.assert_not_awaited()
