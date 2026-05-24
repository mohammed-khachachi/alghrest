"""
visualization.py
================
Generates all project charts and saves them to outputs/figures/.

Charts produced:
  1. Price chart with coloured hidden state backgrounds
  2. Equity curve: Strategy vs Buy-and-Hold
  3. Regime distribution pie chart
  4. Feature distributions per regime (optional)

All charts are saved as PNG files — no GUI window is opened.
"""

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend (no display required)
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path
from typing import Dict, Optional

from src.core.paths import get_output_path


__all__ = [
    "STATE_COLORS",
    "_get_figures_dir",
    "_ensure_dir",
    "plot_price_with_regimes",
    "plot_equity_curves",
    "plot_regime_distribution",
    "plot_transition_matrix",
    "generate_all_charts",
]


# Color palette for up to 6 hidden states
STATE_COLORS = [
    "#4CAF50",   # Green   — typically Bullish
    "#F44336",   # Red     — typically Bearish
    "#2196F3",   # Blue    — Sideways / Moderate
    "#FF9800",   # Orange  — High-Vol
    "#9C27B0",   # Purple  — State 4
    "#795548",   # Brown   — State 5
]


def _get_figures_dir() -> Path:
    return get_output_path("figures")


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def plot_price_with_regimes(
    df_price: pd.DataFrame,
    regime_df: pd.DataFrame,
    labels: Dict[int, str],
    ticker: str = "Market",
    save: bool = True,
    filename: str = "01_price_regimes.png",
) -> None:
    """
    Plot the close price with coloured background for each HMM state.
    """
    figures_dir = _get_figures_dir()
    _ensure_dir(figures_dir)

    fig, ax = plt.subplots(figsize=(16, 6))
    ax.set_facecolor("#f8f9fa")
    fig.patch.set_facecolor("#ffffff")

    # Align price to regime dates
    price = df_price["close"].reindex(regime_df.index)
    dates = regime_df.index
    states = regime_df["state"].values
    n_states = len(labels)

    # Shade background by regime
    i = 0
    while i < len(states):
        j = i
        current_state = states[i]
        while j < len(states) and states[j] == current_state:
            j += 1
        color = STATE_COLORS[current_state % len(STATE_COLORS)]
        ax.axvspan(dates[i], dates[min(j, len(dates)-1)], alpha=0.15, color=color)
        i = j

    # Price line
    ax.plot(dates, price.values, color="#1a1a2e", linewidth=1.2, zorder=5, label="Close Price")
    ax.set_yscale("log")
    ax.set_title(f"HMM Market Regime Detection — {ticker}", fontsize=14, fontweight="bold", pad=12)
    ax.set_ylabel("Price (log scale)", fontsize=11)
    ax.set_xlabel("Date", fontsize=11)
    ax.grid(True, alpha=0.3, linestyle="--")

    # Legend patches
    patches = [
        mpatches.Patch(color=STATE_COLORS[sid % len(STATE_COLORS)], alpha=0.5,
                       label=f"State {sid}: {lbl}")
        for sid, lbl in labels.items()
    ]
    ax.legend(handles=patches, loc="upper left", fontsize=9, framealpha=0.9)

    plt.tight_layout()
    out_path = figures_dir / filename
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHART] Saved: {out_path}")


def plot_equity_curves(
    results_df: pd.DataFrame,
    save: bool = True,
    filename: str = "02_equity_curves.png",
) -> None:
    """
    Plot Strategy vs Buy-and-Hold equity curves.
    """
    figures_dir = _get_figures_dir()
    _ensure_dir(figures_dir)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 9), gridspec_kw={"height_ratios": [3, 1]})

    # --- Top: Equity curves ---
    ax1.set_facecolor("#f8f9fa")
    ax1.plot(results_df.index, results_df["strat_equity"],
             color="#1565C0", linewidth=1.8, label="HMM Strategy", zorder=5)
    ax1.plot(results_df.index, results_df["bnh_equity"],
             color="#B71C1C", linewidth=1.4, linestyle="--", label="Buy & Hold", alpha=0.85)
    ax1.set_title("HMM Strategy vs Buy & Hold — Equity Curves", fontsize=13, fontweight="bold")
    ax1.set_ylabel("Portfolio Value (start = 1.0)", fontsize=11)
    ax1.legend(fontsize=10, framealpha=0.9)
    ax1.grid(True, alpha=0.3, linestyle="--")
    ax1.set_yscale("log")

    # --- Bottom: Signal (in-market indicator) ---
    ax2.set_facecolor("#f8f9fa")
    ax2.fill_between(results_df.index, results_df["signal"], alpha=0.4, color="#1565C0")
    ax2.set_ylabel("In Market", fontsize=10)
    ax2.set_xlabel("Date", fontsize=10)
    ax2.set_ylim(-0.1, 1.3)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(["Cash", "Long"])
    ax2.grid(True, alpha=0.3, linestyle="--")

    # Disclaimer annotation
    fig.text(0.01, 0.01,
             "⚠ Educational backtest only — NOT financial advice. In-sample results may be overfitted.",
             fontsize=8, color="gray", style="italic")

    plt.tight_layout()
    out_path = figures_dir / filename
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHART] Saved: {out_path}")


def plot_regime_distribution(
    stats_df: pd.DataFrame,
    labels: Dict[int, str],
    save: bool = True,
    filename: str = "03_regime_distribution.png",
) -> None:
    """
    Pie chart of time spent in each regime.
    """
    figures_dir = _get_figures_dir()
    _ensure_dir(figures_dir)

    fig, ax = plt.subplots(figsize=(8, 6))

    sizes  = [stats_df.loc[sid, "n_days"] for sid in labels]
    clrs   = [STATE_COLORS[sid % len(STATE_COLORS)] for sid in labels]
    lbls   = [f"State {sid}\n{lbl}\n({stats_df.loc[sid,'pct_of_time']:.1f}%)"
               for sid, lbl in labels.items()]

    wedges, texts, autotexts = ax.pie(
        sizes, labels=lbls, colors=clrs,
        autopct="%1.0f%%", startangle=140,
        pctdistance=0.75, textprops={"fontsize": 9}
    )
    ax.set_title("Market Regime Distribution\n(HMM Hidden States)", fontsize=13, fontweight="bold")

    plt.tight_layout()
    out_path = figures_dir / filename
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHART] Saved: {out_path}")


def plot_transition_matrix(
    trans_df: pd.DataFrame,
    save: bool = True,
    filename: str = "04_transition_matrix.png",
) -> None:
    """
    Heatmap of the HMM transition probability matrix A.
    """
    figures_dir = _get_figures_dir()
    _ensure_dir(figures_dir)

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(trans_df.values, cmap="Blues", vmin=0, vmax=1)

    # Labels
    n = len(trans_df)
    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels([f"→ {c}" for c in trans_df.columns], fontsize=10)
    ax.set_yticklabels([f"{r} →" for r in trans_df.index], fontsize=10)
    ax.set_title("HMM Transition Matrix A\nP(next state | current state)", fontsize=12, fontweight="bold")

    # Cell annotations
    for i in range(n):
        for j in range(n):
            val = trans_df.values[i, j]
            color = "white" if val > 0.5 else "black"
            ax.text(j, i, f"{val:.3f}", ha="center", va="center", fontsize=10, color=color)

    plt.colorbar(im, ax=ax, shrink=0.8, label="Probability")
    plt.tight_layout()
    out_path = figures_dir / filename
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[CHART] Saved: {out_path}")


def generate_all_charts(
    df_price: pd.DataFrame,
    regime_df: pd.DataFrame,
    labels: Dict[int, str],
    stats_df: pd.DataFrame,
    results_df: pd.DataFrame,
    trans_df: pd.DataFrame,
    ticker: str = "Market",
) -> None:
    """Generate and save all project charts."""
    print("\n[CHARTS] Generating figures...")
    plot_price_with_regimes(df_price, regime_df, labels, ticker=ticker)
    plot_equity_curves(results_df)
    plot_regime_distribution(stats_df, labels)
    plot_transition_matrix(trans_df)
    print(f"[CHARTS] All figures saved to: {_get_figures_dir()}")


if __name__ == "__main__":
    print("[viz] Visualization module loaded successfully.")
    print(f"[viz] Figures will be saved to: {_get_figures_dir()}")
