"""Durable approval decisions and exact execution authority for one book.

Kafka publishers cannot create permissions by setting APPROVED or copying an ID.
The approver persists the decision, the router binds one canonical root, and
execution validates that root or an exact persisted TWAP slice before claiming.
Database/host operators and the configured approver/router processes are trusted.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from core.accounting.models import utc
from core.accounting.repository import Ledger
from core.data.models import (
    KafkaTopic,
    Order,
    OrderSide,
    TradeProposal,
    TradeProposalReview,
    TradeProposalStatus,
)
from core.execution.contracts import AccountScope, RecoveryBlockedError
from core.risk.halt import halted as risk_halted


class AuthorizationError(RecoveryBlockedError):
    """An untrusted instruction has no matching durable permission."""


def digest(value: TradeProposal | Order) -> str:
    # This is a submitted request, never a mutable broker observation. Bind
    # every field so a copied permission cannot fabricate fills/status/fees.
    data = value.model_dump(mode="json")
    if isinstance(value, Order):
        data["updated_at"] = utc(value.updated_at).isoformat()
    else:
        if value.expires_at is not None:
            data["expires_at"] = utc(value.expires_at).isoformat()
    data["created_at"] = utc(value.created_at).isoformat()
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


async def validate_authorization(
    conn: Any, book_id: str, order: Order, *, revision: int | None = None
) -> None:
    if (
        order.accounting_book_id != book_id
        or order.authorization_id is None
        or order.proposal_id is None
    ):
        raise AuthorizationError("Explicit matching book and execution authorization are required")
    row = await conn.fetchrow(
        "SELECT * FROM execution.authorizations WHERE book_id=$1 AND proposal_id=$2 FOR SHARE",
        book_id,
        order.proposal_id,
    )
    if (
        not row
        or row["decision"] != "APPROVED"
        or row["authorization_id"] != order.authorization_id
    ):
        raise AuthorizationError("No matching durable approval")
    if not row["root_request"]:
        raise AuthorizationError("Approval has no bound execution intent")
    parent_id = order.algo_params.get("parent_id")
    if parent_id:
        try:
            parent_id = UUID(str(parent_id))
        except ValueError as exc:
            raise AuthorizationError("Invalid TWAP parent identity") from exc
        child = await conn.fetchrow(
            """SELECT s.request,p.request AS parent_request,p.allocated FROM execution.slices s
               JOIN execution.plans p USING(book_id,parent_id)
               WHERE s.book_id=$1 AND s.parent_id=$2 AND s.client_order_id=$3 FOR SHARE OF s,p""",
            book_id,
            parent_id,
            order.client_order_id,
        )
        root = Order.model_validate_json(row["root_request"])
        if (
            child is None
            or root.client_order_id != parent_id
            or digest(Order.model_validate_json(child["parent_request"])) != row["root_hash"]
            or digest(Order.model_validate_json(child["request"])) != digest(order)
            or child["allocated"] > root.size
        ):
            raise AuthorizationError("TWAP child does not match its authorized persisted slice")
    else:
        if row["root_hash"] != digest(order):
            raise AuthorizationError(
                "Execution economics or identity differ from durable authorization"
            )
        if revision is not None and row["approved_revision"] != revision:
            raise AuthorizationError(
                "Approval portfolio revision changed; a new review is required"
            )


class ApprovalStore:
    def __init__(self, ledger: Ledger) -> None:
        self.ledger, self.book_id = ledger, ledger.book_id

    async def review(self, proposal_id: UUID) -> TradeProposalReview | None:
        raw = await self.ledger.pool.fetchval(
            "SELECT review FROM execution.authorizations WHERE book_id=$1 AND proposal_id=$2",
            self.book_id,
            proposal_id,
        )
        return TradeProposalReview.model_validate_json(raw) if raw else None

    async def published(self, proposal_id: UUID) -> None:
        await self.ledger.pool.execute(
            "UPDATE execution.outbox SET delivered_at=now() WHERE book_id=$1 AND event_key=$2",
            self.book_id,
            f"approval:{proposal_id}",
        )

    async def decide(
        self, proposal: TradeProposal, review: TradeProposalReview, *, revision: int | None = None
    ) -> bool:
        if (
            proposal.accounting_book_id != self.book_id
            or review.accounting_book_id != self.book_id
            or review.proposal_id != proposal.proposal_id
            or review.reviewer_agent_id != 3
        ):
            raise AuthorizationError("Approval/review scope or authority does not match")
        if (
            review.decision == TradeProposalStatus.APPROVED
            and proposal.status != TradeProposalStatus.APPROVED
        ):
            raise AuthorizationError("Approved decision requires canonical approved economics")
        async with self.ledger.locked_state() as (conn, state, _opening):
            previous = await conn.fetchval(
                "SELECT decision FROM execution.authorizations WHERE book_id=$1 AND proposal_id=$2",
                self.book_id,
                proposal.proposal_id,
            )
            if previous is not None:
                return False
            if review.decision == TradeProposalStatus.APPROVED:
                gate = await conn.fetchrow(
                    "SELECT * FROM execution.books WHERE book_id=$1", self.book_id
                )
                halted = await risk_halted(conn, self.book_id)
                if (
                    revision is None
                    or revision != state.revision
                    or not gate
                    or not gate["ready"]
                    or gate["verified_revision"] != revision
                    or gate["verified_until"] <= datetime.now(UTC)
                    or halted
                ):
                    raise AuthorizationError("Approval risk evidence is missing, changed or halted")
                accounts = [AccountScope.model_validate(a) for a in json.loads(gate["accounts"])]
                if not any(
                    a.exchange == proposal.exchange
                    and a.account_id == proposal.account_id
                    and proposal.symbol in a.symbols
                    for a in accounts
                ):
                    raise AuthorizationError("Approval account/instrument is not configured")
            await conn.execute(
                """INSERT INTO execution.authorizations
                   (book_id,proposal_id,authorization_id,decision,proposal,proposal_hash,review,approved_revision)
                   VALUES($1,$2,$3,$4,$5::jsonb,$6,$7::jsonb,$8)""",
                self.book_id,
                proposal.proposal_id,
                uuid5(NAMESPACE_URL, f"alghrest:{self.book_id}:proposal:{proposal.proposal_id}"),
                review.decision.value,
                proposal.model_dump_json(),
                digest(proposal),
                review.model_dump_json(),
                revision,
            )
            if review.decision == TradeProposalStatus.APPROVED:
                await conn.execute(
                    """INSERT INTO execution.outbox(book_id,event_key,topic,message_type,payload)
                       VALUES($1,$2,$3,'TradeProposalApproved',$4::jsonb) ON CONFLICT DO NOTHING""",
                    self.book_id,
                    f"approval:{proposal.proposal_id}",
                    KafkaTopic.PROPOSALS_APPROVED.value,
                    proposal.model_dump_json(),
                )
            return True

    async def bind(self, proposal: TradeProposal, order: Order) -> Order:
        async with self.ledger.locked_state() as (conn, _state, _opening):
            row = await conn.fetchrow(
                "SELECT * FROM execution.authorizations WHERE book_id=$1 AND proposal_id=$2 FOR UPDATE",
                self.book_id,
                proposal.proposal_id,
            )
            if not row or row["decision"] != "APPROVED" or row["proposal_hash"] != digest(proposal):
                raise AuthorizationError("Approved message has no matching durable decision")
            expected_stop = proposal.stop_loss if proposal.side == OrderSide.BUY else None
            if (
                order.accounting_book_id != self.book_id
                or order.authorization_id != row["authorization_id"]
                or order.order_id != row["authorization_id"]
                or order.client_order_id != row["authorization_id"]
                or order.proposal_id != proposal.proposal_id
                or order.exchange != proposal.exchange
                or order.account_id != proposal.account_id
                or order.symbol != proposal.symbol
                or order.side != proposal.side
                or order.size != proposal.size
                or order.stop_price != expected_stop
            ):
                raise AuthorizationError("Routed intent exceeds or differs from approved economics")
            if row["root_request"]:
                return Order.model_validate_json(row["root_request"])
            await conn.execute(
                "UPDATE execution.authorizations SET root_request=$3::jsonb,root_hash=$4 WHERE book_id=$1 AND proposal_id=$2",
                self.book_id,
                proposal.proposal_id,
                order.model_dump_json(),
                digest(order),
            )
            await conn.execute(
                """INSERT INTO execution.outbox(book_id,event_key,topic,message_type,payload)
                   VALUES($1,$2,$3,'Order',$4::jsonb) ON CONFLICT DO NOTHING""",
                self.book_id,
                f"authorized-root:{proposal.proposal_id}",
                KafkaTopic.ORDERS_PENDING.value,
                order.model_dump_json(),
            )
            return order
