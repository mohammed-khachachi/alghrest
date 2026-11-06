"""Agent 22: persist paper TWAP plans and schedule reconciled child intents."""

from __future__ import annotations

import asyncio
from typing import Any

from agents.base_agent import BaseAgent
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import AgentConfig, KafkaTopic, Order, OrderType
from core.execution.contracts import RecoveryBlockedError
from core.execution.store import ExecutionStore
from core.execution.twap import TwapScheduler


class SlippageMinimizer(BaseAgent):
    AGENT_ID = 22

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=5, name="SlippageMinimizer", config=config)
        self.store: ExecutionStore | None = None
        self.scheduler: TwapScheduler | None = None
        self._active_plans: dict[Any, Any] = {}  # diagnostic only; PostgreSQL owns progress

    async def initialize(self) -> None:
        settings.require_order_execution()
        if settings.is_live:
            raise RecoveryBlockedError("TWAP is enabled only for isolated paper execution")
        ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        self.store = ExecutionStore(ledger)
        self.scheduler = TwapScheduler(self.store, self.state)

    async def _start_plan(self, parent_order: Order) -> None:
        if self.scheduler is None:
            raise RecoveryBlockedError("Durable scheduler must be initialized")
        await self.scheduler.start(parent_order)

    async def _execution_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            if await self.is_halted():
                continue
            if self.scheduler is None:
                raise RecoveryBlockedError("Durable scheduler must be initialized")
            for parent_id in await self.scheduler.active():
                await self.scheduler.step(parent_id)

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.ORDERS_PENDING])
        await consumer.initialize()
        async with asyncio.TaskGroup() as tasks:
            execution = tasks.create_task(self._execution_loop())
            try:
                async for message in consumer.stream():
                    if await self.is_halted():
                        continue
                    payload = message.get("payload", message)
                    if (
                        not isinstance(payload, dict)
                        or payload.get("accounting_book_id") != settings.accounting_book_id
                    ):
                        continue
                    if payload.get("_child"):
                        continue
                    try:
                        order = Order.model_validate(payload)
                        if order.order_type in (OrderType.TWAP, OrderType.VWAP):
                            # Unsupported or unauthorized plans never enter the
                            # durable scheduler, nor terminate it for other orders.
                            await self._start_plan(order)
                    except (ValueError, TypeError, OverflowError, RecoveryBlockedError) as exc:
                        self.record_processing_error(
                            KafkaTopic.ORDERS_PENDING.value, type(exc).__name__
                        )
            finally:
                execution.cancel()

    async def shutdown(self) -> None:
        if self.store is not None:
            await self.store.close()
