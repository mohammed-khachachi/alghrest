"""
ALGHREST — Backtesting Engine Validation Integration Tests
=========================================================

This test validates the comprehensive backtesting and validation system:
1. Strategy backtesting with historical data
2. Walk-forward analysis validation
3. Monte Carlo simulation testing
4. Risk metrics calculation and validation
5. Performance threshold enforcement
6. Strategy approval/rejection workflow

Test Scenarios:
- Complete backtesting pipeline execution
- Walk-forward analysis with rolling windows
- Monte Carlo simulation validation
- Performance metrics calculation
- Strategy qualification thresholds
- Backtesting data quality validation
"""
from __future__ import annotations

import asyncio
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import structlog

from core.data.models import (
    OHLCVBar,
    Exchange,
    Timeframe,
    SignalDirection,
    TradeProposal,
    OrderSide,
    OrderType,
    BacktestResult,
    PerformanceMetrics,
    RiskMetrics,
    WalkForwardResult,
    MonteCarloResult,
)

logger = structlog.get_logger(__name__)


class MockBacktestEngine:
    """Mock backtesting engine for testing strategy validation."""

    def __init__(self, strategy_name: str):
        self.strategy_name = strategy_name
        self.validation_thresholds = {
            "min_years_data": 5,
            "min_trades_per_year": 50,
            "min_sharpe_ratio_is": 1.0,
            "min_sharpe_ratio_oos": 0.8,
            "max_drawdown": 0.25,
            "min_profit_factor": 1.3,
            "min_walk_forward_efficiency": 0.6,
            "max_monte_carlo_ruin": 0.01,
            "max_monte_carlo_var_95": 0.15,
        }

    def generate_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        timeframe: Timeframe = Timeframe.D1,
    ) -> List[OHLCVBar]:
        """Generate realistic historical OHLCV data for backtesting."""

        bars = []
        current_date = start_date
        base_price = 50000.0  # Starting BTC price

        while current_date <= end_date:
            # Generate price movement with trend and volatility
            days_elapsed = (current_date - start_date).days
            trend_factor = 1 + (days_elapsed * 0.0001)  # Slight upward trend
            volatility = 0.02 * (1 + 0.5 * np.sin(days_elapsed * 0.01))  # Variable volatility

            # Random walk with trend
            price_change = np.random.normal(0.001, volatility)
            current_price = base_price * trend_factor * (1 + price_change)

            # Generate OHLCV
            open_price = base_price if current_date == start_date else bars[-1].close
            high_price = max(open_price, current_price) * (1 + abs(np.random.normal(0, 0.005)))
            low_price = min(open_price, current_price) * (1 - abs(np.random.normal(0, 0.005)))
            close_price = current_price
            volume = abs(np.random.normal(1000000, 200000))

            bar = OHLCVBar(
                time=current_date,
                symbol=symbol,
                exchange=Exchange.BINANCE,
                timeframe=timeframe,
                open=Decimal(str(round(open_price, 2))),
                high=Decimal(str(round(high_price, 2))),
                low=Decimal(str(round(low_price, 2))),
                close=Decimal(str(round(close_price, 2))),
                volume=Decimal(str(round(volume, 2))),
                is_closed=True,
            )

            bars.append(bar)
            base_price = float(close_price)

            # Next day
            current_date += timedelta(days=1)

        return bars

    def simulate_strategy_signals(
        self,
        ohlcv_data: List[OHLCVBar],
        strategy_type: str = "trend_following",
    ) -> List[Dict]:
        """Simulate strategy signals based on OHLCV data."""

        signals = []
        prices = [float(bar.close) for bar in ohlcv_data]

        if strategy_type == "trend_following":
            # Simple moving average crossover
            short_window = 20
            long_window = 50

            for i in range(long_window, len(prices)):
                short_ma = np.mean(prices[i-short_window:i])
                long_ma = np.mean(prices[i-long_window:i])
                prev_short_ma = np.mean(prices[i-short_window-1:i-1])
                prev_long_ma = np.mean(prices[i-long_window-1:i-1])

                # Bullish crossover
                if short_ma > long_ma and prev_short_ma <= prev_long_ma:
                    signals.append({
                        "timestamp": ohlcv_data[i].time,
                        "signal": SignalDirection.BULLISH,
                        "confidence": 0.7 + 0.2 * np.random.random(),
                        "entry_price": float(ohlcv_data[i].close),
                        "bar_index": i,
                    })

                # Bearish crossover
                elif short_ma < long_ma and prev_short_ma >= prev_long_ma:
                    signals.append({
                        "timestamp": ohlcv_data[i].time,
                        "signal": SignalDirection.BEARISH,
                        "confidence": 0.7 + 0.2 * np.random.random(),
                        "entry_price": float(ohlcv_data[i].close),
                        "bar_index": i,
                    })

        return signals

    def simulate_trades(
        self,
        signals: List[Dict],
        ohlcv_data: List[OHLCVBar],
        initial_capital: float = 100000.0,
    ) -> Tuple[List[Dict], PerformanceMetrics]:
        """Simulate trade execution and calculate performance."""

        trades = []
        capital = initial_capital
        position = None
        equity_curve = [initial_capital]

        for signal in signals:
            signal_index = signal["bar_index"]

            if signal["signal"] == SignalDirection.BULLISH and position is None:
                # Enter long position
                entry_price = signal["entry_price"]
                position_size = capital * 0.02 / entry_price  # 2% risk per trade
                position = {
                    "side": "LONG",
                    "entry_price": entry_price,
                    "size": position_size,
                    "entry_time": signal["timestamp"],
                    "entry_index": signal_index,
                }

            elif signal["signal"] == SignalDirection.BEARISH and position is not None:
                # Exit long position
                exit_price = signal["entry_price"]
                exit_time = signal["timestamp"]

                trade_pnl = (exit_price - position["entry_price"]) * position["size"]
                capital += trade_pnl

                trade = {
                    "entry_time": position["entry_time"],
                    "exit_time": exit_time,
                    "entry_price": position["entry_price"],
                    "exit_price": exit_price,
                    "size": position["size"],
                    "pnl": trade_pnl,
                    "return_pct": trade_pnl / (position["entry_price"] * position["size"]),
                    "holding_days": (exit_time - position["entry_time"]).days,
                }

                trades.append(trade)
                position = None

            # Update equity curve
            if position is not None:
                current_price = float(ohlcv_data[min(signal_index, len(ohlcv_data)-1)].close)
                unrealized_pnl = (current_price - position["entry_price"]) * position["size"]
                current_equity = capital + unrealized_pnl
            else:
                current_equity = capital

            equity_curve.append(current_equity)

        # Calculate performance metrics
        if trades:
            total_return = (capital - initial_capital) / initial_capital
            returns = [trade["return_pct"] for trade in trades]
            winning_trades = [r for r in returns if r > 0]
            losing_trades = [r for r in returns if r < 0]

            win_rate = len(winning_trades) / len(trades) if trades else 0
            avg_win = np.mean(winning_trades) if winning_trades else 0
            avg_loss = abs(np.mean(losing_trades)) if losing_trades else 0
            profit_factor = (avg_win * len(winning_trades)) / (avg_loss * len(losing_trades)) if losing_trades else float('inf')

            # Calculate Sharpe ratio
            daily_returns = np.diff(equity_curve) / equity_curve[:-1]
            sharpe_ratio = np.mean(daily_returns) / np.std(daily_returns) * np.sqrt(252) if np.std(daily_returns) > 0 else 0

            # Calculate max drawdown
            cummax = np.maximum.accumulate(equity_curve)
            drawdown = (equity_curve - cummax) / cummax
            max_drawdown = abs(np.min(drawdown))

            performance = PerformanceMetrics(
                total_return=total_return,
                annualized_return=total_return * (365 / len(equity_curve)),
                sharpe_ratio=sharpe_ratio,
                max_drawdown=max_drawdown,
                win_rate=win_rate,
                profit_factor=profit_factor,
                total_trades=len(trades),
                avg_trade_return=np.mean(returns),
                trades_per_year=len(trades) * (365 / len(equity_curve)),
            )
        else:
            performance = PerformanceMetrics(
                total_return=0.0,
                annualized_return=0.0,
                sharpe_ratio=0.0,
                max_drawdown=0.0,
                win_rate=0.0,
                profit_factor=0.0,
                total_trades=0,
                avg_trade_return=0.0,
                trades_per_year=0.0,
            )

        return trades, performance

    def run_backtest(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        strategy_type: str = "trend_following",
        initial_capital: float = 100000.0,
    ) -> BacktestResult:
        """Run complete backtest for a strategy."""

        # Generate historical data
        ohlcv_data = self.generate_historical_data(symbol, start_date, end_date)

        # Generate strategy signals
        signals = self.simulate_strategy_signals(ohlcv_data, strategy_type)

        # Simulate trades
        trades, performance = self.simulate_trades(signals, ohlcv_data, initial_capital)

        result = BacktestResult(
            strategy_name=self.strategy_name,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            final_capital=initial_capital * (1 + performance.total_return),
            performance_metrics=performance,
            trades=trades,
            signals_generated=len(signals),
            data_quality_score=0.95,  # Mock high quality score
        )

        return result

    def run_walk_forward_analysis(
        self,
        backtest_result: BacktestResult,
        num_windows: int = 8,
    ) -> WalkForwardResult:
        """Run walk-forward analysis on backtest results."""

        window_size = (backtest_result.end_date - backtest_result.start_date).days // num_windows
        window_results = []

        for i in range(num_windows):
            window_start = backtest_result.start_date + timedelta(days=i * window_size)
            window_end = window_start + timedelta(days=window_size)

            # Simulate window performance (in reality, would re-run strategy)
            base_performance = backtest_result.performance_metrics
            noise_factor = 1 + np.random.normal(0, 0.1)  # Add realistic variation

            window_performance = PerformanceMetrics(
                total_return=base_performance.total_return * noise_factor * 0.8,  # OOS degradation
                annualized_return=base_performance.annualized_return * noise_factor * 0.8,
                sharpe_ratio=base_performance.sharpe_ratio * noise_factor * 0.85,
                max_drawdown=base_performance.max_drawdown * (1 + abs(np.random.normal(0, 0.2))),
                win_rate=max(0.3, min(0.9, base_performance.win_rate + np.random.normal(0, 0.05))),
                profit_factor=max(0.8, base_performance.profit_factor * noise_factor * 0.9),
                total_trades=int(base_performance.total_trades * window_size / 365),
                avg_trade_return=base_performance.avg_trade_return * noise_factor,
                trades_per_year=base_performance.trades_per_year,
            )

            window_results.append({
                "window_id": i + 1,
                "start_date": window_start,
                "end_date": window_end,
                "performance": window_performance,
            })

        # Calculate walk-forward efficiency
        is_performance = backtest_result.performance_metrics
        avg_oos_performance = np.mean([w["performance"].total_return for w in window_results])
        wf_efficiency = avg_oos_performance / is_performance.total_return if is_performance.total_return > 0 else 0

        result = WalkForwardResult(
            strategy_name=self.strategy_name,
            num_windows=num_windows,
            window_results=window_results,
            in_sample_performance=is_performance,
            out_of_sample_performance=avg_oos_performance,
            walk_forward_efficiency=wf_efficiency,
        )

        return result

    def run_monte_carlo_simulation(
        self,
        trades: List[Dict],
        num_simulations: int = 10000,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation on trade results."""

        if not trades:
            return MonteCarloResult(
                num_simulations=num_simulations,
                final_capitals=[100000.0] * num_simulations,
                ruin_probability=0.0,
                percentile_95_var=0.0,
                confidence_intervals={},
            )

        trade_returns = [trade["return_pct"] for trade in trades]
        initial_capital = 100000.0
        simulation_results = []

        for _ in range(num_simulations):
            capital = initial_capital

            # Randomly resample trades with replacement
            simulated_trades = np.random.choice(len(trade_returns), size=len(trades), replace=True)

            for trade_idx in simulated_trades:
                trade_return = trade_returns[trade_idx]
                capital *= (1 + trade_return)

                # Check for ruin (capital below 50% of initial)
                if capital < initial_capital * 0.5:
                    break

            simulation_results.append(capital)

        # Calculate statistics
        ruin_count = sum(1 for c in simulation_results if c < initial_capital * 0.5)
        ruin_probability = ruin_count / num_simulations

        # Calculate 95% VaR
        sorted_results = sorted(simulation_results)
        var_95_index = int(num_simulations * 0.05)
        var_95_capital = sorted_results[var_95_index]
        var_95_percent = (initial_capital - var_95_capital) / initial_capital

        # Confidence intervals
        confidence_intervals = {
            "5%": np.percentile(simulation_results, 5),
            "25%": np.percentile(simulation_results, 25),
            "50%": np.percentile(simulation_results, 50),
            "75%": np.percentile(simulation_results, 75),
            "95%": np.percentile(simulation_results, 95),
        }

        result = MonteCarloResult(
            num_simulations=num_simulations,
            final_capitals=simulation_results,
            ruin_probability=ruin_probability,
            percentile_95_var=var_95_percent,
            confidence_intervals=confidence_intervals,
        )

        return result

    def validate_strategy(
        self,
        backtest_result: BacktestResult,
        walk_forward_result: WalkForwardResult,
        monte_carlo_result: MonteCarloResult,
    ) -> Tuple[bool, List[str]]:
        """Validate strategy against all thresholds."""

        validation_results = []
        failures = []

        # Data quality checks
        years_of_data = (backtest_result.end_date - backtest_result.start_date).days / 365.25
        if years_of_data < self.validation_thresholds["min_years_data"]:
            failures.append(f"Insufficient data: {years_of_data:.1f} years < {self.validation_thresholds['min_years_data']} required")

        # Trade frequency
        if backtest_result.performance_metrics.trades_per_year < self.validation_thresholds["min_trades_per_year"]:
            failures.append(f"Low trade frequency: {backtest_result.performance_metrics.trades_per_year:.0f} < {self.validation_thresholds['min_trades_per_year']} required")

        # In-sample performance
        if backtest_result.performance_metrics.sharpe_ratio < self.validation_thresholds["min_sharpe_ratio_is"]:
            failures.append(f"Low in-sample Sharpe: {backtest_result.performance_metrics.sharpe_ratio:.2f} < {self.validation_thresholds['min_sharpe_ratio_is']} required")

        # Out-of-sample performance
        avg_oos_sharpe = np.mean([w["performance"].sharpe_ratio for w in walk_forward_result.window_results])
        if avg_oos_sharpe < self.validation_thresholds["min_sharpe_ratio_oos"]:
            failures.append(f"Low out-of-sample Sharpe: {avg_oos_sharpe:.2f} < {self.validation_thresholds['min_sharpe_ratio_oos']} required")

        # Drawdown
        if backtest_result.performance_metrics.max_drawdown > self.validation_thresholds["max_drawdown"]:
            failures.append(f"High drawdown: {backtest_result.performance_metrics.max_drawdown:.2%} > {self.validation_thresholds['max_drawdown']:.0%} allowed")

        # Profit factor
        if backtest_result.performance_metrics.profit_factor < self.validation_thresholds["min_profit_factor"]:
            failures.append(f"Low profit factor: {backtest_result.performance_metrics.profit_factor:.2f} < {self.validation_thresholds['min_profit_factor']} required")

        # Walk-forward efficiency
        if walk_forward_result.walk_forward_efficiency < self.validation_thresholds["min_walk_forward_efficiency"]:
            failures.append(f"Low WF efficiency: {walk_forward_result.walk_forward_efficiency:.1%} < {self.validation_thresholds['min_walk_forward_efficiency']:.0%} required")

        # Monte Carlo risk
        if monte_carlo_result.ruin_probability > self.validation_thresholds["max_monte_carlo_ruin"]:
            failures.append(f"High ruin probability: {monte_carlo_result.ruin_probability:.1%} > {self.validation_thresholds['max_monte_carlo_ruin']:.1%} allowed")

        if monte_carlo_result.percentile_95_var > self.validation_thresholds["max_monte_carlo_var_95"]:
            failures.append(f"High 95% VaR: {monte_carlo_result.percentile_95_var:.1%} > {self.validation_thresholds['max_monte_carlo_var_95']:.0%} allowed")

        passed = len(failures) == 0

        return passed, failures


@pytest.fixture
def backtest_engine():
    """Create backtest engine for testing."""
    return MockBacktestEngine("test_strategy")


@pytest.fixture
def historical_data_config():
    """Configuration for historical data generation."""
    return {
        "symbol": "BTC/USDT",
        "start_date": datetime(2019, 1, 1),
        "end_date": datetime(2024, 1, 1),
        "initial_capital": 100000.0,
    }


@pytest.mark.integration
class TestBacktestingValidation:
    """Integration tests for backtesting and validation system."""

    async def test_complete_backtesting_pipeline(self, backtest_engine, historical_data_config):
        """Test complete backtesting pipeline from data to validation."""

        # Step 1: Run backtest
        backtest_result = backtest_engine.run_backtest(
            symbol=historical_data_config["symbol"],
            start_date=historical_data_config["start_date"],
            end_date=historical_data_config["end_date"],
            initial_capital=historical_data_config["initial_capital"],
        )

        # Verify backtest results
        assert backtest_result.strategy_name == "test_strategy"
        assert backtest_result.symbol == "BTC/USDT"
        assert backtest_result.performance_metrics is not None
        assert backtest_result.trades is not None
        assert backtest_result.signals_generated > 0

        # Step 2: Run walk-forward analysis
        walk_forward_result = backtest_engine.run_walk_forward_analysis(
            backtest_result,
            num_windows=8,
        )

        # Verify walk-forward results
        assert walk_forward_result.num_windows == 8
        assert len(walk_forward_result.window_results) == 8
        assert 0.0 <= walk_forward_result.walk_forward_efficiency <= 2.0

        # Step 3: Run Monte Carlo simulation
        monte_carlo_result = backtest_engine.run_monte_carlo_simulation(
            backtest_result.trades,
            num_simulations=1000,  # Reduced for testing speed
        )

        # Verify Monte Carlo results
        assert monte_carlo_result.num_simulations == 1000
        assert len(monte_carlo_result.final_capitals) == 1000
        assert 0.0 <= monte_carlo_result.ruin_probability <= 1.0
        assert monte_carlo_result.percentile_95_var >= 0.0

        # Step 4: Validate strategy
        passed, failures = backtest_engine.validate_strategy(
            backtest_result,
            walk_forward_result,
            monte_carlo_result,
        )

        # Verify validation process
        assert isinstance(passed, bool)
        assert isinstance(failures, list)

        logger.info(
            "Backtesting pipeline completed",
            passed=passed,
            failures=failures,
            sharpe_ratio=backtest_result.performance_metrics.sharpe_ratio,
            max_drawdown=backtest_result.performance_metrics.max_drawdown,
            wf_efficiency=walk_forward_result.walk_forward_efficiency,
            ruin_probability=monte_carlo_result.ruin_probability,
        )

    async def test_strategy_qualification_thresholds(self, backtest_engine):
        """Test strategy qualification against performance thresholds."""

        # Test failing strategy (low performance)
        weak_strategy_data = {
            "symbol": "BTC/USDT",
            "start_date": datetime(2022, 1, 1),  # Only 2 years of data
            "end_date": datetime(2024, 1, 1),
            "initial_capital": 100000.0,
        }

        # Modify backtest engine to produce weak results
        with patch.object(backtest_engine, 'simulate_trades') as mock_trades:
            # Mock poor performance
            weak_trades = [
                {"return_pct": -0.02, "pnl": -200},
                {"return_pct": 0.01, "pnl": 100},
                {"return_pct": -0.03, "pnl": -300},
            ]

            weak_performance = PerformanceMetrics(
                total_return=-0.05,
                annualized_return=-0.025,
                sharpe_ratio=0.3,  # Below threshold
                max_drawdown=0.35,  # Above threshold
                win_rate=0.33,
                profit_factor=0.8,  # Below threshold
                total_trades=3,
                avg_trade_return=-0.013,
                trades_per_year=30,  # Below threshold
            )

            mock_trades.return_value = (weak_trades, weak_performance)

            backtest_result = backtest_engine.run_backtest(**weak_strategy_data)
            walk_forward_result = backtest_engine.run_walk_forward_analysis(backtest_result)
            monte_carlo_result = backtest_engine.run_monte_carlo_simulation(weak_trades)

            passed, failures = backtest_engine.validate_strategy(
                backtest_result,
                walk_forward_result,
                monte_carlo_result,
            )

            # Should fail validation
            assert passed is False
            assert len(failures) > 0
            assert any("data" in failure.lower() for failure in failures)
            assert any("sharpe" in failure.lower() for failure in failures)
            assert any("drawdown" in failure.lower() for failure in failures)

    async def test_walk_forward_analysis_degradation(self, backtest_engine, historical_data_config):
        """Test walk-forward analysis detects overfitting."""

        backtest_result = backtest_engine.run_backtest(**historical_data_config)

        # Test with severe out-of-sample degradation
        with patch.object(backtest_engine, 'run_walk_forward_analysis') as mock_wf:
            # Mock severe degradation
            degraded_windows = []
            for i in range(8):
                degraded_performance = PerformanceMetrics(
                    total_return=0.02,  # Much lower than in-sample
                    annualized_return=0.01,
                    sharpe_ratio=0.2,  # Severe degradation
                    max_drawdown=0.15,
                    win_rate=0.45,
                    profit_factor=1.1,
                    total_trades=25,
                    avg_trade_return=0.001,
                    trades_per_year=50,
                )

                degraded_windows.append({
                    "window_id": i + 1,
                    "start_date": datetime(2019, 1, 1) + timedelta(days=i * 180),
                    "end_date": datetime(2019, 1, 1) + timedelta(days=(i + 1) * 180),
                    "performance": degraded_performance,
                })

            degraded_wf_result = WalkForwardResult(
                strategy_name="test_strategy",
                num_windows=8,
                window_results=degraded_windows,
                in_sample_performance=backtest_result.performance_metrics,
                out_of_sample_performance=0.02,
                walk_forward_efficiency=0.15,  # Very low efficiency
            )

            mock_wf.return_value = degraded_wf_result

            wf_result = backtest_engine.run_walk_forward_analysis(backtest_result)
            monte_carlo_result = backtest_engine.run_monte_carlo_simulation(backtest_result.trades)

            passed, failures = backtest_engine.validate_strategy(
                backtest_result,
                wf_result,
                monte_carlo_result,
            )

            # Should detect overfitting
            assert passed is False
            assert any("wf efficiency" in failure.lower() or "efficiency" in failure.lower() for failure in failures)

    async def test_monte_carlo_risk_assessment(self, backtest_engine):
        """Test Monte Carlo simulation risk assessment."""

        # Create high-risk trade sequence
        risky_trades = []
        for i in range(50):
            # Alternate between big wins and big losses (high volatility)
            if i % 2 == 0:
                risky_trades.append({"return_pct": 0.15, "pnl": 1500})  # Big win
            else:
                risky_trades.append({"return_pct": -0.12, "pnl": -1200})  # Big loss

        # Run Monte Carlo simulation
        monte_carlo_result = backtest_engine.run_monte_carlo_simulation(
            risky_trades,
            num_simulations=1000,
        )

        # High-volatility strategy should show elevated risk
        assert monte_carlo_result.ruin_probability > 0.005  # Higher than low-risk strategies
        assert monte_carlo_result.percentile_95_var > 0.10   # Significant downside risk

        # Test with conservative strategy
        conservative_trades = []
        for i in range(100):
            # Small consistent wins with occasional small losses
            if i % 10 == 0:
                conservative_trades.append({"return_pct": -0.02, "pnl": -200})  # Small loss
            else:
                conservative_trades.append({"return_pct": 0.005, "pnl": 50})   # Small win

        conservative_mc_result = backtest_engine.run_monte_carlo_simulation(
            conservative_trades,
            num_simulations=1000,
        )

        # Conservative strategy should show lower risk
        assert conservative_mc_result.ruin_probability < monte_carlo_result.ruin_probability
        assert conservative_mc_result.percentile_95_var < monte_carlo_result.percentile_95_var

    async def test_data_quality_validation(self, backtest_engine):
        """Test data quality validation for backtesting."""

        # Test with insufficient data
        short_data_config = {
            "symbol": "BTC/USDT",
            "start_date": datetime(2023, 1, 1),
            "end_date": datetime(2024, 1, 1),  # Only 1 year
            "initial_capital": 100000.0,
        }

        backtest_result = backtest_engine.run_backtest(**short_data_config)
        walk_forward_result = backtest_engine.run_walk_forward_analysis(backtest_result)
        monte_carlo_result = backtest_engine.run_monte_carlo_simulation(backtest_result.trades)

        passed, failures = backtest_engine.validate_strategy(
            backtest_result,
            walk_forward_result,
            monte_carlo_result,
        )

        # Should fail due to insufficient data
        assert passed is False
        assert any("insufficient data" in failure.lower() or "years" in failure.lower() for failure in failures)

        # Test data quality score
        assert hasattr(backtest_result, 'data_quality_score')
        assert 0.0 <= backtest_result.data_quality_score <= 1.0

    async def test_performance_metrics_calculation(self, backtest_engine, historical_data_config):
        """Test accuracy of performance metrics calculation."""

        backtest_result = backtest_engine.run_backtest(**historical_data_config)
        performance = backtest_result.performance_metrics

        # Verify metric bounds and relationships
        assert isinstance(performance.total_return, float)
        assert isinstance(performance.sharpe_ratio, float)
        assert 0.0 <= performance.max_drawdown <= 1.0
        assert 0.0 <= performance.win_rate <= 1.0
        assert performance.profit_factor >= 0.0
        assert performance.total_trades >= 0

        # Verify trades per year calculation
        years_of_data = (backtest_result.end_date - backtest_result.start_date).days / 365.25
        expected_trades_per_year = performance.total_trades / years_of_data
        assert abs(performance.trades_per_year - expected_trades_per_year) < 1.0

        # Verify return calculations
        if backtest_result.trades:
            total_pnl = sum(trade["pnl"] for trade in backtest_result.trades)
            expected_return = total_pnl / historical_data_config["initial_capital"]
            assert abs(performance.total_return - expected_return) < 0.01

    async def test_strategy_approval_workflow(self, backtest_engine, historical_data_config):
        """Test complete strategy approval workflow."""

        # Run full validation process
        backtest_result = backtest_engine.run_backtest(**historical_data_config)
        walk_forward_result = backtest_engine.run_walk_forward_analysis(backtest_result)
        monte_carlo_result = backtest_engine.run_monte_carlo_simulation(backtest_result.trades)

        passed, failures = backtest_engine.validate_strategy(
            backtest_result,
            walk_forward_result,
            monte_carlo_result,
        )

        # Create approval decision record
        approval_record = {
            "strategy_name": backtest_result.strategy_name,
            "validation_date": datetime.utcnow(),
            "passed_validation": passed,
            "failure_reasons": failures,
            "performance_summary": {
                "sharpe_ratio": backtest_result.performance_metrics.sharpe_ratio,
                "max_drawdown": backtest_result.performance_metrics.max_drawdown,
                "profit_factor": backtest_result.performance_metrics.profit_factor,
                "walk_forward_efficiency": walk_forward_result.walk_forward_efficiency,
                "monte_carlo_ruin": monte_carlo_result.ruin_probability,
            },
            "recommended_action": "APPROVED" if passed else "REJECTED",
            "risk_rating": "LOW" if passed and monte_carlo_result.ruin_probability < 0.005 else "MEDIUM",
        }

        # Verify approval record structure
        assert "strategy_name" in approval_record
        assert "validation_date" in approval_record
        assert "passed_validation" in approval_record
        assert "performance_summary" in approval_record
        assert approval_record["recommended_action"] in ["APPROVED", "REJECTED"]

        logger.info(
            "Strategy approval workflow completed",
            strategy_name=approval_record["strategy_name"],
            passed=approval_record["passed_validation"],
            action=approval_record["recommended_action"],
            risk_rating=approval_record["risk_rating"],
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])