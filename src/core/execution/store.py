"""Atomic submission claims, durable delivery, recovery checkpoints and risk gate."""

from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from core.accounting.engine import fingerprint, identity
from core.accounting.models import key
from core.accounting.performance import load as load_performance
from core.accounting.repository import FillConflictError, Ledger
from core.data.models import Fill, KafkaTopic, Order, OrderStatus
from core.execution.authorization import validate_authorization
from core.execution.contracts import (
    TERMINAL,
    AccountScope,
    OrderConflictError,
    RecoveryBlockedError,
    balance_differences,
    native_balances,
)
from core.resilience import (
    DatabaseCircuitBreaker,
    DatabaseCircuitOpenError,
    ExponentialBackoffPolicy,
    is_transient_db_error,
)
from core.risk.halt import halted as risk_halted


def order_fingerprint(order: Order) -> str:
    fields = (
        "client_order_id",
        "order_id",
        "exchange",
        "account_id",
        "symbol",
        "side",
        "order_type",
        "size",
        "price",
        "stop_price",
        "time_in_force",
        "strategy_id",
        "agent_id",
    )
    data = order.model_dump(mode="json", include=set(fields))
    for name in ("size", "price", "stop_price"):
        if data[name] is not None:
            number = format(Decimal(data[name]), "f")
            data[name] = number.rstrip("0").rstrip(".") if "." in number else number
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class ExecutionStore:
    def __init__(
        self,
        ledger: Ledger,
        *,
        backoff: ExponentialBackoffPolicy | None = None,
        circuit_breaker: DatabaseCircuitBreaker | None = None,
    ) -> None:
        self.ledger = ledger
        self.pool = ledger.pool
        self.book_id = ledger.book_id
        self._lease: Any = None
        self._lease_lock = asyncio.Lock()
        self._writer_claimed = False
        self.backoff = backoff or ledger.backoff
        self.circuit_breaker = circuit_breaker or DatabaseCircuitBreaker(
            name=f"execution:{ledger.book_id}"
        )

    async def claim_writer(self) -> None:
        async with self._lease_lock:
            if self._lease is not None:
                raise RecoveryBlockedError("Execution writer lease already claimed")
            lease = await self.pool.acquire()
            lock = int.from_bytes(
                hashlib.sha256(f"execution:{self.book_id}".encode()).digest()[:8], signed=True
            )
            try:
                if not await lease.fetchval("SELECT pg_try_advisory_lock($1)", lock):
                    raise RecoveryBlockedError("Another executor owns this book")
            except BaseException:
                await self.pool.release(lease)
                raise
            self._lease = lease
            self._writer_claimed = True
            self.circuit_breaker.record_success()

    async def check_writer(self) -> None:
        async with self._lease_lock:
            if self._lease is None or self._lease.is_closed():
                raise RecoveryBlockedError("Execution writer lease lost")
            await self._lease.execute("SELECT 1")

    async def recover_writer(self) -> None:
        """Release a dropped writer session and re-acquire the book's advisory lock with backoff."""
        async with self._lease_lock:
            if not self._writer_claimed:
                raise RecoveryBlockedError("Execution writer lease lost")
            if self._lease is not None and not self._lease.is_closed():
                try:
                    await self._lease.execute("SELECT 1")
                    self.circuit_breaker.record_success()
                    return
                except BaseException as exc:
                    if not is_transient_db_error(exc):
                        raise
            if self._lease is not None:
                dead = self._lease
                self._lease = None
                with suppress(Exception):
                    await self.pool.release(dead)
            lock = int.from_bytes(
                hashlib.sha256(f"execution:{self.book_id}".encode()).digest()[:8], signed=True
            )

            async def _reacquire() -> Any:
                lease = await self.pool.acquire()
                try:
                    if not await lease.fetchval("SELECT pg_try_advisory_lock($1)", lock):
                        raise RecoveryBlockedError("Another executor owns this book")
                    return lease
                except BaseException:
                    with suppress(Exception):
                        await self.pool.release(lease)
                    raise

            try:
                self._lease = await self.backoff.run(
                    _reacquire,
                    circuit_breaker=self.circuit_breaker,
                    is_retryable=is_transient_db_error,
                )
            except DatabaseCircuitOpenError as exc:
                raise RecoveryBlockedError("Execution database circuit breaker open") from exc
            except BaseException as exc:
                if isinstance(exc, RecoveryBlockedError):
                    raise
                raise RecoveryBlockedError(
                    f"Execution writer lease recovery failed: {type(exc).__name__}"
                ) from exc

    async def ensure_writer(self) -> None:
        """Verify the active writer lease or recover it automatically on transient session loss."""
        try:
            self.circuit_breaker.check()
        except DatabaseCircuitOpenError as exc:
            raise RecoveryBlockedError("Execution database circuit breaker open") from exc
        try:
            await self.check_writer()
            self.circuit_breaker.record_success()
        except BaseException as exc:
            if not self._writer_claimed or not is_transient_db_error(exc):
                raise
            await self.recover_writer()

    async def close(self) -> None:
        async with self._lease_lock:
            self._writer_claimed = False
            if self._lease is not None:
                with suppress(Exception):
                    await self.pool.release(self._lease)
                self._lease = None
            await self.ledger.close()

    async def configure(self, accounts: list[AccountScope]) -> None:
        if not accounts or len({a.exchange for a in accounts}) != len(accounts):
            raise ValueError("Configure one explicit recovery account per exchange")
        config = json.dumps([a.model_dump(mode="json") for a in accounts], sort_keys=True)
        async with self.ledger.locked_state() as (conn, state, _opening):
            if set(native_balances(state)) - {a.key for a in accounts}:
                raise RecoveryBlockedError(
                    "Opening/current holdings include an unconfigured account"
                )
            await conn.execute(
                "INSERT INTO execution.books(book_id,accounts) VALUES($1,$2::jsonb) ON CONFLICT DO NOTHING",
                self.book_id,
                config,
            )
            saved = await conn.fetchval(
                "SELECT accounts FROM execution.books WHERE book_id=$1", self.book_id
            )
            normalized = [
                AccountScope.model_validate(a).model_dump(mode="json") for a in json.loads(saved)
            ]
            if normalized != json.loads(config):
                raise RecoveryBlockedError(
                    "Recovery account configuration differs from the durable book"
                )
            await self._block(conn, "executor starting/recovering")
            await conn.execute(
                """INSERT INTO safety.halts(book_id,active,reason)
                   VALUES($1,false,'explicit new-book initialization') ON CONFLICT DO NOTHING""",
                self.book_id,
            )

    async def _block(self, conn: Any, reason: str) -> None:
        await conn.execute(
            "UPDATE execution.books SET ready=false,report=$2::jsonb,updated_at=now() WHERE book_id=$1",
            self.book_id,
            json.dumps({"reason": reason}),
        )

    async def block(self, reason: str) -> None:
        async with self.ledger.locked_state() as (conn, _state, _opening):
            await self._block(conn, reason)

    async def _event(
        self, conn: Any, event_key: str, topic: KafkaTopic, kind: str, payload: dict[str, Any]
    ) -> None:
        await conn.execute(
            """INSERT INTO execution.outbox(book_id,event_key,topic,message_type,payload)
               VALUES($1,$2,$3,$4,$5::jsonb) ON CONFLICT DO NOTHING""",
            self.book_id,
            event_key,
            topic.value,
            kind,
            json.dumps(payload),
        )

    async def check_proposal_history(self, conn: Any, order: Order) -> None:
        """Fence pre-upgrade random IDs without changing their audit history.

        Call while holding the book row lock, before claiming a new root intent.
        TWAP children intentionally share a proposal and use their persisted plan.
        """
        if order.proposal_id is not None and await conn.fetchval(
            """SELECT EXISTS(SELECT 1 FROM execution.orders
               WHERE book_id=$1 AND request->>'proposal_id'=$2)""",
            self.book_id,
            str(order.proposal_id),
        ):
            raise RecoveryBlockedError(
                "Replayed proposal has historical execution; review required"
            )

    async def prepare(self, order: Order) -> bool:
        """Claim once before HTTP. Existing/uncertain intent can NEVER be resent."""
        digest = order_fingerprint(order)
        async with self.ledger.locked_state() as (conn, state, _opening):
            previous = await conn.fetchval(
                "SELECT fingerprint FROM execution.orders WHERE book_id=$1 AND client_order_id=$2",
                self.book_id,
                order.client_order_id,
            )
            if previous:
                if previous != digest:
                    raise OrderConflictError("Client order ID reused for different intent")
                return False
            await validate_authorization(conn, self.book_id, order, revision=state.revision)
            if not order.algo_params.get("parent_id"):
                await self.check_proposal_history(conn, order)
            halted = await risk_halted(conn, self.book_id)
            if halted:
                raise RecoveryBlockedError("Persistent risk halt or missing halt state")
            gate = await conn.fetchrow(
                "SELECT * FROM execution.books WHERE book_id=$1", self.book_id
            )
            if (
                not gate
                or not gate["ready"]
                or gate["verified_revision"] != state.revision
                or gate["verified_until"] <= datetime.now(UTC)
            ):
                raise RecoveryBlockedError("Portfolio reconciliation is missing, stale, or changed")
            performance = await load_performance(conn, self.book_id)
            if (
                performance is None
                or performance.book_id != self.book_id
                or performance.revision != state.revision
                or not 0 <= (datetime.now(UTC) - performance.observed_at).total_seconds() <= 15
            ):
                raise RecoveryBlockedError("Durable performance snapshot is missing or changed")
            accounts = [AccountScope.model_validate(a) for a in json.loads(gate["accounts"])]
            if not any(
                a.exchange == order.exchange
                and a.account_id == order.account_id
                and order.symbol in a.symbols
                for a in accounts
            ):
                raise RecoveryBlockedError("Order is outside the configured recovery scope")
            await conn.execute(
                """INSERT INTO execution.orders
                   (book_id,client_order_id,exchange,account_id,fingerprint,request,current_order,phase)
                   VALUES($1,$2,$3,$4,$5,$6::jsonb,$6::jsonb,'submitting')""",
                self.book_id,
                order.client_order_id,
                order.exchange.value,
                order.account_id,
                digest,
                order.model_dump_json(),
            )
            await self._block(conn, "order submission in progress")
            return True

    async def seen(self, order: Order) -> bool:
        previous = await self.pool.fetchval(
            "SELECT fingerprint FROM execution.orders WHERE book_id=$1 AND client_order_id=$2",
            self.book_id,
            order.client_order_id,
        )
        if previous and previous != order_fingerprint(order):
            raise OrderConflictError("Client order ID reused for different intent")
        return bool(previous)

    async def authorize(self, order: Order) -> None:
        async with self.ledger.locked_state() as (conn, _state, _opening):
            await validate_authorization(conn, self.book_id, order)

    async def deny(self, order: Order, reason: str) -> None:
        # Untrusted instructions must not reserve/poison a legitimate client ID.
        await self.pool.execute(
            """INSERT INTO execution.authorization_denials(book_id,proposal_id,client_order_id,reason)
               VALUES($1,$2,$3,$4)""",
            self.book_id,
            order.proposal_id,
            order.client_order_id,
            reason,
        )

    async def reject(self, order: Order, reason: str) -> None:
        rejected = order.model_copy(update={"status": OrderStatus.REJECTED})
        async with self.ledger.locked_state() as (conn, _state, _opening):
            existing = await conn.fetchval(
                "SELECT fingerprint FROM execution.orders WHERE book_id=$1 AND client_order_id=$2",
                self.book_id,
                order.client_order_id,
            )
            if existing:
                if existing != order_fingerprint(order):
                    raise OrderConflictError("Rejected request conflicts with durable intent")
                return
            await conn.execute(
                """INSERT INTO execution.orders(book_id,client_order_id,exchange,account_id,fingerprint,request,current_order,phase,error)
                   VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,'rejected',$8)""",
                self.book_id,
                order.client_order_id,
                order.exchange.value,
                order.account_id,
                order_fingerprint(order),
                order.model_dump_json(),
                rejected.model_dump_json(),
                reason,
            )
            await self._event(
                conn,
                f"rejected:{order.client_order_id}",
                KafkaTopic.ORDERS_EXECUTED,
                "OrderRejected",
                {**rejected.model_dump(mode="json"), "rejection_reason": reason},
            )

    async def abort_prepared(self, order: Order, reason: str) -> None:
        """Caller holds submission lock and has NOT invoked the venue yet."""
        rejected = order.model_copy(update={"status": OrderStatus.REJECTED})
        async with self.ledger.locked_state() as (conn, _state, _opening):
            changed = await conn.fetchval(
                """UPDATE execution.orders SET phase='rejected',current_order=$3::jsonb,error=$4
                   WHERE book_id=$1 AND client_order_id=$2 AND phase='submitting'
                   AND exchange_order_id IS NULL RETURNING client_order_id""",
                self.book_id,
                order.client_order_id,
                rejected.model_dump_json(),
                reason,
            )
            if changed is None:
                raise RecoveryBlockedError("Cannot abort an already attempted submission")
            await self._event(
                conn,
                f"rejected:{order.client_order_id}",
                KafkaTopic.ORDERS_EXECUTED,
                "OrderRejected",
                {**rejected.model_dump(mode="json"), "rejection_reason": reason},
            )
            await self._block(conn, reason)

    async def abort_if_unattempted(self, order: Order, reason: str) -> bool:
        """Idempotently abort a claim if a DB disconnect occurred before the venue was contacted."""
        rejected = order.model_copy(update={"status": OrderStatus.REJECTED})
        async with self.ledger.locked_state() as (conn, _state, _opening):
            row = await conn.fetchrow(
                """SELECT phase,exchange_order_id FROM execution.orders
                   WHERE book_id=$1 AND client_order_id=$2 FOR UPDATE""",
                self.book_id,
                order.client_order_id,
            )
            if row is None or row["phase"] == "rejected":
                return False
            if row["phase"] != "submitting" or row["exchange_order_id"] is not None:
                raise RecoveryBlockedError("Cannot abort an already attempted submission")
            await conn.execute(
                """UPDATE execution.orders SET phase='rejected',current_order=$3::jsonb,error=$4
                   WHERE book_id=$1 AND client_order_id=$2""",
                self.book_id,
                order.client_order_id,
                rejected.model_dump_json(),
                reason,
            )
            await self._event(
                conn,
                f"rejected:{order.client_order_id}",
                KafkaTopic.ORDERS_EXECUTED,
                "OrderRejected",
                {**rejected.model_dump(mode="json"), "rejection_reason": reason},
            )
            await self._block(conn, reason)
            return True

    async def uncertain(self, order: Order, reason: str) -> None:
        async with self.ledger.locked_state() as (conn, _state, _opening):
            await conn.execute(
                "UPDATE execution.orders SET phase='uncertain',error=$3,updated_at=now() WHERE book_id=$1 AND client_order_id=$2",
                self.book_id,
                order.client_order_id,
                reason,
            )
            await self._block(conn, "uncertain order submission")

    async def observe(self, requested: Order, observed: Order) -> Order:
        if (requested.exchange, requested.symbol, requested.side) != (
            observed.exchange,
            observed.symbol,
            observed.side,
        ):
            raise OrderConflictError("Recovered order does not match submitted intent")
        if (
            observed.size != requested.size
            or observed.filled_size < 0
            or observed.filled_size > requested.size
        ):
            raise OrderConflictError("Recovered order quantity conflicts with intent")
        merged = requested.model_copy(
            update={
                "exchange_order_id": observed.exchange_order_id,
                "status": observed.status,
                "filled_size": observed.filled_size,
                "avg_fill_price": observed.avg_fill_price,
                "updated_at": datetime.now(UTC).replace(tzinfo=None),
            }
        )
        async with self.ledger.locked_state() as (conn, _state, _opening):
            old = await conn.fetchrow(
                "SELECT current_order FROM execution.orders WHERE book_id=$1 AND client_order_id=$2",
                self.book_id,
                requested.client_order_id,
            )
            if old is None:
                raise RecoveryBlockedError("Order intent was not journaled")
            previous = Order.model_validate_json(old["current_order"])
            if (
                previous.exchange_order_id
                and previous.exchange_order_id != merged.exchange_order_id
            ):
                raise OrderConflictError("Exchange order ID changed for a durable intent")
            if not merged.exchange_order_id or merged.filled_size < previous.filled_size:
                raise OrderConflictError("Recovered order ID missing or filled quantity regressed")
            if merged.status == OrderStatus.FILLED and merged.filled_size != merged.size:
                raise OrderConflictError("Filled status does not cover submitted quantity")
            if previous.status in TERMINAL and merged.status not in TERMINAL:
                raise OrderConflictError("Terminal order returned to an active state")
            size = await conn.fetchval(
                """SELECT coalesce(sum((payload->>'fill_size')::numeric),0) FROM execution.fills
                   WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND exchange_order_id=$4""",
                self.book_id,
                requested.exchange.value,
                requested.account_id,
                merged.exchange_order_id,
            )
            complete = merged.status in TERMINAL and size >= merged.filled_size
            phase = "complete" if complete else "working"
            await conn.execute(
                """UPDATE execution.orders SET current_order=$3::jsonb,exchange_order_id=$4,
                   phase=$5,error=NULL,updated_at=now() WHERE book_id=$1 AND client_order_id=$2""",
                self.book_id,
                requested.client_order_id,
                merged.model_dump_json(),
                merged.exchange_order_id,
                phase,
            )
            event_key = f"order:{requested.client_order_id}:{merged.status}:{merged.filled_size}:{merged.exchange_order_id}"
            await self._event(
                conn,
                event_key,
                KafkaTopic.ORDERS_EXECUTED,
                "OrderStatusUpdate",
                merged.model_dump(mode="json"),
            )
            return merged

    async def orders(self) -> list[dict[str, Any]]:
        rows = await self.pool.fetch(
            "SELECT * FROM execution.orders WHERE book_id=$1 AND phase NOT IN ('complete','rejected') ORDER BY created_at",
            self.book_id,
        )
        return [dict(r) for r in rows]

    async def request_cancel(self, order: Order) -> None:
        await self.pool.execute(
            "UPDATE execution.orders SET cancel_requested=true WHERE book_id=$1 AND client_order_id=$2",
            self.book_id,
            order.client_order_id,
        )

    async def checkpoint(self, account: AccountScope, symbol: str) -> dict[str, Any]:
        await self.pool.execute(
            """INSERT INTO execution.cursors(book_id,exchange,account_id,symbol) VALUES($1,$2,$3,$4)
               ON CONFLICT DO NOTHING""",
            self.book_id,
            account.exchange.value,
            account.account_id,
            symbol,
        )
        row = await self.pool.fetchrow(
            "SELECT * FROM execution.cursors WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4",
            self.book_id,
            account.exchange.value,
            account.account_id,
            symbol,
        )
        result = dict(row)
        result["cursor"] = json.loads(result["cursor"]) if result["cursor"] else None
        return result

    async def capture_page(
        self,
        account: AccountScope,
        symbol: str,
        version: int,
        cursor: dict[str, Any] | None,
        through_ms: int,
        fills: list[Fill],
        last_full_ms: int | None = None,
    ) -> None:
        async with self.ledger.locked_state() as (conn, _state, _opening):
            actual = await conn.fetchval(
                "SELECT version FROM execution.cursors WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4 FOR UPDATE",
                self.book_id,
                account.exchange.value,
                account.account_id,
                symbol,
            )
            if actual != version:
                raise RecoveryBlockedError("Recovery cursor changed concurrently")
            for fill in fills:
                if fill.accounting_book_id not in (None, self.book_id):
                    raise ValueError("Recovered fill belongs to another accounting book")
                scope = identity(fill)
                if fill.exchange != account.exchange or fill.account_id != account.account_id:
                    raise ValueError("Fill belongs to another account")
                digest = fingerprint(fill)
                previous = await conn.fetchval(
                    "SELECT fingerprint FROM execution.fills WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4 AND trade_id=$5",
                    self.book_id,
                    *scope,
                )
                if previous:
                    if previous != digest:
                        raise FillConflictError("Recovered fill economics changed")
                    continue
                original = await conn.fetchval(
                    "SELECT request FROM execution.orders WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND exchange_order_id=$4",
                    self.book_id,
                    fill.exchange.value,
                    fill.account_id,
                    fill.exchange_order_id,
                )
                update: dict[str, Any] = {"accounting_book_id": self.book_id}
                if original:
                    order = Order.model_validate_json(original)
                    update.update(
                        order_id=order.order_id,
                        strategy_id=order.strategy_id,
                        agent_id=order.agent_id,
                    )
                fill = fill.model_copy(update=update)
                await conn.execute(
                    """INSERT INTO execution.fills(book_id,exchange,account_id,symbol,trade_id,exchange_order_id,fingerprint,payload)
                       VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb)""",
                    self.book_id,
                    *scope,
                    fill.exchange_order_id,
                    digest,
                    fill.model_dump_json(),
                )
                await self._event(
                    conn,
                    f"fill:{key(*scope)}",
                    KafkaTopic.FILLS_CONFIRMED,
                    "Fill",
                    fill.model_dump(mode="json"),
                )
            await conn.execute(
                """UPDATE execution.cursors SET version=version+1,cursor=$5::jsonb,through_ms=$6,
                   last_full_ms=coalesce($7,last_full_ms)
                   WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4""",
                self.book_id,
                account.exchange.value,
                account.account_id,
                symbol,
                json.dumps(cursor) if cursor else None,
                through_ms,
                last_full_ms,
            )
            await self._block(conn, "recovered fills awaiting reconciliation")

    async def outbox(self, *, include_execution_intents: bool = True) -> list[dict[str, Any]]:
        # Redeliver even previously acknowledged fills if the ledger lacks them
        # (consumer outage/retention); transport delivery is not ledger settlement.
        rows = await self.pool.fetch(
            """SELECT * FROM execution.outbox o WHERE book_id=$1
               AND ($2 OR topic<>ALL($3::text[])) AND
               (delivered_at IS NULL OR (message_type='Fill' AND NOT EXISTS (
                  SELECT 1 FROM accounting.fills f WHERE f.book_id=o.book_id
                  AND f.exchange=o.payload->>'exchange' AND f.account_id=o.payload->>'account_id'
                  AND f.symbol=o.payload->>'symbol' AND f.trade_id=o.payload->>'exchange_trade_id')))
               ORDER BY id LIMIT 500""",
            self.book_id,
            include_execution_intents,
            [KafkaTopic.ORDERS_PENDING.value, KafkaTopic.PROPOSALS_APPROVED.value],
        )
        return [dict(r) for r in rows]

    async def delivered(self, event_id: int) -> None:
        await self.pool.execute(
            "UPDATE execution.outbox SET delivered_at=now() WHERE id=$1 AND book_id=$2",
            event_id,
            self.book_id,
        )

    async def verify(
        self,
        accounts: list[AccountScope],
        balances: dict[str, dict[str, Decimal]],
        issues: list[str],
        tolerances: dict[str, Decimal],
        ttl: int,
    ) -> dict[str, Any]:
        async with self.ledger.locked_state() as (conn, state, _opening):
            reasons = list(issues)
            halted = await risk_halted(conn, self.book_id)
            if halted:
                reasons.append("persistent risk halt or missing halt state")
            performance = await load_performance(conn, self.book_id)
            if (
                performance is None
                or performance.book_id != self.book_id
                or performance.revision != state.revision
                or not 0 <= (datetime.now(UTC) - performance.observed_at).total_seconds() <= 15
            ):
                reasons.append("durable performance snapshot missing or changed")
            expected = native_balances(state)
            if set(expected) - {a.key for a in accounts}:
                reasons.append("ledger includes an unconfigured account")
            differences = {}
            for account in accounts:
                for symbol in ["*"] if account.exchange.value == "kraken" else account.symbols:
                    checkpoint = await conn.fetchrow(
                        "SELECT through_ms,cursor FROM execution.cursors WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4",
                        self.book_id,
                        account.exchange.value,
                        account.account_id,
                        symbol,
                    )
                    if (
                        checkpoint is None
                        or checkpoint["cursor"] is not None
                        or checkpoint["through_ms"]
                        < int((datetime.now(UTC) - timedelta(seconds=ttl)).timestamp() * 1000)
                    ):
                        reasons.append(f"history not caught up: {account.key} {symbol}")
                if account.key not in balances:
                    reasons.append(f"missing balance snapshot: {account.key}")
                    continue
                delta = balance_differences(
                    expected.get(account.key, {}), balances[account.key], tolerances
                )
                if delta:
                    differences[account.key] = delta
            if differences:
                reasons.append("exchange balances differ from ledger cash/positions")
            pending = await conn.fetchval(
                """SELECT count(*) FROM execution.fills e WHERE book_id=$1 AND NOT EXISTS (
                  SELECT 1 FROM accounting.fills f WHERE f.book_id=e.book_id AND f.exchange=e.exchange
                  AND f.account_id=e.account_id AND f.symbol=e.symbol AND f.trade_id=e.trade_id
                  AND f.fingerprint=e.fingerprint)""",
                self.book_id,
            )
            if pending:
                reasons.append(f"{pending} recovered fills not settled in ledger")
            if await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM execution.orders WHERE book_id=$1 AND phase NOT IN ('complete','rejected'))",
                self.book_id,
            ):
                reasons.append("open or uncertain orders remain")
            report = {
                "book_id": self.book_id,
                "ready": not reasons,
                "revision": state.revision,
                "checked_at": datetime.now(UTC).isoformat(),
                "reasons": reasons,
                "differences": differences,
            }
            await conn.execute(
                """UPDATE execution.books SET ready=$2,verified_revision=$3,verified_until=$4,
                   report=$5::jsonb,updated_at=now() WHERE book_id=$1""",
                self.book_id,
                not reasons,
                state.revision,
                datetime.now(UTC) + timedelta(seconds=ttl),
                json.dumps(report),
            )
            return report
