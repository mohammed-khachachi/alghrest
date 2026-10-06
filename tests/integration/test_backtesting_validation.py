"""Validate the production backtest engine and its live-eligibility gates."""

from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from backtesting.engine import BacktestEngine
from core.data.models import MonteCarloResult, WalkForwardResult

pytestmark = pytest.mark.integration


@pytest.fixture
def engine():
    return BacktestEngine("test", "test strategy", "BTC/USDT")


@pytest.fixture
def prices():
    close = 100 + np.arange(300) * 0.1 + np.sin(np.arange(300)) * 2
    return pd.DataFrame(
        {"open": close, "high": close + 2, "low": close - 2, "close": close, "volume": 1000},
        index=pd.date_range("2020-01-01", periods=300),
    )


def signals(frame, params=None):
    n = np.arange(len(frame))
    return pd.Series(n % 10 == 1, index=frame.index), pd.Series(n % 10 == 5, index=frame.index)


@pytest.mark.parametrize(
    "changed",
    [
        dict(years=4.9),
        dict(sharpe=0.99),
        dict(max_dd=25),
        dict(trades_per_year=49),
        dict(profit_factor=1.29),
    ],
)
def test_each_hard_threshold_blocks_qualification(engine, changed):
    metrics = dict(years=5, sharpe=1, max_dd=24.9, trades_per_year=50, profit_factor=1.3)
    assert engine._check_validation(**metrics) == []
    assert engine._check_validation(**(metrics | changed))


def test_real_vectorbt_metrics_roundtrip_and_short_history_rejected(engine, prices):
    result = engine.run(prices, *signals(prices))
    assert result.total_trades == 30
    assert result.winning_trades + result.losing_trades == 30
    assert result.final_capital > 0
    assert result.start_date == prices.index[0]
    assert not result.passed_validation
    assert any("history" in failure for failure in result.failure_reasons)


def test_empty_trade_distribution_never_passes_monte_carlo(engine, prices):
    off = pd.Series(False, index=prices.index)
    result = engine._simple_backtest(prices, off, off)
    mc = engine.monte_carlo(result, n_simulations=50)
    assert mc.simulations == 0 and mc.ruin_probability == 1
    assert not mc.passed_validation


def test_monte_carlo_is_repeatable_and_reports_ordered_quantiles(engine, prices):
    result = engine._simple_backtest(prices, *signals(prices))
    result = result.model_copy(
        update={
            "trade_returns": [-0.03, 0.01] * 15,
        }
    )
    first = engine.monte_carlo(result, n_simulations=100)
    assert first == engine.monte_carlo(result, n_simulations=100)
    assert (
        first.percentile_5_return_pct <= first.median_return_pct <= first.percentile_95_return_pct
    )
    assert first.var_99 >= first.var_95
    assert first.failure_reasons and not first.passed_validation


def test_walk_forward_separates_train_and_test_and_rejects_missing_windows(engine, prices):
    result = engine._simple_backtest(prices, *signals(prices))
    engine.run = MagicMock(
        return_value=result.model_copy(update={"sharpe_ratio": 1.2, "total_return_pct": 10.0})
    )
    wf = engine.walk_forward(prices, signals, {}, n_windows=3)
    assert len(wf.windows) == 3
    assert all(w.train_end < w.test_start for w in wf.windows)
    assert wf.avg_oos_sharpe == pytest.approx(1.2)
    assert wf.avg_wf_efficiency == pytest.approx(1)
    engine.run.side_effect = RuntimeError("invalid series")
    failed = engine.walk_forward(prices, signals, {}, n_windows=3)
    assert not failed.passed_validation and not failed.windows
    assert not engine.walk_forward(prices.head(5), signals, {}).passed_validation


def test_all_validation_stages_must_pass(engine, prices):
    backtest = engine._simple_backtest(prices, *signals(prices))
    wf = WalkForwardResult(
        strategy_id="test",
        windows=[],
        avg_oos_sharpe=1,
        avg_oos_return_pct=1,
        avg_wf_efficiency=1,
        passed_validation=True,
        failure_reasons=[],
    )
    mc = MonteCarloResult(
        strategy_id="test",
        simulations=100,
        var_95=0,
        var_99=0,
        cvar_95=0,
        ruin_probability=0,
        median_return_pct=1,
        percentile_5_return_pct=0,
        percentile_95_return_pct=2,
        passed_validation=True,
        failure_reasons=[],
    )
    assert not engine.validate_all(backtest, wf, mc)[0]
    approved = backtest.model_copy(update={"passed_validation": True, "failure_reasons": []})
    assert engine.validate_all(approved, wf, mc) == (True, [])
    mc.passed_validation = False
    passed, reasons = engine.validate_all(approved, wf, mc)
    assert not passed and reasons == ["Monte Carlo did not pass validation"]


def test_trade_streak_and_holding_duration_metrics(engine):
    trades = pd.DataFrame(
        {"PnL": [-1, -2, 1, 0, -1, -1], "Duration": pd.to_timedelta([1, 2, 3, 4, 5, 6], unit="h")}
    )
    assert engine._max_consecutive_losses(trades) == 3
    assert engine._avg_holding_hours(trades) == 3.5
    assert engine._max_consecutive_losses(pd.DataFrame()) == 0
    assert engine._avg_holding_hours(pd.DataFrame()) == 0
