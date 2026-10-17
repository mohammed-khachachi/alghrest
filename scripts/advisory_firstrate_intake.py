"""Read-only FirstRateData dated MES/MNQ minute CSV inspection.

Compose closed five-minute research candles only; no settings, stores or network.
Run with PYTHONPATH=src: python -m scripts.advisory_firstrate_intake --help
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import deque
from datetime import UTC, datetime, timedelta
from decimal import Decimal, DecimalException, localcontext
from pathlib import Path
from typing import Any, Literal, NoReturn
from zoneinfo import ZoneInfo

from pydantic import HttpUrl

from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.health import assess_market_data
from core.advisory.models import CATALOG, Candle, MarketSnapshot, utc_instant
from scripts.advisory_intake import _clock, inspect_snapshot

MAX_CSV_BYTES = 30_000_000
MAX_SOURCE_ROWS = 500_000
_MINUTE = timedelta(minutes=1)
_BUCKET = timedelta(minutes=5)
_EASTERN = ZoneInfo("America/New_York")


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Accidentally supplied credentials and file names must not be echoed.
        super().error("Invalid arguments; use --help for the required offline inputs")


def _identity(source_name: str, query: MarketDataQuery, source_timezone: str) -> None:
    match = re.fullmatch(r"(MES|MNQ)_([HMUZ])([0-9]{2}|[0-9]{4})_1min\.csv", source_name)
    if (
        match is None
        or query.instrument_id not in {"MES", "MNQ"}
        or query.contract is None
        or query.interval != "5m"
        or source_timezone != "America/New_York"
    ):
        raise ValueError("Require a declared individual-contract minute CSV and Eastern starts")
    root, month, suffix = match.groups()
    year = int(suffix) + (2000 if len(suffix) == 2 else 0)
    if (
        root != query.instrument_id
        or not 2000 <= year <= 2099
        or query.contract not in {f"{root}{month}{year}", f"{root}{month}{year % 100:02d}"}
    ):
        raise ValueError("Requested contract does not match the declared source")


def _opened(text: str) -> datetime:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:00", text):
        raise ValueError("Require a native minute start")
    naive = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
    candidates = {
        instant
        for fold in (0, 1)
        if (instant := naive.replace(tzinfo=_EASTERN, fold=fold).astimezone(UTC))
        .astimezone(_EASTERN)
        .replace(tzinfo=None)
        == naive
    }
    if len(candidates) != 1:
        raise ValueError("Ambiguous or nonexistent Eastern minute")
    return candidates.pop()


def _number(text: str) -> Decimal:
    # Bound both precision and exponent before any arithmetic. No float coercion.
    if len(text) > 32 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
        raise ValueError("Invalid finite decimal field")
    return Decimal(text)


def _normalize(
    payload: bytes,
    query: MarketDataQuery,
    *,
    source_name: str,
    source_timezone: str,
    fetched_at: datetime,
) -> tuple[MarketSnapshot | None, dict[str, Any]]:
    _identity(source_name, query, source_timezone)
    if not payload or len(payload) > MAX_CSV_BYTES:
        raise ValueError("Empty or oversized source")
    rows = csv.reader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
    counts = {
        "source_rows": 0,
        "observed_buckets": 0,
        "incomplete_buckets": 0,
        "incomplete_source_rows": 0,
        "complete_buckets": 0,
        "complete_after_query_cut": 0,
        "eligible_closed_buckets": 0,
        "selected_buckets": 0,
        "excluded_by_bar_limit": 0,
        "native_gap_intervals": 0,
        "maximum_native_gap_seconds": 0,
    }
    selected: deque[Candle] = deque(maxlen=query.max_bars)
    bucket_start: datetime | None = None
    bucket: list[Candle] = []
    first: datetime | None = None
    last: datetime | None = None

    def flush() -> None:
        if not bucket or bucket_start is None:
            return
        counts["observed_buckets"] += 1
        if len(bucket) != 5 or any(
            bar.open_time != bucket_start + i * _MINUTE for i, bar in enumerate(bucket)
        ):
            counts["incomplete_buckets"] += 1
            counts["incomplete_source_rows"] += len(bucket)
            return
        counts["complete_buckets"] += 1
        # Test true completion BEFORE converting to the model's inclusive end.
        end = bucket_start + _BUCKET
        if end > query.as_of:
            counts["complete_after_query_cut"] += 1
            return
        counts["eligible_closed_buckets"] += 1
        selected.append(
            Candle(
                open_time=bucket_start,
                close_time=end - timedelta(microseconds=1),
                open=bucket[0].open,
                high=max(bar.high for bar in bucket),
                low=min(bar.low for bar in bucket),
                close=bucket[-1].close,
                volume=sum((bar.volume for bar in bucket), Decimal(0)),
            )
        )

    # At most 32-character decimals and 500k rows; precision 96 preserves sums
    # and tick checks independently of the caller's Decimal context.
    with localcontext() as context:
        context.prec = 96
        for row in rows:
            counts["source_rows"] += 1
            if counts["source_rows"] > MAX_SOURCE_ROWS or len(row) != 6:
                raise ValueError("Invalid column count or row limit")
            opened = _opened(row[0])
            prices = [_number(text) for text in row[1:5]]
            volume = _number(row[5])
            if (
                opened + _MINUTE > fetched_at
                or (last is not None and opened <= last)
                or any(
                    price <= 0 or price % CATALOG[query.instrument_id].tick_size for price in prices
                )
                or volume != volume.to_integral_value()
            ):
                raise ValueError("Invalid chronology, completion, tick or volume")
            bar = Candle(
                open_time=opened,
                close_time=opened + _MINUTE - timedelta(microseconds=1),
                open=prices[0],
                high=prices[1],
                low=prices[2],
                close=prices[3],
                volume=volume,
            )
            if last is not None:
                gap = int((opened - last).total_seconds())
                if gap > 60:
                    counts["native_gap_intervals"] += 1
                    counts["maximum_native_gap_seconds"] = max(
                        counts["maximum_native_gap_seconds"], gap
                    )
            first = first or opened
            last = opened
            start = opened.replace(minute=opened.minute // 5 * 5, second=0, microsecond=0)
            if bucket_start is not None and start != bucket_start:
                flush()
                bucket = []
            bucket_start = start
            bucket.append(bar)
        flush()
    counts["selected_buckets"] = len(selected)
    counts["excluded_by_bar_limit"] = counts["eligible_closed_buckets"] - len(selected)
    details: dict[str, Any] = {
        "counts": counts,
        "first_native_open_utc": first.isoformat() if first else None,
        "last_native_open_utc": last.isoformat() if last else None,
    }
    if not selected:
        return None, details
    return (
        MarketSnapshot(
            instrument_id=query.instrument_id,
            interval=query.interval,
            contract=query.contract,
            source=HttpUrl(f"https://firstratedata.com/i/futures/{query.instrument_id}"),
            fetched_at=fetched_at,
            candles=list(selected),
            data_mode="user_import",
            quality=None,
        ),
        details,
    )


def inspect_firstrate(
    payload: bytes,
    query: MarketDataQuery,
    *,
    source_name: str,
    source_timezone: str,
    fetched_at: datetime,
    origin: Literal["synthetic", "unverified"] = "unverified",
) -> dict[str, Any]:
    """Inspect all source rows, select closed buckets, and preserve abstention.

    Filename, timezone and receipt time are reported inputs, not authenticated
    contract metadata or a permission grant. Caller must keep raw data private.
    """
    query = MarketDataQuery.model_validate(query.model_dump())
    fetched_at = utc_instant(fetched_at)
    if origin not in {"synthetic", "unverified"}:
        raise ValueError("Origin must be synthetic or unverified")
    result = inspect_snapshot(b"{}", query, origin=origin)
    result["input_sha256"] = None
    adapter: dict[str, Any] = {
        "version": "firstrate-offline-v1",
        "normalization": "INVALID",
        "csv_sha256": (
            hashlib.sha256(payload).hexdigest() if len(payload) <= MAX_CSV_BYTES else None
        ),
        "native_interval": "1min",
        "composed_interval": "5m",
        "source_timezone": "America/New_York",
        "reported_fetched_at": fetched_at.isoformat(),
        "counts": None,
        "source_authenticity": "NOT_ESTABLISHED",
        "contract_session_expiry": "NOT_VERIFIED",
        "storage_replay_permission": "NOT_ESTABLISHED_BY_CONVERSION",
        "gap_interpretation": "Unclassified; no calendar or missing trades inferred",
    }
    result["firstrate_adapter"] = adapter
    result["normalized_snapshot"] = None
    try:
        snapshot, details = _normalize(
            payload,
            query,
            source_name=source_name,
            source_timezone=source_timezone,
            fetched_at=fetched_at,
        )
    except (ValueError, TypeError, OverflowError, DecimalException, csv.Error):
        result["input_reasons"] = ["invalid_csv_identity_time_rows_or_limits"]
        return result
    adapter.update(details)
    adapter["normalization"] = "VALID" if snapshot is not None else "EMPTY"
    if snapshot is None:
        result["input_status"] = "VALID"
        result["input_reasons"] = []
        result["data_health"] = assess_market_data(
            None, query.instrument_id, query.interval, now=query.as_of
        ).model_dump(mode="json")
        return result
    # Only the already time-bounded, maximum-500-bar window is serialized.
    bounded = bounded_snapshot(snapshot, query)
    assert bounded is not None
    with localcontext() as context:
        context.prec = 96
        preflight = inspect_snapshot(bounded.model_dump_json().encode(), query, origin=origin)
    preflight["firstrate_adapter"] = adapter
    preflight["normalized_snapshot"] = bounded.model_dump(mode="json")
    return preflight


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument(
        "csv", type=Path, help="Existing ROOT_H26_1min.csv individual-contract file"
    )
    parser.add_argument("--instrument", required=True, choices=("MES", "MNQ"))
    parser.add_argument("--contract", required=True, help="Explicit two/four-digit-year contract")
    parser.add_argument("--source-timezone", required=True, choices=("America/New_York",))
    parser.add_argument("--fetched-at", required=True, type=_clock, help="Actual receipt timestamp")
    parser.add_argument("--as-of", required=True, type=_clock, help="Explicit research cut")
    parser.add_argument("--max-bars", type=int, default=500)
    parser.add_argument("--origin", choices=("synthetic", "unverified"), default="unverified")
    args = parser.parse_args(argv)
    try:
        query = MarketDataQuery(
            instrument_id=args.instrument,
            contract=args.contract,
            interval="5m",
            as_of=args.as_of,
            max_bars=args.max_bars,
        )
        if args.csv.is_symlink() or not args.csv.is_file():
            raise ValueError("Require a regular source file")
        with args.csv.open("rb") as handle:
            payload = handle.read(MAX_CSV_BYTES + 1)
    except (OSError, ValueError):
        parser.error("Require a readable regular file and valid dated contract")
    result = inspect_firstrate(
        payload,
        query,
        source_name=args.csv.name,
        source_timezone=args.source_timezone,
        fetched_at=args.fetched_at,
        origin=args.origin,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    # Missing source-quality evidence is intentional: conversion grants nothing.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
