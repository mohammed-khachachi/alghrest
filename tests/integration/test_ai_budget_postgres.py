"""Concurrent workers share a durable allowance; no Anthropic requests are made."""

import asyncio
import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from core.ai.budget import BudgetUnavailableError, estimate_cost, reserve
from core.config import settings

pytestmark = pytest.mark.integration


async def test_daily_budget_concurrent_restart_and_dollar_limits(monkeypatch):
    dsn = os.getenv("ACCOUNTING_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Requires isolated PostgreSQL test database")
    connection = await asyncpg.connect(dsn)
    scope = "test-budget-" + uuid4().hex
    try:
        await connection.execute(
            (Path(__file__).resolve().parents[2] / "infra/migrations/004_ai_budget.sql").read_text()
        )
        monkeypatch.setattr(settings, "database_url", dsn)
        monkeypatch.setattr(settings, "environment", scope)
        monkeypatch.setattr(settings, "ai_daily_max_calls", 3)
        monkeypatch.setattr(settings, "ai_daily_budget_usd", Decimal(10))
        results = await asyncio.gather(
            *(reserve("claude-opus-4-7", "s", "u", 512) for _ in range(12)), return_exceptions=True
        )
        assert results.count(None) == 3
        assert all(r is None or isinstance(r, BudgetUnavailableError) for r in results)
        # Every reserve creates a fresh connection: restarts have no in-memory reset.
        with pytest.raises(BudgetUnavailableError):
            await reserve("claude-opus-4-7", "s", "u", 512)
        row = await connection.fetchrow(
            "SELECT calls, reserved_usd FROM ai.daily_budget WHERE scope=$1", scope
        )
        cost = estimate_cost("claude-opus-4-7", "s", "u", 512)
        assert row["calls"] == 3 and row["reserved_usd"] == 3 * cost
        monkeypatch.setattr(settings, "ai_daily_max_calls", 100)
        monkeypatch.setattr(settings, "ai_daily_budget_usd", 3 * cost)
        with pytest.raises(BudgetUnavailableError):
            await reserve("claude-opus-4-7", "s", "u", 512)
    finally:
        await connection.execute("DELETE FROM ai.daily_budget WHERE scope=$1", scope)
        await connection.close()
