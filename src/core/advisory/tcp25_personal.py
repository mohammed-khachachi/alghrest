"""Versioned TCP25 personal arithmetic. No firm qualification or execution port."""

import hashlib
import json
from datetime import datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal, localcontext
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, model_validator

from core.advisory.account import AccountState, OpenPosition, WorkingOrder
from core.advisory.analysis import risk_worksheet
from core.advisory.evaluation import EvaluationProfile, EvaluationSession, evaluation_status
from core.advisory.models import CATALOG, RiskWorksheet, Strict, UTCDateTime, utc_instant
from core.advisory.policy import tcp25_rules
from core.advisory.user_policy import UserPolicyRequest
from core.advisory.user_risk import UserRiskRequest

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
POLICY_ID: Literal["tcp25-mes-mnq-ten-micro-v1"] = "tcp25-mes-mnq-ten-micro-v1"
Algorithm = Literal[
    "tcp25-personal-rules-v1",
    "tcp25-personal-status-v1",
    "tcp25-personal-micro-cap-v1",
    "tcp25-personal-plan-v1",
]
SOURCE_FILES = tuple(
    "src/core/advisory/" + name
    for name in (
        "tcp25_personal.py",
        "user_policy.py",
        "user_risk.py",
        "account.py",
        "evaluation.py",
        "analysis.py",
        "models.py",
        "policy.py",
    )
)


class RevisionConflictError(ValueError):
    """The caller must reload policy/account evidence, never reuse capacity."""


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def policy_terms() -> dict[str, Any]:
    rules = tcp25_rules()
    return {
        "starting_balance": str(rules.starting_balance),
        "profit_target": str(rules.profit_target),
        "daily_loss_limit": str(rules.daily_loss_limit),
        "maximum_drawdown": str(rules.maximum_drawdown),
        "program": "trader_career_path",
        "phase": "evaluation_eod",
        "minimum_trading_days": 0,
        "consistency_percent": 30,
        "consistency_comparison": "strictly_less_than",
        "maximum_micro_contracts": 10,
        "maximum_open_minis": 1,
        "mini_supported": False,
        "simultaneous_mini_micro_mixing": False,
        "instruments": ["MES", "MNQ"],
        "entry_start_utc": "07:00",
        "entry_end_utc_exclusive": "14:00",
        "max_account_age_seconds": 1800,
        "working_orders_supported": False,
        "label": "USER POLICY",
        "origin": "user_defined",
    }


def policy_revision() -> str:
    return _sha({"policy_id": POLICY_ID, "terms": policy_terms()})


def source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in SOURCE_FILES}


def matches_terms(profile: EvaluationProfile) -> bool:
    terms = policy_terms()
    return all(
        getattr(profile, key)
        == (Decimal(value) if isinstance(value, str) and value.isdigit() else value)
        for key, value in terms.items()
        if key
        in {
            "starting_balance",
            "profit_target",
            "daily_loss_limit",
            "maximum_drawdown",
            "program",
            "phase",
            "minimum_trading_days",
            "consistency_percent",
        }
    )


class CapacityRequest(UserPolicyRequest):
    schema_version: Literal[2]
    policy_id: Literal["tcp25-mes-mnq-ten-micro-v1"]
    expected_policy_revision: Digest
    expected_account_revision: Digest
    additional_contracts: StrictInt = Field(ge=1, le=10)


class PlanRequest(UserRiskRequest):
    schema_version: Literal[2]
    policy_id: Literal["tcp25-mes-mnq-ten-micro-v1"]
    expected_policy_revision: Digest


def _safety() -> dict[str, Any]:
    return dict(
        firm_compliance="NOT_ASSESSED",
        firm_eligibility="BLOCKED",
        qualified_contracts=0,
        firm_reasons=["unresolved_tcp25_firm_requirements"],
        passing_probability="UNKNOWN",
        trade_permitted=False,
        execution_enabled=False,
    )


def _status(
    profile: EvaluationProfile, sessions: tuple[EvaluationSession, ...], now: datetime
) -> dict[str, Any]:
    result = evaluation_status(profile, list(sessions), now=now)
    result["account_revision"] = _sha([result["profile"], result["sessions"]])
    result["personal_terms_match"] = matches_terms(profile)
    result["personal_targets_met"] = (
        result["personal_terms_match"] and result["recorded_targets_met"]
    )
    result["read_only_legacy"] = not result["personal_terms_match"]
    return result | _safety()


def _context(status: dict[str, Any], now: datetime) -> tuple[list[str], list[str], int | None]:
    blocked, unknown = [], []
    if not status["personal_terms_match"]:
        blocked.append("tcp25_profile_terms_mismatch")
    blocked.extend("recorded_breach:" + value for value in status["breaches"])
    if not status["rules_current"]:
        unknown.append("rules_review_not_current")
    if not status["fresh_observation"]:
        unknown.append("missing_fresh_open_session")
    if not time(7) <= now.time() < time(14) or status["clock"]["regular_hours_closed"]:
        blocked.append("outside_personal_entry_window")
    account = AccountState.model_validate(status["account_state"])
    if account.health != "KNOWN":
        (blocked if account.health == "INVALID" else unknown).extend(account.reasons)
    gross = None
    observation = account.observation
    if observation is not None:
        if observation.positions is None or observation.working_orders is None:
            unknown.append("unknown_exposure_coverage")
        else:
            rows: tuple[OpenPosition | WorkingOrder, ...] = (
                *observation.positions,
                *observation.working_orders,
            )
            if any(
                p.instrument_id not in {"MES", "MNQ"}
                or not CATALOG[p.instrument_id].valid_contract(p.contract)
                for p in rows
            ):
                blocked.append("mini_mixed_or_unsupported_exposure")
            else:
                gross = sum(p.contracts for p in observation.positions)
                if gross > 10:
                    blocked.append("personal_micro_cap_exceeded")
            if observation.working_orders:
                unknown.append("working_order_exposure_unresolved")
    return blocked, unknown, gross


def _project(
    algorithm: Algorithm,
    profile: EvaluationProfile | None,
    sessions: tuple[EvaluationSession, ...],
    request: CapacityRequest | PlanRequest | None,
    now: datetime,
) -> dict[str, Any]:
    if algorithm == "tcp25-personal-rules-v1":
        if profile is not None or sessions or request is not None:
            raise ValueError("Rules cannot contain account inputs")
        return policy_terms() | _safety()
    if profile is None:
        raise ValueError("Account evidence is required")
    profile = EvaluationProfile.model_validate(profile.model_dump())
    sessions = tuple(EvaluationSession.model_validate(row.model_dump()) for row in sessions)
    status = _status(profile, sessions, now)
    if algorithm == "tcp25-personal-status-v1":
        if request is not None:
            raise ValueError("Status cannot contain a calculation request")
        return status
    expected_type = CapacityRequest if algorithm == "tcp25-personal-micro-cap-v1" else PlanRequest
    if not isinstance(request, expected_type):
        raise ValueError("Request/algorithm identity mismatch")
    request = expected_type.model_validate(request.model_dump())
    if (
        request.expected_policy_revision != policy_revision()
        or request.expected_account_revision != status["account_revision"]
    ):
        raise RevisionConflictError("Policy/account revision changed")
    blocked, unknown, gross = _context(status, now)
    account = AccountState.model_validate(status["account_state"])
    expires = min(now + timedelta(seconds=1800), datetime.combine(now.date(), time(14), now.tzinfo))
    if account.observation:
        expires = min(expires, account.observation.observed_at + timedelta(seconds=1800))
    if expires <= now:
        unknown.append("personal_capacity_expired")
    shared = (
        dict(
            account_revision=status["account_revision"],
            account_id=profile.id,
            journal_equity_usd=status["balance"],
            account_state=status["account_state"],
            maximum_micro_contracts=10,
            expires_at=expires.isoformat(),
        )
        | _safety()
    )
    if isinstance(request, CapacityRequest):
        if gross is not None and gross + request.additional_contracts > 10:
            blocked.append("proposed_addition_exceeds_personal_cap")
        state = "BLOCKED" if blocked else "UNKNOWN" if unknown else "WITHIN_CAP"
        return shared | dict(
            state=state,
            reasons=sorted(set(blocked + unknown)),
            gross_micro_contracts=gross,
            remaining_micro_contracts=(
                0 if blocked else None if unknown or gross is None else 10 - gross
            ),
        )
    if not isinstance(request, PlanRequest):
        raise ValueError("Plan request required")
    if account.observation and (
        account.observation.positions or account.observation.working_orders
    ):
        unknown.append("open_exposure_stop_risk_unknown")
    budget = loss = estimated = Decimal(0)
    size = 0
    with localcontext() as context:
        context.prec = 80
        equity = Decimal(status["balance"])
        if equity <= 0:
            blocked.append("nonpositive_equity")
        if not blocked and not unknown:
            worksheet = risk_worksheet(
                RiskWorksheet(
                    instrument_id=request.instrument_id,
                    account_value=equity,
                    risk_percent=request.risk_percent,
                    entry=request.entry,
                    stop=request.stop,
                    fees_per_unit=request.fees_per_unit,
                    slippage_points=request.slippage_points,
                )
            )
            loss = Decimal(worksheet["loss_per_unit"])
            budget = max(
                Decimal(0),
                min(
                    Decimal(worksheet["risk_budget"]),
                    Decimal(status["daily_loss_remaining"]) - request.safety_buffer,
                    Decimal(status["drawdown_remaining"]) - request.safety_buffer,
                ),
            )
            size = min(10, int((budget / loss).to_integral_value(rounding=ROUND_FLOOR)))
            if size == 0:
                blocked.append("risk_budget_below_one_contract")
            estimated = size * loss
    return shared | dict(
        state="BLOCKED" if blocked else "UNKNOWN" if unknown else "CALCULATED",
        reasons=sorted(set(blocked + unknown)),
        risk_budget=str(budget),
        loss_per_unit=str(loss),
        personal_contracts=size,
        estimated_loss_at_stop=str(estimated),
        daily_loss_remaining=status["daily_loss_remaining"],
        drawdown_remaining=status["drawdown_remaining"],
        minimum_balance=status["minimum_balance"],
        consistency_met=status["consistency_met"],
        personal_targets_met=status["personal_targets_met"],
    )


class PersonalEvidence(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal[2] = 2
    policy_id: Literal["tcp25-mes-mnq-ten-micro-v1"] = POLICY_ID
    policy_revision: Digest
    algorithm_version: Algorithm
    generated_at: UTCDateTime
    profile: EvaluationProfile | None = None
    sessions: tuple[EvaluationSession, ...] = Field(default=(), max_length=10000)
    request: CapacityRequest | PlanRequest | None = None
    source_hashes: dict[str, Digest]
    result: dict[str, Any]

    @model_validator(mode="after")
    def replay(self) -> Self:
        if self.policy_revision != policy_revision() or self.source_hashes != source_hashes():
            raise ValueError("Personal policy/source identity differs")
        if self.result != _project(
            self.algorithm_version, self.profile, self.sessions, self.request, self.generated_at
        ):
            raise ValueError("Personal evidence replay mismatch")
        return self


def assess(
    algorithm: Algorithm,
    *,
    now: datetime,
    profile: EvaluationProfile | None = None,
    sessions: list[EvaluationSession] | tuple[EvaluationSession, ...] = (),
    request: CapacityRequest | PlanRequest | None = None,
) -> PersonalEvidence:
    now = utc_instant(now)
    rows = tuple(sessions)
    return PersonalEvidence(
        algorithm_version=algorithm,
        policy_revision=policy_revision(),
        generated_at=now,
        profile=profile,
        sessions=rows,
        request=request,
        source_hashes=source_hashes(),
        result=_project(algorithm, profile, rows, request, now),
    )


def verify_current(
    value: PersonalEvidence,
    *,
    now: datetime,
    profile: EvaluationProfile,
    sessions: list[EvaluationSession],
) -> None:
    restored = PersonalEvidence.model_validate(value.model_dump())
    now = utc_instant(now)
    if now < restored.generated_at or now >= datetime.fromisoformat(restored.result["expires_at"]):
        raise RevisionConflictError("Personal evidence expired")
    current = assess(
        restored.algorithm_version,
        now=now,
        profile=profile,
        sessions=sessions,
        request=restored.request,
    )
    if current.result["state"] != restored.result["state"]:
        raise RevisionConflictError("Current account state no longer matches")
