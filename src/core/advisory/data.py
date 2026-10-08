"""Provider-independent, clock-explicit requests for bounded market snapshots."""

from typing import Literal, Protocol, Self

from pydantic import ConfigDict, Field, StrictInt, model_validator

from core.advisory.models import CATALOG, Interval, MarketSnapshot, Strict, UTCDateTime


class MarketDataQuery(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    instrument_id: str
    interval: Interval
    as_of: UTCDateTime
    contract: str | None = None
    max_bars: StrictInt = Field(default=500, ge=1, le=500)

    @model_validator(mode="after")
    def identity(self) -> Self:
        instrument = CATALOG.get(self.instrument_id)
        if instrument is None:
            raise ValueError("Unknown instrument")
        if self.contract is not None and not instrument.valid_contract(self.contract):
            raise ValueError("Requested contract must match the instrument and month family")
        return self


class MarketDataProvider(Protocol):
    @property
    def mode(self) -> Literal["current", "replay"]: ...

    async def read(self, query: MarketDataQuery) -> MarketSnapshot | None:
        """Return real source data or None; never fabricate a missing market."""
        ...


def bounded_snapshot(value: MarketSnapshot | None, query: MarketDataQuery) -> MarketSnapshot | None:
    """Revalidate source data and include only candles completed by the cut."""
    query = MarketDataQuery.model_validate(query.model_dump())
    if value is None:
        return None
    value = MarketSnapshot.model_validate(value.model_dump())
    if value.instrument_id != query.instrument_id or value.interval != query.interval:
        raise ValueError("Provider market identity/interval mismatch")
    if query.contract is not None and value.contract != query.contract:
        raise ValueError("Provider returned a different dated contract")
    bars = [bar for bar in value.candles if bar.close_time <= query.as_of]
    if not bars:
        return None
    quality = value.quality
    if quality is not None and quality.sequences is not None:
        if len(quality.sequences) != len(value.candles):
            raise ValueError("Source sequences must align with all source candles")
        sequences = tuple(
            sequence
            for bar, sequence in zip(value.candles, quality.sequences, strict=True)
            if bar.close_time <= query.as_of
        )[-query.max_bars :]
        quality = quality.model_copy(update={"sequences": sequences})
    return MarketSnapshot.model_validate(
        value.model_dump()
        | {
            "candles": [bar.model_dump() for bar in bars[-query.max_bars :]],
            "quality": quality.model_dump() if quality is not None else None,
        }
    )
