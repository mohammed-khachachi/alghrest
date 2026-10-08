"""Immutable first strategy definitions and experiment lifecycle, never approval.

Reported research metrics do not authorize lifecycle promotion. Only the migrated
range/volume kernel is represented until other rules have a verified interface.
"""

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from core.advisory.models import UTCDateTime, utc_instant
from core.advisory.selection import Evidence, future_root
from core.strategy_signals import ATRManagementParameters, BreakoutParameters

Identity = Annotated[str, Field(min_length=1, max_length=100, pattern=r".*\S.*")]
Reference = Annotated[str, Field(min_length=1, max_length=500, pattern=r".*\S.*")]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def _digest(value: Evidence) -> str:
    return hashlib.sha256(
        json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class ResearchPartition(Evidence):
    role: Literal["TRAIN", "VALIDATION", "OOS"]
    start: UTCDateTime
    end: UTCDateTime

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.start >= self.end:
            raise ValueError("Research partition must have a positive duration")
        return self


class StrategyResearchPlan(Evidence):
    dataset_id: Identity
    dataset_sha256: Digest
    source_reference: Reference
    research_start: UTCDateTime
    research_end: UTCDateTime
    partitions: tuple[ResearchPartition, ResearchPartition, ResearchPartition]

    @model_validator(mode="after")
    def splits(self) -> Self:
        train, validation, oos = self.partitions
        if tuple(row.role for row in self.partitions) != ("TRAIN", "VALIDATION", "OOS"):
            raise ValueError("Research partitions require TRAIN, VALIDATION, OOS order")
        if not (
            self.research_start
            <= train.start
            < train.end
            < validation.start
            < validation.end
            < oos.start
            < oos.end
            <= self.research_end
        ):
            raise ValueError("Research partitions must be disjoint within the research period")
        return self


class StrategyDefinition(Evidence):
    id: Literal["breakout_hunter_volume"]
    version: Identity
    registered_at: UTCDateTime
    source_reference: Reference
    origin: Literal["reported", "synthetic"]
    code_version: Literal["range-volume-v1"]
    code_sha256: Digest
    parameters: BreakoutParameters
    interval: Literal["1d"]
    supported_markets: tuple[str, ...] = Field(min_length=1, max_length=9)
    research: StrategyResearchPlan | None = None
    management: ATRManagementParameters | None = None

    @model_serializer(mode="wrap")
    def preserve_entry_only_revision(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        payload: dict[str, Any] = handler(self)
        if self.management is None:
            # Old immutable registry digests did not contain this optional field.
            payload.pop("management", None)
        return payload

    @model_validator(mode="after")
    def markets(self) -> Self:
        if len(set(self.supported_markets)) != len(self.supported_markets):
            raise ValueError("Supported markets must be distinct")
        for root in self.supported_markets:
            future_root(root)
        if self.management is not None and (
            self.parameters.minimum_bars <= self.management.atr_period
            or self.management.atr_window < self.parameters.minimum_bars
        ):
            raise ValueError("Strategy warmup must fit its declared ATR management history")
        return self

    @property
    def revision(self) -> str:
        return _digest(self)


class StrategyLifecycleEvent(Evidence):
    # Other lifecycle stages require a verified evidence-producing workflow.
    status: Literal["EXPERIMENT", "RETIRED"]
    known_at: UTCDateTime
    source_reference: Reference
    reason: Reference


class StrategyRecord(Evidence):
    definition: StrategyDefinition
    events: tuple[StrategyLifecycleEvent, ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def transitions(self) -> Self:
        if (
            self.events[0].status != "EXPERIMENT"
            or self.events[0].known_at != self.definition.registered_at
        ):
            raise ValueError("Strategy must originate as EXPERIMENT at registration")
        if len(self.events) == 2 and (
            self.events[1].status != "RETIRED" or self.events[1].known_at <= self.events[0].known_at
        ):
            raise ValueError("Retirement must follow registration; revival requires a new version")
        return self

    @property
    def revision(self) -> str:
        return _digest(self)


class StrategyRegistry(Evidence):
    format_version: Literal["experiment-registry-v1"] = "experiment-registry-v1"
    records: tuple[StrategyRecord, ...] = Field(default=(), max_length=100)

    @model_validator(mode="after")
    def identities(self) -> Self:
        keys = [(row.definition.id, row.definition.version) for row in self.records]
        if keys != sorted(set(keys)):
            raise ValueError("Registry versions must be unique and canonically ordered")
        return self

    @property
    def revision(self) -> str:
        return _digest(self)


class StrategyApprovalCheck(Evidence):
    checked_at: UTCDateTime
    strategy_id: Identity
    strategy_version: Identity
    instrument_id: str
    mode: Literal["current", "replay"]
    record: StrategyRecord | None
    state: Literal["BLOCKED", "UNKNOWN"]
    reasons: tuple[str, ...] = Field(min_length=1)
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def reproducible(self) -> Self:
        future_root(self.instrument_id)
        state, reasons = _approval_reasons(
            self.record,
            self.strategy_id,
            self.strategy_version,
            self.instrument_id,
            self.mode,
            self.checked_at,
        )
        if (self.state, self.reasons) != (state, reasons):
            raise ValueError("Strategy approval check must reproduce its captured registry record")
        return self


def _approval_reasons(
    record: StrategyRecord | None,
    strategy_id: str,
    strategy_version: str,
    instrument_id: str,
    mode: Literal["current", "replay"],
    now: datetime,
) -> tuple[Literal["BLOCKED", "UNKNOWN"], tuple[str, ...]]:
    if record is None:
        return "UNKNOWN", ("missing_strategy_definition",)
    reasons = ["strategy_lifecycle:" + record.events[-1].status]
    definition = record.definition
    if (definition.id, definition.version) != (strategy_id, strategy_version):
        reasons.append("strategy_definition_identity_mismatch")
    if instrument_id not in definition.supported_markets:
        reasons.append("strategy_market_not_supported")
    if record.events[-1].known_at > now:
        reasons.append("future_strategy_registry_revision")
    if mode == "current" and definition.origin == "synthetic":
        reasons.append("synthetic_current_strategy_definition")
    return "BLOCKED", tuple(sorted(reasons))


def assess_strategy_approval(
    registry: StrategyRegistry | None,
    *,
    strategy_id: str,
    strategy_version: str,
    instrument_id: str,
    mode: Literal["current", "replay"],
    now: datetime,
) -> StrategyApprovalCheck:
    now = utc_instant(now)
    if registry is not None:
        registry = StrategyRegistry.model_validate(registry.model_dump(warnings=False))
    record = (
        next(
            (
                row
                for row in registry.records
                if (row.definition.id, row.definition.version) == (strategy_id, strategy_version)
            ),
            None,
        )
        if registry
        else None
    )
    state, reasons = _approval_reasons(
        record, strategy_id, strategy_version, instrument_id, mode, now
    )
    return StrategyApprovalCheck(
        checked_at=now,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        instrument_id=instrument_id,
        mode=mode,
        record=record,
        state=state,
        reasons=reasons,
    )
