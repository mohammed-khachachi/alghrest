"""Descriptive research on the terminal's own symbol and supplied candle series."""

from datetime import datetime
from decimal import Decimal
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from core.advisory.models import Strict, UTCDateTime
from core.advisory.openterminal_context import PublicHeadline, TerminalSource
from core.advisory.research_quality import FIXED_INTERVALS, CandleQuality

TerminalSymbol = Annotated[str, Field(pattern=r"^[A-Z0-9.^=&-]{1,20}$")]
HistoryProvider = Literal["nasdaq", "yahoo", "stooq", "binance", "fred", "UNKNOWN"]
HistoryInterval = Literal["5m", "15m", "1h", "4h", "1d", "1wk", "1mo", "1w", "1M", "UNVERIFIED"]


class HistoryMetadata(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["openterminal-history-v1"]
    symbol: TerminalSymbol
    requested_range: Literal["6M"]
    provider: Literal["nasdaq", "yahoo", "stooq", "binance", "fred"]
    interval: HistoryInterval | None
    interval_basis: Literal["provider_request", "UNVERIFIED"]
    fetched_at: UTCDateTime
    cache_state: Literal["fetched", "cached", "stale"]

    @model_validator(mode="after")
    def interval_identity(self) -> Self:
        known = self.interval not in {None, "UNVERIFIED"}
        if known != (self.interval_basis == "provider_request"):
            raise ValueError("Timeframe needs its declared basis")
        return self


def valid_symbol(value: str) -> str:
    if not any(c.isalnum() for c in value):
        raise ValueError("Symbol requires an alphanumeric character")
    return value


class QuoteObservation(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["quote-observation-v1"]
    fetched_at: UTCDateTime
    cache_state: Literal["fetched", "cached", "stale"]
    market_state_basis: Literal["provider", "UNVERIFIED"]


class ResearchQuote(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: TerminalSymbol
    name: str | None = Field(default=None, max_length=200)
    price: Decimal = Field(gt=0, le=Decimal("1e30"), allow_inf_nan=False)
    change_percent: Decimal | None = Field(default=None, allow_inf_nan=False)
    currency: str = Field(pattern=r"^[A-Za-z]{3,8}$")
    provider: Literal["nasdaq", "yahoo", "yahoo-chart", "stooq", "tradingview", "binance", "fred"]
    market_time: UTCDateTime | None = None
    market_state: str | None = Field(default=None, max_length=64)
    observation: QuoteObservation | None = None

    _symbol = field_validator("symbol")(valid_symbol)

    @model_validator(mode="after")
    def observation_identity(self) -> Self:
        o = self.observation
        if o and (
            (self.market_time is not None and self.market_time > o.fetched_at)
            or (
                o.market_state_basis == "provider"
                and (self.provider not in {"yahoo", "nasdaq"} or not self.market_state)
            )
        ):
            raise ValueError("Invalid quote observation identity/clock")
        return self


class TerminalCandle(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    time: UTCDateTime
    open: Decimal = Field(gt=0, le=Decimal("1e30"), allow_inf_nan=False)
    high: Decimal = Field(gt=0, le=Decimal("1e30"), allow_inf_nan=False)
    low: Decimal = Field(gt=0, le=Decimal("1e30"), allow_inf_nan=False)
    close: Decimal = Field(gt=0, le=Decimal("1e30"), allow_inf_nan=False)
    volume: Decimal = Field(ge=0, le=Decimal("1e30"), allow_inf_nan=False)

    @model_validator(mode="after")
    def envelope(self) -> Self:
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Invalid OHLC envelope")
        return self


class CandleAnalysis(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    count: int = Field(ge=1, le=2000)
    first_time: UTCDateTime
    last_time: UTCDateTime
    last_close: Decimal
    sma20: Decimal | None = None
    sma50: Decimal | None = None
    rsi14_simple: Decimal | None = None
    atr14_simple: Decimal | None = None
    recent20_low: Decimal | None = None
    recent20_high: Decimal | None = None
    trend: Literal["above_averages", "below_averages", "mixed", "insufficient"]
    history_provider: HistoryProvider = "UNKNOWN"
    interval: HistoryInterval = "UNVERIFIED"
    interval_basis: Literal["provider_request", "UNVERIFIED"] = "UNVERIFIED"
    history_fetched_at: UTCDateTime | None = None
    history_cache_state: Literal["fetched", "cached", "stale", "UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def provenance(self) -> Self:
        known = self.history_provider != "UNKNOWN"
        if known != (self.history_fetched_at is not None) or known != (
            self.history_cache_state != "UNKNOWN"
        ):
            raise ValueError("History provenance must travel together")
        if (self.interval != "UNVERIFIED") != (self.interval_basis == "provider_request"):
            raise ValueError("Timeframe needs its declared basis")
        if self.interval != "UNVERIFIED" and not known:
            raise ValueError("Timeframe requires provider provenance")
        return self


class TerminalResearch(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["openterminal-research-v1"] = "openterminal-research-v1"
    symbol: TerminalSymbol
    requested_range: Literal["6M"] = "6M"
    assessed_at: UTCDateTime
    quote: ResearchQuote | None = None
    analysis: CandleAnalysis | None = None
    data_quality: CandleQuality | None = None
    headlines: tuple[PublicHeadline, ...] = ()
    sources: tuple[TerminalSource, ...]
    freshness: Literal["UNKNOWN"] = "UNKNOWN"
    event_risk: Literal["UNKNOWN"] = "UNKNOWN"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    _symbol = field_validator("symbol")(valid_symbol)

    @model_validator(mode="after")
    def coherence(self) -> Self:
        if len(self.sources) != 3 or {s.kind for s in self.sources} != {
            "quotes",
            "news",
            "history",
        }:
            raise ValueError("Three distinct source results are required")
        states = {s.kind: s.state for s in self.sources}
        if any(s.received_at > self.assessed_at for s in self.sources):
            raise ValueError("Future received source")
        if self.quote and (
            self.quote.symbol != self.symbol
            or states["quotes"] != "available"
            or (self.quote.market_time and self.quote.market_time > self.assessed_at)
            or (
                self.quote.observation
                and self.quote.observation.fetched_at
                > next(s.received_at for s in self.sources if s.kind == "quotes")
            )
        ):
            raise ValueError("Quote identity or availability mismatch")
        if self.analysis and (
            states["history"] != "available"
            or self.analysis.first_time > self.analysis.last_time
            or self.analysis.last_time > self.assessed_at
            or (
                self.analysis.history_fetched_at is not None
                and not self.analysis.last_time
                <= self.analysis.history_fetched_at
                <= self.assessed_at
            )
        ):
            raise ValueError("History clock or availability mismatch")
        if self.headlines and states["news"] != "available":
            raise ValueError("Headlines require available news")
        q, a = self.data_quality, self.analysis
        if q:
            if (q.status == "unavailable") != (a is None):
                raise ValueError("Quality and analysis availability mismatch")
            if a and (q.received_candles != a.count or states["history"] != "available"):
                raise ValueError("Quality must describe the analyzed series")
            if a and (
                q.interval_seconds != FIXED_INTERVALS.get(a.interval)
                or (q.continuity_basis == "continuous")
                != (a.history_provider == "binance" and a.interval in FIXED_INTERVALS)
            ):
                raise ValueError("Quality continuity must match source provenance")
            if a and (
                (
                    not q.trend.allowed
                    and (a.sma20 is not None or a.sma50 is not None or a.trend != "insufficient")
                )
                or (not q.momentum.allowed and a.rsi14_simple is not None)
                or (not q.volatility.allowed and a.atr14_simple is not None)
            ):
                raise ValueError("Blocked quality cannot expose indicator conclusions")
        return self


def analyze_candles(
    candles: tuple[TerminalCandle, ...],
    now: datetime,
    metadata: HistoryMetadata | None = None,
    quality: CandleQuality | None = None,
) -> CandleAnalysis:
    """Use bar counts, not assumed daily/intraday frequency or qualified trade signals."""
    if not candles or len(candles) > 2000:
        raise ValueError("History size is invalid")
    if any(c.time > now for c in candles) or any(a.time >= b.time for a, b in pairwise(candles)):
        raise ValueError("History must be strictly ordered without future bars")
    if metadata and not candles[-1].time <= metadata.fetched_at <= now:
        raise ValueError("Invalid history fetch clock")
    if quality and (quality.status == "unavailable" or quality.received_candles != len(candles)):
        raise ValueError("Quality must describe the valid series")
    closes = [c.close for c in candles]
    sma20 = sum(closes[-20:], Decimal(0)) / 20 if len(closes) >= 20 else None
    sma50 = sum(closes[-50:], Decimal(0)) / 50 if len(closes) >= 50 else None
    rsi = atr = None
    if len(closes) >= 15:
        changes = [b - a for a, b in zip(closes[-15:-1], closes[-14:], strict=True)]
        gains = sum((max(c, Decimal(0)) for c in changes), Decimal(0))
        losses = sum((max(-c, Decimal(0)) for c in changes), Decimal(0))
        rsi = Decimal(50) if gains == losses == 0 else 100 * gains / (gains + losses)
        ranges = [
            max(c.high - c.low, abs(c.high - p.close), abs(c.low - p.close))
            for p, c in zip(candles[-15:-1], candles[-14:], strict=True)
        ]
        atr = sum(ranges, Decimal(0)) / 14
    trend: Literal["above_averages", "below_averages", "mixed", "insufficient"] = "insufficient"
    if sma20 is not None and sma50 is not None:
        trend = (
            "above_averages"
            if closes[-1] > sma20 > sma50
            else "below_averages" if closes[-1] < sma20 < sma50 else "mixed"
        )
    if quality:
        if not quality.trend.allowed:
            sma20 = sma50 = None
            trend = "insufficient"
        if not quality.momentum.allowed:
            rsi = None
        if not quality.volatility.allowed:
            atr = None
    return CandleAnalysis(
        count=len(candles),
        first_time=candles[0].time,
        last_time=candles[-1].time,
        last_close=closes[-1],
        sma20=sma20,
        sma50=sma50,
        rsi14_simple=rsi,
        atr14_simple=atr,
        recent20_low=min(c.low for c in candles[-20:]) if len(candles) >= 20 else None,
        recent20_high=max(c.high for c in candles[-20:]) if len(candles) >= 20 else None,
        trend=trend,
        history_provider=metadata.provider if metadata else "UNKNOWN",
        interval=(metadata.interval or "UNVERIFIED") if metadata else "UNVERIFIED",
        interval_basis=metadata.interval_basis if metadata else "UNVERIFIED",
        history_fetched_at=metadata.fetched_at if metadata else None,
        history_cache_state=metadata.cache_state if metadata else "UNKNOWN",
    )
