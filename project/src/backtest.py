"""Simple educational backtest for HMM-derived market regimes."""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestResult:
    equity_frame: pd.DataFrame
    metrics: pd.DataFrame


def select_long_states(state_summary: pd.DataFrame) -> set[int]:
    """Long states have positive average return and not extreme volatility."""

    median_volatility = state_summary["mean_volatility"].median()
    selected = state_summary[
        (state_summary["mean_return"] > 0)
        & (state_summary["mean_volatility"] <= median_volatility * 1.25)
    ]["state"]
    return set(selected.astype(int).tolist())


def _max_drawdown(equity: pd.Series) -> float:
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def _metrics(returns: pd.Series, equity: pd.Series, trades: int) -> dict[str, float]:
    returns = returns.dropna()
    total_return = float(equity.iloc[-1] - 1.0)
    years = max(len(returns) / 252, 1 / 252)
    annualized_return = float((1.0 + total_return) ** (1.0 / years) - 1.0)
    sharpe = 0.0
    if returns.std(ddof=0) > 0:
        sharpe = float(np.sqrt(252) * returns.mean() / returns.std(ddof=0))
    win_rate = float((returns > 0).mean()) if len(returns) else 0.0
    return {
        "total_return": total_return,
        "annualized_return": annualized_return,
        "sharpe_ratio": sharpe,
        "max_drawdown": _max_drawdown(equity),
        "win_rate": win_rate,
        "number_of_trades": float(trades),
    }


def run_regime_strategy(
    frame: pd.DataFrame,
    state_summary: pd.DataFrame,
    transaction_cost: float = 0.0005,
) -> BacktestResult:
    """Backtest a long-only HMM regime strategy.

    The signal is shifted by one day to avoid using today's decoded state for a
    same-day trade. This remains an educational backtest, not investment advice.
    """

    long_states = select_long_states(state_summary)
    result = frame.copy()
    result["signal"] = result["hidden_state"].isin(long_states).astype(int)
    result["position"] = result["signal"].shift(1).fillna(0)
    result["turnover"] = result["position"].diff().abs().fillna(result["position"])
    result["strategy_return"] = (
        result["position"] * result["daily_return"] - result["turnover"] * transaction_cost
    )
    result["buy_hold_return"] = result["daily_return"]
    result["strategy_equity"] = (1.0 + result["strategy_return"]).cumprod()
    result["buy_hold_equity"] = (1.0 + result["buy_hold_return"]).cumprod()

    strategy_trades = int((result["turnover"] > 0).sum())
    metrics = pd.DataFrame(
        [
            {"portfolio": "HMM Strategy", **_metrics(result["strategy_return"], result["strategy_equity"], strategy_trades)},
            {"portfolio": "Buy & Hold", **_metrics(result["buy_hold_return"], result["buy_hold_equity"], 1)},
        ]
    )
    return BacktestResult(equity_frame=result, metrics=metrics)
