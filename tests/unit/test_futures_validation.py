"""Independent sampling/percentile oracles and chronological source replay."""

from datetime import timedelta
from decimal import Decimal, localcontext

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from backtesting.futures import _sha, futures_edge_analysis, run_futures_research
from backtesting.path_risk import LossStreakConfig, paired_block_bootstrap_means
from backtesting.validation import (
    FuturesUncertaintyStudy,
    FuturesWalkPlan,
    FuturesWalkStudy,
    FuturesWalkWindow,
    MeanBootstrapConfig,
    _mean_interval,
    _percentile,
    futures_expectancy_uncertainty,
    verify_futures_uncertainty,
    verify_futures_walk,
    walk_forward_futures,
)
from core.advisory.strategies import ResearchPartition
from tests.unit.test_futures_edge import configuration, research_input
from tests.unit.test_futures_research import ROOTS, changed, request

pytestmark = pytest.mark.unit


def config(**changes):
    return MeanBootstrapConfig.model_validate(
        dict(
            sampling=LossStreakConfig(block_length=1, simulations=60, seed=42),
            confidence_level=Decimal(".9"),
            minimum_observations=2,
        )
        | changes
    )


def oracle(r, usd, sampling):
    paths_r = [[] for _ in range(sampling.simulations)]
    paths_usd = [[] for _ in range(sampling.simulations)]
    rng = np.random.default_rng(sampling.seed)
    for offset in range(0, len(r), sampling.block_length):
        starts = rng.integers(0, len(r) - sampling.block_length + 1, size=sampling.simulations)
        for sample, start in enumerate(starts):
            length = min(sampling.block_length, len(r) - offset)
            paths_r[sample].extend(r[int(start) : int(start) + length])
            paths_usd[sample].extend(usd[int(start) : int(start) + length])
    with localcontext() as c:
        c.prec = 80
        return tuple(sum(path, Decimal(0)) / len(r) for path in paths_r), tuple(
            sum(path, Decimal(0)) / len(r) for path in paths_usd
        )


@pytest.mark.parametrize("block", [1, 2, 3, 4, 5])
def test_paired_full_length_block_means_match_independent_python_paths(block):
    r = tuple(map(Decimal, [-3, 1, -2, 4, 0]))
    usd = tuple(3 * v + 1 for v in r)
    sampling = configuration(block_length=block, simulations=19, seed=2)
    assert paired_block_bootstrap_means(r, usd, configuration=sampling) == oracle(r, usd, sampling)


@given(values=st.lists(st.integers(-100, 100), min_size=2, max_size=35), seed=st.integers(0, 10000))
@settings(max_examples=50, deadline=None)
def test_paired_samples_keep_channel_alignment_and_observed_mean_support(values, seed):
    r = tuple(map(Decimal, values))
    usd = tuple(2 * v + 7 for v in r)
    sampling = configuration(block_length=min(3, len(r)), simulations=12, seed=seed)
    means_r, means_usd = paired_block_bootstrap_means(r, usd, configuration=sampling)
    assert (means_r, means_usd) == oracle(r, usd, sampling)
    with localcontext() as c:
        c.prec = 80
        for a, b in zip(means_r, means_usd, strict=True):
            assert min(r) <= a <= max(r)
            assert abs(b - (2 * a + 7)) < Decimal("1e-72")


@pytest.mark.parametrize(
    "r,usd",
    [
        ((), ()),
        (None, (Decimal(1),)),
        ((Decimal(1),), None),
        ((1,), (Decimal(1),)),
        ((Decimal(1),), (True,)),
        ((Decimal("NaN"),), (Decimal(1),)),
        ((Decimal(1),), (Decimal("Infinity"),)),
        ((Decimal(1),), (Decimal(1), Decimal(2))),
    ],
)
def test_paired_shapes_types_and_finite_values_fail_closed(r, usd):
    with pytest.raises(ValueError, match="aligned bounded finite"):
        paired_block_bootstrap_means(r, usd, configuration=configuration(block_length=1))


def test_paired_sampling_block_and_work_limits():
    with pytest.raises(ValueError, match="Block length"):
        paired_block_bootstrap_means(
            (Decimal(1),), (Decimal(1),), configuration=configuration(block_length=2)
        )
    values = (Decimal(1),) * 10000
    with pytest.raises(ValueError, match="work limit"):
        paired_block_bootstrap_means(
            values, values, configuration=configuration(block_length=2, simulations=1001)
        )


@pytest.mark.parametrize(
    "p,expected",
    [
        (Decimal(0), -3),
        (Decimal(".25"), 0),
        (Decimal(".5"), 3),
        (Decimal(".75"), 6),
        (Decimal(1), 9),
    ],
)
def test_explicit_linear_percentile_boundaries(p, expected):
    assert _percentile(tuple(map(Decimal, [-3, 1, 5, 9])), p) == expected


def test_percentile_confidence_minus_equal_plus_epsilon():
    means = tuple(map(Decimal, [-3, 1, 5, 9]))
    with localcontext() as c:
        c.prec = 80
        values = [
            _mean_interval(means, Decimal(3), 4, config(confidence_level=level))
            for level in (
                Decimal(".9") - Decimal("1e-20"),
                Decimal(".9"),
                Decimal(".9") + Decimal("1e-20"),
            )
        ]
        assert values[0].lower > values[1].lower > values[2].lower
        assert values[0].upper < values[1].upper < values[2].upper
        assert values[1].lower == Decimal("-2.4") and values[1].upper == Decimal("8.4")
        assert abs(values[1].bootstrap_standard_deviation ** 2 - Decimal(80) / 3) < Decimal("1e-70")


@pytest.mark.parametrize(
    "change",
    [
        dict(confidence_level=0),
        dict(confidence_level=1),
        dict(confidence_level="NaN"),
        dict(minimum_observations=1),
        dict(minimum_observations=True),
        dict(sampling=configuration(simulations=1)),
        dict(method="iid-bca"),
    ],
)
def test_uncertainty_configuration_is_explicit_and_strict(change):
    with pytest.raises(ValueError):
        config(**change)


async def edge(value=None):
    source = await run_futures_research(research_input() if value is None else value)
    return await futures_edge_analysis(source, configuration=configuration(block_length=1))


async def test_verified_public_mean_bounds_match_independent_sampling_and_reopen():
    source = await edge()
    result = await futures_expectancy_uncertainty(source, configuration=config())
    for p, run in zip(result.partitions, source.source.partitions, strict=True):
        expected_r, expected_usd = oracle(
            tuple(t.net_r for t in run.trades),
            tuple(t.net_usd for t in run.trades),
            config().sampling,
        )
        with localcontext() as c:
            c.prec = 80
            for interval, means in ((p.mean_r, expected_r), (p.mean_usd, expected_usd)):
                assert interval.state == "CALCULATED" and not interval.reasons
                assert interval.lower == _percentile(means, Decimal(".05"))
                assert interval.upper == _percentile(means, Decimal(".95"))
    assert not result.calibrated_coverage and result.validation_state == "UNVALIDATED"
    assert not result.trade_permitted and not result.execution_enabled
    assert (
        await verify_futures_uncertainty(
            FuturesUncertaintyStudy.model_validate_json(result.model_dump_json())
        )
        == result
    )


@pytest.mark.parametrize("root", ROOTS)
async def test_single_outcome_cannot_create_mean_confidence_even_when_positive(root):
    result = await futures_expectancy_uncertainty(await edge(request(root)), configuration=config())
    assert all(
        p.mean_r.state == p.mean_usd.state == "UNKNOWN" and p.mean_r.lower is None
        for p in result.partitions
    )


@pytest.mark.parametrize(
    "sampling,minimum,reason",
    [
        (configuration(block_length=5), 2, "block_exceeds_mean_history"),
        (configuration(block_length=4), 2, "only_one_available_resample_block"),
        (configuration(block_length=1), 5, "insufficient_outcomes_for_mean_uncertainty"),
    ],
)
async def test_unsupported_inference_is_unknown_without_bounds(sampling, minimum, reason):
    result = await futures_expectancy_uncertainty(
        await edge(), configuration=config(sampling=sampling, minimum_observations=minimum)
    )
    assert all(
        p.mean_r.reasons == (reason,) and p.mean_r.lower is p.mean_usd.upper is None
        for p in result.partitions
    )


async def test_degenerate_distribution_does_not_create_positive_zero_width_confidence():
    result = await futures_expectancy_uncertainty(
        await edge(research_input(winning=(True, True, True, True))), configuration=config()
    )
    for p in result.partitions:
        assert p.mean_r.empirical_mean > 0
        assert p.mean_r.state == "UNKNOWN" and p.mean_usd.state == "UNKNOWN"
        assert p.mean_r.reasons == ("degenerate_bootstrap_distribution",)
        assert (
            p.mean_r.lower is p.mean_r.upper is None and p.mean_r.bootstrap_standard_deviation == 0
        )


async def test_no_trade_source_preserves_unknown_source_reasons():
    value = request()
    records = [value.records[0].model_dump()]
    for b in records[0]["candles"]:
        b["volume"] = 10
    result = await futures_expectancy_uncertainty(
        await edge(changed(value, records=records)), configuration=config()
    )
    assert all(
        p.mean_r.empirical_mean is None and p.mean_r.reasons == ("missing_closed_futures_outcomes",)
        for p in result.partitions
    )


@pytest.mark.parametrize(
    "field", ["bound", "source", "runtime", "implementation", "calibration", "configuration"]
)
async def test_saved_uncertainty_cannot_be_mutated_into_trusted_positive_edge(field):
    result = await futures_expectancy_uncertainty(await edge(), configuration=config())
    payload = result.model_dump()
    if field == "bound":
        payload["partitions"][2]["mean_r"]["lower"] = 1000
    elif field == "source":
        payload["source_sha256"] = "0" * 64
    elif field == "runtime":
        payload["numpy_version"] = "other"
    elif field == "implementation":
        payload["implementation_sha256"] = "0" * 64
    elif field == "calibration":
        payload["calibrated_coverage"] = True
    else:
        payload["configuration"]["sampling"]["seed"] += 1
    with pytest.raises(ValueError):
        FuturesUncertaintyStudy.model_validate(payload)


def walk_input():
    return research_input(winning=(False, True, False, True, True, False))


def walk_plan(value):
    bars = [b for r in value.records for b in r.candles]
    windows = []
    for name, ranges in (
        ("first", ((0, 15), (16, 31), (32, 47))),
        ("second", ((16, 47), (48, 63), (64, 79))),
    ):
        parts = tuple(
            ResearchPartition(role=role, start=bars[start].open_time, end=bars[end].close_time)
            for role, (start, end) in zip(("TRAIN", "VALIDATION", "OOS"), ranges, strict=True)
        )
        windows.append(FuturesWalkWindow(id=name, partitions=parts))
    return FuturesWalkPlan(
        id="SYNTHETIC-fixed-rules",
        version="v1",
        input_sha256=value.revision,
        definition_sha256=value.definition.revision,
        windows=tuple(windows),
    )


async def test_declared_fixed_rule_folds_reuse_runner_and_stop_before_final_holdout():
    value = walk_input()
    plan = walk_plan(value)
    result = await walk_forward_futures(value, plan=plan, configuration=config())
    assert len(result.folds) == 2 and result.final_holdout_scope == "not_evaluated_by_this_walk"
    for fold, w in zip(result.folds, plan.windows, strict=True):
        run = fold.uncertainty.source.source
        assert run.inputs.definition.parameters == value.definition.parameters
        assert run.inputs.definition.management == value.definition.management
        assert run.inputs.definition.version.startswith("wf-")
        assert all(
            b.close_time <= w.partitions[-1].end for r in run.inputs.records for b in r.candles
        )
        assert all(c.observed_at <= w.partitions[-1].end for c in run.inputs.calendars)
        assert all(p.mean_r.state == "CALCULATED" for p in fold.uncertainty.partitions)
    assert (
        await verify_futures_walk(FuturesWalkStudy.model_validate_json(result.model_dump_json()))
        == result
    )
    assert result.validation_state == "UNVALIDATED" and not result.trade_permitted


@pytest.mark.parametrize(
    "fault", ["input", "definition", "duplicate", "overlap", "holdout", "backward", "roles"]
)
async def test_walk_plan_mismatches_and_leaking_or_overlapping_tests_rejected(fault):
    value = walk_input()
    payload = walk_plan(value).model_dump()
    if fault == "input":
        payload["input_sha256"] = "0" * 64
    elif fault == "definition":
        payload["definition_sha256"] = "0" * 64
    elif fault == "duplicate":
        payload["windows"][1]["id"] = "first"
    elif fault == "overlap":
        payload["windows"][1]["partitions"][2]["start"] = payload["windows"][0]["partitions"][2][
            "end"
        ]
    elif fault == "holdout":
        payload["windows"][1]["partitions"][2].update(
            value.definition.research.partitions[2].model_dump()
        )
    elif fault == "backward":
        payload["windows"][1]["partitions"][0]["start"] -= timedelta(days=30)
    else:
        payload["windows"][0]["partitions"][0]["role"] = "OOS"
    with pytest.raises(ValueError):
        await walk_forward_futures(
            value, plan=FuturesWalkPlan.model_validate(payload), configuration=config()
        )


async def test_failed_research_fold_is_retained_with_unknowns_not_skipped():
    value = walk_input()
    records = [value.records[0].model_dump()]
    records[0]["quality"]["provider_state"] = "disconnected"
    value = changed(value, records=records)
    result = await walk_forward_futures(value, plan=walk_plan(value), configuration=config())
    assert len(result.folds) == 2
    assert all(
        p.mean_r.state == "UNKNOWN" for fold in result.folds for p in fold.uncertainty.partitions
    )


async def test_saved_walk_requires_every_declared_fold_and_prefix_join():
    value = walk_input()
    result = await walk_forward_futures(value, plan=walk_plan(value), configuration=config())
    payload = result.model_dump()
    payload["folds"] = payload["folds"][:1]
    with pytest.raises(ValueError, match="Every declared"):
        FuturesWalkStudy.model_validate(payload)
    payload = result.model_dump()
    payload["folds"][0]["window_id"] = "other"
    with pytest.raises(ValueError, match="declared fixed-rule prefix"):
        FuturesWalkStudy.model_validate(payload)


async def test_future_holdout_price_mutation_leaves_fold_statistics_and_bounds_unchanged():
    value = walk_input()
    a = await walk_forward_futures(value, plan=walk_plan(value), configuration=config())
    records = [value.records[0].model_dump()]
    for b in records[0]["candles"][96:]:
        for name in ("open", "high", "low", "close"):
            b[name] += 100
    value = changed(value, records=records)
    b = await walk_forward_futures(value, plan=walk_plan(value), configuration=config())
    for first, last in zip(a.folds, b.folds, strict=True):
        assert first.uncertainty.partitions == last.uncertainty.partitions
        assert first.uncertainty.source.partitions == last.uncertainty.source.partitions


async def test_numeric_context_and_repeatability_do_not_change_public_uncertainty():
    source = await edge()
    a = await futures_expectancy_uncertainty(source, configuration=config())
    with localcontext() as c:
        c.prec = 6
        b = await futures_expectancy_uncertainty(source, configuration=config())
    assert a.model_dump_json() == b.model_dump_json()


def test_tied_percentile_endpoints_do_not_publish_zero_width_confidence():
    interval = _mean_interval(
        tuple(map(Decimal, [0, 1, 1, 1, 1, 1, 2])),
        Decimal(1),
        7,
        config(confidence_level=Decimal(".1")),
    )
    assert interval.state == "UNKNOWN" and interval.reasons == ("collapsed_percentile_interval",)
    assert interval.lower is interval.upper is None
    assert interval.bootstrap_standard_deviation > 0


async def test_future_archive_chunks_are_excluded_from_each_walk_prefix():
    value = walk_input()
    record = value.records[0].model_dump()
    rows = []
    for start in (0, 48, 96):
        row = dict(record)
        row["candles"] = record["candles"][start : start + 48]
        row["quality"] = dict(
            record["quality"], sequences=record["quality"]["sequences"][start : start + 48]
        )
        rows.append(row)
    value = changed(value, records=rows)
    result = await walk_forward_futures(value, plan=walk_plan(value), configuration=config())
    for fold in result.folds:
        records = fold.uncertainty.source.source.inputs.records
        assert all(
            b.close_time < value.definition.research.partitions[-1].start
            for r in records
            for b in r.candles
        )
    assert len(result.folds[0].uncertainty.source.source.inputs.records) == 1
    assert len(result.folds[1].uncertainty.source.source.inputs.records) == 2


async def test_self_consistent_fill_label_forgery_requires_complete_walk_replay():
    value = walk_input()
    result = await walk_forward_futures(value, plan=walk_plan(value), configuration=config())
    payload = result.model_dump()
    uncertainty = payload["folds"][0]["uncertainty"]
    edge = uncertainty["source"]
    edge["source"]["partitions"][0]["fills"][0]["reason"] = "forged_fill_reason"
    # Recompute envelope hashes without changing the matching numerical statistics.
    from backtesting.futures import FuturesEdgeStudy, FuturesResearchRun

    edge["source_sha256"] = _sha(
        FuturesResearchRun.model_validate(edge["source"]).model_dump(mode="json")
    )
    uncertainty["source_sha256"] = _sha(
        FuturesEdgeStudy.model_validate(edge).model_dump(mode="json")
    )
    forged = FuturesWalkStudy.model_validate(payload)
    with pytest.raises(ValueError, match="walk-forward replay mismatch"):
        await verify_futures_walk(forged)
