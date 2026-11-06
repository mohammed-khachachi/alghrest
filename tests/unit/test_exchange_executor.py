"""Submission boundary tests; transactions are tested against PostgreSQL."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest

from agents.tier5_execution.exchange_executor import _SUPPORTED_EXCHANGES, ExchangeExecutor
from core.data.models import Exchange, Order, OrderSide, OrderStatus, OrderType
from core.execution.contracts import RecoveryBlockedError
from core.resilience import DatabaseCircuitOpenError

pytestmark = pytest.mark.unit


def order(**changes):
    return Order(
        **(
            dict(
                symbol="BTC/USD",
                exchange=Exchange.BINANCE,
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=Decimal(1),
                strategy_id="test",
                agent_id=12,
            )
            | changes
        )
    )


def executor():
    ex = ExchangeExecutor()
    ex.store = SimpleNamespace(
        book_id="test",
        check_writer=AsyncMock(),
        ensure_writer=AsyncMock(),
        authorize=AsyncMock(),
        deny=AsyncMock(),
        seen=AsyncMock(return_value=False),
        prepare=AsyncMock(return_value=True),
        abort_prepared=AsyncMock(),
        abort_if_unattempted=AsyncMock(return_value=True),
        reject=AsyncMock(),
        observe=AsyncMock(),
        uncertain=AsyncMock(),
        block=AsyncMock(),
    )
    ex.state = SimpleNamespace(
        is_kill_switch_active=AsyncMock(return_value=False),
        trading_ready=AsyncMock(return_value=True),
        set_reconciliation=AsyncMock(),
    )
    venue = SimpleNamespace(
        place=AsyncMock(return_value=order(exchange_order_id="venue", status=OrderStatus.OPEN))
    )
    ex.venues = {'["binance","default"]': venue}
    return ex, venue


def test_supported_spot_venues_and_identity():
    assert set(_SUPPORTED_EXCHANGES) == {
        Exchange.BINANCE,
        Exchange.BYBIT,
        Exchange.COINBASE,
        Exchange.KRAKEN,
    }
    assert ExchangeExecutor.AGENT_ID == 26


@pytest.mark.parametrize(
    "changes",
    [
        {"exchange": Exchange.ALPACA},
        {"order_type": OrderType.LIMIT},
        {"size": Decimal(0)},
        {"created_at": datetime.utcnow() - timedelta(minutes=3)},
        {"order_type": OrderType.STOP},
    ],
)
async def test_invalid_order_durably_rejected_without_contacting_venue(changes):
    ex, venue = executor()
    assert not await ex._place_order(order(**changes))
    ex.store.reject.assert_awaited_once()
    ex.store.prepare.assert_not_awaited()
    venue.place.assert_not_awaited()


@pytest.mark.parametrize("halted,verified", [(True, True), (False, False)])
async def test_missing_risk_evidence_blocks_submission(halted, verified):
    ex, venue = executor()
    ex.state.is_kill_switch_active.return_value = halted
    ex.state.trading_ready.return_value = verified
    assert not await ex._place_order(order())
    venue.place.assert_not_awaited()


async def test_intent_commits_before_http_and_response_failure_never_resubmits():
    ex, venue = executor()
    intent = order()

    async def place(_):
        ex.store.prepare.assert_awaited_once_with(intent)
        raise TimeoutError("accepted but response lost")

    venue.place.side_effect = place
    assert await ex._place_order(intent)
    ex.store.uncertain.assert_awaited_once_with(intent, "TimeoutError")
    ex.store.reject.assert_not_awaited()
    ex.store.seen.return_value = True
    assert not await ex._place_order(intent)
    venue.place.assert_awaited_once()


async def test_durable_gate_closes_between_cache_check_and_claim():
    ex, venue = executor()
    ex.store.prepare.side_effect = RecoveryBlockedError("changed ledger")
    assert not await ex._place_order(order())
    venue.place.assert_not_awaited()
    ex.store.reject.assert_awaited_once()


async def test_observation_failure_keeps_claim_uncertain_not_rejected():
    ex, venue = executor()
    ex.store.observe.side_effect = ConnectionError()
    assert await ex._place_order(order())
    venue.place.assert_awaited_once()
    ex.store.uncertain.assert_awaited_once()
    ex.store.reject.assert_not_awaited()


async def test_unclaimed_duplicate_does_not_call_venue():
    ex, venue = executor()
    ex.store.prepare.return_value = False
    assert not await ex._place_order(order())
    venue.place.assert_not_awaited()


async def test_history_polling_continues_during_halt(monkeypatch):
    ex, _ = executor()
    ex.state.is_kill_switch_active.return_value = True
    ex.recovery = SimpleNamespace(
        run_once=AsyncMock(return_value={"ready": False, "reasons": ["unsettled"]})
    )
    monkeypatch.setattr(asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await ex._fill_polling_loop()
    ex.recovery.run_once.assert_awaited_once()


async def test_algo_parents_are_not_submitted():
    ex, venue = executor()
    await ex.handle_order({"payload": order(order_type=OrderType.TWAP).model_dump(mode="json")})
    venue.place.assert_not_awaited()


async def test_disconnect_during_prepare_aborts_unattempted_and_never_calls_venue():
    ex, venue = executor()
    intent = order()
    ex.store.prepare.side_effect = asyncpg.ConnectionDoesNotExistError("db dropped at commit")
    # Simulate DB still unreachable during immediate abort attempt, so it queues in _unattempted_claims
    ex.store.abort_if_unattempted.side_effect = [
        asyncpg.ConnectionDoesNotExistError("still down"),
        True,
    ]

    assert not await ex._place_order(intent)
    venue.place.assert_not_awaited()
    ex.store.uncertain.assert_not_awaited()
    assert intent.client_order_id in ex._unattempted_claims

    # Once DB recovers, _flush_pending_journal cleans up the unattempted claim
    await ex._flush_pending_journal()
    assert intent.client_order_id not in ex._unattempted_claims
    assert ex.store.abort_if_unattempted.await_count == 2


async def test_disconnect_after_prepare_before_venue_place_aborts_unattempted():
    ex, venue = executor()
    intent = order()
    # First ensure_writer (before prepare) succeeds; second (after prepare, before venue.place) trips
    ex.store.ensure_writer.side_effect = [
        None,
        DatabaseCircuitOpenError("circuit open before venue contact"),
        None,
    ]

    assert not await ex._place_order(intent)
    venue.place.assert_not_awaited()
    ex.store.uncertain.assert_not_awaited()
    ex.store.abort_if_unattempted.assert_awaited_once()


async def test_disconnect_during_observe_flushes_on_recovery_without_duplicate_venue_place():
    ex, venue = executor()
    intent = order()
    placed_order = order(
        client_order_id=intent.client_order_id,
        exchange_order_id="venue-123",
        status=OrderStatus.OPEN,
    )
    venue.place.return_value = placed_order
    # Both initial observe and immediate retry fail due to DB drop; third call (during flush) succeeds
    ex.store.observe.side_effect = [
        asyncpg.ConnectionDoesNotExistError("dropped during observe"),
        asyncpg.ConnectionDoesNotExistError("still down on immediate retry"),
        None,
    ]

    assert await ex._place_order(intent)
    venue.place.assert_awaited_once()
    assert intent.client_order_id in ex._pending_observations

    await ex._flush_pending_journal()
    assert intent.client_order_id not in ex._pending_observations
    assert ex.store.observe.await_count == 3
    venue.place.assert_awaited_once()
