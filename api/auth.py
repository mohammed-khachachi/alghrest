"""API-key authentication helpers for REST and WebSocket routes."""
from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Header, HTTPException, WebSocket, status

from core.config import settings

API_KEY_HEADER = "X-API-Key"
API_KEY_QUERY_PARAM = "api_key"


def is_api_auth_required() -> bool:
    """Return whether API auth is required for the active environment."""
    if settings.environment in {"paper_trading", "live"}:
        return True
    return settings.api_auth_enabled


def _api_key_matches(provided_key: str | None) -> bool:
    if not provided_key or not settings.alghrest_api_key:
        return False
    return secrets.compare_digest(
        provided_key.encode("utf-8"),
        settings.alghrest_api_key.encode("utf-8"),
    )


async def require_api_key(
    x_api_key: Annotated[str | None, Header(alias=API_KEY_HEADER)] = None,
) -> None:
    """FastAPI dependency for sensitive REST endpoints."""
    if not is_api_auth_required():
        return

    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    if not _api_key_matches(x_api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")


async def require_websocket_api_key(websocket: WebSocket) -> bool:
    """Validate a WebSocket API key before accepting the connection."""
    if not is_api_auth_required():
        return True

    api_key = websocket.headers.get(API_KEY_HEADER) or websocket.query_params.get(API_KEY_QUERY_PARAM)
    if not api_key:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing API key")
        return False

    if not _api_key_matches(api_key):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid API key")
        return False

    return True
