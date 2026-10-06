"""
Agent 32 — Compliance Agent
Trade logging, position limit enforcement, and regulatory reporting.
Ensures every fill is recorded and flagged for compliance review.
"""

from __future__ import annotations

import asyncio
import csv
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from agents.base_agent import BaseAgent
from core.data.models import (
    RISK_LIMITS,
    AgentConfig,
    AlertType,
    Fill,
    KafkaTopic,
    RiskAlert,
    RiskLevel,
)

log = structlog.get_logger(__name__)

_LOG_DIR = Path("logs/compliance")
_WASH_TRADE_WINDOW = 60  # Seconds — same symbol buy+sell within 60s = potential wash trade
_MAX_POSITION_PCT = RISK_LIMITS.max_single_asset  # 5% hard cap per asset
_SANCTIONS_KEYWORDS = ["OFAC", "SDN", "sanctioned"]


class ComplianceAgent(BaseAgent):
    """
    Agent 32 — Compliance.
    1. Logs every fill to a daily CSV audit trail.
    2. Checks for wash trades (same symbol, opposite side, within 60s).
    3. Verifies position limits after every fill.
    4. Generates daily compliance reports.
    """

    AGENT_ID = 32

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=7,
            name="ComplianceAgent",
            config=config,
        )
        self._fill_log: list[Fill] = []
        self._recent_fills: dict[str, list[tuple[str, datetime]]] = {}  # symbol → [(side, ts)]
        self._today_log_path: Path | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._rotate_log()
        log.info("compliance_agent.initialized", log_dir=str(_LOG_DIR))

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.FILLS_CONFIRMED, KafkaTopic.PROPOSALS_BUS])
        await consumer.initialize()
        daily_report_task = asyncio.create_task(self._daily_report_loop())
        try:
            async for msg in consumer.stream():
                # Monitoring must keep recording fills and alerts during a halt.
                try:
                    topic = msg.get("topic", "")
                    if topic == KafkaTopic.FILLS_CONFIRMED.value:
                        await self._process_fill(msg)
                    elif topic == KafkaTopic.PROPOSALS_BUS.value:
                        await self._screen_proposal(msg)
                except Exception as exc:
                    log.warning("compliance_agent.error", error=str(exc))
        finally:
            daily_report_task.cancel()
            await asyncio.gather(daily_report_task, return_exceptions=True)
            await consumer.shutdown()

    async def shutdown(self) -> None:
        await self._flush_log()
        log.info("compliance_agent.shutdown", fills_logged=len(self._fill_log))

    # ── Fill Processing ────────────────────────────────────────────────────────

    async def _process_fill(self, msg: dict[str, Any]) -> None:
        fill = Fill.model_validate(msg.get("payload", msg))

        # Write to CSV audit trail
        await self._log_fill(fill)

        # Wash trade detection
        await self._check_wash_trade(fill)

        # Position limit check post-fill
        await self._check_position_limits(fill)

        self._fill_log.append(fill)

    async def _log_fill(self, fill: Fill) -> None:
        self._rotate_log()
        if self._today_log_path is None:
            raise RuntimeError("Compliance log path was not initialized")
        row = {
            "fill_id": str(fill.fill_id),
            "order_id": str(fill.order_id),
            "exchange_order_id": fill.exchange_order_id,
            "symbol": fill.symbol,
            "exchange": fill.exchange.value,
            "side": fill.side.value,
            "fill_size": str(fill.fill_size),
            "fill_price": str(fill.fill_price),
            "fee": str(fill.fee),
            "fee_currency": fill.fee_currency,
            "is_maker": str(fill.is_maker),
            "strategy_id": fill.strategy_id or "",
            "timestamp": fill.timestamp.isoformat(),
        }
        try:
            with open(self._today_log_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(row.keys()))
                if f.tell() == 0:
                    writer.writeheader()
                writer.writerow(row)
        except Exception as exc:
            log.error("compliance_agent.log_write_error", error=str(exc))

    async def _check_wash_trade(self, fill: Fill) -> None:
        sym = fill.symbol
        side = fill.side.value
        now = fill.timestamp

        recent = self._recent_fills.setdefault(sym, [])
        # Prune old entries
        recent[:] = [(s, ts) for s, ts in recent if (now - ts).total_seconds() < _WASH_TRADE_WINDOW]

        for prev_side, _ in recent:
            if prev_side != side:
                # Opposite side for same symbol within 60s — flag
                await self._raise_alert(
                    alert_type=AlertType.WASH_TRADE_RISK,
                    risk_level=RiskLevel.HIGH,
                    message=f"Potential wash trade: {sym} {prev_side} → {side} within {_WASH_TRADE_WINDOW}s",
                    triggered_value=1.0,
                    threshold_value=0.0,
                    recommended_action="Review fill sequence for wash trade compliance.",
                )
                break

        recent.append((side, now))

    async def _check_position_limits(self, fill: Fill) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None or portfolio.total_capital <= Decimal("0"):
            return

        for pos in portfolio.positions:
            if pos.symbol != fill.symbol:
                continue
            notional = pos.size * pos.current_price
            pct = float(notional / portfolio.total_capital)
            if pct > _MAX_POSITION_PCT:
                await self._raise_alert(
                    alert_type=AlertType.POSITION_LIMIT,
                    risk_level=RiskLevel.CRITICAL,
                    message=f"Position limit breach: {fill.symbol} = {pct*100:.1f}% of NAV (limit {_MAX_POSITION_PCT*100:.0f}%)",
                    triggered_value=pct,
                    threshold_value=_MAX_POSITION_PCT,
                    recommended_action=f"Reduce {fill.symbol} position immediately.",
                )

    # ── Proposal Screening ────────────────────────────────────────────────────

    async def _screen_proposal(self, msg: dict[str, Any]) -> None:
        msg = msg.get("payload", msg)
        rationale = msg.get("rationale", "").lower()
        symbol = msg.get("symbol", "")
        for keyword in _SANCTIONS_KEYWORDS:
            if keyword.lower() in rationale or keyword.lower() in symbol.lower():
                await self._raise_alert(
                    alert_type=AlertType.SANCTIONS_HIT,
                    risk_level=RiskLevel.CRITICAL,
                    message=f"Sanctions keyword '{keyword}' in proposal: {symbol}",
                    triggered_value=1.0,
                    threshold_value=0.0,
                    recommended_action="Block this trade and escalate to compliance team.",
                )

    # ── Daily Report ──────────────────────────────────────────────────────────

    async def _daily_report_loop(self) -> None:
        while True:
            await asyncio.sleep(3600)
            now = datetime.utcnow()
            if now.hour == 23 and now.minute >= 50:
                await self._generate_daily_report()

    async def _generate_daily_report(self) -> None:
        today = date.today().isoformat()
        fills_today = [f for f in self._fill_log if f.timestamp.date() == date.today()]
        total_volume = sum(f.fill_size * f.fill_price for f in fills_today)
        total_fees = sum(f.fee for f in fills_today)
        report = {
            "date": today,
            "total_fills": len(fills_today),
            "total_volume_usd": str(total_volume),
            "total_fees": str(total_fees),
            "exchanges": list({f.exchange.value for f in fills_today}),
            "symbols_traded": list({f.symbol for f in fills_today}),
            "log_file": str(self._today_log_path),
        }
        report_path = _LOG_DIR / f"report_{today}.json"
        with open(report_path, "w") as fp:
            json.dump(report, fp, indent=2, default=str)
        log.info("compliance_agent.daily_report", **report)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _rotate_log(self) -> None:
        today_str = date.today().isoformat()
        new_path = _LOG_DIR / f"fills_{today_str}.csv"
        if new_path != self._today_log_path:
            self._today_log_path = new_path

    async def _flush_log(self) -> None:
        log.info("compliance_agent.flushed", fills=len(self._fill_log))

    async def _raise_alert(
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
        await self.publish(KafkaTopic.RISK_ALERTS, alert.model_dump(mode="json"), "ComplianceAlert")
        log.warning("compliance_agent.alert", alert_type=alert_type.value, message=message)
