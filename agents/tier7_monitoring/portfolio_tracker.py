"""
Agent 30 — Portfolio Tracker

Real-time NAV / drawdown / risk-adjusted-return tracking. Publishes a portfolio
snapshot every 30 s and maintains a rolling 90-day Sharpe / Sortino over
TRUE end-of-day returns.

Why this rewrite (I10):
  The previous implementation computed "Sharpe" by sampling NAV every 30 s,
  taking deltas at index [-30] (so 15-minute returns), then annualizing with
  sqrt(252). Two bugs in one:
    1. 15-minute returns are not daily returns — annualization needed
       sqrt(252 × 96) instead of sqrt(252).
    2. The Sharpe of 15-minute returns has totally different statistical
       properties than daily — autocorrelation, mean reversion at micro
       scales, and the annualization factor explode the noise.

This module now:
  - Buckets NAV by UTC calendar date in a Redis hash `portfolio_tracker:daily_closes`.
  - Persists every snapshot's NAV under today's date (HSET upserts cheaply).
  - On UTC midnight rollover, finalizes yesterday's "close" (last NAV seen
    on that day) and starts a new day.
  - Computes daily returns r_t = (nav_t - nav_{t-1}) / nav_{t-1} from the
    persisted history.
  - Sharpe (annualised) = mean(r) / std(r) × sqrt(252) over the most recent
    `_RETURNS_WINDOW_DAYS` calendar days, with a minimum sample of
    `_MIN_DAYS_FOR_SHARPE` to avoid noisy estimates.
  - Survives restarts: `_daily_closes` is reloaded from Redis on initialize.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

import numpy as np
import structlog

from agents.base_agent import BaseAgent
from core.data.models import (
    AgentConfig,
    KafkaTopic,
    Portfolio,
)

log = structlog.get_logger(__name__)

_SNAPSHOT_INTERVAL = 30                # seconds between published snapshots
_RETURNS_WINDOW_DAYS = 90              # calendar days of returns for Sharpe
_MIN_DAYS_FOR_SHARPE = 20              # minimum sample to publish a value
_NAV_HISTORY_RETENTION_DAYS = 365      # cap on historical daily closes
_TRADING_DAYS_PER_YEAR = 252           # annualisation factor for daily Sharpe

# Redis keys
_PEAK_KEY = "portfolio_tracker:peak_nav"
_DAILY_CLOSES_KEY = "portfolio_tracker:daily_closes"   # hash: YYYY-MM-DD → NAV
_LATEST_METRICS_KEY = "portfolio_tracker:latest"       # JSON snapshot for API


class PortfolioTracker(BaseAgent):
    """
    Agent 30 — Portfolio Tracker.
    Maintains true daily-close NAV history in Redis and publishes
    risk-adjusted return metrics on PORTFOLIO_STATE every 30 s.
    """

    AGENT_ID = 30

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=7,
            name="PortfolioTracker",
            config=config,
        )
        # YYYY-MM-DD → end-of-day NAV (today's entry is the most recent
        # snapshot and is updated on every cycle until midnight rollover).
        self._daily_closes: dict[str, float] = {}
        self._peak_nav: float = 0.0
        self._current_date: Optional[date] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        # Restore peak NAV
        peak_raw = await self.state.redis.get(_PEAK_KEY)
        if peak_raw:
            try:
                self._peak_nav = float(
                    peak_raw.decode() if isinstance(peak_raw, bytes) else peak_raw
                )
            except (ValueError, AttributeError):
                self._peak_nav = 0.0

        # Restore daily closes from Redis hash
        try:
            closes_raw = await self.state.redis.hgetall(_DAILY_CLOSES_KEY)
            if closes_raw:
                self._daily_closes = self._decode_redis_hash(closes_raw)
        except Exception as exc:
            log.warning("portfolio_tracker.daily_closes_load_failed", error=str(exc))
            self._daily_closes = {}

        log.info(
            "portfolio_tracker.initialized",
            peak_nav=self._peak_nav,
            daily_closes_loaded=len(self._daily_closes),
            oldest=min(self._daily_closes.keys()) if self._daily_closes else None,
            newest=max(self._daily_closes.keys()) if self._daily_closes else None,
        )

    async def run(self) -> None:
        while True:
            await asyncio.sleep(_SNAPSHOT_INTERVAL)
            if await self.is_halted():
                continue
            try:
                await self._snapshot()
            except Exception as exc:
                log.error("portfolio_tracker.snapshot_error", error=str(exc))

    async def shutdown(self) -> None:
        if self._peak_nav > 0:
            try:
                await self.state.redis.set(_PEAK_KEY, str(self._peak_nav))
            except Exception:
                pass
        log.info(
            "portfolio_tracker.shutdown",
            peak_nav=self._peak_nav,
            daily_closes_count=len(self._daily_closes),
        )

    # ── Snapshot ──────────────────────────────────────────────────────────────

    async def _snapshot(self) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        nav = float(portfolio.total_capital + portfolio.unrealized_pnl)
        today = datetime.utcnow().date()
        today_str = today.isoformat()

        # ── Day rollover ──────────────────────────────────────────────────────
        # If we crossed UTC midnight since the last snapshot, the previous
        # day's "running close" becomes its final close. We don't need to
        # re-write it — it was last persisted just before midnight, and
        # nothing replaces it now that today_str ≠ previous date.
        if self._current_date is not None and self._current_date != today:
            log.info(
                "portfolio_tracker.day_rollover",
                previous=self._current_date.isoformat(),
                close_nav=self._daily_closes.get(self._current_date.isoformat()),
                new=today_str,
            )

        self._current_date = today

        # ── Update today's running close (every snapshot upserts) ────────────
        self._daily_closes[today_str] = nav

        # ── Trim retention window ─────────────────────────────────────────────
        if len(self._daily_closes) > _NAV_HISTORY_RETENTION_DAYS:
            ordered = sorted(self._daily_closes.keys())
            stale = ordered[: len(self._daily_closes) - _NAV_HISTORY_RETENTION_DAYS]
            for k in stale:
                self._daily_closes.pop(k, None)
                try:
                    await self.state.redis.hdel(_DAILY_CLOSES_KEY, k)
                except Exception:
                    pass

        # ── Peak NAV ──────────────────────────────────────────────────────────
        if nav > self._peak_nav:
            self._peak_nav = nav
            try:
                await self.state.redis.set(_PEAK_KEY, str(nav))
            except Exception:
                pass

        # ── Persist today's close (cheap HSET upsert) ─────────────────────────
        try:
            await self.state.redis.hset(_DAILY_CLOSES_KEY, today_str, str(nav))
        except Exception as exc:
            log.warning("portfolio_tracker.hset_failed", error=str(exc))

        # ── Compute + publish metrics ─────────────────────────────────────────
        metrics = self._compute_metrics(portfolio, nav)
        await self._persist_metrics(metrics)

    # ── Metrics ───────────────────────────────────────────────────────────────

    def _compute_metrics(self, portfolio: Portfolio, nav: float) -> dict:
        drawdown = 0.0
        if self._peak_nav > 0:
            drawdown = max(0.0, (self._peak_nav - nav) / self._peak_nav)

        daily_returns = self._compute_daily_returns(window=_RETURNS_WINDOW_DAYS)
        sharpe: Optional[float] = None
        sortino: Optional[float] = None

        if len(daily_returns) >= _MIN_DAYS_FOR_SHARPE:
            rets = np.asarray(daily_returns, dtype=float)
            mean_ret = float(rets.mean())
            std_ret = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
            if std_ret > 0:
                sharpe = mean_ret / std_ret * np.sqrt(_TRADING_DAYS_PER_YEAR)
            downside = rets[rets < 0]
            if len(downside) > 0:
                downside_std = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
                if downside_std > 0:
                    sortino = mean_ret / downside_std * np.sqrt(_TRADING_DAYS_PER_YEAR)

        return {
            "nav": round(nav, 2),
            "peak_nav": round(self._peak_nav, 2),
            "drawdown_pct": round(drawdown * 100, 3),
            "daily_pnl": float(portfolio.daily_pnl),
            "weekly_pnl": float(portfolio.weekly_pnl),
            "unrealized_pnl": float(portfolio.unrealized_pnl),
            "open_positions": portfolio.open_position_count,
            "leverage": round(portfolio.leverage, 3),
            "sharpe_90d": round(sharpe, 3) if sharpe is not None else None,
            "sortino_90d": round(sortino, 3) if sortino is not None else None,
            "daily_returns_observed": len(daily_returns),
            "min_days_required": _MIN_DAYS_FOR_SHARPE,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _compute_daily_returns(self, window: int) -> list[float]:
        """
        Compute simple daily returns from `_daily_closes` over the most recent
        `window` calendar days.

          r_t = (nav_t - nav_{t-1}) / nav_{t-1}

        Days for which we have no NAV (system was down) are skipped — the
        next available close pairs against the previous available close, which
        produces a multi-day return. This slightly biases volatility upward in
        the gap, which is the conservative direction for Sharpe.
        """
        if len(self._daily_closes) < 2:
            return []
        # Sort by date string; ISO format sorts identically to chronological.
        sorted_dates = sorted(self._daily_closes.keys())
        # Take the last (window + 1) closes so we yield up to `window` returns.
        sorted_dates = sorted_dates[-(window + 1):]
        navs = [self._daily_closes[d] for d in sorted_dates]
        returns: list[float] = []
        for i in range(1, len(navs)):
            prev = navs[i - 1]
            curr = navs[i]
            if prev > 0:
                returns.append((curr - prev) / prev)
        return returns

    # ── Persistence helpers ────────────────────────────────────────────────────

    async def _persist_metrics(self, metrics: dict) -> None:
        try:
            await self.state.redis.setex(
                _LATEST_METRICS_KEY,
                300,
                json.dumps(metrics),
            )
        except Exception as exc:
            log.debug("portfolio_tracker.metrics_setex_failed", error=str(exc))

        await self.publish(
            KafkaTopic.PORTFOLIO_STATE,
            payload=metrics,
            message_type="PortfolioSnapshot",
        )
        log.debug(
            "portfolio_tracker.snapshot",
            nav=metrics["nav"],
            drawdown=metrics["drawdown_pct"],
            sharpe=metrics["sharpe_90d"],
            days_obs=metrics["daily_returns_observed"],
        )

    @staticmethod
    def _decode_redis_hash(raw: dict) -> dict[str, float]:
        """Convert HGETALL bytes/str dict into {YYYY-MM-DD: float}."""
        out: dict[str, float] = {}
        for k, v in raw.items():
            try:
                key = k.decode() if isinstance(k, bytes) else str(k)
                val = v.decode() if isinstance(v, bytes) else str(v)
                out[key] = float(val)
            except (ValueError, AttributeError):
                continue
        return out
