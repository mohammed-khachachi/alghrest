"""Mock portfolio holdings.

Each holding is anchored to a historical date before ANCHOR_DATE; the entry
price comes from the same deterministic random walk that powers /api/history,
so the price the user sees on the sparkline at `opened_at` matches the
holding's `entry_price` exactly.
"""

from __future__ import annotations

from dataclasses import dataclass

from connectors.data_providers.base import AssetClass
from connectors.data_providers.router import QuoteRouter

BROKER_MAP: dict[AssetClass, str] = {
    AssetClass.CRYPTO: "Binance",
    AssetClass.FOREX: "OANDA",
    AssetClass.EQUITY: "Alpaca",
}


@dataclass(frozen=True)
class Holding:
    symbol: str
    broker: str
    asset_class: AssetClass
    side: str  # "BUY" only for the v1 demo (long-only)
    volume: float
    entry_price: float
    opened_at: str  # ISO date


# (symbol, volume, days_before_anchor)
_RAW: tuple[tuple[str, float, int], ...] = (
    ("BTC", 0.50, 16),  # 2025-04-25
    ("ETH", 4.00, 21),  # 2025-04-20
    ("SOL", 25.00, 9),  # 2025-05-02
    ("EUR/USD", 10_000.00, 14),  # 2025-04-27
    ("XAU/USD", 2.00, 28),  # 2025-04-13
    ("AAPL", 25.00, 18),  # 2025-04-23
    ("TSLA", 10.00, 7),  # 2025-05-04
    ("NVDA", 30.00, 12),  # 2025-04-29
)


_cached: list[Holding] | None = None


async def get_holdings(router: QuoteRouter) -> list[Holding]:
    """Build (and cache) the holdings list. Idempotent across calls."""
    global _cached
    if _cached is not None:
        return _cached
    built: list[Holding] = []
    for symbol, volume, days_back in _RAW:
        entry = router.lookup(symbol)
        # Fetch days_back + 1 bars so bars[0] is exactly `days_back` days
        # before the anchor date.
        bars = await router.history(symbol, days_back + 1)
        entry_bar = bars[0]
        built.append(
            Holding(
                symbol=entry.symbol,
                broker=BROKER_MAP[entry.asset_class],
                asset_class=entry.asset_class,
                side="BUY",
                volume=volume,
                entry_price=entry_bar.close,
                opened_at=entry_bar.date,
            )
        )
    _cached = built
    return built


def reset_cache() -> None:
    """Test/dev helper — drop the cached holdings."""
    global _cached
    _cached = None
