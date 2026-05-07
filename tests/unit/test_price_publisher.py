"""Unit tests for the PricePublisher."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.tier2_intelligence.price_publisher import (
    PricePublisher,
    _REDIS_KEY_FMT,
    _REDIS_TTL,
    _THROTTLE_INTERVAL,
)
from core.data.models import Exchange, OHLCVBar, OrderBook, OrderBookLevel, Timeframe


def _build_publisher() -> PricePublisher:
    pub = PricePublisher()
    pub.state = MagicMock()
    pub.state.redis = MagicMock()
    pub.state.redis.setex = AsyncMock()
    return pub


def _ohlcv_payload(symbol: str = "BTC/USDT", close: float = 45123.45,
                   timeframe: Timeframe = Timeframe.M1,
                   exchange: Exchange = Exchange.BINANCE) -> dict:
    bar = OHLCVBar(
        time=datetime.utcnow(),
        symbol=symbol,
        exchange=exchange,
        timeframe=timeframe,
        open=Decimal(str(close)),
        high=Decimal(str(close + 10)),
        low=Decimal(str(close - 10)),
        close=Decimal(str(close)),
        volume=Decimal("1.5"),
    )
    return bar.model_dump(mode="json")


def _orderbook_payload(symbol: str = "BTC/USDT", bid: float = 45000,
                       ask: float = 45050,
                       exchange: Exchange = Exchange.BINANCE) -> dict:
    book = OrderBook(
        symbol=symbol,
        exchange=exchange,
        timestamp=datetime.utcnow(),
        bids=[OrderBookLevel(price=Decimal(str(bid)), size=Decimal("1.0"))],
        asks=[OrderBookLevel(price=Decimal(str(ask)), size=Decimal("1.0"))],
    )
    return book.model_dump(mode="json")


# ── M1 OHLCV writes a `last` key to Redis ────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_m1_ohlcv_writes_to_redis():
    pub = _build_publisher()
    payload = _ohlcv_payload(close=45200.0)
    await pub._handle_ohlcv(payload)

    pub.state.redis.setex.assert_awaited_once()
    args = pub.state.redis.setex.await_args.args
    assert args[0] == _REDIS_KEY_FMT.format(symbol="BTC/USDT")
    assert args[1] == _REDIS_TTL
    blob = json.loads(args[2])
    assert blob["last"] == 45200.0
    assert blob["exchange"] == "binance"
    assert "ts" in blob
    assert pub._writes == 1


# ── Non-M1 timeframes are ignored ─────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_h4_ohlcv_is_skipped():
    pub = _build_publisher()
    payload = _ohlcv_payload(timeframe=Timeframe.H4)
    await pub._handle_ohlcv(payload)
    pub.state.redis.setex.assert_not_awaited()
    assert pub._writes == 0


# ── OrderBook adds bid/ask + uses mid as last fallback ───────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_orderbook_writes_bid_ask_and_mid_fallback():
    pub = _build_publisher()
    payload = _orderbook_payload(bid=44900, ask=45100)
    await pub._handle_order_book(payload)

    pub.state.redis.setex.assert_awaited_once()
    blob = json.loads(pub.state.redis.setex.await_args.args[2])
    assert blob["bid"] == 44900.0
    assert blob["ask"] == 45100.0
    # No prior OHLCV → mid (45000) becomes the `last` proxy.
    assert blob["last"] == 45000.0


# ── Combined: OHLCV `last` + later OrderBook bid/ask coexist ─────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_then_orderbook_merges_fields():
    pub = _build_publisher()
    await pub._handle_ohlcv(_ohlcv_payload(close=45200.0))
    # Force throttle bypass: pretend the previous write happened > 1s ago.
    pub._last_written["BTC/USDT"] = datetime.utcnow() - timedelta(seconds=2)
    await pub._handle_order_book(_orderbook_payload(bid=45100, ask=45300))

    # Two writes total
    assert pub.state.redis.setex.await_count == 2
    last_args = pub.state.redis.setex.await_args_list[-1].args
    blob = json.loads(last_args[2])
    assert blob["last"] == 45200.0       # preserved from OHLCV
    assert blob["bid"] == 45100.0
    assert blob["ask"] == 45300.0


# ── Throttling: rapid updates collapsed into one Redis write ─────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_throttle_collapses_rapid_updates():
    pub = _build_publisher()
    # Two consecutive OHLCV M1 ticks within the throttle window.
    await pub._handle_ohlcv(_ohlcv_payload(close=45000))
    await pub._handle_ohlcv(_ohlcv_payload(close=45050))
    await pub._handle_ohlcv(_ohlcv_payload(close=45100))

    # Only the first is written; the next two are throttled.
    assert pub.state.redis.setex.await_count == 1
    assert pub._writes == 1
    assert pub._skipped == 2


@pytest.mark.unit
def test_throttle_interval_is_one_second():
    """Defensive: changing the throttle inadvertently could overload Redis."""
    assert _THROTTLE_INTERVAL == 1.0
    assert _REDIS_TTL == 60


# ── Invalid payloads do not crash ─────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.asyncio
async def test_invalid_ohlcv_payload_silently_dropped():
    pub = _build_publisher()
    await pub._handle_ohlcv({"not": "valid"})
    pub.state.redis.setex.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_orderbook_with_no_levels_skipped():
    pub = _build_publisher()
    book = OrderBook(
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        timestamp=datetime.utcnow(),
        bids=[],
        asks=[],
    )
    await pub._handle_order_book(book.model_dump(mode="json"))
    pub.state.redis.setex.assert_not_awaited()
