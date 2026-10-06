"""
Agent 25 — Liquidation Guard
Monitors margin levels on all leveraged positions.
Sends pre-emptive reduce orders when margin ratio drops near liquidation.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import structlog

from agents.base_agent import BaseAgent
from core.data.models import (
    AgentConfig,
    AlertType,
    AssetClass,
    KafkaTopic,
    OrderSide,
    OrderType,
    Position,
    RiskAlert,
    RiskLevel,
    TradeProposal,
)

log = structlog.get_logger(__name__)

_CHECK_INTERVAL = 10  # Check margin every 10 seconds
_MARGIN_WARN_PCT = 0.20  # Warn at 20% margin ratio remaining
_MARGIN_REDUCE_PCT = 0.12  # Auto-reduce at 12% margin ratio
_MARGIN_EMERGENCY_PCT = 0.06  # Emergency close at 6% margin ratio
_REDUCE_SIZE_PCT = 0.30  # Reduce position by 30% on warning


class LiquidationGuard(BaseAgent):
    """
    Agent 25 — Margin / liquidation protector.
    Fast polling loop that catches deteriorating margin before the exchange
    triggers forced liquidation.
    """

    AGENT_ID = 25

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="LiquidationGuard",
            config=config,
        )
        self._alerted_positions: set[str] = set()

    async def initialize(self) -> None:
        log.info("liquidation_guard.initialized", check_interval=_CHECK_INTERVAL)

    async def run(self) -> None:
        while True:
            await asyncio.sleep(_CHECK_INTERVAL)
            if await self.is_halted():
                continue
            try:
                await self._scan_margins()
            except Exception as exc:
                log.error("liquidation_guard.scan_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("liquidation_guard.shutdown")

    # ── Margin Scan ───────────────────────────────────────────────────────────

    async def _scan_margins(self) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        for pos in portfolio.positions:
            # Estimate margin ratio: (equity - unrealised) / notional
            # Real implementation would use exchange margin data via CCXT
            notional = pos.size * pos.current_price
            if notional <= Decimal("0"):
                continue

            # Proxy margin ratio using stop distance as collateral proxy
            if pos.stop_loss and pos.current_price > Decimal("0"):
                stop_distance = abs(pos.current_price - pos.stop_loss)
                margin_ratio = float(stop_distance / pos.current_price)
            else:
                continue  # Can't estimate without stop loss

            await self._handle_margin(pos, margin_ratio, notional)

    async def _handle_margin(self, pos: Position, margin_ratio: float, notional: Decimal) -> None:
        sym = pos.symbol

        if margin_ratio <= _MARGIN_EMERGENCY_PCT:
            log.critical(
                "liquidation_guard.EMERGENCY_CLOSE",
                symbol=sym,
                margin_ratio=round(margin_ratio * 100, 2),
            )
            await self._emergency_close(pos, notional)
            return

        if margin_ratio <= _MARGIN_REDUCE_PCT:
            if sym not in self._alerted_positions:
                await self._partial_reduce(pos, notional)
                self._alerted_positions.add(sym)
                log.warning(
                    "liquidation_guard.partial_reduce",
                    symbol=sym,
                    margin_ratio=round(margin_ratio * 100, 2),
                )
            return

        if margin_ratio <= _MARGIN_WARN_PCT:
            await self._send_margin_alert(sym, margin_ratio)
            return

        # Recovered — clear alert state
        self._alerted_positions.discard(sym)

    async def _partial_reduce(self, pos: Position, notional: Decimal) -> None:
        reduce_usd = notional * Decimal(str(_REDUCE_SIZE_PCT))
        price = float(pos.current_price)
        if price <= 0:
            return
        reduce_qty = reduce_usd / Decimal(str(price))

        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY

        proposal = TradeProposal(
            strategy_id="liquidation_guard",
            agent_id=self.AGENT_ID,
            symbol=pos.symbol,
            exchange=pos.exchange,
            asset_class=AssetClass.CRYPTO,
            side=close_side,
            order_type=OrderType.MARKET,
            size=reduce_qty.quantize(Decimal("0.000001")),
            size_usd=reduce_usd.quantize(Decimal("0.01")),
            urgency="immediate",
            confidence_score=1.0,
            rationale=f"Margin protection partial close: margin_ratio={_MARGIN_REDUCE_PCT*100:.0f}% breached",
        )
        await self.publish(
            KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "LiquidationGuardProposal"
        )

    async def _emergency_close(self, pos: Position, notional: Decimal) -> None:
        price = float(pos.current_price)
        if price <= 0:
            return
        full_qty = notional / Decimal(str(price))
        close_side = OrderSide.SELL if pos.side == OrderSide.BUY else OrderSide.BUY

        proposal = TradeProposal(
            strategy_id="liquidation_guard_emergency",
            agent_id=self.AGENT_ID,
            symbol=pos.symbol,
            exchange=pos.exchange,
            asset_class=AssetClass.CRYPTO,
            side=close_side,
            order_type=OrderType.MARKET,
            size=full_qty.quantize(Decimal("0.000001")),
            size_usd=notional.quantize(Decimal("0.01")),
            urgency="immediate",
            confidence_score=1.0,
            rationale="EMERGENCY close: margin near liquidation threshold",
        )
        await self.publish(
            KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "EmergencyClose"
        )
        await self._send_margin_alert(pos.symbol, 0.0, is_emergency=True)

    async def _send_margin_alert(
        self, symbol: str, margin_ratio: float, is_emergency: bool = False
    ) -> None:
        level = RiskLevel.CRITICAL if is_emergency else RiskLevel.HIGH
        alert = RiskAlert(
            alert_type=AlertType.DRAWDOWN_ALERT,
            risk_level=level,
            source_agent_id=self.AGENT_ID,
            message=f"{'EMERGENCY' if is_emergency else 'WARNING'}: {symbol} margin ratio {margin_ratio*100:.1f}% — liquidation risk",
            triggered_value=margin_ratio,
            threshold_value=_MARGIN_EMERGENCY_PCT if is_emergency else _MARGIN_WARN_PCT,
            recommended_action=(
                "Reduce leveraged exposure immediately."
                if is_emergency
                else "Monitor margin closely."
            ),
        )
        await self.publish(KafkaTopic.RISK_ALERTS, alert.model_dump(mode="json"), "RiskAlert")
