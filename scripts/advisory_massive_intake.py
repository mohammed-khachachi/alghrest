"""Offline Massive futures JSON preflight; no credentials, network or storage IO.

Run with PYTHONPATH=src: python -m scripts.advisory_massive_intake --help
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Any, Literal, NoReturn

from pydantic import HttpUrl

from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.models import (
    CATALOG,
    INTERVAL_SECONDS,
    Candle,
    Interval,
    MarketSnapshot,
    utc_instant,
)
from scripts.advisory_intake import MAX_INPUT_BYTES, _clock, _unique_keys, inspect_snapshot

RESOLUTIONS: dict[str, Interval] = {
    "5min": "5m",
    "15min": "15m",
    "1hour": "1h",
    "4hour": "4h",
}
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MONTHS = {"H": 3, "M": 6, "U": 9, "Z": 12}


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        # Unknown options/choices may contain an accidentally supplied secret.
        super().error("Invalid arguments; use --help for the required offline inputs")


def _invalid_constant(value: str) -> None:
    raise ValueError("Non-finite JSON number")


def _response(payload: bytes) -> list[dict[str, Any]]:
    if len(payload) > MAX_INPUT_BYTES:
        raise ValueError("Input too large")
    raw = json.loads(
        payload,
        parse_float=Decimal,
        parse_constant=_invalid_constant,
        object_pairs_hook=_unique_keys,
    )
    if (
        not isinstance(raw, dict)
        or set(raw) - {"status", "request_id", "results", "next_url"}
        or raw.get("status") != "OK"
        or raw.get("next_url") is not None
    ):
        raise ValueError("Require a complete OK response")
    rows = raw.get("results")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 500:
        raise ValueError("Require 1 to 500 rows")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Invalid response row")
    return rows


def _date(value: Any) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("Require an explicit ISO date")
    return date.fromisoformat(value)


def _contract(metadata: dict[str, Any], query: MarketDataQuery) -> tuple[str, date]:
    root = query.instrument_id
    ticker = metadata.get("ticker")
    if not isinstance(ticker, str):
        raise ValueError("Require a dated provider ticker")
    match = re.fullmatch(root + r"([HMUZ])([0-9]{1}|[0-9]{2}|[0-9]{4})", ticker or "")
    if (
        match is None
        or metadata.get("product_code") != root
        or metadata.get("active") is not True
        or metadata.get("type") != "single"
        or metadata.get("trading_venue") != "XCME"
    ):
        raise ValueError("Require matching outright CME contract metadata")
    expiry = _date(metadata.get("settlement_date"))
    trading_day = _date(metadata.get("date"))
    first = _date(metadata.get("first_trade_date"))
    last = _date(metadata.get("last_trade_date"))
    month, suffix = match.groups()
    tick = metadata.get("trade_tick_size")
    if (
        expiry.month != _MONTHS[month]
        or not 2000 <= expiry.year <= 2099
        or suffix != str(expiry.year)[-len(suffix) :]
        or query.contract
        not in {root + month + str(expiry.year), root + month + str(expiry.year)[2:]}
        or not first <= trading_day <= last <= expiry
        or not isinstance(tick, int | Decimal)
        or isinstance(tick, bool)
        or Decimal(tick) != CATALOG[root].tick_size
    ):
        raise ValueError("Contract dates, year or tick size do not match")
    return ticker, trading_day


def normalize_massive(
    bars_payload: bytes,
    metadata_payload: bytes,
    query: MarketDataQuery,
    *,
    resolution: str,
    fetched_at: datetime,
) -> MarketSnapshot:
    """Map reported intraday bars; metadata resolves the year, not permission.

    Prices parse as Decimal and nanoseconds as integers. Sub-microsecond starts
    are rejected rather than rounded. Missing bars remain missing. No calendar,
    heartbeat, source-authentication claim or licensing grant is invented.
    """
    query = MarketDataQuery.model_validate(query.model_dump())
    fetched_at = utc_instant(fetched_at)
    if (
        query.instrument_id not in {"MES", "MNQ"}
        or query.contract is None
        or RESOLUTIONS.get(resolution) != query.interval
    ):
        raise ValueError("Require supported native intraday resolution and dated MES/MNQ")
    metadata = _response(metadata_payload)
    if len(metadata) != 1:
        raise ValueError("Require exactly one contract specification")
    ticker, trading_day = _contract(metadata[0], query)
    rows = _response(bars_payload)
    duration = timedelta(seconds=INTERVAL_SECONDS[query.interval])
    candles = []
    for row in rows:
        timestamp = row.get("window_start")
        if (
            row.get("ticker") != ticker
            or _date(row.get("session_end_date")) != trading_day
            or type(timestamp) is not int
            or timestamp < 0
            or timestamp % 1000
            or type(row.get("volume")) is not int
            or row["volume"] < 0
            or type(row.get("transactions")) is not int
            or row["transactions"] < 0
            or any(
                type(row.get(key)) not in {int, Decimal} for key in ("open", "high", "low", "close")
            )
        ):
            raise ValueError("Invalid bar identity, timestamp or numerical fields")
        opened = _EPOCH + timedelta(microseconds=timestamp // 1000)
        for key in ("open", "high", "low", "close"):
            try:
                Decimal(row[key]) % CATALOG[query.instrument_id].tick_size
            except DecimalException as error:
                raise ValueError(
                    "Price cannot be assessed exactly by the existing tick guard"
                ) from error
        # Existing candles use inclusive closes; require the full source interval
        # to have elapsed, including its final microsecond, before normalization.
        if opened + duration > fetched_at:
            raise ValueError("Unfinished source candle")
        if opened + duration - timedelta(microseconds=1) == query.as_of:
            raise ValueError("Source interval has not fully elapsed at the assessment cut")
        candles.append(
            Candle(
                open_time=opened,
                close_time=opened + duration - timedelta(microseconds=1),
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
            )
        )
    candles.sort(key=lambda candle: candle.open_time)
    return MarketSnapshot(
        instrument_id=query.instrument_id,
        interval=query.interval,
        contract=query.contract,
        source=HttpUrl(f"https://api.massive.com/futures/v1/aggs/{ticker}"),
        fetched_at=fetched_at,
        candles=candles,
        data_mode="user_import",
        quality=None,
    )


def inspect_massive(
    bars_payload: bytes,
    metadata_payload: bytes,
    query: MarketDataQuery,
    *,
    resolution: str,
    fetched_at: datetime,
    origin: Literal["synthetic", "unverified"] = "unverified",
) -> dict[str, Any]:
    """Reuse the existing preflight; successful conversion always abstains."""
    if origin not in {"synthetic", "unverified"}:
        raise ValueError("Origin must be synthetic or unverified")
    snapshot = None
    # Keep malformed source values out of exception output.
    with suppress(ValueError, TypeError, OverflowError, RecursionError):
        snapshot = normalize_massive(
            bars_payload, metadata_payload, query, resolution=resolution, fetched_at=fetched_at
        )
    payload = snapshot.model_dump_json().encode() if snapshot is not None else b"{}"
    result = inspect_snapshot(payload, query, origin=origin)
    result["massive_adapter"] = {
        "version": "massive-offline-v1",
        "resolution": resolution,
        "normalization": "VALID" if snapshot is not None else "INVALID",
        "bars_sha256": (
            hashlib.sha256(bars_payload).hexdigest()
            if len(bars_payload) <= MAX_INPUT_BYTES
            else None
        ),
        "metadata_sha256": (
            hashlib.sha256(metadata_payload).hexdigest()
            if len(metadata_payload) <= MAX_INPUT_BYTES
            else None
        ),
        "source_authenticity": "NOT_ESTABLISHED",
        "storage_replay_permission": "NOT_ESTABLISHED",
    }
    selected = bounded_snapshot(snapshot, query)
    result["normalized_snapshot"] = (
        selected.model_dump(mode="json") if selected is not None else None
    )
    if snapshot is None:
        result["input_sha256"] = None
    return result


def main(argv: list[str] | None = None) -> int:
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument("bars", type=Path, help="Existing aggregates response JSON")
    parser.add_argument("metadata", type=Path, help="Existing single-contract response JSON")
    parser.add_argument("--instrument", required=True, choices=("MES", "MNQ"))
    parser.add_argument("--contract", required=True, help="Explicit two/four-digit-year contract")
    parser.add_argument("--resolution", required=True, choices=tuple(RESOLUTIONS))
    parser.add_argument("--fetched-at", required=True, type=_clock)
    parser.add_argument("--as-of", required=True, type=_clock)
    parser.add_argument("--origin", choices=("synthetic", "unverified"), default="unverified")
    args = parser.parse_args(argv)
    try:
        query = MarketDataQuery(
            instrument_id=args.instrument,
            contract=args.contract,
            interval=RESOLUTIONS[args.resolution],
            as_of=args.as_of,
        )
        inputs = []
        for path in (args.bars, args.metadata):
            if not path.is_file():
                raise ValueError("Not a regular file")
            with path.open("rb") as handle:
                inputs.append(handle.read(MAX_INPUT_BYTES + 1))
    except (OSError, ValueError):
        parser.error("Require readable regular files and a valid dated contract")
    result = inspect_massive(
        inputs[0],
        inputs[1],
        query,
        resolution=args.resolution,
        fetched_at=args.fetched_at,
        origin=args.origin,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["data_health"] and result["data_health"]["state"] == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
