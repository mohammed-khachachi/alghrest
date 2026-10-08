"""Shared rule parity on synthetic bars, not strategy profitability evidence."""

from collections import namedtuple
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pandas as pd
import pytest
from hypothesis import given, settings, strategies as st

from agents.tier4_strategies import breakout_hunter as legacy
from backtesting.engine import BacktestEngine
from core.advisory.analysis import breakout_research_check, build_report
from core.advisory.models import Candle, MarketDataEvidence, MarketSnapshot, StrategyResearchCheck
from core.strategy_signals import BreakoutParameters, VolumeBreakoutKernel
from tests.factories import bar
from tests.unit.test_advisory import clear_event_context

NOW = datetime(2026, 10, 6, 15, tzinfo=UTC)
PriceRow = namedtuple("PriceRow", "high low close volume")


def parameters(**changes):
    return BreakoutParameters.model_validate(
        dict(range_period=20, minimum_bars=30, volume_multiplier=2) | changes
    )


def prices(close=Decimal(105), volume=Decimal(20), count=30):
    previous = [PriceRow(Decimal(100), Decimal(90), Decimal(95), Decimal(10))] * (count - 1)
    return [*previous, PriceRow(max(Decimal(100), close), min(Decimal(90), close), close, volume)]


def daily_market(root="MNQ", close=Decimal(105), volume=Decimal(20), count=80, **changes):
    candles = [
        Candle(
            open_time=NOW - timedelta(days=count - i),
            close_time=NOW - timedelta(days=count - i - 1, milliseconds=1),
            open=95,
            high=value.high,
            low=value.low,
            close=value.close,
            volume=value.volume,
        )
        for i, value in enumerate(prices(close, volume, count))
    ]
    return MarketSnapshot.model_validate(
        dict(
            instrument_id=root,
            interval="1d",
            source="https://example.com/SYNTHETIC-daily",
            fetched_at=NOW,
            candles=candles,
            data_mode="user_import",
            contract=root + "Z26",
            quality=MarketDataEvidence(
                provider_id="SYNTHETIC-daily",
                provider_state="active",
                heartbeat_at=NOW,
                sequence_mode="not_applicable",
            ),
        )
        | changes
    )


def research(market=None, root="MNQ", **changes):
    context = clear_event_context(NOW, root)
    return breakout_research_check(
        **(
            dict(
                instrument_id=root,
                interval="1d",
                market=daily_market(root) if market is None else market,
                parameters=parameters(),
                now=NOW,
                calendar=context["calendar"],
                event_policy=context["event_policy"],
            )
            | changes
        )
    )


pytestmark = pytest.mark.unit


def frame(count=40, volume=10):
    return pd.DataFrame(
        {
            "high": [100.0] * count,
            "low": [90.0] * count,
            "close": [95.0] * count,
            "volume": [float(volume)] * count,
            "ATRr_14": [2.0] * count,
        },
        index=pd.date_range("2026-01-01", periods=count, tz="UTC"),
    )


async def test_zero_baseline_volume_cannot_confirm_an_agent_breakout():
    data = frame(30, volume=0)
    data.iloc[-1, data.columns.get_loc("close")] = 105
    data.iloc[-1, data.columns.get_loc("high")] = 110
    agent = legacy.BreakoutHunter()
    agent._bars["BTC/USDT"].extend(bar() for _ in range(30))
    agent._to_df = Mock(return_value=data)
    agent._compute_indicators = lambda value: value
    agent._enter = AsyncMock()
    await agent._evaluate("BTC/USDT")
    agent._enter.assert_not_awaited()


def test_backtest_cannot_skip_the_immediately_preceding_high(monkeypatch):
    data = frame()
    data.iloc[-3, data.columns.get_loc("high")] = 200
    data.iloc[-2, data.columns.get_loc("close")] = 150
    data.iloc[-2, data.columns.get_loc("high")] = 160
    data.iloc[-2, data.columns.get_loc("volume")] = 30
    run = Mock()
    monkeypatch.setattr(BacktestEngine, "run", run)
    legacy.BreakoutHunter().backtest(data, {})
    assert not run.call_args.args[1].any()


@pytest.mark.parametrize(
    "close,volume,direction,reason",
    [
        (105, 20, "BUY", "above_range"),
        (85, 20, "SELL", "below_range"),
        (100, 20, "WAIT", "inside_range"),
        (90, 20, "WAIT", "inside_range"),
        (95, 20, "WAIT", "inside_range"),
        (105, 19, "WAIT", "volume_not_confirmed"),
    ],
)
def test_numeric_rule_matches_entry_direction_and_reports_features(
    close, volume, direction, reason
):
    value = VolumeBreakoutKernel(parameters()).evaluate(prices(Decimal(close), Decimal(volume)))
    assert value.direction == direction and value.reason == reason
    assert (
        value.previous_high == 100
        and value.previous_low == 90
        and value.previous_average_volume == 10
    )


@pytest.mark.parametrize("epsilon", [Decimal("-.0001"), Decimal(0), Decimal(".0001")])
def test_price_and_volume_decision_boundaries(epsilon):
    kernel = VolumeBreakoutKernel(parameters())
    assert (kernel.evaluate(prices(Decimal(100) + epsilon)).direction == "BUY") is (epsilon > 0)
    assert (kernel.evaluate(prices(Decimal(90) + epsilon)).direction == "SELL") is (epsilon < 0)
    assert (kernel.evaluate(prices(volume=Decimal(20) + epsilon)).direction == "BUY") is (
        epsilon >= 0
    )


@pytest.mark.parametrize(
    "fault",
    [
        "nan",
        "infinite",
        "negative_volume",
        "zero_price",
        "crossed_bar",
        "missing_field",
        "non_numeric",
        "parameters_copy",
    ],
)
def test_unknown_or_corrupt_numeric_inputs_cannot_generate_signal(fault):
    values = prices()
    kernel = VolumeBreakoutKernel(parameters())
    if fault == "nan":
        values[-1] = values[-1]._replace(close=Decimal("NaN"))
    elif fault == "infinite":
        values[-1] = values[-1]._replace(volume=Decimal("Infinity"))
    elif fault == "negative_volume":
        values[-1] = values[-1]._replace(volume=-1)
    elif fault == "zero_price":
        values[-1] = values[-1]._replace(low=0)
    elif fault == "crossed_bar":
        values[-1] = values[-1]._replace(high=1)
    elif fault == "missing_field":
        values[-1] = object()
    elif fault == "non_numeric":
        values[-1] = values[-1]._replace(volume="bad")
    else:
        kernel.parameters = kernel.parameters.model_copy(update={"range_period": True})
    with pytest.raises(ValueError):
        kernel.evaluate(values)


def test_warmup_zero_volume_and_parameter_shapes_remain_explicit():
    kernel = VolumeBreakoutKernel(parameters())
    assert kernel.evaluate(prices(count=29)) is None
    zero = [v._replace(volume=0) for v in prices()]
    assert kernel.evaluate(zero).reason == "unknown_volume_baseline"
    for changes in (
        {"minimum_bars": 20},
        {"range_period": True},
        {"volume_multiplier": 0},
        {"contracts": 10},
    ):
        with pytest.raises(ValueError):
            parameters(**changes)


@settings(max_examples=80, derandomize=True, database=None)
@given(
    close=st.decimals(
        min_value="80", max_value="110", places=4, allow_nan=False, allow_infinity=False
    ),
    volume=st.decimals(
        min_value="0", max_value="40", places=4, allow_nan=False, allow_infinity=False
    ),
)
def test_property_direction_matches_independent_range_and_liquidity_oracle(close, volume):
    values = prices(close, volume)
    value = VolumeBreakoutKernel(parameters()).evaluate(values)
    expected = "WAIT" if volume < 20 else "BUY" if close > 100 else "SELL" if close < 90 else "WAIT"
    assert value.direction == expected


@pytest.mark.parametrize("root", ["MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG"])
def test_guarded_experiment_uses_one_rule_for_all_research_roots(root):
    result = research(root=root)
    assert result.data_health.state == "HEALTHY" and result.event_risk.state == "CLEAR"
    assert result.state == "FEATURES_READY" and result.features.direction == "BUY"
    assert result.lifecycle == "EXPERIMENT" and result.advice == "WAIT"
    assert not result.trade_permitted and not result.execution_enabled


@pytest.mark.parametrize(
    "fault",
    [
        "no_data",
        "provider",
        "stale",
        "future",
        "missing_calendar",
        "intraday",
        "warmup",
        "zero_volume",
        "corrupt_market",
        "corrupt_parameters",
    ],
)
def test_failed_guards_or_missing_strategy_evidence_hide_directional_features(fault):
    market = daily_market()
    changes = {}
    if fault == "no_data":
        changes["market"] = None
    elif fault == "provider":
        market.quality = market.quality.model_copy(update={"provider_state": "unknown"})
    elif fault == "stale":
        changes["now"] = NOW + timedelta(days=2)
    elif fault == "future":
        market.fetched_at = NOW + timedelta(seconds=1)
    elif fault == "missing_calendar":
        changes["calendar"] = None
    elif fault == "intraday":
        changes["interval"] = "15m"
    elif fault == "warmup":
        market = daily_market(count=29)
    elif fault == "zero_volume":
        market = daily_market()
        market.candles = [v.model_copy(update={"volume": Decimal(0)}) for v in market.candles]
    elif fault == "corrupt_market":
        market = market.model_copy(update={"contract": "OTHER"})
    else:
        changes["parameters"] = parameters().model_copy(update={"range_period": True})
    value = (
        research(market=market, **changes)
        if fault != "no_data"
        else breakout_research_check("MNQ", "1d", None, parameters=parameters(), now=NOW)
    )
    assert value.state == "NO_TRADE" and value.features is None and value.advice == "NO TRADE"


def test_wait_signal_experiment_and_parent_report_are_not_approval():
    value = research(market=daily_market(close=Decimal(95)))
    assert value.state == "WAIT" and value.features.direction == "WAIT"
    context = clear_event_context(NOW)
    report = build_report("MNQ", "1d", daily_market(), [], [], now=NOW, **context)
    assert report.strategy_research.features.direction == "BUY"
    assert (
        report.strategy_research.advice == "WAIT"
        and report.strategy_research.lifecycle == "EXPERIMENT"
    )
    assert report.strategy_research.strategy_version == "range-volume-v1"
    forged = report.strategy_research.model_dump() | {"lifecycle": "APPROVED"}
    with pytest.raises(ValueError):
        StrategyResearchCheck.model_validate(forged)


def test_feature_record_revalidates_math_identity_and_permission():
    value = research()
    for changes in (
        {"state": "WAIT"},
        {"state": "NO_TRADE", "reasons": ()},
        {"advice": "BUY"},
        {"trade_permitted": True},
        {"instrument_id": "MGC"},
        {"features": value.features.model_copy(update={"previous_high": Decimal(99)})},
    ):
        with pytest.raises(ValueError):
            StrategyResearchCheck.model_validate(value.model_copy(update=changes).model_dump())


def test_backtest_signals_use_shared_prefix_rule_and_next_close_proxy(monkeypatch):
    data = frame(45)
    data.iloc[35, data.columns.get_loc("close")] = 105
    data.iloc[35, data.columns.get_loc("high")] = 110
    data.iloc[35, data.columns.get_loc("volume")] = 20
    run = Mock()
    monkeypatch.setattr(BacktestEngine, "run", run)
    agent = legacy.BreakoutHunter()
    agent.backtest(data, {})
    entries = run.call_args.args[1]
    assert not entries.iloc[35] and entries.iloc[36]
    original = entries.iloc[:38].copy()
    changed = data.copy()
    changed.iloc[40:, changed.columns.get_loc("high")] = 100000
    agent.backtest(changed, {})
    assert run.call_args.args[1].iloc[:38].equals(original)


async def test_replay_and_current_use_same_guarded_kernel_at_known_cut():
    from connectors.advisory.replay import ReplayProvider
    from core.advisory.data import MarketDataQuery

    source = daily_market()
    context = clear_event_context(NOW)
    provider = ReplayProvider([source], calendars=[context["calendar"]])
    query = MarketDataQuery(instrument_id="MNQ", interval="1d", contract="MNQZ26", as_of=NOW)
    replay = await provider.read(query)
    replay_result = research(market=replay)
    current = research(market=source)
    assert (
        replay_result.features == current.features
        and replay_result.parameters == current.parameters
    )
    assert replay_result.state == current.state == "FEATURES_READY"


@pytest.mark.parametrize("source", ["price_clock", "calendar"])
def test_copied_positive_experiment_cannot_keep_guards_after_source_changes(source):
    value = research()
    if source == "price_clock":
        copied = value.model_copy(
            update={
                "market": value.market.model_copy(update={"fetched_at": NOW + timedelta(seconds=1)})
            }
        )
    else:
        copied = value.model_copy(
            update={
                "event_risk": value.event_risk.model_copy(
                    update={
                        "calendar": value.event_risk.calendar.model_copy(update={"complete": False})
                    }
                )
            }
        )
    with pytest.raises(ValueError):
        StrategyResearchCheck.model_validate(copied.model_dump())


@pytest.mark.parametrize("direction", ["BUY", "SELL", "WAIT"])
async def test_agent_entry_uses_the_shared_kernel_without_sizing_in_it(direction):
    data = frame(30)
    close = 105 if direction == "BUY" else 85 if direction == "SELL" else 95
    data.iloc[-1, data.columns.get_loc("close")] = close
    data.iloc[-1, data.columns.get_loc("high")] = max(100, close)
    data.iloc[-1, data.columns.get_loc("low")] = min(90, close)
    data.iloc[-1, data.columns.get_loc("volume")] = 20
    agent = legacy.BreakoutHunter()
    agent._bars["BTC/USDT"].extend(bar() for _ in range(30))
    agent._to_df = Mock(return_value=data)
    agent._compute_indicators = lambda value: value
    agent._enter = AsyncMock()
    await agent._evaluate("BTC/USDT")
    if direction == "WAIT":
        agent._enter.assert_not_awaited()
    else:
        assert agent._enter.await_args.args[1].value == direction
        assert agent._enter.await_args.args[2:] == (close, 2)


@pytest.mark.parametrize("side,stop,close", [("long", 99, 95), ("short", 91, 95), ("long", 94, 95)])
async def test_shared_entry_rule_does_not_replace_legacy_position_exits(side, stop, close):
    data = frame(30, volume=0)
    agent = legacy.BreakoutHunter()
    agent._bars["BTC/USDT"].extend(bar() for _ in range(30))
    agent._to_df = Mock(return_value=data)
    agent._compute_indicators = lambda value: value
    agent._positions["BTC/USDT"] = side
    agent._trailing_stops["BTC/USDT"] = stop
    agent._exit = AsyncMock()
    update = Mock()
    agent._update_trailing_stop = update
    await agent._evaluate("BTC/USDT")
    if (side == "long" and close < stop) or (side == "short" and close > stop):
        agent._exit.assert_awaited_once()
        update.assert_not_called()
    else:
        agent._exit.assert_not_awaited()
        update.assert_called_once()


def test_kernel_failure_after_guarding_stays_no_trade(monkeypatch):
    monkeypatch.setattr(
        VolumeBreakoutKernel,
        "evaluate",
        lambda *args: (_ for _ in ()).throw(ValueError("SYNTHETIC unavailable computation")),
    )
    value = research()
    assert value.state == "NO_TRADE" and value.features is None
    assert "invalid_strategy_price_window" in value.reasons


def test_forged_positive_state_cannot_erase_missing_source():
    value = research()
    for changes in (
        {"market": None},
        {"data_health": value.data_health.model_copy(update={"state": "UNKNOWN"})},
    ):
        with pytest.raises(ValueError):
            StrategyResearchCheck.model_validate(value.model_copy(update=changes).model_dump())


@pytest.mark.parametrize("operation", ["save", "read"])
def test_experimental_saved_report_must_reproduce_its_captured_guards(tmp_path, operation):
    import json

    from connectors.advisory.storage import AdvisoryStore

    context = clear_event_context(NOW)
    report = build_report("MNQ", "1d", daily_market(), [], [], now=NOW, **context)
    store = AdvisoryStore(str(tmp_path / "strategy-reports.sqlite3"))
    if operation == "save":
        bad = report.strategy_research.model_copy(
            update={
                "market": report.market.model_copy(
                    update={"fetched_at": NOW + timedelta(seconds=1)}
                )
            }
        )
        with pytest.raises(ValueError):
            store.save_report(report.model_copy(update={"strategy_research": bad}))
    else:
        store.save_report(report)
        with store.connect() as db:
            raw = json.loads(db.execute("SELECT payload FROM reports").fetchone()[0])
            raw["strategy_research"]["features"]["previous_high"] = "1"
            db.execute("UPDATE reports SET payload=?", (json.dumps(raw),))
        with pytest.raises(ValueError):
            store.report(report.id)


@pytest.mark.parametrize("column", ["created", "instrument"])
def test_saved_report_rejects_key_identity_changes(tmp_path, column):
    from connectors.advisory.storage import AdvisoryStore

    report = build_report("MNQ", "1d", daily_market(), [], [], now=NOW, **clear_event_context(NOW))
    store = AdvisoryStore(str(tmp_path / "report-identity.sqlite3"))
    store.save_report(report)
    with store.connect() as db:
        db.execute(f"UPDATE reports SET {column}='wrong-key'")
    with pytest.raises(ValueError, match="does not match"):
        store.report(report.id)


def test_no_trade_record_cannot_expose_a_buy_feature():
    value = research()
    with pytest.raises(ValueError, match="cannot expose"):
        StrategyResearchCheck.model_validate(
            value.model_copy(
                update={"state": "NO_TRADE", "advice": "NO TRADE", "reasons": ("blocked",)}
            ).model_dump()
        )
