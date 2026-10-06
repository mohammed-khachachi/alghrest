"""Monitoring continues during a halt and consumes actual Kafka payload envelopes."""

import csv
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from agents.tier7_monitoring import alert_manager as alerts, compliance_agent as compliance
from core.config import settings
from core.data.models import Fill, KafkaTopic
from tests.factories import FiniteConsumer, portfolio, position

pytestmark = pytest.mark.unit


def fill(**changes):
    return Fill(
        **(
            dict(
                order_id=uuid4(),
                exchange_order_id="test",
                symbol="BTC/USDT",
                exchange="binance",
                side="BUY",
                fill_size="1",
                fill_price="100",
                fee="1",
                timestamp=datetime.utcnow(),
            )
            | changes
        )
    )


async def test_compliance_logs_halted_fills_and_flags_wash_trades_and_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(compliance, "_LOG_DIR", tmp_path)
    agent = compliance.ComplianceAgent()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = True
    agent.state.get_portfolio.return_value = portfolio(positions=[position(size="10")])
    agent.publish = AsyncMock()
    fills = [fill(), fill(side="SELL"), fill(timestamp=datetime.utcnow() + timedelta(seconds=90))]
    messages = [
        {"topic": KafkaTopic.FILLS_CONFIRMED.value, "payload": f.model_dump(mode="json")}
        for f in fills
    ]
    messages.extend(
        [
            {
                "topic": KafkaTopic.PROPOSALS_BUS.value,
                "payload": {"rationale": "OFAC screening", "symbol": "BTC"},
            },
            {"topic": KafkaTopic.FILLS_CONFIRMED.value, "payload": {}},
        ]
    )
    consumer = FiniteConsumer(messages)
    monkeypatch.setattr(agent, "make_consumer", lambda topics: consumer)
    await agent.initialize()
    await agent.run()
    assert len(agent._fill_log) == 3
    assert len(agent._recent_fills["BTC/USDT"]) == 1
    kinds = [call.args[1]["alert_type"] for call in agent.publish.await_args_list]
    assert "WASH_TRADE_RISK" in kinds and "POSITION_LIMIT" in kinds and "SANCTIONS_HIT" in kinds
    with next(tmp_path.glob("fills_*.csv")).open() as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 3 and rows[0]["fill_price"] == "100"
    await agent._generate_daily_report()
    report = json.loads(next(tmp_path.glob("report_*.json")).read_text())
    assert report["total_fills"] == 3 and report["total_volume_usd"] == "300"
    await agent.shutdown()
    consumer.initialize.assert_awaited_once()
    consumer.shutdown.assert_awaited_once()


@pytest.mark.parametrize(
    "snapshot",
    [None, portfolio(total_capital=0), portfolio(positions=[position(symbol="ETH/USDT")])],
)
async def test_compliance_skips_missing_or_unrelated_positions(snapshot):
    agent = compliance.ComplianceAgent()
    agent.state = AsyncMock()
    agent.state.get_portfolio.return_value = snapshot
    agent.publish = AsyncMock()
    await agent._check_position_limits(fill())
    await agent._screen_proposal({"rationale": "normal trade", "symbol": "BTC"})
    agent.publish.assert_not_awaited()


async def test_alerts_continue_while_halted_and_escalate_only_critical(monkeypatch):
    agent = alerts.AlertManager()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = True
    agent._send_telegram = AsyncMock()
    agent._send_pagerduty = AsyncMock()
    messages = [
        {
            "topic": KafkaTopic.RISK_ALERTS.value,
            "payload": {"alert_type": "limit", "risk_level": "CRITICAL", "message": "breach"},
        },
        {
            "topic": KafkaTopic.RISK_ALERTS.value,
            "payload": {"alert_type": "limit", "risk_level": "CRITICAL", "message": "breach"},
        },
        {
            "topic": KafkaTopic.RISK_ALERTS.value,
            "payload": {"alert_type": "news", "risk_level": "INVALID", "message": "info"},
        },
        {
            "topic": KafkaTopic.PORTFOLIO_STATE.value,
            "payload": {
                "event": "capital_reallocation",
                "weights": {"test": 0.25},
                "regime": "RISK_ON",
            },
        },
        {"topic": "other", "payload": {}},
    ]
    consumer = FiniteConsumer(messages)
    monkeypatch.setattr(agent, "make_consumer", lambda topics: consumer)
    await agent.run()
    assert agent._send_telegram.await_count == 3
    agent._send_pagerduty.assert_awaited_once()
    assert "breach" in agent._send_telegram.await_args_list[0].args[0]
    assert "25.0%" in agent._send_telegram.await_args_list[-1].args[0]
    consumer.shutdown.assert_awaited_once()
    agent._sent_alerts["old"] = datetime.utcnow() - timedelta(hours=1)
    agent._mark_sent("new")
    assert "old" not in agent._sent_alerts and agent._is_in_cooldown("new")


@pytest.mark.parametrize("status", [200, 202, 500])
async def test_alert_transport_retries_and_escalation_responses(status, monkeypatch):
    agent = alerts.AlertManager()
    for setting in ("telegram_bot_token", "telegram_chat_id", "pagerduty_integration_key"):
        monkeypatch.setattr(settings, setting, "test-only")
    agent._http = AsyncMock()
    agent._http.post.return_value = httpx.Response(status)
    await agent._send_telegram("test")
    assert agent._http.post.await_count == (1 if status == 200 else 3)
    agent._http.post.reset_mock()
    await agent._send_pagerduty("test", {})
    agent._http.post.assert_awaited_once()
    await agent.shutdown()
    agent._http.aclose.assert_awaited_once()


async def test_alert_transport_disabled_uninitialized_and_failure(monkeypatch):
    agent = alerts.AlertManager()
    for setting in ("telegram_bot_token", "telegram_chat_id", "pagerduty_integration_key"):
        monkeypatch.setattr(settings, setting, "")
    await agent._send_telegram("test")
    await agent._send_pagerduty("test", {})
    for setting in ("telegram_bot_token", "telegram_chat_id", "pagerduty_integration_key"):
        monkeypatch.setattr(settings, setting, "test-only")
    with pytest.raises(RuntimeError):
        await agent._send_telegram("test")
    with pytest.raises(RuntimeError):
        await agent._send_pagerduty("test", {})
    agent._http = AsyncMock()
    agent._http.post.side_effect = httpx.ConnectError("offline")
    monkeypatch.setattr(alerts.asyncio, "sleep", AsyncMock())
    await agent._send_telegram("test")
    assert agent._http.post.await_count == 3
    await agent._send_pagerduty("test", {})


async def test_daily_report_uses_actual_portfolio_and_tracker():
    agent = alerts.AlertManager()
    agent.state = AsyncMock()
    agent.state.get_portfolio.return_value = None
    agent._send_telegram = AsyncMock()
    await agent._send_daily_report()
    agent._send_telegram.assert_not_awaited()
    agent.state.get_portfolio.return_value = portfolio(daily_pnl=-12)
    agent.state.redis.get.return_value = b'{"sharpe_90d":1.2,"drawdown_pct":3}'
    await agent._send_daily_report()
    assert "-12.00 USD" in agent._send_telegram.await_args.args[0]
    assert "3.00%" in agent._send_telegram.await_args.args[0]
