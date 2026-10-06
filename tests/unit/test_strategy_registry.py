"""Synthetic registry provenance and races; no approval or trading edge evidence."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from connectors.advisory.storage import AdvisoryStore
from core.advisory.risk import RiskDecision
from core.advisory.strategies import (
    ResearchPartition,
    StrategyApprovalCheck,
    StrategyDefinition,
    StrategyLifecycleEvent,
    StrategyRecord,
    StrategyRegistry,
    StrategyResearchPlan,
    assess_strategy_approval,
)
from tests.unit.test_advisory_risk import decision, make_service, setup
from tests.unit.test_market_selection import NOW

pytestmark = pytest.mark.unit
ROOTS = ("MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG")


def definition(**changes):
    return StrategyDefinition.model_validate(
        dict(
            id="breakout_hunter_volume",
            version="experiment-v1",
            registered_at=NOW,
            source_reference="SYNTHETIC experiment admission, no approval",
            origin="synthetic",
            code_version="range-volume-v1",
            code_sha256="c" * 64,
            parameters=dict(range_period=20, minimum_bars=30, volume_multiplier="2"),
            interval="1d",
            supported_markets=ROOTS,
        )
        | changes
    )


def event(status="EXPERIMENT", **changes):
    return StrategyLifecycleEvent.model_validate(
        dict(
            status=status,
            known_at=NOW if status == "EXPERIMENT" else NOW + timedelta(seconds=1),
            source_reference="SYNTHETIC lifecycle decision",
            reason="Isolated governance fixture",
        )
        | changes
    )


def record(**changes):
    return StrategyRecord.model_validate(dict(definition=definition(), events=(event(),)) | changes)


def check(registry=None, **changes):
    return assess_strategy_approval(
        registry if registry is not None else StrategyRegistry(records=(record(),)),
        **(
            dict(
                strategy_id="breakout_hunter_volume",
                strategy_version="experiment-v1",
                instrument_id="MNQ",
                mode="replay",
                now=NOW,
            )
            | changes
        ),
    )


def plan(**changes):
    return StrategyResearchPlan.model_validate(
        dict(
            dataset_id="synthetic-dataset",
            dataset_sha256="a" * 64,
            source_reference="SYNTHETIC planned splits",
            research_start=NOW - timedelta(days=100),
            research_end=NOW - timedelta(days=1),
            partitions=tuple(
                ResearchPartition(
                    role=role, start=NOW - timedelta(days=a), end=NOW - timedelta(days=b)
                )
                for role, a, b in [("TRAIN", 100, 70), ("VALIDATION", 69, 40), ("OOS", 39, 1)]
            ),
        )
        | changes
    )


def test_optional_research_is_not_fabricated_or_claimed_validated():
    assert definition().research is None
    d = definition(research=plan())
    assert d.research.partitions[-1].role == "OOS"
    assert d.revision == StrategyDefinition.model_validate_json(d.model_dump_json()).revision
    with pytest.raises(ValueError):
        d.version = "different"


@pytest.mark.parametrize(
    "changes",
    [
        dict(supported_markets=("MNQ", "MNQ")),
        dict(supported_markets=("UNKNOWN",)),
        dict(supported_markets=()),
        dict(code_sha256="bad"),
        dict(parameters=dict(range_period=30, minimum_bars=30, volume_multiplier=2)),
        dict(interval="15m"),
        dict(code_version="bogus"),
        dict(version=" "),
        dict(origin="live"),
        dict(lifecycle="APPROVED"),
        dict(trade_permitted=True),
    ],
)
def test_invalid_definition_and_unearned_permissions_are_rejected(changes):
    with pytest.raises(ValueError):
        definition(**changes)


@pytest.mark.parametrize("fault", ["duration", "overlap", "order", "outside"])
def test_partition_boundary_and_order_faults(fault):
    p = plan()
    parts = list(p.partitions)
    if fault == "duration":
        with pytest.raises(ValueError):
            ResearchPartition(role="TRAIN", start=NOW, end=NOW)
        return
    if fault == "overlap":
        parts[1] = parts[1].model_copy(update={"start": parts[0].end})
    if fault == "order":
        parts[0], parts[1] = parts[1], parts[0]
    with pytest.raises(ValueError):
        plan(partitions=parts, research_start=NOW if fault == "outside" else p.research_start)


@pytest.mark.parametrize("delta,valid", [(-1, False), (0, False), (1, True)])
def test_split_limits_use_microsecond_epsilon(delta, valid):
    p = plan()
    parts = list(p.partitions)
    parts[1] = parts[1].model_copy(update={"start": parts[0].end + timedelta(microseconds=delta)})
    if valid:
        assert plan(partitions=parts)
    else:
        with pytest.raises(ValueError):
            plan(partitions=parts)


@pytest.mark.parametrize("status", ["BACKTESTED", "VALIDATED", "SHADOW", "APPROVED", "UNKNOWN"])
def test_no_reported_status_can_promote_without_evidence_producing_workflow(status):
    with pytest.raises(ValueError):
        event(status)


@pytest.mark.parametrize(
    "events",
    [
        (),
        (event("RETIRED"),),
        (event(known_at=NOW - timedelta(seconds=1)),),
        (event(), event()),
        (event(), event("RETIRED", known_at=NOW)),
    ],
)
def test_lifecycle_cannot_skip_origin_rewrite_time_or_revive(events):
    with pytest.raises(ValueError):
        record(events=events)


@pytest.mark.parametrize("root", ROOTS)
def test_each_market_experiment_remains_blocked(root):
    v = check(instrument_id=root)
    assert v.state == "BLOCKED" and v.reasons == ("strategy_lifecycle:EXPERIMENT",)
    assert not v.trade_permitted and not v.execution_enabled
    assert StrategyApprovalCheck.model_validate_json(v.model_dump_json()) == v


@pytest.mark.parametrize("delta,future", [(-1, True), (0, False), (1, False)])
def test_registry_time_boundary_is_reproduced(delta, future):
    v = check(now=NOW + timedelta(microseconds=delta))
    assert ("future_strategy_registry_revision" in v.reasons) == future


def test_missing_retired_wrong_identity_market_and_synthetic_current_all_block():
    assert check(StrategyRegistry()).state == "UNKNOWN"
    assert check(strategy_version="unknown").record is None
    assert "synthetic_current_strategy_definition" in check(mode="current").reasons
    r = record(
        definition=definition(supported_markets=("MES",)), events=(event(), event("RETIRED"))
    )
    v = check(StrategyRegistry(records=(r,)), now=NOW + timedelta(seconds=2))
    assert v.reasons == ("strategy_lifecycle:RETIRED", "strategy_market_not_supported")
    bad = v.model_copy(update={"strategy_version": "wrong"})
    with pytest.raises(ValueError):
        StrategyApprovalCheck.model_validate(bad.model_dump())
    with pytest.raises(ValueError):
        StrategyApprovalCheck.model_validate(v.model_copy(update={"state": "UNKNOWN"}).model_dump())
    with pytest.raises(ValueError):
        StrategyApprovalCheck.model_validate(
            v.model_copy(update={"trade_permitted": True}).model_dump()
        )


def test_registry_requires_unique_canonical_versions_and_revalidates_nested_copies():
    a = record()
    b = record(definition=definition(version="experiment-v2"))
    for rows in [(a, a), (b, a)]:
        with pytest.raises(ValueError):
            StrategyRegistry(records=rows)
    changed = a.model_copy(
        update={"definition": a.definition.model_copy(update={"code_sha256": "corrupt"})}
    )
    with pytest.raises(ValueError):
        check(StrategyRegistry.model_construct(records=(changed,)))


def test_durable_registration_is_immutable_cas_and_retirement_preserves_definition(tmp_path):
    path = str(tmp_path / "registry.sqlite3")
    store = AdvisoryStore(path)
    empty = store.strategy_registry()
    d = definition()
    r = store.register_strategy(d, expected_revision=empty.revision, reason="Research experiment")
    active = AdvisoryStore(path).strategy_registry()
    assert active.records == (r,) and active.revision != empty.revision
    assert (
        store.register_strategy(d, expected_revision=active.revision, reason="Research experiment")
        == r
    )
    for replacement in [
        d.model_copy(
            update={"parameters": d.parameters.model_copy(update={"volume_multiplier": Decimal(3)})}
        ),
        d.model_copy(update={"research": plan()}),
    ]:
        with pytest.raises(ValueError, match="immutable"):
            store.register_strategy(
                replacement, expected_revision=active.revision, reason="Research experiment"
            )
    with pytest.raises(ValueError, match="revision changed"):
        store.register_strategy(
            definition(version="v2"), expected_revision=empty.revision, reason="new"
        )
    with pytest.raises(ValueError, match="Only retirement"):
        store.retire_strategy(d.id, d.version, expected_revision=active.revision, event=event())
    with pytest.raises(ValueError, match="not found"):
        store.retire_strategy(
            d.id, "missing", expected_revision=active.revision, event=event("RETIRED")
        )
    retired = store.retire_strategy(
        d.id, d.version, expected_revision=active.revision, event=event("RETIRED")
    )
    assert retired.definition == d and retired.events == (r.events[0], event("RETIRED"))
    final = store.strategy_registry()
    with pytest.raises(ValueError):
        store.retire_strategy(
            d.id,
            d.version,
            expected_revision=final.revision,
            event=event("RETIRED", known_at=NOW + timedelta(seconds=2)),
        )
    with pytest.raises(ValueError, match="immutable"):
        store.register_strategy(d, expected_revision=final.revision, reason="Research experiment")
    with pytest.raises(ValueError, match="revision changed"):
        store.retire_strategy(
            d.id, d.version, expected_revision=active.revision, event=event("RETIRED")
        )
    assert store.strategy_registry() == final


@pytest.mark.parametrize("fault", ["json", "shape", "digest", "parameters", "promote"])
def test_corrupt_registry_never_repairs_or_silently_drops_records(tmp_path, fault):
    s = AdvisoryStore(str(tmp_path / "corrupt.sqlite3"))
    s.register_strategy(
        definition(), expected_revision=s.strategy_registry().revision, reason="Research experiment"
    )
    with s.connect() as db:
        raw = db.execute("SELECT value FROM settings WHERE key='strategy_registry'").fetchone()[0]
        data = json.loads(raw)
        if fault == "shape":
            data["extra"] = "unexpected"
        elif fault == "digest":
            data["revision"] = "b" * 64
        elif fault == "parameters":
            data["registry"]["records"][0]["definition"]["parameters"]["minimum_bars"] = 1
        elif fault == "promote":
            data["registry"]["records"][0]["events"][0]["status"] = "APPROVED"
        bad = "{" if fault == "json" else json.dumps(data)
        db.execute("UPDATE settings SET value=? WHERE key='strategy_registry'", (bad,))
    with pytest.raises(ValueError):
        s.strategy_registry()
    with s.connect() as db:
        assert (
            db.execute("SELECT value FROM settings WHERE key='strategy_registry'").fetchone()[0]
            == bad
        )


def test_concurrent_registration_cas_cannot_overwrite_another_version(tmp_path):
    path = str(tmp_path / "race.sqlite3")
    s = AdvisoryStore(path)
    rev = s.strategy_registry().revision

    def submit(version):
        try:
            return AdvisoryStore(path).register_strategy(
                definition(version=version), expected_revision=rev, reason="concurrent experiment"
            )
        except ValueError as e:
            return str(e)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, ["v1", "v2"]))
    assert sum(isinstance(r, StrategyRecord) for r in results) == 1
    assert sum(isinstance(r, str) and "revision changed" in r for r in results) == 1
    assert len(s.strategy_registry().records) == 1


@given(
    st.integers(min_value=1, max_value=300),
    st.integers(min_value=1, max_value=50),
    st.decimals(min_value="0.01", max_value="20", allow_nan=False, allow_infinity=False, places=2),
)
@settings(max_examples=80, derandomize=True)
def test_parameter_mutation_always_requires_a_new_manifest(period, warmup, volume):
    d = definition(
        parameters=dict(range_period=period, minimum_bars=period + warmup, volume_multiplier=volume)
    )
    changed = d.model_copy(
        update={"parameters": d.parameters.model_copy(update={"minimum_bars": period + warmup + 1})}
    )
    assert d.revision != changed.revision
    assert check(StrategyRegistry(records=(record(definition=d),))).state == "BLOCKED"


def test_reported_approved_edge_cannot_qualify_default_risk_without_registry():
    assert decision().state == "QUALIFIED"  # Existing isolated arithmetic fixture.
    v = decision(strategy_registry_required=True)
    assert v.state == "UNKNOWN" and v.allowed_contracts == 0 and not v.risk_qualified
    assert (
        "missing_strategy_definition" in v.reasons
        and v.algorithm_version == "registered-structural-risk-v3"
    )
    for changes in [
        {"strategy_approval_check": None},
        {"strategy_registry_required": False, "strategy_approval_check": None},
        {
            "strategy_approval_check": v.strategy_approval_check.model_copy(
                update={"checked_at": NOW + timedelta(seconds=1)}
            )
        },
    ]:
        with pytest.raises(ValueError):
            RiskDecision.model_validate(v.model_copy(update=changes).model_dump())


async def test_service_reads_registry_and_cannot_use_reported_approval(tmp_path):
    service, request, _ = make_service(tmp_path, strategy_registry_required=True)
    v = await service.risk_decision("B", request)
    assert v.allowed_contracts == 0 and v.strategy_approval_check.state == "UNKNOWN"
    assert service.store.risk_decision(v.id) == v
    # Registered source is captured even with no matching market/risk evidence.
    service.store.register_strategy(
        definition(),
        expected_revision=service.store.strategy_registry().revision,
        reason="Research experiment",
    )
    request = request.model_copy(
        update={
            "setup": setup(strategy_id="breakout_hunter_volume", strategy_version="experiment-v1")
        }
    )
    v = await service.risk_decision("B", request)
    assert v.state == "BLOCKED" and v.strategy_approval_check.record.definition == definition()
    assert v.advice == "NO TRADE" and v.allowed_contracts == 0
    assert service.store.risk_decision(v.id) == v


async def test_reader_overlapping_retirement_captures_final_registry(tmp_path):
    service, request, _ = make_service(tmp_path, strategy_registry_required=True)
    store = service.store
    store.register_strategy(
        definition(),
        expected_revision=store.strategy_registry().revision,
        reason="Research experiment",
    )
    previous = service.risk_inputs_reader

    def reader(*args):
        result = previous(*args)
        store.retire_strategy(
            "breakout_hunter_volume",
            "experiment-v1",
            expected_revision=store.strategy_registry().revision,
            event=event("RETIRED"),
        )
        return result

    service.risk_inputs_reader = reader
    service.clock = lambda: NOW + timedelta(seconds=2)
    request = request.model_copy(
        update={
            "setup": setup(strategy_id="breakout_hunter_volume", strategy_version="experiment-v1")
        }
    )
    v = await service.risk_decision("B", request)
    assert v.strategy_approval_check.record.events[-1].status == "RETIRED"
    assert "strategy_lifecycle:RETIRED" in v.reasons and v.allowed_contracts == 0


def test_record_digest_changes_after_retirement_and_current_reported_is_still_experiment():
    r = record()
    retired = record(events=(event(), event("RETIRED")))
    assert r.revision != retired.revision
    assert r.revision == StrategyRecord.model_validate_json(r.model_dump_json()).revision
    v = check(
        StrategyRegistry(records=(record(definition=definition(origin="reported")),)),
        mode="current",
    )
    assert v.state == "BLOCKED" and v.reasons == ("strategy_lifecycle:EXPERIMENT",)


def test_positive_legacy_math_cannot_be_relabeled_as_registered_risk():
    v = decision()
    captured = assess_strategy_approval(
        None,
        strategy_id=v.setup.strategy_id,
        strategy_version=v.setup.strategy_version,
        instrument_id=v.setup.instrument_id,
        mode="replay",
        now=NOW,
    )
    with pytest.raises(ValueError, match="cannot qualify"):
        RiskDecision.model_validate(
            v.model_copy(
                update={
                    "algorithm_version": "registered-structural-risk-v3",
                    "strategy_registry_required": True,
                    "strategy_approval_check": captured,
                }
            ).model_dump()
        )


def test_registry_capacity_never_evicts_versions_or_retirement_history(tmp_path):
    s = AdvisoryStore(str(tmp_path / "capacity.sqlite3"))
    rows = tuple(record(definition=definition(version=f"v{i:03}")) for i in range(100))
    original = StrategyRegistry(records=rows)
    with s.connect() as db:
        s._save_strategy_registry(db, original)
    with pytest.raises(ValueError):
        s.register_strategy(
            definition(version="v100"), expected_revision=original.revision, reason="extra"
        )
    assert s.strategy_registry() == original
    retired = s.retire_strategy(
        "breakout_hunter_volume",
        "v000",
        expected_revision=original.revision,
        event=event("RETIRED"),
    )
    current = s.strategy_registry()
    assert (
        len(current.records) == 100
        and current.records[0] == retired
        and current.records[1:] == rows[1:]
    )
