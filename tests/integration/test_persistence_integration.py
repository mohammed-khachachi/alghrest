"""Integration test — Agent 38 PersistenceWriter against a real TimescaleDB.

Roadmap item 2: prove that real ``AgentMessage`` persistence events land in the
TimescaleDB schema provisioned by ``infra/init/timescale-init.sql``. Unlike the
unit tests (which use a fake session), this exercises the full path:

    AgentMessage.model_dump() → build_persistence_statements →
    TimescalePersistenceRepository.persist_kafka_message → real INSERT →
    SELECT the row back

It covers one **trading** event (TradeProposal), one **market** event (OHLCV),
and one **risk** event (kill switch), so column lists and every ``ON CONFLICT``
target are validated against the live DDL.

────────────────────────────────────────────────────────────────────────────
How to run it
────────────────────────────────────────────────────────────────────────────
The test is marked ``integration`` and needs a running TimescaleDB. The schema
is auto-applied by the container's init script. From the repo root:

    docker compose up -d timescaledb
    # wait until healthy:  docker compose ps timescaledb
    poetry run python -m pytest tests/integration/test_persistence_integration.py -m integration -v

Use ``python -m pytest`` (not the bare ``pytest`` console script) so the repo
root is on ``sys.path`` and ``core`` / ``agents`` import — this matches how
``scripts/run_tests.py`` and CI invoke pytest.

Connection: by default the test reads ``settings.database_url``. In this repo's
``.env`` that URL uses the docker-network hostname ``postgres`` (e.g.
``postgresql+asyncpg://alghrest:...@postgres:5432/alghrest``), which only
resolves *inside* the compose network. When running the test from the **host**
machine, point it at the published port instead via ``ALGHREST_TEST_DATABASE_URL``:

    # PowerShell
    $env:ALGHREST_TEST_DATABASE_URL = "postgresql+asyncpg://alghrest:alghrest_secure_pass_2024@localhost:5432/alghrest"
    poetry run python -m pytest tests/integration/test_persistence_integration.py -m integration -v

If no database is reachable the test **skips** (it never fails on a missing DB)
and prints the exact blocker, including the host:port it tried.
"""

from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from core.config import settings
from core.data.models import (
    AgentMessage,
    AssetClass,
    Exchange,
    KafkaTopic,
    OHLCVBar,
    OrderSide,
    OrderType,
    Timeframe,
    TradeProposal,
    TradeProposalStatus,
)
from core.persistence.database import TimescaleSessionManager
from core.persistence.repository import TimescalePersistenceRepository

pytestmark = pytest.mark.integration


def _test_database_url() -> str:
    return os.getenv("ALGHREST_TEST_DATABASE_URL", settings.database_url)


async def _require_timescale() -> TimescaleSessionManager:
    """Return a session manager bound to the test DB, or skip if unreachable."""
    try:
        from sqlalchemy import text
    except ImportError as exc:  # pragma: no cover - sqlalchemy is a main dep
        pytest.skip(f"sqlalchemy not installed: {exc}")

    manager = TimescaleSessionManager(database_url=_test_database_url())
    try:
        async with manager.session() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:  # connection refused, auth, missing DB, etc.
        await manager.dispose()
        pytest.skip(
            "TimescaleDB not reachable at "
            f"{_test_database_url().rsplit('@', 1)[-1]} ({type(exc).__name__}). "
            "Start it with: docker compose up -d timescaledb"
        )
    return manager


async def _fetch_one(manager: TimescaleSessionManager, sql: str, params: dict):
    from sqlalchemy import text

    async with manager.session() as session:
        result = await session.execute(text(sql), params)
        return result.mappings().first()


async def _execute(manager: TimescaleSessionManager, sql: str, params: dict) -> None:
    from sqlalchemy import text

    async with manager.session() as session:
        await session.execute(text(sql), params)
        await session.commit()


@pytest.mark.asyncio
async def test_trade_proposal_persists_to_trading_schema():
    """Trading event: PROPOSALS_APPROVED → trading.trade_proposals."""
    manager = await _require_timescale()
    repo = TimescalePersistenceRepository(session_manager=manager)
    proposal = TradeProposal(
        strategy_id="integration_test",
        agent_id=12,
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        asset_class=AssetClass.CRYPTO,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.10"),
        size_usd=Decimal("4500"),
        confidence_score=0.71,
        status=TradeProposalStatus.PENDING,
        rationale="persistence integration test",
    )
    envelope = AgentMessage(
        source_agent_id=12,
        topic=KafkaTopic.PROPOSALS_APPROVED,
        message_type="TradeProposalApproved",
        payload=proposal.model_dump(mode="json"),
    ).model_dump(mode="json")

    try:
        written = await repo.persist_kafka_message(envelope)
        assert written == 1

        row = await _fetch_one(
            manager,
            "SELECT proposal_id, status, strategy_id, size_usd "
            "FROM trading.trade_proposals WHERE proposal_id = :pid",
            {"pid": str(proposal.proposal_id)},
        )
        assert row is not None, "trade proposal row was not inserted"
        # PROPOSALS_APPROVED forces the persisted status to APPROVED.
        assert row["status"] == TradeProposalStatus.APPROVED.value
        assert row["strategy_id"] == "integration_test"
        assert Decimal(row["size_usd"]) == Decimal("4500")
    finally:
        await _execute(
            manager,
            "DELETE FROM trading.trade_proposals WHERE proposal_id = :pid",
            {"pid": str(proposal.proposal_id)},
        )
        await manager.dispose()


@pytest.mark.asyncio
async def test_ohlcv_bar_persists_to_market_data_schema():
    """Market event: PRICES_REALTIME (ohlcv) → market_data.ohlcv_bars."""
    manager = await _require_timescale()
    repo = TimescalePersistenceRepository(session_manager=manager)
    # Unique symbol so the row is unambiguous and easy to clean up.
    symbol = f"ITEST{uuid4().hex[:8].upper()}/USDT"
    bar_time = datetime.utcnow().replace(microsecond=0)
    bar = OHLCVBar(
        time=bar_time,
        symbol=symbol,
        exchange=Exchange.BINANCE,
        timeframe=Timeframe.M1,
        open=Decimal("100.5"),
        high=Decimal("101.0"),
        low=Decimal("100.0"),
        close=Decimal("100.8"),
        volume=Decimal("12.5"),
    )
    envelope = AgentMessage(
        source_agent_id=9,
        topic=KafkaTopic.PRICES_REALTIME,
        message_type="ohlcv",
        payload=bar.model_dump(mode="json"),
    ).model_dump(mode="json")

    try:
        written = await repo.persist_kafka_message(envelope)
        assert written == 1

        row = await _fetch_one(
            manager,
            "SELECT symbol, close, volume FROM market_data.ohlcv_bars " "WHERE symbol = :symbol",
            {"symbol": symbol},
        )
        assert row is not None, "ohlcv row was not inserted"
        assert row["symbol"] == symbol
        assert Decimal(row["close"]) == Decimal("100.8")
    finally:
        await _execute(
            manager,
            "DELETE FROM market_data.ohlcv_bars WHERE symbol = :symbol",
            {"symbol": symbol},
        )
        await manager.dispose()


@pytest.mark.asyncio
async def test_kill_switch_event_persists_to_risk_schema():
    """Risk event: RISK_ALERTS (KillSwitchEvent) → risk.kill_switch_events."""
    manager = await _require_timescale()
    repo = TimescalePersistenceRepository(session_manager=manager)
    event_id = str(uuid4())
    payload = {
        "event_id": event_id,
        "reason": "integration drawdown halt",
        "source_agent_id": 2,
        "drawdown_pct": "0.27",
        "scope": "system",
        "positions_closed": 3,
    }
    envelope = AgentMessage(
        source_agent_id=2,
        topic=KafkaTopic.RISK_ALERTS,
        message_type="KillSwitchEvent",
        payload=payload,
    ).model_dump(mode="json")

    try:
        written = await repo.persist_kafka_message(envelope)
        assert written == 1

        row = await _fetch_one(
            manager,
            "SELECT event_id, trigger_reason, drawdown_pct, scope "
            "FROM risk.kill_switch_events WHERE event_id = :eid",
            {"eid": event_id},
        )
        assert row is not None, "kill switch row was not inserted"
        assert row["trigger_reason"] == "integration drawdown halt"
        assert Decimal(row["drawdown_pct"]) == Decimal("0.27")
        assert row["scope"] == "system"
    finally:
        await _execute(
            manager,
            "DELETE FROM risk.kill_switch_events WHERE event_id = :eid",
            {"eid": event_id},
        )
        await manager.dispose()
