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

from collections.abc import Callable
from math import ceil, isfinite
from typing import Any

import numpy as np
import pandas as pd
import structlog

from backtesting.path_risk import LossStreakConfig, LossStreakStudy, loss_streak_analysis
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
        engine = BacktestEngine("trend_follower", "Trend follower", "BTC/USDT")
        result = engine.run(ohlcv_df, entry_signals, exit_signals)
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
        commission_pct: float = 0.001,  # 0.1% per trade (taker fee)
        slippage_pct: float = 0.0005,  # 0.05% slippage
    ) -> None:
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.timeframe = timeframe
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct
        self.slippage_pct = slippage_pct

    @staticmethod
    def _years(index: pd.DatetimeIndex) -> float:
        # Elapsed calendar time, independent of bar count, weekends and timeframe.
        return float((index[-1] - index[0]) / pd.Timedelta(days=365.25))

    def _validate_inputs(
        self, ohlcv: pd.DataFrame, entries: pd.Series, exits: pd.Series, size_pct: float
    ) -> None:
        index = ohlcv.index
        if (
            not isinstance(index, pd.DatetimeIndex)
            or len(index) < 2
            or index.hasnans
            or not index.is_unique
            or not index.is_monotonic_increasing
        ):
            raise ValueError("Backtests require at least two unique, increasing timestamps")
        if (
            "close" not in ohlcv
            or not np.isfinite(ohlcv["close"]).all()
            or (ohlcv["close"] <= 0).any()
        ):
            raise ValueError("Close prices must be finite and positive")
        for signal in (entries, exits):
            if (
                not signal.index.equals(index)
                or not pd.api.types.is_bool_dtype(signal.dtype)
                or signal.isna().any()
            ):
                raise ValueError("Signals must be non-null booleans aligned to the price index")
        if not isfinite(size_pct) or not 0 < size_pct <= 1:
            raise ValueError("size_pct must be in (0, 1]")
        if not isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("Initial capital must be finite and positive")
        if any(
            not isfinite(value) or not 0 <= value < 1
            for value in (self.commission_pct, self.slippage_pct)
        ):
            raise ValueError("Commission and slippage must be finite fractions in [0, 1)")

    def run(
        self,
        ohlcv: pd.DataFrame,
        entries: pd.Series,
        exits: pd.Series,
        size_pct: float = 0.95,
    ) -> BacktestResult:
        """Simulate long-only close-price signals; mark remaining inventory to market.

        Fees apply on each side and slippage changes the execution price. Signals
        are assumed known at execution time; callers must shift predictive signals
        themselves when they use the current bar's closing information.
        """
        self._validate_inputs(ohlcv, entries, exits, size_pct)
        try:
            import vectorbt as vbt
        except ImportError:
            logger.warning("vectorbt not installed — using equivalent long-only simulator")
            return self._simple_backtest(ohlcv, entries, exits, size_pct)

        frequencies = {
            Timeframe.M1: "1min",
            Timeframe.M5: "5min",
            Timeframe.M15: "15min",
            Timeframe.M30: "30min",
            Timeframe.H1: "1h",
            Timeframe.H4: "4h",
            Timeframe.D1: "1D",
            Timeframe.W1: "7D",
        }
        pf = vbt.Portfolio.from_signals(
            close=ohlcv["close"],
            entries=entries,
            exits=exits,
            size=size_pct,
            size_type="percent",
            init_cash=self.initial_capital,
            fees=self.commission_pct,
            slippage=self.slippage_pct,
            freq=frequencies[self.timeframe],
            upon_long_conflict="ignore",
        )
        return self._extract_metrics(pf, ohlcv)

    def _extract_metrics(self, pf: Any, ohlcv: pd.DataFrame) -> BacktestResult:
        """Normalize closed VectorBT trades; open inventory affects equity only."""
        trades = pf.trades.closed.records_readable.copy()
        if not trades.empty:
            # Include the entry fee in committed capital, as well as both fees in PnL.
            cost = trades["Size"] * trades["Avg Entry Price"] + trades["Entry Fees"]
            trades["Return"] = trades["PnL"] / cost
            trades["Duration"] = trades["Exit Timestamp"] - trades["Entry Timestamp"]
        return self._result(ohlcv, pf.value(), trades)

    def _simple_backtest(
        self, ohlcv: pd.DataFrame, entries: pd.Series, exits: pd.Series, size_pct: float = 0.95
    ) -> BacktestResult:
        """Same long-only order semantics as run(), without the VectorBT dependency."""
        self._validate_inputs(ohlcv, entries, exits, size_pct)
        cash = self.initial_capital
        quantity, entry_cost = 0.0, 0.0
        entry_time = ohlcv.index[0]
        equity = []
        trades = []
        for timestamp, price, enter, leave in zip(
            ohlcv.index, ohlcv["close"], entries, exits, strict=True
        ):
            if enter and leave:
                pass  # simultaneous opposing signals are ignored in both backends
            elif enter and quantity == 0:
                entry_cost = cash * size_pct
                execution_price = price * (1 + self.slippage_pct)
                quantity = entry_cost / (execution_price * (1 + self.commission_pct))
                cash -= entry_cost
                entry_time = timestamp
            elif leave and quantity > 0:
                proceeds = quantity * price * (1 - self.slippage_pct) * (1 - self.commission_pct)
                pnl = proceeds - entry_cost
                trades.append(
                    {
                        "PnL": pnl,
                        "Return": pnl / entry_cost,
                        "Duration": timestamp - entry_time,
                    }
                )
                cash += proceeds
                quantity = 0.0
            equity.append(cash + quantity * price)
        return self._result(ohlcv, pd.Series(equity, index=ohlcv.index), pd.DataFrame(trades))

    def _result(
        self, ohlcv: pd.DataFrame, equity: pd.Series, trades: pd.DataFrame
    ) -> BacktestResult:
        years = self._years(ohlcv.index)
        values = equity.to_numpy(dtype=float)
        if not np.isfinite(values).all() or (values < 0).any():
            raise ValueError("Backtest equity must be finite and non-negative")
        final_capital = float(values[-1])
        total_return = final_capital / self.initial_capital - 1
        with np.errstate(over="ignore"):
            annualized = (
                float(np.expm1(np.log1p(total_return) / years)) if final_capital > 0 else -1.0
            )
        # Include idle calendar days. Daily marks avoid annualizing hourly/minute
        # returns as if every bar were an independent trading day.
        daily = equity.resample("D").last().ffill().to_numpy(dtype=float)
        previous = np.r_[self.initial_capital, daily[:-1]]
        daily_returns = np.divide(
            daily - previous, previous, out=np.zeros_like(daily), where=previous > 0
        )
        std = float(daily_returns.std(ddof=1)) if len(daily_returns) > 1 else 0.0
        mean = float(daily_returns.mean())
        sharpe = mean / std * np.sqrt(365.25) if std > 0 else 0.0
        downside = float(np.sqrt(np.mean(np.minimum(daily_returns, 0) ** 2)))
        sortino = mean / downside * np.sqrt(365.25) if downside > 0 else 0.0

        peaks = np.maximum.accumulate(np.r_[self.initial_capital, values])[1:]
        max_dd = float(np.max(1 - values / peaks) * 100)
        peak_value, peak_time = self.initial_capital, ohlcv.index[0]
        max_duration = pd.Timedelta(0)
        underwater = False
        for timestamp, value in equity.items():
            if value < peak_value:
                underwater = True
                max_duration = max(max_duration, timestamp - peak_time)
            else:
                # Include the recovery timestamp when measuring the underwater interval.
                if underwater:
                    max_duration = max(max_duration, timestamp - peak_time)
                peak_value, peak_time = value, timestamp
                underwater = False

        count = len(trades)
        pnls = trades["PnL"].to_numpy(dtype=float) if count else np.array([], dtype=float)
        returns = trades["Return"].to_numpy(dtype=float) if count else np.array([], dtype=float)
        winning, losing = pnls > 0, pnls <= 0
        gross_profit, gross_loss = float(pnls[winning].sum()), float(-pnls[losing].sum())
        profit_factor = (
            gross_profit / gross_loss
            if gross_loss > 0
            else (float("inf") if gross_profit > 0 else 0.0)
        )
        trades_per_year = count / years
        failures = self._check_validation(
            float(sharpe), max_dd, trades_per_year, profit_factor, years
        )
        if not isfinite(annualized):
            failures.append("Annualized return is not finite")
        return BacktestResult(
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            symbol=self.symbol,
            timeframe=self.timeframe,
            start_date=ohlcv.index[0].to_pydatetime(),
            end_date=ohlcv.index[-1].to_pydatetime(),
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return_pct=total_return * 100,
            annualized_return_pct=annualized * 100,
            sharpe_ratio=float(sharpe),
            sortino_ratio=float(sortino),
            calmar_ratio=annualized / (max_dd / 100) if max_dd > 0 else 0.0,
            max_drawdown_pct=max_dd,
            max_drawdown_duration_days=float(max_duration / pd.Timedelta(days=1)),
            total_trades=count,
            winning_trades=int(winning.sum()),
            losing_trades=int(losing.sum()),
            win_rate_pct=float(winning.mean() * 100) if count else 0.0,
            profit_factor=profit_factor,
            avg_return_per_trade_pct=float(returns.mean() * 100) if count else 0.0,
            avg_winning_trade_pct=float(returns[winning].mean() * 100) if winning.any() else 0.0,
            avg_losing_trade_pct=float(returns[losing].mean() * 100) if losing.any() else 0.0,
            largest_winner_pct=float(returns[winning].max() * 100) if winning.any() else 0.0,
            largest_loser_pct=float(returns[losing].min() * 100) if losing.any() else 0.0,
            max_consecutive_losses=self._max_consecutive_losses(trades),
            avg_holding_hours=self._avg_holding_hours(trades),
            trades_per_year=trades_per_year,
            trade_returns=returns.tolist(),
            passed_validation=not failures,
            failure_reasons=failures,
        )

    @staticmethod
    def _check_validation(
        sharpe: float, max_dd: float, trades_per_year: float, profit_factor: float, years: float
    ) -> list[str]:
        failures = []
        if any(
            not isfinite(value) for value in (sharpe, max_dd, trades_per_year, years)
        ) or np.isnan(profit_factor):
            failures.append("Non-finite validation metrics")
        if years < STRATEGY_VALIDATION["min_backtest_years"]:
            failures.append(
                f"Insufficient history: {years:.1f}y < {STRATEGY_VALIDATION['min_backtest_years']}y"
            )
        if sharpe < STRATEGY_VALIDATION["min_sharpe_insample"]:
            failures.append(f"Sharpe {sharpe:.2f} < {STRATEGY_VALIDATION['min_sharpe_insample']}")
        if max_dd >= STRATEGY_VALIDATION["max_drawdown_pct"]:
            failures.append(f"Max DD {max_dd:.1f}% > {STRATEGY_VALIDATION['max_drawdown_pct']}%")
        if trades_per_year < STRATEGY_VALIDATION["min_trades_per_year"]:
            failures.append(
                f"Trades/year {trades_per_year:.0f} < {STRATEGY_VALIDATION['min_trades_per_year']}"
            )
        if profit_factor < STRATEGY_VALIDATION["min_profit_factor"]:
            failures.append(
                f"Profit factor {profit_factor:.2f} < {STRATEGY_VALIDATION['min_profit_factor']}"
            )
        return failures

    def walk_forward(
        self,
        ohlcv: pd.DataFrame,
        strategy_fn: Callable[[pd.DataFrame, dict[str, Any]], tuple[pd.Series, pd.Series]],
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

                windows.append(
                    WalkForwardWindow(
                        window_index=i,
                        train_start=train_df.index[0],
                        train_end=train_df.index[-1],
                        test_start=test_df.index[0],
                        test_end=test_df.index[-1],
                        in_sample=is_result,
                        out_of_sample=oos_result,
                    )
                )
            except Exception as e:
                logger.warning("walk-forward window failed", window=i, error=str(e))

        if not windows:
            return WalkForwardResult(
                strategy_id=self.strategy_id,
                windows=[],
                avg_oos_sharpe=0,
                avg_oos_return_pct=0,
                avg_wf_efficiency=0,
                passed_validation=False,
                failure_reasons=["No walk-forward windows completed"],
            )

        avg_oos_sharpe = float(np.mean([w.out_of_sample.sharpe_ratio for w in windows]))
        avg_oos_return = float(np.mean([w.out_of_sample.annualized_return_pct for w in windows]))
        avg_efficiency = float(np.mean([w.wf_efficiency for w in windows]))

        failures = []
        if avg_oos_sharpe < STRATEGY_VALIDATION["min_sharpe_walkforward"]:
            failures.append(
                f"OOS Sharpe {avg_oos_sharpe:.2f} < {STRATEGY_VALIDATION['min_sharpe_walkforward']}"
            )
        if avg_efficiency < STRATEGY_VALIDATION["wf_efficiency"]:
            failures.append(
                f"WF efficiency {avg_efficiency:.2f} < {STRATEGY_VALIDATION['wf_efficiency']}"
            )

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
        if (
            isinstance(n_simulations, bool)
            or not isinstance(n_simulations, int)
            or not 1 <= n_simulations <= 100_000
        ):
            raise ValueError("n_simulations must be an integer between 1 and 100000")
        observed = backtest_result.trade_returns
        years = (backtest_result.end_date - backtest_result.start_date).total_seconds() / (
            365.25 * 86400
        )
        reason = None
        if backtest_result.total_trades <= 0:
            reason = "No trades available for Monte Carlo validation"
        elif observed is None or len(observed) != backtest_result.total_trades:
            reason = "Complete recorded trade returns are required for Monte Carlo validation"
        elif not np.isfinite(observed).all() or any(value < -1 for value in observed):
            reason = "Recorded trade returns must be finite fractions greater than or equal to -1"
        elif not isfinite(years) or years <= 0:
            reason = "A positive elapsed backtest history is required for Monte Carlo validation"
        if reason:
            return MonteCarloResult(
                strategy_id=self.strategy_id,
                simulations=0,
                var_95=1.0,
                var_99=1.0,
                cvar_95=1.0,
                ruin_probability=1.0,
                median_return_pct=0,
                percentile_5_return_pct=0,
                percentile_95_return_pct=0,
                passed_validation=False,
                failure_reasons=[reason],
            )
        assert observed is not None
        n_trades = ceil(
            len(observed) / years * 3
        )  # three calendar years at the observed trade rate
        if n_trades * n_simulations > 100_000_000:
            raise ValueError("Monte Carlo sample budget exceeded; reduce n_simulations")
        rng = np.random.default_rng(seed=42)
        capital = np.ones(n_simulations)
        ruined = np.zeros(n_simulations, dtype=bool)
        for _ in range(n_trades):
            active = ~ruined
            if not active.any():
                break
            capital[active] *= 1 + rng.choice(observed, size=int(active.sum()), replace=True)
            ruined |= capital <= 0.5  # pathwise, inclusive 50% loss; stop on ruin
        returns_arr = capital - 1
        if not np.isfinite(returns_arr).all():
            raise ValueError("Monte Carlo compounding produced non-finite returns")
        ruin_prob = float(ruined.mean())
        fifth, first = np.percentile(returns_arr, [5, 1])
        var_95, var_99 = max(0.0, float(-fifth)), max(0.0, float(-first))
        cvar_95 = max(0.0, float(-returns_arr[returns_arr <= fifth].mean()))

        failures = []
        if ruin_prob >= STRATEGY_VALIDATION["mc_max_ruin_probability"]:
            failures.append(f"Ruin probability {ruin_prob:.2%} > 1% limit")
        if var_95 >= STRATEGY_VALIDATION["mc_var_95"]:
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
            failure_reasons=failures,
        )

    @staticmethod
    def loss_streaks(
        backtest_result: BacktestResult, *, configuration: LossStreakConfig
    ) -> LossStreakStudy:
        """Recorded outcome probe; never part of the existing go-live qualification."""
        return loss_streak_analysis(backtest_result, configuration=configuration)

    @staticmethod
    def _max_consecutive_losses(trades_df: pd.DataFrame) -> int:
        if len(trades_df) == 0:
            return 0
        is_loss = (
            (trades_df["PnL"] <= 0).astype(int) if "PnL" in trades_df.columns else pd.Series([0])
        )
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
            return 0.0
        try:
            return float(trades_df["Duration"].mean().total_seconds() / 3600)
        except (AttributeError, TypeError, ValueError):
            raise ValueError("Closed trades require valid holding durations") from None

    def validate_all(
        self, backtest: BacktestResult, wf: WalkForwardResult, mc: MonteCarloResult
    ) -> tuple[bool, list[str]]:
        """Final go/no-go decision — ALL three tests must pass."""
        all_failures = backtest.failure_reasons + wf.failure_reasons + mc.failure_reasons
        for stage, result in (("Backtest", backtest), ("Walk-forward", wf), ("Monte Carlo", mc)):
            if not result.passed_validation and not result.failure_reasons:
                all_failures.append(f"{stage} did not pass validation")
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
