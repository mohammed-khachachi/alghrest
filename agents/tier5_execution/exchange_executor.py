"""
Agent 26 — Exchange Executor

The final hop in the execution pipeline. Without it, orders sit on Kafka
and never reach a venue.

Pipeline position:
    PROPOSALS_BUS → ProposalApprover → PROPOSALS_APPROVED
                                     → OrderRouter
                                     → ORDERS_PENDING ─┐
                                     → FeeOptimizer    │  (post-only upgrade)
                                     → SlippageMin.    │  (TWAP/VWAP children)
                                                       │
                       [ExchangeExecutor]  ◄───────────┘
                              │
                              ├──→ live exchange (CCXT Pro)
                              ├──→ ORDERS_EXECUTED  (status updates)
                              └──→ FILLS_CONFIRMED  (per fill)

Idempotency:
  - Distributed Redis lock keyed on `client_order_id` prevents duplicate
    placement across executor restarts or replicas.
  - Exchange-side dedup is handled by passing `clientOrderId` to CCXT.
  - Fill dedup uses `state.is_already_processed("fill_seen:{ex}:{fill_id}")`.

Fill detection:
  - Polls `fetch_order` every _FILL_POLL_INTERVAL seconds for tracked orders.
  - On status change, calls `fetch_trades` to retrieve fill detail and
    publishes each new fill to FILLS_CONFIRMED.
  - Terminal statuses (FILLED / CANCELLED / REJECTED / EXPIRED) drop the
    order from the tracking dict.

Kill switch behaviour:
  - When `is_halted()` is true, no new orders are placed; in-flight tracked
    orders are NOT cancelled here (that is the job of `core/risk/kill_switch`).
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime
from uuid import uuid4

import structlog

from agents.base_agent import BaseAgent
from connectors.exchanges.ccxt_connector import MultiExchangeConnector
from core.data.models import (
    AgentConfig,
    AlertType,
    Exchange,
    KafkaTopic,
    Order,
    OrderStatus,
    OrderType,
    RiskAlert,
    RiskLevel,
)

log = structlog.get_logger(__name__)

_FILL_POLL_INTERVAL = 5  # seconds between fill polling sweeps
_LOCK_TIMEOUT = 30.0
_PLACED_TTL = 86_400  # 24h dedup window for client_order_id

# Durable tracking of open orders — the source of truth for fill polling and
# kill-switch cancellation. Written WITHOUT a TTL on purpose: a resting limit
# order may outlive any TTL, so entries are removed only when the order reaches
# a terminal status. The in-process `_tracked_orders` dict is a cache mirror.
_NS_TRACKED = "alghrest:exec:tracked:{ex_id}"
_TRACKED_PATTERN = "alghrest:exec:tracked:*"

# Per-order fill-polling ownership lease. With multiple executor replicas, only
# the lease holder polls a given order, so duplicate ORDERS_EXECUTED status
# updates are avoided. The TTL is short and > _FILL_POLL_INTERVAL so the holder
# keeps the lease across sweeps, but a dead replica's lease expires and another
# replica takes over. The lease is an optimisation only — it never gates
# placement or kill-switch cancellation.
_NS_POLL_LEASE = "alghrest:exec:poll_lease:{ex_id}"
_POLL_LEASE_TTL = 15

_TERMINAL_STATUSES = {
    OrderStatus.FILLED,
    OrderStatus.CANCELLED,
    OrderStatus.REJECTED,
    OrderStatus.EXPIRED,
}

# Exchanges this executor will place orders on. Must match what
# MultiExchangeConnector knows how to instantiate (see ccxt_connector.py).
_SUPPORTED_EXCHANGES: list[Exchange] = [
    Exchange.BINANCE,
    Exchange.BYBIT,
    Exchange.COINBASE,
    Exchange.KRAKEN,
]


class ExchangeExecutor(BaseAgent):
    """
    Agent 26 — places approved orders on real exchanges and tracks fills.
    """

    AGENT_ID = 26

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="ExchangeExecutor",
            config=config,
        )
        self._connector = MultiExchangeConnector()
        # Unique identity for this executor process, used as the fill-polling
        # lease owner so replicas can tell each other's leases apart.
        self._owner_id = f"{self.name}:{os.getpid()}:{uuid4().hex[:6]}"
        # exchange_order_id → (Order, last_polled_at)
        self._tracked_orders: dict[str, tuple[Order, datetime]] = {}
        self._placed_count = 0
        self._rejected_count = 0
        self._fills_published = 0
        self._cancelled_by_kill_switch = 0
        # message_types on RISK_ALERTS that mean "stop trading immediately"
        self._kill_event_types = {"KillSwitchEvent", "HaltAllStrategies"}

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        await self._connector.connect_all(_SUPPORTED_EXCHANGES)
        await self._recover_tracked_orders()
        log.info(
            "exchange_executor.initialized",
            exchanges=[e.value for e in _SUPPORTED_EXCHANGES],
            tracked_recovered=len(self._tracked_orders),
        )

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.ORDERS_PENDING])
        await consumer.initialize()

        fill_task = asyncio.create_task(self._fill_polling_loop(), name="fill_polling")
        kill_task = asyncio.create_task(
            self._kill_switch_listener_loop(), name="kill_switch_listener"
        )
        try:
            async for msg in consumer.stream():
                if await self.is_halted():
                    log.warning("exchange_executor.kill_switch_active_skipping_order")
                    continue
                try:
                    payload = msg.get("payload", msg)
                    order = Order.model_validate(payload)

                    # TWAP/VWAP parents are handled by SlippageMinimizer, which
                    # publishes LIMIT child orders (with `_child=True`) onto
                    # the same topic. We place the children but skip the parent.
                    if order.order_type in (OrderType.TWAP, OrderType.VWAP):
                        log.debug(
                            "exchange_executor.skipping_algo_parent",
                            order_type=order.order_type.value,
                            symbol=order.symbol,
                        )
                        continue

                    await self._place_with_lock(order)
                except Exception as exc:
                    self.record_processing_error(
                        KafkaTopic.ORDERS_PENDING.value, type(exc).__name__
                    )
                    log.warning("exchange_executor.placement_error", error=str(exc))
        finally:
            fill_task.cancel()
            kill_task.cancel()

    async def shutdown(self) -> None:
        await self._connector.close_all()
        log.info(
            "exchange_executor.shutdown",
            placed=self._placed_count,
            rejected=self._rejected_count,
            fills_published=self._fills_published,
            cancelled_by_kill_switch=self._cancelled_by_kill_switch,
            tracked_remaining=len(self._tracked_orders),
        )

    # ── Kill-switch listener ───────────────────────────────────────────────────

    async def _kill_switch_listener_loop(self) -> None:
        """
        Listen on RISK_ALERTS for kill-switch / halt events and cancel every
        tracked open order. We use auto_offset_reset='latest' so a restart
        does not replay historical kill events; the executor's main `is_halted()`
        guard already prevents new orders from being placed during an active halt.
        """
        try:
            consumer = self.make_consumer([KafkaTopic.RISK_ALERTS], auto_offset_reset="latest")
            await consumer.initialize()
        except Exception as exc:
            log.error("exchange_executor.kill_listener_init_failed", error=str(exc))
            return

        try:
            async for msg in consumer.stream():
                msg_type = msg.get("message_type", "")
                if msg_type not in self._kill_event_types:
                    continue
                payload = msg.get("payload", {})
                reason = payload.get("trigger_reason") or payload.get("reason") or msg_type
                log.critical(
                    "exchange_executor.kill_switch_received",
                    msg_type=msg_type,
                    reason=reason,
                    tracked=len(self._tracked_orders),
                )
                await self._cancel_all_tracked_orders(reason=reason)
        except asyncio.CancelledError:
            return

    async def _cancel_all_tracked_orders(self, reason: str) -> None:
        """
        Best-effort cancellation of every open order across all executor
        replicas. The set is read from Redis (authoritative) rather than the
        local cache, so a restarted or second-replica executor cancels orders
        it never placed locally.
        """
        snapshot = await self._authoritative_tracked()
        if not snapshot:
            log.info("exchange_executor.kill_cancel_nothing_to_do")
            return

        cancelled = 0
        failed = 0

        for ex_order_id, order in snapshot:
            try:
                connector = self._connector.get(order.exchange)
            except KeyError:
                failed += 1
                log.warning(
                    "exchange_executor.kill_cancel_no_connector",
                    exchange=order.exchange.value,
                    exchange_order_id=ex_order_id,
                )
                continue

            try:
                ok = await connector.cancel_order(ex_order_id, order.symbol)
            except Exception as exc:
                ok = False
                log.warning(
                    "exchange_executor.kill_cancel_exception",
                    exchange_order_id=ex_order_id,
                    error=str(exc),
                )

            if ok:
                cancelled += 1
                self._cancelled_by_kill_switch += 1
                cancelled_order = order.model_copy(
                    update={
                        "status": OrderStatus.CANCELLED,
                        "updated_at": datetime.utcnow(),
                    }
                )
                try:
                    await self.publish(
                        KafkaTopic.ORDERS_EXECUTED,
                        payload=cancelled_order.model_dump(mode="json"),
                        message_type="OrderCancelledByKillSwitch",
                    )
                except Exception as exc:
                    log.warning(
                        "exchange_executor.kill_cancel_publish_failed",
                        error=str(exc),
                    )
                await self._remove_tracked(ex_order_id)
            else:
                failed += 1
                # Leave in tracked dict; the fill polling loop will continue
                # to monitor it and pick up any exchange-side state changes.

        log.critical(
            "exchange_executor.kill_cancel_complete",
            reason=reason,
            cancelled=cancelled,
            failed=failed,
            still_tracked=len(self._tracked_orders),
        )

    # ── Durable order tracking (Redis = source of truth, dict = cache) ───────────

    async def _track(self, order: Order, polled_at: datetime) -> None:
        """
        Record an open order as the durable source of truth in Redis and mirror
        it into the local cache. Redis write failures are logged but never abort
        execution — the local mirror keeps this process working, and a restart
        recovers whatever did persist.
        """
        if order.exchange_order_id is None:
            return
        self._tracked_orders[order.exchange_order_id] = (order, polled_at)
        key = _NS_TRACKED.format(ex_id=order.exchange_order_id)
        try:
            await self.state.set_json(
                key,
                {
                    "order": order.model_dump(mode="json"),
                    "last_poll": polled_at.isoformat(),
                },
            )
        except Exception as exc:
            log.warning(
                "exchange_executor.tracked_persist_failed",
                exchange_order_id=order.exchange_order_id,
                error=str(exc),
            )

    async def _remove_tracked(self, exchange_order_id: str) -> None:
        """Drop an order from both the durable set and the local cache."""
        self._tracked_orders.pop(exchange_order_id, None)
        try:
            await self.state.delete_key(_NS_TRACKED.format(ex_id=exchange_order_id))
        except Exception as exc:
            log.warning(
                "exchange_executor.tracked_delete_failed",
                exchange_order_id=exchange_order_id,
                error=str(exc),
            )

    async def _authoritative_tracked(self) -> list[tuple[str, Order]]:
        """
        Return every open order across ALL executor replicas by scanning Redis.
        Used by the kill switch so a restarted or second-replica executor cancels
        orders it never placed locally. If Redis is unreachable, fall back to the
        local mirror (over-cancelling is fail-safe; under-cancelling is not).
        """
        try:
            keys = await self.state.scan_keys(_TRACKED_PATTERN)
        except Exception as exc:
            log.error(
                "exchange_executor.tracked_scan_failed_fallback_local",
                error=str(exc),
            )
            return [(ex_id, o) for ex_id, (o, _) in self._tracked_orders.items()]

        result: list[tuple[str, Order]] = []
        for key in keys:
            try:
                data = await self.state.get_json(key)
                if not data:
                    continue
                order = Order.model_validate(data["order"])
            except Exception as exc:
                log.warning("exchange_executor.tracked_load_skip", key=key, error=str(exc))
                continue
            if order.exchange_order_id:
                result.append((order.exchange_order_id, order))
        return result

    async def _recover_tracked_orders(self) -> None:
        """Repopulate the local cache from durable Redis state on startup."""
        try:
            keys = await self.state.scan_keys(_TRACKED_PATTERN)
        except Exception as exc:
            log.error("exchange_executor.tracked_recover_failed", error=str(exc))
            return
        recovered = 0
        for key in keys:
            try:
                data = await self.state.get_json(key)
                if not data:
                    continue
                order = Order.model_validate(data["order"])
            except Exception as exc:
                log.warning("exchange_executor.tracked_recover_skip", key=key, error=str(exc))
                continue
            if order.exchange_order_id and order.status not in _TERMINAL_STATUSES:
                self._tracked_orders[order.exchange_order_id] = (order, datetime.utcnow())
                recovered += 1
        if recovered:
            log.info("exchange_executor.tracked_recovered", count=recovered)

    # ── Order placement ────────────────────────────────────────────────────────

    async def _place_with_lock(self, order: Order) -> None:
        """Acquire a distributed lock keyed on client_order_id, then place."""
        client_id = str(order.client_order_id)
        lock_name = f"order_placement:{client_id}"
        try:
            async with self.state.lock(lock_name, timeout=_LOCK_TIMEOUT):
                # Idempotency check: was this client_order_id already placed?
                marker_key = f"order_placed:{client_id}"
                already = await self.state.get_json(marker_key)
                if already is not None:
                    log.info(
                        "exchange_executor.duplicate_skipped",
                        client_order_id=client_id,
                        first_placed_at=already.get("placed_at"),
                    )
                    return

                placed_ok = await self._place_order(order)
                if placed_ok:
                    await self.state.set_json(
                        marker_key,
                        {"placed_at": datetime.utcnow().isoformat()},
                        ttl=_PLACED_TTL,
                    )
        except TimeoutError:
            log.warning(
                "exchange_executor.lock_timeout",
                client_order_id=client_id,
            )

    async def _place_order(self, order: Order) -> bool:
        """Place a single order on the configured exchange. Returns True on success."""
        if order.exchange not in _SUPPORTED_EXCHANGES:
            await self._reject(order, f"Exchange {order.exchange.value} not supported")
            return False

        try:
            connector = self._connector.get(order.exchange)
        except KeyError:
            await self._reject(order, f"No active connector for {order.exchange.value}")
            return False

        client_id = str(order.client_order_id)

        try:
            if order.order_type == OrderType.MARKET:
                placed = await connector.place_market_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=order.size,
                    client_order_id=client_id,
                )
            elif order.order_type in (
                OrderType.LIMIT,
                OrderType.STOP,
                OrderType.STOP_LIMIT,
            ):
                if order.price is None:
                    await self._reject(order, "limit/stop order missing price")
                    return False
                placed = await connector.place_limit_order(
                    symbol=order.symbol,
                    side=order.side,
                    amount=order.size,
                    price=order.price,
                    client_order_id=client_id,
                )
            else:
                await self._reject(
                    order,
                    f"Unsupported order type for direct placement: {order.order_type.value}",
                )
                return False
        except Exception as exc:
            await self._reject(order, f"exchange error: {type(exc).__name__}: {exc}")
            return False

        # Merge connector response into our internal Order (preserving order_id,
        # client_order_id, strategy_id, agent_id, proposal_id from the original).
        executed = order.model_copy(
            update={
                "exchange_order_id": placed.exchange_order_id,
                "status": placed.status,
                "filled_size": placed.filled_size,
                "avg_fill_price": placed.avg_fill_price,
                "updated_at": datetime.utcnow(),
            }
        )

        await self.publish(
            KafkaTopic.ORDERS_EXECUTED,
            payload=executed.model_dump(mode="json"),
            message_type="OrderPlaced",
        )

        self._placed_count += 1
        log.info(
            "exchange_executor.order_placed",
            client_order_id=client_id,
            exchange=order.exchange.value,
            symbol=order.symbol,
            side=order.side.value,
            type=order.order_type.value,
            size=float(order.size),
            status=executed.status.value,
            exchange_order_id=executed.exchange_order_id,
        )

        # MARKET orders typically fill instantly — fetch fills now.
        if executed.status == OrderStatus.FILLED:
            await self._fetch_and_publish_fills(executed)
        elif executed.status not in _TERMINAL_STATUSES and executed.exchange_order_id:
            await self._track(executed, datetime.utcnow())

        return True

    async def _reject(self, order: Order, reason: str) -> None:
        rejected = order.model_copy(
            update={
                "status": OrderStatus.REJECTED,
                "updated_at": datetime.utcnow(),
            }
        )
        await self.publish(
            KafkaTopic.ORDERS_EXECUTED,
            payload=rejected.model_dump(mode="json"),
            message_type="OrderRejected",
        )
        alert = RiskAlert(
            alert_type=AlertType.CONNECTIVITY_LOSS,
            risk_level=RiskLevel.MEDIUM,
            source_agent_id=self.AGENT_ID,
            message=(
                f"Exchange placement failed: {order.symbol} "
                f"{order.side.value} {float(order.size)} on {order.exchange.value} — {reason}"
            ),
            triggered_value=float(order.size),
            threshold_value=0.0,
            recommended_action="Review exchange credentials and order parameters.",
        )
        await self.publish(
            KafkaTopic.RISK_ALERTS,
            payload=alert.model_dump(mode="json"),
            message_type="ExecutionRejected",
        )
        self._rejected_count += 1
        log.warning(
            "exchange_executor.rejected",
            client_order_id=str(order.client_order_id),
            exchange=order.exchange.value,
            reason=reason,
        )

    # ── Fill polling ───────────────────────────────────────────────────────────

    async def _acquire_poll_lease(self, exchange_order_id: str) -> bool:
        """
        Try to take (or renew) this order's polling lease for this replica.
        Returns False — skip polling — if another replica owns it OR if Redis
        is unreachable. Failing closed here only delays a status update; it
        never places an order, so it is always the safe choice.
        """
        key = _NS_POLL_LEASE.format(ex_id=exchange_order_id)
        try:
            return await self.state.acquire_lease(key, self._owner_id, _POLL_LEASE_TTL)
        except Exception as exc:
            log.debug(
                "exchange_executor.poll_lease_error_skip",
                exchange_order_id=exchange_order_id,
                error=str(exc),
            )
            return False

    async def _fill_polling_loop(self) -> None:
        """Poll fetch_order for each tracked order; detect fills/cancels."""
        while True:
            try:
                await asyncio.sleep(_FILL_POLL_INTERVAL)
                if await self.is_halted():
                    continue
                # Snapshot to avoid mutation while iterating
                tracked = list(self._tracked_orders.items())
                for ex_order_id, (order, _) in tracked:
                    try:
                        # Only the lease holder polls this order, so multiple
                        # replicas don't emit duplicate status updates. If the
                        # lease is held elsewhere (or Redis is unreachable) we
                        # skip — never poll without ownership.
                        if not await self._acquire_poll_lease(ex_order_id):
                            continue
                        await self._poll_one(ex_order_id, order)
                    except Exception as exc:
                        log.debug(
                            "exchange_executor.poll_failed",
                            exchange_order_id=ex_order_id,
                            error=str(exc),
                        )
            except asyncio.CancelledError:
                return

    async def _poll_one(self, exchange_order_id: str, order: Order) -> None:
        connector = self._connector.get(order.exchange)
        latest = await connector.fetch_order(exchange_order_id, order.symbol)
        if latest is None:
            return

        status_changed = latest.status != order.status
        fill_changed = latest.filled_size != order.filled_size

        if status_changed or fill_changed:
            updated = order.model_copy(
                update={
                    "status": latest.status,
                    "filled_size": latest.filled_size,
                    "avg_fill_price": latest.avg_fill_price,
                    "updated_at": datetime.utcnow(),
                }
            )
            await self._track(updated, datetime.utcnow())

            await self.publish(
                KafkaTopic.ORDERS_EXECUTED,
                payload=updated.model_dump(mode="json"),
                message_type="OrderStatusUpdate",
            )
            await self._fetch_and_publish_fills(updated)

            if latest.status in _TERMINAL_STATUSES:
                await self._remove_tracked(exchange_order_id)
                log.info(
                    "exchange_executor.order_terminal",
                    exchange_order_id=exchange_order_id,
                    status=latest.status.value,
                )

    async def _fetch_and_publish_fills(self, order: Order) -> None:
        """Fetch recent trades for the symbol and publish those that match `order`."""
        if order.exchange_order_id is None:
            return
        connector = self._connector.get(order.exchange)
        try:
            fills = await connector.fetch_trades(order.symbol, limit=20)
        except Exception as exc:
            log.debug("exchange_executor.fill_fetch_error", error=str(exc))
            return

        for fill in fills:
            if fill.exchange_order_id != order.exchange_order_id:
                continue
            dedup_key = f"fill_seen:{order.exchange.value}:{fill.fill_id}"
            if await self.state.is_already_processed(dedup_key, ttl_seconds=_PLACED_TTL):
                continue

            # Inject internal linkage (connector only knows exchange ids)
            fill_internal = fill.model_copy(
                update={
                    "order_id": order.order_id,
                    "strategy_id": order.strategy_id,
                }
            )
            await self.publish(
                KafkaTopic.FILLS_CONFIRMED,
                payload=fill_internal.model_dump(mode="json"),
                message_type="Fill",
            )
            self._fills_published += 1
            log.info(
                "exchange_executor.fill_published",
                exchange=order.exchange.value,
                symbol=fill.symbol,
                side=fill.side.value,
                fill_size=float(fill.fill_size),
                fill_price=float(fill.fill_price),
                strategy_id=order.strategy_id,
                is_maker=fill.is_maker,
            )
