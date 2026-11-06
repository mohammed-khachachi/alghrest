"""Symbol → provider routing + static catalog used by the dashboard."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from connectors.data_providers.base import AssetClass, HistoricalBar, Quote, QuoteProvider
from connectors.data_providers.crypto_provider import MockCryptoProvider
from connectors.data_providers.equity_provider import MockEquityProvider
from connectors.data_providers.forex_provider import MockForexProvider
from connectors.data_providers.openbb_adapter import OpenBBAdapter, OpenBBQuoteProvider
from core.config import Settings, settings as default_settings


@dataclass(frozen=True)
class SymbolCatalogEntry:
    symbol: str
    name: str
    asset_class: AssetClass


# Curated v1 catalog. Extend freely — additions require no router code changes.
_CATALOG: tuple[SymbolCatalogEntry, ...] = (
    # Crypto
    SymbolCatalogEntry("BTC", "Bitcoin", AssetClass.CRYPTO),
    SymbolCatalogEntry("ETH", "Ethereum", AssetClass.CRYPTO),
    SymbolCatalogEntry("SOL", "Solana", AssetClass.CRYPTO),
    SymbolCatalogEntry("BNB", "Binance Coin", AssetClass.CRYPTO),
    SymbolCatalogEntry("XRP", "Ripple", AssetClass.CRYPTO),
    SymbolCatalogEntry("ADA", "Cardano", AssetClass.CRYPTO),
    SymbolCatalogEntry("DOGE", "Dogecoin", AssetClass.CRYPTO),
    SymbolCatalogEntry("AVAX", "Avalanche", AssetClass.CRYPTO),
    # Forex
    SymbolCatalogEntry("EUR/USD", "Euro / US Dollar", AssetClass.FOREX),
    SymbolCatalogEntry("GBP/USD", "British Pound / US Dollar", AssetClass.FOREX),
    SymbolCatalogEntry("USD/JPY", "US Dollar / Japanese Yen", AssetClass.FOREX),
    SymbolCatalogEntry("USD/CHF", "US Dollar / Swiss Franc", AssetClass.FOREX),
    SymbolCatalogEntry("AUD/USD", "Australian Dollar / US Dollar", AssetClass.FOREX),
    SymbolCatalogEntry("USD/CAD", "US Dollar / Canadian Dollar", AssetClass.FOREX),
    SymbolCatalogEntry("XAU/USD", "Gold (Spot)", AssetClass.FOREX),
    SymbolCatalogEntry("XAG/USD", "Silver (Spot)", AssetClass.FOREX),
    # Equities
    SymbolCatalogEntry("AAPL", "Apple Inc.", AssetClass.EQUITY),
    SymbolCatalogEntry("MSFT", "Microsoft Corp.", AssetClass.EQUITY),
    SymbolCatalogEntry("GOOGL", "Alphabet Inc. Class A", AssetClass.EQUITY),
    SymbolCatalogEntry("AMZN", "Amazon.com Inc.", AssetClass.EQUITY),
    SymbolCatalogEntry("META", "Meta Platforms Inc.", AssetClass.EQUITY),
    SymbolCatalogEntry("TSLA", "Tesla Inc.", AssetClass.EQUITY),
    SymbolCatalogEntry("NVDA", "NVIDIA Corp.", AssetClass.EQUITY),
    SymbolCatalogEntry("JPM", "JPMorgan Chase & Co.", AssetClass.EQUITY),
)


class UnknownSymbolError(ValueError):
    pass


class QuoteRouter:
    def __init__(
        self,
        providers: dict[AssetClass, QuoteProvider],
        catalog: Iterable[SymbolCatalogEntry],
    ) -> None:
        self._providers = providers
        self._catalog = {e.symbol.upper(): e for e in catalog}

    @property
    def catalog(self) -> list[SymbolCatalogEntry]:
        return list(self._catalog.values())

    def lookup(self, symbol: str) -> SymbolCatalogEntry:
        entry = self._catalog.get(symbol.upper())
        if entry is None:
            raise UnknownSymbolError(symbol)
        return entry

    async def quote(self, symbol: str) -> Quote:
        entry = self.lookup(symbol)
        provider = self._providers[entry.asset_class]
        return await provider.quote(entry.symbol)

    async def quote_many(self, symbols: Iterable[str]) -> list[Quote]:
        out: list[Quote] = []
        for s in symbols:
            try:
                out.append(await self.quote(s))
            except UnknownSymbolError:
                continue
        return out

    async def history(self, symbol: str, days: int) -> list[HistoricalBar]:
        entry = self.lookup(symbol)
        provider = self._providers[entry.asset_class]
        return await provider.history(entry.symbol, days)


def build_router(
    *,
    config: Settings | None = None,
    adapter: OpenBBAdapter | None = None,
    use_openbb: bool | None = None,
) -> QuoteRouter:
    """Build a QuoteRouter backed by OpenBB when enabled, or mock providers otherwise."""
    cfg = config or default_settings
    enable_obb = cfg.openbb_enabled if use_openbb is None else use_openbb

    mock_crypto = MockCryptoProvider()
    mock_forex = MockForexProvider()
    mock_equity = MockEquityProvider()

    if not enable_obb:
        return QuoteRouter(
            providers={
                AssetClass.CRYPTO: mock_crypto,
                AssetClass.FOREX: mock_forex,
                AssetClass.EQUITY: mock_equity,
            },
            catalog=_CATALOG,
        )

    obb_adapter = adapter or OpenBBAdapter(config=cfg)
    return QuoteRouter(
        providers={
            AssetClass.CRYPTO: OpenBBQuoteProvider(
                AssetClass.CRYPTO,
                adapter=obb_adapter,
                fallback_provider=mock_crypto,
                provider_name=cfg.openbb_default_crypto_provider,
                fallback_to_mock=cfg.openbb_fallback_to_mock,
            ),
            AssetClass.FOREX: OpenBBQuoteProvider(
                AssetClass.FOREX,
                adapter=obb_adapter,
                fallback_provider=mock_forex,
                provider_name=cfg.openbb_default_forex_provider,
                fallback_to_mock=cfg.openbb_fallback_to_mock,
            ),
            AssetClass.EQUITY: OpenBBQuoteProvider(
                AssetClass.EQUITY,
                adapter=obb_adapter,
                fallback_provider=mock_equity,
                provider_name=cfg.openbb_default_equity_provider,
                fallback_to_mock=cfg.openbb_fallback_to_mock,
            ),
        },
        catalog=_CATALOG,
    )


def _build_default_router() -> QuoteRouter:
    return build_router()


default_router = _build_default_router()
