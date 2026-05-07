"""
ALGHREST — PnL History Writer
Reads the current portfolio snapshot from Redis every SNAPSHOT_INTERVAL
seconds and appends a compact {ts, pnl_usd, pnl_pct} point to the
rolling Redis list used by the dashboard PnL chart.

Redis key: alghrest:portfolio:pnl_history
List cap:  MAX_POINTS entries (oldest entries trimmed from the right)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import orjson
import structlog

from core.orchestrator.state_manager import state_manager

logger = structlog.get_logger(__name__)

SNAPSHOT_INTERVAL = 300        # 5 minutes between snapshots
MAX_POINTS = 288               # 24 h at 5-min resolution
PNL_HISTORY_KEY = "alghrest:portfolio:pnl_history"


class PnlHistoryWriter:
    """
    Appends rolling PnL snapshots to a Redis list.
    The list is read by DashboardWebSocketManager._build_portfolio_snapshot()
    and sent to the dashboard's PnL chart.
    """

    def __init__(self) -> None:
        self._log = logger.bind(component="pnl_history_writer")

    async def _snapshot_once(self) -> None:
        portfolio = await state_manager.get_portfolio()
        if portfolio is None:
            self._log.debug("portfolio not yet available, skipping snapshot")
            return

        daily_pnl_usd = float(portfolio.daily_pnl)
        capital = float(portfolio.total_capital)
        daily_pnl_pct = round(daily_pnl_usd / capital * 100, 4) if capital else 0.0

        point = orjson.dumps({
            "ts":      datetime.now(timezone.utc).isoformat(),
            "pnl_usd": round(daily_pnl_usd, 2),
            "pnl_pct": daily_pnl_pct,
        })

        pipe = state_manager.redis.pipeline()
        # Prepend so index 0 = most recent (matches lrange 0..N in _build_portfolio_snapshot)
        pipe.lpush(PNL_HISTORY_KEY, point)
        # Trim to keep only the most recent MAX_POINTS entries
        pipe.ltrim(PNL_HISTORY_KEY, 0, MAX_POINTS - 1)
        await pipe.execute()

        self._log.debug(
            "pnl snapshot written",
            pnl_usd=round(daily_pnl_usd, 2),
            pnl_pct=daily_pnl_pct,
        )

    async def run(self) -> None:
        """Infinite loop — run as asyncio.create_task()."""
        self._log.info("pnl history writer started", interval_s=SNAPSHOT_INTERVAL)
        # Take an immediate snapshot on startup so the chart isn't empty
        try:
            await self._snapshot_once()
        except Exception as exc:
            self._log.warning("initial pnl snapshot failed", error=str(exc))

        while True:
            await asyncio.sleep(SNAPSHOT_INTERVAL)
            try:
                await self._snapshot_once()
            except Exception as exc:
                self._log.warning("pnl snapshot error", error=str(exc))


# Module-level singleton
pnl_history_writer = PnlHistoryWriter()
