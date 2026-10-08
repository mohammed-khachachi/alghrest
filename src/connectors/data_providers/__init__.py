"""
Market-data provider layer.

Each provider implements `QuoteProvider` for a single asset class. The `router`
picks the right provider per symbol from a static catalog. v1 ships with
mock providers; real integrations (ccxt/CoinGecko/Alpha Vantage/Alpaca) plug
in by replacing the mock classes without changing the router or API surface.
"""

from connectors.data_providers.base import AssetClass, Quote, QuoteProvider
from connectors.data_providers.router import QuoteRouter, SymbolCatalogEntry, default_router

__all__ = [
    "AssetClass",
    "Quote",
    "QuoteProvider",
    "QuoteRouter",
    "SymbolCatalogEntry",
    "default_router",
]
