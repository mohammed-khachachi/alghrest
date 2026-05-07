"""Smoke tests: every Pydantic model can be constructed with realistic values."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from core.data.models import (
    AssetClass,
    Exchange,
    Fill,
    KafkaTopic,
    OHLCVBar,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSizingResult,
    SignalDirection,
    Timeframe,
    TradeProposal,
    TradeProposalStatus,
)


@pytest.mark.unit
def test_kafka_topic_enum_includes_new_pipeline_topics():
    assert KafkaTopic.PROPOSALS_APPROVED.value == "proposals.approved"
    assert KafkaTopic.ORDERS_PENDING.value == "orders.pending"
    assert KafkaTopic.PROPOSALS_BUS.value == "proposals.bus"


@pytest.mark.unit
def test_signal_direction_enum_does_not_have_long_short():
    """Regression: old Tier 4 strategies used SignalDirection.LONG/SHORT."""
    assert not hasattr(SignalDirection, "LONG")
    assert not hasattr(SignalDirection, "SHORT")
    assert SignalDirection.BULLISH.value == "BULLISH"
    assert SignalDirection.BEARISH.value == "BEARISH"


@pytest.mark.unit
def test_ohlcv_bar_uses_time_field():
    bar = OHLCVBar(
        time=datetime.utcnow(),
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        timeframe=Timeframe.H4,
        open=Decimal("45000"),
        high=Decimal("46000"),
        low=Decimal("44500"),
        close=Decimal("45500"),
        volume=Decimal("100"),
    )
    assert bar.time is not None
    assert not hasattr(bar, "timestamp")


@pytest.mark.unit
def test_trade_proposal_uses_correct_field_names():
    """Regression: old strategies used direction/entry_price/quantity/confidence."""
    p = TradeProposal(
        strategy_id="trend_follower",
        agent_id=12,
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        asset_class=AssetClass.CRYPTO,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.1"),
        size_usd=Decimal("4500"),
        limit_price=Decimal("45000"),
        stop_loss=Decimal("44000"),
        take_profit=Decimal("48000"),
        confidence_score=0.7,
        rationale="test",
    )
    assert p.confidence_score == 0.7
    assert p.size == Decimal("0.1")
    assert p.limit_price == Decimal("45000")


@pytest.mark.unit
def test_order_uses_size_not_quantity():
    o = Order(
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        size=Decimal("0.1"),
        price=Decimal("45000"),
        strategy_id="test",
        agent_id=12,
    )
    assert o.size == Decimal("0.1")
    assert o.filled_size == Decimal("0")
    assert not hasattr(o, "quantity")
    assert not hasattr(o, "filled_quantity")


@pytest.mark.unit
def test_fill_uses_fill_size_fill_price():
    f = Fill(
        order_id=uuid4(),
        exchange_order_id="abc123",
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        fill_size=Decimal("0.05"),
        fill_price=Decimal("45100"),
        fee=Decimal("0.5"),
        fee_currency="USDT",
        timestamp=datetime.utcnow(),
    )
    assert f.fill_size == Decimal("0.05")
    assert f.fill_price == Decimal("45100")


@pytest.mark.unit
def test_position_sizing_result_full_schema():
    r = PositionSizingResult(
        symbol="BTC/USDT",
        strategy_id="trend_follower",
        entry_price=Decimal("45000"),
        stop_loss=Decimal("44000"),
        total_capital=Decimal("100000"),
        kelly_fraction_raw=0.05,
        kelly_size_usd=Decimal("5000"),
        quarter_kelly_size_usd=Decimal("1250"),
        vol_adjusted_size_usd=Decimal("1000"),
        final_size_usd=Decimal("1000"),
        final_size_units=Decimal("0.022"),
        risk_amount_usd=Decimal("22"),
        risk_pct_of_capital=0.00022,
        constraints_applied=["vol_regime=NORMAL_scalar=1.00"],
    )
    assert r.final_size_usd == Decimal("1000")
    assert "vol_regime" in r.constraints_applied[0]
