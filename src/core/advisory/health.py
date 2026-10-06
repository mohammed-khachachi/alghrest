"""Deterministic closed-bar guard. Unknown evidence never permits analysis."""

from datetime import datetime
from decimal import Decimal
from itertools import pairwise

from pydantic import ConfigDict, Field

from core.advisory.models import (
    CATALOG,
    INTERVAL_SECONDS,
    Interval,
    MarketDataHealth,
    MarketSnapshot,
    Number,
    PriceObservation,
    Strict,
    utc_instant,
)


class DataHealthPolicy(Strict):
    """Server-owned limits. No invented quote/spread/source-agreement defaults."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    max_quote_age_seconds: Number | None = Field(default=None, ge=0)
    max_spread_ticks: Number | None = Field(default=None, ge=0)
    max_source_deviation_ticks: Number | None = Field(default=None, ge=0)
    require_quote: bool = False
    require_reference: bool = False


def assess_market_data(
    value: MarketSnapshot | None,
    instrument_id: str,
    interval: Interval,
    *,
    now: datetime,
    policy: DataHealthPolicy = DataHealthPolicy(),
) -> MarketDataHealth:
    """Check reported facts; HEALTHY applies only to closed-bar research."""
    now = utc_instant(now)
    policy = DataHealthPolicy.model_validate(policy.model_dump())
    failures: list[str] = []
    unknown: list[str] = []
    diagnostics: dict[str, str] = {
        "policy_" + key: str(value) for key, value in policy.model_dump().items()
    }

    def result() -> MarketDataHealth:
        return MarketDataHealth(
            state="UNHEALTHY" if failures else "UNKNOWN" if unknown else "HEALTHY",
            assessed_at=now,
            reasons=tuple(dict.fromkeys(failures + unknown)),
            diagnostics=diagnostics,
        )

    if value is None:
        unknown.append("missing_market")
        return result()
    try:
        value = MarketSnapshot.model_validate(value.model_dump())
    except (ValueError, TypeError):
        failures.append("invalid_market_structure")
        return result()
    if value.instrument_id != instrument_id or value.interval != interval:
        failures.append("market_identity_mismatch")
        return result()
    instrument = CATALOG[instrument_id]
    bars = value.candles
    budget = INTERVAL_SECONDS[interval] * 2 + 60  # Existing research freshness budget.
    for name, timestamp in (("bar", bars[-1].close_time), ("capture", value.fetched_at)):
        age = (now - timestamp).total_seconds()
        diagnostics[f"{name}_age_seconds"] = str(age)
        if age < 0:
            failures.append(f"future_{name}")
        elif age > budget:
            failures.append(f"stale_{name}")
    gaps = sum(
        abs((b.open_time - a.open_time).total_seconds() - INTERVAL_SECONDS[interval]) > 1
        for a, b in pairwise(bars)
    )
    diagnostics["cadence_gaps"] = str(gaps)
    if gaps:
        if instrument.market == "cme_future":
            unknown.append("unverified_session_gap")
        else:
            failures.append("missing_or_irregular_bars")
    if instrument.market == "cme_future" and any(
        price % instrument.tick_size
        for bar in bars
        for price in (bar.open, bar.high, bar.low, bar.close)
    ):
        failures.append("off_tick_bar")
    evidence = value.quality
    if evidence is None:
        unknown.append("missing_quality_evidence")
        return result()
    diagnostics["provider_id"] = evidence.provider_id
    if evidence.provider_state in {"disconnected", "degraded"}:
        failures.append("provider_" + evidence.provider_state)
    elif evidence.provider_state == "unknown":
        unknown.append("unknown_provider_state")
    if evidence.heartbeat_at is None:
        unknown.append("missing_provider_heartbeat")
    else:
        age = (now - evidence.heartbeat_at).total_seconds()
        diagnostics["heartbeat_age_seconds"] = str(age)
        if age < 0:
            failures.append("future_provider_heartbeat")
        elif age > budget:
            failures.append("stale_provider_heartbeat")
    if evidence.sequence_mode == "unknown":
        unknown.append("unknown_sequence_state")
    elif evidence.sequence_mode == "required":
        seq = evidence.sequences
        if seq is None:
            unknown.append("missing_sequences")
        elif len(seq) != len(bars):
            failures.append("sequence_count_mismatch")
        elif any(number < 0 for number in seq):
            failures.append("invalid_sequence_number")
        elif any(b != a + 1 for a, b in pairwise(seq)):
            failures.append("sequence_gap_or_reordering")
    elif evidence.sequences is not None:
        failures.append("inconsistent_sequence_evidence")

    def check_quote(quote: PriceObservation, prefix: str) -> None:
        expected = value.contract or instrument.symbol
        if quote.symbol != expected:
            failures.append(prefix + "_identity_mismatch")
        age = Decimal(str((now - quote.timestamp).total_seconds()))
        diagnostics[prefix + "_age_seconds"] = str(age)
        if age < 0:
            failures.append("future_" + prefix)
        elif policy.max_quote_age_seconds is None:
            unknown.append("missing_quote_age_limit")
        elif age > policy.max_quote_age_seconds:
            failures.append("stale_" + prefix)
        if instrument.market == "cme_future" and any(
            p % instrument.tick_size for p in (quote.price, quote.bid, quote.ask) if p is not None
        ):
            failures.append("off_tick_" + prefix)
        if quote.bid is None or quote.ask is None:
            unknown.append("missing_" + prefix + "_bid_ask")
        else:
            spread = (quote.ask - quote.bid) / instrument.tick_size
            diagnostics[prefix + "_spread_ticks"] = str(spread)
            if policy.max_spread_ticks is None:
                unknown.append("missing_spread_limit")
            elif spread > policy.max_spread_ticks:
                failures.append("abnormal_" + prefix + "_spread")

    if evidence.quote is not None:
        check_quote(evidence.quote, "quote")
    elif policy.require_quote or evidence.reference_quote is not None:
        unknown.append("missing_quote")
    if evidence.reference_quote is not None:
        check_quote(evidence.reference_quote, "reference")
        if evidence.quote is not None:
            if evidence.quote.source.host == evidence.reference_quote.source.host:
                unknown.append("reference_source_not_independent")
            deviation = (
                abs(evidence.quote.price - evidence.reference_quote.price) / instrument.tick_size
            )
            diagnostics["source_deviation_ticks"] = str(deviation)
            if policy.max_source_deviation_ticks is None:
                unknown.append("missing_source_deviation_limit")
            elif deviation > policy.max_source_deviation_ticks:
                failures.append("source_disagreement")
    elif policy.require_reference:
        unknown.append("missing_reference_quote")
    return result()
