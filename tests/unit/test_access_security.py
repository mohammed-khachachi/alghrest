"""Authentication must reject before financial I/O, including alternate transports."""

from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.testclient import TestClient

from api.security import AccessTokenMiddleware
from core.config import settings
from core.telegram.bot_manager import TelegramBotManager

pytestmark = pytest.mark.unit
TOKEN = "a" * 48


@pytest.mark.parametrize("service", ["api", "advisory"])
async def test_http_auth_fail_closed_and_separate_keys(monkeypatch, service):
    from api.advisor import app as advisory
    from api.main import app as trading

    monkeypatch.setattr(settings, "api_access_token", SecretStr(TOKEN))
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("b" * 48))
    app = trading if service == "api" else advisory
    path = "/api/symbols" if service == "api" else "/assistant-api/catalog"
    key = TOKEN if service == "api" else "b" * 48
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        for headers, query in [
            ({}, ""),
            ({"Authorization": "Bearer bad"}, ""),
            ({}, "?token=" + key),
            ({"Authorization": "Basic " + key}, ""),
            ({"Authorization": "Bearer " + "c" * 48}, ""),
            ({"Authorization": "Bearer " + key, "Origin": "https://evil.example"}, ""),
        ]:
            assert (await client.get(path + query, headers=headers)).status_code == 401
        assert (
            await client.get(path, headers={"Authorization": "Bearer " + key})
        ).status_code == 200
        assert (await client.get("/health/live")).json() == {"status": "ok"}
        monkeypatch.setattr(settings, service + "_access_token", SecretStr(""))
        assert (
            await client.get(path, headers={"Authorization": "Bearer " + key})
        ).status_code == 503


async def test_duplicate_credentials_do_not_choose_a_favorable_parser(monkeypatch):
    from api.main import app

    monkeypatch.setattr(settings, "api_access_token", SecretStr(TOKEN))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        r = await client.get(
            "/api/symbols",
            headers=[("Authorization", "Bearer " + TOKEN), ("Authorization", "Bearer wrong")],
        )
        assert r.status_code == 401


@pytest.mark.parametrize("path", ["/ws/dashboard", "/ws/live", "/ws/prices"])
async def test_all_real_ws_routes_reject_before_acceptance_or_state_access(monkeypatch, path):
    from api.main import app

    monkeypatch.setattr(settings, "api_access_token", SecretStr(TOKEN))
    messages = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(value):
        messages.append(value)

    await app(
        {
            "type": "websocket",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"token=" + TOKEN.encode(),
            "headers": [],
            "scheme": "ws",
            "server": ("localhost", 80),
            "client": ("127.0.0.1", 1234),
            "subprotocols": [],
        },
        receive,
        send,
    )
    assert messages == [{"type": "websocket.close", "code": 1008}]


def test_browser_handshake_authorized_control(monkeypatch):
    monkeypatch.setattr(settings, "api_access_token", SecretStr(TOKEN))

    async def ws(socket):
        await socket.accept()
        await socket.send_json({"authorized": True})
        await socket.close()

    app = Starlette(routes=[WebSocketRoute("/ws", ws)])
    app.add_middleware(AccessTokenMiddleware, service="api")
    with (
        TestClient(app) as client,
        client.websocket_connect(
            "/ws",
            subprotocols=["alghrest.v1", "auth." + TOKEN],
            headers={"Origin": "http://localhost:5173"},
        ) as socket,
    ):
        assert socket.accepted_subprotocol == "alghrest.v1"
        assert socket.receive_json() == {"authorized": True}


@pytest.mark.parametrize(
    "command", ["/start", "/pnl", "/risk", "/alerts", "/agent@bot 14", "/help"]
)
async def test_private_reads_and_subscriptions_reject_non_admin(monkeypatch, command):
    monkeypatch.setattr(settings, "telegram_admin_id", "42")
    bot = TelegramBotManager()
    bot.attach_redis(AsyncMock())
    bot._send = AsyncMock()
    await bot._handle_update(
        {"message": {"chat": {"id": 99, "type": "private"}, "from": {"id": 99}, "text": command}}
    )
    bot.redis.sadd.assert_not_awaited()
    bot.redis.get.assert_not_awaited()
    bot.redis.set.assert_not_awaited()
    assert "authorized" in bot._send.await_args.args[1]


async def test_legacy_subscribers_cannot_receive_private_broadcasts(monkeypatch):
    monkeypatch.setattr(settings, "telegram_admin_id", "42")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    bot = TelegramBotManager()
    bot.attach_redis(AsyncMock())
    bot.redis.smembers.return_value = {b"99", b"42"}
    bot._send = AsyncMock()
    await bot._broadcast("private portfolio")
    bot._send.assert_awaited_once_with("42", "private portfolio")
    monkeypatch.setattr(settings, "telegram_admin_id", "")
    bot._send.reset_mock()
    await bot._broadcast("private portfolio")
    bot._send.assert_not_awaited()


@pytest.mark.parametrize("method", ["POST", "PUT"])
async def test_advisory_write_intent_header_cannot_replace_authentication(monkeypatch, method):
    from api.advisor import app

    monkeypatch.setattr(settings, "advisory_access_token", SecretStr(TOKEN))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost"
    ) as client:
        response = await client.request(
            method,
            "/assistant-api/watchlist",
            headers={"X-Advisory-Client": "dashboard"},
            content=b"untrusted import body",
        )
        assert response.status_code == 401
