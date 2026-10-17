"""User-defined Micro exposure ceiling; no firm qualification or execution capability."""

import hashlib
import json
from datetime import datetime, time
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import ConfigDict, Field, StrictInt, model_validator

from core.advisory.account import AccountState, OpenPosition, WorkingOrder
from core.advisory.evaluation import EvaluationProfile, EvaluationSession, evaluation_status
from core.advisory.models import CATALOG, Number, Strict, UTCDateTime, utc_instant


class UserPolicyRequest(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instrument_id: Literal["MES", "MNQ"]
    contract: str = Field(min_length=1, max_length=40)
    additional_contracts: StrictInt = Field(ge=1, le=1000)
    expected_account_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None

    @model_validator(mode="after")
    def dated_micro(self) -> Self:
        if not CATALOG[self.instrument_id].valid_contract(self.contract):
            raise ValueError("User policy requires a dated MES or MNQ contract")
        return self


def _project(
    profile: EvaluationProfile,
    sessions: tuple[EvaluationSession, ...],
    request: UserPolicyRequest,
    now: datetime,
) -> dict[str, Any]:
    """Reconcile one captured journal and count gross reported contracts exactly."""
    profile = EvaluationProfile.model_validate(profile.model_dump())
    rows = [EvaluationSession.model_validate(row.model_dump()) for row in sessions]
    request = UserPolicyRequest.model_validate(request.model_dump())
    now = utc_instant(now)
    encoded = json.dumps(
        [profile.model_dump(mode="json"), [row.model_dump(mode="json") for row in rows]],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    revision = hashlib.sha256(encoded).hexdigest()
    status = evaluation_status(profile, rows, now)
    account = AccountState.model_validate(status["account_state"])
    blocked: list[str] = []
    unknown: list[str] = []
    if account.health == "INVALID":
        blocked.extend(account.reasons)
    elif account.health == "UNKNOWN":
        unknown.extend(account.reasons)
    if not status["fresh_observation"]:
        unknown.append("missing_fresh_open_session")
    if request.expected_account_revision not in (None, revision):
        blocked.append("user_policy_account_revision_mismatch")
    if not time(7) <= now.time() < time(14):
        blocked.append("outside_user_entry_window")
    gross = None
    observation = account.observation
    if observation is not None:
        exposure: tuple[OpenPosition | WorkingOrder, ...] | None = (
            (*observation.positions, *observation.working_orders)
            if (observation.positions is not None and observation.working_orders is not None)
            else None
        )
        if exposure is not None:
            if any(
                row.instrument_id not in {"MES", "MNQ"}
                or not CATALOG[row.instrument_id].valid_contract(row.contract)
                for row in exposure
            ):
                blocked.append("unsupported_user_policy_exposure")
            else:
                gross = sum(row.contracts for row in exposure)
                if gross > 20:
                    blocked.append("user_micro_cap_exceeded")
                if gross + request.additional_contracts > 20:
                    blocked.append("proposed_addition_exceeds_user_micro_cap")
    state = "BLOCKED" if blocked else "UNKNOWN" if unknown else "WITHIN_CAP"
    return {
        "account_id": profile.id,
        "account_revision": revision,
        "journal_equity_usd": Decimal(status["balance"]),
        "account_state": account,
        "gross_micro_contracts": gross,
        # UNKNOWN has no reported capacity; BLOCKED never exposes a positive capacity.
        "remaining_micro_contracts": (
            0 if blocked else 20 - gross if not unknown and gross is not None else None
        ),
        "state": state,
        "reasons": tuple(sorted(set(blocked + unknown))),
    }


class UserPolicyAssessment(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    algorithm_version: Literal["user-micro-cap-v1"] = "user-micro-cap-v1"
    scope: Literal["user_policy_exposure_check"] = "user_policy_exposure_check"
    label: Literal["USER POLICY"] = "USER POLICY"
    origin: Literal["user_defined"] = "user_defined"
    source_reference: Literal["User-approved MES/MNQ-only cap: 20 gross Micro contracts"] = (
        "User-approved MES/MNQ-only cap: 20 gross Micro contracts"
    )
    maximum_micro_contracts: Literal[20] = 20
    entry_start_utc: Literal["07:00"] = "07:00"
    entry_end_utc_exclusive: Literal["14:00"] = "14:00"
    max_account_age_seconds: Literal[1800] = 1800
    generated_at: UTCDateTime
    profile: EvaluationProfile
    sessions: tuple[EvaluationSession, ...] = Field(max_length=10000)
    request: UserPolicyRequest
    account_id: str
    account_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    journal_equity_usd: Number
    account_state: AccountState
    gross_micro_contracts: StrictInt | None = Field(ge=0)
    remaining_micro_contracts: StrictInt | None = Field(ge=0, le=20)
    state: Literal["WITHIN_CAP", "BLOCKED", "UNKNOWN"]
    reasons: tuple[str, ...]
    firm_compliance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    passing_probability: Literal["UNKNOWN"] = "UNKNOWN"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def exact_personal_projection(self) -> Self:
        expected = _project(self.profile, self.sessions, self.request, self.generated_at)
        if any(getattr(self, field) != value for field, value in expected.items()):
            raise ValueError("User policy assessment must match its captured journal and request")
        return self


def assess_user_policy(
    profile: EvaluationProfile,
    sessions: list[EvaluationSession],
    request: UserPolicyRequest,
    *,
    now: datetime,
) -> UserPolicyAssessment:
    """Personal cap only; current account evidence is required independently of firm bands."""
    now = utc_instant(now)
    rows = tuple(sessions)
    return UserPolicyAssessment(
        generated_at=now,
        profile=profile,
        sessions=rows,
        request=request,
        **_project(profile, rows, request, now),
    )


def verify_user_policy_assessment(value: UserPolicyAssessment) -> None:
    """Replay captured evidence on each call; no persistent or cross-request cache."""
    UserPolicyAssessment.model_validate(value.model_dump())
