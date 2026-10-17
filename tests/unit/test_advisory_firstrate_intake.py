"""Synthetic provider-shaped fixtures exercise conversion, never trading edge."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from core.advisory.data import MarketDataQuery
from core.advisory.models import MarketSnapshot
from scripts import advisory_firstrate_intake as intake

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]
START = datetime(2026, 1, 2, 15, tzinfo=UTC)


def fixture(rows=15):
    return "".join(
        (datetime(2026, 1, 2, 10) + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        + f",5000.25,5002.00,4999.75,5001.50,{i + 1}\n"
        for i in range(rows)
    ).encode()


def query(root="MNQ", **changes):
    return MarketDataQuery.model_validate(
        dict(
            instrument_id=root,
            contract=root + "H26",
            interval="5m",
            as_of=START + timedelta(hours=1),
        )
        | changes
    )


def inspect(payload=None, root="MNQ", **changes):
    arguments = (
        dict(
            source_name=root + "_H26_1min.csv",
            source_timezone="America/New_York",
            fetched_at=START + timedelta(hours=1),
        )
        | changes
    )
    return intake.inspect_firstrate(
        fixture() if payload is None else payload, query(root), **arguments
    )


def assert_closed(result):
    assert result["decision"] == "ABSTAIN"
    assert result["trade_permitted"] is result["execution_enabled"] is False
    assert result["tcp50_allowance"] == "BLOCKED"
    assert result["passing_probability"] == "UNKNOWN"
    assert result["firstrate_adapter"]["source_authenticity"] == "NOT_ESTABLISHED"
    assert result["market_data_access"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("root", ["MES", "MNQ"])
@pytest.mark.parametrize("origin", ["synthetic", "unverified"])
def test_exact_native_composition_and_closed_permissions(root, origin):
    payload = fixture()
    result = inspect(payload, root, origin=origin)
    value = MarketSnapshot.model_validate(result["normalized_snapshot"])
    assert value.instrument_id == root and value.contract == root + "H26"
    assert value.fetched_at == START + timedelta(hours=1)
    assert value.data_mode == "user_import" and value.quality is None
    assert len(value.candles) == 3
    first = value.candles[0]
    assert first.open_time == START
    assert first.close_time == START + timedelta(minutes=5, microseconds=-1)
    assert (first.open, first.high, first.low, first.close) == (
        Decimal("5000.25"),
        Decimal("5002.00"),
        Decimal("4999.75"),
        Decimal("5001.50"),
    )
    assert [bar.volume for bar in value.candles] == [Decimal(15), Decimal(40), Decimal(65)]
    adapter = result["firstrate_adapter"]
    assert adapter["csv_sha256"] == hashlib.sha256(payload).hexdigest()
    assert adapter["counts"]["source_rows"] == 15
    assert adapter["counts"]["incomplete_buckets"] == 0
    assert adapter["counts"]["selected_buckets"] == 3
    assert "missing_quality_evidence" in result["data_health"]["reasons"]
    assert "stale_bar" in result["data_health"]["reasons"]
    assert_closed(result)


@pytest.mark.parametrize("suffix", ["26", "2026"])
@pytest.mark.parametrize("source_suffix", ["26", "2026"])
def test_explicit_two_and_four_digit_contract_identity(suffix, source_suffix):
    result = intake.inspect_firstrate(
        fixture(),
        query(contract="MNQH" + suffix),
        source_name=f"MNQ_H{source_suffix}_1min.csv",
        source_timezone="America/New_York",
        fetched_at=START + timedelta(hours=1),
    )
    assert result["normalized_snapshot"]["contract"] == "MNQH" + suffix


@pytest.mark.parametrize("offset", [-1, -0.000001, 0, 1])
def test_true_completion_precedes_inclusive_end_and_historical_cut(offset):
    cut = START + timedelta(minutes=10, seconds=offset)
    result = intake.inspect_firstrate(
        fixture(),
        query(as_of=cut),
        source_name="MNQ_H26_1min.csv",
        source_timezone="America/New_York",
        fetched_at=START + timedelta(hours=1),
    )
    counts = result["firstrate_adapter"]["counts"]
    assert counts["selected_buckets"] == (1 if offset < 0 else 2)
    assert counts["complete_after_query_cut"] == (2 if offset < 0 else 1)
    assert "future_capture" in result["data_health"]["reasons"]
    assert result["normalized_snapshot"]["fetched_at"] == "2026-01-02T16:00:00Z"
    assert_closed(result)


def test_empty_cut_reports_no_market_without_fabricated_candle():
    result = intake.inspect_firstrate(
        fixture(),
        query(as_of=START),
        source_name="MNQ_H26_1min.csv",
        source_timezone="America/New_York",
        fetched_at=START + timedelta(hours=1),
    )
    assert result["input_status"] == "VALID"
    assert result["firstrate_adapter"]["normalization"] == "EMPTY"
    assert result["normalized_snapshot"] is None
    assert result["data_health"]["reasons"] == ["missing_market"]
    assert result["firstrate_adapter"]["counts"]["complete_after_query_cut"] == 3
    assert_closed(result)


def test_all_incomplete_rows_and_gaps_remain_visible_without_filling():
    rows = fixture().splitlines(keepends=True)
    payload = b"".join(rows[1:3] + rows[5:10] + rows[11:])
    result = inspect(payload)
    counts = result["firstrate_adapter"]["counts"]
    assert counts["source_rows"] == 11
    assert counts["observed_buckets"] == 3
    assert counts["incomplete_buckets"] == 2
    assert counts["incomplete_source_rows"] == 6
    assert counts["native_gap_intervals"] == 2
    assert counts["maximum_native_gap_seconds"] == 180
    value = MarketSnapshot.model_validate(result["normalized_snapshot"])
    assert len(value.candles) == 1 and value.candles[0].open_time == START + timedelta(minutes=5)


def test_missing_middle_bucket_remains_unverified_session_gap():
    rows = fixture().splitlines(keepends=True)
    result = inspect(b"".join(rows[:5] + rows[10:]))
    assert "unverified_session_gap" in result["data_health"]["reasons"]
    assert result["firstrate_adapter"]["counts"]["native_gap_intervals"] == 1
    assert len(result["normalized_snapshot"]["candles"]) == 2


def test_all_rows_checked_after_selection_and_maximum_window_is_reported():
    q = query(max_bars=1)
    kwargs = dict(
        source_name="MNQ_H26_1min.csv",
        source_timezone="America/New_York",
        fetched_at=START + timedelta(hours=1),
    )
    result = intake.inspect_firstrate(fixture(), q, **kwargs)
    counts = result["firstrate_adapter"]["counts"]
    assert counts["eligible_closed_buckets"] == 3
    assert counts["excluded_by_bar_limit"] == 2
    assert result["normalized_snapshot"]["candles"][0]["open_time"] == "2026-01-02T15:10:00Z"
    invalid = intake.inspect_firstrate(fixture() + b"secret-token-invalid-row\n", q, **kwargs)
    assert invalid["input_status"] == "INVALID"
    assert invalid["normalized_snapshot"] is None
    assert "secret-token" not in json.dumps(invalid)


def test_full_source_can_exceed_snapshot_cap_without_silent_row_loss():
    cut = START + timedelta(days=3)
    result = intake.inspect_firstrate(
        fixture(2505),
        query(as_of=cut),
        source_name="MNQ_H26_1min.csv",
        source_timezone="America/New_York",
        fetched_at=cut,
    )
    counts = result["firstrate_adapter"]["counts"]
    assert counts["source_rows"] == 2505 and counts["complete_buckets"] == 501
    assert counts["selected_buckets"] == 500 and counts["excluded_by_bar_limit"] == 1
    assert len(result["normalized_snapshot"]["candles"]) == 500
    assert result["normalized_snapshot"]["candles"][0]["open_time"] == "2026-01-02T15:05:00Z"


@pytest.mark.parametrize(
    "source",
    [
        "MNQ_1min_continuous.csv",
        "MNQ_H26_1day.csv",
        "MNQ_H26_5min.csv",
        "MNQH26.csv",
        "MES_H26_1min.csv",
        "MNQ_H27_1min.csv",
        "MNQ_J26_1min.csv",
        "MNQ_H6_1min.csv",
        "MNQ_H1999_1min.csv",
        "MNQ_H2100_1min.csv",
        "../MNQ_H26_1min.csv",
    ],
)
def test_continuous_daily_and_wrong_or_ambiguous_identity_rejected(source):
    result = inspect(source_name=source)
    assert result["input_status"] == "INVALID" and result["normalized_snapshot"] is None
    assert_closed(result)


@pytest.mark.parametrize(
    "payload",
    [
        b"",
        b"\xff",
        b"date,open,high,low,close,volume\n",
        b"\n",
        b"2026-01-02,5000,5001,4999,5000,0,10\n",
        fixture() + fixture()[: fixture().index(b"\n") + 1],
        b"\n".join(fixture().splitlines()[::-1]),
    ],
)
def test_bad_encoding_schema_and_chronology_are_not_repaired(payload):
    result = inspect(payload)
    assert result["input_status"] == "INVALID"
    assert result["firstrate_adapter"]["csv_sha256"] == hashlib.sha256(payload).hexdigest()
    assert_closed(result)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b"5000.25", b"5000.26"),
        (b"5002.00", b"4998.00"),
        (b"4999.75", b"5003"),
        (b"5000.25", b"0"),
        (b"5000.25", b"-1"),
        (b"5000.25", b"NaN"),
        (b"5000.25", b"Infinity"),
        (b"5000.25", b"1e999999"),
        (b"5000.25", b"9" * 33),
        (b",1\n", b",1.5\n"),
        (b",1\n", b",-1\n"),
        (b"10:00:00", b"10:00:01"),
        (b"10:00:00", b"10:00:00Z"),
        (b"2026-01-02", b"2026-02-30"),
    ],
)
def test_invalid_price_tick_volume_and_timestamp_rejected(old, new):
    result = inspect(fixture().replace(old, new, 1))
    assert result["input_status"] == "INVALID"
    assert_closed(result)


@pytest.mark.parametrize("local", ["2026-03-08 02:30:00", "2026-11-01 01:30:00"])
def test_nonexistent_and_ambiguous_eastern_minutes_rejected(local):
    payload = (local + ",5000,5001,4999,5000,1\n").encode()
    result = inspect(payload, fetched_at=datetime(2027, 1, 1, tzinfo=UTC))
    assert result["input_status"] == "INVALID"


@pytest.mark.parametrize(("day", "utc_hour"), [("2026-01-02", 15), ("2026-07-02", 14)])
def test_eastern_standard_and_daylight_offsets(day, utc_hour):
    result = inspect(
        fixture(5).replace(b"2026-01-02", day.encode()), fetched_at=datetime(2026, 8, 1, tzinfo=UTC)
    )
    # Query is January: summer bars are correctly excluded, not backdated.
    first = result["firstrate_adapter"]["first_native_open_utc"]
    assert first == f"{day}T{utc_hour:02d}:00:00+00:00"


def test_exact_decimal_volume_preserved_even_with_low_caller_precision():
    payload = fixture(5).replace(b",1\n", b",123456789012345678901234567890\n")
    with localcontext() as context:
        context.prec = 5
        result = inspect(payload)
    bar = result["normalized_snapshot"]["candles"][0]
    assert Decimal(bar["volume"]) == Decimal("123456789012345678901234567904")


def test_bom_and_crlf_have_exact_complete_source_identities():
    a = inspect(fixture())
    payload = b"\xef\xbb\xbf" + fixture().replace(b"\n", b"\r\n")
    b = inspect(payload)
    assert a["normalized_snapshot"] == b["normalized_snapshot"]
    assert a["firstrate_adapter"]["csv_sha256"] != b["firstrate_adapter"]["csv_sha256"]
    assert b["firstrate_adapter"]["csv_sha256"] == hashlib.sha256(payload).hexdigest()


def test_byte_and_row_limits_never_claim_a_truncated_file_hash(monkeypatch):
    monkeypatch.setattr(intake, "MAX_CSV_BYTES", 10)
    result = inspect()
    assert result["firstrate_adapter"]["csv_sha256"] is None
    assert result["input_sha256"] is None and result["input_status"] == "INVALID"
    monkeypatch.setattr(intake, "MAX_CSV_BYTES", 30_000_000)
    monkeypatch.setattr(intake, "MAX_SOURCE_ROWS", 14)
    assert inspect()["input_status"] == "INVALID"


@pytest.mark.parametrize(
    "change",
    [
        {"source_timezone": "UTC"},
        {"fetched_at": START + timedelta(minutes=14, seconds=59)},
    ],
)
def test_missing_provider_conventions_and_unfinished_native_rows_rejected(change):
    assert inspect(**change)["input_status"] == "INVALID"


def test_origin_and_query_cannot_create_entitlement_or_new_interval():
    with pytest.raises(ValueError, match="Origin"):
        inspect(origin="licensed")
    result = intake.inspect_firstrate(
        fixture(),
        query(interval="15m"),
        source_name="MNQ_H26_1min.csv",
        source_timezone="America/New_York",
        fetched_at=START + timedelta(hours=1),
    )
    assert result["input_status"] == "INVALID"
    with pytest.raises(ValueError, match="timezone"):
        inspect(fetched_at=datetime(2026, 1, 2, 16))


def test_cli_is_fresh_process_offline_without_env_stores_or_writes(tmp_path):
    source = tmp_path / "MNQ_H26_1min.csv"
    source.write_bytes(fixture())
    code = r"""
import sys, os
from pathlib import Path
from importlib.abc import MetaPathFinder
class BlockRuntime(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith(("core.config", "core.advisory.store", "connectors", "agents", "api")):
            raise AssertionError("runtime import")
        return None
sys.meta_path.insert(0, BlockRuntime())
def guard(event, args):
    if event.startswith("socket."): raise AssertionError("network IO")
    if event == "open":
        path, mode, flags = args
        if isinstance(path, (str, bytes)) and Path(os.fsdecode(path)).name.startswith(".env"):
            raise AssertionError("env read")
        if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
            raise AssertionError("file write")
sys.addaudithook(guard)
from scripts.advisory_firstrate_intake import main
raise SystemExit(main(sys.argv[1:]))
"""
    args = [
        str(source),
        "--instrument",
        "MNQ",
        "--contract",
        "MNQH26",
        "--source-timezone",
        "America/New_York",
        "--fetched-at",
        "2026-01-02T16:00:00Z",
        "--as-of",
        "2026-01-02T16:00:00Z",
        "--origin",
        "synthetic",
    ]
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code, *args],
        cwd=ROOT,
        timeout=20,
        env=os.environ | {"PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 2, proc.stderr
    assert_closed(json.loads(proc.stdout))
    assert source.read_bytes() == fixture()


@pytest.mark.parametrize("fault", ["missing", "symlink", "oversized", "secret-argument"])
def test_cli_file_and_argument_failures_are_sanitized(tmp_path, monkeypatch, capsys, fault):
    source = tmp_path / "MNQ_H26_1min.csv"
    args = [
        str(source),
        "--instrument",
        "MNQ",
        "--contract",
        "MNQH26",
        "--source-timezone",
        "America/New_York",
        "--fetched-at",
        "2026-01-02T16:00:00Z",
        "--as-of",
        "2026-01-02T16:00:00Z",
    ]
    if fault == "symlink":
        real = tmp_path / "real.csv"
        real.write_bytes(fixture())
        source.symlink_to(real)
    elif fault == "oversized":
        source.write_bytes(fixture())
        monkeypatch.setattr(intake, "MAX_CSV_BYTES", 10)
        assert intake.main(args) == 2
        result = json.loads(capsys.readouterr().out)
        assert result["firstrate_adapter"]["csv_sha256"] is None
        return
    elif fault == "secret-argument":
        args += ["--api-key", "never-echo-this"]
    with pytest.raises(SystemExit) as exit_info:
        intake.main(args)
    assert exit_info.value.code == 2
    assert "never-echo-this" not in capsys.readouterr().err
