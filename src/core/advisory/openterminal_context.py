"""Public ETF context shared with the terminal; never a futures price or allowance."""

from datetime import datetime
from decimal import Decimal
from typing import Literal, Self

from pydantic import ConfigDict, Field, HttpUrl, model_validator

from core.advisory.models import Strict, UTCDateTime

TerminalInstrument = Literal["MES", "MNQ"]
PROXIES: dict[TerminalInstrument, Literal["SPY", "QQQ"]] = {"MES": "SPY", "MNQ": "QQQ"}


class PublicQuote(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: Literal["SPY", "QQQ"]
    name: str | None = Field(default=None, max_length=200)
    price: Decimal = Field(gt=0, allow_inf_nan=False)
    change_percent: Decimal | None = Field(default=None, allow_inf_nan=False)
    provider: str = Field(min_length=1, max_length=80)
    currency: Literal["USD"]
    market_time: UTCDateTime | None = None


class PublicHeadline(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: str = Field(min_length=1, max_length=400)
    url: HttpUrl
    publisher: str = Field(min_length=1, max_length=150)
    published_at: UTCDateTime | None = None


class TerminalSource(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["quotes", "news", "history"]
    state: Literal["available", "unavailable", "invalid"]
    received_at: UTCDateTime
    response_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def content_identity(self) -> Self:
        if self.state == "available" and self.response_sha256 is None:
            raise ValueError("Available public response requires content identity")
        return self


class OpenTerminalContext(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["openterminal-context-v1"] = "openterminal-context-v1"
    instrument_id: TerminalInstrument
    proxy_symbol: Literal["SPY", "QQQ"]
    assessed_at: UTCDateTime
    quote: PublicQuote | None = None
    headlines: tuple[PublicHeadline, ...] = ()
    sources: tuple[TerminalSource, ...]
    direction: Literal["proxy_up", "proxy_down", "proxy_unchanged", "unknown"] = "unknown"
    scope: Literal["public_etf_context"] = "public_etf_context"
    freshness: Literal["UNKNOWN"] = "UNKNOWN"
    event_risk: Literal["UNKNOWN"] = "UNKNOWN"
    quote_usable_for_risk: Literal[False] = False
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def identities(self) -> Self:
        if self.proxy_symbol != PROXIES[self.instrument_id]:
            raise ValueError("Proxy is not the selected instrument's context")
        if len(self.sources) != 2 or {row.kind for row in self.sources} != {"quotes", "news"}:
            raise ValueError("Both distinct source results are required")
        if any(row.received_at > self.assessed_at for row in self.sources):
            raise ValueError("Source response cannot be future received")
        if self.quote is not None and (
            self.quote.symbol != self.proxy_symbol
            or next(row for row in self.sources if row.kind == "quotes").state != "available"
            or (self.quote.market_time is not None and self.quote.market_time > self.assessed_at)
        ):
            raise ValueError("Quote identity, availability or clock mismatch")
        if any(
            row.published_at is not None and row.published_at > self.assessed_at
            for row in self.headlines
        ):
            raise ValueError("Future-known headline")
        expected = "unknown"
        if self.quote is not None and self.quote.change_percent is not None:
            expected = (
                "proxy_up"
                if self.quote.change_percent > 0
                else "proxy_down" if self.quote.change_percent < 0 else "proxy_unchanged"
            )
        if self.direction != expected:
            raise ValueError("Context direction disagrees with its reported proxy change")
        return self


def build_terminal_context(
    instrument: TerminalInstrument,
    quote: PublicQuote | None,
    headlines: tuple[PublicHeadline, ...],
    sources: tuple[TerminalSource, ...],
    *,
    now: datetime,
) -> OpenTerminalContext:
    """Summarize the proxy only; do not change any market/account/event guard."""
    if quote is not None and quote.symbol != PROXIES[instrument]:
        raise ValueError("Public proxy identity does not match the selected instrument")
    direction: Literal["proxy_up", "proxy_down", "proxy_unchanged", "unknown"] = "unknown"
    if quote is not None and quote.change_percent is not None:
        direction = (
            "proxy_up"
            if quote.change_percent > 0
            else "proxy_down" if quote.change_percent < 0 else "proxy_unchanged"
        )
    return OpenTerminalContext(
        instrument_id=instrument,
        proxy_symbol=PROXIES[instrument],
        assessed_at=now,
        quote=quote,
        headlines=headlines,
        sources=sources,
        direction=direction,
    )
