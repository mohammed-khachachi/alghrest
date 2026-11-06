"""Agent 26: journal intent before submission, recover by identity, reconcile.

PostgreSQL owns orders, fill delivery and history cursors. An uncertain create
is never retried. Development/paper use a persistent simulated exchange.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from agents.base_agent import BaseAgent
from connectors.exchanges.ccxt_connector import ExchangeConnector
from connectors.exchanges.paper import PaperVenue
from connectors.exchanges.recovery import SpotRecoveryAdapter
from core.accounting.models import key, utc
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import AgentConfig, Exchange, KafkaTopic, Order, OrderType
from core.execution.authorization import AuthorizationError
from core.execution.contracts import TERMINAL, OrderConflictError, RecoveryBlockedError
from core.execution.recovery import RecoveryCoordinator
from core.execution.store import ExecutionStore
from core.resilience import DatabaseCircuitOpenError, is_transient_db_error

_SUPPORTED_EXCHANGES = [Exchange.BINANCE, Exchange.BYBIT, Exchange.COINBASE, Exchange.KRAKEN]
_TERMINAL_STATUSES = TERMINAL
_FILL_POLL_INTERVAL = 5


class ExchangeExecutor(BaseAgent):
    AGENT_ID = 26

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=5, name="ExchangeExecutor", config=config)
        self._operation_lock = asyncio.Lock()
        self.store: ExecutionStore | None = None
        self.recovery: RecoveryCoordinator | None = None
        self.venues: dict[str, Any] = {}
        self._live_connectors: list[ExchangeConnector] = []
        self._consumer: Any = None
        self._kill_consumer: Any = None
        self._owns_writer = False
        self._placed_count = self._rejected_count = 0
        self._kill_event_types = {"KillSwitchEvent", "HaltAllStrategies"}
        self._unattempted_claims: dict[Any, tuple[Order, str]] = {}
        self._pending_observations: dict[Any, tuple[Order, Order]] = {}
        self._pending_uncertain: dict[Any, tuple[Order, str]] = {}

    async def _ensure_store_writer(self) -> None:
        assert self.store is not None
        ensure = getattr(self.store, "ensure_writer", None)
        if callable(ensure):
            await ensure()
            return
        await self.store.check_writer()

    async def _abort_or_queue_unattempted(self, order: Order, reason: str) -> None:
        assert self.store is not None
        abort_if = getattr(self.store, "abort_if_unattempted", None)
        abort_fn = getattr(self.store, "abort_prepared", None)
        try:
            await self._ensure_store_writer()
            if callable(abort_if):
                await abort_if(order, reason)
            elif callable(abort_fn):
                await abort_fn(order, reason)
            self._unattempted_claims.pop(order.client_order_id, None)
        except Exception:
            self._unattempted_claims[order.client_order_id] = (order, reason)

    async def _flush_pending_journal(self) -> None:
        assert self.store is not None
        for cid, (unattempted_order, reason) in list(self._unattempted_claims.items()):
            abort_if = getattr(self.store, "abort_if_unattempted", None)
            abort_fn = getattr(self.store, "abort_prepared", None)
            if callable(abort_if):
                await abort_if(unattempted_order, reason)
            elif callable(abort_fn):
                await abort_fn(unattempted_order, reason)
            self._unattempted_claims.pop(cid, None)
        for cid, (req_order, placed_order) in list(self._pending_observations.items()):
            await self.store.observe(req_order, placed_order)
            self._pending_observations.pop(cid, None)
        for cid, (uncertain_order, reason) in list(self._pending_uncertain.items()):
            await self.store.uncertain(uncertain_order, reason)
            self._pending_uncertain.pop(cid, None)

    async def initialize(self) -> None:
        settings.require_order_execution()
        ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        self.store = ExecutionStore(ledger)
        await self.store.claim_writer()
        self._owns_writer = True
        await self.store.configure(settings.execution_accounts)
        await self.state.set_reconciliation({"book_id": self.store.book_id, "ready": False})
        for account in settings.execution_accounts:
            if account.exchange not in _SUPPORTED_EXCHANGES:
                raise ValueError("Unsupported execution recovery exchange")
            if settings.is_live:
                connector = ExchangeConnector(account.exchange, account.account_id)
                self._live_connectors.append(connector)
                await connector.connect()
                self.venues[account.key] = SpotRecoveryAdapter(connector)
            else:
                venue = PaperVenue(
                    self.store,
                    account,
                    self.state,
                    settings.paper_fee_bps,
                    max_fill_size=settings.paper_max_fill_size,
                )
                await venue.initialize()
                self.venues[account.key] = venue
        self.recovery = RecoveryCoordinator(
            self.store,
            settings.execution_accounts,
            self.venues,
            self.state,
            self.publish,
            page_budget=settings.execution_recovery_page_budget,
            ttl=settings.execution_reconciliation_ttl,
            overlap_ms=settings.execution_overlap_seconds * 1000,
            full_scan_ms=settings.execution_full_scan_seconds * 1000,
            tolerances=settings.execution_balance_tolerances,
            order_lock=self._operation_lock,
        )

    async def handle_order(self, message: dict[str, Any]) -> None:
        settings.require_order_execution()
        payload = message.get("payload", message)
        # Every book receives its topic's stream; a foreign or legacy-unscoped
        # message must never be claimed or rejected into this book's journal.
        if (
            not isinstance(payload, dict)
            or payload.get("accounting_book_id") != settings.accounting_book_id
        ):
            return
        try:
            order = Order.model_validate(payload)
        except ValidationError:
            # Poison deliveries must not terminate recovery or claim an ID.
            # Do not log source payloads, which may contain untrusted secrets.
            self.record_processing_error(KafkaTopic.ORDERS_PENDING.value, "ValidationError")
            self._rejected_count += 1
            return
        if order.order_type in (OrderType.TWAP, OrderType.VWAP):
            return
        await self._place_order(order)

    async def _place_order(self, order: Order) -> bool:
        async with self._operation_lock:
            return await self._submit(order)

    async def _submit(self, order: Order) -> bool:
        settings.require_order_execution()
        if self.store is None:
            raise RuntimeError("Durable execution store must be initialized")
        await self._ensure_store_writer()
        await self._flush_pending_journal()
        try:
            await self.store.authorize(order)
        except AuthorizationError as exc:
            await self.store.deny(order, str(exc))
            self._rejected_count += 1
            return False
        if await self.store.seen(order):
            return False
        invalid = (
            order.exchange not in _SUPPORTED_EXCHANGES
            or order.order_type not in (OrderType.MARKET, OrderType.LIMIT)
            or not order.size.is_finite()
            or order.size <= 0
            or (
                order.order_type == OrderType.LIMIT
                and (order.price is None or not order.price.is_finite() or order.price <= 0)
            )
        )
        age = (datetime.now(UTC) - utc(order.created_at)).total_seconds()
        if invalid or not -5 <= age <= 120:
            await self.store.reject(order, "invalid, unsupported, or stale order")
            self._rejected_count += 1
            return False
        if await self.is_halted() or not await self.state.trading_ready():
            await self.store.reject(order, "kill switch or unverified portfolio")
            self._rejected_count += 1
            return False
        try:
            claimed = await self.store.prepare(order)
        except RecoveryBlockedError as exc:
            with suppress(Exception):
                await self.store.reject(order, str(exc))
            self._rejected_count += 1
            return False
        except Exception as exc:
            if is_transient_db_error(exc) or isinstance(exc, DatabaseCircuitOpenError):
                # DB dropped at the exact moment of prepare(); venue was NEVER contacted.
                # Fence and clean up any commit-ack-lost 'submitting' row so no phantom order exists.
                with suppress(Exception):
                    await self.state.set_reconciliation(
                        {"book_id": self.store.book_id, "ready": False}
                    )
                await self._abort_or_queue_unattempted(
                    order, "db session lost during prepare before venue contact"
                )
                return False
            raise
        if not claimed:
            return False
        await self.state.set_reconciliation({"book_id": self.store.book_id, "ready": False})
        venue_contacted = False
        placed: Order | None = None
        try:
            await self._ensure_store_writer()
            if await self.is_halted():
                await self.store.abort_prepared(order, "halted before venue submission")
                return False
            venue_contacted = True
            placed = await self.venues[key(order.exchange.value, order.account_id)].place(order)
            await self.store.observe(order, placed)
            self._placed_count += 1
        except Exception as exc:
            if not venue_contacted:
                # Disconnect or error occurred BEFORE venue.place() was ever invoked.
                await self._abort_or_queue_unattempted(
                    order, f"pre-submission abort ({type(exc).__name__}); venue not contacted"
                )
                return False
            if placed is not None:
                # Venue succeeded, but DB dropped during observe(). Retry after session recovery
                # or buffer observation; fall back to uncertain if durable state cannot be updated yet.
                try:
                    await self._ensure_store_writer()
                    await self.store.observe(order, placed)
                    self._placed_count += 1
                    return True
                except Exception:
                    self._pending_observations[order.client_order_id] = (order, placed)
            try:
                await self._ensure_store_writer()
                await self.store.uncertain(order, type(exc).__name__)
            except Exception:
                self._pending_uncertain[order.client_order_id] = (order, type(exc).__name__)
            self.logger.error(
                "submission awaiting recovery",
                client_order_id=str(order.client_order_id),
                error_type=type(exc).__name__,
            )
        return True

    async def _fill_polling_loop(self) -> None:
        assert self.recovery is not None and self.store is not None
        while True:
            try:
                async with self._operation_lock:
                    await self._flush_pending_journal()
                report = await self.recovery.run_once()
                if not report["ready"]:
                    self.logger.warning(
                        "execution reconciliation blocked", reasons=report["reasons"]
                    )
            except OrderConflictError:
                raise
            except Exception as exc:
                with suppress(Exception):
                    await self.state.set_reconciliation(
                        {"book_id": self.store.book_id, "ready": False}
                    )
                with suppress(Exception):
                    await self._ensure_store_writer()
                    await self.store.block(type(exc).__name__)
                self.logger.warning("execution recovery failed", error_type=type(exc).__name__)
            await asyncio.sleep(_FILL_POLL_INTERVAL)

    async def _kill_switch_listener_loop(self) -> None:
        assert self.recovery is not None
        self._kill_consumer = self.make_consumer([KafkaTopic.RISK_ALERTS])
        await self._kill_consumer.initialize()

        async def handle(message: dict[str, Any]) -> None:
            payload = message.get("payload", message)
            if (
                payload.get("halt_scope") != "global"
                and payload.get("accounting_book_id") != settings.accounting_book_id
            ):
                return
            if message.get("message_type") in self._kill_event_types:
                # Notifications never override an authorized reset. The durable
                # book/global authority determines whether this halt is active.
                if not await self.state.is_kill_switch_active():
                    return
                assert self.recovery is not None and self.store is not None
                await self.state.set_reconciliation({"book_id": self.store.book_id, "ready": False})
                await self._ensure_store_writer()
                await self.store.block("kill switch")
                await self.recovery.recover_orders(halted=True)

        await self._kill_consumer.process(handle)

    async def run(self) -> None:
        self._consumer = self.make_consumer(
            [KafkaTopic.ORDERS_PENDING], auto_offset_reset="earliest"
        )
        await self._consumer.initialize()
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._consumer.process(self.handle_order))
            tasks.create_task(self._fill_polling_loop())
            tasks.create_task(self._kill_switch_listener_loop())

    async def shutdown(self) -> None:
        try:
            if self._owns_writer and self.store is not None:
                await self.store.block("executor stopped")
                await self.state.set_reconciliation({"book_id": self.store.book_id, "ready": False})
        finally:
            for consumer in (self._consumer, self._kill_consumer):
                if consumer is not None:
                    await consumer.shutdown()
            for connector in self._live_connectors:
                await connector.close()
            if self.store is not None:
                await self.store.close()
