"""Explicit legitimate approval setup for tests below the Kafka/approver seam.

The permission, economics binding and risk-evidence checks use the real store.
Only transport delivery is acknowledged here; no production control is disabled.
Full runtime tests use ProposalApprover and Kafka instead of this setup helper.
"""

from uuid import NAMESPACE_URL, uuid4, uuid5

from core.data.models import Order, TradeProposal, TradeProposalReview, TradeProposalStatus
from core.execution.authorization import ApprovalStore


async def authorized_order(store, value: Order) -> Order:
    proposal_id = value.proposal_id or uuid4()
    ident = uuid5(NAMESPACE_URL, f"alghrest:{store.book_id}:proposal:{proposal_id}")
    request = value.model_copy(
        update={
            "accounting_book_id": store.book_id,
            "proposal_id": proposal_id,
            "authorization_id": ident,
            "client_order_id": ident,
            "order_id": ident,
        }
    )
    proposal = TradeProposal(
        accounting_book_id=store.book_id,
        proposal_id=proposal_id,
        created_at=request.created_at,
        symbol=request.symbol,
        exchange=request.exchange,
        account_id=request.account_id,
        side=request.side,
        order_type=request.order_type,
        size=request.size,
        size_usd=request.size * (request.price or 100),
        limit_price=request.price,
        stop_loss=request.stop_price,
        strategy_id=request.strategy_id,
        agent_id=request.agent_id,
        asset_class="CRYPTO",
        confidence_score=0.9,
        status=TradeProposalStatus.APPROVED,
    )
    review = TradeProposalReview(
        accounting_book_id=store.book_id,
        proposal_id=proposal_id,
        reviewer_agent_id=3,
        decision=TradeProposalStatus.APPROVED,
        reason="explicit synthetic approval fixture",
        risk_score=0.1,
    )
    approvals = ApprovalStore(store.ledger)
    await approvals.decide(proposal, review, revision=(await store.ledger.load()).revision)
    request = await approvals.bind(proposal, request)
    await approvals.published(proposal_id)
    for event in await store.outbox():
        if event["event_key"] == f"authorized-root:{proposal_id}":
            await store.delivered(event["id"])
    return request
