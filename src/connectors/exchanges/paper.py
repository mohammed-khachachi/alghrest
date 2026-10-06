"""Persistent spot paper venue; never calls a private exchange API.

Market/crossing limit orders fill at the latest fresh cached mark with an
explicit quote-currency fee. Non-crossing limits remain open across restarts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from core.accounting.models import BookState, currencies
from core.accounting.valuation import Valuation
from core.config import settings
from core.data.models import Fill, FillFee, Order, OrderSide, OrderStatus, OrderType
from core.execution.contracts import AccountScope, OrderConflictError, TradePage, native_balances
from core.execution.store import ExecutionStore, order_fingerprint


class PaperVenue:
    def __init__(
        self,
        store: ExecutionStore,
        account: AccountScope,
        state: Any,
        fee_bps: Decimal = Decimal("10"),
    ) -> None:
        self.store, self.account, self.state, self.fee_bps = store, account, state, fee_bps

    async def initialize(self) -> None:
        settings.require_order_execution()
        async with self.store.ledger.locked_state() as (conn, _book, opening):
            balances = native_balances(BookState.from_opening(opening)).get(self.account.key, {})
            if any(value < 0 for value in balances.values()):
                raise ValueError("Spot paper opening cannot contain borrowed assets")
            await conn.execute(
                """INSERT INTO execution.paper_accounts(book_id,exchange,account_id,balances)
                   VALUES($1,$2,$3,$4::jsonb) ON CONFLICT DO NOTHING""",
                self.store.book_id,
                self.account.exchange.value,
                self.account.account_id,
                json.dumps({c: str(v) for c, v in balances.items()}),
            )

    async def balances(self) -> dict[str, Decimal]:
        raw = await self.store.pool.fetchval(
            "SELECT balances FROM execution.paper_accounts WHERE book_id=$1 AND exchange=$2 AND account_id=$3",
            self.store.book_id,
            self.account.exchange.value,
            self.account.account_id,
        )
        if raw is None:
            raise RuntimeError("Paper opening account missing")
        return {c: Decimal(v) for c, v in json.loads(raw).items()}

    async def place(self, order: Order) -> Order:
        settings.require_order_execution()
        if (
            order.exchange != self.account.exchange
            or order.account_id != self.account.account_id
            or order.symbol not in self.account.symbols
        ):
            raise ValueError("Order outside paper scope")
        if order.order_type not in (OrderType.MARKET, OrderType.LIMIT) or order.size <= 0:
            raise ValueError("Paper venue supports positive spot market/limit orders")
        if order.order_type == OrderType.LIMIT and (order.price is None or order.price <= 0):
            raise ValueError("Limit order requires a positive price")
        async with self.store.pool.acquire() as conn, conn.transaction():
            await conn.fetchval(
                "SELECT balances FROM execution.paper_accounts WHERE book_id=$1 AND exchange=$2 AND account_id=$3 FOR UPDATE",
                self.store.book_id,
                self.account.exchange.value,
                self.account.account_id,
            )
            raw = await conn.fetchval(
                "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2",
                self.store.book_id,
                order.client_order_id,
            )
            if raw:
                previous = Order.model_validate_json(raw)
                if order_fingerprint(previous) != order_fingerprint(order):
                    raise OrderConflictError("Paper client ID reused")
            else:
                previous = order.model_copy(
                    update={
                        "exchange_order_id": f"paper-{order.client_order_id}",
                        "status": OrderStatus.OPEN,
                    }
                )
                await conn.execute(
                    "INSERT INTO execution.paper_orders(book_id,client_order_id,payload) VALUES($1,$2,$3::jsonb)",
                    self.store.book_id,
                    order.client_order_id,
                    previous.model_dump_json(),
                )
        result = await self.lookup(previous)
        assert result is not None
        return result

    async def lookup(self, order: Order) -> Order | None:
        settings.require_order_execution()
        with localcontext() as ctx:
            ctx.prec = 50
            async with self.store.pool.acquire() as conn, conn.transaction():
                account_raw = await conn.fetchval(
                    "SELECT balances FROM execution.paper_accounts WHERE book_id=$1 AND exchange=$2 AND account_id=$3 FOR UPDATE",
                    self.store.book_id,
                    self.account.exchange.value,
                    self.account.account_id,
                )
                raw = await conn.fetchval(
                    "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2",
                    self.store.book_id,
                    order.client_order_id,
                )
                if raw is None:
                    return None
                result = Order.model_validate_json(raw)
                if result.status != OrderStatus.OPEN:
                    return result
                price = await Valuation(self.state, datetime.now(UTC), []).mark(
                    self.account.exchange.value, result.symbol
                )
                if result.order_type == OrderType.LIMIT:
                    assert result.price is not None
                if (
                    result.order_type == OrderType.LIMIT
                    and result.price is not None
                    and (
                        (result.side == OrderSide.BUY and price > result.price)
                        or (result.side == OrderSide.SELL and price < result.price)
                    )
                ):
                    return result
                balances = {c: Decimal(v) for c, v in json.loads(account_raw).items()}
                base, quote = currencies(result.symbol)
                fee = result.size * price * self.fee_bps / Decimal(10000)
                quantity = result.size if result.side == OrderSide.BUY else -result.size
                quote_change = -quantity * price - fee
                enough = (
                    balances.get(base, Decimal(0)) + quantity >= 0
                    and balances.get(quote, Decimal(0)) + quote_change >= 0
                )
                if not enough:
                    result = result.model_copy(update={"status": OrderStatus.REJECTED})
                else:
                    balances[base] = balances.get(base, Decimal(0)) + quantity
                    balances[quote] = balances.get(quote, Decimal(0)) + quote_change
                    result = result.model_copy(
                        update={
                            "status": OrderStatus.FILLED,
                            "filled_size": result.size,
                            "avg_fill_price": price,
                            "fees": fee,
                        }
                    )
                    assert result.exchange_order_id is not None
                    fill = Fill(
                        fill_id=uuid5(
                            NAMESPACE_URL, f"{self.store.book_id}:{result.client_order_id}"
                        ),
                        order_id=result.order_id,
                        exchange_order_id=result.exchange_order_id,
                        exchange_trade_id=f"paper-{result.client_order_id}",
                        account_id=result.account_id,
                        symbol=result.symbol,
                        exchange=result.exchange,
                        side=result.side,
                        fill_size=result.size,
                        fill_price=price,
                        fee=fee,
                        fee_currency=quote,
                        fees=[FillFee(currency=quote, amount=fee)],
                        timestamp=datetime.now(UTC),
                        strategy_id=result.strategy_id,
                        agent_id=result.agent_id,
                    )
                    await conn.execute(
                        "INSERT INTO execution.paper_fills(book_id,exchange,account_id,symbol,payload) VALUES($1,$2,$3,$4,$5::jsonb)",
                        self.store.book_id,
                        self.account.exchange.value,
                        self.account.account_id,
                        result.symbol,
                        fill.model_dump_json(),
                    )
                    await conn.execute(
                        "UPDATE execution.paper_accounts SET balances=$4::jsonb WHERE book_id=$1 AND exchange=$2 AND account_id=$3",
                        self.store.book_id,
                        self.account.exchange.value,
                        self.account.account_id,
                        json.dumps({c: str(v) for c, v in balances.items()}),
                    )
                await conn.execute(
                    "UPDATE execution.paper_orders SET payload=$3::jsonb WHERE book_id=$1 AND client_order_id=$2",
                    self.store.book_id,
                    result.client_order_id,
                    result.model_dump_json(),
                )
                return result

    async def cancel(self, order: Order) -> None:
        # Serialize with matching; a completed fill cannot be overwritten by cancel.
        settings.require_order_execution()
        async with self.store.pool.acquire() as conn, conn.transaction():
            await conn.fetchval(
                "SELECT balances FROM execution.paper_accounts WHERE book_id=$1 AND exchange=$2 AND account_id=$3 FOR UPDATE",
                self.store.book_id,
                self.account.exchange.value,
                self.account.account_id,
            )
            raw = await conn.fetchval(
                "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2 FOR UPDATE",
                self.store.book_id,
                order.client_order_id,
            )
            result = Order.model_validate_json(raw)
            if result.status == OrderStatus.OPEN:
                result.status = OrderStatus.CANCELLED
                await conn.execute(
                    "UPDATE execution.paper_orders SET payload=$3::jsonb WHERE book_id=$1 AND client_order_id=$2",
                    self.store.book_id,
                    order.client_order_id,
                    result.model_dump_json(),
                )

    async def open_orders(self) -> list[Order]:
        rows = await self.store.pool.fetch(
            """SELECT payload FROM execution.paper_orders WHERE book_id=$1
               AND payload->>'exchange'=$2 AND payload->>'account_id'=$3 AND payload->>'status'='OPEN'""",
            self.store.book_id,
            self.account.exchange.value,
            self.account.account_id,
        )
        return [Order.model_validate_json(row["payload"]) for row in rows]

    async def history_page(
        self, symbol: str, start_ms: int, end_ms: int, cursor: dict[str, Any] | None
    ) -> TradePage:
        after = int(cursor["after"]) if cursor else 0
        rows = await self.store.pool.fetch(
            """SELECT sequence,payload FROM execution.paper_fills WHERE book_id=$1 AND exchange=$2 AND account_id=$3
               AND ($4='*' OR symbol=$4) AND sequence>$5
               AND (payload->>'timestamp')::timestamptz >= to_timestamp($6::double precision/1000)
               AND (payload->>'timestamp')::timestamptz < to_timestamp(($7::double precision+1)/1000)
               ORDER BY sequence LIMIT 100""",
            self.store.book_id,
            self.account.exchange.value,
            self.account.account_id,
            symbol,
            after,
            start_ms,
            end_ms,
        )
        return TradePage(
            [Fill.model_validate_json(row["payload"]) for row in rows],
            {"after": rows[-1]["sequence"]} if len(rows) == 100 else None,
        )
