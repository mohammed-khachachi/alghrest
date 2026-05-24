"""
test_features.py
================
Basic sanity tests for the features module.
"""

import numpy as np
import pandas as pd
import pytest

from src.models.features import compute_features, get_feature_matrix


class TestComputeFeatures:
    """Tests for compute_features()."""

    def test_returns_dataframe(self, synthetic_ohlcv):
        feat = compute_features(synthetic_ohlcv, verbose=False)
        assert isinstance(feat, pd.DataFrame)

    def test_no_nan_values(self, synthetic_ohlcv):
        feat = compute_features(synthetic_ohlcv, verbose=False)
        assert feat.isnull().sum().sum() == 0, "Feature DataFrame must have no NaN values"

    def test_no_inf_values(self, synthetic_ohlcv):
        feat = compute_features(synthetic_ohlcv, verbose=False)
        assert not np.isinf(feat.values).any(), "Feature DataFrame must have no Inf values"

    def test_expected_columns_present(self, synthetic_ohlcv):
        feat = compute_features(synthetic_ohlcv, verbose=False)
        expected = ["daily_return", "log_return", "rolling_volatility",
                    "ma_ratio", "volume_change"]
        for col in expected:
            assert col in feat.columns, f"Missing feature column: {col}"

    def test_feature_length_shorter_than_input(self, synthetic_ohlcv):
        feat = compute_features(synthetic_ohlcv, verbose=False)
        # Features should be shorter due to warm-up period (rolling windows)
        assert len(feat) < len(synthetic_ohlcv)
        assert len(feat) > 0


class TestGetFeatureMatrix:
    """Tests for get_feature_matrix()."""

    def test_returns_correct_shape(self, synthetic_ohlcv):
        X, dates, scaler = get_feature_matrix(synthetic_ohlcv, verbose=False)
        assert X.ndim == 2
        assert X.shape[0] == len(dates)
        assert X.shape[1] >= 3

    def test_scaled_values_reasonable(self, synthetic_ohlcv):
        X, _, _ = get_feature_matrix(synthetic_ohlcv, verbose=False)
        # After StandardScaler, mean ≈ 0, std ≈ 1
        assert abs(X.mean()) < 1.0, "Scaled features should have near-zero mean"
        assert abs(X.std() - 1.0) < 0.5, "Scaled features should have near-unit std"

    def test_no_nan_in_matrix(self, synthetic_ohlcv):
        X, _, _ = get_feature_matrix(synthetic_ohlcv, verbose=False)
        assert not np.isnan(X).any(), "Feature matrix must not contain NaN"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
