"""Enumerated probability and independent sequence oracles, never profitability proof."""

from collections import Counter
from datetime import UTC, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import chain, groupby, product

import numpy as np
import pytest
from hypothesis import given, settings, strategies as st

from backtesting.path_risk import (
    HORIZONS,
    LOSS_RUNS,
    LongestRunDistribution,
    LossStreakConfig,
    LossStreakStudy,
    iid_loss_run_probability,
    loss_streak_analysis,
    recorded_loss_run_tables,
)
from tests.unit.test_backtest_math import engine, observed_result

pytestmark = pytest.mark.unit


def config(**changes):
    return LossStreakConfig.model_validate(dict(block_length=3, simulations=100, seed=42) | changes)


@pytest.mark.parametrize(
    "outcomes",
    [
        (),
        None,
        [True],
        [0.5],
        ["0"],
        [Decimal("NaN")],
        [Decimal("Infinity")],
        [Decimal(0)] * 10001,
        {Decimal(1)},
    ],
)
def test_shared_signed_outcome_kernel_rejects_unknown_or_unbounded_sequences(outcomes):
    with pytest.raises(ValueError, match="Decimal outcome sequence"):
        recorded_loss_run_tables(outcomes, configuration=config(block_length=1))


def test_shared_futures_signs_reuse_exact_cash_tables_without_cash_loss_floor():
    returns = [-0.1, 0, 0.2, -0.3, 0.4, -0.5, 0.6]
    source = observed_result(returns)
    cash = loss_streak_analysis(source, configuration=config())
    futures = recorded_loss_run_tables(
        tuple(Decimal(str(v)) * 20 for v in returns), configuration=config()
    )
    assert futures == (
        cash.empirical_loss_fraction,
        cash.iid_baseline,
        cash.bootstrap,
        cash.longest_runs,
    )
    assert min(Decimal(str(v)) * 20 for v in returns) < -1


def test_shared_outcome_kernel_preserves_block_length_boundary():
    with pytest.raises(ValueError, match="Block length"):
        recorded_loss_run_tables((Decimal(-2),), configuration=config())


def longest(bits):
    return max((len(list(rows)) for key, rows in groupby(bits) if key), default=0)


def brute_probability(p, horizon, run):
    return sum(
        (
            p ** sum(bits) * (1 - p) ** (horizon - sum(bits))
            for bits in product((False, True), repeat=horizon)
            if longest(bits) >= run
        ),
        Fraction(0),
    )


@pytest.mark.parametrize(
    "p", [Fraction(0), Fraction(1, 5), Fraction(1, 2), Fraction(4, 5), Fraction(1)]
)
@pytest.mark.parametrize("run", [1, 2, 3, 4, 5])
def test_absorbing_recurrence_matches_exhaustive_sequence_enumeration(p, run):
    with localcontext() as ctx:
        ctx.prec = 50
        value = Decimal(p.numerator) / p.denominator
        for horizon in range(9):
            expected = brute_probability(p, horizon, run)
            expected_decimal = Decimal(expected.numerator) / expected.denominator
            assert abs(iid_loss_run_probability(value, horizon, run) - expected_decimal) < Decimal(
                "1e-47"
            )


def test_anywhere_in_horizon_is_not_the_probability_of_one_fixed_loss_block():
    assert iid_loss_run_probability(Decimal(".5"), 2, 2) == Decimal(".25")
    assert iid_loss_run_probability(Decimal(".5"), 10, 2) == Decimal(".859375")
    assert iid_loss_run_probability(Decimal(".5"), 100, 5) > Decimal(".5") ** 5


@pytest.mark.parametrize(
    "p,n,k",
    [
        (Decimal("NaN"), 10, 2),
        (Decimal("Infinity"), 10, 2),
        (Decimal("-.01"), 10, 2),
        (Decimal("1.01"), 10, 2),
        (0.5, 10, 2),
        (True, 10, 2),
        (Decimal(".5"), True, 2),
        (Decimal(".5"), 10, True),
        (Decimal(".5"), -1, 2),
        (Decimal(".5"), 10001, 2),
        (Decimal(".5"), 10, 0),
        (Decimal(".5"), 10, 1001),
        (Decimal(".5"), 10000, 101),
        (Decimal(".5"), 2.5, 2),
        (Decimal(".5"), 10, 2.5),
    ],
)
def test_invalid_or_unbounded_probability_inputs_are_rejected(p, n, k):
    with pytest.raises(ValueError):
        iid_loss_run_probability(p, n, k)


@pytest.mark.parametrize(
    "changes",
    [
        dict(block_length=0),
        dict(block_length=True),
        dict(block_length=10001),
        dict(simulations=0),
        dict(simulations=True),
        dict(simulations=100001),
        dict(seed=-1),
        dict(seed=True),
        dict(seed=2**64),
        dict(contracts=10),
    ],
)
def test_bootstrap_configuration_is_explicit_strict_and_bounded(changes):
    with pytest.raises(ValueError):
        config(**changes)


@pytest.mark.parametrize(
    "returns", [None, [], [float("nan")], [float("inf")], [-1.01], [True], ["bad"]]
)
def test_missing_or_corrupt_returns_are_unknown_without_invented_probabilities(returns):
    source = observed_result([0.1]).model_copy(update={"trade_returns": returns})
    result = loss_streak_analysis(source, configuration=config(block_length=1))
    assert result.state == "UNKNOWN" and result.source is None and result.reasons
    assert (
        result.empirical_loss_fraction is None
        and result.iid_baseline == result.bootstrap == result.longest_runs == ()
    )
    assert not result.trade_permitted and not result.execution_enabled
    assert LossStreakStudy.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"total_trades": True}, "invalid_recorded_net_trade_history"),
        ({"total_trades": -1}, "invalid_recorded_net_trade_history"),
        ({"total_trades": 2.5}, "invalid_recorded_net_trade_history"),
        ({"total_trades": 2}, "invalid_recorded_net_trade_history"),
        ({"total_trades": 0, "trade_returns": []}, "missing_recorded_net_trade_history"),
        ({"trade_returns": [0.1] * 10001, "total_trades": 10001}, "recorded_trade_history_limit"),
    ],
)
def test_source_counts_and_capacity_never_infer_outcomes_from_summary(changes, reason):
    result = loss_streak_analysis(
        observed_result([0.1]).model_copy(update=changes), configuration=config(block_length=1)
    )
    assert result.state == "UNKNOWN" and result.reasons == (reason,)


def test_invalid_or_mixed_period_clocks_remain_unknown():
    source = observed_result([0.1])
    for end in (
        source.start_date,
        source.start_date - timedelta(seconds=1),
        source.end_date.replace(tzinfo=UTC),
    ):
        result = loss_streak_analysis(
            source.model_copy(update={"end_date": end}), configuration=config(block_length=1)
        )
        assert result.state == "UNKNOWN" and result.reasons == ("invalid_backtest_period",)


def test_zero_returns_count_as_loss_using_the_existing_engine_convention():
    result = loss_streak_analysis(
        observed_result([0, -0.1, 0, 0.1]), configuration=config(block_length=4)
    )
    assert result.state == "CALCULATED" and result.empirical_loss_fraction == Decimal(".75")
    assert result.longest_runs[0].counts[3] == 100
    assert all(r.probability == 1 for r in result.bootstrap if r.loss_run in (2, 3))
    assert all(r.probability == 0 for r in result.bootstrap if r.loss_run in (4, 5))


@pytest.mark.parametrize("returns,p", [([0.1] * 10, 0), ([-0.1] * 10, 1)])
def test_all_win_or_all_loss_support_has_exact_horizon_probabilities(returns, p):
    result = loss_streak_analysis(observed_result(returns), configuration=config(block_length=10))
    assert len(result.iid_baseline) == len(result.bootstrap) == 16
    assert all(row.probability == p for row in (*result.iid_baseline, *result.bootstrap))
    for dist in result.longest_runs:
        assert sum(dist.counts) == 100 and dist.counts[dist.horizon_trades if p else 0] == 100
    assert (
        result.lifecycle == "EXPERIMENT"
        and not result.trade_permitted
        and not result.execution_enabled
    )


def test_clustered_and_alternating_sequences_with_same_loss_fraction_remain_distinct():
    alternating = loss_streak_analysis(
        observed_result([-0.1, 0.1] * 5), configuration=config(block_length=10)
    )
    clustered = loss_streak_analysis(
        observed_result([-0.1] * 5 + [0.1] * 5), configuration=config(block_length=10)
    )
    assert alternating.empirical_loss_fraction == clustered.empirical_loss_fraction == Decimal(".5")
    assert alternating.iid_baseline == clustered.iid_baseline
    assert all(r.probability == 0 for r in alternating.bootstrap)
    assert all(r.probability == 1 for r in clustered.bootstrap)
    assert (
        alternating.longest_runs[0].counts[1] == 100 and clustered.longest_runs[0].counts[5] == 100
    )


@pytest.mark.parametrize("block_length", [1, 3, 7, 33, 100, 150])
def test_bootstrap_matches_independent_python_block_and_longest_run_oracle(block_length):
    values = [-0.1] * 6 + [0.2] * 4 + [0] + [0.3] * 9
    values *= 10
    cfg = config(block_length=block_length, simulations=27, seed=73)
    result = loss_streak_analysis(observed_result(values), configuration=cfg)
    rng = np.random.default_rng(cfg.seed)
    starts = rng.integers(
        0,
        len(values) - block_length + 1,
        size=((100 + block_length - 1) // block_length, cfg.simulations),
    )
    oracle = [
        list(
            chain.from_iterable(
                (
                    [v <= 0 for v in values[int(starts[b, i]) : int(starts[b, i]) + block_length]]
                    for b in range(len(starts))
                ),
            )
        )[:100]
        for i in range(cfg.simulations)
    ]
    with localcontext() as ctx:
        ctx.prec = 50
        for horizon, dist in zip(HORIZONS, result.longest_runs, strict=True):
            expected = Counter(longest(path[:horizon]) for path in oracle)
            assert dist.counts == tuple(expected[i] for i in range(horizon + 1))
            for run in LOSS_RUNS:
                row = next(
                    r for r in result.bootstrap if (r.horizon_trades, r.loss_run) == (horizon, run)
                )
                assert (
                    row.probability
                    == Decimal(sum(v for k, v in expected.items() if k >= run)) / cfg.simulations
                )


def test_engine_reuses_recorded_source_detaches_caller_and_roundtrips_exactly():
    source = observed_result([-0.1, 0.1, 0.2, -0.2] * 5)
    cfg = config(simulations=500)
    first = engine().loss_streaks(source, configuration=cfg)
    assert first == engine().loss_streaks(source, configuration=cfg)
    assert first == LossStreakStudy.model_validate_json(first.model_dump_json())
    source.trade_returns[0] = 0.9
    assert first.source.trade_returns[0] == -0.1
    # Summary metrics and passed_validation never replace the recorded sample.
    changed = first.source.model_copy(
        update={"win_rate_pct": 100, "max_consecutive_losses": 0, "passed_validation": True}
    )
    recomputed = engine().loss_streaks(changed, configuration=cfg)
    assert recomputed.iid_baseline == first.iid_baseline and recomputed.bootstrap == first.bootstrap
    assert recomputed.source_sha256 != first.source_sha256 and recomputed.lifecycle == "EXPERIMENT"


def test_block_length_larger_than_complete_history_is_an_explicit_configuration_error():
    with pytest.raises(ValueError, match="Block length"):
        loss_streak_analysis(observed_result([-0.1, 0.1]), configuration=config())
    bad = config().model_copy(update={"block_length": True})
    with pytest.raises(ValueError):
        loss_streak_analysis(observed_result([-0.1, 0.1]), configuration=bad)


@pytest.mark.parametrize(
    "fault",
    ["source", "digest", "grid", "distribution", "fraction", "config", "state", "permission"],
)
def test_saved_probe_cannot_keep_calculated_fields_after_input_or_result_tampering(fault):
    result = loss_streak_analysis(observed_result([-0.1, 0.1] * 5), configuration=config())
    changes = {
        "source": {"source": result.source.model_copy(update={"trade_returns": [0.1] * 10})},
        "digest": {"source_sha256": "b" * 64},
        "grid": {"bootstrap": ()},
        "distribution": {"longest_runs": ()},
        "fraction": {"empirical_loss_fraction": Decimal(0)},
        "config": {"configuration": config(seed=74)},
        "state": {"state": "UNKNOWN"},
        "permission": {"trade_permitted": True},
    }
    with pytest.raises(ValueError):
        LossStreakStudy.model_validate(result.model_copy(update=changes[fault]).model_dump())


def test_unknown_probe_cannot_add_probability_zeroes_or_false_success_labels():
    result = loss_streak_analysis(observed_result([]), configuration=config())
    for changes in [
        dict(state="CALCULATED"),
        dict(reasons=()),
        dict(reasons=("unrecognized",)),
        dict(empirical_loss_fraction=Decimal(0)),
        dict(source_sha256="a" * 64),
    ]:
        with pytest.raises(ValueError):
            LossStreakStudy.model_validate(result.model_copy(update=changes).model_dump())
    good = loss_streak_analysis(observed_result([0.1]), configuration=config(block_length=1))
    for changes in [
        dict(source=None),
        dict(reasons=("missing_recorded_net_trade_history",)),
        dict(source=good.source.model_copy(update={"trade_returns": None})),
    ]:
        with pytest.raises(ValueError):
            LossStreakStudy.model_validate(good.model_copy(update=changes).model_dump())


def test_histogram_rejects_negative_wrong_length_or_boolean_counts():
    for counts in [(), (0,) * 10, (True,) + (0,) * 10, (-1,) + (0,) * 10]:
        with pytest.raises(ValueError):
            LongestRunDistribution(horizon_trades=10, counts=counts)


@given(st.integers(min_value=0, max_value=1000))
@settings(max_examples=80, derandomize=True)
def test_probability_is_monotone_in_horizon_and_decreases_with_run_threshold(numerator):
    p = Decimal(numerator) / 1000
    table = {(h, k): iid_loss_run_probability(p, h, k) for h in HORIZONS for k in LOSS_RUNS}
    assert all(0 <= v <= 1 for v in table.values())
    for k in LOSS_RUNS:
        assert [table[h, k] for h in HORIZONS] == sorted(table[h, k] for h in HORIZONS)
    for h in HORIZONS:
        assert [table[h, k] for k in LOSS_RUNS] == sorted(
            (table[h, k] for k in LOSS_RUNS), reverse=True
        )


def test_decimal_precision_is_local_and_micro_probability_is_not_cancelled():
    with localcontext() as ctx:
        ctx.prec = 12
        result = iid_loss_run_probability(Decimal("1e-30"), 100, 5)
        assert result > 0 and ctx.prec == 12
        assert abs(result / (Decimal(96) * Decimal("1e-150")) - 1) < Decimal("1e-10")


@pytest.mark.parametrize("returns", [0.1, {-1: 0.1}, {-0.1, 0.1}])
def test_copied_wrong_history_container_is_unknown(returns):
    source = observed_result([0.1]).model_copy(update={"trade_returns": returns})
    result = loss_streak_analysis(source, configuration=config(block_length=1))
    assert result.state == "UNKNOWN" and result.reasons == ("invalid_recorded_net_trade_history",)


def test_copied_non_datetime_periods_are_unknown_before_analysis():
    source = observed_result([0.1]).model_copy(
        update={"start_date": "2020-01-01", "end_date": "2021-01-01"}
    )
    result = loss_streak_analysis(source, configuration=config(block_length=1))
    assert result.state == "UNKNOWN" and result.reasons == ("invalid_backtest_period",)


@pytest.mark.parametrize(
    "value,state",
    [
        (-1.000001, "UNKNOWN"),
        (-1.0, "CALCULATED"),
        (-0.999999, "CALCULATED"),
        (-0.000001, "CALCULATED"),
        (0.0, "CALCULATED"),
        (0.000001, "CALCULATED"),
    ],
)
def test_net_return_loss_and_minus_one_boundaries(value, state):
    result = loss_streak_analysis(observed_result([value]), configuration=config(block_length=1))
    assert result.state == state
    if state == "CALCULATED":
        assert result.empirical_loss_fraction == int(value <= 0)
    else:
        assert result.bootstrap == ()


def test_exact_history_capacity_and_work_budget_boundaries():
    result = loss_streak_analysis(
        observed_result([0.1] * 10000), configuration=config(block_length=10000, simulations=1)
    )
    assert result.state == "CALCULATED" and result.empirical_loss_fraction == 0
    assert iid_loss_run_probability(Decimal(1), 10000, 100) == 1
    with pytest.raises(ValueError):
        iid_loss_run_probability(Decimal(1), 10000, 101)
    assert config(simulations=100000, seed=0)
    assert config(seed=2**64 - 1)


def test_untyped_record_is_explicit_error_and_zero_count_cannot_hide_nonempty_history():
    with pytest.raises(ValueError, match="typed backtest"):
        loss_streak_analysis(None, configuration=config())
    result = loss_streak_analysis(
        observed_result([0.1]).model_copy(update={"total_trades": 0}),
        configuration=config(block_length=1),
    )
    assert result.state == "UNKNOWN" and result.reasons == ("invalid_recorded_net_trade_history",)
