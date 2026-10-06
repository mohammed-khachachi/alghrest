"""Configuration loading and validation utilities."""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path


REQUIRED_CONFIG_KEYS = {
    "ticker",
    "start",
    "end",
    "n_states",
    "covariance_type",
    "n_iter",
    "random_state",
    "transaction_cost",
    "trading_days_per_year",
    "feature_cols",
    "regime_thresholds",
    "rolling_vol_window",
    "ma_fast_window",
    "ma_slow_window",
}

REQUIRED_REGIME_THRESHOLDS = {
    "return_bullish",
    "return_bearish",
    "vol_low",
    "vol_high",
}


def load_config(path: str | Path) -> dict:
    """Load and validate a JSON configuration file."""
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON configuration file: {config_path}") from exc

    if not validate_config(config):
        raise ValueError(f"Invalid configuration schema: {config_path}")

    return config


def validate_config(config: dict) -> bool:
    """Return True when the configuration has the required Phase 2 schema."""
    if not isinstance(config, dict):
        return False

    if not REQUIRED_CONFIG_KEYS.issubset(config):
        return False

    feature_cols = config["feature_cols"]
    if not isinstance(feature_cols, list) or not feature_cols:
        return False

    regime_thresholds = config["regime_thresholds"]
    if not isinstance(regime_thresholds, dict):
        return False

    return REQUIRED_REGIME_THRESHOLDS.issubset(regime_thresholds)
