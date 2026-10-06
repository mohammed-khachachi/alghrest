"""Only proven pre-execution temporary rejections may be retried by the soak."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from scripts import deployment_workload as workload
from tests.factories import proposal

pytestmark = pytest.mark.unit


@pytest.fixture
def worker():
    w = workload.Workload(1, "test")
    w.state = AsyncMock()
    w.ledger = SimpleNamespace(
        book_id="test-book",
        load=AsyncMock(return_value=SimpleNamespace(revision=8)),
        pool=SimpleNamespace(fetchval=AsyncMock(return_value=0)),
    )
    w.save = Mock()
    w.info["active_proposal_id"] = "test-proposal"
    return w


@pytest.mark.parametrize(
    "reason,orders,exception",
    [
        (
            "portfolio exchange reconciliation is unavailable or disagrees",
            0,
            workload.TransientProposalRejectionError,
        ),
        ("no portfolio snapshot available", 0, workload.TransientProposalRejectionError),
        ("system kill switch active", 0, RuntimeError),
        ("Insufficient capital", 0, RuntimeError),
        ("portfolio exchange reconciliation is unavailable or disagrees", 1, RuntimeError),
    ],
)
async def test_classifies_rejection_only_after_checking_execution_records(
    worker, reason, orders, exception
):
    p = proposal()
    worker.state.get_json.return_value = {
        "proposal_id": str(p.proposal_id),
        "reviewer_agent_id": 3,
        "decision": "REJECTED",
        "reason": reason,
        "risk_score": 1.0,
    }
    worker.ledger.pool.fetchval.return_value = orders
    with pytest.raises(exception) as error:
        await worker.wait_for_fill(p, 8)
    assert type(error.value) is exception
    assert worker.ledger.pool.fetchval.await_args.args[-1] == str(p.proposal_id)


async def test_timeout_identifies_proposal_and_is_not_retried(worker):
    p = proposal()
    worker.state.get_json.side_effect = TimeoutError
    with pytest.raises(TimeoutError, match=str(p.proposal_id)):
        await worker.wait_for_fill(p, 8)
    worker._trade_once = AsyncMock(side_effect=TimeoutError("ambiguous fill"))
    with pytest.raises(TimeoutError):
        await worker.trade()
    worker._trade_once.assert_awaited_once()


async def test_bounded_transient_retry_is_reported(worker, monkeypatch):
    monkeypatch.setattr(workload.asyncio, "sleep", AsyncMock())
    worker._trade_once = AsyncMock(
        side_effect=[
            workload.TransientProposalRejectionError("temporary"),
            None,
        ]
    )
    await worker.trade()
    assert worker._trade_once.await_count == 2
    assert len(worker.info["transient_rejections"]) == 1
    worker._trade_once = AsyncMock(
        side_effect=workload.TransientProposalRejectionError("persistent")
    )
    with pytest.raises(workload.TransientProposalRejectionError):
        await worker.trade()
    assert worker._trade_once.await_count == 3


async def test_foreign_review_never_authorizes_retry(worker):
    worker.state.get_json.return_value = {
        "proposal_id": str(proposal().proposal_id),
        "reviewer_agent_id": 3,
        "decision": "REJECTED",
        "reason": "no portfolio snapshot available",
        "risk_score": 1,
    }
    with pytest.raises(RuntimeError, match="identity mismatch"):
        await worker.wait_for_fill(proposal(), 8)
    worker.ledger.pool.fetchval.assert_not_awaited()
