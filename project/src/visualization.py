"""Visualization helpers for HMM market regimes."""

from __future__ import annotations

from pathlib import Path
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


def plot_price_regimes(
    frame: pd.DataFrame,
    output_path: str | Path,
    title: str = "HMM Market Regime Detection",
) -> Path:
    """Plot the close price and color points by inferred market state."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(frame.index, frame["close"], color="black", linewidth=1.2, alpha=0.7, label="Close")

    for state in sorted(frame["hidden_state"].unique()):
        subset = frame[frame["hidden_state"] == state]
        ax.scatter(subset.index, subset["close"], s=9, label=f"State {state}", alpha=0.75)

    ax.set_title(title)
    ax.set_xlabel("Date")
    ax.set_ylabel("Price")
    ax.legend(loc="best")
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def plot_equity_curves(results: pd.DataFrame, output_path: str | Path) -> Path:
    """Plot strategy equity versus buy-and-hold equity."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(results.index, results["strategy_equity"], label="HMM Strategy", linewidth=1.8)
    ax.plot(results.index, results["buy_hold_equity"], label="Buy & Hold", linewidth=1.5)
    ax.set_title("Backtest Equity Curve")
    ax.set_xlabel("Date")
    ax.set_ylabel("Growth of 1.0")
    ax.grid(alpha=0.25)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
