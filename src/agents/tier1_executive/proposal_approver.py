"""
Agent 03 — Proposal Approver (Gateway)

Sits between strategy agents (Tier 4) and the execution layer (Tier 5).

Flow:
  PROPOSALS_BUS  ─┐
                  ├→ PositionLimitChecker → adjusts size or rejects
                  ├→ kill switch / paused strategy filter
                  └→ PROPOSALS_APPROVED   (downstream: OrderRouter)

This is the *only* component that flips a TradeProposal's status to APPROVED.
Without it, the execution pipeline has no input and orders never reach exchanges.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from agents.base_agent import BaseAgent
from core.data.models import (
    AgentConfig,
    AlertType,
    KafkaTopic,
    RiskAlert,
    RiskLevel,
    TradeProposal,
    TradeProposalReview,
    TradeProposalStatus,
)
from core.risk.position_limits import PositionLimitChecker

log = structlog.get_logger(__name__)

_STALE_PROPOSAL_SECONDS = 60


class ProposalApprover(BaseAgent):
    """
    Agent 03 — Proposal Approver.
    Validates every TradeProposal against hard risk limits before it can reach
    the order router. Pure gating layer; the strategies own the trade idea.
    """

    AGENT_ID = 3

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=1,
            name="ProposalApprover",
            config=config,
        )
        self._checker = PositionLimitChecker()
        self._approved_count = 0
        self._rejected_count = 0
        self._adjusted_count = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("proposal_approver.initialized")

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PROPOSALS_BUS])
        await consumer.initialize()
        async for msg in consumer.stream():
            try:
                payload = msg.get("payload", msg)
                await self._process(payload)
            except Exception as exc:
                self.record_processing_error(KafkaTopic.PROPOSALS_BUS.value, type(exc).__name__)
                log.warning("proposal_approver.process_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info(
            "proposal_approver.shutdown",
            approved=self._approved_count,
            rejected=self._rejected_count,
            adjusted=self._adjusted_count,
        )

    # ── Approval logic ─────────────────────────────────────────────────────────

    async def _process(self, payload: dict[str, Any]) -> None:
        try:
            proposal = TradeProposal.model_validate(payload)
        except Exception as exc:
            log.warning("proposal_approver.invalid_proposal", error=str(exc))
            return

        # A redelivered rejected proposal must not later become approved while
        # its sender retries with a fresh ID. Approved publication is likewise
        # never repeated when its delivery outcome may be uncertain.
        previous = await self.state.get_json(f"proposal_review:{proposal.proposal_id}")
        if isinstance(previous, dict):
            review = TradeProposalReview.model_validate(previous)
            if (
                review.proposal_id != proposal.proposal_id
                or review.reviewer_agent_id != self.AGENT_ID
            ):
                raise ValueError("Proposal review identity mismatch")
            if review.decision in (TradeProposalStatus.APPROVED, TradeProposalStatus.REJECTED):
                return

        # 1. Kill switch: reject everything
        if await self.is_halted():
            await self._reject(proposal, "system kill switch active")
            return

        # 2. Stale check
        created = proposal.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - created).total_seconds()
        # Match the router's five-second clock-skew allowance.
        if age < -5 or age > _STALE_PROPOSAL_SECONDS:
            await self._reject(proposal, f"stale proposal ({age:.0f}s old)")
            return

        # 3. Portfolio snapshot for limit checks
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            await self._reject(proposal, "no portfolio snapshot available")
            return

        # 4. Hard limit checks
        if not await self.state.trading_ready(portfolio):
            await self._reject(
                proposal, "portfolio exchange reconciliation is unavailable or disagrees"
            )
            return

        result = self._checker.check_proposal(proposal, portfolio)
        if not result.approved:
            await self._reject(proposal, "; ".join(result.rejections))
            return

        # 5. Approve (with possible size adjustment)
        if result.adjusted_size_usd is not None and result.adjusted_size_usd != proposal.size_usd:
            self._adjusted_count += 1
            adjusted = proposal.model_copy(
                update={
                    "status": TradeProposalStatus.APPROVED,
                    "adjusted_size_usd": result.adjusted_size_usd,
                    "size_usd": result.adjusted_size_usd,
                    # A market proposal has no limit price. Its units must still
                    # shrink with the approved notional before the router sees it.
                    "size": (
                        result.adjusted_size_usd / proposal.limit_price
                        if proposal.limit_price and proposal.limit_price > 0
                        else proposal.size * result.adjusted_size_usd / proposal.size_usd
                    ),
                }
            )
            await self._approve(adjusted, warnings=result.warnings)
        else:
            approved = proposal.model_copy(update={"status": TradeProposalStatus.APPROVED})
            await self._approve(approved, warnings=result.warnings)

    async def _approve(self, proposal: TradeProposal, warnings: list[str]) -> None:
        self._approved_count += 1
        review = TradeProposalReview(
            proposal_id=proposal.proposal_id,
            reviewer_agent_id=self.AGENT_ID,
            decision=TradeProposalStatus.APPROVED,
            reason="; ".join(warnings) if warnings else "all limits OK",
            risk_score=1.0 - min(1.0, proposal.confidence_score),
            adjusted_size_usd=proposal.adjusted_size_usd,
        )
        # Record the decision before publishing. An uncertain delivery requires
        # investigation, never another order under a replacement proposal.
        await self.state.set_json(
            f"proposal_review:{proposal.proposal_id}",
            review.model_dump(mode="json"),
            ttl=86400,
        )
        await self.publish(
            KafkaTopic.PROPOSALS_APPROVED,
            payload=proposal.model_dump(mode="json"),
            message_type="TradeProposalApproved",
        )
        log.info(
            "proposal_approver.approved",
            proposal_id=str(proposal.proposal_id),
            symbol=proposal.symbol,
            size_usd=float(proposal.size_usd),
            warnings=warnings,
        )

    async def _reject(self, proposal: TradeProposal, reason: str) -> None:
        self._rejected_count += 1
        review = TradeProposalReview(
            proposal_id=proposal.proposal_id,
            reviewer_agent_id=self.AGENT_ID,
            decision=TradeProposalStatus.REJECTED,
            reason=reason,
            risk_score=1.0,
        )
        await self.state.set_json(
            f"proposal_review:{proposal.proposal_id}",
            review.model_dump(mode="json"),
            ttl=86400,
        )
        # Publish reject as RiskAlert for transparency
        alert = RiskAlert(
            alert_type=AlertType.POSITION_LIMIT,
            risk_level=RiskLevel.MEDIUM,
            source_agent_id=self.AGENT_ID,
            message=f"Proposal rejected: {proposal.symbol} {proposal.side.value} ${float(proposal.size_usd):,.0f} — {reason}",
            triggered_value=float(proposal.size_usd),
            threshold_value=0.0,
            affected_strategy_ids=[proposal.strategy_id],
            recommended_action="Strategy will need to wait for capacity or reduce signal size.",
        )
        await self.publish(
            KafkaTopic.RISK_ALERTS,
            payload=alert.model_dump(mode="json"),
            message_type="ProposalRejected",
        )
        log.info(
            "proposal_approver.rejected",
            proposal_id=str(proposal.proposal_id),
            symbol=proposal.symbol,
            reason=reason,
        )
