"""Unit tests for the Timescale persistence repository transaction boundary."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from core.data.models import Exchange, Fill, KafkaTopic, OrderSide
from core.persistence.repository import TimescalePersistenceRepository


class _FakeSession:
    def __init__(self) -> None:
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self.raise_on_execute = False

    async def execute(self, statement, params):
        if self.raise_on_execute:
            raise RuntimeError("database unavailable")
        self.executed.append((statement, params))

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


class _FakeSessionManager:
    def __init__(self, session: _FakeSession) -> None:
        self.session_obj = session
        self.disposed = False

    @asynccontextmanager
    async def session(self):
        yield self.session_obj

    async def dispose(self):
        self.disposed = True


def _fill_message() -> dict:
    fill = Fill(
        order_id=uuid4(),
        exchange_order_id="EX-1",
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        fill_size=Decimal("0.01"),
        fill_price=Decimal("45100"),
        fee=Decimal("0.5"),
    )
    return {
        "topic": KafkaTopic.FILLS_CONFIRMED.value,
        "message_type": "Fill",
        "source_agent_id": 26,
        "payload": fill.model_dump(mode="json"),
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_executes_and_commits_mapped_statement():
    session = _FakeSession()
    manager = _FakeSessionManager(session)
    repo = TimescalePersistenceRepository(session_manager=manager)

    count = await repo.persist_kafka_message(_fill_message())

    assert count == 1
    assert len(session.executed) == 1
    assert session.executed[0][1]["symbol"] == "BTC/USDT"
    assert session.committed is True
    assert session.rolled_back is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_rolls_back_execute_failure():
    session = _FakeSession()
    session.raise_on_execute = True
    repo = TimescalePersistenceRepository(session_manager=_FakeSessionManager(session))

    with pytest.raises(RuntimeError, match="database unavailable"):
        await repo.persist_kafka_message(_fill_message())

    assert session.committed is False
    assert session.rolled_back is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_repository_close_disposes_session_manager():
    session = _FakeSession()
    manager = _FakeSessionManager(session)
    repo = TimescalePersistenceRepository(session_manager=manager)

    await repo.close()

    assert manager.disposed is True
