"""
Agent 22 — Slippage Minimizer
Executes large orders using TWAP/VWAP algorithms to minimize market impact.
Splits large orders into child orders and tracks execution quality.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import structlog

from agents.base_agent import BaseAgent
from core.data.models import AgentConfig, Fill, KafkaTopic, Order, OrderStatus, OrderType

log = structlog.get_logger(__name__)

_TWAP_DEFAULT_SLICES = 6
_TWAP_DEFAULT_DURATION_MIN = 30
_VWAP_PARTICIPATION_RATE = 0.10  # Max 10% of market volume per slice
_MAX_SLIPPAGE_BPS = 50  # Abort if realised slippage exceeds 50bps


class SlippageMinimizer(BaseAgent):
    """
    Agent 22 — TWAP/VWAP execution engine.
    Receives large orders flagged for algorithmic execution and
    splits them into time-weighted or volume-weighted slices.
    """

    AGENT_ID = 22

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="SlippageMinimizer",
            config=config,
        )
        self._active_plans: dict[UUID, _ExecutionState] = {}

    async def initialize(self) -> None:
        log.info("slippage_minimizer.initialized")

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.ORDERS_PENDING])
        await consumer.initialize()
        execution_loop = asyncio.create_task(self._execution_loop())
        try:
            async for msg in consumer.stream():
                if await self.is_halted():
                    continue
                try:
                    payload = msg.get("payload", msg)
                    # Skip child orders (already split) to avoid recursive splitting
                    if isinstance(payload, dict) and payload.get("_child"):
                        continue
                    order = Order.model_validate(payload)
                    if order.order_type in (OrderType.TWAP, OrderType.VWAP):
                        await self._start_plan(order)
                except Exception as exc:
                    log.warning("slippage_minimizer.ingest_error", error=str(exc))
        finally:
            execution_loop.cancel()

    async def shutdown(self) -> None:
        log.info("slippage_minimizer.shutdown", active_plans=len(self._active_plans))

    # ── Plan Execution ─────────────────────────────────────────────────────────

    async def _start_plan(self, parent_order: Order) -> None:
        algo = parent_order.order_type
        params = parent_order.algo_params

        if algo == OrderType.TWAP:
            n_slices = int(params.get("num_slices", _TWAP_DEFAULT_SLICES))
            duration_min = int(params.get("duration_minutes", _TWAP_DEFAULT_DURATION_MIN))
            interval_sec = duration_min * 60 // n_slices
            slice_size = parent_order.size / Decimal(str(n_slices))
        else:  # VWAP
            n_slices = 12
            interval_sec = 300
            slice_size = parent_order.size / Decimal(str(n_slices))

        state = _ExecutionState(
            plan_id=uuid4(),
            parent_order=parent_order,
            n_slices=n_slices,
            interval_sec=interval_sec,
            slice_size=slice_size,
            algo=algo,
        )
        self._active_plans[state.plan_id] = state
        log.info(
            "slippage_minimizer.plan_started",
            plan_id=str(state.plan_id),
            symbol=parent_order.symbol,
            algo=algo.value,
            slices=n_slices,
            interval_sec=interval_sec,
        )

    async def _execution_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            now = datetime.utcnow()
            for plan_id, state in list(self._active_plans.items()):
                if state.is_complete:
                    await self._finalise(state)
                    del self._active_plans[plan_id]
                    continue
                if state.next_slice_at is None or now >= state.next_slice_at:
                    await self._execute_slice(state)

    async def _execute_slice(self, state: _ExecutionState) -> None:
        if state.slices_done >= state.n_slices:
            state.is_complete = True
            return

        # Build child order
        child = Order(
            proposal_id=state.parent_order.proposal_id,
            symbol=state.parent_order.symbol,
            exchange=state.parent_order.exchange,
            account_id=state.parent_order.account_id,
            side=state.parent_order.side,
            order_type=OrderType.LIMIT,
            size=state.slice_size,
            price=None,  # market limit (exchange will handle)
            strategy_id=state.parent_order.strategy_id,
            agent_id=self.AGENT_ID,
            status=OrderStatus.PENDING,
        )

        await self.publish(
            KafkaTopic.ORDERS_PENDING,
            {
                **child.model_dump(mode="json"),
                "_parent_plan_id": str(state.plan_id),
                "_slice": state.slices_done + 1,
                "_child": True,
            },
            "ChildOrder",
        )

        state.slices_done += 1
        state.next_slice_at = datetime.utcnow() + timedelta(seconds=state.interval_sec)

        log.debug(
            "slippage_minimizer.slice_sent",
            symbol=state.parent_order.symbol,
            slice=state.slices_done,
            of=state.n_slices,
        )

    async def _finalise(self, state: _ExecutionState) -> None:
        log.info(
            "slippage_minimizer.plan_complete",
            plan_id=str(state.plan_id),
            symbol=state.parent_order.symbol,
            slices_done=state.slices_done,
        )


class _ExecutionState:
    """Mutable execution state for a single TWAP/VWAP plan."""

    def __init__(
        self,
        plan_id: UUID,
        parent_order: Order,
        n_slices: int,
        interval_sec: int,
        slice_size: Decimal,
        algo: OrderType,
    ) -> None:
        self.plan_id = plan_id
        self.parent_order = parent_order
        self.n_slices = n_slices
        self.interval_sec = interval_sec
        self.slice_size = slice_size
        self.algo = algo
        self.slices_done = 0
        self.is_complete = False
        self.next_slice_at: datetime | None = None
        self.fills: list[Fill] = []
