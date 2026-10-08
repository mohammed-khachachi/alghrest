"""Agent 20: preserve approved account/venue and choose execution algorithm."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import (
    AgentConfig,
    KafkaTopic,
    Order,
    OrderStatus,
    OrderType,
    TradeProposal,
    TradeProposalStatus,
)

log = structlog.get_logger(__name__)

_LARGE_ORDER_USD = Decimal("5000")  # Above this, use TWAP instead of MARKET
_PROPOSAL_TTL_SECONDS = 60  # Proposals older than 60s are stale


class OrderRouter(BaseAgent):
    """
    Agent 20 — Order Router.
    Consumes proposals.approved, preserves the approved account/venue,
    and publishes Orders to orders.pending.
    """

    AGENT_ID = 20

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="OrderRouter",
            config=config,
        )

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info(
            "order_router.initialized",
            exchanges=[a.exchange.value for a in settings.execution_accounts],
        )

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PROPOSALS_APPROVED])
        await consumer.initialize()
        async for msg in consumer.stream():
            if await self.is_halted():
                continue
            try:
                payload = msg.get("payload", msg)
                await self._route(payload)
            except Exception as exc:
                log.error("order_router.route_error", error=str(exc))
                self.record_processing_error(
                    KafkaTopic.PROPOSALS_APPROVED.value, type(exc).__name__
                )

    async def shutdown(self) -> None:
        log.info("order_router.shutdown")

    # ── Routing Logic ──────────────────────────────────────────────────────────

    async def _route(self, msg: dict[str, Any]) -> None:
        proposal = TradeProposal(**msg)

        if proposal.status != TradeProposalStatus.APPROVED:
            return

        # Stale check
        created = proposal.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - created).total_seconds()
        if age < -5 or age > _PROPOSAL_TTL_SECONDS:
            log.warning(
                "order_router.stale_proposal",
                proposal_id=str(proposal.proposal_id),
                age_s=round(age),
            )
            return

        # Risk approval is account/venue-specific, particularly for exits.
        # Never move a closing sell to a venue which does not hold the inventory.
        exchange = proposal.exchange
        if not any(
            a.exchange == exchange
            and a.account_id == proposal.account_id
            and proposal.symbol in a.symbols
            for a in settings.execution_accounts
        ):
            log.warning("order_router.outside_scope", symbol=proposal.symbol)
            return
        order_type = self._select_order_type(proposal)

        order = Order(
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            exchange=exchange,
            account_id=proposal.account_id,
            side=proposal.side,
            order_type=order_type,
            size=proposal.size,
            price=proposal.limit_price if order_type == OrderType.LIMIT else None,
            stop_price=proposal.stop_loss,
            time_in_force="GTC",
            status=OrderStatus.PENDING,
            strategy_id=proposal.strategy_id,
            agent_id=proposal.agent_id,
            algo_params=self._build_algo_params(proposal, order_type),
        )

        await self.publish(
            KafkaTopic.ORDERS_PENDING,
            order.model_dump(mode="json"),
            "Order",
        )
        log.info(
            "order_router.routed",
            symbol=proposal.symbol,
            exchange=exchange.value,
            order_type=order_type.value,
            size_usd=float(proposal.size_usd),
        )

    @staticmethod
    def _select_order_type(proposal: TradeProposal) -> OrderType:
        if proposal.order_type in (OrderType.TWAP, OrderType.VWAP):
            return proposal.order_type
        if proposal.size_usd >= _LARGE_ORDER_USD:
            return OrderType.TWAP
        if proposal.urgency == "immediate":
            return OrderType.MARKET
        if proposal.limit_price:
            return OrderType.LIMIT
        return OrderType.MARKET

    @staticmethod
    def _build_algo_params(proposal: TradeProposal, order_type: OrderType) -> dict[str, Any]:
        if order_type == OrderType.TWAP:
            return {
                "duration_minutes": 30,
                "num_slices": 6,
                "slice_interval_seconds": 300,
                "max_participation_rate": 0.10,
            }
        if order_type == OrderType.VWAP:
            return {
                "duration_minutes": 60,
                "max_participation_rate": 0.15,
            }
        return {}
