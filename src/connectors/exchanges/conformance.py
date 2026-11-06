"""External broker sandbox conformance engine and multi-venue wire harness.

Verifies that TWAP child slice execution, client-order-ID recovery, pending
order cancellation, and emergency flatten against an external broker sandbox
produce fills and final balances that strictly match the internal synthetic
BookState accounting engine.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal, localcontext
from typing import Any
from uuid import UUID, uuid5

import ccxt.pro as ccxtpro

from connectors.exchanges.ccxt_connector import ExchangeConnector
from connectors.exchanges.recovery import SpotRecoveryAdapter
from core.accounting.engine import apply_fill, identity
from core.accounting.models import BookState, CashBalance, OpeningBalances, currencies
from core.data.models import Exchange, Fill, Order, OrderSide, OrderStatus, OrderType
from core.execution.contracts import (
    AccountScope,
    OrderConflictError,
    RecoveryBlockedError,
    balance_differences,
    native_balances,
)


@dataclass(frozen=True)
class ConformanceReport:
    """Verified outcome of an external broker sandbox conformance run."""

    exchange: Exchange
    account_id: str
    symbol: str
    twap_slices_executed: int
    twap_total_filled: Decimal
    resting_orders_cancelled: int
    flatten_orders_executed: int
    fills_reconciled: int
    broker_balances: dict[str, Decimal]
    synthetic_book_balances: dict[str, Decimal]
    balance_differences: dict[str, dict[str, str]]
    flat: bool


class ExternalSandboxBroker:
    """Deterministic external broker sandbox implementing CCXTAsyncClient across venues."""

    def __init__(
        self,
        exchange: Exchange,
        *,
        initial_balances: dict[str, Decimal],
        mark_prices: dict[str, Decimal],
        fee_bps: Decimal = Decimal("10"),
        account_id: str = "default",
    ) -> None:
        self.exchange = exchange
        self.account_id = account_id
        self.balances: dict[str, Decimal] = {
            k: Decimal(str(v)) for k, v in initial_balances.items()
        }
        self.mark_prices: dict[str, Decimal] = {k: Decimal(str(v)) for k, v in mark_prices.items()}
        self.fee_bps = fee_bps
        self.options: dict[str, Any] = {}
        self.sandbox_mode: bool = False
        self.markets: dict[str, dict[str, Any]] = {
            symbol: {"id": symbol.replace("/", ""), "symbol": symbol} for symbol in self.mark_prices
        }
        self._orders_by_id: dict[str, dict[str, Any]] = {}
        self._orders_by_client_id: dict[str, dict[str, Any]] = {}
        self._trades: list[dict[str, Any]] = []
        self._seq: int = 0
        self._clock_ms: int = int(datetime.now(UTC).timestamp() * 1000)
        self.block_cancellation: bool = False

    def set_sandbox_mode(self, enabled: bool) -> None:
        self.sandbox_mode = enabled

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self.exchange.value}-{self._seq}"

    def _extract_client_id(self, params: Mapping[str, Any] | None) -> str:
        if not params:
            return ""
        for field in (
            "clientOrderId",
            "newClientOrderId",
            "orderLinkId",
            "client_order_id",
            "cl_ord_id",
            "userref",
        ):
            val = params.get(field)
            if val is not None and str(val):
                return str(val)
        return ""

    def market(self, symbol: str) -> dict[str, Any]:
        return self.markets.setdefault(symbol, {"id": symbol.replace("/", ""), "symbol": symbol})

    def parse_order(
        self, order: Mapping[str, Any], market: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        symbol = order.get("symbol") or (market["symbol"] if market else "BTC/USDT")
        if "/" not in str(symbol):
            for known_sym, meta in self.markets.items():
                if meta["id"] == symbol:
                    symbol = known_sym
                    break
        client_id = (
            order.get("clientOrderId")
            or order.get("orderLinkId")
            or order.get("client_order_id")
            or order.get("cl_ord_id")
            or ""
        )
        return {
            "id": str(order["id"]),
            "clientOrderId": str(client_id),
            "symbol": str(symbol),
            "side": str(order.get("side", "buy")).lower(),
            "type": str(order.get("type", "market")).lower(),
            "amount": float(order.get("amount", 0)),
            "filled": float(order.get("filled", 0)),
            "average": float(order["average"]) if order.get("average") is not None else None,
            "price": float(order["price"]) if order.get("price") is not None else None,
            "status": str(order.get("status", "open")).lower(),
        }

    def parse_trade(
        self, trade: Mapping[str, Any], market: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        symbol = trade.get("symbol") or (market["symbol"] if market else "BTC/USDT")
        return {
            "id": str(trade["id"]),
            "order": str(trade["order"]),
            "symbol": str(symbol),
            "side": str(trade["side"]).lower(),
            "amount": Decimal(str(trade["amount"])),
            "price": Decimal(str(trade["price"])),
            "fee": {
                "cost": Decimal(str(trade["fee"]["cost"])),
                "currency": str(trade["fee"]["currency"]),
            },
            "timestamp": int(trade["timestamp"]),
        }

    async def load_markets(self) -> dict[str, Any]:
        return dict(self.markets)

    async def close(self) -> None:
        return None

    async def fetch_balance(self, params: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return {"total": {asset: float(amount) for asset, amount in self.balances.items()}}

    def _execute_or_rest(
        self,
        *,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Decimal | None,
        client_id: str,
    ) -> dict[str, Any]:
        if client_id and client_id in self._orders_by_client_id:
            existing = self._orders_by_client_id[client_id]
            if (
                existing["symbol"] != symbol
                or existing["side"] != side.lower()
                or Decimal(str(existing["amount"])) != amount
            ):
                raise OrderConflictError("Sandbox client_order_id reused with different parameters")
            return existing

        mark = self.mark_prices[symbol]
        side_lower = side.lower()
        type_lower = order_type.lower()
        marketable = type_lower == "market" or (
            price is not None
            and (
                (side_lower == "buy" and price >= mark) or (side_lower == "sell" and price <= mark)
            )
        )
        order_id = self._next_id("ord")
        if not marketable:
            record: dict[str, Any] = {
                "id": order_id,
                "clientOrderId": client_id,
                "orderLinkId": client_id,
                "client_order_id": client_id,
                "cl_ord_id": client_id,
                "symbol": symbol,
                "side": side_lower,
                "type": type_lower,
                "amount": str(amount),
                "filled": "0",
                "average": None,
                "price": str(price) if price is not None else None,
                "status": "open",
            }
            self._orders_by_id[order_id] = record
            if client_id:
                self._orders_by_client_id[client_id] = record
            return record

        fill_price = mark
        if price is not None and type_lower == "limit":
            fill_price = min(mark, price) if side_lower == "buy" else max(mark, price)

        base, quote = currencies(symbol)
        with localcontext() as ctx:
            ctx.prec = 50
            notional = amount * fill_price
            fee_quote = (notional * self.fee_bps / Decimal("10000")).quantize(
                Decimal("0.00000001"), rounding=ROUND_DOWN
            )
            if side_lower == "buy":
                required_quote = notional + fee_quote
                if self.balances.get(quote, Decimal(0)) < required_quote:
                    raise ccxtpro.InsufficientFunds(f"Insufficient {quote} in sandbox")
                self.balances[quote] = self.balances.get(quote, Decimal(0)) - required_quote
                self.balances[base] = self.balances.get(base, Decimal(0)) + amount
            else:
                if self.balances.get(base, Decimal(0)) < amount:
                    raise ccxtpro.InsufficientFunds(f"Insufficient {base} in sandbox")
                self.balances[base] = self.balances.get(base, Decimal(0)) - amount
                self.balances[quote] = self.balances.get(quote, Decimal(0)) + (notional - fee_quote)

        self._clock_ms += 10
        trade_id = self._next_id("trd")
        trade_record: dict[str, Any] = {
            "id": trade_id,
            "order": order_id,
            "symbol": symbol,
            "side": side_lower,
            "amount": str(amount),
            "price": str(fill_price),
            "fee": {"cost": str(fee_quote), "currency": quote},
            "timestamp": self._clock_ms,
            "margin": "0",
        }
        self._trades.append(trade_record)

        record = {
            "id": order_id,
            "clientOrderId": client_id,
            "orderLinkId": client_id,
            "client_order_id": client_id,
            "cl_ord_id": client_id,
            "symbol": symbol,
            "side": side_lower,
            "type": type_lower,
            "amount": str(amount),
            "filled": str(amount),
            "average": str(fill_price),
            "price": str(price if price is not None else fill_price),
            "status": "closed",
        }
        self._orders_by_id[order_id] = record
        if client_id:
            self._orders_by_client_id[client_id] = record
        return record

    async def create_market_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        client_id = self._extract_client_id(params)
        return self._execute_or_rest(
            symbol=symbol,
            order_type="market",
            side=side,
            amount=Decimal(str(amount)),
            price=None,
            client_id=client_id,
        )

    async def create_limit_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        client_id = self._extract_client_id(params)
        return self._execute_or_rest(
            symbol=symbol,
            order_type="limit",
            side=side,
            amount=Decimal(str(amount)),
            price=Decimal(str(price)),
            client_id=client_id,
        )

    async def cancel_order(
        self,
        id: str,
        symbol: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if id not in self._orders_by_id:
            raise ccxtpro.OrderNotFound(f"Order {id} not found on {symbol}")
        record = self._orders_by_id[id]
        if not self.block_cancellation and record["status"] == "open":
            record["status"] = "canceled"
        return record

    async def cancel_all_orders(
        self,
        symbol: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        cancelled: list[dict[str, Any]] = []
        for record in self._orders_by_id.values():
            if record["status"] == "open" and (symbol is None or record["symbol"] == symbol):
                if not self.block_cancellation:
                    record["status"] = "canceled"
                cancelled.append(record)
        return cancelled

    async def fetch_order(
        self,
        id: str,
        symbol: str | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if id and id in self._orders_by_id:
            return self._orders_by_id[id]
        orig_client = (params or {}).get("origClientOrderId")
        if orig_client and str(orig_client) in self._orders_by_client_id:
            return self._orders_by_client_id[str(orig_client)]
        raise ccxtpro.OrderNotFound(f"Order not found: id={id} params={params}")

    async def fetch_open_orders(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        return [
            o
            for o in self._orders_by_id.values()
            if o["status"] == "open" and (symbol is None or o["symbol"] == symbol)
        ]

    async def fetch_my_trades(
        self,
        symbol: str | None = None,
        since: int | None = None,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        until = int((params or {}).get("until", 9_999_999_999_999))
        low = since if since is not None else 0
        rows = [
            t
            for t in self._trades
            if (symbol is None or t["symbol"] == symbol) and low <= int(t["timestamp"]) <= until
        ]
        return rows[:limit] if limit else rows

    async def fetch_ticker(
        self, symbol: str, params: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        mark = float(self.mark_prices[symbol])
        return {"symbol": symbol, "bid": mark, "ask": mark, "last": mark}

    async def fetch_order_book(
        self,
        symbol: str,
        limit: int | None = None,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        mark = float(self.mark_prices[symbol])
        return {"bids": [[mark, 10.0]], "asks": [[mark, 10.0]], "timestamp": self._clock_ms}

    async def fetch_ohlcv(
        self, symbol: str, timeframe: str = "1h", limit: int = 200
    ) -> list[list[Any]]:
        return []

    async def watch_ticker(self, symbol: str) -> dict[str, Any]:
        return await self.fetch_ticker(symbol)

    async def watch_order_book(self, symbol: str, limit: int = 20) -> dict[str, Any]:
        return await self.fetch_order_book(symbol, limit=limit)

    async def watch_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        return list(self._orders_by_id.values())

    # ── Venue-Specific Implicit REST Endpoints ────────────────────────────────

    async def privateGetV5OrderRealtime(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        order_id = params.get("orderId")
        link_id = params.get("orderLinkId")
        if order_id and str(order_id) in self._orders_by_id:
            row = self._orders_by_id[str(order_id)]
            return {"result": {"list": [row] if row["status"] == "open" else []}}
        if link_id and str(link_id) in self._orders_by_client_id:
            row = self._orders_by_client_id[str(link_id)]
            return {"result": {"list": [row] if row["status"] == "open" else []}}
        opens = [o for o in self._orders_by_id.values() if o["status"] == "open"]
        return {"result": {"list": opens, "nextPageCursor": ""}}

    async def privateGetV5OrderHistory(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        order_id = params.get("orderId")
        link_id = params.get("orderLinkId")
        if order_id and str(order_id) in self._orders_by_id:
            return {"result": {"list": [self._orders_by_id[str(order_id)]]}}
        if link_id and str(link_id) in self._orders_by_client_id:
            return {"result": {"list": [self._orders_by_client_id[str(link_id)]]}}
        return {"result": {"list": []}}

    async def privateGetV5ExecutionList(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        start_ms = int(params.get("startTime", 0))
        end_ms = int(params.get("endTime", 9_999_999_999_999))
        rows = [t for t in self._trades if start_ms <= int(t["timestamp"]) <= end_ms]
        return {"result": {"list": rows, "nextPageCursor": ""}}

    async def v3PrivateGetBrokerageOrdersHistoricalBatch(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        statuses = params.get("order_status")
        if statuses == ["OPEN"]:
            orders = [o for o in self._orders_by_id.values() if o["status"] == "open"]
        else:
            orders = list(self._orders_by_id.values())
        return {"orders": orders, "has_next": False, "cursor": ""}

    async def v3PrivateGetBrokerageOrdersHistoricalFills(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {"fills": list(self._trades), "cursor": ""}

    async def privatePostOpenOrders(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        cl_id = params.get("cl_ord_id")
        open_map = {
            oid: o
            for oid, o in self._orders_by_id.items()
            if o["status"] == "open" and (not cl_id or o.get("cl_ord_id") == cl_id)
        }
        return {"result": {"open": open_map}}

    async def privatePostClosedOrders(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        closed_map = {oid: o for oid, o in self._orders_by_id.items() if o["status"] != "open"}
        return {"result": {"closed": closed_map, "count": len(closed_map)}}

    async def privatePostTradesHistory(  # noqa: N802
        self, params: Mapping[str, Any]
    ) -> dict[str, Any]:
        trades_map = {t["id"]: t for t in self._trades}
        return {"result": {"trades": trades_map, "count": len(trades_map)}}


class BrokerConformanceSuite:
    """Executes TWAP and emergency flatten conformance against an external sandbox adapter."""

    def __init__(
        self,
        adapter: SpotRecoveryAdapter,
        *,
        scope: AccountScope,
        opening_balances: dict[str, Decimal],
        tolerances: dict[str, Decimal] | None = None,
        book_id: str = "paper_trading:conformance",
    ) -> None:
        self.adapter = adapter
        self.scope = scope
        self.book_id = book_id
        self.tolerances = tolerances or {}
        opening = OpeningBalances(
            as_of=datetime.now(UTC),
            reference="sandbox-conformance",
            cash=[
                CashBalance(
                    exchange=scope.exchange,
                    account_id=scope.account_id,
                    currency=currency,
                    amount=amount,
                )
                for currency, amount in sorted(opening_balances.items())
            ],
            positions=[],
        )
        self.book = BookState.from_opening(opening)
        self._seen_trade_keys: set[tuple[str, str, str, str]] = set()

    async def reconcile_fills(self, symbol: str, start_ms: int = 0) -> list[Fill]:
        """Paginate fills from the external broker and apply new fills to synthetic BookState."""
        now_ms = int(datetime.now(UTC).timestamp() * 1000) + 60_000
        cursor: dict[str, Any] | None = None
        applied: list[Fill] = []
        for _ in range(50):
            page = await self.adapter.history_page(symbol, start_ms, now_ms, cursor)
            for fill in page.fills:
                key_tuple = identity(fill)
                if key_tuple not in self._seen_trade_keys:
                    self._seen_trade_keys.add(key_tuple)
                    apply_fill(self.book, fill)
                    applied.append(fill)
            if page.cursor is None:
                break
            cursor = page.cursor
        return applied

    def build_twap_slices(
        self,
        parent: Order,
        *,
        mark_price: Decimal,
    ) -> list[Order]:
        """Decompose a parent TWAP order into deterministic child limit orders."""
        if parent.order_type != OrderType.TWAP:
            raise ValueError("Parent order must have OrderType.TWAP")
        num_slices = int(parent.algo_params.get("num_slices", 3))
        if num_slices < 1:
            raise ValueError("TWAP num_slices must be >= 1")
        rules = self.scope.market_rules.get(parent.symbol)
        if rules is None:
            raise RecoveryBlockedError("TWAP conformance requires InstrumentRules for symbol")

        raw_price = mark_price
        if parent.price is not None:
            raw_price = (
                min(mark_price, parent.price)
                if parent.side == OrderSide.BUY
                else max(mark_price, parent.price)
            )
        rounding = ROUND_DOWN if parent.side == OrderSide.BUY else ROUND_UP
        slice_price = (raw_price / rules.tick_size).to_integral_value(
            rounding=rounding
        ) * rules.tick_size

        allocated = Decimal(0)
        children: list[Order] = []
        for index in range(num_slices):
            remaining = parent.size - allocated
            size = (
                remaining
                if index == num_slices - 1
                else (parent.size / Decimal(num_slices) / rules.quantity_step).to_integral_value(
                    rounding=ROUND_DOWN
                )
                * rules.quantity_step
            )
            rules.validate_order(size, slice_price)
            allocated += size
            child_id = uuid5(parent.client_order_id, f"twap-slice:{index}")
            children.append(
                Order(
                    accounting_book_id=self.book_id,
                    authorization_id=parent.authorization_id,
                    order_id=child_id,
                    client_order_id=child_id,
                    proposal_id=parent.proposal_id,
                    symbol=parent.symbol,
                    exchange=self.scope.exchange,
                    account_id=self.scope.account_id,
                    side=parent.side,
                    order_type=OrderType.LIMIT,
                    size=size,
                    price=slice_price,
                    strategy_id=parent.strategy_id,
                    agent_id=parent.agent_id,
                    algo_params={"parent_id": str(parent.client_order_id), "slice": index},
                )
            )
        return children

    async def run_full_conformance(
        self,
        *,
        twap_parent: Order,
        mark_price: Decimal,
        resting_limit_order: Order,
        flatten_operation_id: UUID,
    ) -> ConformanceReport:
        """Execute TWAP slices, resting order placement, and halted emergency flatten."""
        children = self.build_twap_slices(twap_parent, mark_price=mark_price)
        twap_filled = Decimal(0)

        for idx, child in enumerate(children):
            placed = await self.adapter.place(child)
            # Verify lost-response client_order_id lookup on the first slice
            lookup_probe = (
                child.model_copy(update={"exchange_order_id": None}) if idx == 0 else placed
            )
            verified = await self.adapter.lookup(lookup_probe)
            if verified is None or verified.status != OrderStatus.FILLED:
                raise RecoveryBlockedError("TWAP child slice did not fill or failed lookup")
            twap_filled += verified.filled_size

        twap_fills = await self.reconcile_fills(twap_parent.symbol)
        broker_after_twap = await self.adapter.balances()
        expected_after_twap = native_balances(self.book).get(self.scope.key, {})
        diffs_after_twap = balance_differences(
            expected_after_twap, broker_after_twap, self.tolerances
        )
        if diffs_after_twap:
            raise RecoveryBlockedError(
                f"TWAP balance divergence between broker and synthetic book: {diffs_after_twap}"
            )

        # Submit a non-marketable resting limit order to verify flatten cancels pending orders
        resting_placed = await self.adapter.place(resting_limit_order)
        if resting_placed.status != OrderStatus.OPEN:
            raise RecoveryBlockedError("Expected non-marketable limit order to rest OPEN")

        flatten_result = await self.adapter.flatten(
            flatten_operation_id,
            symbols=[twap_parent.symbol],
            market_rules=self.scope.market_rules,
            reference_prices={twap_parent.symbol: mark_price},
            halted=True,
            book_id=self.book_id,
        )
        flatten_fills = await self.reconcile_fills(twap_parent.symbol)

        final_broker_balances = await self.adapter.balances()
        final_book_balances = native_balances(self.book).get(self.scope.key, {})
        final_diffs = balance_differences(
            final_book_balances, final_broker_balances, self.tolerances
        )
        if final_diffs:
            raise RecoveryBlockedError(
                f"Post-flatten balance divergence between broker and synthetic book: {final_diffs}"
            )

        return ConformanceReport(
            exchange=self.scope.exchange,
            account_id=self.scope.account_id,
            symbol=twap_parent.symbol,
            twap_slices_executed=len(children),
            twap_total_filled=twap_filled,
            resting_orders_cancelled=int(flatten_result["cancelled"]),
            flatten_orders_executed=len(flatten_result["orders"]),
            fills_reconciled=len(twap_fills) + len(flatten_fills),
            broker_balances=final_broker_balances,
            synthetic_book_balances=final_book_balances,
            balance_differences=final_diffs,
            flat=bool(flatten_result["flat"]) and not self.book.positions,
        )


def build_sandbox_adapter(
    exchange: Exchange,
    *,
    initial_balances: dict[str, Decimal],
    mark_prices: dict[str, Decimal],
    fee_bps: Decimal = Decimal("10"),
    account_id: str = "default",
) -> tuple[SpotRecoveryAdapter, ExternalSandboxBroker]:
    """Create a connected ExchangeConnector + SpotRecoveryAdapter backed by ExternalSandboxBroker."""
    connector = ExchangeConnector(exchange, account_id=account_id, sandbox=True)
    sandbox = ExternalSandboxBroker(
        exchange,
        initial_balances=initial_balances,
        mark_prices=mark_prices,
        fee_bps=fee_bps,
        account_id=account_id,
    )
    sandbox.set_sandbox_mode(True)
    connector._client = sandbox
    return SpotRecoveryAdapter(connector), sandbox
