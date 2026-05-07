"""
Agent 31 — Alert Manager
Telegram bot for trade signals, daily P&L summaries, and critical alerts.
Also handles PagerDuty escalation for kill-switch and agent crash events.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import httpx
import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import (
    AgentConfig,
    AlertType,
    KafkaTopic,
    RiskAlert,
    RiskLevel,
)

log = structlog.get_logger(__name__)

_DAILY_REPORT_HOUR = 20          # 20:00 UTC daily summary
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_PAGERDUTY_API = "https://events.pagerduty.com/v2/enqueue"
_COOLDOWN_SECONDS = 300           # Suppress duplicate alerts for 5 min
_MAX_RETRIES = 3


class AlertManager(BaseAgent):
    """
    Agent 31 — Alert Manager.
    Routes alerts to Telegram (trade signals, drawdown warnings) and
    PagerDuty (critical kill-switch and connectivity alerts).
    """

    AGENT_ID = 31

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=7,
            name="AlertManager",
            config=config,
        )
        self._http: Optional[httpx.AsyncClient] = None
        self._sent_alerts: dict[str, datetime] = {}   # dedup key → last sent
        self._last_daily_report: Optional[datetime] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        self._http = httpx.AsyncClient(timeout=10.0)
        log.info(
            "alert_manager.initialized",
            telegram=bool(settings.telegram_bot_token),
            pagerduty=bool(settings.pagerduty_integration_key),
        )

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.RISK_ALERTS, KafkaTopic.PORTFOLIO_STATE])
        daily_task = asyncio.create_task(self._daily_report_loop())
        try:
            async for msg in consumer.stream():
                if await self.is_halted():
                    continue
                try:
                    topic = msg.get("topic", "")
                    await self._dispatch(topic, msg)
                except Exception as exc:
                    log.warning("alert_manager.dispatch_error", error=str(exc))
        finally:
            daily_task.cancel()

    async def shutdown(self) -> None:
        if self._http:
            await self._http.aclose()
        log.info("alert_manager.shutdown")

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def _dispatch(self, topic: str, msg: dict) -> None:
        if topic == KafkaTopic.RISK_ALERTS.value:
            await self._handle_risk_alert(msg)
        elif topic == KafkaTopic.PORTFOLIO_STATE.value:
            await self._handle_portfolio_event(msg)

    async def _handle_risk_alert(self, msg: dict) -> None:
        alert_type_raw = msg.get("alert_type", "")
        risk_level_raw = msg.get("risk_level", "")
        message = msg.get("message", "")

        dedup_key = f"{alert_type_raw}:{message[:40]}"
        if self._is_in_cooldown(dedup_key):
            return
        self._mark_sent(dedup_key)

        try:
            risk_level = RiskLevel(risk_level_raw)
        except ValueError:
            risk_level = RiskLevel.MEDIUM

        emoji = {"LOW": "ℹ️", "MEDIUM": "⚠️", "HIGH": "🚨", "CRITICAL": "🔴"}.get(
            risk_level.value, "⚠️"
        )
        text = (
            f"{emoji} *ALGHREST ALERT*\n"
            f"Type: `{alert_type_raw}`\n"
            f"Level: `{risk_level.value}`\n"
            f"Message: {message}\n"
            f"Action: {msg.get('recommended_action', 'Review system.')}\n"
            f"Time: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}`"
        )
        await self._send_telegram(text)

        # Escalate to PagerDuty for critical
        if risk_level == RiskLevel.CRITICAL:
            await self._send_pagerduty(
                summary=f"ALGHREST CRITICAL: {alert_type_raw}",
                details=msg,
            )

    async def _handle_portfolio_event(self, msg: dict) -> None:
        event = msg.get("event", "")
        if event == "capital_reallocation":
            weights = msg.get("weights", {})
            regime = msg.get("regime", "")
            text = (
                f"🔄 *Capital Reallocation*\n"
                f"Regime: `{regime}`\n"
                + "\n".join(f"  • {k}: `{v*100:.1f}%`" for k, v in weights.items())
            )
            await self._send_telegram(text)

    # ── Daily Report ──────────────────────────────────────────────────────────

    async def _daily_report_loop(self) -> None:
        while True:
            await asyncio.sleep(60)
            now = datetime.utcnow()
            if now.hour == _DAILY_REPORT_HOUR and now.minute < 5:
                if self._last_daily_report is None or (now - self._last_daily_report) > timedelta(hours=23):
                    await self._send_daily_report()
                    self._last_daily_report = now

    async def _send_daily_report(self) -> None:
        portfolio = await self.state.get_portfolio()
        tracker_raw = await self.state.redis.get("portfolio_tracker:latest")

        if not portfolio:
            return

        tracker = json.loads(tracker_raw) if tracker_raw else {}
        sharpe = tracker.get("sharpe_90d", "N/A")
        dd = tracker.get("drawdown_pct", 0.0)

        daily_pnl = float(portfolio.daily_pnl)
        pnl_emoji = "🟢" if daily_pnl >= 0 else "🔴"
        text = (
            f"📊 *ALGHREST Daily Report* — {datetime.utcnow().strftime('%Y-%m-%d')}\n\n"
            f"{pnl_emoji} Daily P&L: `{daily_pnl:+.2f} USD`\n"
            f"💼 Capital: `{float(portfolio.total_capital):,.0f} USD`\n"
            f"📉 Drawdown: `{dd:.2f}%`\n"
            f"📈 Sharpe (90d): `{sharpe}`\n"
            f"🔢 Open Positions: `{portfolio.open_position_count}`\n"
            f"⚖️ Leverage: `{portfolio.leverage:.2f}x`\n"
            f"🌐 Env: `{settings.environment}`"
        )
        await self._send_telegram(text)
        log.info("alert_manager.daily_report_sent")

    # ── Telegram ──────────────────────────────────────────────────────────────

    async def _send_telegram(self, text: str) -> None:
        token = settings.telegram_bot_token
        chat_id = settings.telegram_chat_id
        if not token or not chat_id:
            log.debug("alert_manager.telegram_not_configured")
            return
        url = _TELEGRAM_API.format(token=token)
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._http.post(url, json=payload)
                if resp.status_code == 200:
                    return
                log.warning("alert_manager.telegram_error", status=resp.status_code, attempt=attempt)
            except Exception as exc:
                log.warning("alert_manager.telegram_exception", error=str(exc), attempt=attempt)
                await asyncio.sleep(2 ** attempt)

    # ── PagerDuty ─────────────────────────────────────────────────────────────

    async def _send_pagerduty(self, summary: str, details: dict) -> None:
        key = settings.pagerduty_integration_key
        if not key:
            log.debug("alert_manager.pagerduty_not_configured")
            return
        payload = {
            "routing_key": key,
            "event_action": "trigger",
            "payload": {
                "summary": summary,
                "severity": "critical",
                "source": "alghrest",
                "custom_details": details,
            },
        }
        try:
            resp = await self._http.post(_PAGERDUTY_API, json=payload)
            if resp.status_code not in (200, 202):
                log.error("alert_manager.pagerduty_error", status=resp.status_code)
        except Exception as exc:
            log.error("alert_manager.pagerduty_exception", error=str(exc))

    # ── Dedup Helpers ─────────────────────────────────────────────────────────

    def _is_in_cooldown(self, key: str) -> bool:
        last = self._sent_alerts.get(key)
        if last is None:
            return False
        return (datetime.utcnow() - last).total_seconds() < _COOLDOWN_SECONDS

    def _mark_sent(self, key: str) -> None:
        self._sent_alerts[key] = datetime.utcnow()
        # Prune old entries
        cutoff = datetime.utcnow() - timedelta(seconds=_COOLDOWN_SECONDS * 2)
        self._sent_alerts = {k: v for k, v in self._sent_alerts.items() if v > cutoff}
