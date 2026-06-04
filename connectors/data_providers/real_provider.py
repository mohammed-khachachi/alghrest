"""Real market-data providers with a deterministic mock fallback.

Roadmap item 3. These wrap the existing mock providers so the dashboard never
breaks and tests never need an API key:

- A real upstream call is attempted **only** when the master flag
  ``settings.enable_real_market_data`` is on **and** the relevant API key is
  present (``enabled``).
- Any missing key, disabled flag, or upstream error (network, HTTP, parse)
  falls back to the deterministic mock anchored to ``ANCHOR_DATE``.

The ``QuoteProvider`` interface, ``QuoteRouter``, and the catalog are untouched
— a real provider *is* a ``QuoteProvider`` that delegates to a mock on failure.
Concrete venue parsing is intentionally thin; these classes exist to swap mocks
for real feeds later (see CLAUDE.md), so the tested contract is the gating +
fallback behaviour, not venue-specific response shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from connectors.data_providers.base import (
    AssetClass,
    HistoricalBar,
    Quote,
    QuoteProvider,
)
from connectors.data_providers.crypto_provider import MockCryptoProvider
from connectors.data_providers.equity_provider import MockEquityProvider
from connectors.data_providers.forex_provider import MockForexProvider

logger = structlog.get_logger(__name__)


class FallbackQuoteProvider(QuoteProvider):
    """Attempt a real upstream, fall back to a deterministic mock on any failure.

    Subclasses implement ``_fetch_quote`` / ``_fetch_history`` for the real call.
    They are invoked only when ``enabled`` is true; otherwise (and on any raised
    exception) the wrapped ``fallback`` mock provider answers. This guarantees
    the dashboard keeps working with no keys and that tests need no network.
    """

    def __init__(self, fallback: QuoteProvider, *, enabled: bool) -> None:
        self._fallback = fallback
        self._enabled = enabled
        # Mirror the wrapped provider's asset class so the router treats us the same.
        self.asset_class = fallback.asset_class

    @property
    def real_enabled(self) -> bool:
        return self._enabled

    async def quote(self, symbol: str) -> Quote:
        if self._enabled:
            try:
                return await self._fetch_quote(symbol)
            except Exception as exc:  # network, HTTP status, parse — all fall back
                logger.warning(
                    "real_provider.quote_failed_falling_back",
                    provider=type(self).__name__,
                    symbol=symbol,
                    error=str(exc),
                )
        return await self._fallback.quote(symbol)

    async def history(self, symbol: str, days: int) -> list[HistoricalBar]:
        if self._enabled:
            try:
                return await self._fetch_history(symbol, days)
            except Exception as exc:
                logger.warning(
                    "real_provider.history_failed_falling_back",
                    provider=type(self).__name__,
                    symbol=symbol,
                    error=str(exc),
                )
        return await self._fallback.history(symbol, days)

    async def _fetch_quote(self, symbol: str) -> Quote:  # pragma: no cover - network
        raise NotImplementedError

    async def _fetch_history(
        self, symbol: str, days: int
    ) -> list[HistoricalBar]:  # pragma: no cover - network
        raise NotImplementedError


async def _get_json(url: str, *, params: dict | None = None, headers: dict | None = None) -> object:
    """Thin async GET returning parsed JSON. Raises on any transport/HTTP error."""
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()


class CoinGeckoCryptoProvider(FallbackQuoteProvider):
    """Crypto quotes via CoinGecko, falling back to ``MockCryptoProvider``."""

    _IDS = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "SOL": "solana",
        "BNB": "binancecoin",
        "XRP": "ripple",
        "ADA": "cardano",
        "DOGE": "dogecoin",
        "AVAX": "avalanche-2",
    }

    def __init__(
        self,
        *,
        api_key: str = "",
        enabled: bool | None = None,
        fallback: QuoteProvider | None = None,
    ) -> None:
        self._api_key = api_key
        super().__init__(
            fallback=fallback or MockCryptoProvider(),
            enabled=bool(api_key) if enabled is None else enabled,
        )

    async def _fetch_quote(self, symbol: str) -> Quote:  # pragma: no cover - network
        coin_id = self._IDS.get(symbol.upper())
        if coin_id is None:
            raise ValueError(f"No CoinGecko id for {symbol}")
        data = await _get_json(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={"vs_currency": "usd", "ids": coin_id},
            headers={"x-cg-demo-api-key": self._api_key} if self._api_key else None,
        )
        if not isinstance(data, list) or not data:
            raise ValueError("Empty CoinGecko response")
        row = data[0]
        price = float(row["current_price"])
        change = float(row.get("price_change_percentage_24h") or 0.0)
        high = float(row.get("high_24h") or price)
        low = float(row.get("low_24h") or price)
        open_p = price / (1 + change / 100) if change != -100 else price
        spread = price * 0.0005
        return Quote(
            symbol=symbol.upper(),
            asset_class=AssetClass.CRYPTO,
            price=round(price, 4),
            open=round(open_p, 4),
            high=round(high, 4),
            low=round(low, 4),
            change_24h_pct=round(change, 2),
            bid=round(price - spread, 4),
            ask=round(price + spread, 4),
            volume_24h=float(row.get("total_volume") or 0.0),
            ts=datetime.now(UTC).isoformat(),
        )

    async def _fetch_history(
        self, symbol: str, days: int
    ) -> list[HistoricalBar]:  # pragma: no cover - network
        coin_id = self._IDS.get(symbol.upper())
        if coin_id is None:
            raise ValueError(f"No CoinGecko id for {symbol}")
        data = await _get_json(
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/ohlc",
            params={"vs_currency": "usd", "days": days},
            headers={"x-cg-demo-api-key": self._api_key} if self._api_key else None,
        )
        if not isinstance(data, list) or not data:
            raise ValueError("Empty CoinGecko OHLC response")
        bars: list[HistoricalBar] = []
        for ts_ms, o, h, low_v, c in data:
            day = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).date().isoformat()
            bars.append(
                HistoricalBar(
                    date=day,
                    open=round(float(o), 4),
                    high=round(float(h), 4),
                    low=round(float(low_v), 4),
                    close=round(float(c), 4),
                    volume=None,
                )
            )
        return bars


class AlphaVantageForexProvider(FallbackQuoteProvider):
    """Forex quotes via Alpha Vantage, falling back to ``MockForexProvider``."""

    def __init__(
        self,
        *,
        api_key: str = "",
        enabled: bool | None = None,
        fallback: QuoteProvider | None = None,
    ) -> None:
        self._api_key = api_key
        super().__init__(
            fallback=fallback or MockForexProvider(),
            enabled=bool(api_key) if enabled is None else enabled,
        )

    async def _fetch_quote(self, symbol: str) -> Quote:  # pragma: no cover - network
        from_sym, _, to_sym = symbol.upper().partition("/")
        if not to_sym:
            raise ValueError(f"Forex symbol must be PAIR/PAIR, got {symbol}")
        data = await _get_json(
            "https://www.alphavantage.co/query",
            params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": from_sym,
                "to_currency": to_sym,
                "apikey": self._api_key,
            },
        )
        rate_block = data.get("Realtime Currency Exchange Rate") if isinstance(data, dict) else None
        if not rate_block:
            raise ValueError("Alpha Vantage returned no exchange rate")
        price = float(rate_block["5. Exchange Rate"])
        bid = float(rate_block.get("8. Bid Price") or price)
        ask = float(rate_block.get("9. Ask Price") or price)
        return Quote(
            symbol=symbol.upper(),
            asset_class=AssetClass.FOREX,
            price=round(price, 5),
            open=round(price, 5),
            high=round(max(price, ask), 5),
            low=round(min(price, bid), 5),
            change_24h_pct=0.0,
            bid=round(bid, 5),
            ask=round(ask, 5),
            volume_24h=None,
            ts=datetime.now(UTC).isoformat(),
        )

    async def _fetch_history(
        self, symbol: str, days: int
    ) -> list[HistoricalBar]:  # pragma: no cover - network
        # Daily FX history is gated behind a premium Alpha Vantage tier; defer to
        # the deterministic fallback rather than ship a half-real path.
        raise NotImplementedError("Alpha Vantage daily FX history not wired")


class AlpacaEquityProvider(FallbackQuoteProvider):
    """Equity quotes via Alpaca market data, falling back to ``MockEquityProvider``."""

    def __init__(
        self,
        *,
        api_key: str = "",
        api_secret: str = "",
        enabled: bool | None = None,
        fallback: QuoteProvider | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        super().__init__(
            fallback=fallback or MockEquityProvider(),
            enabled=bool(api_key and api_secret) if enabled is None else enabled,
        )

    def _headers(self) -> dict:
        return {
            "APCA-API-KEY-ID": self._api_key,
            "APCA-API-SECRET-KEY": self._api_secret,
        }

    async def _fetch_quote(self, symbol: str) -> Quote:  # pragma: no cover - network
        ticker = symbol.upper()
        data = await _get_json(
            f"https://data.alpaca.markets/v2/stocks/{ticker}/snapshot",
            headers=self._headers(),
        )
        if not isinstance(data, dict):
            raise ValueError("Alpaca returned a non-object snapshot")
        trade = data.get("latestTrade") or {}
        quote = data.get("latestQuote") or {}
        daily = data.get("dailyBar") or {}
        price = float(trade.get("p") or daily.get("c") or 0.0)
        if price <= 0:
            raise ValueError("Alpaca snapshot missing price")
        open_p = float(daily.get("o") or price)
        return Quote(
            symbol=ticker,
            asset_class=AssetClass.EQUITY,
            price=round(price, 2),
            open=round(open_p, 2),
            high=round(float(daily.get("h") or price), 2),
            low=round(float(daily.get("l") or price), 2),
            change_24h_pct=round(((price - open_p) / open_p) * 100, 2) if open_p else 0.0,
            bid=round(float(quote.get("bp") or price), 2),
            ask=round(float(quote.get("ap") or price), 2),
            volume_24h=float(daily.get("v") or 0.0),
            ts=datetime.now(UTC).isoformat(),
        )

    async def _fetch_history(
        self, symbol: str, days: int
    ) -> list[HistoricalBar]:  # pragma: no cover - network
        ticker = symbol.upper()
        data = await _get_json(
            f"https://data.alpaca.markets/v2/stocks/{ticker}/bars",
            params={"timeframe": "1Day", "limit": days},
            headers=self._headers(),
        )
        bars_raw = data.get("bars") if isinstance(data, dict) else None
        if not bars_raw:
            raise ValueError("Alpaca returned no bars")
        bars: list[HistoricalBar] = []
        for bar in bars_raw:
            bars.append(
                HistoricalBar(
                    date=str(bar["t"])[:10],
                    open=round(float(bar["o"]), 2),
                    high=round(float(bar["h"]), 2),
                    low=round(float(bar["l"]), 2),
                    close=round(float(bar["c"]), 2),
                    volume=float(bar.get("v") or 0.0),
                )
            )
        return bars
