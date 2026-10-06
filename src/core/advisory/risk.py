"""Deterministic structural risk checks; independent of AI, providers and execution.

A qualified risk check is one gate, not trade permission. Policy allowances and
strategy history are supplied by a server-owned reader; reported facts do not
prove authenticated strategy approval or rule-exact evaluation compliance.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from core.advisory.account import (
    AccountConfiguration,
    AccountObservation,
    AccountPlan,
    AccountRoleCheck,
    AccountState,
    OpenPosition,
    WorkingOrder,
    account_state,
    assess_account_role,
)
from core.advisory.analysis import risk_worksheet
from core.advisory.models import (
    CATALOG,
    Number,
    PolicyRiskAllowance as PolicyRiskAllowance,
    Price,
    RiskWorksheet,
    Strict,
    UTCDateTime,
    utc_instant,
)
from core.advisory.policy import PolicyAssessment, verify_policy_assessment
from core.advisory.selection import MarketSelection, future_root, select_markets
from core.advisory.strategies import (
    StrategyApprovalCheck,
    StrategyRegistry,
    assess_strategy_approval,
)

Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Reference = Annotated[str, Field(min_length=1, max_length=500, pattern=r".*\S.*")]
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Evidence(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StructuralSetup(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    known_at: UTCDateTime
    instrument_id: str
    contract: str
    side: Literal["BUY", "SELL"]
    entry: Price
    invalidation: Price
    structure: Reference
    source_kind: Literal["manual", "strategy", "ai_proposal"]
    source_reference: Reference
    strategy_id: str = Field(min_length=1, max_length=100)
    strategy_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def market(self) -> Self:
        future_root(self.instrument_id)
        if not CATALOG[self.instrument_id].valid_contract(self.contract):
            raise ValueError("Setup requires a dated contract for its futures root")
        return self


class RiskConfiguration(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    source_reference: Reference
    risk_percent: Annotated[Decimal, Field(gt=0, le=1, allow_inf_nan=False)]
    safety_buffer_usd: Price
    round_trip_fees_per_contract_usd: Nonnegative
    slippage_ticks: Nonnegative
    cost_model_version: str = Field(min_length=1, max_length=100)
    max_entry_deviation_ticks: Nonnegative
    max_account_age_seconds: StrictInt = Field(ge=0, le=1800)
    max_setup_age_seconds: StrictInt = Field(ge=0, le=604800)
    max_selection_age_seconds: StrictInt = Field(ge=0, le=1800)
    max_risk_evidence_age_seconds: StrictInt = Field(ge=0, le=1800)
    max_consecutive_losses: StrictInt = Field(ge=1, le=5)
    max_drawdown_fraction: Annotated[Decimal, Field(gt=0, le=Decimal(".25"), allow_inf_nan=False)]


class StrategyRiskHistory(Evidence):
    account_id: str
    account_revision: Revision
    known_at: UTCDateTime
    source_reference: Reference
    strategy_id: str
    strategy_version: str
    consecutive_losses: StrictInt = Field(ge=0)
    peak_equity_usd: Price


class RiskInputs(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    known_at: UTCDateTime
    source_reference: Reference
    halted: StrictBool | None
    halted_at: UTCDateTime | None = None
    configuration: RiskConfiguration | None
    history: StrategyRiskHistory | None
    allowance: PolicyRiskAllowance | None

    @model_validator(mode="after")
    def knowledge(self) -> Self:
        if self.halted_at is not None and self.halted_at > self.known_at:
            raise ValueError("Risk revision cannot contain a future-known halt state")
        if any(row and row.known_at > self.known_at for row in (self.history, self.allowance)):
            raise ValueError("Risk input revision cannot contain future-known evidence")
        return self


class RiskDecision(Evidence):
    id: str
    generated_at: UTCDateTime
    algorithm_version: Literal[
        "structural-risk-v1", "role-scoped-structural-risk-v2", "registered-structural-risk-v3"
    ] = "structural-risk-v1"
    scope: Literal["structural_risk_check"] = "structural_risk_check"
    account_id: str
    journal_equity_usd: Number
    journal_revision: Revision
    journal_blocks: tuple[str, ...]
    setup: StructuralSetup
    selection_source: MarketSelection | None
    selection: MarketSelection | None
    account_state: AccountState
    risk_inputs: RiskInputs | None
    evaluation_policy: PolicyAssessment | None = None
    account_roles_required: StrictBool = False
    account_role_check: AccountRoleCheck | None = None
    strategy_registry_required: StrictBool = False
    strategy_approval_check: StrategyApprovalCheck | None = None
    state: Literal["QUALIFIED", "BLOCKED", "UNKNOWN"]
    reasons: tuple[str, ...]
    risk_qualified: StrictBool
    advice: Literal["WAIT", "NO TRADE"]
    allowed_contracts: StrictInt = Field(ge=0)
    stop_distance: Nonnegative
    percentage_budget_usd: Nonnegative | None
    risk_budget_usd: Nonnegative | None
    loss_per_contract_usd: Nonnegative | None
    estimated_loss_at_stop_usd: Nonnegative | None
    drawdown_fraction: Nonnegative | None
    correlated_exposure_ids: tuple[str, ...]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        registry_scope = self.strategy_registry_required or self.strategy_approval_check is not None
        role_scope = self.account_roles_required or self.account_role_check is not None
        expected_version = (
            "registered-structural-risk-v3"
            if registry_scope
            else "role-scoped-structural-risk-v2" if role_scope else "structural-risk-v1"
        )
        if self.algorithm_version != expected_version:
            raise ValueError(
                "Risk algorithm version must retain its account-role and registry scope"
            )
        if registry_scope and (
            self.strategy_approval_check is None
            or (
                self.strategy_approval_check.checked_at,
                self.strategy_approval_check.strategy_id,
                self.strategy_approval_check.strategy_version,
                self.strategy_approval_check.instrument_id,
            )
            != (
                self.generated_at,
                self.setup.strategy_id,
                self.setup.strategy_version,
                self.setup.instrument_id,
            )
        ):
            raise ValueError(
                "Registry-scoped risk must capture the exact strategy identity and clock"
            )
        qualified = self.state == "QUALIFIED"
        if self.risk_qualified != qualified or self.advice != ("WAIT" if qualified else "NO TRADE"):
            raise ValueError("Advice and risk qualification must match the decision state")
        if not qualified and self.allowed_contracts != 0:
            raise ValueError("Blocked or unknown risk cannot suggest a positive contract count")
        if qualified:
            if registry_scope:
                raise ValueError("Experimental registry records cannot qualify strategy risk")
            if (
                self.reasons
                or self.journal_blocks
                or (self.account_roles_required and self.account_role_check is None)
                or (
                    self.account_role_check is not None and self.account_role_check.state != "READY"
                )
                or self.allowed_contracts < 1
                or self.account_state.health != "KNOWN"
                or self.account_state.observation is None
                or self.account_state.observation.positions != ()
                or self.account_state.observation.working_orders != ()
                or self.selection is None
                or self.setup.instrument_id not in {self.selection.primary, self.selection.backup}
                or self.correlated_exposure_ids
                or self.risk_inputs is None
                or self.risk_inputs.configuration is None
                or self.risk_inputs.history is None
                or self.risk_inputs.halted is not False
                or self.risk_inputs.allowance is None
                or self.risk_inputs.allowance.state != "READY"
                or self.risk_inputs.allowance.maximum_contracts is None
                or self.percentage_budget_usd is None
                or self.risk_budget_usd is None
                or self.loss_per_contract_usd is None
                or self.estimated_loss_at_stop_usd is None
            ):
                raise ValueError("Qualified risk requires complete, known and unblocked evidence")
            if (
                self.estimated_loss_at_stop_usd
                != self.allowed_contracts * self.loss_per_contract_usd
                or not 0 < self.estimated_loss_at_stop_usd <= self.risk_budget_usd
                or self.risk_budget_usd > self.percentage_budget_usd
                or self.percentage_budget_usd > self.journal_equity_usd / 100
                or self.allowed_contracts > self.risk_inputs.allowance.maximum_contracts
            ):
                raise ValueError("Suggested contracts must stay within every risk budget and cap")
            expected = _sizing(
                self.setup,
                self.risk_inputs.configuration,
                self.risk_inputs.allowance,
                self.journal_equity_usd,
            )
            if (
                self.percentage_budget_usd,
                self.risk_budget_usd,
                self.loss_per_contract_usd,
                self.allowed_contracts,
            ) != expected:
                raise ValueError("Stored structural risk calculation does not match its inputs")
        return self


def _sizing(
    setup: StructuralSetup,
    configuration: RiskConfiguration,
    allowance: PolicyRiskAllowance,
    equity: Decimal,
) -> tuple[Decimal, Decimal, Decimal, int]:
    assert (
        allowance.daily_loss_remaining_usd is not None
        and allowance.drawdown_remaining_usd is not None
        and allowance.maximum_contracts is not None
    )
    result = risk_worksheet(
        RiskWorksheet(
            instrument_id=setup.instrument_id,
            account_value=equity,
            risk_percent=configuration.risk_percent,
            entry=setup.entry,
            stop=setup.invalidation,
            fees_per_unit=configuration.round_trip_fees_per_contract_usd,
            slippage_points=configuration.slippage_ticks * CATALOG[setup.instrument_id].tick_size,
        )
    )
    percentage = Decimal(result["risk_budget"])
    loss = Decimal(result["loss_per_unit"])
    budget = max(
        Decimal(0),
        min(
            percentage,
            allowance.daily_loss_remaining_usd - configuration.safety_buffer_usd,
            allowance.drawdown_remaining_usd - configuration.safety_buffer_usd,
        ),
    )
    return percentage, budget, loss, min(int(budget // loss), allowance.maximum_contracts)


def assess_risk(
    setup: StructuralSetup,
    selection: MarketSelection | None,
    observation: AccountObservation | None,
    *,
    account_id: str,
    journal_equity: Decimal,
    journal_revision: str,
    journal_blocks: tuple[str, ...],
    inputs: RiskInputs | None,
    now: datetime,
    evaluation_policy: PolicyAssessment | None = None,
    account_plan: AccountPlan | None = None,
    account_roles_required: bool = False,
    strategy_registry: StrategyRegistry | None = None,
    strategy_registry_required: bool = True,
) -> RiskDecision:
    """Structure -> invalidation -> distance -> available budget -> integer size.

    Only a complete flat account is currently sized. Correlated existing exposure
    blocks; other open exposure remains unknown until stop-risk is quantified.
    Neither opposite sides nor unfilled orders are assumed to release risk.
    """
    now = utc_instant(now)
    if not journal_equity.is_finite():
        raise ValueError("Journal equity must be finite")
    setup = StructuralSetup.model_validate(setup.model_dump())
    invalid: list[str] = []
    unknown: list[str] = []
    invalid.extend("journal_constraint:" + reason for reason in journal_blocks)
    if evaluation_policy is not None:
        evaluation_policy = PolicyAssessment.model_validate(evaluation_policy.model_dump())
        verify_policy_assessment(evaluation_policy)
        if (evaluation_policy.profile.id, evaluation_policy.account_revision) != (
            account_id,
            journal_revision,
        ):
            invalid.append("evaluation_policy_account_mismatch")
        if evaluation_policy.state == "BLOCKED":
            invalid.append("evaluation_policy_blocked")
        elif evaluation_policy.state == "UNKNOWN":
            unknown.append("evaluation_policy_unknown")
    if inputs is not None:
        try:
            inputs = RiskInputs.model_validate(inputs.model_dump(warnings=False))
        except (ValueError, TypeError, AttributeError):
            inputs = None
            invalid.append("invalid_risk_evidence")
    configuration = inputs.configuration if inputs else None
    if configuration is None:
        unknown.append("missing_risk_configuration")
    account = account_state(
        observation,
        account_id=account_id,
        journal_equity=journal_equity,
        now=now,
        max_age_seconds=configuration.max_account_age_seconds if configuration else 0,
    )
    if account.health == "INVALID":
        invalid.extend(account.reasons)
    elif account.health != "KNOWN":
        unknown.extend(account.reasons)
    if journal_equity <= 0:
        invalid.append("nonpositive_account_equity")
    fresh = None
    if selection is None:
        unknown.append("missing_market_selection")
    else:
        try:
            selection = MarketSelection.model_validate(selection.model_dump())
            policies = {
                row.event_risk.policy.model_dump_json()
                for row in selection.assessments
                if row.event_risk.policy
            }
            if len(policies) > 1:
                raise ValueError("Selection has conflicting event policies")
            fresh = select_markets(
                {row.instrument_id: row.market for row in selection.assessments},
                {row.instrument_id: row.evidence for row in selection.assessments},
                {row.instrument_id: row.event_risk.calendar for row in selection.assessments},
                interval=selection.interval,
                now=now,
                mode=selection.mode,
                policy=selection.policy,
                event_policy=next(
                    (
                        row.event_risk.policy
                        for row in selection.assessments
                        if row.event_risk.policy
                    ),
                    None,
                ),
            )
            if setup.instrument_id not in {fresh.primary, fresh.backup}:
                invalid.append("market_not_nominated")
            if (
                configuration is not None
                and not 0
                <= (now - selection.generated_at).total_seconds()
                <= configuration.max_selection_age_seconds
            ):
                invalid.append("stale_or_future_selection")
        except (ValueError, TypeError, AttributeError):
            selection = None
            invalid.append("invalid_market_selection")
    row = (
        next(
            (item for item in fresh.assessments if item.instrument_id == setup.instrument_id), None
        )
        if fresh
        else None
    )
    candidate = row.evidence if row else None
    strategy_check = None
    if strategy_registry_required or strategy_registry is not None:
        strategy_check = assess_strategy_approval(
            strategy_registry,
            strategy_id=setup.strategy_id,
            strategy_version=setup.strategy_version,
            instrument_id=setup.instrument_id,
            mode=(
                fresh.mode
                if fresh
                else (
                    "replay"
                    if account.observation and account.observation.source == "replay"
                    else "current"
                )
            ),
            now=now,
        )
        if strategy_check.state == "BLOCKED":
            invalid.extend(strategy_check.reasons)
        else:
            unknown.extend(strategy_check.reasons)
    role_check = None
    if account_roles_required or account_plan is not None:
        requested_configuration = None
        if configuration and candidate and candidate.edge and candidate.fit:
            edge, fit = candidate.edge, candidate.fit
            requested_configuration = AccountConfiguration(
                instrument_id=setup.instrument_id,
                strategy_id=setup.strategy_id,
                strategy_version=setup.strategy_version,
                risk_configuration_id=configuration.id,
                risk_configuration_version=configuration.version,
                evaluation_policy_id=fit.evaluation_policy_id,
                evaluation_policy_version=fit.evaluation_policy_version,
                cost_model_version=configuration.cost_model_version,
                edge_id=edge.id,
                edge_version=edge.version,
                fit_id=fit.id,
                fit_version=fit.version,
                dataset_sha256=edge.dataset_sha256,
            )
        role_check = assess_account_role(
            account_plan,
            account_id=account_id,
            requested_configuration=requested_configuration,
            mode=(
                fresh.mode
                if fresh
                else (
                    "replay"
                    if account.observation and account.observation.source == "replay"
                    else "current"
                )
            ),
            now=now,
        )
        if role_check.state == "BLOCKED":
            invalid.extend(role_check.reasons)
        elif role_check.state == "UNKNOWN":
            unknown.extend(role_check.reasons)
    if (
        fresh
        and account.observation
        and ((account.observation.source == "replay") != (fresh.mode == "replay"))
    ):
        invalid.append("replay_current_account_mismatch")
    if row and setup.contract != row.contract:
        invalid.append("setup_contract_mismatch")
    instrument = CATALOG[setup.instrument_id]
    if setup.entry % instrument.tick_size or setup.invalidation % instrument.tick_size:
        invalid.append("off_tick_structure")
    if (setup.side == "BUY" and setup.invalidation >= setup.entry) or (
        setup.side == "SELL" and setup.invalidation <= setup.entry
    ):
        invalid.append("invalid_invalidation_direction")
    correlated = []
    if account.observation is not None:
        positions, orders = account.observation.positions, account.observation.working_orders
        spec = instrument.futures_spec
        assert spec is not None
        holdings: tuple[OpenPosition | WorkingOrder, ...] = (*(positions or ()), *(orders or ()))
        for holding in holdings:
            item = CATALOG.get(holding.instrument_id)
            if (
                item is None
                or item.futures_spec is None
                or not item.valid_contract(holding.contract)
            ):
                unknown.append("unknown_open_exposure")
            elif item.futures_spec.exposure_group == spec.exposure_group:
                correlated.append(
                    "position:" + holding.position_id
                    if isinstance(holding, OpenPosition)
                    else "order:" + holding.order_id
                )
                invalid.append("correlated_open_exposure")
            else:
                unknown.append("unquantified_open_exposure")
    drawdown = None
    if inputs is None:
        unknown.append("missing_risk_inputs")
    else:
        if inputs.halted is None:
            unknown.append("unknown_halt_state")
        elif inputs.halted:
            invalid.append("risk_halted")
        if configuration is not None:
            for name, stamp, age_limit in (
                ("setup", setup.known_at, configuration.max_setup_age_seconds),
                ("risk_inputs", inputs.known_at, configuration.max_risk_evidence_age_seconds),
                (
                    "halt_state",
                    inputs.halted_at or inputs.known_at,
                    configuration.max_risk_evidence_age_seconds,
                ),
            ):
                if not 0 <= (now - stamp).total_seconds() <= age_limit:
                    invalid.append("stale_or_future_" + name)
            history, allowance = inputs.history, inputs.allowance
            if history is None:
                unknown.append("missing_strategy_loss_history")
            else:
                if (
                    history.account_id,
                    history.account_revision,
                    history.strategy_id,
                    history.strategy_version,
                ) != (account_id, journal_revision, setup.strategy_id, setup.strategy_version):
                    invalid.append("strategy_history_identity_mismatch")
                if (
                    not 0
                    <= (now - history.known_at).total_seconds()
                    <= configuration.max_risk_evidence_age_seconds
                ):
                    invalid.append("stale_or_future_strategy_history")
                if history.consecutive_losses >= configuration.max_consecutive_losses:
                    invalid.append("consecutive_loss_pause")
                if history.peak_equity_usd < journal_equity:
                    invalid.append("invalid_peak_equity")
                else:
                    drawdown = max(
                        Decimal(0),
                        (history.peak_equity_usd - journal_equity) / history.peak_equity_usd,
                    )
                    if (
                        history.peak_equity_usd - journal_equity
                        >= history.peak_equity_usd * configuration.max_drawdown_fraction
                    ):
                        invalid.append("portfolio_drawdown_limit")
            if allowance is None:
                unknown.append("missing_policy_allowance")
            else:
                if allowance.state == "BLOCKED":
                    invalid.append("policy_blocked")
                elif allowance.state == "UNKNOWN":
                    unknown.append("policy_unknown")
                if (
                    allowance.account_id,
                    allowance.account_revision,
                    allowance.instrument_id,
                    allowance.contract,
                    allowance.at_invalidation,
                ) != (
                    account_id,
                    journal_revision,
                    setup.instrument_id,
                    setup.contract,
                    setup.invalidation,
                ):
                    invalid.append("policy_allowance_identity_mismatch")
                if (
                    not 0
                    <= (now - allowance.known_at).total_seconds()
                    <= configuration.max_risk_evidence_age_seconds
                ):
                    invalid.append("stale_or_future_policy_allowance")
                if (
                    fresh
                    and fresh.policy
                    and (allowance.policy_id, allowance.policy_version)
                    != (fresh.policy.evaluation_policy_id, fresh.policy.evaluation_policy_version)
                ):
                    invalid.append("policy_version_mismatch")
            if candidate is None or candidate.edge is None or candidate.measurement is None:
                unknown.append("missing_selected_strategy_evidence")
            else:
                edge, measurement = candidate.edge, candidate.measurement
                if (
                    setup.strategy_id,
                    setup.strategy_version,
                    configuration.id,
                    configuration.risk_percent,
                ) != (
                    edge.strategy_id,
                    edge.strategy_version,
                    edge.risk_configuration_id,
                    edge.risk_percent,
                ):
                    invalid.append("strategy_risk_configuration_mismatch")
                if configuration.cost_model_version != edge.cost_model_version:
                    invalid.append("risk_cost_model_mismatch")
                if configuration.slippage_ticks < max(
                    edge.assumed_slippage_ticks, measurement.slippage_ticks
                ):
                    invalid.append("understated_slippage")
                quote = measurement.quote
                book = quote.ask if setup.side == "BUY" else quote.bid
                if book is None:
                    unknown.append("missing_entry_quote")
                elif (
                    abs(setup.entry - book) / instrument.tick_size
                    > configuration.max_entry_deviation_ticks
                ):
                    invalid.append("entry_outside_tolerance")
    percentage_budget = budget = loss = estimated = None
    size = 0
    if not invalid and not unknown:
        assert configuration is not None and inputs is not None and inputs.allowance is not None
        percentage_budget, budget, loss, size = _sizing(
            setup, configuration, inputs.allowance, journal_equity
        )
        if size < 1:
            invalid.append("structural_risk_does_not_fit")
        else:
            estimated = size * loss
    state: Literal["QUALIFIED", "BLOCKED", "UNKNOWN"] = (
        "BLOCKED" if invalid else "UNKNOWN" if unknown else "QUALIFIED"
    )
    return RiskDecision(
        algorithm_version=(
            "registered-structural-risk-v3"
            if strategy_check is not None
            else (
                "role-scoped-structural-risk-v2" if role_check is not None else "structural-risk-v1"
            )
        ),
        id=str(uuid4()),
        generated_at=now,
        account_id=account_id,
        journal_equity_usd=journal_equity,
        journal_revision=journal_revision,
        journal_blocks=journal_blocks,
        setup=setup,
        selection_source=selection,
        selection=fresh,
        account_state=account,
        risk_inputs=inputs,
        evaluation_policy=evaluation_policy,
        account_roles_required=account_roles_required,
        account_role_check=role_check,
        strategy_registry_required=strategy_registry_required,
        strategy_approval_check=strategy_check,
        state=state,
        reasons=tuple(sorted(set(invalid + unknown))),
        risk_qualified=state == "QUALIFIED",
        advice="WAIT" if state == "QUALIFIED" else "NO TRADE",
        allowed_contracts=size if state == "QUALIFIED" else 0,
        stop_distance=abs(setup.entry - setup.invalidation),
        percentage_budget_usd=percentage_budget,
        risk_budget_usd=budget,
        loss_per_contract_usd=loss,
        estimated_loss_at_stop_usd=estimated,
        drawdown_fraction=drawdown,
        correlated_exposure_ids=tuple(sorted(correlated)),
    )


class RiskRequest(Evidence):
    selection_id: str | None = Field(default=None, min_length=1, max_length=100)
    setup: StructuralSetup


def verify_qualified_record(value: RiskDecision) -> None:
    """Re-run all gates for a positive saved check at its original clock."""
    if not value.risk_qualified:
        return
    if value.evaluation_policy is not None:
        verify_policy_assessment(value.evaluation_policy)
    expected = assess_risk(
        value.setup,
        value.selection_source,
        value.account_state.observation,
        account_id=value.account_id,
        journal_equity=value.journal_equity_usd,
        journal_revision=value.journal_revision,
        journal_blocks=value.journal_blocks,
        inputs=value.risk_inputs,
        now=value.generated_at,
        evaluation_policy=value.evaluation_policy,
        account_plan=value.account_role_check.plan if value.account_role_check else None,
        account_roles_required=value.account_roles_required,
        strategy_registry_required=value.strategy_registry_required,
    )
    actual_fields = value.model_dump(exclude={"id"})
    expected_fields = expected.model_dump(exclude={"id"})
    # Re-assessment IDs carry no financial meaning; every input, gate,
    # amount, outcome and clock must still reproduce exactly.
    if actual_fields["selection"] is not None:
        actual_fields["selection"].pop("id")
    if expected_fields["selection"] is not None:
        expected_fields["selection"].pop("id")
    if actual_fields != expected_fields:
        raise ValueError("Stored qualified risk decision does not reproduce from its evidence")
