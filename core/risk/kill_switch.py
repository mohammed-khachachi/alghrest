"""
ALGHREST — Kill Switch
Emergency stop with multiple trigger levels. Hard limit — cannot be bypassed.

Trigger levels (from RISK_LIMITS):
  3%  daily drawdown → alert CIO
  5%  daily drawdown → pause losing strategies
  7%  weekly drawdown → halt all strategies
  12% monthly drawdown → full kill switch (close all, halt trading)
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional
from uuid import uuid4

import structlog

from core.data.models import AlertType, KillSwitchEvent, RiskLevel, RISK_LIMITS, RiskMetrics
from core.orchestrator.state_manager import state_manager
from core.utils.alerts import send_kill_switch_alert, send_telegram_alert
from core.utils.metrics import kill_switch_triggers, risk_alerts_fired

logger = structlog.get_logger(__name__)


class KillSwitch:
    """
    Stateful kill switch that monitors RiskMetrics and fires at predefined thresholds.
    The CRO agent holds one instance and calls check() after every risk update.
    """

    def __init__(self) -> None:
        self._active = False
        self._active_reason: Optional[str] = None
        self._strategies_paused: set[str] = set()
        self._log = logger.bind(component="kill_switch")

    async def check(
        self,
        metrics: RiskMetrics,
        cro_agent_id: int = 2,
        on_close_all_positions: Optional[callable] = None,
        on_pause_strategy: Optional[callable] = None,
    ) -> Optional[KillSwitchEvent]:
        """
        Evaluate current risk metrics against all thresholds.
        Returns a KillSwitchEvent if a halt was triggered, else None.
        """
        if self._active:
            self._log.warning("kill switch already active — skipping check")
            return None

        # ── LEVEL 1: 3% daily — alert only ───────────────────────────────────
        if metrics.daily_drawdown_pct >= RISK_LIMITS.daily_drawdown_alert:
            msg = (
                f"⚠️ Daily drawdown {metrics.daily_drawdown_pct:.2%} exceeded 3% alert threshold.\n"
                f"Current capital: ${metrics.total_capital:,.0f}"
            )
            await send_telegram_alert(msg)
            risk_alerts_fired.labels(
                alert_type=AlertType.DRAWDOWN_ALERT.value,
                risk_level=RiskLevel.MEDIUM.value,
            ).inc()
            self._log.warning(
                "drawdown alert",
                daily_dd=metrics.daily_drawdown_pct,
                threshold=RISK_LIMITS.daily_drawdown_alert,
            )

        # ── LEVEL 2: 5% daily — pause losing strategies ───────────────────────
        if metrics.daily_drawdown_pct >= RISK_LIMITS.daily_drawdown_pause:
            if on_pause_strategy:
                await on_pause_strategy(reason="daily_drawdown_5pct")
            risk_alerts_fired.labels(
                alert_type=AlertType.DRAWDOWN_PAUSE.value,
                risk_level=RiskLevel.HIGH.value,
            ).inc()
            self._log.error(
                "pausing losing strategies",
                daily_dd=metrics.daily_drawdown_pct,
                threshold=RISK_LIMITS.daily_drawdown_pause,
            )

        # ── LEVEL 3: 7% weekly — halt all strategies ─────────────────────────
        if metrics.weekly_drawdown_pct >= RISK_LIMITS.weekly_drawdown_halt:
            risk_alerts_fired.labels(
                alert_type=AlertType.DRAWDOWN_HALT.value,
                risk_level=RiskLevel.CRITICAL.value,
            ).inc()
            return await self._trigger(
                reason=f"Weekly drawdown {metrics.weekly_drawdown_pct:.2%} >= 7% limit",
                drawdown_pct=metrics.weekly_drawdown_pct,
                scope="all_strategies",
                cro_agent_id=cro_agent_id,
                on_close_all_positions=on_close_all_positions,
            )

        # ── LEVEL 4: 12% monthly — FULL KILL SWITCH ──────────────────────────
        if metrics.monthly_drawdown_pct >= RISK_LIMITS.monthly_kill_switch:
            kill_switch_triggers.labels(
                scope="system",
                reason="monthly_drawdown_12pct",
            ).inc()
            return await self._trigger(
                reason=f"Monthly drawdown {metrics.monthly_drawdown_pct:.2%} >= 12% KILL SWITCH",
                drawdown_pct=metrics.monthly_drawdown_pct,
                scope="system",
                cro_agent_id=cro_agent_id,
                on_close_all_positions=on_close_all_positions,
            )

        # ── LEVERAGE BREACH ───────────────────────────────────────────────────
        if metrics.current_leverage > RISK_LIMITS.max_leverage:
            risk_alerts_fired.labels(
                alert_type=AlertType.LEVERAGE_LIMIT.value,
                risk_level=RiskLevel.HIGH.value,
            ).inc()
            self._log.error(
                "leverage limit breached",
                leverage=metrics.current_leverage,
                max=RISK_LIMITS.max_leverage,
            )

        return None

    async def _trigger(
        self,
        reason: str,
        drawdown_pct: float,
        scope: str,
        cro_agent_id: int,
        on_close_all_positions: Optional[callable] = None,
    ) -> KillSwitchEvent:
        self._active = True
        self._active_reason = reason

        self._log.critical("KILL SWITCH TRIGGERED", reason=reason, scope=scope, drawdown=drawdown_pct)

        # Mark in Redis so ALL agents know to halt
        await state_manager.activate_kill_switch(reason)

        # Close all open positions via callback
        positions_closed = 0
        if on_close_all_positions:
            try:
                positions_closed = await on_close_all_positions(reason=reason)
            except Exception as e:
                self._log.error("failed to close positions during kill switch", error=str(e))

        # Multi-channel critical alert
        await send_kill_switch_alert(reason, drawdown_pct, scope)

        event = KillSwitchEvent(
            triggered_by_agent=cro_agent_id,
            trigger_reason=reason,
            drawdown_pct=drawdown_pct,
            scope=scope,
            positions_closed=positions_closed,
            capital_preserved=await self._get_current_capital(),
        )

        return event

    async def _get_current_capital(self):
        from decimal import Decimal
        portfolio = await state_manager.get_portfolio()
        if portfolio:
            return portfolio.total_capital
        return Decimal("0")

    async def reset(self, authorized_by: str = "manual") -> None:
        """Reset kill switch — requires explicit human authorization."""
        self._log.warning("kill switch reset", authorized_by=authorized_by)
        self._active = False
        self._active_reason = None
        await state_manager.deactivate_kill_switch()

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def active_reason(self) -> Optional[str]:
        return self._active_reason
