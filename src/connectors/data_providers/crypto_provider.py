"""Mock crypto provider. Replace with ccxt/CoinGecko later — keep the QuoteProvider interface."""

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
    "BTC": 67_500.0,
    "ETH": 3_450.0,
    "SOL": 165.0,
    "BNB": 590.0,
    "XRP": 0.58,
    "ADA": 0.42,
    "DOGE": 0.155,
    "AVAX": 32.8,
}


def _anchor(symbol: str) -> float:
    anchor = _BASE_PRICES.get(symbol)
    if anchor is None:
        h = int(hashlib.sha1(symbol.encode()).hexdigest()[:8], 16)
        anchor = (h % 1000) + 1.0
    return anchor


class MockCryptoProvider(QuoteProvider):
    asset_class = AssetClass.CRYPTO

    async def quote(self, symbol: str) -> Quote:
        base = symbol.upper()
        anchor = _anchor(base)
        # Deterministic per-symbol open so intraday OHLC is stable.
        det = random.Random(_seed_for(base) ^ ANCHOR_DATE.toordinal())
        open_p = anchor * (1 + det.gauss(0, 0.009))
        # Live close jitters around anchor each call.
        close_p = anchor * (1 + random.uniform(-0.015, 0.015))
        amp = abs(det.gauss(0, 0.013))
        high_p = max(open_p, close_p) * (1 + amp)
        low_p = min(open_p, close_p) * (1 - amp)
        spread = close_p * 0.0005
        return Quote(
            symbol=base,
            asset_class=self.asset_class,
            price=round(close_p, 4),
            open=round(open_p, 4),
            high=round(high_p, 4),
            low=round(low_p, 4),
            change_24h_pct=round(((close_p - open_p) / open_p) * 100, 2),
            bid=round(close_p - spread, 4),
            ask=round(close_p + spread, 4),
            volume_24h=round(random.uniform(1e7, 5e9), 2),
            ts=datetime.now(UTC).isoformat(),
        )

    async def history(self, symbol: str, days: int) -> list[HistoricalBar]:
        base = symbol.upper()
        return random_walk_history(
            anchor_close=_anchor(base),
            days=days,
            seed=_seed_for(base),
            vol=0.025,
            price_decimals=4,
            volume_range=(1e7, 5e9),
        )
