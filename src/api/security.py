"""Fail-closed authentication before HTTP handlers or WebSocket acceptance.

Single-operator bearer tokens stay out of URLs and browser persistent storage.
Browsers carry WebSocket credentials in the handshake's subprotocol header;
the server does not echo the credential as its selected protocol.
"""

import re
import secrets
from typing import Literal

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from core.config import settings

_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")


class AccessTokenMiddleware:
    def __init__(self, app: ASGIApp, service: Literal["api", "advisory"]) -> None:
        self.app, self.service = app, service

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        kind = scope["type"]
        if kind not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        if kind == "http" and (
            scope.get("method") == "OPTIONS"
            or (scope.get("path") == "/health/live" and scope.get("method") in {"GET", "HEAD"})
        ):
            await self.app(scope, receive, send)
            return
        expected = getattr(settings, f"{self.service}_access_token").get_secret_value()
        headers = Headers(scope=scope)
        credentials = []
        for value in headers.getlist("authorization"):
            parts = value.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                credentials.append(parts[1])
            else:
                credentials.append("")
        if kind == "websocket":
            for value in headers.getlist("sec-websocket-protocol"):
                credentials.extend(
                    p.strip()[5:] for p in value.split(",") if p.strip().startswith("auth.")
                )
        origins = headers.getlist("origin")
        allowed = getattr(settings, f"{self.service}_allowed_origins")
        origin_ok = not origins or (len(origins) == 1 and origins[0] in allowed)
        configured = bool(_TOKEN.fullmatch(expected))
        authorized = (
            configured
            and origin_ok
            and len(credentials) == 1
            and bool(_TOKEN.fullmatch(credentials[0]))
            and secrets.compare_digest(expected, credentials[0])
        )
        if not authorized:
            if kind == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                status = 503 if not configured else 401
                await JSONResponse(
                    {
                        "detail": (
                            "Access is not configured"
                            if status == 503
                            else "Authentication required"
                        )
                    },
                    status_code=status,
                    headers={"WWW-Authenticate": "Bearer", "Cache-Control": "no-store"},
                )(scope, receive, send)
            return
        if kind == "websocket" and "alghrest.v1" in scope.get("subprotocols", []):

            async def accept_public_protocol(message: Message) -> None:
                if message["type"] == "websocket.accept":
                    message = {**message, "subprotocol": "alghrest.v1"}
                await send(message)

            await self.app(scope, receive, accept_public_protocol)
        else:
            await self.app(scope, receive, send)
