"""User-reported chart observations; never market qualification or trade permission."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BeforeValidator, ConfigDict, Field, model_validator

from core.advisory.models import CATALOG, Strict, UTCDateTime, utc_instant

MAX_BYTES = 100_000
MAX_AGE_SECONDS = 900  # Display warning only, never a market-health or permission gate.


def decimal_text(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"-?(0|[1-9]\d{0,11})(\.\d{1,8})?", value):
        raise ValueError("Use a finite decimal string without separators or exponent")
    return value


def timestamp(value: Any) -> Any:
    if not isinstance(value, str | datetime):
        raise ValueError("Use a timezone-aware timestamp, not an epoch number")
    return value


DecimalText = Annotated[str, BeforeValidator(decimal_text)]
ObservationTime = Annotated[UTCDateTime, BeforeValidator(timestamp)]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


class ObservationModel(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PrintedValue(ObservationModel):
    label: str = Field(min_length=1, max_length=100)
    value: DecimalText | None
    evidence: str = Field(min_length=1, max_length=500)


class ObservationFrame(ObservationModel):
    image_id: Identifier
    contract: str | None = Field(max_length=40)
    interval: Literal["5m", "15m", "1h"]
    captured_at: ObservationTime | None
    observed_at: ObservationTime | None
    last_closed_bar_at: ObservationTime | None
    delay_status: Literal["real_time_reported", "delayed", "unknown"]
    last: DecimalText | None
    bid: DecimalText | None
    ask: DecimalText | None
    price_evidence: str = Field(min_length=1, max_length=500)
    indicators: tuple[PrintedValue, ...] = Field(default=(), max_length=20)
    printed_levels: tuple[PrintedValue, ...] = Field(default=(), max_length=20)
    hypotheses: tuple[Annotated[str, Field(min_length=1, max_length=500)], ...] = Field(
        default=(), max_length=10
    )

    @model_validator(mode="after")
    def coherent(self) -> Self:
        for value in (self.last, self.bid, self.ask, *(p.value for p in self.printed_levels)):
            if value is not None and (Decimal(value) <= 0 or Decimal(value) % Decimal("0.25")):
                raise ValueError("MES/MNQ prices must be positive quarter-point values")
        if self.bid is not None and self.ask is not None and Decimal(self.bid) > Decimal(self.ask):
            raise ValueError("Bid exceeds ask")
        if self.captured_at is not None:
            for stamp in (self.observed_at, self.last_closed_bar_at):
                if stamp is not None and stamp > self.captured_at:
                    raise ValueError("Price/bar timestamp is after capture")
        return self


class ObservationPacket(ObservationModel):
    schema_version: Literal["user-observation-v1"]
    instrument_id: Literal["MES", "MNQ"]
    contract: str | None = Field(max_length=40)
    source_kind: Literal["manual", "screenshot_transcription"]
    source_reference: str = Field(min_length=1, max_length=500)
    frames: tuple[ObservationFrame, ...] = Field(min_length=1, max_length=3)

    @model_validator(mode="after")
    def identities(self) -> Self:
        if self.contract is not None and not CATALOG[self.instrument_id].valid_contract(
            self.contract
        ):
            raise ValueError("Expected a dated contract for the selected Micro instrument")
        if len({f.interval for f in self.frames}) != len(self.frames) or len(
            {f.image_id for f in self.frames}
        ) != len(self.frames):
            raise ValueError("Duplicate interval or image identifier")
        if any(f.contract != self.contract for f in self.frames):
            raise ValueError("Every frame must agree with the packet contract")
        return self


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> Any:
    raise ValueError("Non-finite JSON constant")


def parse_observation(raw: str) -> ObservationPacket:
    """Parse only JSON data; no network, prompts, code, or file references are executed."""
    if len(raw.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Observation exceeds 100 KB")
    try:
        data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        return ObservationPacket.model_validate(data)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid or excessively nested observation") from exc


def observation_warnings(packet: ObservationPacket, *, now: datetime) -> tuple[str, ...]:
    """Reconstruct and reassess on every call; review never refreshes the source clock."""
    packet = ObservationPacket.model_validate(packet.model_dump())
    now = utc_instant(now)
    warnings = ["user_reported_not_independently_verified", "not_a_candle_dataset"]
    if packet.contract is None:
        warnings.append("missing_contract")
    if len(packet.frames) < 3:
        warnings.append("incomplete_timeframes")
    for frame in packet.frames:
        for field in ("captured_at", "observed_at", "last_closed_bar_at"):
            stamp = getattr(frame, field)
            if stamp is None:
                warnings.append(f"{frame.interval}:missing_{field}")
            elif stamp > now:
                raise ValueError("Observation contains future timestamps")
        if frame.observed_at is not None and now - frame.observed_at >= timedelta(
            seconds=MAX_AGE_SECONDS
        ):
            warnings.append(f"{frame.interval}:stale_price")
        if frame.delay_status != "real_time_reported":
            warnings.append(f"{frame.interval}:{frame.delay_status}_delay")
        if frame.last is None:
            warnings.append(f"{frame.interval}:missing_last")
    return tuple(warnings)


def observation_sources() -> dict[str, str]:
    return {"observations.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ObservationRevision(ObservationModel):
    id: Identifier
    revision: Digest
    parent_revision: Digest | None
    created_at: ObservationTime
    raw_json: str = Field(min_length=1, max_length=MAX_BYTES)
    packet: ObservationPacket
    source_hashes: dict[str, str]

    @model_validator(mode="after")
    def verify(self) -> Self:
        if self.source_hashes != observation_sources():
            raise ValueError("Observation source hashes differ; preserve old evidence")
        if self.packet != parse_observation(self.raw_json):
            raise ValueError("Saved packet differs from its original JSON")
        observation_warnings(self.packet, now=self.created_at)
        if self.revision != digest(self.model_dump(mode="json", exclude={"revision"})):
            raise ValueError("Observation revision hash differs")
        return self


def make_revision(
    raw: str, *, observation_id: str, parent_revision: str | None, now: datetime
) -> ObservationRevision:
    packet = parse_observation(raw)
    observation_warnings(packet, now=now)
    payload = {
        "id": observation_id,
        "parent_revision": parent_revision,
        "created_at": utc_instant(now).isoformat().replace("+00:00", "Z"),
        "raw_json": raw,
        "packet": packet.model_dump(mode="json"),
        "source_hashes": observation_sources(),
    }
    return ObservationRevision.model_validate({**payload, "revision": digest(payload)})


class ObservationView(ObservationModel):
    record: ObservationRevision
    latest_revision: Digest
    reviewed_at: ObservationTime | None
    assessed_at: ObservationTime
    warnings: tuple[str, ...]
    origin: Literal["user_reported"] = "user_reported"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False


class ObservationWrite(ObservationModel):
    raw_json: str = Field(min_length=1, max_length=MAX_BYTES)
    expected_revision: Digest | None


class ObservationReview(ObservationModel):
    expected_revision: Digest
    action: Literal["review_this_revision"]
