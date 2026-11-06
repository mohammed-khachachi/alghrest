"""
Agent 02 — Risk Governor
Portfolio-level risk limits, kill switch, and drawdown circuit breakers.
Monitors the entire system continuously and intervenes when limits are breached.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal

import structlog

from agents.base_agent import BaseAgent
from core.accounting.performance import require_performance
from core.config import settings
from core.data.models import (
    RISK_LIMITS,
    AgentConfig,
    AlertType,
    KafkaTopic,
    KillSwitchEvent,
    Portfolio,
    RiskAlert,
    RiskLevel,
    RiskMetrics,
)

log = structlog.get_logger(__name__)

_CHECK_INTERVAL = 30  # Portfolio risk check every 30 seconds
_LEVERAGE_CHECK_INTERVAL = 10  # Leverage checked more frequently


class RiskGovernor(BaseAgent):
    """
    Agent 02 — Risk Governor.
    The last line of defence before real money is lost.
    Runs two parallel loops:
      1. Full risk scan every 30 s
      2. Fast leverage check every 10 s
    Triggers kill switch when monthly drawdown exceeds 12%.
    """

    AGENT_ID = 2

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=1,
            name="RiskGovernor",
            config=config,
        )
        self._paused_strategies: set[str] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("risk_governor.initialized", performance_source="durable accountant")

    async def run(self) -> None:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(self._risk_loop())
            tasks.create_task(self._leverage_loop())
            tasks.create_task(self._consume_alerts())

    async def shutdown(self) -> None:
        log.info("risk_governor.shutdown")

    # ── Risk Scan Loop ─────────────────────────────────────────────────────────

    async def _risk_loop(self) -> None:
        while True:
            await asyncio.sleep(_CHECK_INTERVAL)
            try:
                await self._full_risk_scan()
            except Exception as exc:
                log.error("risk_governor.scan_error", error=str(exc))

    async def _full_risk_scan(self) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        performance = require_performance(portfolio)
        capital = portfolio.total_capital + portfolio.unrealized_pnl
        daily_dd = performance.drawdown(performance.day.unit_price)
        weekly_dd = performance.drawdown(performance.week.unit_price)
        monthly_dd = performance.drawdown(performance.month.unit_price)

        # Build and persist risk metrics
        metrics = RiskMetrics(
            timestamp=datetime.utcnow(),
            total_capital=capital,
            available_capital=portfolio.available_capital,
            unrealized_pnl=portfolio.unrealized_pnl,
            daily_pnl=portfolio.daily_pnl,
            daily_drawdown_pct=daily_dd,
            weekly_drawdown_pct=weekly_dd,
            monthly_drawdown_pct=monthly_dd,
            max_drawdown_pct=performance.drawdown(),
            current_leverage=portfolio.leverage,
            open_positions=portfolio.open_position_count,
        )
        await self.state.set_risk_metrics(metrics)

        if performance.drawdown() >= 0.25:
            await self._trigger_kill_switch(
                reason="Portfolio drawdown reached 25%", drawdown_pct=performance.drawdown()
            )
        else:
            await self._check_drawdown_limits(daily_dd, weekly_dd, monthly_dd)
        await self._check_position_concentration(portfolio)

    # ── Drawdown Checks ────────────────────────────────────────────────────────

    async def _check_drawdown_limits(
        self, daily_dd: float, weekly_dd: float, monthly_dd: float
    ) -> None:
        limits = RISK_LIMITS

        if monthly_dd >= limits.monthly_kill_switch:
            await self._trigger_kill_switch(
                reason=f"Monthly drawdown {monthly_dd*100:.2f}% breached kill-switch threshold {limits.monthly_kill_switch*100:.0f}%",
                drawdown_pct=monthly_dd,
            )
            return

        if weekly_dd >= limits.weekly_drawdown_halt:
            await self._publish_alert(
                alert_type=AlertType.DRAWDOWN_HALT,
                risk_level=RiskLevel.CRITICAL,
                message=f"Weekly drawdown {weekly_dd*100:.2f}% hit halt threshold. Halting all strategies.",
                triggered_value=weekly_dd,
                threshold_value=limits.weekly_drawdown_halt,
                recommended_action="Halt all strategy agents and await manual review.",
            )
            await self._halt_all_strategies()
            return

        if daily_dd >= limits.daily_drawdown_pause:
            await self._publish_alert(
                alert_type=AlertType.DRAWDOWN_PAUSE,
                risk_level=RiskLevel.HIGH,
                message=f"Daily drawdown {daily_dd*100:.2f}% — pausing underperforming strategies.",
                triggered_value=daily_dd,
                threshold_value=limits.daily_drawdown_pause,
                recommended_action="Pause strategies with negative daily P&L.",
            )
            return

        if daily_dd >= limits.daily_drawdown_alert:
            await self._publish_alert(
                alert_type=AlertType.DRAWDOWN_ALERT,
                risk_level=RiskLevel.MEDIUM,
                message=f"Daily drawdown {daily_dd*100:.2f}% — alerting CIO.",
                triggered_value=daily_dd,
                threshold_value=limits.daily_drawdown_alert,
                recommended_action="Review open positions. CIO notified.",
            )

    # ── Leverage Check ─────────────────────────────────────────────────────────

    async def _leverage_loop(self) -> None:
        while True:
            await asyncio.sleep(_LEVERAGE_CHECK_INTERVAL)
            try:
                portfolio = await self.state.get_portfolio()
                if portfolio:
                    await self._check_leverage(portfolio.leverage)
            except Exception as exc:
                log.warning("risk_governor.leverage_check_error", error=str(exc))

    async def _check_leverage(self, leverage: float) -> None:
        if leverage > RISK_LIMITS.max_leverage:
            await self._publish_alert(
                alert_type=AlertType.LEVERAGE_LIMIT,
                risk_level=RiskLevel.CRITICAL,
                message=f"Portfolio leverage {leverage:.2f}x exceeds hard limit {RISK_LIMITS.max_leverage:.1f}x.",
                triggered_value=leverage,
                threshold_value=RISK_LIMITS.max_leverage,
                recommended_action="Immediately reduce largest positions to bring leverage below limit.",
            )
            log.error(
                "risk_governor.leverage_breach",
                leverage=round(leverage, 3),
                limit=RISK_LIMITS.max_leverage,
            )

    # ── Position Concentration ─────────────────────────────────────────────────

    async def _check_position_concentration(self, portfolio: Portfolio) -> None:
        if not hasattr(portfolio, "positions") or not portfolio.positions:
            return
        if portfolio.total_capital <= Decimal("0"):
            return

        for pos in portfolio.positions:
            notional = pos.size * pos.current_price
            pct = float(notional / portfolio.total_capital)
            if pct > RISK_LIMITS.max_single_asset:
                await self._publish_alert(
                    alert_type=AlertType.POSITION_LIMIT,
                    risk_level=RiskLevel.HIGH,
                    message=f"{pos.symbol} notional {pct*100:.1f}% exceeds single-asset limit {RISK_LIMITS.max_single_asset*100:.0f}%.",
                    triggered_value=pct,
                    threshold_value=RISK_LIMITS.max_single_asset,
                    recommended_action=f"Reduce {pos.symbol} position.",
                )

    # ── Alert Consumer ─────────────────────────────────────────────────────────

    async def _consume_alerts(self) -> None:
        consumer = self.make_consumer([KafkaTopic.RISK_ALERTS])
        try:
            await consumer.initialize()
            async for msg in consumer.stream():
                payload = msg.get("payload", msg)
                if (
                    payload.get("halt_scope") != "global"
                    and payload.get("accounting_book_id") != settings.accounting_book_id
                ):
                    continue
                if await self.is_halted():
                    continue
                try:
                    payload = msg.get("payload", msg)
                    alert_type_raw = payload.get("alert_type", "")
                    if alert_type_raw == AlertType.CONSECUTIVE_LOSSES.value:
                        strategy_ids = payload.get("affected_strategy_ids") or []
                        strategy_id = strategy_ids[0] if strategy_ids else None
                        if strategy_id:
                            log.warning(
                                "risk_governor.consecutive_losses",
                                strategy_id=strategy_id,
                            )
                except Exception as exc:
                    log.warning("risk_governor.alert_consumer_error", error=str(exc))
        finally:
            await consumer.shutdown()

    # ── Kill Switch ────────────────────────────────────────────────────────────

    async def _trigger_kill_switch(self, reason: str, drawdown_pct: float) -> None:
        if await self.state.is_kill_switch_active():
            return  # already triggered

        log.critical(
            "risk_governor.KILL_SWITCH_TRIGGERED",
            reason=reason,
            drawdown_pct=round(drawdown_pct * 100, 2),
        )

        await self.state.activate_kill_switch(reason)

        event = KillSwitchEvent(
            triggered_by_agent=self.AGENT_ID,
            trigger_reason=reason,
            drawdown_pct=drawdown_pct,
            scope="system",
            capital_preserved=await self._get_current_capital(),
        )
        await self.publish(
            KafkaTopic.RISK_ALERTS,
            event.model_dump(mode="json"),
            "KillSwitchEvent",
        )

    async def _halt_all_strategies(self) -> None:
        await self.state.activate_kill_switch("weekly_drawdown_halt")
        await self.publish(
            KafkaTopic.RISK_ALERTS,
            {
                "event": "halt_all_strategies",
                "reason": "weekly_drawdown_halt",
                "issued_by": self.AGENT_ID,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "HaltAllStrategies",
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _drawdown(baseline: Decimal | None, current: Decimal) -> float:
        if baseline is None or baseline <= Decimal("0"):
            return 0.0
        if current >= baseline:
            return 0.0
        return float((baseline - current) / baseline)

    async def _get_current_capital(self) -> Decimal:
        portfolio = await self.state.get_portfolio()
        if portfolio:
            return portfolio.total_capital + portfolio.unrealized_pnl
        return Decimal("0")

    async def _publish_alert(
        self,
        alert_type: AlertType,
        risk_level: RiskLevel,
        message: str,
        triggered_value: float,
        threshold_value: float,
        recommended_action: str,
    ) -> None:
        alert = RiskAlert(
            alert_type=alert_type,
            risk_level=risk_level,
            source_agent_id=self.AGENT_ID,
            message=message,
            triggered_value=triggered_value,
            threshold_value=threshold_value,
            recommended_action=recommended_action,
        )
        await self.publish(
            KafkaTopic.RISK_ALERTS,
            alert.model_dump(mode="json"),
            "RiskAlert",
        )
        log.warning(
            "risk_governor.alert",
            alert_type=alert_type.value,
            risk_level=risk_level.value,
            triggered=round(triggered_value, 4),
        )
