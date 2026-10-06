"""Experimental paired-mean uncertainty and fixed-rule chronological research.

Percentile bounds describe a chosen block resampling model, not calibrated
coverage, approval, real account returns or TCP25 pass probability. Full source
replay is mandatory. Final holdout prices do not enter fold calculations.
"""

import hashlib
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Annotated, Literal, Self

import numpy as np
from pydantic import Field, StrictInt, model_validator

from backtesting.futures import (
    FuturesEdgeStudy,
    FuturesResearchInput,
    _sha,
    futures_dataset_digest,
    futures_edge_analysis,
    run_futures_research,
    verify_futures_edge_study,
)
from backtesting.path_risk import LossStreakConfig, paired_block_bootstrap_means
from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.models import Number
from core.advisory.selection import Evidence, Nonnegative
from core.advisory.strategies import Digest, Identity, ResearchPartition, StrategyResearchPlan


class MeanBootstrapConfig(Evidence):
    sampling: LossStreakConfig
    confidence_level: Annotated[Decimal, Field(gt=0, lt=1, allow_inf_nan=False)]
    minimum_observations: StrictInt = Field(ge=2, le=10000)
    method: Literal["paired-noncircular-block-percentile-v1"] = (
        "paired-noncircular-block-percentile-v1"
    )
    quantiles: Literal["linear-(m-1)p"] = "linear-(m-1)p"

    @model_validator(mode="after")
    def simulations(self) -> Self:
        if self.sampling.simulations < 2:
            raise ValueError("Mean uncertainty requires at least two resamples")
        return self


class MeanInterval(Evidence):
    state: Literal["CALCULATED", "UNKNOWN"]
    reasons: tuple[str, ...]
    observations: StrictInt = Field(ge=0)
    empirical_mean: Number | None
    lower: Number | None
    upper: Number | None
    bootstrap_standard_deviation: Nonnegative | None
    distribution_sha256: Digest | None


class PartitionUncertainty(Evidence):
    role: Literal["TRAIN", "VALIDATION", "OOS"]
    mean_r: MeanInterval
    mean_usd: MeanInterval


def _percentile(values: tuple[Decimal, ...], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    rank = Decimal(len(ordered) - 1) * probability
    left = int(rank)
    fraction = rank - left
    return (
        ordered[left]
        if fraction == 0
        else ordered[left] + fraction * (ordered[left + 1] - ordered[left])
    )


def _mean_interval(
    means: tuple[Decimal, ...], point: Decimal, n: int, config: MeanBootstrapConfig
) -> MeanInterval:
    digest = _sha([str(v) for v in means])
    if min(means) == max(means):
        return MeanInterval(
            state="UNKNOWN",
            reasons=("degenerate_bootstrap_distribution",),
            observations=n,
            empirical_mean=point,
            lower=None,
            upper=None,
            bootstrap_standard_deviation=Decimal(0),
            distribution_sha256=digest,
        )
    average = sum(means, Decimal(0)) / len(means)
    variance = sum(((v - average) ** 2 for v in means), Decimal(0)) / (len(means) - 1)
    tail = (1 - config.confidence_level) / 2
    lower, upper = _percentile(means, tail), _percentile(means, 1 - tail)
    if lower == upper:
        return MeanInterval(
            state="UNKNOWN",
            reasons=("collapsed_percentile_interval",),
            observations=n,
            empirical_mean=point,
            lower=None,
            upper=None,
            bootstrap_standard_deviation=variance.sqrt(),
            distribution_sha256=digest,
        )
    return MeanInterval(
        state="CALCULATED",
        reasons=(),
        observations=n,
        empirical_mean=point,
        lower=lower,
        upper=upper,
        bootstrap_standard_deviation=variance.sqrt(),
        distribution_sha256=digest,
    )


def _uncertainty_parts(
    source: FuturesEdgeStudy, config: MeanBootstrapConfig
) -> tuple[PartitionUncertainty, PartitionUncertainty, PartitionUncertainty]:
    results = []
    with localcontext() as context:
        context.prec = 80
        for edge, run in zip(source.partitions, source.source.partitions, strict=True):
            metrics = edge.metrics
            n = len(run.trades)
            reason = (
                edge.reasons[0]
                if metrics is None
                else (
                    "insufficient_outcomes_for_mean_uncertainty"
                    if n < config.minimum_observations
                    else (
                        "block_exceeds_mean_history"
                        if config.sampling.block_length > n
                        else (
                            "only_one_available_resample_block"
                            if config.sampling.block_length == n
                            else (
                                "mean_bootstrap_work_limit"
                                if n * config.sampling.simulations > 10000000
                                else None
                            )
                        )
                    )
                )
            )
            if reason is not None:
                intervals = []
                for point in (
                    metrics.expectancy_r if metrics else None,
                    metrics.total_net_usd / n if metrics else None,
                ):
                    intervals.append(
                        MeanInterval(
                            state="UNKNOWN",
                            reasons=(reason,),
                            observations=n,
                            empirical_mean=point,
                            lower=None,
                            upper=None,
                            bootstrap_standard_deviation=None,
                            distribution_sha256=None,
                        )
                    )
                r, usd = intervals
            else:
                assert metrics is not None
                means_r, means_usd = paired_block_bootstrap_means(
                    tuple(t.net_r for t in run.trades),
                    tuple(t.net_usd for t in run.trades),
                    configuration=config.sampling,
                )
                r = _mean_interval(means_r, metrics.expectancy_r, n, config)
                usd = _mean_interval(means_usd, metrics.total_net_usd / n, n, config)
            results.append(PartitionUncertainty(role=edge.role, mean_r=r, mean_usd=usd))
    return results[0], results[1], results[2]


def _implementation_digest() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


class FuturesUncertaintyStudy(Evidence):
    algorithm_version: Literal["futures-mean-uncertainty-v1"] = "futures-mean-uncertainty-v1"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    validation_state: Literal["UNVALIDATED"] = "UNVALIDATED"
    calibrated_coverage: Literal[False] = False
    source: FuturesEdgeStudy
    source_sha256: Digest
    implementation_sha256: Digest
    numpy_version: Identity
    configuration: MeanBootstrapConfig
    partitions: tuple[PartitionUncertainty, PartitionUncertainty, PartitionUncertainty]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def reproduce(self) -> Self:
        if self.source_sha256 != _sha(self.source.model_dump(mode="json")):
            raise ValueError("Uncertainty source digest mismatch")
        if (
            self.implementation_sha256 != _implementation_digest()
            or self.numpy_version != np.__version__
        ):
            raise ValueError("Uncertainty implementation/runtime mismatch")
        if self.partitions != _uncertainty_parts(self.source, self.configuration):
            raise ValueError("Mean uncertainty must reproduce paired source outcomes")
        return self


async def futures_expectancy_uncertainty(
    source: FuturesEdgeStudy, *, configuration: MeanBootstrapConfig
) -> FuturesUncertaintyStudy:
    configuration = MeanBootstrapConfig.model_validate(configuration.model_dump(warnings=False))
    source = await verify_futures_edge_study(source)
    return FuturesUncertaintyStudy(
        source=source,
        source_sha256=_sha(source.model_dump(mode="json")),
        implementation_sha256=_implementation_digest(),
        numpy_version=np.__version__,
        configuration=configuration,
        partitions=_uncertainty_parts(source, configuration),
    )


async def verify_futures_uncertainty(value: FuturesUncertaintyStudy) -> FuturesUncertaintyStudy:
    value = FuturesUncertaintyStudy.model_validate(value.model_dump(warnings=False))
    return await futures_expectancy_uncertainty(value.source, configuration=value.configuration)


class FuturesWalkWindow(Evidence):
    id: Identity
    partitions: tuple[ResearchPartition, ResearchPartition, ResearchPartition]

    @model_validator(mode="after")
    def chronology(self) -> Self:
        # Reuse the existing exact split validator, with the window's own bounds.
        StrategyResearchPlan(
            dataset_id=self.id,
            dataset_sha256=_sha(self.model_dump(mode="json")),
            source_reference="Declared fixed-rule walk-forward window",
            research_start=self.partitions[0].start,
            research_end=self.partitions[-1].end,
            partitions=self.partitions,
        )
        return self


class FuturesWalkPlan(Evidence):
    id: Identity
    version: Identity
    input_sha256: Digest
    definition_sha256: Digest
    windows: tuple[FuturesWalkWindow, ...] = Field(min_length=2, max_length=10)
    parameter_selection: Literal["frozen_definition_no_tuning"] = "frozen_definition_no_tuning"

    @model_validator(mode="after")
    def unique_tests(self) -> Self:
        if len({w.id for w in self.windows}) != len(self.windows):
            raise ValueError("Walk-forward window identities must be unique")
        for previous, current in zip(self.windows, self.windows[1:], strict=False):
            if (
                previous.partitions[-1].end >= current.partitions[-1].start
                or previous.partitions[0].start > current.partitions[0].start
            ):
                raise ValueError(
                    "Walk-forward tests must be chronological/disjoint; training moves forward"
                )
        return self


def _check_walk(inputs: FuturesResearchInput, plan: FuturesWalkPlan) -> None:
    if (plan.input_sha256, plan.definition_sha256) != (inputs.revision, inputs.definition.revision):
        raise ValueError("Walk plan must match its captured input/definition revisions")
    research = inputs.definition.research
    assert research is not None
    for w in plan.windows:
        if (
            w.partitions[0].start < research.partitions[0].start
            or w.partitions[-1].end > research.partitions[1].end
        ):
            raise ValueError("Walk-forward windows must end before the reserved final holdout")


def _fold_input(inputs: FuturesResearchInput, window: FuturesWalkWindow) -> FuturesResearchInput:
    cut = window.partitions[-1].end
    records = []
    for record in inputs.records:
        prefix = bounded_snapshot(
            record,
            MarketDataQuery(
                instrument_id=inputs.instrument.id,
                interval=inputs.definition.interval,
                contract=record.contract,
                as_of=cut,
                max_bars=500,
            ),
        )
        if prefix is not None:
            records.append(prefix)
    definition = inputs.definition.model_dump()
    assert inputs.definition.research is not None
    research = inputs.definition.research.model_dump()
    research.update(
        dataset_sha256=futures_dataset_digest(tuple(records)),
        research_start=window.partitions[0].start,
        research_end=cut,
        partitions=tuple(p.model_dump() for p in window.partitions),
    )
    definition.update(
        version="wf-"
        + _sha(
            {"definition": inputs.definition.revision, "window": window.model_dump(mode="json")}
        ),
        research=research,
    )
    return FuturesResearchInput.model_validate(
        inputs.model_dump()
        | {
            "definition": definition,
            "records": tuple(r.model_dump() for r in records),
            "calendars": tuple(c.model_dump() for c in inputs.calendars if c.observed_at <= cut),
        }
    )


class FuturesWalkFold(Evidence):
    window_id: Identity
    uncertainty: FuturesUncertaintyStudy


class FuturesWalkStudy(Evidence):
    algorithm_version: Literal["fixed-rule-futures-walk-v1"] = "fixed-rule-futures-walk-v1"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    validation_state: Literal["UNVALIDATED"] = "UNVALIDATED"
    final_holdout_scope: Literal["not_evaluated_by_this_walk"] = "not_evaluated_by_this_walk"
    inputs: FuturesResearchInput
    plan: FuturesWalkPlan
    configuration: MeanBootstrapConfig
    folds: tuple[FuturesWalkFold, ...]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def joins(self) -> Self:
        _check_walk(self.inputs, self.plan)
        if len(self.folds) != len(self.plan.windows):
            raise ValueError("Every declared walk-forward window must be retained")
        for fold, window in zip(self.folds, self.plan.windows, strict=True):
            if (
                fold.window_id != window.id
                or fold.uncertainty.configuration != self.configuration
                or fold.uncertainty.source.source.inputs != _fold_input(self.inputs, window)
            ):
                raise ValueError("Walk-forward fold must match its declared fixed-rule prefix")
        return self


async def walk_forward_futures(
    inputs: FuturesResearchInput, *, plan: FuturesWalkPlan, configuration: MeanBootstrapConfig
) -> FuturesWalkStudy:
    inputs = FuturesResearchInput.model_validate(inputs.model_dump(warnings=False))
    plan = FuturesWalkPlan.model_validate(plan.model_dump(warnings=False))
    configuration = MeanBootstrapConfig.model_validate(configuration.model_dump(warnings=False))
    _check_walk(inputs, plan)
    folds = []
    for window in plan.windows:
        run = await run_futures_research(_fold_input(inputs, window))
        edge = await futures_edge_analysis(run, configuration=configuration.sampling)
        uncertainty = await futures_expectancy_uncertainty(edge, configuration=configuration)
        folds.append(FuturesWalkFold(window_id=window.id, uncertainty=uncertainty))
    return FuturesWalkStudy(
        inputs=inputs, plan=plan, configuration=configuration, folds=tuple(folds)
    )


async def verify_futures_walk(value: FuturesWalkStudy) -> FuturesWalkStudy:
    value = FuturesWalkStudy.model_validate(value.model_dump(warnings=False))
    replayed = await walk_forward_futures(
        value.inputs, plan=value.plan, configuration=value.configuration
    )
    if value.model_dump(mode="json") != replayed.model_dump(mode="json"):
        raise ValueError("Futures walk-forward replay mismatch")
    return replayed
