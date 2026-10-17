"""Mission-map provenance and denial through its public interface, without agent runtime."""

import shutil
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from core.advisory import capability_registry as registry
from core.advisory.briefing import AGENT_TOPICS

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def source_copy(tmp_path, monkeypatch):
    value = registry.capability_registry()
    for name in value.source_hashes:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    monkeypatch.setattr(registry, "_ROOT", tmp_path)
    return tmp_path


def test_every_agent_and_helper_has_one_distinct_mission_role():
    value = registry.capability_registry()
    actual = {
        str(path.relative_to(ROOT))
        for path in (ROOT / "src/agents").rglob("*.py")
        if path.name != "__init__.py"
    }
    assert len(value.definitions) == len(actual) == 40
    assert {d.source_file for d in value.definitions} == actual
    assert len({d.id for d in value.definitions}) == len(actual)
    assert {d.context_topic for d in value.definitions if d.context_topic} == set(AGENT_TOPICS)
    assert all(d.required_inputs and len(d.acceptance_criteria) >= 2 for d in value.definitions)
    assert all(d.qualified_signal is False for d in value.definitions)
    excluded = {d.id: d.exclusion_reason for d in value.definitions if d.adaptation == "EXCLUDED"}
    assert {
        "exchange_executor",
        "copy_trading_channel",
        "onchain_sleuth",
        "arb_cross_exchange",
    } <= excluded.keys()
    assert all(
        d.adaptation == "EXCLUDED" for d in value.definitions if "tier6_defi" in d.source_file
    )
    assert all(excluded.values())


def test_public_json_and_record_replay_retain_no_qualification():
    value = registry.capability_registry()
    saved = registry.CapabilityRegistry.model_validate_json(value.model_dump_json())
    assert registry.verify_capability_registry(saved) == value
    assert saved.runtime_status == "NOT_OBSERVED"
    assert saved.market_qualification == "NOT_ASSESSED"
    assert saved.passing_probability == "UNKNOWN"
    assert saved.all_agents_integrated is saved.trade_permitted is saved.execution_enabled is False


def test_separate_requests_repeat_source_checks_and_reject_previous_hashes(source_copy):
    first = registry.capability_registry()
    changed = source_copy / "src/agents/tier3_quant/technical_analyst.py"
    changed.write_bytes(changed.read_bytes() + b"\n# independent source revision\n")
    second = registry.capability_registry()
    assert first.source_hashes != second.source_hashes
    assert second.definitions == first.definitions
    assert second.runtime_status == "NOT_OBSERVED" and second.trade_permitted is False
    with pytest.raises(ValueError, match="source hashes differ"):
        registry.verify_capability_registry(first)
    assert registry.verify_capability_registry(second) == second


@pytest.mark.parametrize("change", ["missing", "unmapped", "symlink"])
def test_missing_unmapped_or_redirected_source_cannot_yield_a_registry(source_copy, change):
    target = source_copy / "src/agents/tier3_quant/technical_analyst.py"
    if change == "missing":
        target.unlink()
    elif change == "unmapped":
        (target.parent / "unexpected_agent.py").write_text("# not declared\n")
    else:
        external = source_copy / "redirected.py"
        target.rename(external)
        target.symlink_to(external)
    with pytest.raises(ValueError):
        registry.capability_registry()


@pytest.mark.parametrize("field", ["all_agents_integrated", "execution_enabled", "trade_permitted"])
def test_constructed_or_serialized_permission_flags_cannot_unlock_registry(field):
    value = registry.capability_registry()
    forged = value.model_copy(update={field: True})
    with pytest.raises(ValidationError):
        registry.verify_capability_registry(forged)
    data = value.model_dump(mode="json") | {field: True}
    with pytest.raises(ValidationError):
        registry.CapabilityRegistry.model_validate(data)


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_status", "RUNNING"),
        ("market_qualification", "READY"),
        ("passing_probability", "90%"),
    ],
)
def test_runtime_readiness_and_probability_cannot_be_inferred(field, value):
    data = registry.capability_registry().model_dump(mode="json") | {field: value}
    with pytest.raises(ValidationError):
        registry.CapabilityRegistry.model_validate(data)


@pytest.mark.parametrize("change", ["missing", "mismatch", "extra"])
def test_missing_inconsistent_source_evidence_is_rejected(change):
    data = registry.capability_registry().model_dump(mode="json")
    key = next(iter(data["source_hashes"]))
    if change == "missing":
        del data["source_hashes"][key]
    elif change == "mismatch":
        data["source_hashes"][key] = "0" * 64
    else:
        data["source_hashes"]["unrelated"] = "0" * 64
    with pytest.raises(ValueError, match="source hashes differ"):
        registry.CapabilityRegistry.model_validate(data)


@pytest.mark.parametrize(
    "change", ["duplicate", "renamed", "qualified", "hypothetical_confirmed", "role"]
)
def test_altered_definitions_or_confirmed_hypotheses_remain_insufficient(change):
    data = registry.capability_registry().model_dump(mode="json")
    if change == "duplicate":
        data["definitions"][1] = data["definitions"][0]
    elif change == "renamed":
        data["definitions"][0]["id"] = "renamed-agent"
    elif change == "qualified":
        data["definitions"][0]["qualified_signal"] = True
    elif change == "hypothetical_confirmed":
        data["confirmed"] = True
    else:
        data["definitions"][0]["advisory_role"] = "READY to execute"
    with pytest.raises(ValidationError):
        registry.CapabilityRegistry.model_validate(data)


def test_generation_time_never_becomes_a_market_source_clock():
    value = registry.capability_registry()
    older = value.model_copy(update={"generated_at": value.generated_at - timedelta(days=30)})
    saved = registry.verify_capability_registry(older)
    assert saved.runtime_status == "NOT_OBSERVED" and saved.market_qualification == "NOT_ASSESSED"
    assert saved.trade_permitted is False
    future = value.model_copy(update={"generated_at": value.generated_at + timedelta(days=1)})
    with pytest.raises(ValueError, match="Future registry"):
        registry.verify_capability_registry(future)


def test_definitions_cannot_mutate_the_shared_catalog():
    value = registry.capability_registry()
    with pytest.raises(ValidationError, match="frozen"):
        value.definitions[0].adaptation = "PLANNED"
    assert registry.capability_registry().definitions == value.definitions


def test_duplicate_catalog_identity_is_rejected(source_copy, monkeypatch):
    values = registry.DEFINITIONS
    monkeypatch.setattr(registry, "DEFINITIONS", (values[0], values[0], *values[2:]))
    with pytest.raises(ValueError, match="inventory differs"):
        registry.capability_registry()


def test_import_and_public_call_do_not_load_or_start_agents():
    script = """
import sys
from core.advisory.capability_registry import capability_registry
value = capability_registry()
assert value.execution_enabled is False
blocked = ('agents', 'core.orchestrator', 'connectors.exchanges', 'core.execution', 'core.accounting')
assert not any(name == prefix or name.startswith(prefix + '.') for name in sys.modules for prefix in blocked)
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
    assert not result.stdout
