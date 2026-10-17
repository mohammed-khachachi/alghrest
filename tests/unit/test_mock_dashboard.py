"""The demo feed must not masquerade as a connected paper account."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from api.mock_server import MockDashboardManager

pytestmark = pytest.mark.unit


@pytest.fixture
async def demo_messages():
    manager = MockDashboardManager()
    ws = AsyncMock()
    await manager.connect(ws)
    received = {}
    completed = asyncio.Event()

    async def receive(message):
        received[message["channel"]] = message["data"]
        if message["channel"] == "risk.limits":
            completed.set()

    ws.send_json.side_effect = receive
    task = asyncio.create_task(manager.run_loops())
    try:
        await asyncio.wait_for(completed.wait(), timeout=3)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        manager.disconnect(ws)
    return received


async def test_demo_feed_identifies_itself_in_system_status(demo_messages):
    status = demo_messages["system.status"]
    assert status["status"] == "DEMO"
    assert status["environment"] == "demo"


async def test_empty_demo_positions_have_no_exposure_or_phantom_positions(demo_messages):
    positions = demo_messages["positions.updates"]
    assert positions["open_positions"] == positions["closed_trades"] == []
    assert positions["long_exposure"] == positions["short_exposure"] == positions["net_delta"] == 0
    portfolio = demo_messages["portfolio.snapshot"]
    assert portfolio["open_positions"] == len(positions["open_positions"])
    assert portfolio["unrealized_pnl"] == portfolio["leverage"] == 0
