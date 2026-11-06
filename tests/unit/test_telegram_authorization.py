"""Control commands must authenticate before touching shared risk state."""

from importlib import import_module
from unittest.mock import AsyncMock

import pytest

from core.config import settings
from core.telegram.bot_manager import TelegramBotManager

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def halt_control(monkeypatch):
    control = AsyncMock()
    monkeypatch.setattr(import_module("core.orchestrator.state_manager"), "state_manager", control)
    return control


@pytest.mark.parametrize("command", ["/ks off", "/killswitch@bot on", "/pause 14", "/restart 14"])
@pytest.mark.parametrize(
    "admin,sender,chat,chat_type",
    [
        ("42", 99, 99, "private"),
        ("42", 99, 42, "private"),
        ("42", 42, -100, "group"),
        ("42", 42, 42, "group"),
        ("42", None, 42, "private"),
        ("", 42, 42, "private"),
    ],
)
async def test_untrusted_control_command_cannot_change_state(
    monkeypatch, command, admin, sender, chat, chat_type, halt_control
):
    monkeypatch.setattr(settings, "telegram_admin_id", admin)
    bot = TelegramBotManager()
    bot.attach_redis(AsyncMock())
    bot._send = AsyncMock()
    bot._broadcast = AsyncMock()
    message = {"chat": {"id": chat, "type": chat_type}, "text": command}
    if sender is not None:
        message["from"] = {"id": sender}
    await bot._handle_update({"message": message})
    bot.redis.set.assert_not_awaited()
    bot.redis.delete.assert_not_awaited()
    bot.redis.sadd.assert_not_awaited()
    bot._broadcast.assert_not_awaited()
    assert not halt_control.mock_calls
    assert "authorized" in bot._send.await_args.args[1].lower()


@pytest.mark.parametrize("command", ["/ks off", "/killswitch@bot on", "/pause 14", "/restart 14"])
async def test_configured_admin_can_control_from_private_chat(monkeypatch, command, halt_control):
    monkeypatch.setattr(settings, "telegram_admin_id", "42")
    bot = TelegramBotManager()
    bot.attach_redis(AsyncMock())
    bot._send = AsyncMock()
    bot._broadcast = AsyncMock()
    await bot._handle_update(
        {"message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}, "text": command}}
    )
    if command == "/ks off":
        bot.redis.delete.assert_not_awaited()
        assert "Halt remains active" in bot._send.await_args.args[1]
        assert not halt_control.mock_calls
    elif command == "/killswitch@bot on":
        halt_control.activate_global_kill_switch.assert_awaited_once()
    else:
        bot.redis.set.assert_awaited()
