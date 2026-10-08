"""
ALGHREST — Risk Engine
Computes VaR, CVaR, drawdown, Sharpe, and portfolio-level risk aggregates.
Called by the CRO agent (Agent 02) every 60 seconds.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal

import numpy as np
import structlog
from numpy.typing import NDArray

from core.accounting.performance import require_performance
from core.data.models import RISK_LIMITS, Portfolio, RiskLimits, RiskMetrics

logger = structlog.get_logger(__name__)


class RiskEngine:
    """
    Stateless risk calculator. All methods are pure functions that take
    portfolio/return data and return risk metrics.
    """

    def __init__(self, limits: RiskLimits = RISK_LIMITS) -> None:
        self.limits = limits

    # ── VALUE AT RISK ─────────────────────────────────────────────────────────

    @staticmethod
    def historical_var(returns: NDArray[np.float64], confidence: float = 0.95) -> float:
        """
        Historical simulation VaR.
        Returns loss as a positive percentage (0.05 = 5% potential loss).
        """
        if len(returns) < 30:
            return 0.0
        return float(-np.percentile(returns, (1 - confidence) * 100))

    @staticmethod
    def historical_cvar(returns: NDArray[np.float64], confidence: float = 0.95) -> float:
        """
        Conditional VaR (Expected Shortfall) — average loss beyond the VaR threshold.
        """
        if len(returns) < 30:
            return 0.0
        var_threshold = np.percentile(returns, (1 - confidence) * 100)
        tail_losses = returns[returns <= var_threshold]
        if len(tail_losses) == 0:
            return 0.0
        return float(-tail_losses.mean())

    @staticmethod
    def parametric_var(
        portfolio_value: float,
        daily_vol: float,
        confidence: float = 0.95,
    ) -> float:
        """
        Parametric (Normal) VaR. Used when historical data is insufficient.
        Returns dollar amount at risk.
        """
        z_score = {0.95: 1.645, 0.99: 2.326, 0.999: 3.090}.get(confidence, 1.645)
        return portfolio_value * daily_vol * z_score

    # ── DRAWDOWN ──────────────────────────────────────────────────────────────

    def compute_drawdown(self, current_capital: Decimal, reference_capital: Decimal) -> float:
        """Returns drawdown as a positive decimal (0.05 = 5% loss from peak)."""
        if reference_capital <= 0:
            return 0.0
        drawdown = float((reference_capital - current_capital) / reference_capital)
        return max(0.0, drawdown)

    # ── SHARPE / SORTINO ──────────────────────────────────────────────────────

    @staticmethod
    def sharpe_ratio(returns: NDArray[np.float64], risk_free_daily: float = 0.0) -> float:
        """
        Annualized Sharpe ratio from daily returns.
        Returns 0.0 if insufficient data or zero volatility.
        """
        if len(returns) < 20:
            return 0.0
        excess = returns - risk_free_daily
        std = excess.std(ddof=1)
        if std == 0:
            return 0.0
        return float(excess.mean() / std * math.sqrt(365.25))

    @staticmethod
    def sortino_ratio(returns: NDArray[np.float64], risk_free_daily: float = 0.0) -> float:
        """Annualized Sortino ratio — penalizes only downside volatility."""
        if len(returns) < 20:
            return 0.0
        excess = returns - risk_free_daily
        downside_deviation = float(np.sqrt(np.mean(np.minimum(excess, 0) ** 2)))
        if downside_deviation == 0:
            return 0.0
        return float(excess.mean() / downside_deviation * math.sqrt(365.25))

    @staticmethod
    def calmar_ratio(annualized_return: float, max_drawdown: float) -> float:
        if max_drawdown == 0:
            return 0.0
        return annualized_return / max_drawdown

    # ── POSITION CONCENTRATION ────────────────────────────────────────────────

    @staticmethod
    def compute_concentration(portfolio: Portfolio) -> dict[str, float]:
        """Returns concentration by asset as fraction of total capital."""
        if portfolio.total_capital <= 0:
            return {}
        notional_by_symbol: dict[str, Decimal] = {}
        for position in portfolio.positions:
            notional_by_symbol[position.symbol] = notional_by_symbol.get(
                position.symbol, Decimal("0")
            ) + abs(position.size * position.current_price)
        return {
            symbol: float(notional / portfolio.total_capital)
            for symbol, notional in notional_by_symbol.items()
        }

    # ── EFFECTIVE N (DIVERSIFICATION) ─────────────────────────────────────────

    @staticmethod
    def effective_n(correlation_matrix: NDArray[np.float64]) -> float:
        """
        Computes the effective number of independent bets using the
        eigenvalue entropy method. Low value = concentrated, correlated positions.
        """
        if correlation_matrix.shape[0] == 0:
            return 0.0
        eigenvalues = np.linalg.eigvalsh(correlation_matrix)
        eigenvalues = eigenvalues[eigenvalues > 0]
        if len(eigenvalues) == 0:
            return 0.0
        normalized = eigenvalues / eigenvalues.sum()
        entropy = -np.sum(normalized * np.log(normalized + 1e-10))
        return float(np.exp(entropy))

    # ── FULL METRICS COMPUTATION ──────────────────────────────────────────────

    def compute_metrics(
        self,
        portfolio: Portfolio,
        correlation_matrix: NDArray[np.float64] | None = None,
    ) -> RiskMetrics:
        """
        Compute the full RiskMetrics snapshot.
        Called by CRO agent every 60 seconds.
        """
        performance = require_performance(portfolio)
        daily_dd = performance.drawdown(performance.day.unit_price)
        weekly_dd = performance.drawdown(performance.week.unit_price)
        monthly_dd = performance.drawdown(performance.month.unit_price)
        max_dd = performance.drawdown()
        daily_returns = np.asarray(performance.daily_returns(90), dtype=np.float64)
        total_cap = float(portfolio.total_capital + portfolio.unrealized_pnl)
        var_95 = self.historical_var(daily_returns, 0.95) if len(daily_returns) >= 30 else 0.0
        cvar_95 = self.historical_cvar(daily_returns, 0.95) if len(daily_returns) >= 30 else 0.0
        var_99 = self.historical_var(daily_returns, 0.99) if len(daily_returns) >= 30 else 0.0

        eff_n = self.effective_n(correlation_matrix) if correlation_matrix is not None else 0.0

        returns_90d = daily_returns[-90:] if len(daily_returns) >= 90 else daily_returns

        return RiskMetrics(
            timestamp=datetime.utcnow(),
            total_capital=portfolio.total_capital + portfolio.unrealized_pnl,
            available_capital=portfolio.available_capital,
            unrealized_pnl=portfolio.unrealized_pnl,
            daily_pnl=portfolio.daily_pnl,
            var_95_1d=Decimal(str(round(total_cap * var_95, 2))),
            var_99_1d=Decimal(str(round(total_cap * var_99, 2))),
            cvar_95_1d=Decimal(str(round(total_cap * cvar_95, 2))),
            daily_drawdown_pct=daily_dd,
            weekly_drawdown_pct=weekly_dd,
            monthly_drawdown_pct=monthly_dd,
            max_drawdown_pct=max_dd,
            current_leverage=portfolio.leverage,
            open_positions=portfolio.open_position_count,
            position_concentration=self.compute_concentration(portfolio),
            effective_n=eff_n,
            sharpe_90d=self.sharpe_ratio(returns_90d) if len(returns_90d) >= 20 else None,
            sortino_90d=self.sortino_ratio(returns_90d) if len(returns_90d) >= 20 else None,
        )
