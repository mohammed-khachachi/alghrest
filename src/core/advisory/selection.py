"""Guarded futures research nominations, never entry or execution permission.

Evidence is supplied by a server-owned research record reader. These contracts
validate reported facts; they do not authenticate approval or compute edge/fit.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import ConfigDict, Field, StrictBool, StrictInt, model_validator

from core.advisory.analysis import average_true_range
from core.advisory.events import assess_event_risk
from core.advisory.health import DataHealthPolicy, assess_market_data
from core.advisory.models import (
    CATALOG,
    INTERVAL_SECONDS,
    EconomicCalendar,
    EventRiskAssessment,
    EventRiskPolicy,
    Interval,
    MarketDataHealth,
    MarketSnapshot,
    Number,
    Price,
    PriceObservation,
    Strict,
    UTCDateTime,
    utc_instant,
)
from core.data.models import MarketRegime

Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
Probability = Annotated[Decimal, Field(ge=0, le=1, allow_inf_nan=False)]


class Evidence(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


def future_root(root: str) -> str:
    instrument = CATALOG.get(root)
    if instrument is None or instrument.futures_spec is None:
        raise ValueError("Selection requires a catalog futures market")
    return root


class LosingStreakEstimate(Evidence):
    horizon_trades: Literal[10, 25, 50, 100]
    # 5 means five or more consecutive losses somewhere in the horizon.
    loss_run: Literal[2, 3, 4, 5]
    probability: Probability


class TradingEdgeEvidence(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    instrument_id: str
    strategy_id: str = Field(min_length=1, max_length=100)
    strategy_version: str = Field(min_length=1, max_length=100)
    risk_configuration_id: str = Field(min_length=1, max_length=100)
    risk_percent: Annotated[Decimal, Field(gt=0, le=1, allow_inf_nan=False)]
    origin: Literal["historical", "synthetic"]
    source_reference: str = Field(min_length=1, max_length=500)
    dataset_id: str = Field(min_length=1, max_length=100)
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    available_at: UTCDateTime
    train_start: UTCDateTime
    train_end: UTCDateTime
    validation_start: UTCDateTime
    validation_end: UTCDateTime
    oos_start: UTCDateTime
    oos_end: UTCDateTime
    lifecycle: Literal["EXPERIMENT", "BACKTESTED", "VALIDATED", "SHADOW", "APPROVED", "RETIRED"]
    supported_regimes: tuple[MarketRegime, ...] = Field(min_length=1)
    costs_included: StrictBool
    walk_forward_verified: StrictBool
    final_holdout_untuned: StrictBool
    cost_model_version: str = Field(min_length=1, max_length=100)
    assumed_slippage_ticks: Nonnegative
    oos_trades: StrictInt = Field(ge=0)
    expectancy_r: Number
    confidence_level: Annotated[Decimal, Field(gt=0, lt=1, allow_inf_nan=False)]
    expectancy_lower_bound_r: Number
    median_r: Number
    variance_r_squared: Nonnegative
    cvar95_loss_r: Nonnegative
    max_drawdown_fraction: Probability
    losing_streaks: tuple[LosingStreakEstimate, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        future_root(self.instrument_id)
        if not (
            self.train_start
            < self.train_end
            < self.validation_start
            < self.validation_end
            < self.oos_start
            < self.oos_end
            <= self.available_at
        ):
            raise ValueError("Train, validation and OOS periods must be chronological and disjoint")
        if self.expectancy_lower_bound_r > self.expectancy_r:
            raise ValueError("Expectancy lower bound cannot exceed the point estimate")
        if len(set(self.supported_regimes)) != len(self.supported_regimes):
            raise ValueError("Supported regimes must be distinct")
        keys = [(row.horizon_trades, row.loss_run) for row in self.losing_streaks]
        if len(set(keys)) != len(keys):
            raise ValueError("Duplicate losing-streak estimate")
        return self


class EvaluationFitEvidence(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    edge_id: str
    edge_version: str
    available_at: UTCDateTime
    source_reference: str = Field(min_length=1, max_length=500)
    evaluation_policy_id: str = Field(min_length=1, max_length=100)
    evaluation_policy_version: str = Field(min_length=1, max_length=100)
    cost_model_version: str = Field(min_length=1, max_length=100)
    simulator_version: str = Field(min_length=1, max_length=100)
    seed: StrictInt = Field(ge=0)
    horizon_trades: StrictInt = Field(ge=1)
    horizon_days: StrictInt = Field(ge=1)
    simulations: StrictInt = Field(ge=1)
    passed: StrictInt = Field(ge=0)
    failed: StrictInt = Field(ge=0)
    censored: StrictInt = Field(ge=0)
    rule_exact_verified: StrictBool
    dependence_preserved: StrictBool
    costs_included: StrictBool
    pass_probability_lower_bound: Probability
    confidence_level: Annotated[Decimal, Field(gt=0, lt=1, allow_inf_nan=False)]
    failure_probability_upper_bound: Probability
    daily_loss_breach_probability: Probability
    drawdown_breach_probability: Probability
    progression_breach_probability: Probability
    median_days_to_pass: Price | None
    p95_days_to_pass: Price | None
    expected_evaluation_cost_usd: Nonnegative

    @property
    def pass_probability(self) -> Decimal:
        return Decimal(self.passed) / self.simulations

    @property
    def failure_probability(self) -> Decimal:
        return Decimal(self.failed) / self.simulations

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.passed + self.failed + self.censored != self.simulations:
            raise ValueError("Every simulation must be passed, failed or censored")
        if (
            self.pass_probability_lower_bound > self.pass_probability
            or self.failure_probability_upper_bound < self.failure_probability
        ):
            raise ValueError("Probability bounds must enclose empirical trial fractions")
        if self.passed == 0:
            if self.median_days_to_pass is not None or self.p95_days_to_pass is not None:
                raise ValueError("No-pass trials have no conditional pass-time percentiles")
        elif self.median_days_to_pass is None or self.p95_days_to_pass is None:
            raise ValueError("Successful trials require pass-time percentiles")
        elif (
            self.median_days_to_pass > self.p95_days_to_pass
            or self.p95_days_to_pass > self.horizon_days
        ):
            raise ValueError("Pass-time percentiles must be ordered within the simulation horizon")
        if (
            max(
                self.daily_loss_breach_probability,
                self.drawdown_breach_probability,
                self.progression_breach_probability,
            )
            > self.failure_probability
        ):
            raise ValueError("Rule-breach probabilities cannot exceed total failure probability")
        return self


class MarketMeasurement(Evidence):
    known_at: UTCDateTime
    source_reference: str = Field(min_length=1, max_length=500)
    quote: PriceObservation
    slippage_ticks: Nonnegative
    regime: MarketRegime | None
    regime_version: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def timestamp(self) -> Self:
        if self.quote.timestamp > self.known_at:
            raise ValueError("Measurement cannot contain a future-known quote")
        return self


class CandidateEvidence(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    available_at: UTCDateTime
    instrument_id: str
    measurement: MarketMeasurement | None = None
    edge: TradingEdgeEvidence | None = None
    fit: EvaluationFitEvidence | None = None
    # Reported eligibility is separate from catalog membership and API entitlement.
    eligibility_confirmed: StrictBool = False
    eligibility_reference: str | None = None

    @model_validator(mode="after")
    def identity(self) -> Self:
        future_root(self.instrument_id)
        if self.edge is not None and self.edge.instrument_id != self.instrument_id:
            raise ValueError("Trading-edge market must match the candidate")
        if self.fit is not None and (
            self.edge is None
            or (self.fit.edge_id, self.fit.edge_version) != (self.edge.id, self.edge.version)
        ):
            raise ValueError("Evaluation fit must reference the exact trading-edge revision")
        if any(
            stamp > self.available_at
            for stamp in (
                self.measurement.known_at if self.measurement else self.available_at,
                self.edge.available_at if self.edge else self.available_at,
                self.fit.available_at if self.fit else self.available_at,
            )
        ):
            raise ValueError("Candidate revision cannot contain future-known evidence")
        return self


class MarketLimits(Evidence):
    instrument_id: str
    min_liquidity_contracts_per_minute: Price
    max_spread_ticks: Nonnegative
    max_slippage_ticks: Nonnegative
    min_atr_ticks: Price
    max_atr_ticks: Price
    max_quote_age_seconds: StrictInt = Field(ge=0, le=604800)
    max_measurement_age_seconds: StrictInt = Field(ge=0, le=604800)
    max_source_deviation_ticks: Nonnegative | None = None

    @model_validator(mode="after")
    def coherent(self) -> Self:
        future_root(self.instrument_id)
        if self.max_atr_ticks < self.min_atr_ticks:
            raise ValueError("Volatility limits must be ordered")
        return self


class MarketSelectionPolicy(Evidence):
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    universe: tuple[str, ...] = Field(min_length=1, max_length=20)
    market_limits: tuple[MarketLimits, ...]
    evaluation_policy_id: str
    evaluation_policy_version: str
    cost_model_version: str
    simulator_version: str
    confidence_level: Annotated[Decimal, Field(gt=0, lt=1, allow_inf_nan=False)]
    simulation_horizon_trades: StrictInt = Field(ge=1)
    simulation_horizon_days: StrictInt = Field(ge=1)
    minimum_oos_trades: StrictInt = Field(ge=1)
    minimum_simulations: StrictInt = Field(ge=1)
    liquidity_lookback_bars: StrictInt = Field(ge=1, le=500)
    max_research_age_seconds: StrictInt = Field(ge=0, le=31536000)
    max_failure_probability: Probability
    max_drawdown_fraction: Annotated[Decimal, Field(gt=0, le=Decimal("0.25"), allow_inf_nan=False)]
    max_cvar95_loss_r: Nonnegative
    max_variance_r_squared: Nonnegative
    max_five_loss_probability_100: Probability
    max_evaluation_cost_usd: Nonnegative
    backup_mode: Literal["distinct_exposure_group", "alternative_with_warning"]

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if len(set(self.universe)) != len(self.universe):
            raise ValueError("Selection universe must be distinct")
        for root in self.universe:
            future_root(root)
        limits = [row.instrument_id for row in self.market_limits]
        if len(set(limits)) != len(limits) or not set(limits) <= set(self.universe):
            raise ValueError("Market limits must be unique members of the universe")
        return self


class MarketAssessment(Evidence):
    instrument_id: str
    contract: str | None
    eligible: StrictBool
    reasons: tuple[str, ...]
    data_health: MarketDataHealth
    event_risk: EventRiskAssessment
    market: MarketSnapshot | None
    evidence: CandidateEvidence | None
    liquidity_contracts_per_minute: Number | None = None
    atr_ticks: Number | None = None
    spread_ticks: Number | None = None
    exposure_group: str

    @model_validator(mode="after")
    def identity(self) -> Self:
        future_root(self.instrument_id)
        spec = CATALOG[self.instrument_id].futures_spec
        assert spec is not None
        if self.exposure_group != spec.exposure_group:
            raise ValueError("Assessment exposure group must match the catalog")
        if self.contract != (self.market.contract if self.market else None):
            raise ValueError("Assessment contract identity mismatch")
        if self.market is not None and self.market.instrument_id != self.instrument_id:
            raise ValueError("Assessment market identity mismatch")
        if self.evidence is not None and self.evidence.instrument_id != self.instrument_id:
            raise ValueError("Assessment research identity mismatch")
        if self.eligible and (
            self.reasons
            or self.data_health.state != "HEALTHY"
            or self.event_risk.state != "CLEAR"
            or self.market is None
            or self.evidence is None
            or self.evidence.edge is None
            or self.evidence.fit is None
        ):
            raise ValueError("Eligible assessment cannot contain blocked or missing evidence")
        return self


class MarketSelection(Evidence):
    id: str
    generated_at: UTCDateTime
    interval: Interval
    mode: Literal["current", "replay"]
    algorithm_version: Literal["guarded-selection-v1"] = "guarded-selection-v1"
    scope: Literal["research_nomination"] = "research_nomination"
    primary: str | None
    backup: str | None
    ranked: tuple[str, ...]
    assessments: tuple[MarketAssessment, ...]
    policy: MarketSelectionPolicy | None
    reasons: tuple[str, ...]
    trade_permitted: Literal[False] = False
    simultaneous_use_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> Self:
        roots = [row.instrument_id for row in self.assessments]
        eligible = {row.instrument_id for row in self.assessments if row.eligible}
        if (
            len(set(roots)) != len(roots)
            or len(set(self.ranked)) != len(self.ranked)
            or set(self.ranked) != eligible
        ):
            raise ValueError("Selection rankings must contain each eligible market exactly once")
        if self.primary != (self.ranked[0] if self.ranked else None):
            raise ValueError("Primary must be the highest ranked qualified market")
        if self.backup is not None and (
            self.backup == self.primary or self.backup not in self.ranked
        ):
            raise ValueError("Backup must be a distinct qualified alternative")
        if self.policy is None and self.ranked:
            raise ValueError("Selection requires an explicit policy")
        if self.policy is not None and set(roots) != set(self.policy.universe):
            raise ValueError("Every configured market must have an assessment")
        if self.backup is not None and self.policy is not None:
            assert self.primary is not None
            groups = {row.instrument_id: row.exposure_group for row in self.assessments}
            if (
                self.policy.backup_mode == "distinct_exposure_group"
                and groups[self.backup] == groups[self.primary]
            ):
                raise ValueError("Backup exposure violates the selection policy")
        return self


def select_markets(
    snapshots: dict[str, MarketSnapshot | None],
    evidence: dict[str, CandidateEvidence | None],
    calendars: dict[str, EconomicCalendar | None],
    *,
    interval: Interval,
    now: datetime,
    mode: Literal["current", "replay"],
    policy: MarketSelectionPolicy | None,
    event_policy: EventRiskPolicy | None,
) -> MarketSelection:
    now = utc_instant(now)
    if mode not in {"current", "replay"}:
        raise ValueError("Unknown selection mode")
    policy = (
        MarketSelectionPolicy.model_validate(policy.model_dump()) if policy is not None else None
    )
    universe = (
        policy.universe
        if policy is not None
        else tuple(
            root
            for root, item in CATALOG.items()
            if item.futures_spec and item.futures_spec.research_tier == 1
        )
    )
    assessments = []
    for root in universe:
        limits = (
            next((row for row in policy.market_limits if row.instrument_id == root), None)
            if policy
            else None
        )
        value = evidence.get(root)
        reasons = []
        if value is not None:
            try:
                value = CandidateEvidence.model_validate(value.model_dump())
                if value.instrument_id != root:
                    raise ValueError("Candidate identity mismatch")
            except (ValueError, TypeError, AttributeError):
                value = None
                reasons.append("invalid_research_evidence")
        market = snapshots.get(root)
        if market is not None:
            try:
                market = MarketSnapshot.model_validate(market.model_dump())
                if market.instrument_id != root or market.interval != interval:
                    raise ValueError("Market identity mismatch")
                if (market.data_mode == "replay") != (mode == "replay"):
                    raise ValueError("Selection mode and market provenance disagree")
            except (ValueError, TypeError, AttributeError):
                market = None
                reasons.append("invalid_selection_market")
        if (
            market is not None
            and value is not None
            and value.measurement is not None
            and market.quality is not None
        ):
            # Keep source heartbeat/sequence faults. A separately reported quote
            # can enrich a bar archive, never replace conflicting source quotes.
            quote = value.measurement.quote
            if market.quality.quote is not None and market.quality.quote != quote:
                reasons.append("conflicting_selection_quote")
            else:
                market.quality = market.quality.model_copy(update={"quote": quote})
        health_policy = DataHealthPolicy(
            require_quote=True,
            max_quote_age_seconds=Decimal(limits.max_quote_age_seconds) if limits else None,
            max_spread_ticks=limits.max_spread_ticks if limits else None,
            max_source_deviation_ticks=limits.max_source_deviation_ticks if limits else None,
        )
        health = assess_market_data(market, root, interval, now=now, policy=health_policy)
        events = assess_event_risk(calendars.get(root), event_policy, root, now=now)
        if health.state != "HEALTHY":
            reasons.append("data_health:" + health.state)
        if events.state != "CLEAR":
            reasons.append("event_risk:" + events.state)
        if policy is None:
            reasons.append("missing_selection_policy")
        if limits is None:
            reasons.append("missing_market_limits")
        liquidity = atr_ticks = spread = None
        if (
            market is not None
            and health.state == "HEALTHY"
            and limits is not None
            and policy is not None
        ):
            atr = average_true_range(market.candles)
            if atr is None or len(market.candles) < policy.liquidity_lookback_bars:
                reasons.append("insufficient_selection_bars")
            else:
                liquidity = sum(
                    (bar.volume for bar in market.candles[-policy.liquidity_lookback_bars :]),
                    Decimal(0),
                ) / (Decimal(INTERVAL_SECONDS[interval]) * policy.liquidity_lookback_bars / 60)
                atr_ticks = atr / CATALOG[root].tick_size
                if liquidity < limits.min_liquidity_contracts_per_minute:
                    reasons.append("insufficient_liquidity")
                if not limits.min_atr_ticks <= atr_ticks <= limits.max_atr_ticks:
                    reasons.append("volatility_outside_limits")
                assert market.quality is not None and market.quality.quote is not None
                quote = market.quality.quote
                assert quote.bid is not None and quote.ask is not None
                spread = (quote.ask - quote.bid) / CATALOG[root].tick_size
        if value is None:
            reasons.append("missing_research_evidence")
        else:
            if value.available_at > now:
                reasons.append("future_candidate_revision")
            if not value.eligibility_confirmed or not value.eligibility_reference:
                reasons.append("unconfirmed_market_eligibility")
            measurement, edge, fit = value.measurement, value.edge, value.fit
            if measurement is None:
                reasons.append("missing_market_measurement")
            elif limits is not None:
                age = (now - measurement.known_at).total_seconds()
                if not 0 <= age <= limits.max_measurement_age_seconds:
                    reasons.append("stale_or_future_measurement")
                if measurement.regime is None:
                    reasons.append("unknown_regime")
                if measurement.slippage_ticks > limits.max_slippage_ticks:
                    reasons.append("excessive_slippage")
            if edge is None:
                reasons.append("missing_trading_edge")
            elif policy is not None:
                if edge.lifecycle != "APPROVED":
                    reasons.append("strategy_not_approved")
                if mode == "current" and edge.origin == "synthetic":
                    reasons.append("synthetic_current_evidence")
                if (
                    not 0
                    <= (now - edge.available_at).total_seconds()
                    <= policy.max_research_age_seconds
                ):
                    reasons.append("stale_or_future_edge")
                if not (
                    edge.costs_included
                    and edge.walk_forward_verified
                    and edge.final_holdout_untuned
                ):
                    reasons.append("unverified_edge_validation")
                if edge.oos_trades < policy.minimum_oos_trades:
                    reasons.append("insufficient_oos_trades")
                if edge.expectancy_lower_bound_r <= 0:
                    reasons.append("nonpositive_oos_edge")
                if edge.cost_model_version != policy.cost_model_version:
                    reasons.append("cost_model_mismatch")
                if edge.confidence_level != policy.confidence_level:
                    reasons.append("confidence_level_mismatch")
                if edge.max_drawdown_fraction >= policy.max_drawdown_fraction:
                    reasons.append("drawdown_limit")
                if edge.cvar95_loss_r > policy.max_cvar95_loss_r:
                    reasons.append("tail_risk_limit")
                if edge.variance_r_squared > policy.max_variance_r_squared:
                    reasons.append("variance_limit")
                required = {(h, r) for h in (10, 25, 50, 100) for r in (2, 3, 4, 5)}
                if {(row.horizon_trades, row.loss_run) for row in edge.losing_streaks} != required:
                    reasons.append("incomplete_losing_streak_evidence")
                elif (
                    next(
                        row.probability
                        for row in edge.losing_streaks
                        if row.horizon_trades == 100 and row.loss_run == 5
                    )
                    > policy.max_five_loss_probability_100
                ):
                    reasons.append("losing_streak_limit")
                if measurement is not None:
                    if measurement.regime not in edge.supported_regimes:
                        reasons.append("regime_incompatible")
                    if measurement.slippage_ticks > edge.assumed_slippage_ticks:
                        reasons.append("optimistic_slippage_assumption")
            if fit is None:
                reasons.append("missing_evaluation_fit")
            elif policy is not None:
                if (
                    not 0
                    <= (now - fit.available_at).total_seconds()
                    <= policy.max_research_age_seconds
                ):
                    reasons.append("stale_or_future_fit")
                if not (
                    fit.rule_exact_verified and fit.dependence_preserved and fit.costs_included
                ):
                    reasons.append("unverified_evaluation_fit")
                if (
                    fit.evaluation_policy_id,
                    fit.evaluation_policy_version,
                    fit.cost_model_version,
                    fit.horizon_trades,
                    fit.horizon_days,
                ) != (
                    policy.evaluation_policy_id,
                    policy.evaluation_policy_version,
                    policy.cost_model_version,
                    policy.simulation_horizon_trades,
                    policy.simulation_horizon_days,
                ):
                    reasons.append("incomparable_evaluation_fit")
                if fit.simulations < policy.minimum_simulations:
                    reasons.append("insufficient_simulations")
                if fit.passed == 0:
                    reasons.append("no_simulated_passes")
                if (
                    fit.confidence_level != policy.confidence_level
                    or fit.simulator_version != policy.simulator_version
                ):
                    reasons.append("incomparable_simulation_method")
                if fit.failure_probability_upper_bound > policy.max_failure_probability:
                    reasons.append("failure_probability_limit")
                if fit.expected_evaluation_cost_usd > policy.max_evaluation_cost_usd:
                    reasons.append("evaluation_cost_limit")
        spec = CATALOG[root].futures_spec
        assert spec is not None
        assessments.append(
            MarketAssessment(
                instrument_id=root,
                contract=market.contract if market else None,
                eligible=not reasons,
                reasons=tuple(sorted(set(reasons))),
                data_health=health,
                event_risk=events,
                market=market,
                evidence=value,
                liquidity_contracts_per_minute=liquidity,
                atr_ticks=atr_ticks,
                spread_ticks=spread,
                exposure_group=spec.exposure_group,
            )
        )

    def rank(row: MarketAssessment) -> tuple[Decimal | str, ...]:
        assert (
            row.evidence is not None
            and row.evidence.edge is not None
            and row.evidence.fit is not None
        )
        edge, fit = row.evidence.edge, row.evidence.fit
        streak = next(
            r.probability
            for r in edge.losing_streaks
            if r.horizon_trades == 100 and r.loss_run == 5
        )
        assert row.spread_ticks is not None and row.liquidity_contracts_per_minute is not None
        assert fit.median_days_to_pass is not None and fit.p95_days_to_pass is not None
        return (
            -fit.pass_probability_lower_bound,
            fit.failure_probability_upper_bound,
            fit.expected_evaluation_cost_usd,
            fit.p95_days_to_pass,
            fit.median_days_to_pass,
            -edge.expectancy_lower_bound_r,
            edge.cvar95_loss_r,
            streak,
            edge.variance_r_squared,
            row.spread_ticks,
            -row.liquidity_contracts_per_minute,
            row.instrument_id,
        )

    ranked = sorted((row for row in assessments if row.eligible), key=rank)
    primary = ranked[0] if ranked else None
    backup = (
        next(
            (
                row
                for row in ranked[1:]
                if policy is not None
                and (
                    policy.backup_mode == "alternative_with_warning"
                    or row.exposure_group != primary.exposure_group
                )
            ),
            None,
        )
        if primary
        else None
    )
    reasons = [] if primary else ["no_qualified_market"]
    if primary and backup and primary.exposure_group == backup.exposure_group:
        reasons.append("correlated_backup_alternative_only")
    return MarketSelection(
        id=str(uuid4()),
        generated_at=now,
        interval=interval,
        mode=mode,
        primary=primary.instrument_id if primary else None,
        backup=backup.instrument_id if backup else None,
        ranked=tuple(row.instrument_id for row in ranked),
        assessments=tuple(assessments),
        policy=policy,
        reasons=tuple(reasons),
    )
