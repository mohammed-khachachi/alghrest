"""Replayed personal account arithmetic and flat-account sizing; no execution permission."""

import hashlib
import json
from datetime import datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, model_validator

from core.advisory.analysis import risk_worksheet
from core.advisory.evaluation import EvaluationProfile, EvaluationSession, evaluation_status
from core.advisory.models import (
    CATALOG,
    Number,
    Price,
    RiskWorksheet,
    Strict,
    UTCDateTime,
    utc_instant,
)
from core.advisory.user_policy import UserPolicyRequest, assess_user_policy

Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
TERMS = {
    "starting_balance": "50000",
    "profit_target": "3000",
    "daily_loss_limit": "1100",
    "maximum_drawdown": "2000",
    "consistency_percent": 30,
}


def personal_rules() -> dict[str, Any]:
    """Local user reference, not an external firm's agreement or approval."""
    return dict(TERMS) | {
        "label": "USER POLICY",
        "origin": "user_defined",
        "maximum_micro_contracts": 20,
        "instruments": ["MES", "MNQ"],
        "consistency_comparison": "strictly_less_than",
        "minimum_trading_days": 0,
        "entry_start_utc": "07:00",
        "entry_end_utc_exclusive": "14:00",
        "journal_date_convention": "America/Chicago; next session date at 17:00",
        "firm_compliance": "NOT_ASSESSED",
        "passing_probability": "UNKNOWN",
        "trade_permitted": False,
        "execution_enabled": False,
    }


def _source_hashes() -> dict[str, str]:
    directory = Path(__file__).parent
    return {
        "src/core/advisory/" + name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
        for name in (
            "user_risk.py",
            "user_policy.py",
            "account.py",
            "evaluation.py",
            "analysis.py",
            "models.py",
        )
    }


class UserRiskRequest(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instrument_id: Literal["MES", "MNQ"]
    contract: str = Field(min_length=1, max_length=40)
    entry: Price
    stop: Price
    risk_percent: Annotated[Decimal, Field(gt=0, le=1, allow_inf_nan=False)]
    fees_per_unit: Nonnegative
    slippage_points: Nonnegative
    safety_buffer: Price
    cost_source: Literal["user_declared", "synthetic"]
    cost_reference: str = Field(min_length=1, max_length=500)
    costs_reviewed: Literal[True]
    expected_account_revision: Revision

    @model_validator(mode="after")
    def complete_stop_and_costs(self) -> Self:
        instrument = CATALOG[self.instrument_id]
        if not instrument.valid_contract(self.contract):
            raise ValueError("Personal sizing requires a dated MES/MNQ contract")
        try:
            if (
                self.entry == self.stop
                or self.entry % instrument.tick_size
                or self.stop % instrument.tick_size
            ):
                raise ValueError("Entry and stop must differ and align with the 0.25 tick")
        except InvalidOperation as exc:
            raise ValueError("Entry or stop price is too large for tick validation") from exc
        if not self.cost_reference.strip():
            raise ValueError("Costs need an explicit reviewed reference or assumption")
        return self


def personal_account_status(
    profile: EvaluationProfile, sessions: list[EvaluationSession], *, now: datetime
) -> dict[str, Any]:
    """Replay shared EOD/account arithmetic, applying only personal eligibility semantics."""
    now = utc_instant(now)
    status = evaluation_status(profile, sessions, now)
    encoded = json.dumps(
        [status["profile"], status["sessions"]], sort_keys=True, separators=(",", ":")
    ).encode()
    revision = hashlib.sha256(encoded).hexdigest()
    matches = all(getattr(profile, field) == Decimal(str(value)) for field, value in TERMS.items())
    status.update(
        account_revision=revision,
        personal_terms_match=matches,
        rules=personal_rules(),
        recorded_targets_met=bool(sessions)
        and all(row.closed for row in sessions)
        and matches
        and not status["breaches"]
        and status["consistency_met"]
        and Decimal(status["total_pnl"]) >= Decimal("3000"),
        note="سجل قواعد المستخدم فقط؛ لا يؤكد اجتياز شركة أو اتصال وسيط. صافي PnL شامل الرسوم دون خصمها مرتين.",
    )
    status["clock"] = dict(status["clock"]) | {
        "note": "تاريخ الدفتر يتغير عند 17:00 شيكاغو. الدخول الشخصي 07:00-14:00 UTC؛ لا إغلاق تلقائي.",
    }
    return status


def _project(
    profile: EvaluationProfile,
    sessions: tuple[EvaluationSession, ...],
    request: UserRiskRequest,
    now: datetime,
) -> dict[str, Any]:
    profile = EvaluationProfile.model_validate(profile.model_dump())
    rows = [EvaluationSession.model_validate(row.model_dump()) for row in sessions]
    request = UserRiskRequest.model_validate(request.model_dump())
    status = personal_account_status(profile, rows, now=now)
    cap = assess_user_policy(
        profile,
        rows,
        UserPolicyRequest(
            instrument_id=request.instrument_id,
            contract=request.contract,
            additional_contracts=1,
            expected_account_revision=request.expected_account_revision,
        ),
        now=now,
    )
    blocked = list(cap.reasons) if cap.state == "BLOCKED" else []
    unknown = list(cap.reasons) if cap.state == "UNKNOWN" else []
    if not status["personal_terms_match"]:
        blocked.append("journal_personal_terms_mismatch")
    blocked.extend("recorded_breach:" + reason for reason in status["breaches"])
    observation = cap.account_state.observation
    if observation is not None and (observation.positions or observation.working_orders):
        unknown.append("open_exposure_stop_risk_unknown")
    with localcontext() as context:
        context.prec = 80
        equity = Decimal(status["balance"])
        # Nonpositive equity cannot supply a percentage budget; shared Price would reject it.
        budget = loss = estimated = Decimal(0)
        size = 0
        if equity <= 0:
            blocked.append("nonpositive_equity")
        else:
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
            if budget <= 0:
                blocked.append("no_remaining_buffered_risk_budget")
            if not blocked and not unknown:
                size = min(20, int((budget / loss).to_integral_value(rounding=ROUND_FLOOR)))
                estimated = size * loss
        state = "BLOCKED" if blocked else "UNKNOWN" if unknown else "CALCULATED"
    expires = min(now + timedelta(seconds=1800), datetime.combine(now.date(), time(14), now.tzinfo))
    if observation is not None:
        expires = min(expires, observation.observed_at + timedelta(seconds=1800))
    return dict(
        account_revision=cap.account_revision,
        journal_equity_usd=equity,
        state=state,
        reasons=tuple(sorted(set(blocked + unknown))),
        risk_budget=budget,
        loss_per_unit=loss,
        contracts=size,
        estimated_loss_at_stop=estimated,
        daily_loss_remaining=Decimal(status["daily_loss_remaining"]),
        drawdown_remaining=Decimal(status["drawdown_remaining"]),
        minimum_balance=Decimal(status["minimum_balance"]),
        consistency_met=status["consistency_met"],
        recorded_targets_met=status["recorded_targets_met"],
        expires_at=expires,
    )


class UserRiskAssessment(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1
    algorithm_version: Literal["user-personal-plan-v1"] = "user-personal-plan-v1"
    scope: Literal["user_personal_risk_plan"] = "user_personal_risk_plan"
    label: Literal["USER POLICY"] = "USER POLICY"
    origin: Literal["user_defined"] = "user_defined"
    generated_at: UTCDateTime
    expires_at: UTCDateTime
    profile: EvaluationProfile
    sessions: tuple[EvaluationSession, ...] = Field(max_length=10000)
    request: UserRiskRequest
    source_hashes: dict[str, Revision]
    account_revision: Revision
    journal_equity_usd: Number
    state: Literal["CALCULATED", "BLOCKED", "UNKNOWN"]
    reasons: tuple[str, ...]
    risk_budget: Nonnegative
    loss_per_unit: Nonnegative
    contracts: StrictInt = Field(ge=0, le=20)
    estimated_loss_at_stop: Nonnegative
    daily_loss_remaining: Nonnegative
    drawdown_remaining: Nonnegative
    minimum_balance: Number
    consistency_met: bool
    recorded_targets_met: bool
    firm_compliance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    passing_probability: Literal["UNKNOWN"] = "UNKNOWN"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def exact_replay(self) -> Self:
        if self.source_hashes != _source_hashes():
            raise ValueError("Personal evidence whole-file source hashes differ")
        expected = _project(self.profile, self.sessions, self.request, self.generated_at)
        if any(getattr(self, key) != value for key, value in expected.items()):
            raise ValueError("Personal evidence must match exact captured-input replay")
        return self


def assess_user_risk(
    profile: EvaluationProfile,
    sessions: list[EvaluationSession],
    request: UserRiskRequest,
    *,
    now: datetime,
) -> UserRiskAssessment:
    now = utc_instant(now)
    return UserRiskAssessment(
        generated_at=now,
        profile=profile,
        sessions=tuple(sessions),
        request=request,
        source_hashes=_source_hashes(),
        **_project(profile, tuple(sessions), request, now),
    )


def verify_user_risk_assessment(
    value: UserRiskAssessment,
    *,
    now: datetime,
    current_profile: EvaluationProfile,
    current_sessions: list[EvaluationSession],
) -> None:
    """Always source-check and replay, then compare against the current journal and clock."""
    restored = UserRiskAssessment.model_validate(value.model_dump())
    now = utc_instant(now)
    current = personal_account_status(current_profile, current_sessions, now=now)
    if current["account_revision"] != restored.account_revision:
        raise ValueError("Personal evidence current journal revision differs")
    if now < restored.generated_at or now >= restored.expires_at:
        raise ValueError("Personal evidence is expired or clock moved backwards")
    fresh = _project(current_profile, tuple(current_sessions), restored.request, now)
    if restored.state == "CALCULATED" and fresh["state"] != "CALCULATED":
        raise ValueError("Personal evidence is no longer eligible")
