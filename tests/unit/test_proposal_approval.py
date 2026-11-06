"""Approval must preserve risk reductions and compare proposal instants in UTC."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from agents.tier1_executive import proposal_approver
from core.data.models import KafkaTopic, TradeProposal, TradeProposalReview
from tests.factories import portfolio, proposal

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 29, 3, tzinfo=UTC)


@pytest.fixture
def approver(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

        @classmethod
        def utcnow(cls):
            return NOW.replace(tzinfo=None)

    monkeypatch.setattr(proposal_approver, "datetime", Clock)
    agent = proposal_approver.ProposalApprover()
    agent.authorizations = AsyncMock()
    agent.authorizations.review.return_value = None
    agent.authorizations.decide.return_value = True
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = False
    agent.state.trading_ready.return_value = True
    agent.state.get_portfolio.return_value = portfolio()
    agent.publish = AsyncMock()
    return agent


@pytest.mark.parametrize("order_type,limit_price", [("MARKET", None), ("LIMIT", "100")])
async def test_concentration_reduction_scales_executable_quantity(
    approver, order_type, limit_price
):
    original = proposal(
        symbol="SOL/USDT",
        created_at=NOW,
        order_type=order_type,
        limit_price=limit_price,
        size="100",
        size_usd="10000",
    )
    await approver._process(original.model_dump(mode="json"))
    call = approver.publish.await_args
    assert call.args[0] == KafkaTopic.PROPOSALS_APPROVED
    approved = TradeProposal.model_validate(call.kwargs["payload"])
    assert approved.size_usd == Decimal("500")
    assert approved.adjusted_size_usd == Decimal("500")
    assert approved.size == Decimal("5")
    assert approved.size / original.size == approved.size_usd / original.size_usd
    assert original.size == Decimal("100")


@pytest.mark.parametrize("offset_hours", [0, 2, -5])
@pytest.mark.parametrize(
    "age,accepted", [(0, True), (59, True), (61, False), (-4, True), (-6, False)]
)
async def test_freshness_uses_instant_and_bounds_clock_skew(approver, offset_hours, age, accepted):
    created = (NOW - timedelta(seconds=age)).astimezone(timezone(timedelta(hours=offset_hours)))
    await approver._process(proposal(created_at=created).model_dump(mode="json"))
    topic = approver.publish.await_args.args[0]
    assert topic == (KafkaTopic.PROPOSALS_APPROVED if accepted else KafkaTopic.RISK_ALERTS)
    if not accepted:
        approver.state.get_portfolio.assert_not_awaited()


async def test_legacy_naive_proposal_time_is_utc(approver):
    await approver._process(proposal(created_at=NOW.replace(tzinfo=None)).model_dump(mode="json"))
    assert approver.publish.await_args.args[0] == KafkaTopic.PROPOSALS_APPROVED


async def test_transient_rejection_is_correlated_and_never_approved(approver):
    approver.state.trading_ready.return_value = False
    p = proposal(created_at=NOW)
    await approver._process(p.model_dump(mode="json"))
    call = approver.state.set_json.await_args
    assert call.args[0] == f"proposal_review:{p.proposal_id}"
    assert call.args[1]["decision"] == "REJECTED"
    assert call.args[1]["proposal_id"] == str(p.proposal_id)
    assert call.args[1]["reason"] == "portfolio exchange reconciliation is unavailable or disagrees"
    assert approver.publish.await_args.args[0] == KafkaTopic.RISK_ALERTS
    assert approver._approved_count == 0


async def test_redelivered_rejection_cannot_later_be_approved(approver):
    p = proposal(created_at=NOW)
    approver.state.trading_ready.return_value = False
    await approver._process(p.model_dump(mode="json"))
    approver.authorizations.review.return_value = TradeProposalReview.model_validate(
        approver.state.set_json.await_args.args[1]
    )
    approver.state.trading_ready.return_value = True
    approver.publish.reset_mock()
    await approver._process(p.model_dump(mode="json"))
    approver.publish.assert_not_awaited()
    assert approver._approved_count == 0


async def test_uncertain_approval_publication_is_not_repeated(approver):
    p = proposal(created_at=NOW)
    approver.publish.side_effect = TimeoutError("uncertain publication")
    with pytest.raises(TimeoutError):
        await approver._process(p.model_dump(mode="json"))
    approver.authorizations.review.return_value = TradeProposalReview.model_validate(
        approver.state.set_json.await_args.args[1]
    )
    assert approver.authorizations.review.return_value.decision == "APPROVED"
    await approver._process(p.model_dump(mode="json"))
    approver.publish.assert_awaited_once()
