"""Synthetic management extraction and immutable provenance; not futures edge."""

import hashlib
import importlib.util
import json
import os
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import numpy as np
import pandas as pd
import pandas_ta as ta
import pytest
from hypothesis import given, settings, strategies as st

from agents.tier4_strategies.breakout_hunter import BreakoutHunter
from connectors.advisory.replay import ReplayProvider
from connectors.advisory.storage import AdvisoryStore
from core.advisory.analysis import breakout_research_check, build_report
from core.advisory.data import MarketDataQuery
from core.advisory.models import StrategyResearchCheck
from core.advisory.strategies import StrategyRegistry
from core.data.models import MarketState, OrderSide, TradeProposal
from core.strategy_signals import (
    ATRManagementParameters,
    ATRTradePlan,
    ATRTradeStep,
    atr_entry_plan,
    atr_trailing_step,
    close_crossed_stop,
    seeded_range_atr,
)
from tests.factories import bar, position
from tests.unit.test_advisory import clear_event_context
from tests.unit.test_strategy_behavior import wire
from tests.unit.test_strategy_registry import definition
from tests.unit.test_strategy_signals import NOW, daily_market, frame, parameters, prices

pytestmark = pytest.mark.unit
ROOTS = ("MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG")


def management(**changes):
    return ATRManagementParameters.model_validate(
        dict(atr_period=14, atr_window=200, atr_stop_multiplier=2, proposed_target_r=3) | changes
    )


@pytest.fixture
def candidate():
    if os.getenv("ALGHREST_TEST_MANAGEMENT_ARCHIVE") == "1":
        path = Path(
            "artifacts/tcp25-goal/trade-management/before/src/agents/tier4_strategies/breakout_hunter.py"
        )
        spec = importlib.util.spec_from_file_location("management_archive_agent", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return wire(module.BreakoutHunter())
    return wire(BreakoutHunter())


async def test_entry_does_not_accept_zero_atr_or_mutate_local_position(candidate):
    await candidate._enter("BTC/USDT", OrderSide.BUY, 100, 0)
    candidate.publish.assert_not_awaited()
    assert candidate._positions == candidate._trailing_stops == {}


async def test_missing_indicator_cannot_be_replaced_with_percent_of_price(candidate):
    candidate._bars["BTC/USDT"].extend(bar() for _ in range(30))
    data = frame(30).drop(columns="ATRr_14")
    data.iloc[-1, data.columns.get_loc("close")] = 105
    data.iloc[-1, data.columns.get_loc("high")] = 110
    data.iloc[-1, data.columns.get_loc("volume")] = 30
    candidate._to_df = Mock(return_value=data)
    candidate._compute_indicators = lambda x: x
    candidate._enter = AsyncMock()
    await candidate._evaluate("BTC/USDT")
    candidate._enter.assert_not_awaited()


async def test_missing_current_price_is_not_zero_and_cannot_report_exit(candidate):
    candidate._trailing_stops["BTC/USDT"] = 96
    state = MarketState(symbol="BTC/USDT", price=100, prices={})
    assert not await candidate.should_exit(position(), state)


@pytest.mark.parametrize(
    "changes",
    [
        dict(atr_period=True),
        dict(atr_period=0),
        dict(atr_period=500),
        dict(atr_window=14),
        dict(atr_window=501),
        dict(atr_stop_multiplier=0),
        dict(proposed_target_r=-1),
        dict(atr_method="talib"),
        dict(exit_rule="target_first"),
        dict(contracts=1),
    ],
)
def test_management_manifest_is_explicit_bounded_and_nonpermissive(changes):
    with pytest.raises(ValueError):
        management(**changes)


@pytest.mark.parametrize("period", [1, 3, 14, 30])
def test_seeded_decimal_atr_matches_verified_installed_backend_without_future_bars(period):
    rng = np.random.default_rng(31)
    close = 100 + np.cumsum(rng.integers(-2, 3, 300))
    data = pd.DataFrame(dict(high=close + 2, low=close - 2, close=close, volume=10))
    cfg = management(atr_period=period)
    for cut in [period + 1, 40, 200, 201, 300]:
        current = data.iloc[max(0, cut - 200) : cut]
        expected = ta.atr(
            current.high, current.low, current.close, length=period, talib=False
        ).iloc[-1]
        actual = seeded_range_atr(list(data.iloc[:cut].itertuples()), cfg)
        assert float(actual) == pytest.approx(expected, abs=1e-11, rel=1e-12)
        changed = data.copy()
        changed.loc[cut:, "high"] = 100000
        assert seeded_range_atr(list(changed.iloc[:cut].itertuples()), cfg) == actual


def test_independent_hand_calculation_pins_seed_and_recursive_updates():
    rows = prices(count=4)
    rows[-1] = rows[-1]._replace(high=120, low=110, close=115)
    cfg = management(atr_period=3, atr_window=4)
    # First 3 true ranges are 10, then max(10,120-95,95-110)=25.
    assert seeded_range_atr(rows, cfg) == 15
    assert seeded_range_atr(rows[:3], cfg) is None
    flat = [x._replace(high=100, low=100, close=100) for x in rows]
    assert seeded_range_atr(flat, cfg) is None


@pytest.mark.parametrize("fault", ["nan", "inf", "negative", "bad_range", "text", "copied_params"])
def test_invalid_atr_input_cannot_produce_geometry(fault):
    rows = prices(count=30)
    cfg = management()
    if fault == "copied_params":
        cfg = cfg.model_copy(update={"atr_period": True})
    else:
        row = rows[-1]
        if fault == "nan":
            row = row._replace(close=Decimal("NaN"))
        elif fault == "inf":
            row = row._replace(high=Decimal("Infinity"))
        elif fault == "negative":
            row = row._replace(low=Decimal(-1))
        elif fault == "bad_range":
            row = row._replace(high=90, close=100)
        else:
            row = row._replace(low="bad")
        rows[-1] = row
    with pytest.raises(ValueError):
        seeded_range_atr(rows, cfg)


@pytest.mark.parametrize("side,stop,target", [("BUY", 96, 112), ("SELL", 104, 88)])
def test_entry_geometry_precedes_size_and_has_no_execution_or_quantity(side, stop, target):
    value = atr_entry_plan(side, Decimal(100), Decimal(2), management())
    assert (
        value.stop_distance == 4 and value.invalidation == stop and value.proposed_target == target
    )
    assert (
        value.lifecycle == "EXPERIMENT"
        and not value.trade_permitted
        and not value.execution_enabled
    )
    assert "contracts" not in value.model_dump() and "risk_budget" not in value.model_dump()
    assert ATRTradePlan.model_validate_json(value.model_dump_json()) == value
    for changes in [
        dict(invalidation=Decimal(100)),
        dict(stop_distance=Decimal(1)),
        dict(trade_permitted=True),
    ]:
        with pytest.raises(ValueError):
            ATRTradePlan.model_validate(value.model_copy(update=changes).model_dump())


@pytest.mark.parametrize("side", ["BUY", "SELL"])
@pytest.mark.parametrize("epsilon", [Decimal("-.000001"), Decimal(0), Decimal(".000001")])
def test_exit_checks_existing_stop_first_and_touch_preserves_legacy_strict_comparison(
    side, epsilon
):
    stop = Decimal(100)
    close = stop + epsilon
    expected = epsilon < 0 if side == "BUY" else epsilon > 0
    assert close_crossed_stop(side, close, stop) == expected
    value = atr_trailing_step(side, close, stop, None, management())
    assert value.action == ("EXIT" if expected else "NO_TRADE") and value.next_stop == stop
    assert value.atr is None and not value.execution_enabled


@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_ratchet_does_not_loosen_when_volatility_increases_or_price_retraces(side):
    cfg = management()
    old = Decimal(96 if side == "BUY" else 104)
    close = Decimal(110 if side == "BUY" else 90)
    first = atr_trailing_step(side, close, old, Decimal(2), cfg)
    assert first.action == "HOLD" and first.next_stop == Decimal(106 if side == "BUY" else 94)
    second = atr_trailing_step(
        side, Decimal(108 if side == "BUY" else 92), first.next_stop, Decimal(10), cfg
    )
    assert second.action == "HOLD" and second.next_stop == first.next_stop
    assert ATRTradeStep.model_validate_json(second.model_dump_json()) == second
    for changes in [dict(next_stop=Decimal(1)), dict(action="EXIT"), dict(execution_enabled=True)]:
        with pytest.raises(ValueError):
            ATRTradeStep.model_validate(second.model_copy(update=changes).model_dump())


@pytest.mark.parametrize(
    "atr", [None, Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")]
)
def test_unavailable_atr_blocks_new_ratchet_but_not_a_known_stop_crossing(atr):
    cfg = management()
    hold = atr_trailing_step("BUY", Decimal(100), Decimal(96), atr, cfg)
    exit = atr_trailing_step("BUY", Decimal(95), Decimal(96), atr, cfg)
    assert hold.action == "NO_TRADE" and hold.next_stop == 96
    assert exit.action == "EXIT" and exit.next_stop == 96 and exit.atr is None


@pytest.mark.parametrize(
    "side,price,atr",
    [
        ("UNKNOWN", Decimal(100), Decimal(2)),
        ("BUY", Decimal(100), Decimal(0)),
        ("BUY", Decimal(1), Decimal(2)),
        ("SELL", Decimal(1), Decimal(2)),
        ("BUY", Decimal(100), Decimal("1e-100")),
        ("SELL", Decimal(100), Decimal("1e-100")),
    ],
)
def test_nondirectional_unrepresentable_or_negative_geometry_is_rejected(side, price, atr):
    with pytest.raises(ValueError):
        atr_entry_plan(side, price, atr, management())


def test_unknown_or_invalid_position_state_is_not_coerced_to_short():
    with pytest.raises(ValueError):
        close_crossed_stop("UNKNOWN", Decimal(100), Decimal(96))
    with pytest.raises(ValueError):
        close_crossed_stop("BUY", Decimal(0), Decimal(96))
    with pytest.raises(ValueError):
        atr_trailing_step("BUY", Decimal(100), Decimal(0), Decimal(2), management())
    value = atr_trailing_step("BUY", Decimal(100), Decimal(96), Decimal("1e-100"), management())
    assert value.action == "NO_TRADE" and value.reason == "unrepresentable_trailing_geometry"


@pytest.mark.parametrize("side", ["BUY", "SELL"])
async def test_agent_entry_and_stop_ratchet_match_shared_plan(side):
    agent = wire(BreakoutHunter())
    enum = OrderSide(side)
    await agent._enter("BTC/USDT", enum, 100, 2)
    proposed = TradeProposal.model_validate(agent.publish.await_args.args[1])
    plan = atr_entry_plan(side, Decimal(100), Decimal(2), management())
    assert proposed.stop_loss == plan.invalidation and proposed.take_profit == plan.proposed_target
    old = agent._trailing_stops["BTC/USDT"]
    close = 110 if side == "BUY" else 90
    agent._update_trailing_stop("BTC/USDT", close, 2, "long" if side == "BUY" else "short")
    expected = atr_trailing_step(side, Decimal(close), Decimal(str(old)), Decimal(2), management())
    assert agent._trailing_stops["BTC/USDT"] == float(expected.next_stop)


@pytest.mark.parametrize("atr", [None, float("nan"), float("inf"), -1, 0, "bad"])
async def test_agent_unknown_atr_never_enters_and_existing_cross_can_still_exit(atr):
    agent = wire(BreakoutHunter())
    data = frame(30)
    data["ATRr_14"] = atr
    data.iloc[-1, data.columns.get_loc("close")] = 105
    data.iloc[-1, data.columns.get_loc("high")] = 110
    data.iloc[-1, data.columns.get_loc("volume")] = 30
    agent._bars["BTC/USDT"].extend(bar() for _ in range(30))
    agent._to_df = Mock(return_value=data)
    agent._compute_indicators = lambda x: x
    agent._enter = AsyncMock()
    await agent._evaluate("BTC/USDT")
    agent._enter.assert_not_awaited()
    agent._positions["BTC/USDT"] = "long"
    agent._trailing_stops["BTC/USDT"] = 106
    agent._exit = AsyncMock()
    await agent._evaluate("BTC/USDT")
    agent._exit.assert_awaited_once()


@pytest.mark.parametrize(
    "side,stop", [("UNKNOWN", 96), ("long", None), ("long", 0), ("long", float("nan"))]
)
async def test_agent_invalid_local_position_never_creates_or_updates_a_stop(side, stop):
    agent = wire(BreakoutHunter())
    agent._bars["BTC/USDT"].extend(bar() for _ in range(30))
    agent._to_df = Mock(return_value=frame(30))
    agent._compute_indicators = lambda x: x
    agent._positions["BTC/USDT"] = side
    if stop is not None:
        agent._trailing_stops["BTC/USDT"] = stop
    agent._exit = AsyncMock()
    agent._update_trailing_stop = Mock()
    await agent._evaluate("BTC/USDT")
    agent._exit.assert_not_awaited()
    agent._update_trailing_stop.assert_not_called()


def test_optional_manifest_preserves_old_registry_digest_and_requires_a_new_version(tmp_path):
    store = AdvisoryStore(str(tmp_path / "registry.sqlite3"))
    d = definition()
    r = store.register_strategy(
        d, expected_revision=store.strategy_registry().revision, reason="Research experiment"
    )
    old_payload = json.loads(r.model_dump_json())
    assert "management" not in old_payload["definition"]
    old_registry = dict(format_version="experiment-registry-v1", records=[old_payload])
    digest = hashlib.sha256(
        json.dumps(old_registry, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with store.connect() as db:
        db.execute(
            "UPDATE settings SET value=? WHERE key='strategy_registry'",
            (json.dumps(dict(revision=digest, registry=old_registry)),),
        )
    assert AdvisoryStore(str(tmp_path / "registry.sqlite3")).strategy_registry().revision == digest
    enriched = d.model_copy(update={"management": management()})
    with pytest.raises(ValueError, match="immutable"):
        store.register_strategy(enriched, expected_revision=digest, reason="Research experiment")
    new = definition(version="managed-v2", management=management())
    managed = store.register_strategy(new, expected_revision=digest, reason="Managed experiment")
    assert managed.definition.management == management() and new.revision != d.revision
    assert (
        StrategyRegistry.model_validate_json(store.strategy_registry().model_dump_json())
        == store.strategy_registry()
    )
    for cfg in [management(atr_period=40), management(atr_window=20)]:
        with pytest.raises(ValueError):
            definition(management=cfg)


@pytest.mark.parametrize("root", ROOTS)
def test_guarded_research_geometry_uses_same_definition_across_all_roots(root):
    source = daily_market(root)
    context = clear_event_context(NOW, root)
    value = breakout_research_check(
        root,
        "1d",
        source,
        parameters=parameters(),
        management_parameters=management(),
        now=NOW,
        **context,
    )
    assert value.state == "FEATURES_READY" and value.advice == "WAIT"
    assert value.management == atr_entry_plan(
        "BUY", value.features.close, seeded_range_atr(source.candles, management()), management()
    )
    assert (
        value.management_parameters == management()
        and not value.trade_permitted
        and not value.management.execution_enabled
    )
    assert StrategyResearchCheck.model_validate_json(value.model_dump_json()) == value


async def test_replay_and_current_management_match_with_captured_guard_provenance():
    source = daily_market()
    context = clear_event_context(NOW)
    provider = ReplayProvider([source], calendars=[context["calendar"]])
    replay = await provider.read(
        MarketDataQuery(instrument_id="MNQ", interval="1d", contract="MNQZ26", as_of=NOW)
    )
    direct = breakout_research_check(
        "MNQ",
        "1d",
        source,
        parameters=parameters(),
        management_parameters=management(),
        now=NOW,
        **context,
    )
    historical = breakout_research_check(
        "MNQ",
        "1d",
        replay,
        parameters=parameters(),
        management_parameters=management(),
        now=NOW,
        **context,
    )
    assert historical.features == direct.features and historical.management == direct.management
    with pytest.raises(ValueError):
        StrategyResearchCheck.model_validate(
            direct.model_copy(
                update={"management": direct.management.model_copy(update={"atr": Decimal(1)})}
            ).model_dump()
        )
    with pytest.raises(ValueError):
        StrategyResearchCheck.model_validate(
            direct.model_copy(update={"management": None}).model_dump()
        )


def test_report_captures_geometry_and_rejects_corruption_on_save_and_read(tmp_path):
    report = build_report("MNQ", "1d", daily_market(), [], [], now=NOW, **clear_event_context(NOW))
    assert report.strategy_research.management is not None
    store = AdvisoryStore(str(tmp_path / "reports.sqlite3"))
    store.save_report(report)
    assert store.report(report.id) == report.model_dump(mode="json")
    changed = report.strategy_research.model_copy(
        update={"management_parameters": management(atr_stop_multiplier=3)}
    )
    with pytest.raises(ValueError):
        store.save_report(report.model_copy(update={"strategy_research": changed}))
    with store.connect() as db:
        raw = json.loads(db.execute("SELECT payload FROM reports").fetchone()[0])
        raw["strategy_research"]["management"]["invalidation"] = "1"
        db.execute("UPDATE reports SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError):
        store.report(report.id)


def test_legacy_entry_only_report_roundtrip_does_not_invent_management():
    value = breakout_research_check(
        "MNQ", "1d", daily_market(), parameters=parameters(), now=NOW, **clear_event_context(NOW)
    )
    raw = value.model_dump(mode="json")
    raw.pop("management")
    raw.pop("management_parameters")
    restored = StrategyResearchCheck.model_validate(raw)
    assert restored.management is restored.management_parameters is None


@pytest.mark.parametrize("fault", ["params", "period", "geometry", "neutral", "clock", "source"])
def test_management_failures_and_non_directional_input_cannot_expose_geometry(fault):
    source = daily_market()
    cfg = management()
    context = clear_event_context(NOW)
    if fault == "params":
        cfg = cfg.model_copy(update={"atr_stop_multiplier": Decimal(0)})
    elif fault == "period":
        cfg = management(atr_period=100)
    elif fault == "geometry":
        cfg = management(atr_stop_multiplier=100)
    elif fault == "neutral":
        source = daily_market(close=Decimal(95), volume=Decimal(20))
    elif fault == "clock":
        source = source.model_copy(update={"fetched_at": NOW + timedelta(seconds=1)})
    else:
        source = None
    value = breakout_research_check(
        "MNQ", "1d", source, parameters=parameters(), management_parameters=cfg, now=NOW, **context
    )
    assert value.management is None
    assert value.state == ("WAIT" if fault == "neutral" else "NO_TRADE")


@given(st.integers(min_value=1, max_value=100), st.integers(min_value=1, max_value=100))
@settings(max_examples=80, derandomize=True)
def test_geometry_is_symmetric_and_ratchet_monotone_without_quantity_or_global_precision(
    gap, atr_value
):
    entry = Decimal(1000)
    atr = Decimal(atr_value) / 10
    cfg = management()
    with localcontext() as ctx:
        ctx.prec = 6
        long = atr_entry_plan("BUY", entry, atr, cfg)
        short = atr_entry_plan("SELL", entry, atr, cfg)
        assert long.stop_distance == short.stop_distance == 2 * atr
        assert long.invalidation + short.invalidation == 2 * entry
        assert long.proposed_target + short.proposed_target == 2 * entry
        a = atr_trailing_step("BUY", entry + gap, long.invalidation, atr, cfg)
        b = atr_trailing_step("SELL", entry - gap, short.invalidation, atr, cfg)
        assert a.next_stop >= long.invalidation and b.next_stop <= short.invalidation
        assert ctx.prec == 6


def test_actual_agent_indicator_bridge_uses_pinned_atr_and_preserves_input_frame():
    data = frame(30)
    original = data.copy(deep=True)
    actual = BreakoutHunter._compute_indicators(data)
    assert data.equals(original)
    expected = seeded_range_atr(list(data.itertuples()), management())
    assert actual.iloc[-1].ATRr_14 == float(expected)
    assert actual.ATRr_14.iloc[:-1].isna().all()
    data[["high", "low", "close"]] = 95
    flat = BreakoutHunter._compute_indicators(data)
    assert flat.ATRr_14.isna().all()


async def test_real_evaluation_bridge_uses_shared_atr_before_entry():
    agent = wire(BreakoutHunter())
    data = frame(30)
    data.iloc[-1, data.columns.get_loc("close")] = 105
    data.iloc[-1, data.columns.get_loc("high")] = 110
    data.iloc[-1, data.columns.get_loc("volume")] = 30
    agent._bars["BTC/USDT"].extend(bar() for _ in range(30))
    agent._to_df = Mock(return_value=data)
    agent._enter = AsyncMock()
    await agent._evaluate("BTC/USDT")
    expected = seeded_range_atr(list(data.itertuples()), management())
    assert agent._enter.await_args.args == ("BTC/USDT", OrderSide.BUY, 105, float(expected))


@pytest.mark.parametrize("atr", [float("nan"), float("inf"), -1])
async def test_invalid_direct_entry_geometry_cannot_read_budget_or_emit(candidate, atr):
    await candidate._enter("BTC/USDT", OrderSide.BUY, 100, atr)
    candidate.publish.assert_not_awaited()
    candidate.state.get_portfolio.assert_not_awaited()
    assert not candidate._positions and not candidate._trailing_stops


async def test_unknown_agent_side_is_not_implicitly_short_and_bad_price_is_not_an_exit(candidate):
    await candidate._enter("BTC/USDT", "UNKNOWN", 100, 2)
    candidate.publish.assert_not_awaited()
    candidate._trailing_stops["BTC/USDT"] = 96
    assert not await candidate.should_exit(
        position(), MarketState(symbol="BTC/USDT", price=0, prices={"BTC/USDT": Decimal(0)})
    )
    candidate._update_trailing_stop("BTC/USDT", 100, 2, "UNKNOWN")
    assert candidate._trailing_stops["BTC/USDT"] == 96
    candidate._positions["BTC/USDT"] = "long"
    candidate._update_trailing_stop("BTC/USDT", 100, float("nan"), "long")
    assert candidate._trailing_stops["BTC/USDT"] == 96
    candidate._trailing_stops["BTC/USDT"] = float("nan")
    candidate._update_trailing_stop("BTC/USDT", 100, 2, "long")
    assert np.isnan(candidate._trailing_stops["BTC/USDT"])


def test_geometry_cannot_be_attached_to_neutral_or_undeclared_report_parameters():
    context = clear_event_context(NOW)
    managed = breakout_research_check(
        "MNQ",
        "1d",
        daily_market(),
        parameters=parameters(),
        management_parameters=management(),
        now=NOW,
        **context,
    )
    with pytest.raises(ValueError, match="declared parameters"):
        StrategyResearchCheck.model_validate(
            managed.model_copy(update={"management_parameters": None}).model_dump()
        )
    neutral = breakout_research_check(
        "MNQ",
        "1d",
        daily_market(close=Decimal(95)),
        parameters=parameters(),
        management_parameters=management(),
        now=NOW,
        **context,
    )
    with pytest.raises(ValueError, match="declared parameters"):
        StrategyResearchCheck.model_validate(
            neutral.model_copy(update={"management": managed.management}).model_dump()
        )
    with pytest.raises(ValueError, match="cannot expose"):
        StrategyResearchCheck.model_validate(
            managed.model_copy(
                update={
                    "state": "NO_TRADE",
                    "advice": "NO TRADE",
                    "features": None,
                    "reasons": ("blocked",),
                }
            ).model_dump()
        )


def test_atr_precision_and_geometry_reproduction_are_independent_of_global_context():
    rows = prices(count=30)
    rows[-1] = rows[-1]._replace(high=120, low=110, close=115)
    cfg = management()
    expected = seeded_range_atr(rows, cfg)
    with localcontext() as ctx:
        ctx.prec = 4
        atr = seeded_range_atr(rows, cfg)
        assert atr == expected and ctx.prec == 4
        plan = atr_entry_plan("BUY", Decimal(1000), atr, cfg)
        assert ATRTradePlan.model_validate_json(plan.model_dump_json()) == plan
