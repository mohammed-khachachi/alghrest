"""Provisioning must target the isolated paper stack; failed evidence blocks readiness."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.config import settings
from scripts import paper_runtime, test_with_services

pytestmark = pytest.mark.unit


def local(monkeypatch):
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(
        settings, "database_url", "postgresql://test:test@127.0.0.1:15432/alghrest_paper"
    )
    monkeypatch.setattr(settings, "redis_url", "redis://127.0.0.1:16379")
    monkeypatch.setattr(settings, "kafka_bootstrap_servers", "127.0.0.1:19092")


@pytest.mark.parametrize(
    "field,value",
    [
        ("environment", "live"),
        ("database_url", "postgresql://test:test@127.0.0.1:5432/production"),
        ("redis_url", "redis://127.0.0.1:6379"),
        ("kafka_bootstrap_servers", "127.0.0.1:9092"),
    ],
)
async def test_provision_refuses_unrelated_environment_before_connecting(monkeypatch, field, value):
    local(monkeypatch)
    monkeypatch.setattr(settings, field, value)
    connect = AsyncMock()
    monkeypatch.setattr(paper_runtime.Ledger, "connect", connect)
    with pytest.raises(ValueError, match="dedicated local paper"):
        await paper_runtime.provision()
    connect.assert_not_awaited()


async def test_quality_runner_refuses_live_environment_before_connecting(monkeypatch):
    local(monkeypatch)
    monkeypatch.setattr(settings, "environment", "live")
    connect = AsyncMock()
    monkeypatch.setattr(test_with_services.asyncpg, "connect", connect)
    with pytest.raises(ValueError, match="dedicated local paper"):
        await test_with_services.test_environment()
    connect.assert_not_awaited()


@pytest.mark.parametrize("exists", [True, False])
async def test_quality_runner_isolates_storage_and_closes_connection(monkeypatch, exists):
    local(monkeypatch)
    admin = AsyncMock()
    admin.fetchval.return_value = exists
    monkeypatch.setattr(test_with_services.asyncpg, "connect", AsyncMock(return_value=admin))
    environment = await test_with_services.test_environment()
    assert environment["ACCOUNTING_TEST_DATABASE_URL"].endswith("/alghrest_quality")
    assert environment["ACCOUNTING_TEST_REDIS_URL"].endswith(":16379/14")
    assert environment["PAPER_RUNTIME_TESTS"] == "1"
    assert settings.database_url.endswith("/alghrest_paper")
    if exists:
        admin.execute.assert_not_awaited()
    else:
        admin.execute.assert_awaited_once_with("CREATE DATABASE alghrest_quality")
    admin.close.assert_awaited_once()


async def test_preflight_collects_failure_types_without_leaking_connection_secrets(monkeypatch):
    local(monkeypatch)
    monkeypatch.setattr(
        paper_runtime.Ledger, "connect", AsyncMock(side_effect=RuntimeError("secret password"))
    )
    state = SimpleNamespace(
        initialize=AsyncMock(side_effect=ValueError("private URL")), shutdown=AsyncMock()
    )
    admin = SimpleNamespace(
        start=AsyncMock(side_effect=TimeoutError("private URL")), close=AsyncMock()
    )
    monkeypatch.setattr(paper_runtime, "StateManager", lambda: state)
    monkeypatch.setattr(paper_runtime, "AIOKafkaAdminClient", lambda **kwargs: admin)
    result = await paper_runtime.preflight()
    assert not result["ready"]
    assert result["errors"] == {
        "database": "RuntimeError",
        "redis": "ValueError",
        "kafka": "TimeoutError",
    }
    assert "secret" not in str(result) and "private" not in str(result)
    state.shutdown.assert_awaited_once()
    admin.close.assert_awaited_once()
