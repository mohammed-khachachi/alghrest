"""
features.py
===========
Constructs the Observation Matrix for the HMM from raw OHLCV data.

In Stanford's HMM formulation:
  - Observations O = {o_1, o_2, ..., o_T} are the visible data points
  - Each observation o_t is a multi-dimensional feature vector
  - The HMM discovers hidden states Q = {q_1, ..., q_T} (market regimes)
    that best explain the sequence of observations

Feature engineering philosophy:
  Rather than feeding raw prices (non-stationary) to HMM, we compute
  stationary, informative features that capture different aspects of
  market behavior: direction, volatility, momentum, and volume.
"""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from typing import List, Optional, Tuple


def compute_features(
    df: pd.DataFrame,
    verbose: bool = True,
    config: Optional[dict] = None,
) -> pd.DataFrame:
    """
    Compute HMM observation features from raw OHLCV data.

    Parameters
    ----------
    df      : pd.DataFrame  — cleaned OHLCV data from data_loader
    verbose : bool          — print feature summary

    Returns
    -------
    pd.DataFrame with computed features (NaN rows dropped)
    """
    config = config or {}
    rolling_vol_window = config.get("rolling_vol_window", 20)
    ma_fast_window = config.get("ma_fast_window", 10)
    ma_slow_window = config.get("ma_slow_window", 50)

    features = pd.DataFrame(index=df.index)

    # ------------------------------------------------------------------
    # 1. RETURN-BASED FEATURES
    #    Capture directional movement of price
    # ------------------------------------------------------------------
    # Daily simple return: (P_t - P_{t-1}) / P_{t-1}
    features["daily_return"] = df["close"].pct_change()

    # Log return: ln(P_t / P_{t-1}) — more symmetric, preferred for HMM
    features["log_return"] = np.log(df["close"] / df["close"].shift(1))

    # ------------------------------------------------------------------
    # 2. VOLATILITY FEATURES
    #    Capture uncertainty / dispersion of returns
    # ------------------------------------------------------------------
    # Rolling volatility (annualised)
    features["rolling_volatility"] = (
        features["log_return"].rolling(window=rolling_vol_window, min_periods=5).std()
        * np.sqrt(252)
    )

    # Intraday range as volatility proxy: (High - Low) / Close
    features["intraday_range"] = (df["high"] - df["low"]) / df["close"]

    # ------------------------------------------------------------------
    # 3. TREND / MOMENTUM FEATURES
    #    Capture the direction and strength of the current trend
    # ------------------------------------------------------------------
    # Fast moving average
    features["ma_fast"] = df["close"].rolling(window=ma_fast_window, min_periods=5).mean()
    # Slow moving average
    features["ma_slow"] = df["close"].rolling(window=ma_slow_window, min_periods=20).mean()
    # MA ratio: fast/slow — >1 means uptrend, <1 means downtrend
    features["ma_ratio"] = features["ma_fast"] / features["ma_slow"]

    # ------------------------------------------------------------------
    # 4. VOLUME FEATURES
    #    Capture participation / conviction in price moves
    # ------------------------------------------------------------------
    # Daily volume change (log ratio)
    features["volume_change"] = np.log(df["volume"] / df["volume"].shift(1))

    # Replace inf/-inf that can arise from zero volume
    features.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Drop rows with NaN (initial warm-up period)
    before = len(features)
    features = features.dropna()
    if verbose:
        dropped = before - len(features)
        print(f"[FEATURES] Computed {len(features.columns)} features over {len(features):,} days "
              f"({dropped} warm-up rows dropped).")
        print(f"[FEATURES] Columns: {list(features.columns)}")

    return features


def get_feature_matrix(
    df: pd.DataFrame,
    feature_cols: List[str] = None,
    verbose: bool = True,
    config: Optional[dict] = None,
) -> Tuple[np.ndarray, pd.DatetimeIndex, StandardScaler]:
    """
    Prepare and standardize the feature matrix for GaussianHMM.

    In the HMM framework this produces the observation matrix X
    where X[t] = o_t (one row per trading day).

    Parameters
    ----------
    df           : raw OHLCV DataFrame
    feature_cols : list of feature names to use (None = use all)
    verbose      : print summary

    Returns
    -------
    X       : np.ndarray of shape (T, n_features)  — scaled observations
    dates   : pd.DatetimeIndex matching rows of X
    scaler  : fitted StandardScaler (for inverse-transforming later)
    """
    feat_df = compute_features(df, verbose=verbose, config=config)

    if feature_cols is None:
        # Core HMM features: avoid using MA columns directly (use ratio instead)
        feature_cols = [
            "log_return",
            "rolling_volatility",
            "ma_ratio",
            "volume_change",
            "intraday_range",
        ]

    # Ensure all requested features exist
    missing = [c for c in feature_cols if c not in feat_df.columns]
    if missing:
        raise ValueError(f"Features not found in DataFrame: {missing}")

    X_raw = feat_df[feature_cols].values

    # Standardise: GaussianHMM convergence is much more stable on scaled data
    scaler = StandardScaler()
    X = scaler.fit_transform(X_raw)

    if verbose:
        print(f"[FEATURES] Feature matrix shape: {X.shape}  (T={X.shape[0]}, d={X.shape[1]})")
        print(f"[FEATURES] Using: {feature_cols}")

    return X, feat_df.index, scaler


if __name__ == "__main__":
    # Quick sanity check
    from src.data.loader import download_data

    df = download_data("^GSPC", "2018-01-01", "2023-12-31")
    X, dates, scaler = get_feature_matrix(df)
    print(f"X shape: {X.shape}")
    print(f"First row (scaled): {X[0]}")
