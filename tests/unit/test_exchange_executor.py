"""Unit tests for the ExchangeExecutor.

Focus: pure logic that doesn't require a real exchange connection. The
network-touching paths (place_order, fetch_order) are mocked.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from agents.tier5_execution.exchange_executor import (
    ExchangeExecutor,
    _SUPPORTED_EXCHANGES,
    _TERMINAL_STATUSES,
)
from core.data.models import (
    AssetClass,
    Exchange,
    Fill,
    KafkaTopic,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


def _order(
    exchange: Exchange = Exchange.BINANCE,
    order_type: OrderType = OrderType.MARKET,
    price: Decimal | None = None,
) -> Order:
    return Order(
        order_id=uuid4(),
        client_order_id=uuid4(),
        symbol="BTC/USDT",
        exchange=exchange,
        side=OrderSide.BUY,
        order_type=order_type,
        size=Decimal("0.01"),
        price=price,
        strategy_id="test_strategy",
        agent_id=12,
    )


def _build_executor() -> ExchangeExecutor:
    """Construct an executor with stubbed Kafka producer + Redis state."""
    ex = ExchangeExecutor()
    # Replace producer with a no-op mock so .publish() doesn't actually emit.
    ex.producer = MagicMock()
    ex.producer.send = AsyncMock()
    # Stub state methods used in the placement path.
    ex.state = MagicMock()
    ex.state.lock = MagicMock()
    ex.state.get_json = AsyncMock(return_value=None)
    ex.state.set_json = AsyncMock()
    ex.state.is_already_processed = AsyncMock(return_value=False)
    ex.state.is_kill_switch_active = AsyncMock(return_value=False)
    return ex


@pytest.mark.unit
def test_supported_exchanges_match_connector_capabilities():
    """The executor's supported list must be a subset of what the connector knows."""
    expected = {Exchange.BINANCE, Exchange.BYBIT, Exchange.COINBASE, Exchange.KRAKEN}
    assert set(_SUPPORTED_EXCHANGES) == expected


@pytest.mark.unit
def test_terminal_statuses_set():
    assert OrderStatus.FILLED in _TERMINAL_STATUSES
    assert OrderStatus.CANCELLED in _TERMINAL_STATUSES
    assert OrderStatus.REJECTED in _TERMINAL_STATUSES
    assert OrderStatus.EXPIRED in _TERMINAL_STATUSES
    assert OrderStatus.OPEN not in _TERMINAL_STATUSES
    assert OrderStatus.PENDING not in _TERMINAL_STATUSES


@pytest.mark.unit
def test_agent_id_in_tier5_metrics_port_window():
    """AGENT_ID must be unique within tier 5 (20-26 range used now)."""
    assert ExchangeExecutor.AGENT_ID == 26
    # Metrics port = 9200 + agent_id → must not collide with siblings
    used_ids = {20, 22, 23, 24, 25, 26}  # router, slippage, hedge, fee, liq, executor
    assert ExchangeExecutor.AGENT_ID in used_ids


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reject_unsupported_exchange():
    ex = _build_executor()
    ex.publish = AsyncMock()
    # Bybit is supported, fake one that isn't (Alpaca)
    bad_order = _order(exchange=Exchange.ALPACA)
    placed_ok = await ex._place_order(bad_order)
    assert placed_ok is False
    # Two publishes: ORDERS_EXECUTED (rejected) + RISK_ALERTS
    assert ex.publish.await_count == 2
    topics = [call.kwargs.get("topic") or call.args[0] for call in ex.publish.await_args_list]
    assert KafkaTopic.ORDERS_EXECUTED in topics
    assert KafkaTopic.RISK_ALERTS in topics
    assert ex._rejected_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reject_limit_without_price():
    ex = _build_executor()
    ex.publish = AsyncMock()
    # Inject a fake connector so the exchange lookup succeeds
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=MagicMock())
    bad_order = _order(order_type=OrderType.LIMIT, price=None)
    placed_ok = await ex._place_order(bad_order)
    assert placed_ok is False
    assert ex._rejected_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_market_order_path_calls_market_placement():
    ex = _build_executor()
    ex.publish = AsyncMock()

    fake_connector = MagicMock()
    fake_connector.place_market_order = AsyncMock(return_value=Order(
        order_id=uuid4(),
        client_order_id=uuid4(),
        exchange_order_id="EX-12345",
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        filled_size=Decimal("0.01"),
        avg_fill_price=Decimal("45100"),
        status=OrderStatus.FILLED,
        strategy_id="test",
        agent_id=12,
    ))
    fake_connector.fetch_trades = AsyncMock(return_value=[])
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_connector)

    order = _order(order_type=OrderType.MARKET)
    placed_ok = await ex._place_order(order)
    assert placed_ok is True
    fake_connector.place_market_order.assert_awaited_once()
    fake_connector.place_limit_order = AsyncMock()
    fake_connector.place_limit_order.assert_not_awaited()
    assert ex._placed_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_limit_order_path_calls_limit_placement():
    ex = _build_executor()
    ex.publish = AsyncMock()

    fake_connector = MagicMock()
    fake_connector.place_limit_order = AsyncMock(return_value=Order(
        order_id=uuid4(),
        client_order_id=uuid4(),
        exchange_order_id="EX-67890",
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
    ))
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_connector)

    order = _order(order_type=OrderType.LIMIT, price=Decimal("45000"))
    placed_ok = await ex._place_order(order)
    assert placed_ok is True
    # Open order → goes into tracking dict for fill polling
    assert "EX-67890" in ex._tracked_orders


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fill_publication_dedup():
    ex = _build_executor()
    ex.publish = AsyncMock()

    fake_connector = MagicMock()
    fill = Fill(
        order_id=uuid4(),  # placeholder from connector
        exchange_order_id="EX-FILL-1",
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        fill_size=Decimal("0.01"),
        fill_price=Decimal("45100"),
        fee=Decimal("0.5"),
        fee_currency="USDT",
        timestamp=datetime.utcnow(),
    )
    fake_connector.fetch_trades = AsyncMock(return_value=[fill])
    ex._connector = MagicMock()
    ex._connector.get = MagicMock(return_value=fake_connector)

    order = _order(order_type=OrderType.MARKET)
    order = order.model_copy(update={"exchange_order_id": "EX-FILL-1"})

    # First call → publishes
    await ex._fetch_and_publish_fills(order)
    first_calls = ex.publish.await_count
    assert ex._fills_published == 1

    # Second call with dedup hit (mock returns True for is_already_processed)
    ex.state.is_already_processed = AsyncMock(return_value=True)
    await ex._fetch_and_publish_fills(order)
    # No new publishes
    assert ex.publish.await_count == first_calls
    assert ex._fills_published == 1
