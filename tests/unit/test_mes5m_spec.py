"""Frozen MES protocol and immutable engineering evidence, never qualification."""

import json
from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from backtesting.mes5m_spec import (
    CostScenario,
    ResearchSpec,
    SourceIdentity,
    registry_event,
    verify_registry,
)

pytestmark = pytest.mark.unit


def test_specification_freezes_parameters_and_denies_non_development_access():
    spec = ResearchSpec()
    assert spec.range_period == 12
    assert spec.minimum_bars == 13
    assert spec.volume_multiplier == "1.5"
    assert spec.entry_delay_seconds == 60
    assert spec.firm_eligibility == "BLOCKED"
    assert spec.qualified_contracts == 0
    assert spec.passing_probability == "UNKNOWN"
    assert spec.execution_permissions is False
    assert spec.partitions[0].start == date(2025, 12, 15)
    spec.authorize_day(date(2026, 1, 6))
    for day in [date(2026, 1, 27), date(2026, 2, 18), date(2025, 12, 25)]:
        with pytest.raises(PermissionError):
            spec.authorize_day(day)
    assert ResearchSpec.model_validate_json(spec.model_dump_json()) == spec


@pytest.mark.parametrize(
    "change",
    [
        {"range_period": 11},
        {"volume_multiplier": "1.6"},
        {"entry_delay_seconds": 0},
        {"maximum_research_contracts": 10},
        {"personal_maximum_micros": 20},
        {"historical_performance_authorized": True},
        {"holdout_access_authorized": True},
        {"execution_permissions": True},
        {"execution_permissions": 0},
        {"qualified_contracts": False},
        {"qualified_contracts": 1},
        {"minimum_partition_trades": [9, 5, 10]},
        {"source_acquired_at": "2025-01-01T00:00:00Z"},
    ],
)
def test_frozen_spec_rejects_parameter_and_permission_changes(change):
    with pytest.raises(ValidationError):
        ResearchSpec.model_validate(change)


def test_partitions_and_costs_cannot_be_reordered_or_relabelled():
    values = ResearchSpec().model_dump(mode="json")
    values["partitions"].reverse()
    with pytest.raises(ValidationError):
        ResearchSpec.model_validate(values)
    with pytest.raises(ValidationError):
        CostScenario(id="baseline", commission_per_side_usd="1.50", adverse_ticks_per_side=2)
    assert [c.round_trip_usd for c in ResearchSpec().costs] == [
        __import__("decimal").Decimal("4.90"),
        __import__("decimal").Decimal("8.00"),
        __import__("decimal").Decimal("14.00"),
    ]


def test_registry_chain_reopens_exactly_and_detects_mutation_deletion_and_forgery():
    sources = (SourceIdentity(path="synthetic.fixture", sha256="a" * 64),)
    first = registry_event(
        sequence=1, kind="FROZEN", at=datetime(2026, 10, 19, tzinfo=UTC), sources=sources
    )
    second = registry_event(
        sequence=2,
        kind="QUALIFICATION_ONLY",
        at=datetime(2026, 10, 19, 1, tzinfo=UTC),
        sources=sources,
        previous=first.event_sha256,
    )
    verify_registry([first, second])
    assert first.model_validate_json(first.model_dump_json()) == first
    assert second.tested_strategy_variants == 0
    assert second.prior_performance_access == "NOT_ESTABLISHED"
    with pytest.raises(ValueError):
        verify_registry([second])
    with pytest.raises(ValueError):
        verify_registry([first, second.model_copy(update={"notes": ("changed",)})])
    with pytest.raises(ValidationError):
        first.model_validate(
            json.loads(first.model_dump_json()) | {"holdout_access_authorized": True}
        )


def test_model_copy_cannot_authorize_a_holdout_day():
    forged = ResearchSpec().model_copy(update={"partitions": ()})
    with pytest.raises(PermissionError):
        forged.authorize_day(date(2026, 2, 18))
