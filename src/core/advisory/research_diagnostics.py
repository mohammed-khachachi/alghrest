"""Safe per-symbol observations from the current OpenTerminal process."""

from typing import Literal, Self

from pydantic import Field, model_validator

from core.advisory.models import Strict, UTCDateTime
from core.advisory.openterminal_research import TerminalSymbol


class ProviderClock(Strict):
    value: str = Field(min_length=1, max_length=160)
    basis: Literal["provider_text_unconverted", "ticker_window_close", "daily_close_date"]


class ProviderObservation(Strict):
    symbol: TerminalSymbol
    feed: Literal["quotes", "history", "news"]
    provider: Literal[
        "nasdaq", "yahoo", "yahoo-chart", "stooq", "binance", "fred", "yahoo-rss", "google-rss"
    ]
    state: Literal["available", "unavailable"]
    last_attempt: UTCDateTime
    last_success: UTCDateTime | None
    last_failure: UTCDateTime | None
    failure: Literal["timeout", "upstream_http", "empty_response", "provider_error"] | None
    http_status: int | None = Field(ge=400, le=599)
    clock: ProviderClock | None

    @model_validator(mode="after")
    def coherence(self) -> Self:
        if (self.failure is None) != (self.last_failure is None):
            raise ValueError("Failure requires its observation time")
        if (self.failure == "upstream_http") != (self.http_status is not None):
            raise ValueError("HTTP failure requires a status")
        if self.state == "available" and (
            self.last_success is None or self.last_success < self.last_attempt
        ):
            raise ValueError("Success requires its original clock")
        if self.state == "unavailable" and (
            self.last_failure is None or self.last_failure < self.last_attempt
        ):
            raise ValueError("Failure requires its original clock")
        if (self.feed == "news") != (self.provider in {"yahoo-rss", "google-rss"}):
            raise ValueError("News diagnostics require their RSS source")
        if self.clock and (
            self.feed != "quotes"
            or self.clock.basis
            != {
                "nasdaq": "provider_text_unconverted",
                "binance": "ticker_window_close",
                "fred": "daily_close_date",
            }.get(self.provider)
        ):
            raise ValueError("Clock label does not match its provider")
        return self


class ResearchDiagnostics(Strict):
    schema_version: Literal["research-diagnostics-v1"]
    symbol: TerminalSymbol
    assessed_at: UTCDateTime
    started_at: UTCDateTime
    scope: Literal["process_memory"]
    observations: tuple[ProviderObservation, ...] = Field(max_length=14)

    @model_validator(mode="after")
    def identities(self) -> Self:
        keys = [(r.feed, r.provider) for r in self.observations]
        if len(set(keys)) != len(keys) or self.started_at > self.assessed_at:
            raise ValueError("Invalid diagnostic identity")
        for row in self.observations:
            if row.symbol != self.symbol or any(
                t is not None and not self.started_at <= t <= self.assessed_at
                for t in (row.last_attempt, row.last_success, row.last_failure)
            ):
                raise ValueError("Invalid diagnostic source or clock")
        return self


class DiagnosticResult(Strict):
    symbol: TerminalSymbol
    checked_at: UTCDateTime
    state: Literal["available", "unavailable", "invalid"]
    diagnostics: ResearchDiagnostics | None = None

    @model_validator(mode="after")
    def consistency(self) -> Self:
        d = self.diagnostics
        if (self.state == "available") != (d is not None):
            raise ValueError("Availability requires diagnostics")
        if d and (d.symbol != self.symbol or d.assessed_at > self.checked_at):
            raise ValueError("Diagnostic identity or clock mismatch")
        return self
