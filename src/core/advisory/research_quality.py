"""Observed candle integrity and bounded indicator eligibility, without a market calendar."""

from datetime import datetime
from itertools import pairwise
from typing import Literal, Self

from pydantic import ConfigDict, Field, model_validator

from core.advisory.models import Strict

QualityReason = Literal[
    "history_unavailable",
    "invalid_response",
    "invalid_metadata",
    "no_candles",
    "invalid_candles",
    "invalid_timestamps",
    "duplicate_timestamps",
    "out_of_order_timestamps",
    "future_timestamps",
    "inconsistent_fetch_time",
    "missing_intervals",
    "irregular_intervals",
    "stale_cache",
    "provider_unverified",
    "interval_unverified",
    "session_calendar_unverified",
    "calendar_interval_unverified",
    "insufficient_samples",
]


class ConclusionQuality(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    allowed: bool
    reasons: tuple[QualityReason, ...] = ()

    @model_validator(mode="after")
    def eligibility(self) -> Self:
        if self.allowed != (not self.reasons):
            raise ValueError("Conclusion eligibility requires its reasons")
        return self


class CandleQuality(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["candle-quality-v1"] = "candle-quality-v1"
    status: Literal["usable", "limited", "unavailable"]
    # None means unobserved, not a claim of zero defects.
    received_candles: int | None = Field(default=None, ge=0, le=256000)
    invalid_candles: int | None = Field(default=None, ge=0, le=2000)
    invalid_timestamps: int | None = Field(default=None, ge=0, le=2000)
    duplicate_timestamps: int | None = Field(default=None, ge=0, le=2000)
    out_of_order_pairs: int | None = Field(default=None, ge=0, le=2000)
    future_timestamps: int | None = Field(default=None, ge=0, le=2000)
    interval_seconds: int | None = Field(default=None, gt=0)
    gap_count: int | None = Field(default=None, ge=0, le=2000)
    missing_intervals: int | None = Field(default=None, ge=0)
    irregular_intervals: int | None = Field(default=None, ge=0, le=2000)
    largest_gap_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    continuity_basis: Literal["continuous", "session_unverified", "unverified"] = "unverified"
    reasons: tuple[QualityReason, ...]
    trend: ConclusionQuality
    momentum: ConclusionQuality
    volatility: ConclusionQuality

    @model_validator(mode="after")
    def consistency(self) -> Self:
        conclusions = (self.trend, self.momentum, self.volatility)
        if (self.status == "usable") != (not self.reasons):
            raise ValueError("Quality status requires its reasons")
        if self.status == "usable" and not all(c.allowed for c in conclusions):
            raise ValueError("Usable quality cannot have blocked conclusions")
        if self.status == "unavailable" and any(c.allowed for c in conclusions):
            raise ValueError("Unavailable quality cannot allow conclusions")
        if self.status != "unavailable":
            if self.received_candles is None or self.received_candles < 1:
                raise ValueError("Available quality requires an observed candle count")
            if (self.received_candles < 50 and self.trend.allowed) or (
                self.received_candles < 15 and (self.momentum.allowed or self.volatility.allowed)
            ):
                raise ValueError("Conclusion eligibility requires enough samples")
        if self.status == "usable" and self.continuity_basis != "continuous":
            raise ValueError("Unverified continuity must remain limited")
        if any(reason not in self.reasons for c in conclusions for reason in c.reasons):
            raise ValueError("Conclusion reasons must appear in the quality assessment")
        for count, reason in (
            (self.invalid_candles, "invalid_candles"),
            (self.invalid_timestamps, "invalid_timestamps"),
            (self.duplicate_timestamps, "duplicate_timestamps"),
            (self.out_of_order_pairs, "out_of_order_timestamps"),
            (self.future_timestamps, "future_timestamps"),
        ):
            if count and (reason not in self.reasons or self.status != "unavailable"):
                raise ValueError("Integrity defects must block the series")
        if "stale_cache" in self.reasons and any(c.allowed for c in conclusions):
            raise ValueError("Stale cache cannot allow current conclusions")
        return self


FIXED_INTERVALS = {
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
    "1wk": 604800,
    "1w": 604800,
}


def unavailable_quality(reason: QualityReason, count: int | None = None) -> CandleQuality:
    blocked = ConclusionQuality(allowed=False, reasons=(reason,))
    return CandleQuality(
        status="unavailable",
        received_candles=count,
        reasons=(reason,),
        trend=blocked,
        momentum=blocked,
        volatility=blocked,
    )


def assess_candle_quality(
    times: tuple[datetime | None, ...],
    now: datetime,
    *,
    invalid_candles: int = 0,
    provider: str | None = None,
    interval: str | None = None,
    fetched_at: datetime | None = None,
    cache_state: str | None = None,
) -> CandleQuality:
    """Never sort, deduplicate, interpolate or infer frequency from returned spacing.

    Only Binance's explicitly declared fixed intervals are treated as a continuous
    grid. Session-based sources need a calendar before gaps can mean missing bars.
    Each conclusion depends on its own trailing 50/15-candle window.
    """
    if not times:
        return unavailable_quality("no_candles", 0)
    known = [t for t in times if t is not None]
    duplicate = len(known) - len(set(known))
    reversed_pairs = sum(a > b for a, b in pairwise(times) if a is not None and b is not None)
    future = sum(t > now for t in known)
    invalid_times = len(times) - len(known)
    reasons: list[QualityReason] = []
    defects: list[tuple[int, QualityReason]] = [
        (invalid_candles, "invalid_candles"),
        (invalid_times, "invalid_timestamps"),
        (duplicate, "duplicate_timestamps"),
        (reversed_pairs, "out_of_order_timestamps"),
        (future, "future_timestamps"),
    ]
    for count, reason in defects:
        if count:
            reasons.append(reason)
    if fetched_at and (fetched_at > now or any(t > fetched_at for t in known)):
        reasons.append("inconsistent_fetch_time")
    structural = tuple(reasons)
    seconds = FIXED_INTERVALS.get(interval or "")
    continuous = provider == "binance" and seconds is not None
    deltas = [
        (b - a).total_seconds() if a is not None and b is not None else None
        for a, b in pairwise(times)
    ]
    gap_count = sum(d > seconds for d in deltas if d is not None) if seconds else None
    missing = (
        sum(max(0, int(d // seconds) - 1) for d in deltas if d and d > 0)
        if continuous and seconds
        else None
    )
    irregular = (
        sum(d % seconds != 0 for d in deltas if d and d > 0) if continuous and seconds else None
    )
    if missing:
        reasons.append("missing_intervals")
    if irregular:
        reasons.append("irregular_intervals")
    if not provider:
        reasons.append("provider_unverified")
    if interval in {None, "UNVERIFIED"}:
        reasons.append("interval_unverified")
    elif seconds is None:
        reasons.append("calendar_interval_unverified")
    if not continuous:
        reasons.append("session_calendar_unverified")
    if cache_state == "stale":
        reasons.append("stale_cache")

    def conclusion(required: int) -> ConclusionQuality:
        blocked = list(structural)
        if len(times) < required:
            blocked.append("insufficient_samples")
        if cache_state == "stale":
            blocked.append("stale_cache")
        if continuous and seconds:
            window = deltas[-(required - 1) :]
            if any(d is not None and d >= 2 * seconds for d in window):
                blocked.append("missing_intervals")
            if any(d is not None and d > 0 and d % seconds != 0 for d in window):
                blocked.append("irregular_intervals")
        return ConclusionQuality(allowed=not blocked, reasons=tuple(blocked))

    trend, momentum, volatility = conclusion(50), conclusion(15), conclusion(15)
    if any("insufficient_samples" in c.reasons for c in (trend, momentum, volatility)):
        reasons.append("insufficient_samples")
    return CandleQuality(
        status="unavailable" if structural else "limited" if reasons else "usable",
        received_candles=len(times),
        invalid_candles=invalid_candles,
        invalid_timestamps=invalid_times,
        duplicate_timestamps=duplicate,
        out_of_order_pairs=reversed_pairs,
        future_timestamps=future,
        interval_seconds=seconds,
        gap_count=gap_count,
        missing_intervals=missing,
        irregular_intervals=irregular,
        largest_gap_seconds=max((d for d in deltas if d is not None and d >= 0), default=None),
        continuity_basis=(
            "continuous" if continuous else "session_unverified" if provider else "unverified"
        ),
        reasons=tuple(reasons),
        trend=trend,
        momentum=momentum,
        volatility=volatility,
    )
