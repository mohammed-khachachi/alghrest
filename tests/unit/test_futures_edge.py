"""Hand-derived net outcome statistics and verified synthetic source boundaries."""

import hashlib
import json
import math
import statistics
from datetime import timedelta
from decimal import Decimal, localcontext
from fractions import Fraction

import pytest
from hypothesis import given, settings, strategies as st

from backtesting.futures import (
    FuturesEdgeStudy,
    FuturesEntry,
    FuturesTrade,
    _edge_partitions,
    _net_metrics,
    futures_edge_analysis,
    run_futures_research,
    verify_futures_edge_study,
)
from backtesting.path_risk import LossStreakConfig
from core.advisory.models import EconomicCalendar
from tests.unit.test_futures_research import ROOTS, START, changed, request

pytestmark = pytest.mark.unit


def configuration(**changes):
    return LossStreakConfig.model_validate(dict(block_length=2, simulations=50, seed=42) | changes)


def observations(outcomes, dollars=None):
    """Typed synthetic statistic inputs; public research still requires path replay."""
    values = tuple(Decimal(str(v)) for v in outcomes)
    dollars = (
        tuple(Decimal(str(v)) for v in dollars)
        if dollars is not None
        else tuple(v * 10 for v in values)
    )
    records = []
    for i, (r, usd) in enumerate(zip(values, dollars, strict=True)):
        records.append(
            FuturesTrade(
                entry=FuturesEntry(
                    side="BUY",
                    signal_at=START + timedelta(days=i, hours=1),
                    entry_at=START + timedelta(days=i, hours=2),
                    entry_open=1000,
                    entry_fill=Decimal("1000.25"),
                    raw_invalidation=990,
                    initial_stop=990,
                    initial_risk_usd=10,
                ),
                exit_signal_at=START + timedelta(days=i, hours=3),
                exit_at=START + timedelta(days=i + 1),
                exit_open=1000,
                exit_fill=Decimal("999.75"),
                exit_stop=990,
                gross_usd=usd + 2,
                commission_usd=2,
                net_usd=usd,
                net_r=r,
            )
        )
    return tuple(records)


def metrics(outcomes, dollars=None):
    with localcontext() as context:
        context.prec = 80
        return _net_metrics(observations(outcomes, dollars), start=START, point_value=Decimal(5))


def research_input(winning=(False, True, False, False)):
    """Actual shared rules produce one fully observed trade per eight-bar episode."""
    value = request()
    bars = []
    for cycle, win in enumerate(winning * 3):
        template = value.records[0].candles[:8]
        levels = (
            [400, 400, 416, 424, 480, 440, 448, 440]
            if win
            else [400, 400, 416, 424, 396, 392, 400, 400]
        )
        for offset, original in enumerate(template):
            i = cycle * 8 + offset
            level = Decimal(levels[offset]) * Decimal(".25")
            b = original.model_dump()
            b.update(
                open_time=START + timedelta(days=i),
                close_time=START + timedelta(days=i + 1, milliseconds=-1),
                open=level,
                close=level,
                high=level + Decimal(".5"),
                low=level - Decimal(".5"),
            )
            if win and offset == 5:
                b.update(close=Decimal(104), low=Decimal("103.5"))
            bars.append(b)
    payload = value.model_dump()
    payload["records"][0].update(candles=bars, fetched_at=bars[-1]["close_time"])
    payload["records"][0]["quality"].update(
        heartbeat_at=bars[-1]["close_time"], sequences=tuple(range(len(bars)))
    )
    calendars = []
    for i, b in enumerate(bars):
        c = value.calendars[0].model_dump()
        c.update(
            version=str(i),
            observed_at=b["close_time"],
            coverage_start=b["open_time"],
            coverage_end=b["close_time"] + timedelta(days=1),
        )
        calendars.append(EconomicCalendar.model_validate(c))
    payload["calendars"] = tuple(calendars)
    n = len(winning) * 8
    payload["definition"]["research"]["research_end"] = bars[-1]["close_time"]
    for i, p in enumerate(payload["definition"]["research"]["partitions"]):
        p.update(start=bars[i * n]["open_time"], end=bars[(i + 1) * n - 1]["close_time"])
    return changed(value, **payload)


def test_hand_derived_mean_variance_skew_tail_profit_factor_and_recovery():
    m = metrics([2, -1, 0, -3, 4, 1])
    assert (m.observations, m.winners, m.losers, m.flat) == (6, 3, 2, 1)
    assert m.win_rate == Decimal(".5")
    with localcontext() as c:
        c.prec = 80
        assert m.average_winner_r == Decimal(7) / 3
    assert m.average_loser_r == -2
    assert m.expectancy_r == m.median_r == Decimal(".5")
    assert m.sample_variance_r_squared == Decimal("5.9")
    assert abs(m.sample_standard_deviation_r**2 - Decimal("5.9")) < Decimal("1e-25")
    assert m.adjusted_sample_skew == 0
    assert m.profit_factor_r == m.profit_factor_usd == Decimal("1.75")
    assert m.quantile05_r == -3 and m.empirical_es95_loss_r == 3
    assert m.total_net_usd == 30 and m.total_commission_usd == 12
    assert m.total_adverse_slippage_usd == 15
    assert m.max_closed_trade_drawdown_r == 4
    assert m.max_closed_trade_drawdown_usd == 40
    assert m.unrecovered_drawdown_r == 0 and m.max_underwater_trades == 4
    assert m.longest_nonpositive_run == 3
    recovery = m.recoveries[0]
    assert (recovery.peak_trade, recovery.trough_trade, recovery.recovery_trade) == (1, 4, 5)
    assert recovery.depth_r == 4 and recovery.elapsed_calendar_days == 4


def test_adjusted_skew_matches_independent_float_moment_formula():
    values = [-1, 0, 1, 5]
    m = metrics(values)
    mean = statistics.mean(values)
    population_variance = statistics.pvariance(values)
    third = statistics.mean([(v - mean) ** 3 for v in values])
    expected = math.sqrt(4 * 3) / 2 * third / population_variance**1.5
    assert float(m.adjusted_sample_skew) == pytest.approx(expected)
    assert (
        metrics([-v for v in values]).adjusted_sample_skew == m.adjusted_sample_skew.copy_negate()
    )


@pytest.mark.parametrize("count", [19, 20, 21])
def test_fractional_tail_mass_not_ceiling_sample_average(count):
    m = metrics([-10, -9] + [1] * (count - 2))
    if count <= 20:
        assert m.quantile05_r == -10 and m.empirical_es95_loss_r == 10
    else:
        assert m.quantile05_r == -9
        with localcontext() as c:
            c.prec = 80
            assert m.empirical_es95_loss_r == Decimal(209) / 21
        assert m.empirical_es95_loss_r != Decimal("9.5")


@pytest.mark.parametrize(
    "outcomes,status,variance,skew",
    [
        ([1], "UNDEFINED_NO_LOSSES", None, None),
        ([-1], "FINITE", None, None),
        ([0], "UNDEFINED_ALL_FLAT", None, None),
        ([0, 0, 0], "UNDEFINED_ALL_FLAT", Decimal(0), None),
        ([1, 1, 1], "UNDEFINED_NO_LOSSES", Decimal(0), None),
        ([-1, -1, -1], "FINITE", Decimal(0), None),
    ],
)
def test_no_loss_flat_single_observation_and_zero_variance_are_explicit(
    outcomes, status, variance, skew
):
    m = metrics(outcomes)
    assert m.profit_factor_state == status
    assert m.sample_variance_r_squared == variance and m.adjusted_sample_skew == skew
    assert (
        m.average_winner_r is None if not any(v > 0 for v in outcomes) else m.average_winner_r > 0
    )
    assert m.average_loser_r is None if not any(v < 0 for v in outcomes) else m.average_loser_r < 0
    assert m.profit_factor_r == 0 if status == "FINITE" else m.profit_factor_r is None
    assert "Infinity" not in m.model_dump_json() and "NaN" not in m.model_dump_json()


def test_nonpositive_boundaries_and_distinct_dollar_r_profit_factors():
    m = metrics([-Decimal("1e-40"), 0, Decimal("1e-40")])
    assert (m.winners, m.losers, m.flat) == (1, 1, 1)
    assert m.longest_nonpositive_run == 2
    different = metrics([2, -1], [10, -10])
    assert different.profit_factor_r == 2 and different.profit_factor_usd == 1
    assert different.expectancy_r == Decimal(".5") and different.total_net_usd == 0


def test_initial_and_unrecovered_underwater_episodes_keep_peak_and_duration():
    m = metrics([-1, 0, 1, -2, 1])
    assert m.max_closed_trade_drawdown_r == 2 and m.unrecovered_drawdown_r == 1
    assert m.max_underwater_trades == 3 and len(m.recoveries) == 2
    first, last = m.recoveries
    assert (first.peak_trade, first.trough_trade, first.recovery_trade) == (0, 1, 3)
    assert first.peak_at == START and first.elapsed_calendar_days == 3
    assert (last.peak_trade, last.trough_trade, last.recovery_trade, last.observed_until_trade) == (
        3,
        4,
        None,
        5,
    )
    assert last.depth_r == 2 and last.elapsed_calendar_days == 2


@given(values=st.lists(st.integers(-100, 100), min_size=1, max_size=45))
@settings(max_examples=70, deadline=None)
def test_statistics_match_fraction_oracle_and_path_invariants(values):
    m = metrics(values)
    with localcontext() as c:
        c.prec = 80
        expected = Fraction(sum(values), len(values))
        assert m.expectancy_r == Decimal(expected.numerator) / expected.denominator
        if len(values) > 1:
            v = sum((Fraction(x) - expected) ** 2 for x in values) / (len(values) - 1)
            assert abs(
                m.sample_variance_r_squared - Decimal(v.numerator) / v.denominator
            ) < Decimal("1e-72")
    assert m.winners + m.losers + m.flat == len(values)
    assert min(values) <= m.median_r <= max(values)
    cumulative = 0
    peak = 0
    maximum = 0
    for value in values:
        cumulative += value
        peak = max(peak, cumulative)
        maximum = max(maximum, peak - cumulative)
    assert m.max_closed_trade_drawdown_r == maximum
    assert m.max_closed_trade_drawdown_usd == maximum * 10
    assert m.unrecovered_drawdown_r == peak - cumulative


async def test_verified_public_study_computes_each_split_and_reuses_path_tables():
    source = await run_futures_research(research_input())
    study = await futures_edge_analysis(source, configuration=configuration())
    assert study.validation_state == "UNVALIDATED" and study.lifecycle == "EXPERIMENT"
    for part in study.partitions:
        assert part.state == "CALCULATED" and not part.reasons
        m = part.metrics
        assert (m.observations, m.winners, m.losers, m.flat) == (4, 1, 3, 0)
        assert m.total_net_usd == Decimal("-108")
        assert m.total_commission_usd == 8 and m.total_adverse_slippage_usd == 10
        assert (
            part.loss_runs.state == "CALCULATED"
            and part.loss_runs.empirical_loss_fraction == Decimal(".75")
        )
        assert len(part.loss_runs.iid_baseline) == len(part.loss_runs.bootstrap) == 16
        assert len(part.loss_runs.longest_runs) == 4
        assert all(sum(row.counts) == 50 for row in part.loss_runs.longest_runs)
    assert not study.trade_permitted and not study.execution_enabled
    reopened = FuturesEdgeStudy.model_validate_json(study.model_dump_json())
    assert await verify_futures_edge_study(reopened) == study


@pytest.mark.parametrize("root", ROOTS)
async def test_single_trade_all_roots_are_descriptive_without_invented_sample_variance(root):
    source = await run_futures_research(request(root))
    study = await futures_edge_analysis(source, configuration=configuration(block_length=1))
    for p in study.partitions:
        assert p.metrics.sample_variance_r_squared is None
        assert p.metrics.adjusted_sample_skew is None
        assert p.metrics.expectancy_r == source.partitions[0].trades[0].net_r
        assert p.loss_runs.empirical_loss_fraction == 1
        assert all(row.probability == 1 for row in p.loss_runs.iid_baseline)
    assert study.validation_state == "UNVALIDATED"


async def test_block_longer_than_history_does_not_invent_path_estimates():
    source = await run_futures_research(request())
    study = await futures_edge_analysis(source, configuration=configuration())
    for p in study.partitions:
        assert p.state == "CALCULATED" and p.metrics.observations == 1
        assert p.loss_runs.state == "UNKNOWN"
        assert p.loss_runs.reasons == ("block_exceeds_recorded_futures_outcomes",)
        assert p.loss_runs.empirical_loss_fraction is None
        assert p.loss_runs.iid_baseline == p.loss_runs.bootstrap == p.loss_runs.longest_runs == ()


async def test_complete_no_trade_history_has_unknown_metrics_and_no_probabilities():
    value = request()
    records = [value.records[0].model_dump()]
    for b in records[0]["candles"]:
        b["volume"] = 10
    source = await run_futures_research(changed(value, records=records))
    assert all(p.state == "COMPLETE" for p in source.partitions)
    study = await futures_edge_analysis(source, configuration=configuration())
    assert all(
        p.state == "UNKNOWN"
        and p.metrics is None
        and p.reasons == ("missing_closed_futures_outcomes",)
        for p in study.partitions
    )


async def test_incomplete_paths_do_not_cherry_pick_their_closed_trade_subset():
    value = research_input(winning=(False, False))
    records = [value.records[0].model_dump()]
    for i, b in enumerate(records[0]["candles"]):
        if i % 16 >= 11:
            b.update(open=106, close=106, high=Decimal("106.5"), low=Decimal("105.5"))
    source = await run_futures_research(changed(value, records=records))
    assert all(p.trades and p.censored for p in source.partitions)
    study = await futures_edge_analysis(source, configuration=configuration(block_length=1))
    for p in study.partitions:
        assert p.state == "UNKNOWN" and p.metrics is None and p.loss_runs.state == "UNKNOWN"
        assert p.reasons == ("incomplete_futures_partition",)


@pytest.mark.parametrize(
    "tamper", ["source_digest", "mean", "tail", "recovery", "loss_run", "config", "permissions"]
)
async def test_saved_statistics_and_source_joins_reject_tampering(tamper):
    study = await futures_edge_analysis(
        await run_futures_research(research_input()), configuration=configuration()
    )
    payload = study.model_dump()
    if tamper == "source_digest":
        payload["source_sha256"] = "0" * 64
    elif tamper == "mean":
        payload["partitions"][2]["metrics"]["expectancy_r"] = 10000
    elif tamper == "tail":
        payload["partitions"][2]["metrics"]["empirical_es95_loss_r"] = 0
    elif tamper == "recovery":
        payload["partitions"][2]["metrics"]["recoveries"] = ()
    elif tamper == "loss_run":
        payload["partitions"][2]["loss_runs"]["bootstrap"][0]["probability"] = Decimal(".999999")
    elif tamper == "config":
        payload["configuration"]["block_length"] = 4
    elif tamper == "permissions":
        payload["trade_permitted"] = True
    with pytest.raises(ValueError):
        FuturesEdgeStudy.model_validate(payload)


async def test_public_analysis_replays_source_before_using_reported_pnl():
    source = await run_futures_research(request())
    p = source.partitions[2]
    corrupted = p.model_copy(
        update={
            "trades": (
                p.trades[0].model_copy(update={"net_usd": Decimal(999), "net_r": Decimal(999)}),
            )
        }
    )
    source = source.model_copy(update={"partitions": (*source.partitions[:2], corrupted)})
    with pytest.raises(ValueError, match="replay mismatch"):
        await futures_edge_analysis(source, configuration=configuration(block_length=1))


async def test_self_consistent_forged_summary_still_requires_underlying_path_replay():
    study = await futures_edge_analysis(
        await run_futures_research(request()), configuration=configuration(block_length=1)
    )
    p = study.source.partitions[2]
    corrupted = p.model_copy(
        update={
            "trades": (
                p.trades[0].model_copy(update={"net_usd": Decimal(999), "net_r": Decimal(999)}),
            )
        }
    )
    source = study.source.model_copy(
        update={"partitions": (*study.source.partitions[:2], corrupted)}
    )
    digest = hashlib.sha256(
        json.dumps(source.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    value = FuturesEdgeStudy(
        source=source,
        source_sha256=digest,
        configuration=study.configuration,
        partitions=_edge_partitions(source, study.configuration),
    )
    with pytest.raises(ValueError, match="replay mismatch"):
        await verify_futures_edge_study(value)


async def test_oos_mutation_does_not_change_earlier_metrics_and_numeric_context_is_fixed():
    value = research_input()
    a = await futures_edge_analysis(
        await run_futures_research(value), configuration=configuration()
    )
    records = [value.records[0].model_dump()]
    for b in records[0]["candles"][64:]:
        for field in ("open", "high", "low", "close"):
            b[field] += 100
    b = await futures_edge_analysis(
        await run_futures_research(changed(value, records=records)), configuration=configuration()
    )
    assert a.partitions[:2] == b.partitions[:2]
    with localcontext() as c:
        c.prec = 6
        current = await futures_edge_analysis(
            await run_futures_research(value), configuration=configuration()
        )
    assert current == a
