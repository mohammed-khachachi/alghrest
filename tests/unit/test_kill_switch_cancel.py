"""Kill events use durable cancellation/recovery rather than a RAM order map."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.tier5_execution.exchange_executor import ExchangeExecutor

pytestmark = pytest.mark.unit


async def test_kill_events_fence_risk_then_recover_durable_orders():
    ex = ExchangeExecutor()
    ex.store = SimpleNamespace(book_id="test", check_writer=AsyncMock(), block=AsyncMock())
    ex.state = SimpleNamespace(set_reconciliation=AsyncMock())

    async def recover(*, halted):
        assert halted
        ex.store.block.assert_awaited_with("kill switch")
        ex.state.set_reconciliation.assert_awaited_with({"book_id": "test", "ready": False})

    ex.recovery = SimpleNamespace(recover_orders=AsyncMock(side_effect=recover))

    async def process(handle):
        await handle({"message_type": "RiskAlert"})
        ex.recovery.recover_orders.assert_not_awaited()
        await handle({"message_type": "KillSwitchEvent"})
        await handle({"message_type": "HaltAllStrategies"})

    consumer = SimpleNamespace(initialize=AsyncMock(), process=AsyncMock(side_effect=process))
    ex.make_consumer = MagicMock(return_value=consumer)
    await ex._kill_switch_listener_loop()
    assert ex.recovery.recover_orders.await_count == 2
