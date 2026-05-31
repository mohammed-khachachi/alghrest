from __future__ import annotations

import os
from unittest.mock import AsyncMock

_ENV_KEYS = ("ENVIRONMENT", "API_AUTH_ENABLED", "ALGHREST_API_KEY", "API_ALLOWED_ORIGINS")
_ORIGINAL_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}
os.environ.update(
    {
        "ENVIRONMENT": "development",
        "API_AUTH_ENABLED": "true",
        "ALGHREST_API_KEY": "test-api-key",
        "API_ALLOWED_ORIGINS": "http://localhost:5173,http://localhost:8000",
    }
)

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api import main as api_main
from api.auth import API_KEY_HEADER
from core.config import Settings

for key, value in _ORIGINAL_ENV.items():
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value

API_KEY = "test-api-key"


def _client(monkeypatch: pytest.MonkeyPatch, *, auth_enabled: bool = True) -> TestClient:
    monkeypatch.setattr(api_main.settings, "environment", "development")
    monkeypatch.setattr(api_main.settings, "api_auth_enabled", auth_enabled)
    monkeypatch.setattr(api_main.settings, "alghrest_api_key", API_KEY)
    monkeypatch.setattr(api_main.state_manager, "get_portfolio", AsyncMock(return_value=None))
    return TestClient(api_main.app)


def test_unauthenticated_request_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/api/v1/portfolio")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_authenticated_request_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/api/v1/portfolio", headers={API_KEY_HEADER: API_KEY})

    assert response.status_code == 200
    assert response.json()["message"].startswith("Portfolio data not yet available")


def test_invalid_api_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch)

    response = client.get("/api/v1/portfolio", headers={API_KEY_HEADER: "wrong-key"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


def test_development_bypass_works_only_when_explicitly_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch, auth_enabled=False)

    response = client.get("/api/v1/portfolio")

    assert response.status_code == 200


@pytest.mark.parametrize("environment", ["paper_trading", "live"])
def test_non_development_cannot_disable_auth(environment: str) -> None:
    with pytest.raises(ValidationError, match="API_AUTH_ENABLED"):
        Settings(
            _env_file=None,
            environment=environment,
            api_auth_enabled=False,
            alghrest_api_key=API_KEY,
        )


@pytest.mark.parametrize("environment", ["paper_trading", "live"])
def test_non_development_rejects_wildcard_origins(environment: str) -> None:
    with pytest.raises(ValidationError, match="API_ALLOWED_ORIGINS"):
        Settings(
            _env_file=None,
            environment=environment,
            api_auth_enabled=True,
            alghrest_api_key=API_KEY,
            api_allowed_origins="*",
        )
