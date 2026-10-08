"""Telegram contracts use mocked HTTP/Redis exclusively; no real messages are sent."""

import csv
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import orjson
import pytest

from core.config import settings
from core.telegram import bot as broadcaster_module, bot_manager as module
from core.utils import alerts
from core.utils.audit_reporter import AuditReporter
from tests.factories import health, portfolio, position, risk

pytestmark = pytest.mark.unit


@pytest.fixture
def bot(monkeypatch):
    monkeypatch.setattr(settings, "telegram_admin_id", "42")
    manager = module.TelegramBotManager()
    manager._token = "test-only"
    manager.attach_redis(AsyncMock())
    manager._send = AsyncMock()
    manager._broadcast = AsyncMock()
    state = AsyncMock()
    state.get_portfolio.return_value = portfolio(positions=[position()], daily_pnl=-100)
    state.get_risk_metrics.return_value = risk(daily_drawdown_pct=0.03)
    state.get_all_agent_healths.return_value = [
        health(),
        health(agent_id=15, status="ERROR", last_error="timeout"),
    ]
    state.get_agent_health.return_value = health()
    state.is_kill_switch_active.return_value = False
    monkeypatch.setattr(import_module("core.orchestrator.state_manager"), "state_manager", state)
    manager.test_state = state
    return manager


@pytest.mark.parametrize(
    "command,args,fragment",
    [
        ("start", [], "Welcome"),
        ("help", [], "Command Reference"),
        ("status", [], "System Status"),
        ("agents", [], "Tier 4"),
        ("agent", ["14"], "Agent #14"),
        ("pnl", [], "$-100.00"),
        ("risk", [], "3.00%"),
        ("tier", ["4"], "Strategy"),
        ("tier", ["8"], "between 1 and 7"),
        ("tier", [], "Usage"),
        ("agent", [], "Usage"),
        ("pause", [], "Usage"),
        ("restart", [], "Usage"),
        ("killswitch", [], "Usage"),
        ("killswitch", ["invalid"], "Usage"),
    ],
)
async def test_command_responses_use_domain_state(bot, command, args, fragment):
    await getattr(bot, f"_cmd_{command}")("test-chat", args)
    assert fragment in bot._send.await_args.args[1]


@pytest.mark.parametrize(
    "command,getter",
    [("pnl", "get_portfolio"), ("risk", "get_risk_metrics"), ("agent", "get_agent_health")],
)
async def test_commands_handle_missing_domain_state(bot, command, getter):
    getattr(bot.test_state, getter).return_value = None
    await getattr(bot, f"_cmd_{command}")("chat", ["14"])
    assert any(text in bot._send.await_args.args[1] for text in ("not available", "not found"))


async def test_update_routing_and_empty_messages(bot):
    await bot._handle_update({})
    await bot._handle_update(
        {"message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}, "text": " "}}
    )
    bot.redis.sadd.assert_not_awaited()
    await bot._handle_update(
        {
            "message": {
                "chat": {"id": 42, "type": "private"},
                "from": {"id": 42},
                "text": "/agent@bot 14",
            }
        }
    )
    assert "Agent #14" in bot._send.await_args.args[1]
    bot.redis.sadd.assert_awaited_with(module._KEY_REGISTERED_CHATS, "42")
    await bot._handle_update(
        {"message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}, "text": "/unknown"}}
    )
    assert "Unknown command" in bot._send.await_args.args[1]


@pytest.mark.parametrize("command,value", [("pause", "PAUSE"), ("restart", "RESTART")])
async def test_control_commands_store_expiring_intent(bot, command, value):
    await getattr(bot, f"_cmd_{command}")("chat", ["14"])
    call = bot.redis.set.await_args
    assert call.args[0] == "alghrest:agent:command:14"
    assert orjson.loads(call.args[1])["command"] == value
    assert call.kwargs["ex"] == 300


async def test_kill_switch_commands_and_recent_alerts_use_mock_redis(bot):
    await bot._cmd_killswitch("chat", ["on"])
    assert bot.redis.set.await_args_list[0].args[0] == "alghrest:kill_switch:active"
    await bot._cmd_killswitch("chat", ["off"])
    bot.redis.delete.assert_any_await("alghrest:kill_switch:active")
    assert bot._broadcast.await_count == 2
    bot.redis.lrange.return_value = []
    await bot._cmd_alerts("chat", [])
    assert "No recent" in bot._send.await_args.args[1]
    bot.redis.lrange.return_value = [orjson.dumps({"severity": "CRITICAL", "message": "drawdown"})]
    await bot._cmd_alerts("chat", [])
    assert "drawdown" in bot._send.await_args.args[1]


async def test_registration_offset_storage_and_broadcast_deduplicates(bot, monkeypatch):
    bot.redis.smembers.return_value = {b"42", "43"}
    monkeypatch.setattr(settings, "telegram_chat_id", "42")
    monkeypatch.setattr(settings, "telegram_admin_id", "44")
    await module.TelegramBotManager._broadcast(bot, "test")
    assert {call.args[0] for call in bot._send.await_args_list} == {"42", "44"}
    assert bot._send.await_count == 2
    bot.redis.get.return_value = b"12"
    assert await bot._load_offset() == 12
    bot.redis.get.return_value = None
    assert await bot._load_offset() == 0
    await bot._save_offset(13)
    bot.redis.set.assert_awaited_with(module._KEY_LAST_UPDATE_ID, 13)


async def test_http_send_failure_and_missing_client_are_tolerated(bot):
    await module.TelegramBotManager._send(bot, "chat", "message")
    bot._client = AsyncMock()
    await module.TelegramBotManager._send(bot, "chat", "message")
    assert bot._client.post.await_args.kwargs["json"]["text"] == "message"
    bot._client.post.side_effect = httpx.ConnectError("offline")
    await module.TelegramBotManager._send(bot, "chat", "message")
    await bot.stop()
    bot._client.aclose.assert_awaited_once()


async def test_polling_advances_offset_after_handling(bot):
    bot.redis.get.return_value = b"8"
    bot._client = AsyncMock()
    bot._running = True

    async def get(*a, **kw):
        bot._running = False
        return SimpleNamespace(
            json=lambda: {
                "ok": True,
                "result": [
                    {
                        "update_id": 8,
                        "message": {
                            "chat": {"id": 42, "type": "private"},
                            "from": {"id": 42},
                            "text": "/help",
                        },
                    }
                ],
            }
        )

    bot._client.get.side_effect = get
    await bot._poll_loop()
    bot.redis.set.assert_awaited_with(module._KEY_LAST_UPDATE_ID, 9)
    assert "Command Reference" in bot._send.await_args.args[1]


async def test_disabled_bot_does_not_allocate_http_client():
    bot = module.TelegramBotManager()
    bot._token = ""
    await bot.start()
    assert bot._client is None
    with pytest.raises(RuntimeError):
        _ = bot.redis
    with pytest.raises(RuntimeError):
        await bot._poll_loop()


@pytest.mark.parametrize(
    "before,after,fragment",
    [
        ("RUNNING", "ERROR", "Status Change"),
        ("ERROR", "RUNNING", "Recovered"),
        ("RUNNING", "RUNNING", None),
    ],
)
async def test_watchdog_only_notifies_on_meaningful_status_change(
    bot, monkeypatch, before, after, fragment
):
    bot._prev_agent_statuses = {14: before}
    bot.test_state.get_all_agent_healths.return_value = [health(status=after)]
    bot._running = True

    async def tick(*a):
        bot._running = False

    monkeypatch.setattr(module.asyncio, "sleep", tick)
    await bot._watchdog_loop()
    if fragment:
        assert fragment in bot._broadcast.await_args.args[0]
    else:
        bot._broadcast.assert_not_awaited()


async def test_alert_pubsub_ignores_subscription_messages(bot):
    bot._running = True
    pubsub = MagicMock(subscribe=AsyncMock())

    async def messages():
        yield {"type": "subscribe"}
        yield {
            "type": "message",
            "data": orjson.dumps(
                {"severity": "CRITICAL", "message": "risk test", "limit_name": "drawdown"}
            ),
        }
        bot._running = False

    pubsub.listen = messages
    bot.redis.pubsub = MagicMock(return_value=pubsub)
    await bot._alert_loop()
    assert "risk test" in bot._broadcast.await_args.args[0]


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
async def test_copy_signal_formats_prices_and_handles_transport_failure(monkeypatch, direction):
    client = AsyncMock()
    client.post.return_value = httpx.Response(200)
    monkeypatch.setattr(broadcaster_module.httpx, "AsyncClient", lambda: client)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-only")
    monkeypatch.setenv("TELEGRAM_CHANNEL_ID", "test-channel")
    broadcaster = broadcaster_module.TelegramBroadcaster()
    await broadcaster.broadcast_signal("BTC/USDT", direction, 100, "test", 0.9, tp=120, sl=95)
    payload = client.post.await_args.kwargs["json"]
    assert (
        direction in payload["text"]
        and "120.0000" in payload["text"]
        and "95.0000" in payload["text"]
    )
    client.post.return_value = httpx.Response(500, text="failed")
    await broadcaster._send_text("test")
    client.post.side_effect = httpx.ConnectError("offline")
    await broadcaster._send_text("test")
    await broadcaster.close()
    client.aclose.assert_awaited_once()


async def test_alert_channels_use_mock_http_and_contain_failures(monkeypatch):
    for name in ("telegram_bot_token", "telegram_admin_id", "pagerduty_api_key"):
        monkeypatch.setattr(settings, name, "")
    await alerts.send_telegram_alert("test")
    await alerts.send_pagerduty_alert("test")
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.post.return_value = httpx.Response(200, request=httpx.Request("POST", "https://test"))
    monkeypatch.setattr(alerts.httpx, "AsyncClient", lambda **kw: client)
    for name in ("telegram_bot_token", "telegram_admin_id", "pagerduty_api_key"):
        monkeypatch.setattr(settings, name, "test-only")
    await alerts.send_kill_switch_alert("test", 0.25, "system")
    assert client.post.await_count == 2
    client.post.side_effect = httpx.ConnectError("offline")
    await alerts.send_kill_switch_alert("test", 0.25, "system")
    assert client.post.await_count == 4


def test_audit_report_persists_one_header_and_incident_details(tmp_path):
    reporter = AuditReporter(str(tmp_path))
    reporter.log_trade_execution({"symbol": "BTC/USDT", "price": "100.00000001"})
    reporter.log_trade_execution({"symbol": "ETH/USDT", "amount": 2})
    with next(tmp_path.glob("*.csv")).open() as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == 2 and rows[0]["price"] == "100.00000001"
    report = Path(reporter.generate_daily_compliance_report([], 2))
    assert "No risk limits breached" in report.read_text()
    reporter.generate_daily_compliance_report(
        [{"time": "12:00", "description": "test incident"}], 2
    )
    assert "test incident" in report.read_text()
