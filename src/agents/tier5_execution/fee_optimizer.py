"""
Agent 24 — Fee Optimizer
Routes orders to maker/taker based on exchange fee tiers and rebate schedules.
Prefers limit orders (maker) to collect rebates when urgency allows.
"""

from __future__ import annotations

from decimal import Decimal

import structlog

from agents.base_agent import BaseAgent
from core.data.models import AgentConfig, Exchange, KafkaTopic, Order, OrderType

log = structlog.get_logger(__name__)

# Fee structure: (maker_bps, taker_bps, has_rebate)
_FEE_TIERS: dict[Exchange, tuple[float, float, bool]] = {
    Exchange.BINANCE: (-2.0, 7.5, True),  # -0.02% maker rebate
    Exchange.BYBIT: (-1.0, 10.0, True),
    Exchange.OKX: (-1.0, 8.0, True),
    Exchange.COINBASE: (0.0, 20.0, False),
    Exchange.KRAKEN: (0.0, 16.0, False),
}

_MAKER_OFFSET_BPS = 5  # Post limit _5bps_ inside best bid/ask to qualify as maker
_URGENCY_TAKER = {"immediate", "high"}


class FeeOptimizer(BaseAgent):
    """
    Agent 24 — Fee optimiser.
    Intercepts outgoing orders and upgrades MARKET → LIMIT (post-only)
    when urgency allows, to earn maker rebates.
    """

    AGENT_ID = 24

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="FeeOptimizer",
            config=config,
        )
        self._monthly_fees_saved: Decimal = Decimal("0")

    async def initialize(self) -> None:
        log.info("fee_optimizer.initialized", exchanges=list(_FEE_TIERS.keys()))

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.ORDERS_PENDING])
        await consumer.initialize()
        async for msg in consumer.stream():
            if await self.is_halted():
                continue
            try:
                payload = msg.get("payload", msg)
                # Avoid feedback loop: skip orders already optimized
                if isinstance(payload, dict) and payload.get("_optimised"):
                    continue
                order = Order.model_validate(payload)
                optimised = self._optimise(order)
                if optimised is not order:
                    out = optimised.model_dump(mode="json")
                    out["_optimised"] = True
                    await self.publish(
                        KafkaTopic.ORDERS_PENDING,
                        out,
                        "OptimisedOrder",
                    )
            except Exception as exc:
                log.warning("fee_optimizer.error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("fee_optimizer.shutdown", fees_saved_usd=float(self._monthly_fees_saved))

    # ── Optimisation ───────────────────────────────────────────────────────────

    def _optimise(self, order: Order) -> Order:
        if order.order_type != OrderType.MARKET:
            return order  # Already limit or algo — leave unchanged

        fee_info = _FEE_TIERS.get(order.exchange)
        if fee_info is None or not fee_info[2]:
            return order  # No rebate on this exchange

        # Determine urgency from algo_params or fallback to 'normal'
        urgency = order.algo_params.get("urgency", "normal")
        if urgency in _URGENCY_TAKER:
            return order  # Need to fill immediately — stay market

        if order.price is None:
            return order  # No price to work with

        # Post limit just inside best quote to collect maker rebate
        offset = order.price * Decimal(str(_MAKER_OFFSET_BPS / 10_000))
        from core.data.models import OrderSide

        limit_price = order.price - offset if order.side == OrderSide.BUY else order.price + offset

        optimised = order.model_copy(
            update={
                "order_type": OrderType.LIMIT,
                "price": limit_price.quantize(Decimal("0.01")),
                "time_in_force": "GTX",  # Post-only
                "algo_params": {**order.algo_params, "is_maker": True},
            }
        )

        maker_rebate_bps = abs(fee_info[0])
        taker_fee_bps = fee_info[1]
        savings_bps = maker_rebate_bps + taker_fee_bps
        savings_usd = float(order.size) * float(order.price or Decimal("0")) * savings_bps / 10_000
        self._monthly_fees_saved += Decimal(str(savings_usd))

        log.debug(
            "fee_optimizer.upgraded_to_limit",
            symbol=order.symbol,
            exchange=order.exchange.value,
            savings_bps=savings_bps,
        )
        return optimised
