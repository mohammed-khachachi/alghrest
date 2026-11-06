"""Approved-message replay through router instances preserves execution intent."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.tier5_execution.order_router import OrderRouter
from core.config import settings
from core.data.models import Order, OrderType, TradeProposalStatus
from core.execution.contracts import AccountScope
from tests.factories import proposal

pytestmark = pytest.mark.unit


async def route_approval(value, authorizations=None):
    class Delivery:
        initialize = AsyncMock()

        async def stream(self):
            yield {"payload": value.model_dump(mode="json")}

    router = OrderRouter()
    result = None

    async def bind(proposal, order):
        nonlocal result
        result = await authorizations.bind(proposal, order) if authorizations else order
        return result

    router.authorizations = SimpleNamespace(bind=bind)
    router.make_consumer = MagicMock(return_value=Delivery())
    router.state = AsyncMock()
    router.state.is_kill_switch_active.return_value = False
    router.producer = AsyncMock()
    await router.run()
    assert result is not None
    return Order.model_validate(result)


async def test_approval_replay_after_router_restart_has_one_stable_intent(monkeypatch):
    approved = proposal(status=TradeProposalStatus.APPROVED)
    monkeypatch.setattr(
        settings,
        "execution_accounts",
        [AccountScope(exchange=approved.exchange, symbols=[approved.symbol])],
    )
    first = await route_approval(approved)
    restarted = await route_approval(approved)
    assert first.client_order_id == restarted.client_order_id
    assert first.order_id == restarted.order_id
    assert first.created_at == restarted.created_at
    assert first.proposal_id == approved.proposal_id


async def test_unreadable_authoritative_halt_blocks_risk():
    from core.orchestrator.state_manager import StateManager

    state = StateManager()
    state.halt_store = AsyncMock(side_effect=ConnectionError("database unavailable"))
    assert await state.is_kill_switch_active()


async def test_configured_twap_cadence_survives_approval_routing(monkeypatch):
    approved = proposal(status=TradeProposalStatus.APPROVED, order_type=OrderType.TWAP)
    monkeypatch.setattr(
        settings,
        "execution_accounts",
        [AccountScope(exchange=approved.exchange, symbols=[approved.symbol])],
    )
    monkeypatch.setattr(settings, "execution_twap_num_slices", 3)
    monkeypatch.setattr(settings, "execution_twap_interval_seconds", 1)
    routed = await route_approval(approved)
    assert routed.order_type == OrderType.TWAP
    assert routed.size == approved.size
    assert routed.algo_params["num_slices"] == 3
    assert routed.algo_params["slice_interval_seconds"] == 1
