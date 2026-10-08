"""Mock equity provider. Replace with Alpaca / Finnhub / IEX Cloud later."""

from __future__ import annotations

import hashlib
import random
from datetime import UTC, datetime

from connectors.data_providers.base import (
    ANCHOR_DATE,
    AssetClass,
    HistoricalBar,
    Quote,
    QuoteProvider,
    _seed_for,
    random_walk_history,
)

_BASE_PRICES: dict[str, float] = {
    "AAPL": 224.50,
    "MSFT": 415.80,
    "GOOGL": 168.30,
    "AMZN": 188.65,
    "META": 512.40,
    "TSLA": 245.20,
    "NVDA": 138.75,
    "JPM": 215.10,
}


def _anchor(symbol: str) -> float:
    anchor = _BASE_PRICES.get(symbol)
    if anchor is None:
        h = int(hashlib.sha1(symbol.encode()).hexdigest()[:8], 16)
        anchor = (h % 500) + 10.0
    return anchor


class MockEquityProvider(QuoteProvider):
    asset_class = AssetClass.EQUITY

    async def quote(self, symbol: str) -> Quote:
        ticker = symbol.upper()
        anchor = _anchor(ticker)
        det = random.Random(_seed_for(ticker) ^ ANCHOR_DATE.toordinal())
        open_p = anchor * (1 + det.gauss(0, 0.007))
        close_p = anchor * (1 + random.uniform(-0.012, 0.012))
        amp = abs(det.gauss(0, 0.01))
        high_p = max(open_p, close_p) * (1 + amp)
        low_p = min(open_p, close_p) * (1 - amp)
        spread = max(close_p * 0.0002, 0.01)
        return Quote(
            symbol=ticker,
            asset_class=self.asset_class,
            price=round(close_p, 2),
            open=round(open_p, 2),
            high=round(high_p, 2),
            low=round(low_p, 2),
            change_24h_pct=round(((close_p - open_p) / open_p) * 100, 2),
            bid=round(close_p - spread, 2),
            ask=round(close_p + spread, 2),
            volume_24h=round(random.uniform(5e5, 8e7), 0),
            ts=datetime.now(UTC).isoformat(),
        )

    async def history(self, symbol: str, days: int) -> list[HistoricalBar]:
        ticker = symbol.upper()
        return random_walk_history(
            anchor_close=_anchor(ticker),
            days=days,
            seed=_seed_for(ticker),
            vol=0.018,
            price_decimals=2,
            volume_range=(5e5, 8e7),
        )
