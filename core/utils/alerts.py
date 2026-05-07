"""
ALGHREST — Alerting Utilities
Sends critical alerts via Telegram and PagerDuty.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog

from core.config import settings

logger = structlog.get_logger(__name__)


async def send_telegram_alert(message: str, parse_mode: str = "HTML") -> None:
    """Send alert message to the admin Telegram chat."""
    if not settings.telegram_bot_token or not settings.telegram_admin_id:
        logger.warning("Telegram not configured — alert not sent", message=message[:100])
        return

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_admin_id,
        "text": message,
        "parse_mode": parse_mode,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
    except Exception as e:
        logger.error("Failed to send Telegram alert", error=str(e))


async def send_pagerduty_alert(summary: str, severity: str = "critical", details: Optional[dict] = None) -> None:
    """Trigger a PagerDuty incident for critical system events."""
    if not settings.pagerduty_api_key:
        logger.warning("PagerDuty not configured — incident not created", summary=summary)
        return

    payload = {
        "routing_key": settings.pagerduty_api_key,
        "event_action": "trigger",
        "payload": {
            "summary": f"ALGHREST: {summary}",
            "severity": severity,
            "source": "alghrest-trading-system",
            "custom_details": details or {},
        },
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
            )
            r.raise_for_status()
            logger.info("PagerDuty incident created", summary=summary)
    except Exception as e:
        logger.error("Failed to create PagerDuty incident", error=str(e))


async def send_kill_switch_alert(reason: str, drawdown_pct: float, scope: str) -> None:
    """Multi-channel alert for kill switch activation."""
    message = (
        f"🚨 <b>KILL SWITCH ACTIVATED</b>\n\n"
        f"Scope: {scope}\n"
        f"Reason: {reason}\n"
        f"Drawdown: {drawdown_pct:.2%}\n"
        f"Action: All positions being closed. Trading halted."
    )

    await asyncio.gather(
        send_telegram_alert(message),
        send_pagerduty_alert(
            f"Kill Switch Activated — {reason}",
            severity="critical",
            details={"drawdown_pct": drawdown_pct, "scope": scope, "reason": reason},
        ),
        return_exceptions=True,
    )
