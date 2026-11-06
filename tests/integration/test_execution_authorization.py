"""Real durable approval is required at the journal admission seam."""

import asyncio
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from core.data.models import TradeProposal, TradeProposalReview, TradeProposalStatus
from core.execution.authorization import ApprovalStore, AuthorizationError
from tests.integration.test_execution_recovery import order, ready

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.integration.test_execution_recovery",)


async def test_concurrent_approval_writers_commit_only_one_decision(recovery):
    r = recovery
    await ready(r)
    value = TradeProposal(
        accounting_book_id=r.store.book_id,
        proposal_id=uuid4(),
        strategy_id="concurrent-approval",
        agent_id=12,
        symbol="BTC/USD",
        exchange="binance",
        asset_class="CRYPTO",
        side="BUY",
        order_type="LIMIT",
        size=".1",
        size_usd="10",
        limit_price="100",
        stop_loss="99",
        confidence_score=0.9,
        status="APPROVED",
    )
    review = TradeProposalReview(
        accounting_book_id=r.store.book_id,
        proposal_id=value.proposal_id,
        reviewer_agent_id=3,
        decision="APPROVED",
        reason="explicit concurrent synthetic approval",
        risk_score=0.1,
    )
    store = ApprovalStore(r.ledger)
    revision = (await r.ledger.load()).revision
    results = await asyncio.gather(
        *(store.decide(value, review, revision=revision) for _ in range(16))
    )
    assert results.count(True) == 1
    assert await store.review(value.proposal_id) == review
    outbox = await r.store.outbox()
    assert len([e for e in outbox if e["event_key"] == f"approval:{value.proposal_id}"]) == 1


def scoped_order(r):
    proposal_id = uuid4()
    ident = uuid5(NAMESPACE_URL, f"alghrest:{r.store.book_id}:proposal:{proposal_id}")
    return order(proposal_id=proposal_id).model_copy(
        update={
            "accounting_book_id": r.store.book_id,
            "authorization_id": ident,
            "order_id": ident,
            "client_order_id": ident,
        }
    )


async def approve(r, value):
    proposal = TradeProposal(
        accounting_book_id=r.store.book_id,
        proposal_id=value.proposal_id,
        created_at=value.created_at,
        strategy_id=value.strategy_id,
        agent_id=value.agent_id,
        symbol=value.symbol,
        exchange=value.exchange,
        account_id=value.account_id,
        asset_class="CRYPTO",
        side=value.side,
        order_type=value.order_type,
        size=value.size,
        size_usd=value.size * 100,
        limit_price=value.price,
        stop_loss=value.stop_price,
        confidence_score=0.9,
        status=TradeProposalStatus.APPROVED,
    )
    review = TradeProposalReview(
        accounting_book_id=r.store.book_id,
        proposal_id=proposal.proposal_id,
        reviewer_agent_id=3,
        decision=TradeProposalStatus.APPROVED,
        reason="explicit synthetic risk approval",
        risk_score=0.1,
    )
    store = ApprovalStore(r.ledger)
    assert await store.decide(proposal, review, revision=(await r.ledger.load()).revision)
    return await store.bind(proposal, value)


async def test_missing_durable_approval_cannot_claim_or_poison_intent(recovery):
    r = recovery
    await ready(r)
    value = scoped_order(r)
    with pytest.raises(AuthorizationError, match="durable approval"):
        await r.store.prepare(value)
    assert not await r.store.seen(value)
    authorized = await approve(r, value)
    assert await r.store.prepare(authorized)


@pytest.mark.parametrize(
    "changes",
    [
        {"size": "2"},
        {"stop_price": "1"},
        {"account_id": "other"},
        {"accounting_book_id": "test:other"},
        {"authorization_id": None},
    ],
)
async def test_tampered_instruction_cannot_use_anotherwise_valid_approval(recovery, changes):
    r = recovery
    await ready(r)
    value = await approve(r, scoped_order(r))
    # Revalidate JSON so numeric changes retain the actual wire contract types.
    bad = type(value).model_validate({**value.model_dump(mode="json"), **changes})
    with pytest.raises(AuthorizationError):
        await r.store.prepare(bad)
    assert not await r.store.seen(value)


@pytest.mark.parametrize(
    "changes",
    [
        {"filled_size": "1"},
        {"fees": "100"},
        {"status": "FILLED"},
        {"exchange_order_id": "forged-observation"},
    ],
)
async def test_submission_cannot_forge_broker_observation_fields(recovery, changes):
    r = recovery
    await ready(r)
    value = await approve(r, scoped_order(r))
    bad = type(value).model_validate({**value.model_dump(mode="json"), **changes})
    with pytest.raises(AuthorizationError):
        await r.store.prepare(bad)
    assert not await r.store.seen(value)


async def test_scheduler_survives_malformed_and_unauthorized_kafka_deliveries(recovery):
    from agents.tier5_execution.slippage_minimizer import SlippageMinimizer
    from core.data.models import OrderType
    from core.execution.twap import TwapScheduler

    r = recovery
    await ready(r)
    value = scoped_order(r).model_copy(update={"order_type": OrderType.TWAP})

    class Delivery:
        async def initialize(self):
            pass

        async def stream(self):
            yield {"payload": {"accounting_book_id": r.store.book_id, "size": "invalid"}}
            yield {
                "payload": value.model_copy(
                    update={"algo_params": {"num_slices": "invalid"}}
                ).model_dump(mode="json")
            }
            yield {"payload": value.model_dump(mode="json")}

    agent = SlippageMinimizer()
    agent.state = r.state
    agent.store = r.store
    agent.scheduler = TwapScheduler(r.store, r.state)
    agent.make_consumer = lambda *_args, **_kwargs: Delivery()
    await agent.run()
    assert await agent.scheduler.active() == []
    assert not await r.store.seen(value)
