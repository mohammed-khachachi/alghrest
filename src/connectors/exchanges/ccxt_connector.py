"""
Unified CCXT exchange connector — order placement, balances, and position queries.
Wraps ccxt.pro async clients with retry logic, rate limiting, and structured logging.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any

import ccxt.pro as ccxtpro
import structlog

from core.config import settings
from core.data.models import Exchange, Fill, FillFee, Order, OrderSide, OrderStatus, OrderType

log = structlog.get_logger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 1.0  # seconds


class ExchangeConnector:
    """Async wrapper around a single CCXT Pro exchange instance."""

    def __init__(self, exchange: Exchange, account_id: str = "default") -> None:
        self.exchange_id = exchange
        self.account_id = account_id
        self._client: ccxtpro.Exchange | None = None

    async def connect(self) -> None:
        settings.require_order_execution()
        exchange_map: dict[Exchange, type[ccxtpro.Exchange]] = {
            Exchange.BINANCE: ccxtpro.binance,
            Exchange.BYBIT: ccxtpro.bybit,
            Exchange.COINBASE: ccxtpro.coinbase,
            Exchange.KRAKEN: ccxtpro.kraken,
        }
        cls = exchange_map[self.exchange_id]
        config: dict[str, Any] = {
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        }
        if self.exchange_id == Exchange.BINANCE:
            if settings.binance_testnet:
                config["apiKey"] = settings.binance_testnet_api_key
                config["secret"] = settings.binance_testnet_secret
                config["options"]["testnet"] = True
            else:
                config["apiKey"] = settings.binance_api_key
                config["secret"] = settings.binance_secret
        elif self.exchange_id == Exchange.BYBIT:
            config["apiKey"] = settings.bybit_api_key
            config["secret"] = settings.bybit_secret
            if settings.bybit_testnet:
                config["options"]["testnet"] = True
        elif self.exchange_id == Exchange.COINBASE:
            config["apiKey"] = settings.coinbase_api_key
            config["secret"] = settings.coinbase_secret
        elif self.exchange_id == Exchange.KRAKEN:
            config["apiKey"] = settings.kraken_api_key
            config["secret"] = settings.kraken_secret

        self._client = cls(config)
        if (self.exchange_id == Exchange.BINANCE and settings.binance_testnet) or (
            self.exchange_id == Exchange.BYBIT and settings.bybit_testnet
        ):
            self._client.set_sandbox_mode(True)
        await self._client.load_markets()
        log.info("exchange.connected", exchange=self.exchange_id.value)

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    # ─── Order placement ─────────────────────────────────────────────────────

    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: Decimal,
        price: Decimal,
        client_order_id: str | None = None,
    ) -> Order:
        settings.require_order_execution()
        if not settings.is_live:
            raise RuntimeError("Real exchange orders require ENVIRONMENT=live")
        params: dict[str, Any] = {}
        if client_order_id:
            params["clientOrderId"] = client_order_id

        # A lost response is ambiguous. Retrying a create can open a second order.
        raw = await self._client.create_limit_order(
            symbol,
            side.value.lower(),
            float(amount),
            float(price),
            params,
        )
        return self._raw_to_order(raw, symbol, side, OrderType.LIMIT)

    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        amount: Decimal,
        client_order_id: str | None = None,
    ) -> Order:
        settings.require_order_execution()
        if not settings.is_live:
            raise RuntimeError("Real exchange orders require ENVIRONMENT=live")
        params: dict[str, Any] = {}
        if client_order_id:
            params["clientOrderId"] = client_order_id

        raw = await self._client.create_market_order(
            symbol,
            side.value.lower(),
            float(amount),
            params,
        )
        return self._raw_to_order(raw, symbol, side, OrderType.MARKET)

    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        settings.require_order_execution()
        if not settings.is_live:
            raise RuntimeError("Real exchange cancellation requires ENVIRONMENT=live")
        try:
            await self._retry(self._client.cancel_order, order_id, symbol)
            return True
        except Exception as exc:
            log.warning("cancel_order.failed", order_id=order_id, error=str(exc))
            return False

    async def cancel_all_orders(self, symbol: str) -> int:
        settings.require_order_execution()
        if not settings.is_live:
            raise RuntimeError("Real exchange cancellation requires ENVIRONMENT=live")
        try:
            raw_list = await self._retry(self._client.cancel_all_orders, symbol)
            return len(raw_list) if raw_list else 0
        except Exception as exc:
            log.warning("cancel_all.failed", symbol=symbol, error=str(exc))
            return 0

    async def fetch_order(self, order_id: str, symbol: str) -> Order | None:
        try:
            raw = await self._retry(self._client.fetch_order, order_id, symbol)
            return self._raw_to_order(
                raw, symbol, OrderSide(raw["side"].upper()), self._parse_order_type(raw)
            )
        except Exception as exc:
            log.warning("fetch_order.failed", order_id=order_id, error=str(exc))
            return None

    async def fetch_open_orders(self, symbol: str) -> list[Order]:
        raw_list = await self._retry(self._client.fetch_open_orders, symbol)
        orders = []
        for raw in raw_list:
            try:
                orders.append(
                    self._raw_to_order(
                        raw,
                        symbol,
                        OrderSide(raw["side"].upper()),
                        self._parse_order_type(raw),
                    )
                )
            except Exception as exc:
                log.debug("open_order_parse_failed", error=str(exc))
        return orders

    @staticmethod
    def _parse_order_type(raw: dict) -> OrderType:
        t = (raw.get("type") or "limit").lower()
        mapping = {
            "limit": OrderType.LIMIT,
            "market": OrderType.MARKET,
            "stop": OrderType.STOP,
            "stop_limit": OrderType.STOP_LIMIT,
            "stop-limit": OrderType.STOP_LIMIT,
        }
        return mapping.get(t, OrderType.LIMIT)

    # ─── Account queries ──────────────────────────────────────────────────────

    async def fetch_balance(self) -> dict[str, Decimal]:
        raw = await self._retry(self._client.fetch_balance)
        result: dict[str, Decimal] = {}
        if not isinstance(raw.get("total"), dict):
            raise ValueError("Exchange balance snapshot has no totals")
        for currency, data in raw["total"].items():
            if data is None:
                raise ValueError("Exchange balance contains an unknown amount")
            amount = Decimal(str(data))
            if not amount.is_finite():
                raise ValueError("Exchange balance is not finite")
            result[currency] = amount  # preserve zero and negative liabilities
        return result

    async def fetch_ticker(self, symbol: str) -> dict[str, Any]:
        return await self._retry(self._client.fetch_ticker, symbol)

    async def fetch_order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return await self._retry(self._client.fetch_order_book, symbol, limit)

    async def fetch_trades(self, symbol: str, limit: int = 100) -> list[Fill]:
        """
        Fetch recent fills for `symbol`.

        Note: `Fill.order_id` is our internal UUID and is NOT known here
        (this connector only sees the exchange's order id). We set a
        placeholder UUID; the caller (ExchangeExecutor) must overwrite
        `order_id` with the matching internal UUID after correlating
        against `exchange_order_id`.
        """
        raw_list = await self._retry(self._client.fetch_my_trades, symbol, limit=limit)
        return self.normalize_trades(raw_list, symbol)

    def normalize_trades(
        self, raw_list: list[dict[str, Any]], symbol: str | None = None
    ) -> list[Fill]:
        from datetime import UTC, datetime as _dt
        from uuid import NAMESPACE_URL, uuid4, uuid5

        from core.accounting.models import key

        fills = []
        for raw in raw_list:
            try:
                actual_symbol = raw.get("symbol") or symbol
                if not actual_symbol or (symbol and actual_symbol != symbol):
                    raise ValueError("Missing/conflicting exchange trade market")
                trade_id = raw.get("id")
                if trade_id is None or str(trade_id) == "" or raw.get("order") is None:
                    raise ValueError("Exchange fill is missing trade/order identity")
                ts_raw = raw.get("datetime") or raw.get("timestamp")
                if isinstance(ts_raw, str):
                    timestamp = _dt.fromisoformat(ts_raw.replace("Z", "+00:00"))
                elif isinstance(ts_raw, int | float):
                    timestamp = _dt.fromtimestamp(ts_raw / 1000, UTC)
                else:
                    raise ValueError("Exchange fill is missing its execution time")
                raw_fees = raw.get("fees")
                if not raw_fees:
                    if raw.get("fee") is None:
                        raise ValueError("Exchange fill is missing fee information")
                    raw_fees = [raw["fee"]]
                fee_items = [
                    FillFee(currency=item["currency"], amount=Decimal(str(item["cost"])))
                    for item in raw_fees
                ]
                primary_fee = fee_items[0]
                fills.append(
                    Fill(
                        fill_id=uuid5(
                            NAMESPACE_URL,
                            key(
                                self.exchange_id.value,
                                self.account_id,
                                actual_symbol,
                                str(trade_id),
                            ),
                        ),
                        exchange_trade_id=str(trade_id),
                        account_id=self.account_id,
                        order_id=uuid4(),  # placeholder — caller overwrites via model_copy
                        exchange_order_id=str(raw["order"]),
                        symbol=actual_symbol,
                        exchange=self.exchange_id,
                        side=OrderSide(raw["side"].upper()),
                        fill_size=Decimal(str(raw["amount"])),
                        fill_price=Decimal(str(raw["price"])),
                        fee=primary_fee.amount,
                        fee_currency=primary_fee.currency,
                        fees=fee_items,
                        timestamp=timestamp,
                        is_maker=bool(raw.get("takerOrMaker") == "maker"),
                    )
                )
            except Exception as exc:
                # Partial batches hide exposure. The caller must retry/reconcile.
                raise ValueError("Cannot normalize exchange fill batch") from exc
        return fills

    # ─── Helpers ──────────────────────────────────────────────────────────────

    def _raw_to_order(
        self, raw: dict, symbol: str, side: OrderSide, order_type: OrderType
    ) -> Order:
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "rejected": OrderStatus.REJECTED,
            "expired": OrderStatus.EXPIRED,
        }
        return Order(
            exchange_order_id=str(raw["id"]),
            symbol=symbol,
            exchange=self.exchange_id,
            side=side,
            order_type=order_type,
            size=Decimal(str(raw.get("amount", 0))),
            price=Decimal(str(raw["price"])) if raw.get("price") else None,
            filled_size=Decimal(str(raw.get("filled", 0))),
            avg_fill_price=Decimal(str(raw["average"])) if raw.get("average") else None,
            status=status_map.get(raw.get("status", "open"), OrderStatus.OPEN),
            strategy_id=raw.get("clientOrderId", "external"),
            agent_id=0,
        )

    async def _retry(self, fn, *args, **kwargs) -> Any:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                return await fn(*args, **kwargs)
            except ccxtpro.RateLimitExceeded:
                wait = _RETRY_DELAY * (2**attempt)
                log.warning("rate_limit", exchange=self.exchange_id.value, wait=wait)
                await asyncio.sleep(wait)
                last_exc = None  # not a hard error
            except ccxtpro.NetworkError as exc:
                wait = _RETRY_DELAY * (2**attempt)
                log.warning(
                    "network_error",
                    exchange=self.exchange_id.value,
                    attempt=attempt,
                    error=str(exc),
                )
                await asyncio.sleep(wait)
                last_exc = exc
            except ccxtpro.ExchangeError as exc:
                log.error("exchange_error", exchange=self.exchange_id.value, error=str(exc))
                raise
        if last_exc:
            raise last_exc
        raise RuntimeError(f"Max retries exceeded on {self.exchange_id.value}")


class MultiExchangeConnector:
    """Manages connectors for all configured exchanges."""

    def __init__(self) -> None:
        self._connectors: dict[Exchange, ExchangeConnector] = {}

    async def connect_all(self, exchanges: list[Exchange]) -> None:
        tasks = []
        for ex in exchanges:
            connector = ExchangeConnector(ex)
            self._connectors[ex] = connector
            tasks.append(connector.connect())
        await asyncio.gather(*tasks, return_exceptions=True)

    async def close_all(self) -> None:
        await asyncio.gather(
            *(c.close() for c in self._connectors.values()), return_exceptions=True
        )

    def get(self, exchange: Exchange) -> ExchangeConnector:
        if exchange not in self._connectors:
            raise KeyError(f"Connector for {exchange.value} not initialized")
        return self._connectors[exchange]

    def all_exchanges(self) -> list[Exchange]:
        return list(self._connectors.keys())

    async def fetch_all_tickers(self, symbol: str) -> dict[Exchange, dict]:
        results: dict[Exchange, dict] = {}
        for ex, connector in self._connectors.items():
            try:
                results[ex] = await connector.fetch_ticker(symbol)
            except Exception as exc:
                log.warning("ticker.failed", exchange=ex.value, symbol=symbol, error=str(exc))
        return results
