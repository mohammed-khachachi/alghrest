"""Development-only timestamp gate before any numeric parsing or normalization.

The normalizer is injected by the offline CLI: application packages never import
scripts. This module produces structural diagnostics, never signals or outcomes.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from pydantic import Field

from backtesting.mes5m_spec import Digest, ResearchModel, ResearchSpec, Safety
from core.advisory.data import MarketDataQuery
from core.advisory.models import Candle, MarketSnapshot, UTCDateTime, utc_instant

Origin = Literal["synthetic", "real_provider_sample"]
MINUTE = timedelta(minutes=1)
FIVE = timedelta(minutes=5)
EASTERN = ZoneInfo("America/New_York")


class FiveMinuteNormalizer(Protocol):
    def __call__(
        self,
        payload: bytes,
        query: MarketDataQuery,
        *,
        source_name: str,
        source_timezone: str,
        fetched_at: datetime,
    ) -> tuple[MarketSnapshot | None, dict[str, Any]]: ...


class MissingInterval(ResearchModel):
    start: UTCDateTime
    end_exclusive: UTCDateTime
    classification: Literal["UNCLASSIFIED_MISSING"] = "UNCLASSIFIED_MISSING"


class DevelopmentSlice(Safety):
    schema_version: Literal["mes5m-data-manifest-v1"] = "mes5m-data-manifest-v1"
    day: date
    as_of: UTCDateTime
    origin: Origin
    source_sha256: Digest
    selected_rows_sha256: Digest
    candidate_minutes: int = Field(ge=0, le=420, strict=True)
    observed_minutes: int = Field(ge=0, le=420, strict=True)
    unavailable_complete_5m_intervals: int = Field(ge=0, le=84, strict=True)
    missing_intervals: tuple[MissingInterval, ...]
    candles: tuple[Candle, ...]
    data_status: Literal["PARTIAL"] = "PARTIAL"
    calendar_status: Literal["PARTIAL"] = "PARTIAL"
    historical_signal_generation_authorized: Literal[False] = False
    performance_observation_valid: Literal[False] = False

    def summary(self) -> dict[str, Any]:
        result = self.model_dump(mode="json", exclude={"candles"})
        result["complete_5m_bars"] = len(self.candles)
        return result


def _timestamp(prefix: bytes) -> datetime:
    if not re.fullmatch(rb"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:00", prefix):
        raise ValueError("Invalid source minute timestamp")
    naive = datetime.strptime(prefix.decode("ascii"), "%Y-%m-%d %H:%M:%S")
    instants = {
        at
        for fold in (0, 1)
        if (at := naive.replace(tzinfo=EASTERN, fold=fold).astimezone(UTC))
        .astimezone(EASTERN)
        .replace(tzinfo=None)
        == naive
    }
    if len(instants) != 1:
        raise ValueError("Ambiguous or nonexistent source minute")
    return instants.pop()


def _cut(spec: ResearchSpec, day: date, as_of: datetime) -> datetime:
    spec.authorize_day(day)
    cut = utc_instant(as_of)
    if cut.date() != day or not time(7) <= cut.time() <= time(14):
        raise PermissionError("Cut must be inside the authorized DEVELOPMENT window")
    return cut


def _select(
    payload: bytes,
    *,
    cuts: dict[date, datetime],
    expected_sha256: str,
    origin: Origin,
    spec: ResearchSpec,
) -> dict[date, list[tuple[datetime, bytes]]]:
    # Authenticate declared scope before touching numeric fields anywhere.
    if origin not in {"synthetic", "real_provider_sample"}:
        raise ValueError("Unknown source origin")
    if origin == "real_provider_sample" and expected_sha256 != spec.source_csv_sha256:
        raise ValueError("Real source must match the preserved MES identity")
    if (
        not payload
        or len(payload) > 30_000_000
        or hashlib.sha256(payload).hexdigest() != expected_sha256
    ):
        raise ValueError("Source size or checksum mismatch")
    lines = payload.splitlines()
    if len(lines) > 500_000:
        raise ValueError("Source row bound exceeded")
    selected: dict[date, list[tuple[datetime, bytes]]] = {day: [] for day in cuts}
    previous = None
    for index, supplied in enumerate(lines):
        raw = supplied.removeprefix(b"\xef\xbb\xbf") if index == 0 else supplied
        # Only timestamp bytes are inspected until partition/window/cut filtering.
        prefix, _, _ = raw.partition(b",")
        opened = _timestamp(prefix)
        if previous is not None and opened <= previous:
            raise ValueError("Source timestamps must be unique and increasing")
        previous = opened
        cut = cuts.get(opened.date())
        if cut is not None and time(7) <= opened.time() < time(14) and opened + MINUTE <= cut:
            selected[opened.date()].append((opened, raw))
    return selected


def _slice(
    selected: list[tuple[datetime, bytes]],
    *,
    day: date,
    cut: datetime,
    source_hash: str,
    origin: Origin,
    spec: ResearchSpec,
    normalizer: FiveMinuteNormalizer,
) -> DevelopmentSlice:
    rows = b"\n".join(raw for _, raw in selected)
    snapshot = None
    if rows:
        snapshot, _ = normalizer(
            rows,
            MarketDataQuery(instrument_id="MES", interval="5m", contract="MESH26", as_of=cut),
            source_name=spec.source_name,
            source_timezone=spec.source_timezone,
            fetched_at=spec.source_acquired_at,
        )
    candles: tuple[Candle, ...] = ()
    if snapshot is not None:
        snapshot = MarketSnapshot.model_validate(snapshot.model_dump())
        if (snapshot.instrument_id, snapshot.interval, snapshot.contract) != (
            "MES",
            "5m",
            "MESH26",
        ):
            raise ValueError("Normalizer identity mismatch")
        candles = tuple(snapshot.candles)
        for candle in candles:
            if (
                candle.open_time.date() != day
                or not time(7) <= candle.open_time.time() < time(14)
                or candle.open_time + FIVE > cut
                or candle.close_time != candle.open_time + FIVE - timedelta(microseconds=1)
            ):
                raise ValueError("Normalizer escaped the authorized event-time cut")
    start = datetime.combine(day, time(7), UTC)
    candidate_minutes = int((cut - start).total_seconds() // 60)
    observed = {at for at, _ in selected}
    absent = [
        start + i * MINUTE for i in range(candidate_minutes) if start + i * MINUTE not in observed
    ]
    missing: list[MissingInterval] = []
    for at in absent:
        if missing and missing[-1].end_exclusive == at:
            missing[-1] = MissingInterval(start=missing[-1].start, end_exclusive=at + MINUTE)
        else:
            missing.append(MissingInterval(start=at, end_exclusive=at + MINUTE))
    return DevelopmentSlice(
        day=day,
        as_of=cut,
        origin=origin,
        source_sha256=source_hash,
        selected_rows_sha256=hashlib.sha256(rows).hexdigest(),
        candidate_minutes=candidate_minutes,
        observed_minutes=len(selected),
        unavailable_complete_5m_intervals=candidate_minutes // 5 - len(candles),
        missing_intervals=tuple(missing),
        candles=candles,
    )


def development_snapshot(
    payload: bytes,
    *,
    day: date,
    as_of: datetime,
    expected_sha256: str,
    normalizer: FiveMinuteNormalizer,
    origin: Origin,
    spec: ResearchSpec | None = None,
) -> DevelopmentSlice:
    frozen = ResearchSpec.model_validate((spec or ResearchSpec()).model_dump())
    cut = _cut(frozen, day, as_of)
    selected = _select(
        payload, cuts={day: cut}, expected_sha256=expected_sha256, origin=origin, spec=frozen
    )
    return _slice(
        selected[day],
        day=day,
        cut=cut,
        source_hash=expected_sha256,
        origin=origin,
        spec=frozen,
        normalizer=normalizer,
    )


def preflight_development(
    payload: bytes,
    *,
    expected_sha256: str,
    normalizer: FiveMinuteNormalizer,
    origin: Origin,
    spec: ResearchSpec | None = None,
) -> dict[str, Any]:
    frozen = ResearchSpec.model_validate((spec or ResearchSpec()).model_dump())
    cuts = {}
    day = frozen.partitions[0].start
    while day <= frozen.partitions[0].end:
        try:
            frozen.authorize_day(day)
        except PermissionError:
            pass
        else:
            cuts[day] = datetime.combine(day, time(14), UTC)
        day += timedelta(days=1)
    selected = _select(
        payload, cuts=cuts, expected_sha256=expected_sha256, origin=origin, spec=frozen
    )
    summaries = [
        _slice(
            selected[day],
            day=day,
            cut=cut,
            source_hash=expected_sha256,
            origin=origin,
            spec=frozen,
            normalizer=normalizer,
        ).summary()
        for day, cut in cuts.items()
    ]
    return {
        **Safety().model_dump(mode="json"),
        "schema_version": "mes5m-qualification-v1",
        "scope": "development_data_preflight_only",
        "status": "PARTIAL",
        "origin": origin,
        "specification_sha256": frozen.revision,
        "source_sha256": expected_sha256,
        "days": summaries,
        "candidate_dates": len(summaries),
        "observed_native_minutes": sum(row["observed_minutes"] for row in summaries),
        "complete_5m_bars": sum(row["complete_5m_bars"] for row in summaries),
        "missing_minutes": sum(
            row["candidate_minutes"] - row["observed_minutes"] for row in summaries
        ),
        "price_fields_parsed_outside_development": False,
        "validation_access": "DENIED",
        "holdout_access": "DENIED",
        "performance_evaluation_performed": False,
        "sample_sufficiency": "UNKNOWN",
        "limitations": [
            "unclassified_missing_minutes",
            "calendar_partial",
            "costs_assumed",
            "historical_publication_latency_unknown",
            "no_historical_strategy_run",
        ],
    }
