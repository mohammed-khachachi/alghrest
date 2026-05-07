"""
ALGHREST — Risk Engine
Computes VaR, CVaR, drawdown, Sharpe, and portfolio-level risk aggregates.
Called by the CRO agent (Agent 02) every 60 seconds.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import numpy as np
import structlog

from core.data.models import (
    Portfolio,
    RiskLimits,
    RiskMetrics,
    RISK_LIMITS,
)

logger = structlog.get_logger(__name__)


class RiskEngine:
    """
    Stateless risk calculator. All methods are pure functions that take
    portfolio/return data and return risk metrics.
    """

    def __init__(self, limits: RiskLimits = RISK_LIMITS) -> None:
        self.limits = limits
        self._peak_capital: Optional[Decimal] = None
        self._daily_open_capital: Optional[Decimal] = None
        self._weekly_open_capital: Optional[Decimal] = None
        self._monthly_open_capital: Optional[Decimal] = None

    # ── VALUE AT RISK ─────────────────────────────────────────────────────────

    @staticmethod
    def historical_var(returns: np.ndarray, confidence: float = 0.95) -> float:
        """
        Historical simulation VaR.
        Returns loss as a positive percentage (0.05 = 5% potential loss).
        """
        if len(returns) < 30:
            return 0.0
        return float(-np.percentile(returns, (1 - confidence) * 100))

    @staticmethod
    def historical_cvar(returns: np.ndarray, confidence: float = 0.95) -> float:
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

    def update_high_watermark(self, current_capital: Decimal) -> None:
        if self._peak_capital is None or current_capital > self._peak_capital:
            self._peak_capital = current_capital

    def set_period_open(self, capital: Decimal) -> None:
        """Call at the start of each day/week/month."""
        now = datetime.utcnow()
        if self._daily_open_capital is None:
            self._daily_open_capital = capital
        if self._weekly_open_capital is None:
            self._weekly_open_capital = capital
        if self._monthly_open_capital is None:
            self._monthly_open_capital = capital

    # ── SHARPE / SORTINO ──────────────────────────────────────────────────────

    @staticmethod
    def sharpe_ratio(returns: np.ndarray, risk_free_daily: float = 0.0) -> float:
        """
        Annualized Sharpe ratio from daily returns.
        Returns 0.0 if insufficient data or zero volatility.
        """
        if len(returns) < 20:
            return 0.0
        excess = returns - risk_free_daily
        std = excess.std()
        if std == 0:
            return 0.0
        return float(excess.mean() / std * math.sqrt(252))

    @staticmethod
    def sortino_ratio(returns: np.ndarray, risk_free_daily: float = 0.0) -> float:
        """Annualized Sortino ratio — penalizes only downside volatility."""
        if len(returns) < 20:
            return 0.0
        excess = returns - risk_free_daily
        downside = returns[returns < 0]
        if len(downside) == 0:
            return float("inf")
        downside_std = downside.std()
        if downside_std == 0:
            return 0.0
        return float(excess.mean() / downside_std * math.sqrt(252))

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
        return {
            p.symbol: float(p.size * p.current_price / portfolio.total_capital)
            for p in portfolio.positions
        }

    # ── EFFECTIVE N (DIVERSIFICATION) ─────────────────────────────────────────

    @staticmethod
    def effective_n(correlation_matrix: np.ndarray) -> float:
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
        daily_returns: np.ndarray,
        correlation_matrix: Optional[np.ndarray] = None,
    ) -> RiskMetrics:
        """
        Compute the full RiskMetrics snapshot.
        Called by CRO agent every 60 seconds.
        """
        self.update_high_watermark(portfolio.total_capital)
        self.set_period_open(portfolio.total_capital)

        daily_dd = self.compute_drawdown(
            portfolio.total_capital, self._daily_open_capital or portfolio.total_capital
        )
        weekly_dd = self.compute_drawdown(
            portfolio.total_capital, self._weekly_open_capital or portfolio.total_capital
        )
        monthly_dd = self.compute_drawdown(
            portfolio.total_capital, self._monthly_open_capital or portfolio.total_capital
        )
        max_dd = self.compute_drawdown(
            portfolio.total_capital, self._peak_capital or portfolio.total_capital
        )

        total_cap = float(portfolio.total_capital)
        var_95 = self.historical_var(daily_returns, 0.95) if len(daily_returns) >= 30 else 0.0
        cvar_95 = self.historical_cvar(daily_returns, 0.95) if len(daily_returns) >= 30 else 0.0
        var_99 = self.historical_var(daily_returns, 0.99) if len(daily_returns) >= 30 else 0.0

        eff_n = self.effective_n(correlation_matrix) if correlation_matrix is not None else 0.0

        returns_90d = daily_returns[-90:] if len(daily_returns) >= 90 else daily_returns

        return RiskMetrics(
            timestamp=datetime.utcnow(),
            total_capital=portfolio.total_capital,
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

    # ── DRAWDOWN PERIOD RESETS ────────────────────────────────────────────────

    def reset_daily(self, current_capital: Decimal) -> None:
        self._daily_open_capital = current_capital

    def reset_weekly(self, current_capital: Decimal) -> None:
        self._weekly_open_capital = current_capital

    def reset_monthly(self, current_capital: Decimal) -> None:
        self._monthly_open_capital = current_capital
