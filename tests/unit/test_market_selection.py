"""Synthetic selection fixtures prove guards, not trading edge or pass probability."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from hypothesis import given, settings, strategies as st

from api.services.advisory import AdvisoryService
from connectors.advisory.replay import ReplayProvider
from connectors.advisory.storage import AdvisoryStore
from core.advisory.analysis import average_true_range
from core.advisory.models import CATALOG, PriceObservation
from core.advisory.selection import (
    CandidateEvidence,
    EvaluationFitEvidence,
    LosingStreakEstimate,
    MarketMeasurement,
    MarketSelectionPolicy,
    TradingEdgeEvidence,
    select_markets,
)
from core.data.models import MarketRegime
from tests.unit.test_advisory import clear_event_context
from tests.unit.test_market_data_provider import records

pytestmark = pytest.mark.unit
NOW = records(80)[0].fetched_at
ROOTS = ("MES", "MYM", "MNQ", "MGC")


def policy(roots=ROOTS, **changes):
    return MarketSelectionPolicy.model_validate(
        dict(
            id="synthetic-selector",
            version="fixture-v1",
            universe=roots,
            market_limits=[
                dict(
                    instrument_id=root,
                    min_liquidity_contracts_per_minute="0.1",
                    max_spread_ticks=2,
                    max_slippage_ticks=2,
                    min_atr_ticks="0.1",
                    max_atr_ticks=100,
                    max_quote_age_seconds=10,
                    max_measurement_age_seconds=10,
                )
                for root in roots
            ],
            evaluation_policy_id="synthetic-evaluation",
            evaluation_policy_version="fixture-v1",
            cost_model_version="synthetic-costs-v1",
            simulator_version="synthetic-rule-exact-v1",
            confidence_level="0.95",
            simulation_horizon_trades=100,
            simulation_horizon_days=30,
            minimum_oos_trades=100,
            minimum_simulations=1000,
            liquidity_lookback_bars=4,
            max_research_age_seconds=86400,
            max_failure_probability="0.4",
            max_drawdown_fraction="0.25",
            max_cvar95_loss_r=5,
            max_variance_r_squared=5,
            max_five_loss_probability_100="0.3",
            max_evaluation_cost_usd=500,
            backup_mode="distinct_exposure_group",
        )
        | changes
    )


def edge(root="MNQ", **changes):
    return TradingEdgeEvidence.model_validate(
        dict(
            id=f"synthetic-edge-{root}",
            version="fixture-v1",
            instrument_id=root,
            strategy_id="synthetic-strategy",
            strategy_version="fixture-v1",
            risk_configuration_id="synthetic-risk-v1",
            risk_percent="0.5",
            origin="synthetic",
            source_reference="SYNTHETIC, NO RESEARCH CONCLUSION",
            dataset_id="synthetic-dataset",
            dataset_sha256="a" * 64,
            available_at=NOW,
            train_start=NOW - timedelta(days=2000),
            train_end=NOW - timedelta(days=1000),
            validation_start=NOW - timedelta(days=999),
            validation_end=NOW - timedelta(days=500),
            oos_start=NOW - timedelta(days=499),
            oos_end=NOW - timedelta(days=1),
            lifecycle="APPROVED",
            supported_regimes=(MarketRegime.NEUTRAL,),
            costs_included=True,
            walk_forward_verified=True,
            final_holdout_untuned=True,
            cost_model_version="synthetic-costs-v1",
            assumed_slippage_ticks=2,
            oos_trades=200,
            expectancy_r="0.5",
            expectancy_lower_bound_r="0.2",
            confidence_level="0.95",
            median_r="0.1",
            variance_r_squared=1,
            cvar95_loss_r=2,
            max_drawdown_fraction="0.1",
            losing_streaks=[
                LosingStreakEstimate(horizon_trades=h, loss_run=r, probability="0.1")
                for h in (10, 25, 50, 100)
                for r in (2, 3, 4, 5)
            ],
        )
        | changes
    )


def fit(root="MNQ", **changes):
    return EvaluationFitEvidence.model_validate(
        dict(
            id=f"synthetic-fit-{root}",
            version="fixture-v1",
            edge_id=f"synthetic-edge-{root}",
            edge_version="fixture-v1",
            available_at=NOW,
            source_reference="SYNTHETIC, NO PASS-RATE CONCLUSION",
            evaluation_policy_id="synthetic-evaluation",
            evaluation_policy_version="fixture-v1",
            cost_model_version="synthetic-costs-v1",
            simulator_version="synthetic-rule-exact-v1",
            seed=42,
            horizon_trades=100,
            horizon_days=30,
            simulations=1000,
            passed=600,
            failed=300,
            censored=100,
            rule_exact_verified=True,
            dependence_preserved=True,
            costs_included=True,
            confidence_level="0.95",
            pass_probability_lower_bound="0.55",
            failure_probability_upper_bound="0.35",
            daily_loss_breach_probability="0.1",
            drawdown_breach_probability="0.2",
            progression_breach_probability=0,
            median_days_to_pass=10,
            p95_days_to_pass=20,
            expected_evaluation_cost_usd=200,
        )
        | changes
    )


def candidate(root="MNQ", **changes):
    tick = CATALOG[root].tick_size
    return CandidateEvidence.model_validate(
        dict(
            id=f"synthetic-candidate-{root}",
            version="fixture-v1",
            available_at=NOW,
            instrument_id=root,
            measurement=MarketMeasurement(
                known_at=NOW,
                source_reference="SYNTHETIC order-quality observation",
                quote=PriceObservation(
                    symbol=root + "Z26",
                    price=180,
                    bid=180 - tick,
                    ask=180 + tick,
                    timestamp=NOW,
                    source="https://example.com/synthetic-book",
                ),
                slippage_ticks=1,
                regime=MarketRegime.NEUTRAL,
                regime_version="synthetic-regime-v1",
            ),
            edge=edge(root),
            fit=fit(root),
            eligibility_confirmed=True,
            eligibility_reference="SYNTHETIC eligibility, no real prop-firm claim",
        )
        | changes
    )


def snapshots(roots=ROOTS):
    return {
        root: records(80, root=root, contract=root + "Z26")[0].model_copy(
            update={"data_mode": "replay"}
        )
        for root in roots
    }


def context(roots=ROOTS):
    return {
        root: clear_event_context(NOW, root)["calendar"].model_copy(
            update={"id": f"fixture-{root}"}
        )
        for root in roots
    }


def select(
    *, roots=ROOTS, inputs=None, markets=None, calendars=None, rules=None, now=NOW, mode="replay"
):
    return select_markets(
        snapshots(roots) if markets is None else markets,
        {root: candidate(root) for root in roots} if inputs is None else inputs,
        context(roots) if calendars is None else calendars,
        interval="15m",
        now=now,
        mode=mode,
        policy=rules if rules is not None else policy(roots),
        event_policy=clear_event_context(NOW)["event_policy"],
    )


def test_no_policy_or_research_never_implies_a_default_primary():
    result = select_markets(
        {}, {}, {}, interval="15m", now=NOW, mode="replay", policy=None, event_policy=None
    )
    assert result.primary is result.backup is None and result.ranked == ()
    assert {row.instrument_id for row in result.assessments} == set(ROOTS)
    assert all("missing_research_evidence" in row.reasons for row in result.assessments)
    assert result.reasons == ("no_qualified_market",) and not result.trade_permitted


def test_selection_has_one_primary_and_at_most_one_backup_with_shared_exposure_guard():
    result = select()
    assert result.primary == "MES" and result.backup == "MGC"
    assert result.ranked == ("MES", "MGC", "MNQ", "MYM")
    assert all(row.eligible for row in result.assessments)
    assert result.scope == "research_nomination" and not result.trade_permitted
    assert not result.simultaneous_use_permitted and not result.execution_enabled
    row = next(r for r in result.assessments if r.instrument_id == "MNQ")
    assert row.atr_ticks == 12 and row.spread_ticks == 2
    assert row.liquidity_contracts_per_minute == Decimal(2) / 3
    assert row.market.quality.quote == row.evidence.measurement.quote
    original = snapshots()
    select(markets=original)
    assert all(value.quality.quote is None for value in original.values())


def test_higher_pass_fit_cannot_override_negative_edge():
    inputs = {root: candidate(root) for root in ROOTS}
    inputs["MNQ"] = candidate(
        "MNQ",
        edge=edge(expectancy_r="-0.1", expectancy_lower_bound_r="-0.2"),
        fit=fit(
            passed=900,
            failed=50,
            censored=50,
            pass_probability_lower_bound="0.85",
            failure_probability_upper_bound="0.1",
            daily_loss_breach_probability=0,
            drawdown_breach_probability=0,
        ),
    )
    result = select(inputs=inputs)
    assert "MNQ" not in result.ranked
    assert (
        "nonpositive_oos_edge"
        in next(r for r in result.assessments if r.instrument_id == "MNQ").reasons
    )


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"lifecycle": "SHADOW"}, "strategy_not_approved"),
        ({"costs_included": False}, "unverified_edge_validation"),
        ({"walk_forward_verified": False}, "unverified_edge_validation"),
        ({"final_holdout_untuned": False}, "unverified_edge_validation"),
        ({"oos_trades": 99}, "insufficient_oos_trades"),
        ({"expectancy_lower_bound_r": 0}, "nonpositive_oos_edge"),
        ({"max_drawdown_fraction": "0.25"}, "drawdown_limit"),
        ({"cvar95_loss_r": "5.00001"}, "tail_risk_limit"),
        ({"variance_r_squared": "5.00001"}, "variance_limit"),
        ({"cost_model_version": "other"}, "cost_model_mismatch"),
        ({"confidence_level": "0.9"}, "confidence_level_mismatch"),
        ({"losing_streaks": ()}, "incomplete_losing_streak_evidence"),
        ({"supported_regimes": (MarketRegime.RISK_ON,)}, "regime_incompatible"),
        ({"assumed_slippage_ticks": "0.9"}, "optimistic_slippage_assumption"),
    ],
)
def test_unqualified_edge_is_filtered(changes, reason):
    result = select(roots=("MNQ",), inputs={"MNQ": candidate(edge=edge(**changes))})
    assert result.primary is None and reason in result.assessments[0].reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"rule_exact_verified": False}, "unverified_evaluation_fit"),
        ({"dependence_preserved": False}, "unverified_evaluation_fit"),
        ({"costs_included": False}, "unverified_evaluation_fit"),
        ({"evaluation_policy_version": "other"}, "incomparable_evaluation_fit"),
        ({"cost_model_version": "other"}, "incomparable_evaluation_fit"),
        ({"horizon_days": 31}, "incomparable_evaluation_fit"),
        ({"horizon_trades": 101}, "incomparable_evaluation_fit"),
        ({"simulator_version": "other"}, "incomparable_simulation_method"),
        ({"confidence_level": "0.9"}, "incomparable_simulation_method"),
        ({"failure_probability_upper_bound": "0.40001"}, "failure_probability_limit"),
        ({"expected_evaluation_cost_usd": "500.00001"}, "evaluation_cost_limit"),
    ],
)
def test_unqualified_fit_is_filtered(changes, reason):
    result = select(roots=("MNQ",), inputs={"MNQ": candidate(fit=fit(**changes))})
    assert result.primary is None and reason in result.assessments[0].reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"eligibility_confirmed": False}, "unconfirmed_market_eligibility"),
        ({"eligibility_reference": None}, "unconfirmed_market_eligibility"),
        ({"measurement": None}, "missing_market_measurement"),
        ({"edge": None, "fit": None}, "missing_trading_edge"),
        ({"fit": None}, "missing_evaluation_fit"),
    ],
)
def test_missing_inputs_are_not_zero_scores(changes, reason):
    result = select(roots=("MNQ",), inputs={"MNQ": candidate(**changes)})
    assert result.primary is None and reason in result.assessments[0].reasons


@pytest.mark.parametrize(
    "fault",
    [
        "bar",
        "calendar",
        "heartbeat",
        "sequence",
        "measurement",
        "quote",
        "conflict",
        "identity",
        "provenance",
    ],
)
def test_guard_faults_cannot_be_overridden_by_perfect_fit(fault):
    values = snapshots(("MNQ",))
    data = {"MNQ": candidate()}
    calendars = context(("MNQ",))
    if fault == "bar":
        values["MNQ"].candles[-1].high = Decimal(1)
    elif fault == "calendar":
        calendars = {}
    elif fault == "heartbeat":
        values["MNQ"].quality = values["MNQ"].quality.model_copy(update={"heartbeat_at": None})
    elif fault == "sequence":
        values["MNQ"].quality = values["MNQ"].quality.model_copy(
            update={"sequence_mode": "required"}
        )
    elif fault == "measurement":
        data["MNQ"] = candidate().model_copy(
            update={
                "measurement": candidate().measurement.model_copy(
                    update={"slippage_ticks": Decimal(-1)}
                )
            }
        )
    elif fault == "quote":
        q = data["MNQ"].measurement.quote.model_copy(update={"symbol": "NQZ26"})
        data["MNQ"] = candidate(measurement=data["MNQ"].measurement.model_copy(update={"quote": q}))
    elif fault == "conflict":
        values["MNQ"].quality = values["MNQ"].quality.model_copy(
            update={
                "quote": data["MNQ"].measurement.quote.model_copy(update={"price": Decimal(181)})
            }
        )
    elif fault == "identity":
        values["MNQ"] = values["MNQ"].model_copy(
            update={"instrument_id": "NQ", "contract": "NQZ26"}
        )
    else:
        values["MNQ"].data_mode = "user_import"
    result = select(roots=("MNQ",), inputs=data, markets=values, calendars=calendars)
    assert result.primary is None and result.ranked == () and not result.trade_permitted


@pytest.mark.parametrize(
    "field,limit,strict",
    [
        ("expectancy_lower_bound_r", Decimal(0), True),
        ("max_drawdown_fraction", Decimal("0.25"), True),
        ("cvar95_loss_r", Decimal(5), False),
        ("variance_r_squared", Decimal(5), False),
    ],
)
@pytest.mark.parametrize("epsilon", [Decimal("-0.000001"), Decimal(0), Decimal("0.000001")])
def test_edge_limits_at_epsilon(field, limit, strict, epsilon):
    changed = {field: limit + epsilon}
    if field == "expectancy_lower_bound_r":
        changed["expectancy_r"] = 1
    result = select(roots=("MNQ",), inputs={"MNQ": candidate(edge=edge(**changed))})
    allowed = (
        epsilon > 0
        if field == "expectancy_lower_bound_r"
        else epsilon < 0 if strict else epsilon <= 0
    )
    assert (result.primary == "MNQ") is allowed


def test_censored_trials_and_absence_of_success_are_explicit():
    value = fit()
    assert value.pass_probability == Decimal("0.6") and value.failure_probability == Decimal("0.3")
    zero = fit(
        passed=0,
        failed=900,
        censored=100,
        pass_probability_lower_bound=0,
        failure_probability_upper_bound="0.95",
        median_days_to_pass=None,
        p95_days_to_pass=None,
    )
    result = select(
        roots=("MNQ",),
        inputs={"MNQ": candidate(fit=zero)},
        rules=policy(("MNQ",), max_failure_probability=1),
    )
    assert "no_simulated_passes" in result.assessments[0].reasons and result.primary is None


def test_unknown_regime_missing_limits_short_bars_and_correlated_backup():
    unknown = candidate(measurement=candidate().measurement.model_copy(update={"regime": None}))
    assert (
        "unknown_regime" in select(roots=("MNQ",), inputs={"MNQ": unknown}).assessments[0].reasons
    )
    assert select(roots=("MNQ",), rules=policy(("MNQ",), market_limits=())).primary is None
    values = snapshots(("MNQ",))
    values["MNQ"].candles = values["MNQ"].candles[-14:]
    assert (
        "insufficient_selection_bars"
        in select(roots=("MNQ",), markets=values).assessments[0].reasons
    )
    same = select(
        roots=("MNQ", "MES"), rules=policy(("MNQ", "MES"), backup_mode="alternative_with_warning")
    )
    assert same.primary == "MES" and same.backup == "MNQ"
    assert (
        same.reasons == ("correlated_backup_alternative_only",)
        and not same.simultaneous_use_permitted
    )
    assert select(roots=("MNQ", "MES")).backup is None


def test_synthetic_records_cannot_nominate_a_current_market():
    values = {k: v.model_copy(update={"data_mode": "user_import"}) for k, v in snapshots().items()}
    result = select(markets=values, mode="current")
    assert result.primary is None and all(
        "synthetic_current_evidence" in row.reasons for row in result.assessments
    )


def test_shared_atr_has_no_fabricated_short_history():
    bars = snapshots()["MNQ"].candles
    assert average_true_range(bars) == 3 and average_true_range(bars[:14]) is None
    with pytest.raises(ValueError):
        average_true_range(bars, 0)


async def test_replay_service_nomination_reuses_guards_and_archived_known_at_evidence(tmp_path):
    dataset = [records(80, root=root, contract=root + "Z26")[0] for root in ROOTS]
    provider = ReplayProvider(
        dataset, calendars=list(context().values()), research=[candidate(root) for root in ROOTS]
    )
    store = AdvisoryStore(str(tmp_path / "selection.sqlite3"))
    service = AdvisoryService(
        store,
        Mock(),
        provider=provider,
        clock=lambda: NOW,
        research_reader=provider.research,
        calendar_reader=provider.calendar,
        selection_policy=policy(),
        event_policy=clear_event_context(NOW)["event_policy"],
    )
    first = await service.selection()
    assert first.primary == "MES" and first.backup == "MGC" and service.cache == {}
    saved = AdvisoryStore(str(tmp_path / "selection.sqlite3")).selection(first.id)
    assert saved == first
    repeated = await service.selection()
    assert repeated.model_dump(exclude={"id"}) == first.model_dump(exclude={"id"})
    assert store.selection("missing") is None


async def test_current_service_missing_evidence_and_source_faults_never_select(
    tmp_path, monkeypatch
):
    provider = Mock(mode="current", read=AsyncMock(side_effect=ValueError("missing data")))
    store = AdvisoryStore(str(tmp_path / "empty.sqlite3"))
    monkeypatch.setattr("api.services.advisory.time.monotonic", lambda: 10)
    service = AdvisoryService(
        store,
        Mock(),
        provider=provider,
        clock=lambda: NOW,
        research_reader=lambda *args: (_ for _ in ()).throw(ValueError("missing research")),
        calendar_reader=lambda *args: (_ for _ in ()).throw(ValueError("missing calendar")),
    )
    result = await service.selection()
    assert result.primary is result.backup is None and provider.read.await_count == 4
    with pytest.raises(ValueError, match="few seconds"):
        await service.selection()
    provider.mode = "unknown"
    with pytest.raises(ValueError, match="provider mode"):
        await service.selection()


@settings(max_examples=60, derandomize=True, database=None)
@given(
    order=st.permutations(ROOTS),
    bound=st.decimals(
        min_value="0.01", max_value="0.5", places=3, allow_nan=False, allow_infinity=False
    ),
)
def test_property_ranking_is_order_independent_and_never_permits_execution(order, bound):
    inputs = {
        root: candidate(root, fit=fit(root, pass_probability_lower_bound=bound)) for root in order
    }
    first = select(roots=tuple(order), inputs=inputs)
    second = select(inputs=inputs)
    assert (first.primary, first.backup, first.ranked) == (
        second.primary,
        second.backup,
        second.ranked,
    )
    assert (
        not first.trade_permitted
        and not first.simultaneous_use_permitted
        and not first.execution_enabled
    )


@pytest.mark.parametrize(
    "kind,changes",
    [
        ("edge", {"instrument_id": "BTCUSDT"}),
        ("edge", {"validation_start": NOW - timedelta(days=2000)}),
        ("edge", {"expectancy_lower_bound_r": 1}),
        ("edge", {"supported_regimes": ("NEUTRAL", "NEUTRAL")}),
        (
            "edge",
            {"losing_streaks": [{"horizon_trades": 10, "loss_run": 2, "probability": ".1"}] * 2},
        ),
        ("fit", {"passed": 601}),
        ("fit", {"pass_probability_lower_bound": ".61"}),
        ("fit", {"failure_probability_upper_bound": ".29"}),
        ("fit", {"median_days_to_pass": None}),
        ("fit", {"median_days_to_pass": 21}),
        ("fit", {"p95_days_to_pass": 31}),
        ("fit", {"daily_loss_breach_probability": ".31"}),
        (
            "fit",
            {
                "passed": 0,
                "failed": 900,
                "pass_probability_lower_bound": 0,
                "failure_probability_upper_bound": 1,
            },
        ),
        ("candidate", {"instrument_id": "MGC"}),
        ("candidate", {"fit": fit(edge_version="other")}),
        ("candidate", {"edge": None}),
        ("candidate", {"available_at": NOW - timedelta(seconds=1)}),
        ("policy", {"universe": ("MNQ", "MNQ")}),
        ("policy", {"universe": ("ETHUSDT",)}),
        ("policy", {"market_limits": policy().market_limits * 2}),
        ("policy", {"universe": ("MNQ",)}),
        ("policy", {"max_drawdown_fraction": ".250001"}),
    ],
)
def test_evidence_validators_reject_incoherent_reported_facts(kind, changes):
    factory = {"edge": edge, "fit": fit, "candidate": candidate, "policy": policy}[kind]
    with pytest.raises(ValueError):
        factory(**changes)


def test_measurement_and_market_limit_invalid_time_and_order():
    m = candidate().measurement
    with pytest.raises(ValueError):
        MarketMeasurement.model_validate(
            m.model_copy(update={"known_at": NOW - timedelta(microseconds=1)}).model_dump()
        )
    row = policy().market_limits[0]
    with pytest.raises(ValueError):
        type(row).model_validate(
            row.model_copy(update={"max_atr_ticks": Decimal(".01")}).model_dump()
        )


@pytest.mark.parametrize(
    "fault",
    [
        "future-candidate",
        "stale-measurement",
        "future-measurement",
        "slippage",
        "stale-edge",
        "future-edge",
        "stale-fit",
        "future-fit",
        "five-loss",
        "liquidity",
        "volatility",
    ],
)
def test_known_time_cost_and_path_faults_block_the_candidate(fault):
    data = candidate()
    markets = snapshots(("MNQ",))
    changes = {}
    if fault == "future-candidate":
        data = candidate(available_at=NOW + timedelta(microseconds=1))
    elif fault in {"stale-measurement", "future-measurement"}:
        stamp = (
            NOW - timedelta(seconds=11) if fault.startswith("stale") else NOW + timedelta(seconds=1)
        )
        quote = data.measurement.quote.model_copy(update={"timestamp": min(stamp, NOW)})
        data = candidate(
            available_at=max(stamp, NOW),
            measurement=data.measurement.model_copy(update={"known_at": stamp, "quote": quote}),
        )
    elif fault == "slippage":
        data = candidate(
            measurement=data.measurement.model_copy(update={"slippage_ticks": Decimal(3)})
        )
    elif fault in {"stale-edge", "future-edge", "stale-fit", "future-fit"}:
        stamp = (
            NOW - timedelta(seconds=86401)
            if fault.startswith("stale")
            else NOW + timedelta(microseconds=1)
        )
        target = data.edge if fault.endswith("edge") else data.fit
        updates = {"available_at": stamp}
        if fault == "stale-edge":
            updates["oos_end"] = stamp - timedelta(seconds=1)
        data = candidate(
            available_at=max(stamp, NOW), **{fault.split("-")[1]: target.model_copy(update=updates)}
        )
    elif fault == "five-loss":
        runs = list(data.edge.losing_streaks)
        runs[-1] = runs[-1].model_copy(update={"probability": Decimal(".300001")})
        data = candidate(edge=edge(losing_streaks=tuple(runs)))
    elif fault == "liquidity":
        changes = {
            "market_limits": tuple(
                row.model_copy(update={"min_liquidity_contracts_per_minute": Decimal(1)})
                for row in policy(("MNQ",)).market_limits
            )
        }
    else:
        changes = {
            "market_limits": tuple(
                row.model_copy(update={"max_atr_ticks": Decimal(1)})
                for row in policy(("MNQ",)).market_limits
            )
        }
    result = select(
        roots=("MNQ",), inputs={"MNQ": data}, markets=markets, rules=policy(("MNQ",), **changes)
    )
    assert result.primary is None and result.assessments[0].reasons


@pytest.mark.parametrize(
    "field,base",
    [
        ("max_failure_probability", Decimal(".35")),
        ("max_evaluation_cost_usd", Decimal(200)),
        ("max_five_loss_probability_100", Decimal(".1")),
    ],
)
@pytest.mark.parametrize("epsilon", [Decimal("-.000001"), Decimal(0), Decimal(".000001")])
def test_policy_thresholds_at_epsilon(field, base, epsilon):
    result = select(roots=("MNQ",), rules=policy(("MNQ",), **{field: base + epsilon}))
    assert (result.primary == "MNQ") is (epsilon >= 0)


@pytest.mark.parametrize(
    "field,changes",
    [
        ("selection", {"primary": "MYM"}),
        ("selection", {"backup": "MES"}),
        ("selection", {"ranked": ()}),
        ("selection", {"policy": None}),
        ("selection", {"policy": policy(("MNQ",))}),
        ("assessment", {"instrument_id": "MNQ"}),
        ("assessment", {"exposure_group": "uncorrelated"}),
        ("assessment", {"contract": "MESM27"}),
        ("assessment", {"reasons": ("blocked",)}),
    ],
)
def test_stored_nomination_cannot_accept_corrupt_identity_or_permissions(field, changes):
    result = select()
    value = result if field == "selection" else result.assessments[0]
    with pytest.raises(ValueError):
        type(value).model_validate(value.model_copy(update=changes).model_dump())


def test_record_store_detects_corruption_and_keeps_one_hundred_recent_records(tmp_path):
    store = AdvisoryStore(str(tmp_path / "retention.sqlite3"))
    result = select(roots=("MNQ",))
    for i in range(102):
        store.save_selection(
            result.model_copy(update={"id": f"{i:03}", "generated_at": NOW + timedelta(seconds=i)})
        )
    assert store.selection("000") is None and store.selection("001") is None
    assert store.selection("101").primary == "MNQ"
    with store.connect() as db:
        db.execute("UPDATE selections SET created='corrupt' WHERE id='101'")
    with pytest.raises(ValueError, match="identity/time"):
        store.selection("101")
    with store.connect() as db:
        db.execute("UPDATE selections SET payload='{}' WHERE id='100'")
    with pytest.raises(ValueError):
        store.selection("100")


def test_research_archive_future_revisions_never_rewrite_past_known_evidence():
    old = candidate()
    future = candidate(
        id="future",
        version="v2",
        available_at=NOW + timedelta(seconds=1),
        edge=edge(lifecycle="RETIRED"),
    )
    provider = ReplayProvider([records(80)[0]], research=[future, old])
    assert provider.research("MNQ", NOW) == old
    assert provider.research("MNQ", NOW - timedelta(microseconds=1)) is None
    assert provider.research("MGC", NOW) is None
    assert provider.research("MNQ", future.available_at) == future
    with pytest.raises(ValueError):
        provider.research("unknown", NOW)
    with pytest.raises(ValueError):
        provider.research("MNQ", NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="Duplicate"):
        ReplayProvider([records(80)[0]], research=[old, old])
    with pytest.raises(ValueError, match="ambiguous"):
        ReplayProvider([records(80)[0]], research=[old, old.model_copy(update={"id": "other"})])
    # Mutating a nested caller-owned quote cannot alter the serialized archive.
    old.measurement.quote.price = Decimal(100)
    assert provider.research("MNQ", NOW).measurement.quote.price == 180


async def test_current_acquisition_latency_rechecks_guard_ages_at_return(tmp_path):
    values = {k: v.model_copy(update={"data_mode": "user_import"}) for k, v in snapshots().items()}
    data = {root: candidate(root, edge=edge(root, origin="historical")) for root in ROOTS}
    clock = iter([NOW, NOW + timedelta(seconds=11)])
    provider = Mock(
        mode="current", read=AsyncMock(side_effect=lambda query: values[query.instrument_id])
    )
    service = AdvisoryService(
        AdvisoryStore(str(tmp_path / "late.sqlite3")),
        Mock(),
        provider=provider,
        clock=lambda: next(clock),
        research_reader=lambda root, cut: data[root],
        calendar_reader=lambda root, cut: context()[root],
        selection_policy=policy(),
        event_policy=clear_event_context(NOW)["event_policy"],
    )
    result = await service.selection()
    assert result.generated_at == NOW + timedelta(seconds=11) and result.primary is None
    assert all("stale_or_future_measurement" in row.reasons for row in result.assessments)


def test_remaining_source_identity_and_configuration_faults_are_fail_closed():
    result = select(roots=("MNQ",), inputs={"MNQ": candidate("MGC")})
    assert result.primary is None and "invalid_research_evidence" in result.assessments[0].reasons
    with pytest.raises(ValueError, match="mode"):
        select(mode="unknown")
    result = select_markets(
        snapshots(),
        {root: candidate(root) for root in ROOTS},
        context(),
        interval="15m",
        now=NOW,
        mode="replay",
        policy=None,
        event_policy=clear_event_context(NOW)["event_policy"],
    )
    assert result.primary is None
    row = select().assessments[0]
    with pytest.raises(ValueError, match="research identity"):
        type(row).model_validate(row.model_copy(update={"evidence": candidate("MGC")}).model_dump())
    assert select(roots=("MNQ",), rules=policy(("MNQ",), minimum_simulations=1001)).primary is None


def test_corrupt_saved_backup_cannot_bypass_the_configured_exposure_constraint():
    value = select()
    with pytest.raises(ValueError, match="Backup exposure"):
        type(value).model_validate(value.model_copy(update={"backup": "MNQ"}).model_dump())
