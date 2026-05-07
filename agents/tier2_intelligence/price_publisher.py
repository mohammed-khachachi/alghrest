"""
Agent 04 — Price Publisher

Single-purpose ticker cache writer. Consumes the raw OHLCV + OrderBook stream
from `prices.realtime` and maintains a per-symbol "current ticker" record in
Redis under `prices:{symbol}`. Other agents (hedge_manager, macro_rotator,
liquidation_guard, dashboards) read this key for a quick last-price lookup
without subscribing to Kafka.

Output format:
  Redis key:    prices:{symbol}              (e.g. "prices:BTC/USDT")
  Redis value:  JSON object:
    {
      "last":     <float>,                   # latest M1 close (or mid as fallback)
      "bid":      <float | null>,            # best bid from order book
      "ask":      <float | null>,            # best ask from order book
      "exchange": <str>,                     # most recent venue
      "ts":       <iso8601>,                 # timestamp of the source event
    }
  TTL:        60 s — stale data → consumers treat as missing.

Design notes:
  - Only M1 OHLCV is used for `last`; other timeframes carry the same close
    price but at lower update frequency, so they are ignored to halve work.
  - Throttled at one Redis write per symbol per second (`_THROTTLE_INTERVAL`)
    to avoid hammering Redis when an order book updates 10+× per second.
  - This agent does NOT honour the kill switch — price data is needed by
    monitoring agents and dashboards even while trading is halted.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

import structlog

from agents.base_agent import BaseAgent
from core.data.models import (
    AgentConfig,
    KafkaTopic,
    OHLCVBar,
    OrderBook,
    Timeframe,
)

log = structlog.get_logger(__name__)

_REDIS_KEY_FMT = "prices:{symbol}"
_REDIS_TTL = 60                # seconds — short enough that consumers fail fast
_THROTTLE_INTERVAL = 1.0       # seconds between Redis writes per symbol


class PricePublisher(BaseAgent):
    """
    Agent 04 — Price Publisher.
    Maintains a Redis cache of `prices:{symbol}` for cheap last-price lookups.
    """

    AGENT_ID = 4

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=2,
            name="PricePublisher",
            config=config,
        )
        # Most recent merged ticker per symbol — accumulated from OHLCV and
        # OrderBook events, written to Redis on a throttle.
        self._latest: dict[str, dict] = {}
        self._last_written: dict[str, datetime] = {}
        self._writes = 0
        self._skipped = 0
        self._unwritable = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("price_publisher.initialized", ttl=_REDIS_TTL)

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PRICES_REALTIME])
        await consumer.initialize()
        async for msg in consumer.stream():
            try:
                msg_type = msg.get("message_type", "")
                payload = msg.get("payload", msg)
                if msg_type == "ohlcv":
                    await self._handle_ohlcv(payload)
                elif msg_type == "order_book":
                    await self._handle_order_book(payload)
            except Exception as exc:
                self.record_processing_error(
                    KafkaTopic.PRICES_REALTIME.value, type(exc).__name__
                )
                log.warning("price_publisher.error", error=str(exc))

    async def shutdown(self) -> None:
        log.info(
            "price_publisher.shutdown",
            writes=self._writes,
            skipped_throttle=self._skipped,
            redis_errors=self._unwritable,
            tracked_symbols=len(self._latest),
        )

    # ── Handlers ───────────────────────────────────────────────────────────────

    async def _handle_ohlcv(self, payload: dict) -> None:
        try:
            bar = OHLCVBar.model_validate(payload)
        except Exception:
            return
        # Only M1 — other timeframes carry duplicate information at lower freq.
        if bar.timeframe != Timeframe.M1:
            return

        existing = self._latest.get(bar.symbol, {})
        existing.update({
            "last": float(bar.close),
            "exchange": bar.exchange.value,
            "ts": bar.time.isoformat() if hasattr(bar.time, "isoformat") else str(bar.time),
        })
        self._latest[bar.symbol] = existing
        await self._maybe_write(bar.symbol)

    async def _handle_order_book(self, payload: dict) -> None:
        try:
            book = OrderBook.model_validate(payload)
        except Exception:
            return

        bid = float(book.best_bid) if book.best_bid else None
        ask = float(book.best_ask) if book.best_ask else None
        if bid is None and ask is None:
            return

        existing = self._latest.get(book.symbol, {})
        existing.update({
            "bid": bid,
            "ask": ask,
            "exchange": book.exchange.value,
            "ts": (
                book.timestamp.isoformat()
                if hasattr(book.timestamp, "isoformat")
                else str(book.timestamp)
            ),
        })
        # If we have not seen an OHLCV bar yet, mid serves as a `last` proxy.
        if "last" not in existing and book.mid_price is not None:
            existing["last"] = float(book.mid_price)
        self._latest[book.symbol] = existing
        await self._maybe_write(book.symbol)

    async def _maybe_write(self, symbol: str) -> None:
        now = datetime.utcnow()
        last_at = self._last_written.get(symbol)
        if last_at is not None and (now - last_at).total_seconds() < _THROTTLE_INTERVAL:
            self._skipped += 1
            return
        payload = self._latest.get(symbol)
        if not payload or "last" not in payload:
            return
        try:
            await self.state.redis.setex(
                _REDIS_KEY_FMT.format(symbol=symbol),
                _REDIS_TTL,
                json.dumps(payload),
            )
            self._last_written[symbol] = now
            self._writes += 1
        except Exception as exc:
            self._unwritable += 1
            log.warning(
                "price_publisher.redis_write_error",
                symbol=symbol,
                error=str(exc),
            )
