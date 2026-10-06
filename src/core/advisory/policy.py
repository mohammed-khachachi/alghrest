"""Replaceable evaluation policy. Public TCP25 review is data, not strategy logic.

Daily/EOD/consistency arithmetic reuses the journal. Unverified progression,
calendar, margin or external floor evidence remains unknown. No trade permission,
funded-account rules, evaluation certification or rule-exact simulator is implied.
"""

from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Literal, Protocol, Self
from uuid import uuid4

from pydantic import ConfigDict, Field, HttpUrl, StrictBool, StrictInt, model_validator

from core.advisory.account import AccountState
from core.advisory.evaluation import (
    EvaluationProfile,
    EvaluationSession,
    evaluation_risk_blocks,
    evaluation_status,
)
from core.advisory.models import (
    CATALOG,
    Number,
    PolicyRiskAllowance,
    Price,
    Strict,
    UTCDateTime,
    utc_instant,
)

TCP25_REVIEWED_AT = datetime.fromisoformat("2026-10-06T09:31:44+00:00")
TCP25_SOURCES = (
    "https://www.earn2trade.com/trader-career-path",
    "https://help.earn2trade.com/en/articles/5941958-what-are-the-evaluation-rules",
    "https://help.earn2trade.com/en/articles/3395926-how-is-my-daily-loss-calculated",
    "https://help.earn2trade.com/en/articles/5372687-how-does-end-of-day-drawdown-work",
    "https://help.earn2trade.com/en/articles/3849975-what-is-the-maintain-consistency-rule",
    "https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path",
    "https://help.earn2trade.com/en/articles/3224526-are-there-any-restrictions-on-when-i-can-trade-in-my-evaluation-account",
)
TCP25_MICROS = ("MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG")
Reference = Annotated[str, Field(min_length=1, max_length=500, pattern=r".*\S.*")]
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Evidence(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyControls(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    source_reference: Reference
    max_evidence_age_seconds: StrictInt = Field(ge=0, le=1800)
    max_review_age_days: StrictInt = Field(ge=0, le=30)


class EODRules(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    known_at: UTCDateTime
    sources: tuple[HttpUrl, ...] = Field(min_length=1, max_length=20)
    program: Literal["trader_career_path", "gauntlet_mini"]
    starting_balance: Price
    profit_target: Price
    daily_loss_limit: Price
    maximum_drawdown: Price
    consistency_percent: Literal[30] = 30
    minimum_trading_days: StrictInt = Field(ge=0, le=365)
    maximum_standard_contracts: StrictInt = Field(ge=1, le=30)
    eligible_markets: tuple[str, ...] = Field(min_length=1, max_length=20)
    micro_markets: tuple[str, ...]
    micros_per_standard: StrictInt = Field(ge=1, le=100)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.maximum_drawdown >= self.starting_balance:
            raise ValueError("Drawdown must be below capital")
        if len(set(self.eligible_markets)) != len(self.eligible_markets) or len(
            set(self.micro_markets)
        ) != len(self.micro_markets):
            raise ValueError("Policy markets must be distinct")
        if not set(self.micro_markets) <= set(self.eligible_markets):
            raise ValueError("Micro markets must belong to the policy universe")
        if any(
            root not in CATALOG or CATALOG[root].futures_spec is None
            for root in self.eligible_markets
        ):
            raise ValueError("Policy universe requires known futures markets")
        return self


def tcp25_rules() -> EODRules:
    return EODRules(
        id="earn2trade-tcp25-eod",
        version="tcp25-eod-public-2026-10-06",
        known_at=TCP25_REVIEWED_AT,
        sources=tuple(HttpUrl(url) for url in TCP25_SOURCES),
        program="trader_career_path",
        starting_balance=Decimal(25000),
        profit_target=Decimal(1750),
        daily_loss_limit=Decimal(550),
        maximum_drawdown=Decimal(1500),
        minimum_trading_days=0,
        maximum_standard_contracts=3,
        eligible_markets=(*TCP25_MICROS, "NQ"),
        micro_markets=TCP25_MICROS,
        micros_per_standard=10,
    )


class ProgressionBand(Evidence):
    minimum_equity: Number
    maximum_standard_contracts: StrictInt = Field(ge=0, le=30)


class ProgressionSchedule(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    policy_id: str
    policy_version: str
    known_at: UTCDateTime
    source_reference: Reference
    confirmed: StrictBool
    bands: tuple[ProgressionBand, ...] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def ordered(self) -> Self:
        for a, b in zip(self.bands, self.bands[1:], strict=False):
            if (
                a.minimum_equity >= b.minimum_equity
                or a.maximum_standard_contracts > b.maximum_standard_contracts
            ):
                raise ValueError("Progression bands must be ordered, distinct and nondecreasing")
        return self


class TradingWindow(Evidence):
    instrument_id: str
    start: UTCDateTime
    end: UTCDateTime
    flat_by: UTCDateTime

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.instrument_id not in CATALOG or CATALOG[self.instrument_id].futures_spec is None:
            raise ValueError("Calendar requires known futures market")
        if not self.start < self.flat_by <= self.end:
            raise ValueError("Window must have an ordered mandatory flat deadline")
        return self


class TradingCalendar(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    known_at: UTCDateTime
    source_reference: Reference
    confirmed: StrictBool
    complete: StrictBool
    coverage_start: UTCDateTime
    coverage_end: UTCDateTime
    covered_markets: tuple[str, ...] = Field(min_length=1, max_length=20)
    windows: tuple[TradingWindow, ...] = Field(max_length=1000)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.coverage_start >= self.coverage_end or len(set(self.covered_markets)) != len(
            self.covered_markets
        ):
            raise ValueError("Calendar requires ordered coverage and distinct markets")
        for root in self.covered_markets:
            if root not in CATALOG or CATALOG[root].futures_spec is None:
                raise ValueError("Unknown calendar market")
            windows = sorted(
                (w for w in self.windows if w.instrument_id == root), key=lambda w: w.start
            )
            if any(a.end > b.start for a, b in pairwise(windows)):
                raise ValueError("Calendar windows cannot overlap")
        if any(
            w.instrument_id not in self.covered_markets
            or w.start < self.coverage_start
            or w.end > self.coverage_end
            for w in self.windows
        ):
            raise ValueError("Calendar windows must lie within reported coverage")
        return self


class EvaluationEvidence(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    account_id: str
    account_revision: Revision
    instrument_id: str
    contract: str
    known_at: UTCDateTime
    source_reference: Reference
    origin: Literal["reported", "synthetic"]
    confirmed: StrictBool
    observed_minimum_balance: Price | None
    thresholds_in_sync: StrictBool | None
    margin_contracts_available: StrictInt | None = Field(ge=0)
    progression: ProgressionSchedule | None
    calendar: TradingCalendar | None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.instrument_id not in CATALOG or not CATALOG[self.instrument_id].valid_contract(
            self.contract
        ):
            raise ValueError("Evidence requires a dated futures market")
        if any(
            value and value.known_at > self.known_at for value in (self.progression, self.calendar)
        ):
            raise ValueError("Evidence cannot contain future-known child revisions")
        return self


class PolicyAssessment(Evidence):
    id: str
    generated_at: UTCDateTime
    scope: Literal["evaluation_policy_check"] = "evaluation_policy_check"
    algorithm_version: Literal["reported-eod-policy-v1"] = "reported-eod-policy-v1"
    rules: EODRules
    controls: PolicyControls
    profile: EvaluationProfile
    sessions: tuple[EvaluationSession, ...]
    evidence: EvaluationEvidence | None
    account_revision: Revision
    account_state: AccountState
    state: Literal["READY", "BLOCKED", "UNKNOWN"]
    outcome: Literal["CONTINUE", "FAILED", "TARGETS_RECORDED"]
    reasons: tuple[str, ...]
    balance: Number
    daily_loss_remaining: Number
    drawdown_remaining: Number
    minimum_balance: Number
    best_day: Number
    total_pnl: Number
    consistency_met: StrictBool
    recorded_targets_met: StrictBool
    flat_by: UTCDateTime | None
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.state == "READY" and (
            self.reasons
            or self.evidence is None
            or self.account_state.health != "KNOWN"
            or self.flat_by is None
        ):
            raise ValueError("Ready policy requires complete known unblocked evidence")
        if self.state != "READY" and not self.reasons:
            raise ValueError("Blocked/unknown policy needs reasons")
        return self


class EvaluationPolicy(Protocol):
    @property
    def rules(self) -> EODRules: ...
    def assess(
        self,
        profile: EvaluationProfile,
        sessions: list[EvaluationSession],
        *,
        account_revision: str,
        evidence: EvaluationEvidence | None,
        now: datetime,
    ) -> PolicyAssessment: ...
    def allowance(
        self,
        assessment: PolicyAssessment,
        *,
        instrument_id: str,
        contract: str,
        invalidation: Decimal,
        loss_per_contract: Decimal | None,
    ) -> PolicyRiskAllowance: ...


class EODPolicy:
    """Reusable journal-backed EOD family; other policy families use the same port."""

    def __init__(self, rules: EODRules, controls: PolicyControls) -> None:
        self.rules = EODRules.model_validate(rules.model_dump())
        self.controls = PolicyControls.model_validate(controls.model_dump())

    def assess(
        self,
        profile: EvaluationProfile,
        sessions: list[EvaluationSession],
        *,
        account_revision: str,
        evidence: EvaluationEvidence | None,
        now: datetime,
    ) -> PolicyAssessment:
        now = utc_instant(now)
        rules = EODRules.model_validate(self.rules.model_dump(warnings=False))
        controls = PolicyControls.model_validate(self.controls.model_dump(warnings=False))
        status = evaluation_status(profile, sessions, now=now)
        profile = EvaluationProfile.model_validate(status["profile"])
        sessions = [EvaluationSession.model_validate(row) for row in status["sessions"]]
        account = AccountState.model_validate(status["account_state"])
        blocked = list(evaluation_risk_blocks(status))
        unknown = []
        expected = (
            rules.program,
            rules.starting_balance,
            rules.profit_target,
            rules.daily_loss_limit,
            rules.maximum_drawdown,
            rules.minimum_trading_days,
            rules.consistency_percent,
        )
        actual = (
            profile.program,
            profile.starting_balance,
            profile.profit_target,
            profile.daily_loss_limit,
            profile.maximum_drawdown,
            profile.minimum_trading_days,
            profile.consistency_percent,
        )
        if actual != expected:
            blocked.append("journal_profile_policy_mismatch")
        if not 0 <= (now - rules.known_at).total_seconds() <= controls.max_review_age_days * 86400:
            unknown.append("stale_or_future_rule_review")
        if account.health != "KNOWN":
            unknown.extend(account.reasons)
        if account.observation and (
            account.observation.positions or account.observation.working_orders
        ):
            unknown.append("unquantified_open_exposure")
        if evidence is not None:
            try:
                evidence = EvaluationEvidence.model_validate(evidence.model_dump(warnings=False))
            except (ValueError, TypeError, AttributeError):
                evidence = None
                blocked.append("invalid_policy_evidence")
        flat_by = None
        if evidence is None:
            unknown.append("missing_policy_evidence")
        else:
            if (evidence.account_id, evidence.account_revision) != (profile.id, account_revision):
                blocked.append("policy_evidence_account_mismatch")
            if evidence.instrument_id not in rules.eligible_markets:
                blocked.append("policy_market_not_eligible")
            if (
                evidence.origin == "synthetic"
                and account.observation
                and account.observation.source != "replay"
            ):
                blocked.append("synthetic_current_policy_evidence")
            if not evidence.confirmed:
                unknown.append("unconfirmed_policy_evidence")
            if (
                not 0
                <= (now - evidence.known_at).total_seconds()
                <= controls.max_evidence_age_seconds
            ):
                unknown.append("stale_or_future_policy_evidence")
            if (
                evidence.thresholds_in_sync is not True
                or evidence.observed_minimum_balance is None
                or evidence.observed_minimum_balance != Decimal(status["minimum_balance"])
            ):
                unknown.append("minimum_balance_not_synchronized")
            if evidence.margin_contracts_available is None:
                unknown.append("unknown_contract_margin")
            progression = evidence.progression
            if progression is None:
                unknown.append("unknown_progression_schedule")
            else:
                if not progression.confirmed:
                    unknown.append("unconfirmed_progression_schedule")
                if (
                    not 0
                    <= (now - progression.known_at).total_seconds()
                    <= controls.max_evidence_age_seconds
                ):
                    unknown.append("stale_or_future_progression_schedule")
                if (progression.policy_id, progression.policy_version) != (rules.id, rules.version):
                    blocked.append("progression_policy_mismatch")
                if progression.bands[
                    0
                ].minimum_equity > rules.starting_balance - rules.maximum_drawdown or any(
                    b.maximum_standard_contracts > rules.maximum_standard_contracts
                    for b in progression.bands
                ):
                    blocked.append("invalid_progression_bounds")
            calendar = evidence.calendar
            if calendar is None:
                unknown.append("unknown_exchange_calendar")
            else:
                if not (calendar.confirmed and calendar.complete):
                    unknown.append("unconfirmed_exchange_calendar")
                if (
                    not 0
                    <= (now - calendar.known_at).total_seconds()
                    <= controls.max_evidence_age_seconds
                ):
                    unknown.append("stale_or_future_exchange_calendar")
                if (
                    evidence.instrument_id not in calendar.covered_markets
                    or not calendar.coverage_start <= now < calendar.coverage_end
                ):
                    unknown.append("calendar_outside_coverage")
                else:
                    window = next(
                        (
                            w
                            for w in calendar.windows
                            if w.instrument_id == evidence.instrument_id and w.start <= now < w.end
                        ),
                        None,
                    )
                    if window is None or now >= window.flat_by:
                        blocked.append("exchange_closed_or_flat_deadline")
                    else:
                        flat_by = min(
                            window.flat_by,
                            datetime.fromisoformat(status["clock"]["required_flat_by"]),
                        )
        state: Literal["READY", "BLOCKED", "UNKNOWN"] = (
            "BLOCKED" if blocked else "UNKNOWN" if unknown else "READY"
        )
        return PolicyAssessment(
            id=str(uuid4()),
            generated_at=now,
            rules=rules,
            controls=controls,
            profile=profile,
            sessions=tuple(sessions),
            evidence=evidence,
            account_revision=account_revision,
            account_state=account,
            state=state,
            outcome=(
                "FAILED"
                if status["breaches"]
                else "TARGETS_RECORDED" if status["recorded_targets_met"] else "CONTINUE"
            ),
            reasons=tuple(sorted(set(blocked + unknown))),
            balance=status["balance"],
            daily_loss_remaining=status["daily_loss_remaining"],
            drawdown_remaining=status["drawdown_remaining"],
            minimum_balance=status["minimum_balance"],
            best_day=status["best_day"],
            total_pnl=status["total_pnl"],
            consistency_met=status["consistency_met"],
            recorded_targets_met=status["recorded_targets_met"],
            flat_by=flat_by,
        )

    def allowance(
        self,
        assessment: PolicyAssessment,
        *,
        instrument_id: str,
        contract: str,
        invalidation: Decimal,
        loss_per_contract: Decimal | None,
    ) -> PolicyRiskAllowance:
        assessment = PolicyAssessment.model_validate(assessment.model_dump())
        verify_policy_assessment(assessment)
        evidence = assessment.evidence
        reasons = list(assessment.reasons)
        state = assessment.state
        maximum = None
        if assessment.rules != self.rules or assessment.controls != self.controls:
            state = "BLOCKED"
            reasons.append("policy_allowance_configuration_mismatch")
        if evidence and (evidence.instrument_id, evidence.contract) != (instrument_id, contract):
            state = "BLOCKED"
            reasons.append("policy_allowance_market_mismatch")
        if state == "READY":
            if (
                loss_per_contract is None
                or not loss_per_contract.is_finite()
                or loss_per_contract <= 0
            ):
                state = "UNKNOWN"
                reasons.append("missing_stop_cost_estimate")
            else:
                assert (
                    evidence
                    and evidence.progression
                    and evidence.margin_contracts_available is not None
                )
                units = (
                    assessment.rules.micros_per_standard
                    if instrument_id in assessment.rules.micro_markets
                    else 1
                )
                upper = min(
                    assessment.rules.maximum_standard_contracts * units,
                    evidence.margin_contracts_available,
                )
                maximum = 0
                for quantity in range(1, upper + 1):
                    loss = loss_per_contract * quantity
                    equity_at_stop = assessment.balance - loss
                    if (
                        loss >= assessment.daily_loss_remaining
                        or equity_at_stop <= assessment.minimum_balance
                    ):
                        continue
                    band = next(
                        (
                            b
                            for b in reversed(evidence.progression.bands)
                            if equity_at_stop >= b.minimum_equity
                        ),
                        None,
                    )
                    if band and quantity <= band.maximum_standard_contracts * units:
                        maximum = quantity
        return PolicyRiskAllowance(
            account_id=assessment.profile.id,
            account_revision=assessment.account_revision,
            known_at=assessment.generated_at,
            source_reference=f"Policy assessment {assessment.id}; {assessment.rules.id}/{assessment.rules.version}",
            policy_id=assessment.rules.id,
            policy_version=assessment.rules.version,
            instrument_id=instrument_id,
            contract=contract,
            at_invalidation=invalidation,
            state=state,
            reasons=tuple(sorted(set(reasons))),
            daily_loss_remaining_usd=assessment.daily_loss_remaining,
            drawdown_remaining_usd=assessment.drawdown_remaining,
            maximum_contracts=maximum,
        )


class TCP25Policy(EODPolicy):
    def __init__(self, controls: PolicyControls) -> None:
        super().__init__(tcp25_rules(), controls)


def verify_policy_assessment(value: PolicyAssessment) -> None:
    if value.state != "READY":
        return
    expected = EODPolicy(value.rules, value.controls).assess(
        value.profile,
        list(value.sessions),
        account_revision=value.account_revision,
        evidence=value.evidence,
        now=value.generated_at,
    )
    if value.model_dump(exclude={"id"}) != expected.model_dump(exclude={"id"}):
        raise ValueError("Policy assessment does not reproduce from its source snapshot")
