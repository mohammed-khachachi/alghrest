"""Bounded public GET-only market adapter; never receives account credentials."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal

import httpx
from pydantic import HttpUrl

from connectors.advisory.storage import AdvisoryStore
from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.models import (
    CATALOG,
    Candle,
    Interval,
    MarketDataEvidence,
    MarketSnapshot,
    PriceObservation,
    utcnow,
)

SPOT = "https://data-api.binance.vision"
FUTURES = "https://fapi.binance.com"
COINBASE = "https://api.exchange.coinbase.com"


class PublicMarkets:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self.client = client

    async def get(self, base: str, path: str, params: dict[str, str | int] | None = None) -> Any:
        response = await self.client.get(base + path, params=params)
        response.raise_for_status()
        if len(response.content) > 1_000_000:
            raise ValueError("Market response too large")
        return response.json()

    async def spot(self, symbol: str) -> PriceObservation:
        raw = await self.get(SPOT, "/api/v3/ticker/24hr", {"symbol": symbol.replace("/", "")})
        return PriceObservation(
            symbol=symbol,
            price=Decimal(raw["lastPrice"]),
            timestamp=datetime.fromtimestamp(raw["closeTime"] / 1000, UTC),
            source=HttpUrl(SPOT + "/api/v3/ticker/24hr"),
        )

    async def tether_usd(self) -> PriceObservation:
        raw = await self.get(COINBASE, "/products/USDT-USD/ticker")
        return PriceObservation(
            symbol="USDT/USD",
            price=Decimal(raw["price"]),
            timestamp=raw["time"],
            bid=raw["bid"],
            ask=raw["ask"],
            source=HttpUrl(COINBASE + "/products/USDT-USD/ticker"),
        )

    async def snapshot(self, instrument_id: str, symbol: str, interval: Interval) -> MarketSnapshot:
        raw = await self.get(
            FUTURES, "/fapi/v1/klines", {"symbol": symbol, "interval": interval, "limit": 201}
        )
        now = utcnow()
        candles = [
            Candle(
                open_time=datetime.fromtimestamp(r[0] / 1000, UTC),
                close_time=datetime.fromtimestamp(r[6] / 1000, UTC),
                open=r[1],
                high=r[2],
                low=r[3],
                close=r[4],
                volume=r[5],
            )
            for r in raw
            if r[6] < int(now.timestamp() * 1000)
        ]
        result = MarketSnapshot(
            instrument_id=instrument_id,
            interval=interval,
            source=HttpUrl(FUTURES + "/fapi/v1/klines"),
            fetched_at=now,
            candles=candles,
            data_mode="public_exchange",
            quality=MarketDataEvidence(
                provider_id="binance-public-klines",
                provider_state="active",
                heartbeat_at=now,
                # HTTP complete-window response has no exchange event sequence.
                sequence_mode="not_applicable",
            ),
        )
        # Missing derivatives fields never become zero. Price scenarios can still
        # be useful when an optional interest/funding endpoint is unavailable.
        try:
            mark = await self.get(FUTURES, "/fapi/v1/premiumIndex", {"symbol": symbol})
            interest = await self.get(FUTURES, "/fapi/v1/openInterest", {"symbol": symbol})
            if any(
                not 0 <= (utcnow().timestamp() * 1000 - int(item["time"])) <= 120000
                for item in (mark, interest)
            ):
                raise ValueError("Stale derivatives observation")
            result.derivatives = {
                name: Decimal(str(value))
                for name, value in {
                    "mark_price": mark["markPrice"],
                    "index_price": mark["indexPrice"],
                    "last_funding_rate": mark["lastFundingRate"],
                    "open_interest_base": interest["openInterest"],
                    "next_funding_time_ms": mark["nextFundingTime"],
                    "observed_at_ms": mark["time"],
                }.items()
            }
            if any(not v.is_finite() for v in result.derivatives.values()):
                raise ValueError("Non-finite derivatives fields")
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            result.derivatives = {}
            result.observations.append("بيانات التمويل أو العقود المفتوحة غير متاحة أو قديمة.")
        return result


class AdvisoryMarketData:
    """Reuse current public reads and isolated imports through one domain boundary."""

    mode: Literal["current"] = "current"

    def __init__(self, public: PublicMarkets, store: AdvisoryStore) -> None:
        self.public, self.store = public, store

    async def read(self, query: MarketDataQuery) -> MarketSnapshot | None:
        query = MarketDataQuery.model_validate(query.model_dump())
        instrument = CATALOG[query.instrument_id]
        value: MarketSnapshot | None
        if instrument.market == "crypto_perpetual":
            value = await self.public.snapshot(instrument.id, instrument.symbol, query.interval)
        else:
            value = await asyncio.to_thread(self.store.market, instrument.id, query.interval)
        return bounded_snapshot(value, query)
