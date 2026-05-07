"""
ALGHREST — Backtesting Engine
VectorBT-based backtesting wrapper with standardized interface.
Every Tier 4 strategy uses this engine before going live.

Validation thresholds (STRATEGY_VALIDATION):
  - Minimum 5 years of data
  - Minimum 50 trades/year for statistical significance
  - Sharpe >= 1.0 (in-sample), >= 0.8 (walk-forward OOS)
  - Max drawdown < 25%
  - Profit factor >= 1.3
  - Walk-forward efficiency >= 60%
  - Monte Carlo ruin probability < 1%
"""
from __future__ import annotations

import warnings
from datetime import datetime
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd
import structlog

warnings.filterwarnings("ignore", category=FutureWarning)

from core.data.models import (
    BacktestResult,
    MonteCarloResult,
    Timeframe,
    WalkForwardResult,
    WalkForwardWindow,
)

logger = structlog.get_logger(__name__)

# ── VALIDATION THRESHOLDS ─────────────────────────────────────────────────────
STRATEGY_VALIDATION = {
    "min_backtest_years": 5,
    "min_trades_per_year": 50,
    "min_sharpe_insample": 1.0,
    "min_sharpe_walkforward": 0.8,
    "max_drawdown_pct": 25.0,
    "min_profit_factor": 1.3,
    "wf_windows": 8,
    "wf_efficiency": 0.6,
    "mc_simulations": 10_000,
    "mc_max_ruin_probability": 0.01,
    "mc_var_95": 0.15,
}


class BacktestEngine:
    """
    Standardized backtesting engine for all 8 Tier 4 strategies.

    Usage:
        engine = BacktestEngine(strategy_id="trend_follower", symbol="BTC/USDT")
        result = engine.run(ohlcv_df, entry_signals, exit_signals)
        is_valid = engine.validate(result)
        wf_result = engine.walk_forward(ohlcv_df, strategy_fn, params)
        mc_result = engine.monte_carlo(result)
    """

    def __init__(
        self,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        timeframe: Timeframe = Timeframe.D1,
        initial_capital: float = 100_000.0,
        commission_pct: float = 0.001,   # 0.1% per trade (taker fee)
        slippage_pct: float = 0.0005,    # 0.05% slippage
    ) -> None:
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

    def run(
        self,
        ohlcv: pd.DataFrame,
        entries: pd.Series,
        exits: pd.Series,
        size_pct: float = 0.95,          # % of capital per trade
    ) -> BacktestResult:
        """
        Run vectorized backtest.

        Args:
            ohlcv: DataFrame with columns open, high, low, close, volume
            entries: Boolean Series (True = enter long)
            exits: Boolean Series (True = exit long)
            size_pct: Fraction of available capital per trade

        Returns:
            BacktestResult with all performance metrics.
        """
        try:
            import vectorbt as vbt
        except ImportError:
            logger.warning("vectorbt not installed — using simplified backtest")
            return self._simple_backtest(ohlcv, entries, exits)

        close = ohlcv["close"]
        pf = vbt.Portfolio.from_signals(
            close=close,
            entries=entries,
            exits=exits,
            size=size_pct,
            size_type="percent",
            init_cash=self.initial_capital,
            fees=self.commission_pct + self.slippage_pct,
            freq="D" if self.timeframe == Timeframe.D1 else "h",
        )

        return self._extract_metrics(pf, ohlcv)

    def _extract_metrics(self, pf: Any, ohlcv: pd.DataFrame) -> BacktestResult:
        """Extract all metrics from VectorBT Portfolio object."""
        stats = pf.stats()
        trades_df = pf.trades.records_readable if len(pf.trades.records) > 0 else pd.DataFrame()

        total_return = float(stats.get("Total Return [%]", 0)) / 100
        total_trades = int(stats.get("Total Trades", 0))
        days = len(ohlcv)
        years = days / 252

        winning = len(trades_df[trades_df["PnL"] > 0]) if len(trades_df) > 0 else 0
        losing = len(trades_df[trades_df["PnL"] <= 0]) if len(trades_df) > 0 else 0

        gross_profit = trades_df[trades_df["PnL"] > 0]["PnL"].sum() if winning > 0 else 0
        gross_loss = abs(trades_df[trades_df["PnL"] <= 0]["PnL"].sum()) if losing > 0 else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        sharpe = float(pf.sharpe_ratio(freq="252D") or 0)
        sortino = float(pf.sortino_ratio(freq="252D") or 0)
        max_dd = float(abs(pf.max_drawdown()) * 100)
        calmar = (total_return / years) / (max_dd / 100) if max_dd > 0 else 0

        avg_return_per_trade = trades_df["Return [%]"].mean() if len(trades_df) > 0 else 0

        failure_reasons = self._check_validation(
            sharpe=sharpe,
            max_dd=max_dd,
            trades_per_year=total_trades / max(years, 0.1),
            profit_factor=profit_factor,
            years=years,
        )

        return BacktestResult(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_date=ohlcv.index[0] if hasattr(ohlcv.index[0], "to_pydatetime") else datetime.utcnow(),
            end_date=ohlcv.index[-1] if hasattr(ohlcv.index[-1], "to_pydatetime") else datetime.utcnow(),
            initial_capital=self.initial_capital,
            final_capital=float(pf.final_value()),
            total_return_pct=total_return * 100,
            annualized_return_pct=(total_return / max(years, 0.01)) * 100,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            max_drawdown_pct=max_dd,
            max_drawdown_duration_days=int(pf.max_drawdown_duration().days) if hasattr(pf.max_drawdown_duration(), "days") else 0,
            total_trades=total_trades,
            winning_trades=winning,
            losing_trades=losing,
            win_rate_pct=(winning / total_trades * 100) if total_trades > 0 else 0,
            profit_factor=profit_factor,
            avg_return_per_trade_pct=float(avg_return_per_trade),
            avg_winning_trade_pct=float(trades_df[trades_df["PnL"] > 0]["Return [%]"].mean() if winning > 0 else 0),
            avg_losing_trade_pct=float(trades_df[trades_df["PnL"] <= 0]["Return [%]"].mean() if losing > 0 else 0),
            largest_winner_pct=float(trades_df["Return [%]"].max() if len(trades_df) > 0 else 0),
            largest_loser_pct=float(trades_df["Return [%]"].min() if len(trades_df) > 0 else 0),
            max_consecutive_losses=self._max_consecutive_losses(trades_df),
            avg_holding_hours=self._avg_holding_hours(trades_df),
            trades_per_year=total_trades / max(years, 0.01),
            passed_validation=len(failure_reasons) == 0,
            failure_reasons=failure_reasons,
        )

    def _simple_backtest(self, ohlcv: pd.DataFrame, entries: pd.Series, exits: pd.Series) -> BacktestResult:
        """Fallback backtest without VectorBT — simplified vectorized simulation."""
        close = ohlcv["close"].values
        capital = self.initial_capital
        position = 0.0
        entry_price = 0.0
        trades: list[dict] = []

        for i in range(1, len(close)):
            if entries.iloc[i] and position == 0:
                # Enter
                fee = capital * self.commission_pct
                position = (capital - fee) / close[i]
                entry_price = close[i]
                capital -= fee

            elif (exits.iloc[i] or i == len(close) - 1) and position > 0:
                # Exit
                exit_value = position * close[i]
                fee = exit_value * self.commission_pct
                pnl = exit_value - fee - (position * entry_price)
                trades.append({"pnl": pnl, "return_pct": pnl / (position * entry_price) * 100})
                capital = exit_value - fee
                position = 0
                entry_price = 0

        final_capital = capital + (position * close[-1] if position > 0 else 0)
        total_return = (final_capital - self.initial_capital) / self.initial_capital * 100
        years = len(close) / 252
        trades_df = pd.DataFrame(trades)

        winning = sum(1 for t in trades if t["pnl"] > 0)
        losing = sum(1 for t in trades if t["pnl"] <= 0)
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] <= 0))

        # Compute Sharpe from trade returns
        returns = np.array([t["return_pct"] / 100 for t in trades]) if trades else np.array([0])
        sharpe = float(returns.mean() / (returns.std() + 1e-10) * np.sqrt(252)) if len(returns) > 1 else 0

        failure_reasons = self._check_validation(
            sharpe=sharpe,
            max_dd=30.0,  # simplified
            trades_per_year=len(trades) / max(years, 0.01),
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else 0,
            years=years,
        )

        return BacktestResult(
            strategy_id=self.strategy_id, strategy_name=self.strategy_name,
            symbol=self.symbol, timeframe=self.timeframe,
            start_date=datetime.utcnow(), end_date=datetime.utcnow(),
            initial_capital=self.initial_capital, final_capital=final_capital,
            total_return_pct=total_return, annualized_return_pct=total_return / max(years, 0.01),
            sharpe_ratio=sharpe, sortino_ratio=0, calmar_ratio=0, max_drawdown_pct=30,
            max_drawdown_duration_days=0, total_trades=len(trades), winning_trades=winning,
            losing_trades=losing, win_rate_pct=winning / len(trades) * 100 if trades else 0,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else 0,
            avg_return_per_trade_pct=float(trades_df["return_pct"].mean()) if trades else 0,
            avg_winning_trade_pct=0, avg_losing_trade_pct=0, largest_winner_pct=0, largest_loser_pct=0,
            max_consecutive_losses=0, avg_holding_hours=24, trades_per_year=len(trades) / max(years, 0.01),
            passed_validation=len(failure_reasons) == 0, failure_reasons=failure_reasons,
        )

    @staticmethod
    def _check_validation(
        sharpe: float, max_dd: float, trades_per_year: float, profit_factor: float, years: float
    ) -> list[str]:
        failures = []
        if years < STRATEGY_VALIDATION["min_backtest_years"]:
            failures.append(f"Insufficient history: {years:.1f}y < {STRATEGY_VALIDATION['min_backtest_years']}y")
        if sharpe < STRATEGY_VALIDATION["min_sharpe_insample"]:
            failures.append(f"Sharpe {sharpe:.2f} < {STRATEGY_VALIDATION['min_sharpe_insample']}")
        if max_dd > STRATEGY_VALIDATION["max_drawdown_pct"]:
            failures.append(f"Max DD {max_dd:.1f}% > {STRATEGY_VALIDATION['max_drawdown_pct']}%")
        if trades_per_year < STRATEGY_VALIDATION["min_trades_per_year"]:
            failures.append(f"Trades/year {trades_per_year:.0f} < {STRATEGY_VALIDATION['min_trades_per_year']}")
        if profit_factor < STRATEGY_VALIDATION["min_profit_factor"]:
            failures.append(f"Profit factor {profit_factor:.2f} < {STRATEGY_VALIDATION['min_profit_factor']}")
        return failures

    def walk_forward(
        self,
        ohlcv: pd.DataFrame,
        strategy_fn: Callable,
        params: dict[str, Any],
        n_windows: int = 8,
        train_pct: float = 0.7,
    ) -> WalkForwardResult:
        """
        Walk-forward analysis with n_windows train/test splits.
        strategy_fn(ohlcv_slice, params) → (entries, exits)
        """
        total_bars = len(ohlcv)
        window_size = total_bars // n_windows
        windows: list[WalkForwardWindow] = []

        for i in range(n_windows):
            start_idx = i * window_size
            end_idx = min((i + 2) * window_size, total_bars)
            slice_df = ohlcv.iloc[start_idx:end_idx]

            train_size = int(len(slice_df) * train_pct)
            train_df = slice_df.iloc[:train_size]
            test_df = slice_df.iloc[train_size:]

            if len(train_df) < 50 or len(test_df) < 20:
                continue

            try:
                train_entries, train_exits = strategy_fn(train_df, params)
                is_result = self.run(train_df, train_entries, train_exits)

                test_entries, test_exits = strategy_fn(test_df, params)
                oos_result = self.run(test_df, test_entries, test_exits)

                windows.append(WalkForwardWindow(
                    window_index=i,
                    train_start=train_df.index[0],
                    train_end=train_df.index[-1],
                    test_start=test_df.index[0],
                    test_end=test_df.index[-1],
                    in_sample=is_result,
                    out_of_sample=oos_result,
                ))
            except Exception as e:
                logger.warning("walk-forward window failed", window=i, error=str(e))

        if not windows:
            return WalkForwardResult(
                strategy_id=self.strategy_id, windows=[],
                avg_oos_sharpe=0, avg_oos_return_pct=0, avg_wf_efficiency=0,
                passed_validation=False, failure_reasons=["No walk-forward windows completed"],
            )

        avg_oos_sharpe = float(np.mean([w.out_of_sample.sharpe_ratio for w in windows]))
        avg_oos_return = float(np.mean([w.out_of_sample.annualized_return_pct for w in windows]))
        avg_efficiency = float(np.mean([w.wf_efficiency for w in windows]))

        failures = []
        if avg_oos_sharpe < STRATEGY_VALIDATION["min_sharpe_walkforward"]:
            failures.append(f"OOS Sharpe {avg_oos_sharpe:.2f} < {STRATEGY_VALIDATION['min_sharpe_walkforward']}")
        if avg_efficiency < STRATEGY_VALIDATION["wf_efficiency"]:
            failures.append(f"WF efficiency {avg_efficiency:.2f} < {STRATEGY_VALIDATION['wf_efficiency']}")

        return WalkForwardResult(
            strategy_id=self.strategy_id,
            windows=windows,
            avg_oos_sharpe=avg_oos_sharpe,
            avg_oos_return_pct=avg_oos_return,
            avg_wf_efficiency=avg_efficiency,
            passed_validation=len(failures) == 0,
            failure_reasons=failures,
        )

    def monte_carlo(
        self, backtest_result: BacktestResult, n_simulations: int = 10_000
    ) -> MonteCarloResult:
        """
        Bootstrap Monte Carlo by randomly sampling trade returns.
        Tests ruin probability and VaR of the strategy.
        """
        if backtest_result.total_trades == 0:
            return MonteCarloResult(
                strategy_id=self.strategy_id, simulations=0,
                var_95=1.0, var_99=1.0, cvar_95=1.0,
                ruin_probability=1.0, median_return_pct=0, percentile_5_return_pct=0,
                percentile_95_return_pct=0, passed_validation=False,
            )

        # Reconstruct trade return distribution from backtest stats
        win_rate = backtest_result.win_rate_pct / 100
        avg_win = backtest_result.avg_winning_trade_pct / 100
        avg_loss = abs(backtest_result.avg_losing_trade_pct / 100)

        rng = np.random.default_rng(seed=42)
        simulation_returns = []

        for _ in range(n_simulations):
            capital = 1.0
            n_trades = int(backtest_result.trades_per_year * 3)  # Simulate 3 years
            for _ in range(n_trades):
                if rng.random() < win_rate:
                    trade_return = rng.normal(avg_win, avg_win * 0.5)
                else:
                    trade_return = -rng.normal(avg_loss, avg_loss * 0.5)
                capital *= (1 + trade_return)
                if capital <= 0.5:  # 50% ruin threshold
                    break
            simulation_returns.append(capital - 1.0)

        returns_arr = np.array(simulation_returns)
        ruin_prob = float(np.mean(returns_arr < -0.5))
        var_95 = float(-np.percentile(returns_arr, 5))
        var_99 = float(-np.percentile(returns_arr, 1))
        cvar_95 = float(-returns_arr[returns_arr <= -var_95].mean()) if any(returns_arr <= -var_95) else var_95

        failures = []
        if ruin_prob > STRATEGY_VALIDATION["mc_max_ruin_probability"]:
            failures.append(f"Ruin probability {ruin_prob:.2%} > 1% limit")
        if var_95 > STRATEGY_VALIDATION["mc_var_95"]:
            failures.append(f"95% VaR {var_95:.2%} > 15% limit")

        return MonteCarloResult(
            strategy_id=self.strategy_id,
            simulations=n_simulations,
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            ruin_probability=ruin_prob,
            median_return_pct=float(np.median(returns_arr) * 100),
            percentile_5_return_pct=float(np.percentile(returns_arr, 5) * 100),
            percentile_95_return_pct=float(np.percentile(returns_arr, 95) * 100),
            passed_validation=len(failures) == 0,
        )

    @staticmethod
    def _max_consecutive_losses(trades_df: pd.DataFrame) -> int:
        if len(trades_df) == 0:
            return 0
        is_loss = (trades_df["PnL"] <= 0).astype(int) if "PnL" in trades_df.columns else pd.Series([0])
        max_streak = 0
        streak = 0
        for v in is_loss:
            if v:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        return max_streak

    @staticmethod
    def _avg_holding_hours(trades_df: pd.DataFrame) -> float:
        if len(trades_df) == 0 or "Duration" not in trades_df.columns:
            return 24.0
        try:
            return float(trades_df["Duration"].mean().total_seconds() / 3600)
        except Exception:
            return 24.0

    def validate_all(
        self, backtest: BacktestResult, wf: WalkForwardResult, mc: MonteCarloResult
    ) -> tuple[bool, list[str]]:
        """Final go/no-go decision — ALL three tests must pass."""
        all_failures = backtest.failure_reasons + wf.failure_reasons + mc.failure_reasons
        passed = len(all_failures) == 0
        if not passed:
            logger.warning(
                "strategy failed validation",
                strategy_id=self.strategy_id,
                failures=all_failures,
            )
        else:
            logger.info("strategy PASSED validation", strategy_id=self.strategy_id)
        return passed, all_failures
