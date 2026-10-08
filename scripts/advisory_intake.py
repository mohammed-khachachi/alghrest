"""Read-only MES/MNQ snapshot preflight; no store, provider login or trading IO.

Run with PYTHONPATH=src: python -m scripts.advisory_intake --help
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.health import assess_market_data
from core.advisory.models import INTERVAL_SECONDS, MarketSnapshot, utc_instant

MAX_INPUT_BYTES = 500_000


def inspect_snapshot(
    payload: bytes,
    query: MarketDataQuery,
    *,
    origin: Literal["synthetic", "unverified"] = "unverified",
) -> dict[str, Any]:
    """Inspect a declared snapshot, without promoting provenance or permissions.

    An explicit clock and requested dated contract prevent automatic roll/clock
    assumptions. HEALTHY remains the existing closed-bar research assessment.
    """
    query = MarketDataQuery.model_validate(query.model_dump())
    if query.instrument_id not in {"MES", "MNQ"} or query.contract is None:
        raise ValueError("Intake requires MES/MNQ and an explicit dated contract")
    if origin not in {"synthetic", "unverified"}:
        raise ValueError("Origin must be synthetic or unverified")
    result: dict[str, Any] = {
        "schema_version": "offline-intake-v1",
        "scope": "snapshot_preflight_only",
        "input_sha256": hashlib.sha256(payload).hexdigest(),
        "query": query.model_dump(mode="json"),
        "declared_origin": origin,
        "evidence_label": (
            "SYNTHETIC MECHANICS ONLY" if origin == "synthetic" else "UNVERIFIED INPUT"
        ),
        "input_status": "INVALID",
        "input_reasons": [],
        "data_health": None,
        "counts": {"input_bars": 0, "reviewed_bars": 0, "excluded_bars": 0},
        "market_data_access": "NOT_ESTABLISHED",
        "evaluation_rule_verification": "INCOMPLETE",
        "target_program": "TCP50",
        "tcp50_allowance": "BLOCKED",
        "strategy_validation": "NOT_ASSESSED",
        "costs_and_slippage": "NOT_ASSESSED",
        "live_advisory_readiness": "CANNOT_ASSESS",
        "passing_probability": "UNKNOWN",
        "decision": "ABSTAIN",
        "trade_permitted": False,
        "execution_enabled": False,
        "limitations": [
            "Reported source facts do not establish licensing or authenticity.",
            "A snapshot does not verify exchange sessions, listing, expiry or rolls.",
            "No account, evaluation rules, costs, strategy edge or live feed is qualified.",
            "Historical cuts inspect candles only; current context is not replay evidence.",
        ],
    }
    if len(payload) > MAX_INPUT_BYTES:
        result["input_reasons"] = ["input_too_large"]
        return result
    try:
        # Reject ambiguous JSON instead of silently accepting the last repeated key.
        raw = json.loads(payload, object_pairs_hook=_unique_keys)
        snapshot = MarketSnapshot.model_validate(raw)
        bounded = bounded_snapshot(snapshot, query)
    except (ValueError, TypeError, RecursionError):
        # Validation exceptions can contain raw source rows or credentials.
        result["input_reasons"] = ["invalid_snapshot_or_requested_identity"]
        return result
    reviewed = len(bounded.candles) if bounded is not None else 0
    result["input_status"] = "VALID"
    result["counts"] = {
        "input_bars": len(snapshot.candles),
        "reviewed_bars": reviewed,
        "excluded_bars": len(snapshot.candles) - reviewed,
    }
    result["data_health"] = assess_market_data(
        bounded, query.instrument_id, query.interval, now=query.as_of
    ).model_dump(mode="json")
    return result


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def _clock(value: str) -> datetime:
    try:
        return utc_instant(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "as-of requires an ISO timestamp with UTC offset"
        ) from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Existing MarketSnapshot JSON; read only")
    parser.add_argument("--instrument", required=True, choices=("MES", "MNQ"))
    parser.add_argument("--contract", required=True, help="Explicit dated contract, e.g. MNQZ26")
    parser.add_argument("--interval", required=True, choices=tuple(INTERVAL_SECONDS))
    parser.add_argument("--as-of", required=True, type=_clock, help="Explicit assessment clock")
    parser.add_argument("--origin", choices=("synthetic", "unverified"), default="unverified")
    args = parser.parse_args(argv)
    try:
        query = MarketDataQuery(
            instrument_id=args.instrument,
            interval=args.interval,
            contract=args.contract,
            as_of=args.as_of,
        )
    except ValueError:
        parser.error("Invalid requested contract or market identity")
    try:
        if not args.snapshot.is_file():
            parser.error("Snapshot must be an existing regular file")
        with args.snapshot.open("rb") as handle:
            payload = handle.read(MAX_INPUT_BYTES + 1)
    except OSError:
        parser.error("Snapshot cannot be read")
    result = inspect_snapshot(payload, query, origin=args.origin)
    # A truncated prefix is not an identity for the complete oversized file.
    if len(payload) > MAX_INPUT_BYTES:
        result["input_sha256"] = None
    print(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True))
    # Success certifies only a structurally valid, healthy closed-bar window.
    return 0 if result["data_health"] and result["data_health"]["state"] == "HEALTHY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
