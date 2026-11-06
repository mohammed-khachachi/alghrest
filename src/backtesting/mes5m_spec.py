"""Frozen, offline MES research contracts. No runner or trading authority."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictInt, model_validator

from core.advisory.models import UTCDateTime

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _false(value: object) -> bool:
    if type(value) is not bool or value:
        raise ValueError("Permission must be explicitly false")
    return False


Closed = Annotated[Literal[False], BeforeValidator(_false)]


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str | Decimal):
        raise ValueError("Financial values require Decimal or decimal strings")
    result = Decimal(value)
    if (
        not result.is_finite()
        or len(result.as_tuple().digits) > 32
        or not -16 <= int(str(result.as_tuple().exponent)) <= 16
    ):
        raise ValueError("Require a bounded finite financial value")
    return result


Money = Annotated[Decimal, BeforeValidator(_decimal)]


class ResearchModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Safety(ResearchModel):
    firm_eligibility: Literal["BLOCKED"] = "BLOCKED"
    qualified_contracts: Annotated[int, Field(strict=True, ge=0, le=0)] = 0
    passing_probability: Literal["UNKNOWN"] = "UNKNOWN"
    execution_permissions: Closed = False
    trade_permitted: Closed = False
    execution_enabled: Closed = False


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


PARTITIONS = {
    "DEVELOPMENT": (date(2025, 12, 15), date(2026, 1, 23)),
    "VALIDATION": (date(2026, 1, 27), date(2026, 2, 13)),
    "SEALED_HOLDOUT": (date(2026, 2, 18), date(2026, 3, 13)),
}
EXCLUSIONS = (
    (date(2025, 12, 24), date(2025, 12, 26)),
    (date(2025, 12, 31), date(2026, 1, 2)),
    (date(2026, 1, 19), date(2026, 1, 20)),
    (date(2026, 2, 16), date(2026, 2, 17)),
)


class Partition(ResearchModel):
    role: Literal["DEVELOPMENT", "VALIDATION", "SEALED_HOLDOUT"]
    start: date
    end: date

    @model_validator(mode="after")
    def frozen_dates(self) -> Self:
        if (self.start, self.end) != PARTITIONS[self.role]:
            raise ValueError("Partition changes require a separately approved experiment")
        return self


class CostScenario(ResearchModel):
    id: Literal["baseline", "adverse", "severe"]
    commission_per_side_usd: Literal["1.20", "1.50", "2.00"]
    adverse_ticks_per_side: Literal[1, 2, 4]
    classification: Literal["ASSUMPTION_NOT_OBSERVED_OR_BOUND"] = "ASSUMPTION_NOT_OBSERVED_OR_BOUND"

    @model_validator(mode="after")
    def frozen_costs(self) -> Self:
        expected = {"baseline": ("1.20", 1), "adverse": ("1.50", 2), "severe": ("2.00", 4)}
        if (self.commission_per_side_usd, self.adverse_ticks_per_side) != expected[self.id]:
            raise ValueError("Cost scenario differs from the frozen protocol")
        return self

    @property
    def round_trip_usd(self) -> Decimal:
        return 2 * Decimal(self.commission_per_side_usd) + Decimal("2.50") * (
            self.adverse_ticks_per_side
        )


def _partitions() -> tuple[Partition, ...]:
    return tuple(
        Partition.model_validate(dict(role=role, start=a, end=b))
        for role, (a, b) in PARTITIONS.items()
    )


def _costs() -> tuple[CostScenario, ...]:
    return (
        CostScenario(id="baseline", commission_per_side_usd="1.20", adverse_ticks_per_side=1),
        CostScenario(id="adverse", commission_per_side_usd="1.50", adverse_ticks_per_side=2),
        CostScenario(id="severe", commission_per_side_usd="2.00", adverse_ticks_per_side=4),
    )


class ResearchSpec(Safety):
    schema_version: Literal["mes5m-research-spec-v1"] = "mes5m-research-spec-v1"
    experiment_id: Literal["mes5m-range-volume-h26-v1"] = "mes5m-range-volume-h26-v1"
    instrument: Literal["MES"] = "MES"
    contract: Literal["MESH26"] = "MESH26"
    interval: Literal["5m"] = "5m"
    source_name: Literal["MES_H26_1min.csv"] = "MES_H26_1min.csv"
    source_csv_sha256: Literal[
        "b8765ffd496c17457e4edbd956336537f6996981e80d042c0692345a0e21ee01"
    ] = "b8765ffd496c17457e4edbd956336537f6996981e80d042c0692345a0e21ee01"
    source_timezone: Literal["America/New_York"] = "America/New_York"
    account_timezone: Literal["America/Chicago"] = "America/Chicago"
    source_acquired_at: UTCDateTime = datetime.fromisoformat("2026-10-09T21:07:58.978873+00:00")
    partitions: tuple[Partition, ...] = Field(default_factory=_partitions)
    personal_exclusion_ranges: tuple[tuple[date, date], ...] = EXCLUSIONS
    costs: tuple[CostScenario, ...] = Field(default_factory=_costs)
    range_period: Literal[12] = 12
    minimum_bars: Literal[13] = 13
    volume_multiplier: Literal["1.5"] = "1.5"
    window_start_utc: Literal["07:00"] = "07:00"
    window_end_utc: Literal["14:00"] = "14:00"
    first_decision_utc: Literal["08:05"] = "08:05"
    decision_end_exclusive_utc: Literal["12:55"] = "12:55"
    entry_delay_seconds: Literal[60] = 60
    stop_offset_ticks: Literal[1] = 1
    target_distance_multiple: Literal[2] = 2
    maximum_holding_minutes: Literal[60] = 60
    flat_by_utc: Literal["13:55"] = "13:55"
    maximum_research_contracts: Literal[1] = 1
    maximum_daily_entries: Literal[2] = 2
    pause_after_consecutive_losses: Literal[5] = 5
    trade_risk_cap_usd: Literal["100"] = "100"
    equity_risk_fraction: Literal["0.01"] = "0.01"
    personal_daily_stop_usd: Literal["200"] = "200"
    public_daily_loss_usd: Literal["550"] = "550"
    public_drawdown_usd: Literal["1500"] = "1500"
    public_starting_balance_usd: Literal["25000"] = "25000"
    public_target_usd: Literal["1750"] = "1750"
    financial_reserve_usd: Literal["100"] = "100"
    gap_reserve_usd: Literal["5"] = "5"
    personal_maximum_micros: Literal[10] = 10
    personal_maximum_minis: Literal[1] = 1
    mini_supported: Closed = False
    simultaneous_mini_micro_mixing: Closed = False
    trailing_stop: Closed = False
    averaging: Closed = False
    historical_performance_authorized: Closed = False
    holdout_access_authorized: Closed = False
    account_simulation_authorized: Closed = False
    minimum_dates: Literal[40] = 40
    minimum_calendar_weeks: Literal[8] = 8
    minimum_partition_dates: tuple[int, int, int] = (15, 10, 10)
    minimum_trades: Literal[30] = 30
    minimum_partition_trades: tuple[int, int, int] = (10, 5, 10)
    minimum_per_direction: Literal[5] = 5
    minimum_dates_per_eastern_offset: Literal[5] = 5
    minimum_outcomes_per_range_condition: Literal[5] = 5
    sample_sufficiency: Literal["UNKNOWN"] = "UNKNOWN"

    @model_validator(mode="after")
    def frozen_structure(self) -> Self:
        if (
            tuple(p.role for p in self.partitions) != tuple(PARTITIONS)
            or tuple(c.id for c in self.costs) != ("baseline", "adverse", "severe")
            or self.personal_exclusion_ranges != EXCLUSIONS
            or self.minimum_partition_dates != (15, 10, 10)
            or self.minimum_partition_trades != (10, 5, 10)
            or self.source_acquired_at.isoformat() != "2026-10-09T21:07:58.978873+00:00"
        ):
            raise ValueError("Frozen protocol changed")
        return self

    def authorize_day(self, day: date) -> None:
        # Check constants, including against model_copy/model_construct bypasses.
        a, b = PARTITIONS["DEVELOPMENT"]
        if not a <= day <= b or day.weekday() >= 5 or any(a <= day <= b for a, b in EXCLUSIONS):
            raise PermissionError("Only non-excluded DEVELOPMENT dates are authorized")

    @property
    def revision(self) -> str:
        return digest(self.model_dump(mode="json"))


class SourceIdentity(ResearchModel):
    path: str = Field(min_length=1, max_length=300)
    sha256: Digest


class RegistryEvent(Safety):
    schema_version: Literal["mes5m-experiment-event-v1"] = "mes5m-experiment-event-v1"
    experiment_id: Literal["mes5m-range-volume-h26-v1"] = "mes5m-range-volume-h26-v1"
    sequence: StrictInt = Field(ge=1)
    kind: Literal["FROZEN", "QUALIFICATION_ONLY", "ENGINEERING_VERIFIED", "RETIRED"]
    at: UTCDateTime
    specification_sha256: Digest
    sources: tuple[SourceIdentity, ...]
    previous_event_sha256: Digest | None
    event_sha256: Digest
    access_scope: Literal["development_preflight_and_synthetic_tests"] = (
        "development_preflight_and_synthetic_tests"
    )
    tested_strategy_variants: Literal[0] = 0
    historical_performance_authorized: Closed = False
    holdout_access_authorized: Closed = False
    prior_structural_quality_audit: Literal[True] = True
    prior_performance_access: Literal["NOT_ESTABLISHED"] = "NOT_ESTABLISHED"
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def identity(self) -> Self:
        if (
            self.specification_sha256 != ResearchSpec().revision
            or self.event_sha256 != digest(self.model_dump(mode="json", exclude={"event_sha256"}))
            or len({s.path for s in self.sources}) != len(self.sources)
            or tuple(s.path for s in self.sources) != tuple(sorted(s.path for s in self.sources))
        ):
            raise ValueError("Registry identity mismatch")
        return self


def registry_event(
    *,
    sequence: int,
    kind: Literal["FROZEN", "QUALIFICATION_ONLY", "ENGINEERING_VERIFIED", "RETIRED"],
    at: datetime,
    sources: tuple[SourceIdentity, ...],
    previous: str | None = None,
    notes: tuple[str, ...] = (),
) -> RegistryEvent:
    values: dict[str, Any] = dict(
        sequence=sequence,
        kind=kind,
        at=at,
        sources=sources,
        notes=notes,
        specification_sha256=ResearchSpec().revision,
        previous_event_sha256=previous,
    )
    # Obtain the canonical defaults before calculating the event's own identity.
    provisional = RegistryEvent.model_construct(**values, event_sha256="0" * 64)
    values["event_sha256"] = digest(provisional.model_dump(mode="json", exclude={"event_sha256"}))
    return RegistryEvent.model_validate(values)


def verify_registry(events: Sequence[RegistryEvent]) -> None:
    previous = None
    for sequence, supplied in enumerate(events, 1):
        event = RegistryEvent.model_validate(supplied.model_dump())
        if event.sequence != sequence or event.previous_event_sha256 != previous:
            raise ValueError("Registry chain mismatch")
        previous = event.event_sha256
