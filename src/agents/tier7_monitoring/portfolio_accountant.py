"""Agent 37: durable fill processing and a recoverable portfolio cache."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any

from agents.base_agent import BaseAgent
from core.accounting import performance
from core.accounting.repository import Ledger
from core.accounting.valuation import MissingValuationError, Valuation
from core.config import settings
from core.data.models import Fill, KafkaTopic
from core.orchestrator.message_bus import AlghrestConsumer
from core.resilience import DatabaseCircuitOpenError, is_transient_db_error


class PortfolioAccountant(BaseAgent):
    AGENT_ID = 37

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=7, name="portfolio_accountant")
        self.ledger: Ledger | None = None
        self.consumer: AlghrestConsumer | None = None
        self._owns_writer = False

    async def initialize(self) -> None:
        self.ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        await self.ledger.claim_writer()
        self._owns_writer = True
        await self.state.invalidate_portfolio()
        await self.ledger.load()  # no implicit capital or opening-position assumptions
        self.consumer = self.make_consumer(
            [KafkaTopic.FILLS_CONFIRMED], auto_offset_reset="earliest"
        )
        # A different opening book must not inherit another book's Kafka cursor.
        await self.consumer.initialize()

    async def _ensure_ledger_writer(self) -> None:
        assert self.ledger is not None
        ensure = getattr(self.ledger, "ensure_writer", None)
        if callable(ensure):
            await ensure()
        else:
            await self.ledger.check_writer()

    async def handle_fill(self, message: dict[str, Any]) -> None:
        if message.get("message_type") != "Fill":
            raise ValueError("Unexpected message on fills.confirmed")
        assert self.ledger is not None
        await self._ensure_ledger_writer()
        fill = Fill.model_validate(message["payload"])
        if fill.accounting_book_id and fill.accounting_book_id != self.ledger.book_id:
            return
        if fill.exchange_trade_id is None or fill.accounting_book_id is None:
            await self.ledger.archive_opening_covered_message(message, fill)
        else:
            await self.ledger.record(fill)

    async def snapshot(self) -> bool:
        assert self.ledger is not None and self.consumer is not None
        await self._ensure_ledger_writer()
        if not await self.consumer.caught_up():
            await self.state.invalidate_portfolio()
            return False
        # Serialize with fills while reading and publishing. A stale projection
        # cannot race a newer book revision into Redis.
        async with self.ledger.locked_state() as (conn, book, _opening):
            now = datetime.now(UTC)
            day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week = day - timedelta(days=day.weekday())
            rows = await self.ledger.pnl_since(conn, week)
            valuation = Valuation(
                self.state,
                now,
                settings.accounting_usd_pegs,
                settings.accounting_mark_max_age_seconds,
            )
            portfolio = await valuation.portfolio(self.ledger.book_id, book, rows)
            portfolio.performance = await performance.snapshot(conn, book, portfolio)
            await self.state.set_accounting_portfolio(portfolio)
        await self.publish(
            KafkaTopic.PORTFOLIO_STATE,
            payload=portfolio.model_dump(mode="json"),
            message_type="PortfolioState",
        )
        return True

    async def _snapshots(self) -> None:
        while True:
            try:
                await self.snapshot()
            except Exception as exc:
                if isinstance(
                    exc,
                    MissingValuationError
                    | performance.PerformanceUnavailableError
                    | DatabaseCircuitOpenError,
                ) or is_transient_db_error(exc):
                    with suppress(Exception):
                        await self.state.invalidate_portfolio()
                    self.logger.warning("accounting valuation unavailable", reason=str(exc))
                else:
                    raise
            await asyncio.sleep(5)

    async def run(self) -> None:
        assert self.consumer is not None
        try:
            # Accounting must continue during a kill switch: late fills and
            # cancellations change exposure even though opening risk is halted.
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self.consumer.process(self.handle_fill))
                tasks.create_task(self._snapshots())
        finally:
            await self.state.invalidate_portfolio()

    async def shutdown(self) -> None:
        try:
            if self._owns_writer:
                await self.state.invalidate_portfolio()
        finally:
            if self.consumer is not None:
                await self.consumer.shutdown()
            if self.ledger is not None:
                await self.ledger.close()
