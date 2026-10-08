"""
ALGHREST — Agent 05: Market Data Hub
Connects to Binance, Bybit, Coinbase, Kraken via CCXT Pro WebSockets.
Streams OHLCV bars and order books → publishes to prices.realtime Kafka topic.

Partitioning: Kafka key = exchange:symbol so same pair always goes to same partition.
"""

from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from decimal import Decimal
from typing import Any

import ccxt.pro as ccxtpro
import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import Exchange, KafkaTopic, OHLCVBar, OrderBook, OrderBookLevel, Timeframe
from core.utils.metrics import price_updates_received, websocket_reconnections

logger = structlog.get_logger(__name__)

# Symbols to stream per exchange
WATCHED_SYMBOLS: dict[str, list[str]] = {
    Exchange.BINANCE.value: [
        "BTC/USDT",
        "ETH/USDT",
        "BNB/USDT",
        "SOL/USDT",
        "AVAX/USDT",
        "MATIC/USDT",
        "LINK/USDT",
        "UNI/USDT",
        "AAVE/USDT",
    ],
    Exchange.BYBIT.value: [
        "BTC/USDT",
        "ETH/USDT",
        "SOL/USDT",
        "AVAX/USDT",
    ],
    Exchange.COINBASE.value: [
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
    ],
}

WATCHED_TIMEFRAMES = [Timeframe.M1, Timeframe.M5, Timeframe.H1, Timeframe.H4, Timeframe.D1]


class MarketDataHub(BaseAgent):
    """Agent 05 — Streams live OHLCV and order book data to Kafka."""

    AGENT_ID = 5

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="market_data_hub")
        self._exchanges: dict[str, Any] = {}
        self._tasks: list[asyncio.Task[None]] = []

    async def initialize(self) -> None:
        self.logger.info("initializing exchange connections")
        self._exchanges = await self._create_exchanges()
        self.logger.info("exchange connections ready", count=len(self._exchanges))

    async def _create_exchanges(self) -> dict[str, Any]:
        exchanges = {}

        if settings.binance_testnet:
            binance = ccxtpro.binance(
                {
                    "apiKey": settings.binance_testnet_api_key or settings.binance_api_key,
                    "secret": settings.binance_testnet_secret or settings.binance_secret,
                    "options": {"defaultType": "spot", "testnet": True},
                    "enableRateLimit": True,
                }
            )
            binance.set_sandbox_mode(True)
        else:
            binance = ccxtpro.binance(
                {
                    "apiKey": settings.binance_api_key,
                    "secret": settings.binance_secret,
                    "options": {"defaultType": "spot"},
                    "enableRateLimit": True,
                }
            )
        exchanges[Exchange.BINANCE.value] = binance

        bybit = ccxtpro.bybit(
            {
                "apiKey": settings.bybit_api_key,
                "secret": settings.bybit_secret,
                "options": {"testnet": settings.bybit_testnet},
                "enableRateLimit": True,
            }
        )
        exchanges[Exchange.BYBIT.value] = bybit

        return exchanges

    async def run(self) -> None:
        self.logger.info("starting market data streams")

        # Launch one coroutine per exchange-symbol-timeframe combination
        for exchange_id, symbols in WATCHED_SYMBOLS.items():
            if exchange_id not in self._exchanges:
                continue
            exchange = self._exchanges[exchange_id]

            for symbol in symbols:
                # Stream OHLCV for each timeframe
                for tf in WATCHED_TIMEFRAMES:
                    task = asyncio.create_task(
                        self._stream_ohlcv(exchange, exchange_id, symbol, tf.value),
                        name=f"ohlcv:{exchange_id}:{symbol}:{tf.value}",
                    )
                    self._tasks.append(task)

                # Stream order book (best 20 levels)
                task = asyncio.create_task(
                    self._stream_order_book(exchange, exchange_id, symbol),
                    name=f"ob:{exchange_id}:{symbol}",
                )
                self._tasks.append(task)

        self.logger.info("streams launched", count=len(self._tasks))

        # Wait for all stream tasks (they run forever unless cancelled)
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _stream_ohlcv(
        self,
        exchange: Any,
        exchange_id: str,
        symbol: str,
        timeframe: str,
    ) -> None:
        log = self.logger.bind(exchange=exchange_id, symbol=symbol, timeframe=timeframe)
        reconnects = 0

        while True:
            try:
                ohlcv_list = await exchange.watch_ohlcv(symbol, timeframe)

                for candle in ohlcv_list:
                    bar = self._normalize_ohlcv(candle, exchange_id, symbol, timeframe)
                    if bar is None:
                        continue

                    await self.publish(
                        KafkaTopic.PRICES_REALTIME,
                        payload=bar.model_dump(mode="json"),
                        message_type="ohlcv",
                    )

                    price_updates_received.labels(
                        exchange=exchange_id,
                        symbol=symbol,
                        timeframe=timeframe,
                    ).inc()

            except asyncio.CancelledError:
                return
            except Exception as e:
                reconnects += 1
                websocket_reconnections.labels(exchange=exchange_id).inc()
                log.warning("ohlcv stream error, reconnecting", error=str(e), attempt=reconnects)
                await asyncio.sleep(min(2 ** min(reconnects, 6), 60))

    async def _stream_order_book(
        self,
        exchange: Any,
        exchange_id: str,
        symbol: str,
        limit: int = 20,
    ) -> None:
        log = self.logger.bind(exchange=exchange_id, symbol=symbol)
        reconnects = 0

        while True:
            try:
                ob_raw = await exchange.watch_order_book(symbol, limit)
                book = self._normalize_order_book(ob_raw, exchange_id, symbol)
                if book is None:
                    continue

                await self.publish(
                    KafkaTopic.PRICES_REALTIME,
                    payload=book.model_dump(mode="json"),
                    message_type="order_book",
                )

            except asyncio.CancelledError:
                return
            except Exception as e:
                reconnects += 1
                websocket_reconnections.labels(exchange=exchange_id).inc()
                log.warning("order book stream error", error=str(e), attempt=reconnects)
                await asyncio.sleep(min(2 ** min(reconnects, 6), 60))

    @staticmethod
    def _normalize_ohlcv(
        candle: list[Any],
        exchange_id: str,
        symbol: str,
        timeframe: str,
    ) -> OHLCVBar | None:
        """Convert CCXT candle array [ts, open, high, low, close, vol] to OHLCVBar."""
        try:
            ts, o, h, low, c, v = candle[0], candle[1], candle[2], candle[3], candle[4], candle[5]
            if None in (o, h, low, c) or h < low:
                return None

            tf_map = {
                "1m": Timeframe.M1,
                "5m": Timeframe.M5,
                "15m": Timeframe.M15,
                "30m": Timeframe.M30,
                "1h": Timeframe.H1,
                "4h": Timeframe.H4,
                "1d": Timeframe.D1,
                "1w": Timeframe.W1,
            }
            tf_enum = tf_map.get(timeframe, Timeframe.M1)
            ex_enum = (
                Exchange(exchange_id)
                if exchange_id in Exchange._value2member_map_
                else Exchange.BINANCE
            )

            return OHLCVBar(
                time=datetime.utcfromtimestamp(ts / 1000),
                symbol=symbol,
                exchange=ex_enum,
                timeframe=tf_enum,
                open=Decimal(str(o)),
                high=Decimal(str(h)),
                low=Decimal(str(low)),
                close=Decimal(str(c)),
                volume=Decimal(str(v or 0)),
            )
        except Exception:
            return None

    @staticmethod
    def _normalize_order_book(
        ob_raw: dict[str, Any], exchange_id: str, symbol: str
    ) -> OrderBook | None:
        """Convert CCXT order book dict to OrderBook model."""
        try:
            ex_enum = (
                Exchange(exchange_id)
                if exchange_id in Exchange._value2member_map_
                else Exchange.BINANCE
            )
            bids = [
                OrderBookLevel(price=Decimal(str(b[0])), size=Decimal(str(b[1])))
                for b in ob_raw["bids"][:20]
            ]
            asks = [
                OrderBookLevel(price=Decimal(str(a[0])), size=Decimal(str(a[1])))
                for a in ob_raw["asks"][:20]
            ]
            return OrderBook(
                symbol=symbol,
                exchange=ex_enum,
                timestamp=datetime.utcnow(),
                bids=bids,
                asks=asks,
            )
        except Exception:
            return None

    async def shutdown(self) -> None:
        for task in self._tasks:
            task.cancel()
        for exchange in self._exchanges.values():
            with contextlib.suppress(Exception):
                await exchange.close()
        self.logger.info("market data hub shutdown")
