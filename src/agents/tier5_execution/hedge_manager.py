"""
Agent 23 — Hedge Manager
Portfolio delta hedging using correlation-weighted offsetting positions.
Monitors net portfolio delta and places hedge orders when exposure drifts
beyond tolerance.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from agents.base_agent import BaseAgent
from core.data.models import (
    AgentConfig,
    AssetClass,
    Exchange,
    KafkaTopic,
    OrderSide,
    OrderType,
    TradeProposal,
)

log = structlog.get_logger(__name__)

_HEDGE_CHECK_INTERVAL = 60  # Seconds between delta checks
_DELTA_TOLERANCE = 0.10  # 10% of NAV — acceptable imbalance
_HEDGE_SYMBOL = "BTC/USDT"  # Primary hedge instrument
_HEDGE_STRATEGY_ID = "hedge_manager_delta"


class HedgeManager(BaseAgent):
    """
    Agent 23 — Delta hedge manager.
    Computes net portfolio delta (long USD - short USD) relative to NAV
    and places offsetting positions when |delta| > tolerance.
    """

    AGENT_ID = 23

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="HedgeManager",
            config=config,
        )
        self._hedge_position_usd: Decimal = Decimal("0")

    async def initialize(self) -> None:
        log.info("hedge_manager.initialized")

    async def run(self) -> None:
        while True:
            await asyncio.sleep(_HEDGE_CHECK_INTERVAL)
            if await self.is_halted():
                continue
            try:
                await self._check_delta()
            except Exception as exc:
                log.error("hedge_manager.check_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("hedge_manager.shutdown", hedge_position_usd=float(self._hedge_position_usd))

    # ── Delta Computation ──────────────────────────────────────────────────────

    async def _check_delta(self) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None or portfolio.total_capital <= Decimal("0"):
            return

        long_usd = Decimal("0")
        short_usd = Decimal("0")
        for pos in portfolio.positions:
            notional = pos.size * pos.current_price
            if pos.side == OrderSide.BUY:
                long_usd += notional
            else:
                short_usd += notional

        net_delta = long_usd - short_usd
        delta_pct = float(net_delta / portfolio.total_capital)

        log.debug(
            "hedge_manager.delta",
            net_delta_usd=round(float(net_delta), 2),
            delta_pct=round(delta_pct * 100, 2),
        )

        if abs(delta_pct) > _DELTA_TOLERANCE:
            await self._place_hedge(net_delta, portfolio.total_capital)

    async def _place_hedge(self, net_delta: Decimal, nav: Decimal) -> None:
        # We want to neutralise half the excess delta
        target_reduction = net_delta * Decimal("0.5")
        hedge_side = OrderSide.SELL if target_reduction > Decimal("0") else OrderSide.BUY

        hedge_usd = abs(target_reduction)
        if hedge_usd < Decimal("50"):
            return

        # Get current BTC price from Redis
        btc_price_raw = await self.state.redis.get("prices:BTC/USDT")
        if not btc_price_raw:
            return
        import json

        btc_data = json.loads(btc_price_raw)
        btc_price = Decimal(str(btc_data.get("last", 0)))
        if btc_price <= Decimal("0"):
            return

        hedge_qty = hedge_usd / btc_price
        stop_pct = Decimal("0.05")
        if hedge_side == OrderSide.SELL:
            stop = btc_price * (Decimal("1") + stop_pct)
        else:
            stop = btc_price * (Decimal("1") - stop_pct)

        proposal = TradeProposal(
            strategy_id=_HEDGE_STRATEGY_ID,
            agent_id=self.AGENT_ID,
            symbol=_HEDGE_SYMBOL,
            exchange=Exchange.BINANCE,
            asset_class=AssetClass.CRYPTO,
            side=hedge_side,
            order_type=OrderType.MARKET,
            size=hedge_qty.quantize(Decimal("0.000001")),
            size_usd=hedge_usd.quantize(Decimal("0.01")),
            stop_loss=stop.quantize(Decimal("0.01")),
            confidence_score=0.80,
            rationale=f"Delta hedge: net_delta={float(net_delta):.2f} nav={float(nav):.2f}",
        )
        await self.publish(
            KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "HedgeProposal"
        )
        self._hedge_position_usd += target_reduction * Decimal("-1")
        log.info(
            "hedge_manager.hedge_placed",
            side=hedge_side.value,
            hedge_usd=round(float(hedge_usd), 2),
            btc_price=float(btc_price),
        )
