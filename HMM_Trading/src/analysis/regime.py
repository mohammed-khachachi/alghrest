"""
regime_interpreter.py
=====================
Interprets each hidden HMM state as a meaningful market regime.

The HMM discovers states automatically (unsupervised). This module
labels each state based on its statistical properties:
  - Mean return    → direction (bullish / bearish / sideways)
  - Volatility     → risk level (low / medium / high)
  - Volume change  → conviction / participation

This directly maps to Stanford's HMM emission distributions:
  B_i(o_t) = N(o_t; μ_i, Σ_i)
Each state i has a characteristic μ_i (mean return, volatility, volume)
that we use to assign a human-readable regime label.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple


def get_thresholds(config: Optional[dict] = None) -> dict:
    defaults = {
        "return_bullish": 0.0003,
        "return_bearish": -0.0003,
        "vol_low": 0.12,
        "vol_high": 0.22,
    }
    if config and "regime_thresholds" in config:
        defaults.update(config["regime_thresholds"])
    return defaults


def compute_regime_stats(
    df_features: pd.DataFrame,
    states: np.ndarray,
    df_price: pd.DataFrame,
) -> pd.DataFrame:
    """
    Compute per-regime statistics to characterise each hidden state.

    Parameters
    ----------
    df_features : DataFrame with computed features (same index as states)
    states      : np.ndarray of state labels (0, 1, ..., n_states-1)
    df_price    : raw OHLCV DataFrame (for close prices)

    Returns
    -------
    pd.DataFrame — one row per state with descriptive statistics
    """
    # Align features with states (features may have fewer rows due to warm-up)
    feat_idx = df_features.index
    price_aligned = df_price["close"].reindex(feat_idx)
    returns_aligned = df_price["close"].pct_change().reindex(feat_idx)

    records = []
    n_states = len(np.unique(states))

    for state_id in range(n_states):
        mask = states == state_id
        n_days = mask.sum()

        if n_days == 0:
            continue

        # Daily returns in this regime
        ret = returns_aligned[mask]
        # Rolling volatility in this regime (annualised)
        vol = df_features["rolling_volatility"][mask] if "rolling_volatility" in df_features.columns else pd.Series(dtype=float)
        # Volume change
        vc  = df_features["volume_change"][mask] if "volume_change" in df_features.columns else pd.Series(dtype=float)
        # Log return
        lr  = df_features["log_return"][mask] if "log_return" in df_features.columns else ret

        records.append({
            "state_id":        state_id,
            "n_days":          n_days,
            "pct_of_time":     100.0 * n_days / len(states),
            "mean_daily_ret":  ret.mean(),
            "std_daily_ret":   ret.std(),
            "mean_log_ret":    lr.mean(),
            "annualised_ret":  ret.mean() * 252,
            "mean_volatility": vol.mean() if len(vol) > 0 else np.nan,
            "mean_vol_change": vc.mean()  if len(vc)  > 0 else np.nan,
            "sharpe_approx":   (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0.0,
            "positive_days":   (ret > 0).mean() * 100,
        })

    stats_df = pd.DataFrame(records).set_index("state_id")
    return stats_df


def assign_regime_labels(
    stats_df: pd.DataFrame,
    config: Optional[dict] = None,
) -> Dict[int, str]:
    """
    Assign a human-readable label to each state based on statistics.

    Classification logic:
      - Bullish / Bearish: based on mean daily return sign & magnitude
      - Low / High volatility: based on annualised rolling volatility
      - Sideways: neutral return with any volatility level
    """
    thresholds = get_thresholds(config)
    labels = {}

    for state_id, row in stats_df.iterrows():
        ret = row["mean_daily_ret"]
        vol = row["mean_volatility"] if not np.isnan(row["mean_volatility"]) else 0.18

        # Direction
        if ret > thresholds["return_bullish"]:
            direction = "Bullish"
        elif ret < thresholds["return_bearish"]:
            direction = "Bearish"
        else:
            direction = "Sideways"

        # Volatility level
        if vol < thresholds["vol_low"]:
            vol_level = "Low-Vol"
        elif vol < thresholds["vol_high"]:
            vol_level = "Moderate-Vol"
        else:
            vol_level = "High-Vol"

        # Compose label
        label = f"{direction} / {vol_level}"
        labels[state_id] = label

    return labels


def interpret_regimes(
    df_features: pd.DataFrame,
    states: np.ndarray,
    df_price: pd.DataFrame,
    verbose: bool = True,
    config: Optional[dict] = None,
) -> Tuple[pd.DataFrame, Dict[int, str]]:
    """
    Main entry point: compute stats and assign regime labels.

    Returns
    -------
    stats_df : DataFrame with per-regime statistics
    labels   : dict mapping state_id → regime label string
    """
    stats_df = compute_regime_stats(df_features, states, df_price)
    labels   = assign_regime_labels(stats_df, config=config)

    if verbose:
        print("\n" + "=" * 65)
        print("  MARKET REGIME INTERPRETATION")
        print("  (Based on HMM Emission Distribution Statistics)")
        print("=" * 65)
        for state_id, row in stats_df.iterrows():
            lbl = labels[state_id]
            print(f"\n  State {state_id} — [{lbl}]")
            print(f"    Days in regime:      {row['n_days']:,}  ({row['pct_of_time']:.1f}% of history)")
            print(f"    Mean daily return:   {row['mean_daily_ret']*100:+.3f}%")
            print(f"    Annualised return:   {row['annualised_ret']*100:+.1f}%")
            print(f"    Std daily return:    {row['std_daily_ret']*100:.3f}%")
            print(f"    Mean volatility:     {row['mean_volatility']*100:.1f}%  (annualised)")
            print(f"    Approx Sharpe:       {row['sharpe_approx']:.2f}")
            print(f"    % Positive days:     {row['positive_days']:.1f}%")
        print("=" * 65)

    return stats_df, labels


def build_regime_series(
    dates: pd.DatetimeIndex,
    states: np.ndarray,
    labels: Dict[int, str],
) -> pd.DataFrame:
    """
    Build a date-indexed DataFrame with state and regime label per day.
    """
    df_regimes = pd.DataFrame({
        "state":       states,
        "regime_label": [labels[s] for s in states],
    }, index=dates)
    return df_regimes


if __name__ == "__main__":
    from src.data.loader import download_data
    from src.models.features import compute_features, get_feature_matrix
    from src.models.hmm import train_hmm, decode_states

    df = download_data("^GSPC", "2015-01-01", "2023-12-31")
    X, dates, scaler = get_feature_matrix(df)
    model  = train_hmm(X, n_states=3)
    states = decode_states(model, X)
    feat_df = compute_features(df).loc[dates]
    stats, labels = interpret_regimes(feat_df, states, df)
