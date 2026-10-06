"""QuoteProvider abstract base + shared types."""

from __future__ import annotations

import hashlib
import random
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum

# Demo data is anchored to 2025-05-11. Real provider implementations should
# replace this with the current date from their upstream feed.
ANCHOR_DATE: date = date(2025, 5, 11)


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    FOREX = "forex"
    EQUITY = "equity"


@dataclass(frozen=True)
class Quote:
    symbol: str
    asset_class: AssetClass
    price: float  # current / close
    open: float
    high: float
    low: float
    change_24h_pct: float
    bid: float
    ask: float
    volume_24h: float | None
    ts: str  # ISO-8601


@dataclass(frozen=True)
class HistoricalBar:
    date: str  # YYYY-MM-DD
    open: float
    high: float
    low: float
    close: float
    volume: float | None


def _seed_for(symbol: str) -> int:
    """Stable per-symbol seed so historical series don't churn on refresh."""
    return int(hashlib.sha1(symbol.upper().encode()).hexdigest()[:12], 16)


def random_walk_history(
    anchor_close: float,
    days: int,
    seed: int,
    *,
    drift: float = 0.0005,
    vol: float = 0.012,
    price_decimals: int = 4,
    volume_range: tuple[float, float] | None = (1e6, 1e9),
    end_date: date = ANCHOR_DATE,
) -> list[HistoricalBar]:
    """Deterministic random walk ending at ~anchor_close on `end_date`.

    Generates `days` bars from (end_date - days + 1) to end_date inclusive.
    Uses geometric Brownian-style steps so all prices stay positive.
    """
    rng = random.Random(seed)
    # Walk backwards from anchor_close, then reverse so the series ends at it.
    closes: list[float] = [anchor_close]
    for _ in range(days - 1):
        step = rng.gauss(drift, vol)
        prev = closes[-1] / (1 + step)
        closes.append(max(prev, anchor_close * 0.01))
    closes.reverse()

    bars: list[HistoricalBar] = []
    for i, close in enumerate(closes):
        bar_date = end_date - timedelta(days=days - 1 - i)
        prev_close = closes[i - 1] if i > 0 else close * (1 + rng.gauss(0, vol * 0.5))
        intra_vol = vol * 0.35
        high = max(close, prev_close) * (1 + abs(rng.gauss(0, intra_vol)))
        low = min(close, prev_close) * (1 - abs(rng.gauss(0, intra_vol)))
        vol_value = round(rng.uniform(*volume_range), 2) if volume_range is not None else None
        bars.append(
            HistoricalBar(
                date=bar_date.isoformat(),
                open=round(prev_close, price_decimals),
                high=round(high, price_decimals),
                low=round(low, price_decimals),
                close=round(close, price_decimals),
                volume=vol_value,
            )
        )
    return bars


class QuoteProvider(ABC):
    """One asset class per provider. Implementations should be stateless w.r.t.
    request boundaries — any caching belongs in the router or HTTP layer."""

    asset_class: AssetClass

    @abstractmethod
    async def quote(self, symbol: str) -> Quote: ...

    @abstractmethod
    async def history(self, symbol: str, days: int) -> list[HistoricalBar]: ...

    async def quote_many(self, symbols: Iterable[str]) -> list[Quote]:
        return [await self.quote(s) for s in symbols]
