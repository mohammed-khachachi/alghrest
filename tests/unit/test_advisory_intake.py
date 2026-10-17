"""Offline data onboarding stays separate from entitlement and trading permission."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from core.advisory.data import MarketDataQuery
from scripts.advisory_intake import MAX_INPUT_BYTES, inspect_snapshot, main
from tests.unit.test_market_data_provider import records

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def snapshot(root="MNQ"):
    return records(80, root=root, contract=root + "Z26")[0]


def query(value, **changes):
    return MarketDataQuery.model_validate(
        {
            "instrument_id": value.instrument_id,
            "interval": value.interval,
            "contract": value.contract,
            "as_of": value.fetched_at,
        }
        | changes
    )


def inspect(value, **kwargs):
    return inspect_snapshot(value.model_dump_json().encode(), query(value), **kwargs)


def assert_abstains(result):
    assert result["decision"] == "ABSTAIN"
    assert result["trade_permitted"] is result["execution_enabled"] is False
    assert result["tcp50_allowance"] == "BLOCKED"
    assert result["passing_probability"] == "UNKNOWN"
    assert result["market_data_access"] == "NOT_ESTABLISHED"
    assert result["evaluation_rule_verification"] == "INCOMPLETE"
    assert result["live_advisory_readiness"] == "CANNOT_ASSESS"


@pytest.mark.parametrize("root", ["MES", "MNQ"])
@pytest.mark.parametrize("origin", ["synthetic", "unverified"])
def test_healthy_input_never_qualifies_license_rules_or_trading(root, origin):
    value = snapshot(root)
    before = value.model_dump_json().encode()
    result = inspect(value, origin=origin)
    assert result["input_status"] == "VALID"
    assert result["data_health"]["state"] == "HEALTHY"
    assert result["input_sha256"] == hashlib.sha256(before).hexdigest()
    assert result["counts"] == {"input_bars": 80, "reviewed_bars": 80, "excluded_bars": 0}
    assert value.model_dump_json().encode() == before
    assert_abstains(result)


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("quality", "missing_quality_evidence"),
        ("stale", "stale_bar"),
        ("gap", "unverified_session_gap"),
        ("off_tick", "off_tick_bar"),
        ("disconnected", "provider_disconnected"),
    ],
)
def test_existing_health_failures_remain_visible(fault, reason):
    value = snapshot()
    cut = value.fetched_at
    if fault == "quality":
        value.quality = None
    elif fault == "stale":
        cut += timedelta(hours=1)
    elif fault == "gap":
        del value.candles[10]
    elif fault == "off_tick":
        value.candles[10].close += Decimal("0.01")
    else:
        value.quality = value.quality.model_copy(update={"provider_state": "disconnected"})
    result = inspect_snapshot(value.model_dump_json().encode(), query(value, as_of=cut))
    assert result["data_health"]["state"] != "HEALTHY"
    assert reason in result["data_health"]["reasons"]
    assert_abstains(result)


@pytest.mark.parametrize("fault", ["duplicate", "wrong_contract", "future", "permission"])
def test_bad_structures_and_injected_permission_are_rejected(fault):
    value = snapshot()
    raw = value.model_dump(mode="json")
    if fault == "duplicate":
        raw["candles"].insert(1, raw["candles"][0])
    elif fault == "wrong_contract":
        raw["contract"] = "MESZ26"
    elif fault == "future":
        raw["fetched_at"] = raw["candles"][0]["close_time"]
    else:
        raw["trade_permitted"] = True
    result = inspect_snapshot(json.dumps(raw).encode(), query(value))
    assert result["input_status"] == "INVALID" and result["data_health"] is None
    assert_abstains(result)


@pytest.mark.parametrize("payload", [b"{", b"[]", b"null", b"\xff", b'{"a":1,"a":2}'])
def test_invalid_json_does_not_echo_input(payload):
    result = inspect_snapshot(payload, query(snapshot()))
    assert result["input_reasons"] == ["invalid_snapshot_or_requested_identity"]
    assert_abstains(result)


def test_cut_is_explicit_and_current_capture_cannot_be_promoted_to_replay():
    value = snapshot()
    result = inspect_snapshot(
        value.model_dump_json().encode(), query(value, as_of=value.candles[10].close_time)
    )
    assert result["counts"]["reviewed_bars"] == 11
    assert result["counts"]["excluded_bars"] == 69
    assert "future_capture" in result["data_health"]["reasons"]
    assert_abstains(result)
    empty = inspect_snapshot(
        value.model_dump_json().encode(), query(value, as_of=value.candles[0].open_time)
    )
    assert empty["data_health"]["reasons"] == ["missing_market"]
    assert_abstains(empty)


def test_no_qualified_origin_or_unpinned_contract_shortcut():
    value = snapshot()
    with pytest.raises(ValueError, match="Origin"):
        inspect(value, origin="licensed")
    with pytest.raises(ValueError, match="explicit dated"):
        inspect_snapshot(value.model_dump_json().encode(), query(value, contract=None))


def arguments(path, value):
    return [
        str(path),
        "--instrument",
        value.instrument_id,
        "--contract",
        value.contract,
        "--interval",
        value.interval,
        "--as-of",
        value.fetched_at.isoformat(),
    ]


def test_cli_exit_codes_and_read_only_output(tmp_path, capsys):
    value = snapshot()
    path = tmp_path / "snapshot.json"
    payload = value.model_dump_json().encode()
    path.write_bytes(payload)
    assert main([*arguments(path, value), "--origin", "synthetic"]) == 0
    assert_abstains(json.loads(capsys.readouterr().out))
    value.quality = None
    path.write_text(value.model_dump_json())
    assert main(arguments(path, value)) == 2
    assert (
        "missing_quality_evidence" in json.loads(capsys.readouterr().out)["data_health"]["reasons"]
    )
    path.write_bytes(payload)
    assert list(tmp_path.iterdir()) == [path] and path.read_bytes() == payload


def test_cli_oversized_input_has_no_false_full_file_identity(tmp_path, capsys):
    value = snapshot()
    path = tmp_path / "oversized.json"
    path.write_bytes(b" " * (MAX_INPUT_BYTES + 10))
    assert main(arguments(path, value)) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["input_reasons"] == ["input_too_large"]
    assert result["input_sha256"] is None
    assert_abstains(result)


@pytest.mark.parametrize("option", ["--execute", "--cancel", "--submit", "--allow-trading"])
def test_cli_rejects_order_options(tmp_path, option):
    with pytest.raises(SystemExit) as raised:
        main([*arguments(tmp_path / "missing.json", snapshot()), option])
    assert raised.value.code == 2


def test_cli_missing_file_and_naive_clock_are_errors(tmp_path):
    args = arguments(tmp_path / "missing.json", snapshot())
    with pytest.raises(SystemExit) as raised:
        main(args)
    assert raised.value.code == 2
    args[-1] = "2026-01-01T00:00:00"
    with pytest.raises(SystemExit) as raised:
        main(args)
    assert raised.value.code == 2


def test_fresh_process_never_opens_network_database_config_or_writes(tmp_path):
    value = snapshot()
    path = tmp_path / "input.json"
    path.write_text(value.model_dump_json())
    # Process-wide audit traps catch indirect IO as well as direct calls.
    code = """
import os, sys
def guard(event, args):
    if event in {"socket.connect", "socket.bind", "sqlite3.connect", "subprocess.Popen"}:
        raise RuntimeError("Forbidden IO: " + event)
    if event == "open":
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            raise RuntimeError("Forbidden write")
        if isinstance(path, str) and os.path.basename(path).startswith(".env"):
            raise RuntimeError("Configuration read")
sys.addaudithook(guard)
from scripts.advisory_intake import main
status = main(sys.argv[1:])
assert "core.config" not in sys.modules
assert "connectors.advisory.storage" not in sys.modules
raise SystemExit(status)
"""
    completed = subprocess.run(
        [sys.executable, "-B", "-c", code, *arguments(path, value)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert_abstains(json.loads(completed.stdout))
    assert list(tmp_path.iterdir()) == [path]
