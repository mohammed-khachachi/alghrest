"""
test_features.py
================
Basic sanity tests for the features module.
"""

import numpy as np
import pandas as pd
import pytest

from src.models.features import compute_features, get_feature_matrix


def _make_dummy_ohlcv(n: int = 100) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame for testing."""
    np.random.seed(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    prices = 100 * np.cumprod(1 + np.random.randn(n) * 0.01)
    df = pd.DataFrame({
        "open":   prices * (1 + np.random.randn(n) * 0.002),
        "high":   prices * (1 + abs(np.random.randn(n)) * 0.005),
        "low":    prices * (1 - abs(np.random.randn(n)) * 0.005),
        "close":  prices,
        "volume": np.random.randint(1_000_000, 10_000_000, n).astype(float),
    }, index=dates)
    df["high"] = df[["open", "high", "close"]].max(axis=1)
    df["low"]  = df[["open", "low",  "close"]].min(axis=1)
    return df


class TestComputeFeatures:
    """Tests for compute_features()."""

    def test_returns_dataframe(self):
        df = _make_dummy_ohlcv(100)
        feat = compute_features(df, verbose=False)
        assert isinstance(feat, pd.DataFrame)

    def test_no_nan_values(self):
        df = _make_dummy_ohlcv(120)
        feat = compute_features(df, verbose=False)
        assert feat.isnull().sum().sum() == 0, "Feature DataFrame must have no NaN values"

    def test_no_inf_values(self):
        df = _make_dummy_ohlcv(120)
        feat = compute_features(df, verbose=False)
        assert not np.isinf(feat.values).any(), "Feature DataFrame must have no Inf values"

    def test_expected_columns_present(self):
        df = _make_dummy_ohlcv(120)
        feat = compute_features(df, verbose=False)
        expected = ["daily_return", "log_return", "rolling_volatility",
                    "ma_ratio", "volume_change"]
        for col in expected:
            assert col in feat.columns, f"Missing feature column: {col}"

    def test_feature_length_shorter_than_input(self):
        n = 120
        df = _make_dummy_ohlcv(n)
        feat = compute_features(df, verbose=False)
        # Features should be shorter due to warm-up period (rolling windows)
        assert len(feat) < n
        assert len(feat) > 0


class TestGetFeatureMatrix:
    """Tests for get_feature_matrix()."""

    def test_returns_correct_shape(self):
        df = _make_dummy_ohlcv(150)
        X, dates, scaler = get_feature_matrix(df, verbose=False)
        assert X.ndim == 2
        assert X.shape[0] == len(dates)
        assert X.shape[1] >= 3

    def test_scaled_values_reasonable(self):
        df = _make_dummy_ohlcv(150)
        X, _, _ = get_feature_matrix(df, verbose=False)
        # After StandardScaler, mean ≈ 0, std ≈ 1
        assert abs(X.mean()) < 1.0, "Scaled features should have near-zero mean"
        assert abs(X.std() - 1.0) < 0.5, "Scaled features should have near-unit std"

    def test_no_nan_in_matrix(self):
        df = _make_dummy_ohlcv(150)
        X, _, _ = get_feature_matrix(df, verbose=False)
        assert not np.isnan(X).any(), "Feature matrix must not contain NaN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
