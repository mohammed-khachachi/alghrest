"""
backtest.py - HMM Trading Strategy Backtest (Educational)
"""
import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple


__all__ = ["_auto_select_long_states", "build_signal", "run_backtest"]


def _auto_select_long_states(regime_labels, stats_df=None):
    """Pick LONG states from regime labels + optional stats."""
    long_states = set()
    for sid, label in regime_labels.items():
        if "Bearish" in label:
            continue
        if "Bullish" in label:
            long_states.add(sid)
            continue
        if "Sideways" in label and stats_df is not None:
            ret = stats_df.loc[sid, "mean_daily_ret"] if sid in stats_df.index else 0.0
            if ret >= 0:
                long_states.add(sid)
    # fallback: pick state with best mean return
    if not long_states and stats_df is not None and not stats_df.empty:
        long_states.add(int(stats_df["mean_daily_ret"].idxmax()))
    return long_states


def build_signal(
    regime_df,
    regime_labels,
    long_keywords=("Bullish",),
    avoid_keywords=("Bearish",),
    transaction_cost=0.001,
    verbose=True,
    stats_df=None,
):
    """
    Convert regime labels into shifted trading signals (0=Cash, 1=Long).
    Uses _auto_select_long_states for smart state selection.
    Shift by 1 day prevents look-ahead bias.
    """
    long_states = _auto_select_long_states(regime_labels, stats_df)

    if verbose:
        if long_states:
            long_lbls = [f"State {s}: {regime_labels[s]}" for s in sorted(long_states)]
            print(f"[SIGNAL] Long states: {', '.join(long_lbls)}")
        else:
            print("[SIGNAL] WARNING: No long states selected - all Cash.")

    state_series = regime_df["state"]

    def _classify(s):
        lbl = regime_labels.get(s, "")
        if any(kw in lbl for kw in avoid_keywords):
            return 0
        return 1 if s in long_states else 0

    raw_signal = state_series.apply(_classify)
    signal_shifted = raw_signal.shift(1).fillna(0)

    signal_df = pd.DataFrame({
        "raw_signal":   raw_signal,
        "signal":       signal_shifted.astype(int),
        "regime_label": regime_df["regime_label"],
    })

    if verbose:
        n_long = (signal_df["signal"] == 1).sum()
        n_cash = (signal_df["signal"] == 0).sum()
        pct = 100 * n_long / max(len(signal_df), 1)
        print(f"[SIGNAL] Long days: {n_long:,}  ({pct:.1f}%)")
        print(f"[SIGNAL] Cash days: {n_cash:,}  ({100-pct:.1f}%)")

    return signal_df


def run_backtest(df_price, signal_df, transaction_cost=0.001, verbose=True):
    """
    Run educational backtest and return (results_df, metrics dict).

    DISCLAIMER: In-sample only. Not financial advice.
    """
    TRADING_DAYS = 252
    daily_ret = df_price["close"].pct_change()
    aligned   = daily_ret.reindex(signal_df.index)

    # Transaction cost on signal changes
    trades        = signal_df["signal"].diff().abs().fillna(0)
    strat_returns = signal_df["signal"] * aligned - trades * transaction_cost
    bnh_returns   = aligned.copy()

    strat_equity = (1 + strat_returns).cumprod()
    bnh_equity   = (1 + bnh_returns).cumprod()

    results_df = pd.DataFrame({
        "close":        df_price["close"].reindex(signal_df.index),
        "daily_return": aligned,
        "signal":       signal_df["signal"],
        "regime_label": signal_df["regime_label"],
        "strat_return": strat_returns,
        "bnh_return":   bnh_returns,
        "strat_equity": strat_equity,
        "bnh_equity":   bnh_equity,
    })

    def _metrics(returns, label):
        ret   = returns.dropna()
        if len(ret) == 0:
            return {f"{label}_{k}": 0.0 for k in
                    ["total_return","annual_return","annual_vol","sharpe",
                     "max_drawdown","win_rate","n_trades"]}
        total  = (1 + ret).prod() - 1
        ann    = (1 + total) ** (TRADING_DAYS / len(ret)) - 1
        vol    = ret.std() * np.sqrt(TRADING_DAYS)
        sharpe = ann / vol if vol > 0 else 0.0
        eq     = (1 + ret).cumprod()
        max_dd = (eq / eq.cummax() - 1).min()
        win_rate = (ret > 0).mean()
        if label == "Strategy":
            sig = results_df["signal"].reindex(ret.index)
            n_trades = sig.diff().abs().sum() / 2
        else:
            n_trades = 1.0
        return {
            f"{label}_total_return":  total,
            f"{label}_annual_return": ann,
            f"{label}_annual_vol":    vol,
            f"{label}_sharpe":        sharpe,
            f"{label}_max_drawdown":  max_dd,
            f"{label}_win_rate":      win_rate,
            f"{label}_n_trades":      n_trades,
        }

    metrics = {**_metrics(strat_returns, "Strategy"),
               **_metrics(bnh_returns,   "BuyHold")}

    if verbose:
        print()
        print("=" * 60)
        print("  BACKTEST RESULTS")
        print("  WARNING: Educational use only. Not financial advice.")
        print("=" * 60)
        fmt = {
            "total_return":  "%",
            "annual_return": "%",
            "annual_vol":    "%",
            "sharpe":        "x",
            "max_drawdown":  "%",
            "win_rate":      "%",
        }
        print(f"  {'Metric':<28} {'Strategy':>12}  {'Buy&Hold':>12}")
        print(f"  {'-'*28} {'-'*12}  {'-'*12}")
        for key, unit in fmt.items():
            sv = metrics[f"Strategy_{key}"]
            bv = metrics[f"BuyHold_{key}"]
            if unit == "%":
                print(f"  {key:<28} {sv*100:>11.2f}%  {bv*100:>11.2f}%")
            else:
                print(f"  {key:<28} {sv:>12.2f}  {bv:>12.2f}")
        print(f"\n  Strategy trades: {metrics['Strategy_n_trades']:.0f}")
        print(f"  Transaction cost: {transaction_cost*100:.2f}% per side")
        print("=" * 60)

    return results_df, metrics


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from data_loader import load_data
    from features import get_feature_matrix, compute_features
    from hmm_model import train_hmm, decode_states
    from regime_interpreter import interpret_regimes, build_regime_series

    df = load_data("^GSPC", "2015-01-01", "2023-12-31")
    X, dates, scaler = get_feature_matrix(df)
    model  = train_hmm(X, n_states=3)
    states = decode_states(model, X)
    feat_df = compute_features(df).loc[dates]
    stats, labels = interpret_regimes(feat_df, states, df, verbose=False)
    regime_df = build_regime_series(dates, states, labels)
    signal_df = build_signal(regime_df, labels, stats_df=stats)
    results, metrics = run_backtest(df, signal_df)
