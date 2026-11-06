"""Durable, serial paper TWAP intents; fills reconcile before the next slice."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any
from uuid import UUID, uuid5

from core.accounting.models import currencies
from core.accounting.valuation import Valuation
from core.config import settings
from core.data.models import KafkaTopic, Order, OrderSide, OrderStatus, OrderType
from core.execution.authorization import validate_authorization
from core.execution.contracts import (
    AccountScope,
    OrderConflictError,
    RecoveryBlockedError,
    native_balances,
)
from core.execution.store import ExecutionStore
from core.risk.halt import halted as risk_halted


class TwapScheduler:
    def __init__(self, store: ExecutionStore, state: Any) -> None:
        self.store, self.state = store, state

    async def start(self, parent: Order) -> None:
        settings.require_order_execution()
        if settings.is_live or parent.order_type != OrderType.TWAP:
            raise RecoveryBlockedError("Only paper TWAP is supported by this scheduler")
        slices = int(parent.algo_params.get("num_slices", 6))
        if not 1 <= slices <= 1000 or not parent.size.is_finite() or parent.size <= 0:
            raise ValueError("Invalid TWAP quantity/slices")
        body = parent.model_dump(mode="json", exclude={"created_at", "updated_at", "status"})
        digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        async with self.store.ledger.locked_state() as (conn, _book, _opening):
            halted = await risk_halted(conn, self.store.book_id)
            if halted:
                raise RecoveryBlockedError("TWAP plan blocked by persistent halt")
            previous = await conn.fetchval(
                "SELECT fingerprint FROM execution.plans WHERE book_id=$1 AND parent_id=$2",
                self.store.book_id,
                parent.client_order_id,
            )
            await validate_authorization(
                conn,
                self.store.book_id,
                parent,
                revision=_book.revision if previous is None else None,
            )
            if previous is None:
                await self.store.check_proposal_history(conn, parent)
            await conn.execute(
                """INSERT INTO execution.plans(book_id,parent_id,fingerprint,request,slices)
                   VALUES($1,$2,$3,$4::jsonb,$5) ON CONFLICT DO NOTHING""",
                self.store.book_id,
                parent.client_order_id,
                digest,
                parent.model_dump_json(),
                slices,
            )
            previous = await conn.fetchval(
                "SELECT fingerprint FROM execution.plans WHERE book_id=$1 AND parent_id=$2",
                self.store.book_id,
                parent.client_order_id,
            )
            if previous != digest:
                raise OrderConflictError("TWAP identity reused with changed economics")

    async def active(self) -> list[UUID]:
        rows = await self.store.pool.fetch(
            "SELECT parent_id FROM execution.plans WHERE book_id=$1 AND state='active'",
            self.store.book_id,
        )
        return [row["parent_id"] for row in rows]

    async def step(self, parent_id: UUID) -> Order | None:
        settings.require_order_execution()
        if settings.is_live:
            raise RecoveryBlockedError("Live TWAP is not enabled")
        async with self.store.ledger.locked_state() as (conn, book, _opening):
            plan = await conn.fetchrow(
                "SELECT * FROM execution.plans WHERE book_id=$1 AND parent_id=$2 FOR UPDATE",
                self.store.book_id,
                parent_id,
            )
            if plan is None or plan["state"] != "active":
                return None
            active_halt = await risk_halted(conn, self.store.book_id)
            if active_halt:
                return None
            parent = Order.model_validate_json(plan["request"])
            await validate_authorization(conn, self.store.book_id, parent)
            previous = await conn.fetchrow(
                """SELECT o.phase,o.current_order,s.client_order_id FROM execution.slices s
                   LEFT JOIN execution.orders o ON o.book_id=s.book_id AND o.client_order_id=s.client_order_id
                   WHERE s.book_id=$1 AND s.parent_id=$2 ORDER BY s.slice DESC LIMIT 1""",
                self.store.book_id,
                parent_id,
            )
            if previous:
                if previous["phase"] not in ("complete", "rejected"):
                    # Partial, open, missing, and uncertain children reserve their
                    # entire allocation. Never create a replacement identity.
                    if datetime.now(UTC) > plan["next_at"] + timedelta(seconds=120):
                        if previous["client_order_id"]:
                            await conn.execute(
                                "UPDATE execution.orders SET cancel_requested=true WHERE book_id=$1 AND client_order_id=$2",
                                self.store.book_id,
                                previous["client_order_id"],
                            )
                        await conn.execute(
                            "UPDATE execution.plans SET state='blocked',reason='child timeout; cancellation/reconciliation required' WHERE book_id=$1 AND parent_id=$2",
                            self.store.book_id,
                            parent_id,
                        )
                    return None
                observed = Order.model_validate_json(previous["current_order"])
                if observed.status != OrderStatus.FILLED:
                    await conn.execute(
                        "UPDATE execution.plans SET state='blocked',reason='child rejected or cancelled; reconciliation required' WHERE book_id=$1 AND parent_id=$2",
                        self.store.book_id,
                        parent_id,
                    )
                    return None
            if plan["next_slice"] >= plan["slices"]:
                await conn.execute(
                    "UPDATE execution.plans SET state='complete' WHERE book_id=$1 AND parent_id=$2",
                    self.store.book_id,
                    parent_id,
                )
                return None
            if plan["next_at"] > datetime.now(UTC):
                return None
            gate = await conn.fetchrow(
                "SELECT * FROM execution.books WHERE book_id=$1", self.store.book_id
            )
            if (
                not gate["ready"]
                or gate["verified_revision"] != book.revision
                or gate["verified_until"] <= datetime.now(UTC)
            ):
                return None
            accounts = [AccountScope.model_validate(a) for a in json.loads(gate["accounts"])]
            account = next(
                (
                    a
                    for a in accounts
                    if a.exchange == parent.exchange and a.account_id == parent.account_id
                ),
                None,
            )
            rules = account.market_rules.get(parent.symbol) if account else None
            if account is None or rules is None:
                raise RecoveryBlockedError("TWAP requires explicit instrument metadata")
            mark = await Valuation(self.state, datetime.now(UTC), []).mark(
                parent.exchange.value, parent.symbol
            )
            price = mark
            if parent.price is not None:
                price = (
                    min(mark, parent.price)
                    if parent.side == OrderSide.BUY
                    else max(mark, parent.price)
                )
            rounding = ROUND_DOWN if parent.side == OrderSide.BUY else ROUND_UP
            price = (price / rules.tick_size).to_integral_value(rounding=rounding) * rules.tick_size
            remaining = parent.size - plan["allocated"]
            size = (
                remaining
                if plan["next_slice"] == plan["slices"] - 1
                else (parent.size / plan["slices"] / rules.quantity_step).to_integral_value(
                    rounding=ROUND_DOWN
                )
                * rules.quantity_step
            )
            rules.validate_order(size, price)
            balances = native_balances(book).get(account.key, {})
            base, quote = currencies(parent.symbol)
            if (parent.side == OrderSide.SELL and size > balances.get(base, Decimal(0))) or (
                parent.side == OrderSide.BUY
                and size * price * (1 + settings.paper_fee_bps / Decimal(10000))
                > balances.get(quote, Decimal(0))
            ):
                raise RecoveryBlockedError("TWAP child exceeds reconciled available inventory/cash")
            if size > remaining:
                raise RecoveryBlockedError("TWAP allocation exceeds authorized quantity")
            index = plan["next_slice"]
            child_id = uuid5(parent.client_order_id, f"twap-slice:{index}")
            child = Order(
                accounting_book_id=self.store.book_id,
                authorization_id=parent.authorization_id,
                order_id=child_id,
                client_order_id=child_id,
                proposal_id=parent.proposal_id,
                symbol=parent.symbol,
                exchange=parent.exchange,
                account_id=parent.account_id,
                side=parent.side,
                order_type=OrderType.LIMIT,
                size=size,
                price=price,
                stop_price=parent.stop_price,
                strategy_id=parent.strategy_id,
                agent_id=parent.agent_id,
                algo_params={"parent_id": str(parent_id), "slice": index},
            )
            await conn.execute(
                "INSERT INTO execution.slices(book_id,parent_id,slice,client_order_id,request) VALUES($1,$2,$3,$4,$5::jsonb)",
                self.store.book_id,
                parent_id,
                index,
                child_id,
                child.model_dump_json(),
            )
            interval = int(parent.algo_params.get("slice_interval_seconds", 300))
            if not 0 <= interval <= 86400:
                raise ValueError("Invalid TWAP interval")
            await conn.execute(
                "UPDATE execution.plans SET next_slice=next_slice+1,allocated=allocated+$3,next_at=$4 WHERE book_id=$1 AND parent_id=$2",
                self.store.book_id,
                parent_id,
                size,
                datetime.now(UTC) + timedelta(seconds=interval),
            )
            await self.store._event(
                conn,
                f"twap:{parent_id}:{index}",
                KafkaTopic.ORDERS_PENDING,
                "ChildOrder",
                {**child.model_dump(mode="json"), "_child": True},
            )
            return child
