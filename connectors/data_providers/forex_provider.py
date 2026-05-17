"""Mock forex provider. Replace with Alpha Vantage / ExchangeRate-API / Polygon later."""
from __future__ import annotations

import random
from datetime import datetime, timezone

from connectors.data_providers.base import (
    ANCHOR_DATE,
    AssetClass,
    HistoricalBar,
    Quote,
    QuoteProvider,
    _seed_for,
    random_walk_history,
)

_BASE_RATES: dict[str, float] = {
    "EUR/USD": 1.0865,
    "GBP/USD": 1.2710,
    "USD/JPY": 154.82,
    "USD/CHF": 0.9035,
    "AUD/USD": 0.6612,
    "USD/CAD": 1.3672,
    "XAU/USD": 2_345.50,  # Gold
    "XAG/USD": 28.45,      # Silver
}


def _is_metal(symbol: str) -> bool:
    return symbol.startswith("XAU") or symbol.startswith("XAG")


class MockForexProvider(QuoteProvider):
    asset_class = AssetClass.FOREX

    async def quote(self, symbol: str) -> Quote:
        pair = symbol.upper()
        anchor = _BASE_RATES.get(pair, 1.0)
        det = random.Random(_seed_for(pair) ^ ANCHOR_DATE.toordinal())
        open_p = anchor * (1 + det.gauss(0, 0.002))
        close_p = anchor * (1 + random.uniform(-0.003, 0.003))
        amp = abs(det.gauss(0, 0.003))
        high_p = max(open_p, close_p) * (1 + amp)
        low_p = min(open_p, close_p) * (1 - amp)
        spread = close_p * 0.0001
        decimals = 2 if _is_metal(pair) else 5
        return Quote(
            symbol=pair,
            asset_class=self.asset_class,
            price=round(close_p, decimals),
            open=round(open_p, decimals),
            high=round(high_p, decimals),
            low=round(low_p, decimals),
            change_24h_pct=round(((close_p - open_p) / open_p) * 100, 3),
            bid=round(close_p - spread, decimals),
            ask=round(close_p + spread, decimals),
            volume_24h=None,
            ts=datetime.now(timezone.utc).isoformat(),
        )

    async def history(self, symbol: str, days: int) -> list[HistoricalBar]:
        pair = symbol.upper()
        return random_walk_history(
            anchor_close=_BASE_RATES.get(pair, 1.0),
            days=days,
            seed=_seed_for(pair),
            vol=0.005 if not _is_metal(pair) else 0.011,
            price_decimals=2 if _is_metal(pair) else 5,
            volume_range=None,
        )
