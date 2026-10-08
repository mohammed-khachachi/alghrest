"""Explicit spot history pagination; never infer completion from filtered results.

Binance bounded ranges subdivide saturated pages, including timestamp ties.
Bybit/Coinbase follow native cursors. Kraken offsets use the unfiltered account
result and its server count, before CCXT parses individual trades.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import ccxt.pro as ccxtpro

from connectors.exchanges.ccxt_connector import ExchangeConnector
from core.accounting.models import utc
from core.config import settings
from core.data.models import Exchange, Order, OrderSide, OrderType
from core.execution.contracts import RecoveryBlockedError, TradePage


class SpotRecoveryAdapter:
    def __init__(self, connector: ExchangeConnector) -> None:
        self.connector = connector
        self.exchange = connector.exchange_id
        self.account_id = connector.account_id

    @property
    def client(self) -> Any:
        return self.connector._client

    async def balances(self) -> dict[str, Decimal]:
        return await self.connector.fetch_balance()

    async def place(self, order: Order) -> Order:
        settings.require_order_execution()
        args: dict[str, Any] = dict(
            symbol=order.symbol,
            side=order.side,
            amount=order.size,
            client_order_id=str(order.client_order_id),
        )
        if order.order_type == OrderType.MARKET:
            return await self.connector.place_market_order(**args)
        if order.order_type == OrderType.LIMIT and order.price is not None:
            return await self.connector.place_limit_order(**args, price=order.price)
        raise ValueError("Recovery executor supports spot MARKET/LIMIT orders only")

    async def cancel(self, order: Order) -> None:
        settings.require_order_execution()
        if not order.exchange_order_id:
            raise RecoveryBlockedError("Cannot cancel an unidentified submission")
        if not await self.connector.cancel_order(order.exchange_order_id, order.symbol):
            raise RecoveryBlockedError("Cancellation not confirmed")

    def _order(self, raw: dict[str, Any]) -> Order:
        return self.connector._raw_to_order(
            raw,
            raw["symbol"],
            OrderSide(raw["side"].upper()),
            OrderType(str(raw["type"]).upper()),
        )

    async def lookup(self, order: Order) -> Order | None:
        """None is unresolved, NEVER permission to send again."""
        client_id = str(order.client_order_id)
        market = self.client.market(order.symbol)
        try:
            if self.exchange == Exchange.BINANCE:
                raw = await self.client.fetch_order(
                    order.exchange_order_id or "",
                    order.symbol,
                    {} if order.exchange_order_id else {"origClientOrderId": client_id},
                )
                if not order.exchange_order_id and raw.get("clientOrderId") != client_id:
                    raise RecoveryBlockedError("Client ID lookup returned a different order")
                return self._order(raw)
            if self.exchange == Exchange.BYBIT:
                query = {"category": "spot", "symbol": market["id"]}
                query["orderId" if order.exchange_order_id else "orderLinkId"] = (
                    order.exchange_order_id or client_id
                )
                for endpoint in (
                    self.client.privateGetV5OrderRealtime,
                    self.client.privateGetV5OrderHistory,
                ):
                    response = await endpoint(query)
                    rows = response["result"]["list"]
                    if rows:
                        if len(rows) != 1:
                            raise RecoveryBlockedError("Ambiguous order lookup")
                        parsed = self.client.parse_order(rows[0], market)
                        if not order.exchange_order_id and parsed.get("clientOrderId") != client_id:
                            raise RecoveryBlockedError(
                                "Client ID lookup returned a different order"
                            )
                        return self._order(parsed)
                return None
            if order.exchange_order_id:
                return self._order(
                    await self.client.fetch_order(order.exchange_order_id, order.symbol)
                )
            if self.exchange == Exchange.COINBASE:
                token = None
                seen = set()
                for _ in range(1000):
                    query = {
                        "product_ids": [market["id"]],
                        "start_date": (utc(order.created_at) - timedelta(minutes=1)).isoformat(),
                        "limit": 100,
                    }
                    if token:
                        query["cursor"] = token
                    response = await self.client.v3PrivateGetBrokerageOrdersHistoricalBatch(query)
                    for raw in response["orders"]:
                        if raw.get("client_order_id") == client_id:
                            return self._order(self.client.parse_order(raw, market))
                    if not response.get("has_next", False):
                        return None
                    token = response.get("cursor")
                    if not token or token in seen:
                        raise RecoveryBlockedError("Order history cursor did not advance")
                    seen.add(token)
                raise RecoveryBlockedError("Order history page budget exceeded")
            if self.exchange == Exchange.KRAKEN:
                opens = await self.client.privatePostOpenOrders({"cl_ord_id": client_id})
                for order_id, raw in opens["result"]["open"].items():
                    if raw.get("cl_ord_id") == client_id:
                        return self._order(self.client.parse_order({**raw, "id": order_id}, market))
                offset = 0
                for _ in range(1000):
                    response = await self.client.privatePostClosedOrders(
                        {
                            "start": int(utc(order.created_at).timestamp()) - 60,
                            "ofs": offset,
                        }
                    )
                    rows = response["result"]["closed"]
                    for order_id, raw in rows.items():
                        if raw.get("cl_ord_id") == client_id:
                            return self._order(
                                self.client.parse_order({**raw, "id": order_id}, market)
                            )
                    offset += len(rows)
                    if offset >= int(response["result"]["count"]):
                        return None
                    if not rows:
                        raise RecoveryBlockedError("Empty Kraken order page before server count")
                raise RecoveryBlockedError("Order history page budget exceeded")
            raise RecoveryBlockedError("Unsupported recovery exchange")
        except ccxtpro.OrderNotFound:
            return None

    async def open_orders(self) -> list[Order]:
        if self.exchange == Exchange.BINANCE:
            self.client.options.setdefault("fetchOpenOrders", {})["warnWithoutSymbol"] = False
            return [self._order(raw) for raw in await self.client.fetch_open_orders()]
        if self.exchange == Exchange.KRAKEN:
            response = await self.client.privatePostOpenOrders({})
            return [
                self._order(self.client.parse_order({**raw, "id": oid}))
                for oid, raw in response["result"]["open"].items()
            ]
        result: list[Order] = []
        token = None
        seen = set()
        for _ in range(1000):
            if self.exchange == Exchange.BYBIT:
                query = {"category": "spot", "openOnly": 0, "limit": 50}
                if token:
                    query["cursor"] = token
                response = await self.client.privateGetV5OrderRealtime(query)
                rows = response["result"]["list"]
                token = response["result"].get("nextPageCursor") or None
            else:
                query = {"order_status": ["OPEN"], "limit": 100}
                if token:
                    query["cursor"] = token
                response = await self.client.v3PrivateGetBrokerageOrdersHistoricalBatch(query)
                rows = response["orders"]
                token = response.get("cursor") if response.get("has_next") else None
                if response.get("has_next") and not token:
                    raise RecoveryBlockedError("Open order pagination missing cursor")
            result.extend(self._order(self.client.parse_order(raw)) for raw in rows)
            if not token:
                return result
            if token in seen:
                raise RecoveryBlockedError("Open order cursor repeated")
            seen.add(token)
        raise RecoveryBlockedError("Open order page budget exceeded")

    async def history_page(
        self, symbol: str, start_ms: int, end_ms: int, cursor: dict[str, Any] | None
    ) -> TradePage:
        market: Any = self.client.market(symbol) if symbol != "*" else None
        if self.exchange == Exchange.BINANCE:
            ranges = list(cursor["ranges"]) if cursor else [[start_ms, end_ms]]
            low, high = ranges.pop(0)
            raw = await self.client.fetch_my_trades(symbol, low, 1000, {"until": high})
            if any(r.get("timestamp") is None or not low <= r["timestamp"] <= high for r in raw):
                raise RecoveryBlockedError("Binance history response outside requested range")
            if len(raw) >= 1000:
                if low == high:
                    raise RecoveryBlockedError(
                        "Trade page saturated at one millisecond; cannot prove completeness"
                    )
                middle = (low + high) // 2
                ranges = [[low, middle], [middle + 1, high], *ranges]
            return TradePage(
                self.connector.normalize_trades(raw, symbol), {"ranges": ranges} if ranges else None
            )
        if self.exchange == Exchange.BYBIT:
            query = {
                "category": "spot",
                "symbol": market["id"],
                "startTime": start_ms,
                "endTime": end_ms,
                "limit": 100,
            }
            if cursor:
                query["cursor"] = cursor["token"]
            response = await self.client.privateGetV5ExecutionList(query)
            rows = response["result"]["list"]
            token = response["result"].get("nextPageCursor") or None
            following = {"token": token} if token else None
        elif self.exchange == Exchange.COINBASE:
            query = {
                "product_id": market["id"],
                "start_sequence_timestamp": datetime.fromtimestamp(
                    start_ms / 1000, UTC
                ).isoformat(),
                "end_sequence_timestamp": datetime.fromtimestamp(end_ms / 1000, UTC).isoformat(),
                "limit": 250,
            }
            if cursor:
                query["cursor"] = cursor["token"]
            response = await self.client.v3PrivateGetBrokerageOrdersHistoricalFills(query)
            rows = response["fills"]
            token = response.get("cursor") or None
            following = {"token": token} if token else None
        elif self.exchange == Exchange.KRAKEN:
            offset = int(cursor["offset"]) if cursor else 0
            response = await self.client.privatePostTradesHistory(
                {"start": start_ms // 1000 - 1, "end": end_ms // 1000 + 1, "ofs": offset}
            )
            rows = [{**raw, "id": tid} for tid, raw in response["result"]["trades"].items()]
            if any(Decimal(str(raw.get("margin", "0"))) != 0 for raw in rows):
                raise RecoveryBlockedError("Margin trade in spot accounting scope")
            next_offset = offset + len(rows)
            if not rows and next_offset < int(response["result"]["count"]):
                raise RecoveryBlockedError("Incomplete Kraken history page")
            following = (
                {"offset": next_offset} if next_offset < int(response["result"]["count"]) else None
            )
        else:
            raise RecoveryBlockedError("Unsupported recovery exchange")
        if following and following == cursor:
            raise RecoveryBlockedError("Trade history cursor did not advance")
        parsed = [self.client.parse_trade(raw, market) for raw in rows]
        return TradePage(
            self.connector.normalize_trades(parsed, None if symbol == "*" else symbol), following
        )
