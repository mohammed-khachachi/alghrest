from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture(scope="session")
def project_root():
    return Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def default_config(project_root):
    from src.core.config import load_config

    return load_config(project_root / "configs" / "default.json")


@pytest.fixture
def synthetic_ohlcv():
    from src.data.synthetic import generate_synthetic_data

    return generate_synthetic_data(
        ticker="TEST", start="2018-01-01", end="2022-12-31", seed=42, verbose=False
    )


@pytest.fixture
def feature_matrix(synthetic_ohlcv, default_config):
    from src.models.features import get_feature_matrix

    X, dates, scaler = get_feature_matrix(
        synthetic_ohlcv,
        feature_cols=default_config["feature_cols"],
        verbose=False,
    )
    return X, dates, scaler


@pytest.fixture
def trained_model(feature_matrix, default_config):
    from src.models.hmm import decode_states, train_hmm

    X, dates, scaler = feature_matrix
    model = train_hmm(
        X,
        n_states=default_config["n_states"],
        n_iter=30,
        random_state=42,
        verbose=False,
    )
    states = decode_states(model, X, verbose=False)
    return model, states, X, dates
