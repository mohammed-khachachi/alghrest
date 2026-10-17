"""Immutable research snapshots, independent of the futures watchlist."""

from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from core.advisory.models import Strict, UTCDateTime
from core.advisory.openterminal_research import TerminalResearch, TerminalSymbol


class ResearchWatch(Strict):
    watched: bool


class CaptureRequest(Strict):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")


class ResearchSnapshot(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["research-snapshot-v1"] = "research-snapshot-v1"
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    saved_at: UTCDateTime
    report: TerminalResearch
    restored_from_backup: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def clocks(self) -> Self:
        age = (self.saved_at - self.report.assessed_at).total_seconds()
        if not 0 <= age < 90:
            raise ValueError("Snapshot must be saved from a newly collected report")
        return self


class ResearchWatchEntry(Strict):
    symbol: TerminalSymbol
    snapshots: int = Field(ge=0, le=100)
    latest_saved_at: UTCDateTime | None
