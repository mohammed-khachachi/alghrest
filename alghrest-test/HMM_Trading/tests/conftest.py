"""Shared pytest fixtures for the HMM_Trading test suite."""

from __future__ import annotations

import pytest

from src.core.config import load_config
from src.core.paths import PROJECT_ROOT
from src.data.synthetic import generate_synthetic_data
from src.models.features import get_feature_matrix


@pytest.fixture
def project_root():
    """Return the HMM_Trading project root."""
    return PROJECT_ROOT


@pytest.fixture
def default_config():
    """Load the default project configuration."""
    return load_config("configs/default.json")


@pytest.fixture
def synthetic_ohlcv():
    """Return a small deterministic OHLCV sample for fast tests."""
    return generate_synthetic_data(
        ticker="TEST",
        start="2020-01-01",
        end="2020-06-30",
        seed=42,
        verbose=False,
    )


@pytest.fixture
def feature_matrix(synthetic_ohlcv, default_config):
    """Return the scaled HMM feature matrix for the synthetic OHLCV sample."""
    X, _, _ = get_feature_matrix(
        synthetic_ohlcv,
        default_config["feature_cols"],
        verbose=False,
    )
    return X
