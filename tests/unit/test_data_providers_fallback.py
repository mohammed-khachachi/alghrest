"""Roadmap item 3 — real market-data providers with deterministic fallback.

These tests prove the *gating + fallback* contract without any API key or
network access:

- A real call is attempted only when the provider is ``enabled`` (env flag + key).
- Missing key (``enabled=False``) → the deterministic mock answers.
- An upstream failure while enabled → fall back to the deterministic mock.
- An enabled provider whose real fetch succeeds → the real value is used.
- ``_build_default_router`` keeps using mocks when the master flag is off, so the
  dashboard mock server is unaffected.

The real HTTP bodies (``_fetch_quote`` / ``_fetch_history``) are never called by
these tests — that is the point of the fallback design.
"""

from __future__ import annotations

import pytest

from connectors.data_providers.base import AssetClass, HistoricalBar, Quote
from connectors.data_providers.crypto_provider import MockCryptoProvider
from connectors.data_providers.real_provider import (
    AlpacaEquityProvider,
    AlphaVantageForexProvider,
    CoinGeckoCryptoProvider,
    FallbackQuoteProvider,
)
from connectors.data_providers.router import _build_default_router


def _sample_quote(symbol: str = "BTC") -> Quote:
    return Quote(
        symbol=symbol,
        asset_class=AssetClass.CRYPTO,
        price=1.0,
        open=1.0,
        high=1.0,
        low=1.0,
        change_24h_pct=0.0,
        bid=1.0,
        ask=1.0,
        volume_24h=None,
        ts="2025-05-11T00:00:00+00:00",
    )


class _BoomProvider(FallbackQuoteProvider):
    """Enabled provider whose real fetch always fails (simulates a network error)."""

    async def _fetch_quote(self, symbol: str) -> Quote:
        raise RuntimeError("simulated upstream failure")

    async def _fetch_history(self, symbol: str, days: int) -> list[HistoricalBar]:
        raise RuntimeError("simulated upstream failure")


class _StubRealProvider(FallbackQuoteProvider):
    """Enabled provider whose real fetch succeeds with a sentinel value."""

    SENTINEL = "REAL-PRICE-SENTINEL"

    async def _fetch_quote(self, symbol: str) -> Quote:
        return _sample_quote(self.SENTINEL)

    async def _fetch_history(self, symbol: str, days: int) -> list[HistoricalBar]:
        return [HistoricalBar(date="2025-05-11", open=1, high=1, low=1, close=1, volume=None)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_disabled_provider_uses_mock_fallback() -> None:
    """No key → enabled is False → the deterministic mock answers."""
    provider = CoinGeckoCryptoProvider(api_key="")  # no key
    assert provider.real_enabled is False

    quote = await provider.quote("BTC")
    mock_quote = await MockCryptoProvider().quote("BTC")
    # Same provider answered: open price is deterministic and stable across calls.
    assert quote.symbol == mock_quote.symbol == "BTC"
    assert quote.open == mock_quote.open


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enabled_provider_falls_back_on_upstream_error() -> None:
    """Network/upstream failure while enabled → deterministic mock fallback."""
    fallback = MockCryptoProvider()
    provider = _BoomProvider(fallback=fallback, enabled=True)
    assert provider.real_enabled is True

    quote = await provider.quote("ETH")
    mock_quote = await fallback.quote("ETH")
    assert quote.open == mock_quote.open  # fell back to the mock

    bars = await provider.history("ETH", 5)
    assert len(bars) == 5  # mock history, not the (failed) real path


@pytest.mark.unit
@pytest.mark.asyncio
async def test_enabled_provider_uses_real_value_on_success() -> None:
    """Enabled + real fetch succeeds → the real value is used, not the mock."""
    provider = _StubRealProvider(fallback=MockCryptoProvider(), enabled=True)

    quote = await provider.quote("BTC")
    assert quote.symbol == _StubRealProvider.SENTINEL

    bars = await provider.history("BTC", 30)
    assert len(bars) == 1  # the stub real history, not a 30-bar mock series


@pytest.mark.unit
def test_provider_enabled_only_with_flag_and_key() -> None:
    """enabled requires a present key (and both key+secret for Alpaca)."""
    assert CoinGeckoCryptoProvider(api_key="").real_enabled is False
    assert CoinGeckoCryptoProvider(api_key="cg-key").real_enabled is True

    assert AlphaVantageForexProvider(api_key="").real_enabled is False
    assert AlphaVantageForexProvider(api_key="av-key").real_enabled is True

    assert AlpacaEquityProvider(api_key="id", api_secret="").real_enabled is False
    assert AlpacaEquityProvider(api_key="", api_secret="sec").real_enabled is False
    assert AlpacaEquityProvider(api_key="id", api_secret="sec").real_enabled is True


@pytest.mark.unit
def test_router_defaults_to_mocks_when_flag_off(monkeypatch) -> None:
    """Master flag off → router keeps mock providers (dashboard mock unaffected)."""
    import core.config

    monkeypatch.setattr(core.config.settings, "enable_real_market_data", False, raising=False)
    router = _build_default_router()

    provider = router._providers[AssetClass.CRYPTO]
    assert isinstance(provider, MockCryptoProvider)
    assert not isinstance(provider, FallbackQuoteProvider)


@pytest.mark.unit
def test_router_upgrades_to_real_when_flag_and_key_present(monkeypatch) -> None:
    """Master flag on + key present → crypto becomes a real provider with mock fallback."""
    import core.config

    monkeypatch.setattr(core.config.settings, "enable_real_market_data", True, raising=False)
    monkeypatch.setattr(core.config.settings, "coingecko_api_key", "cg-key", raising=False)
    # No forex/equity keys → those stay mocks.
    monkeypatch.setattr(core.config.settings, "alpha_vantage_api_key", "", raising=False)
    monkeypatch.setattr(core.config.settings, "alpaca_api_key", "", raising=False)
    monkeypatch.setattr(core.config.settings, "alpaca_secret", "", raising=False)

    router = _build_default_router()

    crypto = router._providers[AssetClass.CRYPTO]
    assert isinstance(crypto, CoinGeckoCryptoProvider)
    assert crypto.real_enabled is True
    # Forex without a key remains the plain mock.
    from connectors.data_providers.forex_provider import MockForexProvider

    assert isinstance(router._providers[AssetClass.FOREX], MockForexProvider)
