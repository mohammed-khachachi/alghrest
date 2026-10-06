"""Agent 30: publish metrics from the accountant's durable unitized index."""

from __future__ import annotations

import asyncio
from typing import Any

import numpy as np

from agents.base_agent import BaseAgent
from core.accounting.performance import require_performance
from core.data.models import AgentConfig, KafkaTopic, Portfolio

_SNAPSHOT_INTERVAL = 30
_RETURNS_WINDOW_DAYS = 90
_MIN_DAYS_FOR_SHARPE = 20
_TRADING_DAYS_PER_YEAR = 365.25


class PortfolioTracker(BaseAgent):
    AGENT_ID = 30

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=7, name="PortfolioTracker", config=config)

    async def initialize(self) -> None:
        # PostgreSQL/accountant owns all history. Never import legacy raw-NAV
        # Redis peaks, which cannot distinguish deposits from trading returns.
        self.logger.info("portfolio_tracker.initialized")

    async def shutdown(self) -> None:
        pass

    async def run(self) -> None:
        while True:
            await asyncio.sleep(_SNAPSHOT_INTERVAL)
            try:
                # Monitoring must continue while strategies are halted.
                await self._snapshot()
            except Exception as exc:
                self.logger.warning("portfolio_tracker.unavailable", error=str(exc))

    async def _snapshot(self) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return
        metrics = self._compute_metrics(portfolio)
        await self.state.set_json(
            f"portfolio_tracker:{portfolio.accounting_book_id}:latest", metrics, ttl=60
        )
        await self.publish(
            KafkaTopic.PORTFOLIO_STATE, payload=metrics, message_type="PortfolioSnapshot"
        )

    def _compute_metrics(self, portfolio: Portfolio) -> dict[str, Any]:
        performance = require_performance(portfolio)
        daily_returns = performance.daily_returns(_RETURNS_WINDOW_DAYS)
        sharpe: float | None = None
        sortino: float | None = None
        if len(daily_returns) >= _MIN_DAYS_FOR_SHARPE:
            rets = np.asarray(daily_returns, dtype=float)
            mean_ret = float(rets.mean())
            std_ret = float(rets.std(ddof=1))
            if std_ret > 0:
                sharpe = float(mean_ret / std_ret * np.sqrt(_TRADING_DAYS_PER_YEAR))
            downside_deviation = float(np.sqrt(np.mean(np.minimum(rets, 0) ** 2)))
            if downside_deviation > 0:
                sortino = float(mean_ret / downside_deviation * np.sqrt(_TRADING_DAYS_PER_YEAR))
        return {
            "book_id": performance.book_id,
            "revision": performance.revision,
            "nav": float(portfolio.total_capital + portfolio.unrealized_pnl),
            "unit_price": str(performance.unit_price),
            "peak_unit_price": str(performance.peak),
            "drawdown_pct": round(performance.drawdown() * 100, 3),
            "daily_pnl": float(portfolio.daily_pnl),
            "weekly_pnl": float(portfolio.weekly_pnl),
            "unrealized_pnl": float(portfolio.unrealized_pnl),
            "open_positions": portfolio.open_position_count,
            "leverage": round(portfolio.leverage, 3),
            "sharpe_90d": round(sharpe, 3) if sharpe is not None else None,
            "sortino_90d": round(sortino, 3) if sortino is not None else None,
            "daily_returns_observed": len(daily_returns),
            "min_days_required": _MIN_DAYS_FOR_SHARPE,
            "timestamp": performance.observed_at.isoformat(),
        }
