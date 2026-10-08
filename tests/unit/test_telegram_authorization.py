"""Control commands must authenticate before touching shared risk state."""

from unittest.mock import AsyncMock

import pytest

from core.config import settings
from core.telegram.bot_manager import TelegramBotManager

pytestmark = pytest.mark.unit


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
    monkeypatch, command, admin, sender, chat, chat_type
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
    assert "authorized" in bot._send.await_args.args[1].lower()


@pytest.mark.parametrize("command", ["/ks off", "/killswitch@bot on", "/pause 14", "/restart 14"])
async def test_configured_admin_can_control_from_private_chat(monkeypatch, command):
    monkeypatch.setattr(settings, "telegram_admin_id", "42")
    bot = TelegramBotManager()
    bot.attach_redis(AsyncMock())
    bot._send = AsyncMock()
    bot._broadcast = AsyncMock()
    await bot._handle_update(
        {"message": {"chat": {"id": 42, "type": "private"}, "from": {"id": 42}, "text": command}}
    )
    if command == "/ks off":
        bot.redis.delete.assert_any_await("alghrest:kill_switch:active")
    else:
        bot.redis.set.assert_awaited()
