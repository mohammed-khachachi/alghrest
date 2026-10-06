"""Financial feature engineering for HMM regime detection."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


@dataclass
class FeatureSet:
    frame: pd.DataFrame
    matrix: np.ndarray
    scaler: StandardScaler
    columns: list[str]


def build_features(
    data: pd.DataFrame,
    volatility_window: int = 20,
    fast_ma: int = 20,
    slow_ma: int = 60,
) -> FeatureSet:
    """Create scaled HMM features from OHLCV data."""

    frame = data.copy()
    frame["daily_return"] = frame["close"].pct_change()
    frame["log_return"] = np.log(frame["close"]).diff()
    frame["volatility"] = frame["daily_return"].rolling(volatility_window).std() * np.sqrt(252)
    frame["ma_fast"] = frame["close"].rolling(fast_ma).mean()
    frame["ma_slow"] = frame["close"].rolling(slow_ma).mean()
    frame["ma_ratio"] = frame["ma_fast"] / frame["ma_slow"] - 1.0
    frame["volume_change"] = frame["volume"].pct_change().clip(lower=-5, upper=5)

    feature_columns = ["daily_return", "volatility", "ma_ratio", "volume_change"]
    frame = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=feature_columns + ["close"])

    scaler = StandardScaler()
    matrix = scaler.fit_transform(frame[feature_columns])
    return FeatureSet(frame=frame, matrix=matrix, scaler=scaler, columns=feature_columns)
