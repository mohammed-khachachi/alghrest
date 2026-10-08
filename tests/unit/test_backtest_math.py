"""Independent arithmetic examples and backend parity for historical validation."""

import builtins
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from backtesting.engine import BacktestEngine
from core.data.models import BacktestResult, Timeframe

pytestmark = pytest.mark.unit


def engine(timeframe=Timeframe.D1, fee=0, slippage=0):
    return BacktestEngine("math", "Arithmetic", "BTC/USDT", timeframe, 1000, fee, slippage)


def frame(prices, freq="D"):
    return pd.DataFrame(
        {"close": prices}, index=pd.date_range("2020-01-01", periods=len(prices), freq=freq)
    )


def signals(data, entries=(0,), exits=()):
    return (
        pd.Series(np.isin(np.arange(len(data)), entries), index=data.index),
        pd.Series(np.isin(np.arange(len(data)), exits), index=data.index),
    )


@pytest.mark.parametrize("backend", ["run", "_simple_backtest"])
def test_fees_slippage_size_and_closed_return_have_exact_cash_arithmetic(backend):
    data = frame([100, 80, 110])
    result = getattr(engine(fee=0.01, slippage=0.02), backend)(
        data, *signals(data, exits=(2,)), size_pct=0.5
    )
    # 500 cash is committed, including the entry fee. The other 500 stays idle.
    quantity = 500 / (102 * 1.01)
    proceeds = quantity * (110 * 0.98) * 0.99
    final_cash = 500 + proceeds
    assert result.final_capital == pytest.approx(final_cash)
    assert result.total_return_pct == pytest.approx((final_cash / 1000 - 1) * 100)
    assert result.max_drawdown_pct == pytest.approx((1 - (500 + quantity * 80) / 1000) * 100)
    assert result.trade_returns == pytest.approx([(proceeds - 500) / 500])
    assert result.avg_holding_hours == 48
    assert result.max_drawdown_duration_days == 2
    assert result.total_trades == 1
    assert BacktestResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize("backend", ["run", "_simple_backtest"])
def test_open_inventory_is_marked_but_is_not_a_closed_trade(backend):
    data = frame([100, 70, 120])
    result = getattr(engine(), backend)(data, *signals(data), size_pct=1)
    assert result.final_capital == pytest.approx(1200)
    assert result.max_drawdown_pct == pytest.approx(30)
    assert result.max_drawdown_duration_days == 2
    assert result.trade_returns == []
    assert result.total_trades == 0
    assert not engine().monte_carlo(result).passed_validation


@pytest.mark.parametrize(
    "prices,expected_duration",
    [
        ([100, 80, 100, 100], 2),
        ([100, 80, 110, 110], 2),
        ([100, 80, 70, 70], 3),
        ([100, 100, 100, 100], 0),
    ],
)
def test_drawdown_duration_counts_recovery_and_unrecovered_periods(prices, expected_duration):
    data = frame(prices, freq="h")
    result = engine(Timeframe.H1)._simple_backtest(data, *signals(data), size_pct=1)
    assert result.max_drawdown_duration_days == pytest.approx(expected_duration / 24)


@pytest.mark.parametrize(
    "freq,timeframe",
    [
        ("min", Timeframe.M1),
        ("5min", Timeframe.M5),
        ("15min", Timeframe.M15),
        ("30min", Timeframe.M30),
        ("h", Timeframe.H1),
        ("4h", Timeframe.H4),
        ("D", Timeframe.D1),
        ("7D", Timeframe.W1),
    ],
)
def test_both_backends_have_matching_trade_and_equity_metrics(freq, timeframe):
    data = frame([100, 103, 97, 105, 110, 108, 95, 107], freq)
    enter, leave = signals(data, entries=(0, 2, 5, 7), exits=(1, 4, 6))
    subject = engine(timeframe, fee=0.001, slippage=0.0005)
    vector = subject.run(data, enter, leave, size_pct=0.6)
    fallback = subject._simple_backtest(data, enter, leave, size_pct=0.6)
    for field in (
        "final_capital",
        "total_return_pct",
        "annualized_return_pct",
        "sharpe_ratio",
        "sortino_ratio",
        "max_drawdown_pct",
        "max_drawdown_duration_days",
        "trades_per_year",
        "avg_holding_hours",
    ):
        assert getattr(fallback, field) == pytest.approx(getattr(vector, field))
    assert fallback.trade_returns == pytest.approx(vector.trade_returns)
    assert fallback.total_trades == vector.total_trades == 3


def test_elapsed_calendar_years_and_cagr_use_timestamps_not_number_of_bars():
    # Two years pass across just four observations, with irregular gaps.
    data = pd.DataFrame(
        {"close": [100, 100, 110, 121]},
        index=pd.to_datetime(["2020-01-01", "2020-01-02", "2020-08-01", "2022-01-01"]),
    )
    result = engine()._simple_backtest(data, *signals(data, exits=(3,)), size_pct=1)
    years = 731 / 365.25
    assert result.trades_per_year == pytest.approx(1 / years)
    assert result.annualized_return_pct == pytest.approx((1.21 ** (1 / years) - 1) * 100)
    assert result.start_date == data.index[0]
    assert result.end_date == data.index[-1]
    assert "2.0y" in result.failure_reasons[0]


def test_five_year_history_gate_cannot_be_met_by_a_few_weeks_of_hourly_bars():
    data = frame(np.ones(2000) * 100, "h")
    result = engine(Timeframe.H1)._simple_backtest(data, *signals(data, exits=(1999,)))
    assert any("Insufficient history" in reason for reason in result.failure_reasons)
    assert result.trades_per_year == pytest.approx(365.25 * 24 / 1999)


def test_sharpe_is_computed_from_daily_marked_equity_returns():
    data = frame([100, 110, 99, 108])
    result = engine()._simple_backtest(data, *signals(data), size_pct=1)
    returns = np.array([0, 0.1, -0.1, 108 / 99 - 1])
    expected = returns.mean() / returns.std(ddof=1) * np.sqrt(365.25)
    assert result.sharpe_ratio == pytest.approx(expected)


def test_missing_vectorbt_uses_same_sizing_and_conflict_policy():
    data = frame([100, 200, 100])
    enter, leave = signals(data, entries=(0, 1), exits=(1, 2))
    original = builtins.__import__

    def without_vectorbt(name, *args, **kwargs):
        if name == "vectorbt":
            raise ImportError("optional backend unavailable")
        return original(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=without_vectorbt):
        result = engine().run(data, enter, leave, size_pct=0.25)
    assert result.final_capital == 1000  # opposing signals at the peak were ignored
    assert result.total_trades == 1
    assert result.max_drawdown_pct == pytest.approx(20)


@pytest.mark.parametrize(
    "bad",
    [
        "range",
        "reversed",
        "duplicate",
        "nat",
        "short",
        "nan_price",
        "zero_price",
        "unaligned",
        "null_signal",
        "numeric_signal",
        "zero_size",
        "nan_size",
    ],
)
def test_invalid_inputs_never_produce_a_validation_result(bad):
    data = frame([100, 101, 102])
    size = 1
    if bad == "range":
        data.index = pd.RangeIndex(3)
    elif bad == "reversed":
        data = data.iloc[::-1]
    elif bad == "duplicate":
        data.index = pd.DatetimeIndex([data.index[0]] * 3)
    elif bad == "nat":
        data.index = pd.DatetimeIndex([data.index[0], pd.NaT, data.index[2]])
    elif bad == "short":
        data = data.head(1)
    elif bad in {"nan_price", "zero_price"}:
        data["close"] = [100, np.nan if bad == "nan_price" else 0, 102]
    enter, leave = signals(data)
    if bad == "unaligned":
        enter.index = enter.index + pd.Timedelta(hours=1)
    elif bad == "null_signal":
        enter = pd.Series([True, None, False], index=data.index, dtype="boolean")
    elif bad == "numeric_signal":
        enter = enter.astype(int)
    elif bad == "zero_size":
        size = 0
    elif bad == "nan_size":
        size = float("nan")
    with pytest.raises(ValueError):
        engine().run(data, enter, leave, size_pct=size)


def observed_result(returns, years=3):
    data = frame([100, 101])
    result = engine()._simple_backtest(data, *signals(data, exits=(1,)))
    return result.model_copy(
        update={
            "trade_returns": returns,
            "total_trades": len(returns),
            "end_date": result.start_date + pd.Timedelta(days=365.25 * years),
        }
    )


def test_empirical_bootstrap_uses_observed_support_and_ignores_summary_estimates():
    # Exactly one draw per simulation: two trades over six years, three-year horizon.
    result = observed_result([-0.5, 0.2], years=6)
    mc = engine().monte_carlo(result, n_simulations=10000)
    assert mc.percentile_5_return_pct == -50
    assert mc.percentile_95_return_pct == pytest.approx(20)
    assert mc.var_95 == mc.var_99 == mc.cvar_95 == 0.5
    assert mc.ruin_probability == pytest.approx(0.5, abs=0.02)
    changed = result.model_copy(
        update={
            "win_rate_pct": 100,
            "avg_winning_trade_pct": 1000,
            "avg_losing_trade_pct": 0,
            "trades_per_year": 999,
        }
    )
    assert engine().monte_carlo(changed) == mc
    restored = BacktestResult.model_validate_json(result.model_dump_json())
    assert engine().monte_carlo(restored) == mc


def test_identical_empirical_gains_have_exact_compounding_and_zero_loss_risk():
    result = observed_result([0.1], years=1)
    mc = engine().monte_carlo(result, n_simulations=50)
    assert mc.median_return_pct == pytest.approx(33.1)
    assert mc.percentile_5_return_pct == mc.percentile_95_return_pct
    assert mc.var_95 == mc.var_99 == mc.cvar_95 == mc.ruin_probability == 0


def test_ruin_is_pathwise_inclusive_and_stops_at_fifty_percent():
    mc = engine().monte_carlo(observed_result([-0.5], years=1), n_simulations=50)
    assert mc.ruin_probability == 1
    assert mc.median_return_pct == -50  # not -87.5 after continuing three losing trades
    assert not mc.passed_validation


@pytest.mark.parametrize(
    "updates",
    [
        {"trade_returns": None},
        {"trade_returns": []},
        {"trade_returns": [float("nan")]},
        {"trade_returns": [float("inf")]},
        {"trade_returns": [-1.01]},
        {"end_date": pd.Timestamp("2019-01-01")},
    ],
)
def test_missing_or_invalid_empirical_evidence_fails_closed(updates):
    result = observed_result([0.01]).model_copy(update=updates)
    mc = engine().monte_carlo(result, n_simulations=10)
    assert not mc.passed_validation and mc.simulations == 0
    assert mc.failure_reasons


@pytest.mark.parametrize("count", [0, -1, True, 2.5, 100001])
def test_invalid_simulation_count_is_rejected(count):
    with pytest.raises(ValueError, match="n_simulations"):
        engine().monte_carlo(observed_result([0.01]), n_simulations=count)
