"""
test_backtest.py
================
Basic sanity tests for the backtest module.
"""

import numpy as np
import pandas as pd
import pytest

from src.analysis.backtest import build_signal, run_backtest


def _make_dummy_regime_df(n: int = 200) -> tuple:
    """Create synthetic regime DataFrame and labels for testing."""
    np.random.seed(42)
    dates = pd.date_range("2018-01-01", periods=n, freq="B")
    labels = {
        0: "Bullish / Low-Vol",
        1: "Bearish / High-Vol",
        2: "Sideways / Moderate-Vol",
    }
    states = np.random.choice([0, 1, 2], size=n)
    regime_df = pd.DataFrame(
        {
            "state": states,
            "regime_label": [labels[s] for s in states],
        },
        index=dates,
    )
    return regime_df, labels


def _make_dummy_price_df(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Synthetic price series aligned with dates."""
    np.random.seed(42)
    n = len(dates)
    returns = np.random.randn(n) * 0.01
    prices = 100 * np.cumprod(1 + returns)
    volume = np.random.randint(1_000_000, 10_000_000, n).astype(float)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices * 1.005,
            "low": prices * 0.995,
            "close": prices,
            "volume": volume,
        },
        index=dates,
    )


class TestBuildSignal:

    def test_signal_is_binary(self):
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        unique_vals = set(signal_df["signal"].unique())
        assert unique_vals.issubset({0, 1}), "Signal must be 0 (Cash) or 1 (Long)"

    def test_signal_is_shifted(self):
        """Signal at row 0 should be NaN->0 (no look-ahead)."""
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        # After shift(1).fillna(0), the first value should be 0
        assert signal_df["signal"].iloc[0] == 0

    def test_output_has_correct_length(self):
        n = 150
        regime_df, labels = _make_dummy_regime_df(n)
        signal_df = build_signal(regime_df, labels, verbose=False)
        assert len(signal_df) == n


class TestRunBacktest:

    def test_returns_metrics_dict(self):
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        price_df = _make_dummy_price_df(regime_df.index)
        _, metrics = run_backtest(price_df, signal_df, verbose=False)
        assert isinstance(metrics, dict)

    def test_required_metrics_present(self):
        required = [
            "Strategy_total_return",
            "Strategy_annual_return",
            "Strategy_sharpe",
            "Strategy_max_drawdown",
            "Strategy_win_rate",
            "BuyHold_total_return",
            "BuyHold_sharpe",
            "BuyHold_max_drawdown",
        ]
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        price_df = _make_dummy_price_df(regime_df.index)
        _, metrics = run_backtest(price_df, signal_df, verbose=False)
        for key in required:
            assert key in metrics, f"Missing metric: {key}"

    def test_max_drawdown_is_negative_or_zero(self):
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        price_df = _make_dummy_price_df(regime_df.index)
        _, metrics = run_backtest(price_df, signal_df, verbose=False)
        assert metrics["Strategy_max_drawdown"] <= 0, "Max drawdown must be <= 0"
        assert metrics["BuyHold_max_drawdown"] <= 0, "Max drawdown must be <= 0"

    def test_equity_curve_starts_at_one(self):
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        price_df = _make_dummy_price_df(regime_df.index)
        results_df, _ = run_backtest(price_df, signal_df, verbose=False)
        # First non-NaN value of equity should be close to 1.0
        first_eq = results_df["strat_equity"].dropna().iloc[0]
        assert abs(first_eq - 1.0) < 0.05, "Equity curve should start near 1.0"

    def test_results_df_has_required_columns(self):
        regime_df, labels = _make_dummy_regime_df(200)
        signal_df = build_signal(regime_df, labels, verbose=False)
        price_df = _make_dummy_price_df(regime_df.index)
        results_df, _ = run_backtest(price_df, signal_df, verbose=False)
        for col in ["strat_equity", "bnh_equity", "signal", "regime_label"]:
            assert col in results_df.columns, f"Missing column: {col}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
