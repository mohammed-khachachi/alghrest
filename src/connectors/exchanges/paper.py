"""Persistent spot paper venue; never calls a private exchange API.

Market/crossing limit orders fill at the latest fresh cached mark with an
explicit quote-currency fee. Non-crossing limits remain open across restarts.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, localcontext
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from core.accounting.models import BookState, currencies
from core.accounting.valuation import Valuation
from core.config import settings
from core.data.models import Fill, FillFee, Order, OrderSide, OrderStatus, OrderType
from core.execution.contracts import (
    AccountScope,
    OrderConflictError,
    RecoveryBlockedError,
    TradePage,
    native_balances,
)
from core.execution.store import ExecutionStore, order_fingerprint
from core.risk.halt import halted as risk_halted


class PaperVenue:
    def __init__(
        self,
        store: ExecutionStore,
        account: AccountScope,
        state: Any,
        fee_bps: Decimal = Decimal("10"),
        *,
        max_fill_size: Decimal | None = None,
    ) -> None:
        self.store, self.account, self.state, self.fee_bps = store, account, state, fee_bps
        if max_fill_size is not None and (
            not max_fill_size.is_finite()
            or max_fill_size <= 0
            or any(symbol not in account.market_rules for symbol in account.symbols)
        ):
            raise RecoveryBlockedError(
                "Partial matching requires a positive cap and market metadata"
            )
        self.max_fill_size = max_fill_size

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
        from core.risk.halt import RiskHaltStore

        if order.accounting_book_id not in (None, self.store.book_id):
            raise RecoveryBlockedError("Order belongs to another paper book")
        # Native broker/position-management calls are bound by this adapter's
        # explicit book context; Kafka ingress separately rejects unscoped data.
        order = order.model_copy(update={"accounting_book_id": self.store.book_id})

        if (
            order.side == OrderSide.BUY
            and await RiskHaltStore(self.store.pool, self.store.book_id).is_active()
        ):
            raise RecoveryBlockedError("Persistent halt blocks new paper exposure")
        if (
            order.exchange != self.account.exchange
            or order.account_id != self.account.account_id
            or order.symbol not in self.account.symbols
        ):
            raise ValueError("Order outside paper scope")
        if (
            order.order_type not in (OrderType.MARKET, OrderType.LIMIT, OrderType.STOP)
            or order.size <= 0
        ):
            raise ValueError("Paper venue supports positive spot market/limit orders")
        if order.order_type == OrderType.LIMIT and (order.price is None or order.price <= 0):
            raise ValueError("Limit order requires a positive price")
        if order.stop_price is not None:
            rules = self.account.market_rules.get(order.symbol)
            if rules is None:
                raise RecoveryBlockedError("Protection requires explicit instrument metadata")
            reference = order.price or await Valuation(self.state, datetime.now(UTC), []).mark(
                self.account.exchange.value, order.symbol
            )
            rules.validate_order(order.size, order.stop_price)
            expected = OrderSide.SELL if order.order_type == OrderType.STOP else OrderSide.BUY
            if order.side != expected or order.stop_price >= reference:
                raise RecoveryBlockedError("Unsupported or incorrectly directed long-spot stop")
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
                # Matching itself is fenced, not just ingestion. A limit which
                # becomes marketable after a halt must be cancelled, not filled
                # as a side effect of recovery lookup.
                if result.side == OrderSide.BUY:
                    halted = await risk_halted(conn, self.store.book_id)
                    if halted:
                        result = result.model_copy(update={"status": OrderStatus.CANCELLED})
                        await conn.execute(
                            "UPDATE execution.paper_orders SET payload=$3::jsonb WHERE book_id=$1 AND client_order_id=$2",
                            self.store.book_id,
                            result.client_order_id,
                            result.model_dump_json(),
                        )
                        return result
                price = await Valuation(self.state, datetime.now(UTC), []).mark(
                    self.account.exchange.value, result.symbol
                )
                if result.side == OrderSide.BUY and result.stop_price is not None:
                    protected_raw = await conn.fetchval(
                        "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2",
                        self.store.book_id,
                        uuid5(result.client_order_id, "protective-stop"),
                    )
                    protection = Order.model_validate_json(protected_raw) if protected_raw else None
                    if price <= result.stop_price or (
                        protection is not None
                        and (protection.status != OrderStatus.OPEN or protection.filled_size > 0)
                    ):
                        result = result.model_copy(update={"status": OrderStatus.CANCELLED})
                        await conn.execute(
                            "UPDATE execution.paper_orders SET payload=$3::jsonb WHERE book_id=$1 AND client_order_id=$2",
                            self.store.book_id,
                            result.client_order_id,
                            result.model_dump_json(),
                        )
                        return result
                    if result.filled_size and (
                        protection is None
                        or protection.size != result.filled_size
                        or protection.stop_price != result.stop_price
                        or protection.side != OrderSide.SELL
                        or not protection.algo_params.get("reduce_only")
                    ):
                        raise RecoveryBlockedError(
                            "Partial entry protection is missing or inconsistent"
                        )
                if result.order_type == OrderType.STOP and (
                    result.stop_price is None or price > result.stop_price
                ):
                    return result
                if result.order_type == OrderType.STOP and result.algo_params.get("protection_for"):
                    parent_id = UUID(result.algo_params["protection_for"])
                    parent_raw = await conn.fetchval(
                        "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2",
                        self.store.book_id,
                        parent_id,
                    )
                    if parent_raw is None or result.client_order_id != uuid5(
                        parent_id, "protective-stop"
                    ):
                        raise RecoveryBlockedError("Protective stop has no verified parent")
                    parent = Order.model_validate_json(parent_raw)
                    if parent.status == OrderStatus.OPEN:
                        parent.status = OrderStatus.CANCELLED
                        await conn.execute(
                            "UPDATE execution.paper_orders SET payload=$3::jsonb WHERE book_id=$1 AND client_order_id=$2",
                            self.store.book_id,
                            parent_id,
                            parent.model_dump_json(),
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
                remaining = result.size - result.filled_size
                if remaining <= 0:
                    raise RecoveryBlockedError("Open paper order has no remaining quantity")
                executed_size = remaining
                if self.max_fill_size is not None:
                    step = self.account.market_rules[result.symbol].quantity_step
                    executed_size = (min(remaining, self.max_fill_size) / step).to_integral_value(
                        rounding=ROUND_DOWN
                    ) * step
                    if executed_size <= 0:
                        raise RecoveryBlockedError("Paper matching cap is below the quantity step")
                if result.side == OrderSide.SELL and result.algo_params.get("reduce_only"):
                    executed_size = min(
                        executed_size, max(Decimal(0), balances.get(base, Decimal(0)))
                    )
                    if not executed_size:
                        result = result.model_copy(update={"status": OrderStatus.CANCELLED})
                        await conn.execute(
                            "UPDATE execution.paper_orders SET payload=$3::jsonb WHERE book_id=$1 AND client_order_id=$2",
                            self.store.book_id,
                            result.client_order_id,
                            result.model_dump_json(),
                        )
                        return result
                fee = executed_size * price * self.fee_bps / Decimal(10000)
                quantity = executed_size if result.side == OrderSide.BUY else -executed_size
                quote_change = -quantity * price - fee
                enough = (
                    balances.get(base, Decimal(0)) + quantity >= 0
                    and balances.get(quote, Decimal(0)) + quote_change >= 0
                )
                if not enough:
                    result = result.model_copy(
                        update={
                            "status": (
                                OrderStatus.CANCELLED
                                if result.filled_size
                                else OrderStatus.REJECTED
                            )
                        }
                    )
                else:
                    previously_filled = result.filled_size
                    cumulative_size = previously_filled + executed_size
                    notional = (result.avg_fill_price or Decimal(0)) * previously_filled
                    balances[base] = balances.get(base, Decimal(0)) + quantity
                    balances[quote] = balances.get(quote, Decimal(0)) + quote_change
                    result = result.model_copy(
                        update={
                            "status": (
                                OrderStatus.FILLED
                                if cumulative_size == result.size
                                else (
                                    OrderStatus.CANCELLED
                                    if result.side == OrderSide.SELL
                                    and result.algo_params.get("reduce_only")
                                    and balances[base] == 0
                                    else OrderStatus.OPEN
                                )
                            ),
                            "filled_size": cumulative_size,
                            "avg_fill_price": (notional + price * executed_size) / cumulative_size,
                            "fees": result.fees + fee,
                        }
                    )
                    assert result.exchange_order_id is not None
                    # Keep the historical first-fill identity. Each subsequent
                    # match is keyed by the persisted cumulative starting size.
                    suffix = "" if not previously_filled else f":{previously_filled.normalize():f}"
                    fill = Fill(
                        accounting_book_id=self.store.book_id,
                        fill_id=uuid5(
                            NAMESPACE_URL, f"{self.store.book_id}:{result.client_order_id}{suffix}"
                        ),
                        order_id=result.order_id,
                        exchange_order_id=result.exchange_order_id,
                        exchange_trade_id=f"paper-{result.client_order_id}{suffix}",
                        account_id=result.account_id,
                        symbol=result.symbol,
                        exchange=result.exchange,
                        side=result.side,
                        fill_size=executed_size,
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
                    if result.side == OrderSide.BUY and result.stop_price is not None:
                        # Broker-side paper bundle: entry fill and standing stop
                        # commit together, not via a vulnerable post-fill callback.
                        stop_id = uuid5(result.client_order_id, "protective-stop")
                        stop = Order(
                            accounting_book_id=self.store.book_id,
                            authorization_id=result.authorization_id,
                            order_id=stop_id,
                            client_order_id=stop_id,
                            proposal_id=result.proposal_id,
                            symbol=result.symbol,
                            exchange=result.exchange,
                            account_id=result.account_id,
                            side=OrderSide.SELL,
                            order_type=OrderType.STOP,
                            size=cumulative_size,
                            stop_price=result.stop_price,
                            strategy_id=result.strategy_id,
                            agent_id=result.agent_id,
                            exchange_order_id=f"paper-{stop_id}",
                            status=OrderStatus.OPEN,
                            algo_params={
                                "reduce_only": True,
                                "protection_for": str(result.client_order_id),
                            },
                        )
                        await conn.execute(
                            "INSERT INTO execution.paper_orders(book_id,client_order_id,payload) VALUES($1,$2,$3::jsonb) ON CONFLICT(book_id,client_order_id) DO UPDATE SET payload=$3::jsonb",
                            self.store.book_id,
                            stop_id,
                            stop.model_dump_json(),
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
            balances_raw = await conn.fetchval(
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
                base, _quote = currencies(result.symbol)
                if (
                    result.order_type == OrderType.STOP
                    and result.algo_params.get("protection_for")
                    and Decimal(json.loads(balances_raw).get(base, "0")) > 0
                ):
                    from core.risk.halt import RiskHaltStore

                    await RiskHaltStore(
                        self.store.pool, self.store.book_id
                    ).activate_in_transaction(
                        conn,
                        "protective order cancelled with remaining exposure",
                        actor="paper-protection",
                    )
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

    async def maintain_protection(self) -> None:
        for order in await self.open_orders():
            if order.order_type == OrderType.STOP:
                base, _quote = currencies(order.symbol)
                if (await self.balances()).get(base, Decimal(0)) == 0:
                    await self.cancel(order)
                else:
                    await self.lookup(order)

    async def verify_protection(self, order: Order) -> bool:
        from uuid import UUID

        parent_id = order.algo_params.get("protection_for")
        if not parent_id or order.order_type != OrderType.STOP:
            return False
        parent_raw = await self.store.pool.fetchval(
            "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2",
            self.store.book_id,
            UUID(parent_id),
        )
        if parent_raw is None:
            return False
        parent = Order.model_validate_json(parent_raw)
        return (
            order.client_order_id == uuid5(parent.client_order_id, "protective-stop")
            and order.side == OrderSide.SELL
            and parent.side == OrderSide.BUY
            and order.stop_price == parent.stop_price
            and order.size == parent.filled_size
            and order.symbol == parent.symbol
            and order.account_id == parent.account_id
            and order.exchange == parent.exchange
            and bool(order.algo_params.get("reduce_only"))
        )

    async def cancel_pending(self, *, preserve_flatten_operation: UUID | None = None) -> int:
        """Cancellation is only cancellation; it makes no claim about inventory."""

        def preserved(order: Order) -> bool:
            return (
                preserve_flatten_operation is not None
                and order.strategy_id == "emergency_flatten"
                and bool(order.algo_params.get("reduce_only"))
                and order.algo_params.get("flatten_operation") == str(preserve_flatten_operation)
            )

        pending = [order for order in await self.open_orders() if not preserved(order)]
        for order in pending:
            await self.cancel(order)
        if any(not preserved(order) for order in await self.open_orders()):
            raise RecoveryBlockedError("Pending order cancellation is not confirmed")
        return len(pending)

    async def flatten(self, operation_id: Any) -> dict[str, Any]:
        """Reconcile native inventory and close only what exists, while halted.

        Stable operator operation IDs and account-row locking prevent repeated
        or concurrent closes from reversing a spot position. This is a paper
        broker operation, not permission for the advisory API or live adapters.
        """
        from uuid import UUID

        from core.risk.halt import RiskHaltStore

        settings.require_order_execution()
        if not await RiskHaltStore(self.store.pool, self.store.book_id).is_active():
            raise RecoveryBlockedError("Emergency flatten requires a persistent halt")
        operation_id = UUID(str(operation_id))
        cancelled = await self.cancel_pending(preserve_flatten_operation=operation_id)
        for symbol in self.account.symbols:
            base, _quote = currencies(symbol)
            size = (await self.balances()).get(base, Decimal(0))
            if size < 0:
                raise RecoveryBlockedError("Borrowed spot inventory cannot be flattened here")
            if not size:
                continue
            rules = self.account.market_rules.get(symbol)
            if rules is None:
                raise RecoveryBlockedError("Flatten requires explicit instrument metadata")
            mark = await Valuation(self.state, datetime.now(UTC), []).mark(
                self.account.exchange.value, symbol
            )
            rules.validate_order(size, mark)
            close_id = uuid5(operation_id, f"{self.store.book_id}:{self.account.key}:{symbol}")
            previous = await self.store.pool.fetchval(
                "SELECT payload FROM execution.paper_orders WHERE book_id=$1 AND client_order_id=$2",
                self.store.book_id,
                close_id,
            )
            close = (
                Order.model_validate_json(previous)
                if previous
                else Order(
                    accounting_book_id=self.store.book_id,
                    order_id=close_id,
                    client_order_id=close_id,
                    symbol=symbol,
                    exchange=self.account.exchange,
                    account_id=self.account.account_id,
                    side=OrderSide.SELL,
                    order_type=OrderType.MARKET,
                    size=size,
                    strategy_id="emergency_flatten",
                    agent_id=26,
                    algo_params={"reduce_only": True, "flatten_operation": str(operation_id)},
                )
            )
            observed = await self.place(close)
            for _ in range(1000):
                if observed.status != OrderStatus.OPEN:
                    break
                previous_size = observed.filled_size
                following = await self.lookup(observed)
                if following is None or following.filled_size <= previous_size:
                    raise RecoveryBlockedError("Emergency close is not making confirmed progress")
                observed = following
        balances = await self.balances()
        flat = not await self.open_orders() and all(
            balances.get(currencies(symbol)[0], Decimal(0)) == 0 for symbol in self.account.symbols
        )
        if not flat:
            raise RecoveryBlockedError("Flatten incomplete; broker exposure remains")
        return {
            "flat": True,
            "cancelled_orders": cancelled,
            "book_id": self.store.book_id,
            "account": self.account.key,
            "balances": {k: str(v) for k, v in balances.items()},
            "observed_at": datetime.now(UTC).isoformat(),
        }

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
