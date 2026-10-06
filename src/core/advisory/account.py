"""Provider-independent account evidence. No broker or execution capability."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from core.advisory.models import CATALOG, Number, Strict, UTCDateTime, utc_instant

Identity = Annotated[str, Field(min_length=1, max_length=100, pattern=r".*\S.*")]
AccountId = Annotated[str, Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")]


class _Evidence(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AccountConfiguration(_Evidence):
    """Exact research/configuration identity; contains no account balance or budget."""

    instrument_id: str
    strategy_id: Identity
    strategy_version: Identity
    risk_configuration_id: Identity
    risk_configuration_version: Identity
    evaluation_policy_id: Identity
    evaluation_policy_version: Identity
    cost_model_version: Identity
    edge_id: Identity
    edge_version: Identity
    fit_id: Identity
    fit_version: Identity
    dataset_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]

    @model_validator(mode="after")
    def market(self) -> Self:
        if self.instrument_id not in CATALOG or CATALOG[self.instrument_id].futures_spec is None:
            raise ValueError("Account assignment requires a catalog futures market")
        return self


class ResearchAssignment(_Evidence):
    configuration: AccountConfiguration
    selection_id: Identity
    source_reference: Annotated[str, Field(min_length=1, max_length=500, pattern=r".*\S.*")]


class AccountBinding(_Evidence):
    slot: Literal["B", "A", "C"]
    account_id: AccountId
    assignments: tuple[ResearchAssignment, ...] = Field(default=(), max_length=20)

    @model_validator(mode="after")
    def assignments_distinct(self) -> Self:
        roots = [assignment.configuration.instrument_id for assignment in self.assignments]
        if len(set(roots)) != len(roots):
            raise ValueError("An account has at most one assigned configuration per market")
        if self.slot == "C" and self.assignments:
            raise ValueError("Initial reserve account cannot have configuration assignments")
        return self


class AccountPlan(_Evidence):
    """Initial isolated roles, before proven workflow/promotion support exists."""

    algorithm_version: Literal["initial-account-roles-v1"] = "initial-account-roles-v1"
    id: Identity
    version: Identity
    known_at: UTCDateTime
    source_reference: Annotated[str, Field(min_length=1, max_length=500, pattern=r".*\S.*")]
    origin: Literal["reported", "synthetic"]
    bindings: tuple[AccountBinding, ...] = Field(min_length=3, max_length=3)
    reserve_locked: Literal[True] = True
    challenger_shadow_only: Literal[True] = True
    trade_copying_enabled: Literal[False] = False

    @model_validator(mode="after")
    def isolated(self) -> Self:
        if {b.slot for b in self.bindings} != {"B", "A", "C"}:
            raise ValueError("Account plan needs exactly one B, A and C slot")
        if len({b.account_id for b in self.bindings}) != 3:
            raise ValueError("Account slots must bind distinct financial journals")
        return self

    @property
    def revision(self) -> str:
        encoded = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


class AccountRoleCheck(_Evidence):
    generated_at: UTCDateTime
    account_id: AccountId
    plan: AccountPlan | None
    plan_revision: str | None
    requested_configuration: AccountConfiguration | None
    mode: Literal["current", "replay"]
    slot: Literal["B", "A", "C"] | None
    role: Literal["champion", "challenger", "reserve"] | None
    state: Literal["READY", "BLOCKED", "UNKNOWN"]
    reasons: tuple[str, ...]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        roles = {"B": "champion", "A": "challenger", "C": "reserve", None: None}
        if self.role != roles[self.slot] or self.plan_revision != (
            self.plan.revision if self.plan else None
        ):
            raise ValueError("Account role/revision must match the captured plan")
        if self.state == "READY" and (
            self.reasons
            or self.slot != "B"
            or self.plan is None
            or self.requested_configuration is None
        ):
            raise ValueError("Ready account role needs a matched champion configuration")
        if self.state != "READY" and not self.reasons:
            raise ValueError("Blocked/unknown account roles need reasons")
        return self


def assess_account_role(
    plan: AccountPlan | None,
    *,
    account_id: str,
    requested_configuration: AccountConfiguration | None,
    mode: Literal["current", "replay"],
    now: datetime,
) -> AccountRoleCheck:
    """Deny missing assignments, shadow and reserve independently of financial gates."""
    now = utc_instant(now)
    blocked, unknown = [], []
    if requested_configuration is not None:
        try:
            requested_configuration = AccountConfiguration.model_validate(
                requested_configuration.model_dump(warnings=False)
            )
        except (ValueError, TypeError, AttributeError):
            requested_configuration = None
            blocked.append("invalid_requested_account_configuration")
    if plan is not None:
        try:
            plan = AccountPlan.model_validate(plan.model_dump(warnings=False))
        except (ValueError, TypeError, AttributeError):
            plan = None
            blocked.append("invalid_account_plan")
    binding = next((b for b in plan.bindings if b.account_id == account_id), None) if plan else None
    if plan is None:
        unknown.append("missing_account_plan")
    elif plan.known_at > now:
        blocked.append("future_known_account_plan")
    if plan and plan.origin == "synthetic" and mode != "replay":
        blocked.append("synthetic_current_account_plan")
    if plan and binding is None:
        blocked.append("account_not_in_plan")
    if binding:
        if binding.slot == "C":
            blocked.append("reserve_account_locked")
        elif binding.slot == "A":
            blocked.extend(("challenger_shadow_only", "champion_workflow_not_proven"))
        else:
            assignment = next(
                (
                    a
                    for a in binding.assignments
                    if requested_configuration
                    and a.configuration.instrument_id == requested_configuration.instrument_id
                ),
                None,
            )
            if assignment is None:
                unknown.append("missing_champion_configuration_assignment")
            elif assignment.configuration != requested_configuration:
                blocked.append("account_configuration_mismatch")
    roles: dict[str, Literal["champion", "challenger", "reserve"]] = {
        "B": "champion",
        "A": "challenger",
        "C": "reserve",
    }
    return AccountRoleCheck(
        generated_at=now,
        account_id=account_id,
        plan=plan,
        plan_revision=plan.revision if plan else None,
        requested_configuration=requested_configuration,
        mode=mode,
        slot=binding.slot if binding else None,
        role=roles[binding.slot] if binding else None,
        state="BLOCKED" if blocked else "UNKNOWN" if unknown else "READY",
        reasons=tuple(sorted(set(blocked + unknown))),
    )


class OpenPosition(_Evidence):
    position_id: str = Field(min_length=1, max_length=100)
    instrument_id: str = Field(min_length=1, max_length=30)
    contract: str = Field(min_length=1, max_length=40)
    side: Literal["BUY", "SELL"]
    contracts: StrictInt = Field(ge=1)
    unrealized_pnl: Number


class WorkingOrder(_Evidence):
    order_id: str = Field(min_length=1, max_length=100)
    instrument_id: str = Field(min_length=1, max_length=30)
    contract: str = Field(min_length=1, max_length=40)
    side: Literal["BUY", "SELL"]
    contracts: StrictInt = Field(ge=1)


class AccountObservation(_Evidence):
    schema_version: Literal[1] = 1
    account_id: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    source: Literal["manual_report", "replay", "read_only_report"]
    source_reference: str = Field(min_length=1, max_length=500, pattern=r".*\S.*")
    observed_at: UTCDateTime
    human_confirmed: StrictBool
    costs_included: StrictBool
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    cash_balance: Number
    unrealized_pnl: Number
    equity: Number
    # None means coverage is unknown; an explicitly empty tuple means checked flat.
    positions: tuple[OpenPosition, ...] | None = Field(default=None, max_length=200)
    working_orders: tuple[WorkingOrder, ...] | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def consistent_economics(self) -> Self:
        if self.equity != self.cash_balance + self.unrealized_pnl:
            raise ValueError("Account equity must equal cash balance plus unrealized PnL")
        if self.positions is not None:
            if sum((p.unrealized_pnl for p in self.positions), Decimal(0)) != self.unrealized_pnl:
                raise ValueError("Position PnL must reconcile with account unrealized PnL")
            if len({p.position_id for p in self.positions}) != len(self.positions):
                raise ValueError("Duplicate position identity")
        if self.working_orders is not None and len(
            {o.order_id for o in self.working_orders}
        ) != len(self.working_orders):
            raise ValueError("Duplicate working-order identity")
        return self


class AccountState(_Evidence):
    health: Literal["KNOWN", "UNKNOWN", "INVALID"]
    reasons: tuple[str, ...]
    observation: AccountObservation | None = None


def account_state(
    observation: AccountObservation | None,
    *,
    account_id: str,
    journal_equity: Decimal,
    now: datetime,
    max_age_seconds: int,
    journal_currency: str = "USD",
) -> AccountState:
    """Assess one account against durable journal equity and an explicit clock.

    KNOWN means complete and internally reconciled reported state, not broker
    authentication, strategy approval, data-health approval or trade permission.
    """
    if observation is None:
        return AccountState(health="UNKNOWN", reasons=("missing_account_observation",))
    try:
        value = AccountObservation.model_validate(observation.model_dump())
    except ValueError:
        return AccountState(health="INVALID", reasons=("invalid_account_observation",))
    invalid = []
    if value.account_id != account_id:
        invalid.append("account_identity_mismatch")
    if value.currency != journal_currency:
        invalid.append("account_currency_mismatch")
    if not journal_equity.is_finite() or value.equity != journal_equity:
        invalid.append("journal_equity_mismatch")
    if now.tzinfo is None or now.utcoffset() is None or max_age_seconds < 0:
        invalid.append("invalid_account_clock")
    if invalid:
        return AccountState(health="INVALID", reasons=tuple(invalid), observation=value)
    unknown = []
    age = (utc_instant(now) - value.observed_at).total_seconds()
    if not 0 <= age <= max_age_seconds:
        unknown.append("stale_or_future_account_observation")
    if not value.human_confirmed:
        unknown.append("unconfirmed_account_observation")
    if not value.costs_included:
        unknown.append("account_costs_unknown")
    if value.positions is None:
        unknown.append("positions_unknown")
    if value.working_orders is None:
        unknown.append("working_orders_unknown")
    return AccountState(
        health="UNKNOWN" if unknown else "KNOWN", reasons=tuple(unknown), observation=value
    )
