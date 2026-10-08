"""Archived candles through the current market-snapshot contract; no live IO."""

from bisect import bisect_right
from collections.abc import Iterable
from datetime import datetime
from typing import Literal

from pydantic import HttpUrl

from core.advisory.data import MarketDataQuery
from core.advisory.models import (
    CATALOG,
    INTERVAL_SECONDS,
    Candle,
    EconomicCalendar,
    Interval,
    MarketDataEvidence,
    MarketSnapshot,
    utc_instant,
)
from core.advisory.selection import CandidateEvidence

StreamKey = tuple[str, Interval, str | None]


class ReplayProvider:
    mode: Literal["replay"] = "replay"

    def __init__(
        self,
        records: Iterable[MarketSnapshot],
        *,
        calendars: Iterable[EconomicCalendar] = (),
        research: Iterable[CandidateEvidence] = (),
    ) -> None:
        bars: dict[StreamKey, list[str]] = {}
        times: dict[StreamKey, list[datetime]] = {}
        sources: dict[StreamKey, HttpUrl] = {}
        quality: dict[StreamKey, list[str | None]] = {}
        for record in records:
            record = MarketSnapshot.model_validate(record.model_dump())
            key = (record.instrument_id, record.interval, record.contract)
            if key in sources and sources[key] != record.source:
                raise ValueError("Replay stream cannot combine disagreeing sources")
            sources[key] = record.source
            stream, clock = bars.setdefault(key, []), times.setdefault(key, [])
            evidence = record.quality
            if (
                evidence is not None
                and evidence.sequences is not None
                and len(evidence.sequences) != len(record.candles)
            ):
                raise ValueError("Replay sequences must align with the recorded candles")
            for index, bar in enumerate(record.candles):
                if clock and bar.open_time <= clock[-1]:
                    raise ValueError("Replay bars must be ordered without duplicates or overlap")
                stream.append(bar.model_dump_json())
                clock.append(bar.close_time)
                row = evidence
                if row is not None:
                    updates: dict[str, object] = {}
                    if row.sequences is not None:
                        updates["sequences"] = (row.sequences[index],)
                    # Only closed-bar evidence can be projected to a virtual
                    # archive clock. Captured quotes need timestamped history.
                    if (
                        row.quote is not None
                        or row.reference_quote is not None
                        or row.heartbeat_at is not None
                        and not (
                            0
                            <= (record.fetched_at - row.heartbeat_at).total_seconds()
                            <= INTERVAL_SECONDS[record.interval] * 2 + 60
                        )
                    ):
                        updates.update(
                            provider_state=(
                                row.provider_state
                                if row.provider_state in {"degraded", "disconnected"}
                                else "unknown"
                            ),
                            heartbeat_at=None,
                        )
                    row = row.model_copy(update=updates)
                quality.setdefault(key, []).append(
                    row.model_dump_json() if row is not None else None
                )
        # Serialized bars detach replay evidence from callers' mutable models.
        self._bars = {key: tuple(value) for key, value in bars.items()}
        self._times = {key: tuple(value) for key, value in times.items()}
        self._sources = sources
        self._quality = {key: tuple(value) for key, value in quality.items()}
        revisions: list[EconomicCalendar] = []
        identities: set[tuple[str, str]] = set()
        for calendar in calendars:
            calendar = EconomicCalendar.model_validate(calendar.model_dump())
            identity = (calendar.id, calendar.version)
            if identity in identities:
                raise ValueError("Duplicate archived calendar revision")
            if any(
                row.observed_at == calendar.observed_at
                and set(row.covered_markets) & set(calendar.covered_markets)
                for row in revisions
            ):
                raise ValueError("Ambiguous archived calendar cut")
            identities.add(identity)
            revisions.append(calendar)
        self._calendars = tuple(
            row.model_dump_json() for row in sorted(revisions, key=lambda row: row.observed_at)
        )
        candidates = []
        revisions_seen: set[tuple[str, str]] = set()
        cuts_seen: set[tuple[str, datetime]] = set()
        for candidate in research:
            candidate = CandidateEvidence.model_validate(candidate.model_dump())
            identity = (candidate.id, candidate.version)
            cut = (candidate.instrument_id, candidate.available_at)
            if identity in revisions_seen or cut in cuts_seen:
                raise ValueError("Duplicate or ambiguous archived research revision")
            revisions_seen.add(identity)
            cuts_seen.add(cut)
            candidates.append(candidate)
        self._research = tuple(
            row.model_dump_json() for row in sorted(candidates, key=lambda row: row.available_at)
        )

    def research(self, instrument_id: str, as_of: datetime) -> CandidateEvidence | None:
        as_of = utc_instant(as_of)
        if instrument_id not in CATALOG:
            raise ValueError("Unknown research market")
        for record in reversed(self._research):
            value = CandidateEvidence.model_validate_json(record)
            if value.instrument_id == instrument_id and value.available_at <= as_of:
                return value
        return None

    def calendar(self, instrument_id: str, as_of: datetime) -> EconomicCalendar | None:
        """Latest reported revision known at this cut; never today's release schedule."""
        as_of = utc_instant(as_of)
        if instrument_id not in CATALOG:
            raise ValueError("Unknown event-calendar market")
        for record in reversed(self._calendars):
            row = EconomicCalendar.model_validate_json(record)
            if row.observed_at <= as_of and instrument_id in row.covered_markets:
                return row
        return None

    async def read(self, query: MarketDataQuery) -> MarketSnapshot | None:
        query = MarketDataQuery.model_validate(query.model_dump())
        keys = [
            key
            for key in self._bars
            if key[:2] == (query.instrument_id, query.interval)
            and (query.contract is None or key[2] == query.contract)
            and self._times[key][0] <= query.as_of
        ]
        if not keys:
            return None
        if len(keys) != 1:
            raise ValueError("Replay requires a pinned contract when dated streams overlap")
        key = keys[0]
        end = bisect_right(self._times[key], query.as_of)
        start = max(0, end - query.max_bars)
        candles = [Candle.model_validate_json(row) for row in self._bars[key][start:end]]
        return MarketSnapshot(
            instrument_id=query.instrument_id,
            interval=query.interval,
            contract=key[2],
            source=self._sources[key],
            fetched_at=query.as_of,
            candles=candles,
            data_mode="replay",
            quality=self._window_quality(key, start, end, query.as_of),
            # Current derivatives/free text can reveal information from after
            # the replay cut. Only archived candles enter this initial adapter.
            derivatives={},
            observations=["Historical candle replay; live derivatives/context excluded."],
        )

    def _window_quality(
        self, key: StreamKey, start: int, end: int, now: datetime
    ) -> MarketDataEvidence | None:
        rows = self._quality[key][start:end]
        if any(row is None for row in rows):
            return None
        evidence = [MarketDataEvidence.model_validate_json(row) for row in rows if row is not None]
        latest = evidence[-1]
        states = {row.provider_state for row in evidence}
        state = next(s for s in ("disconnected", "degraded", "unknown", "active") if s in states)
        modes = {row.sequence_mode for row in evidence}
        mode = modes.pop() if len(modes) == 1 else "unknown"
        if len({row.provider_id for row in evidence}) != 1:
            state = "unknown"
        # Archive reader heartbeat says nothing about real-time execution data.
        heartbeat = now if all(row.heartbeat_at is not None for row in evidence) else None
        sequences = (
            tuple(number for row in evidence for number in row.sequences or ())
            if any(row.sequences is not None for row in evidence)
            else None
        )
        return MarketDataEvidence.model_validate(
            latest.model_dump()
            | {
                "provider_state": state,
                "heartbeat_at": heartbeat,
                "sequence_mode": mode,
                "sequences": sequences,
            }
        )
