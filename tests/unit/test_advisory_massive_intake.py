"""Synthetic Massive-shaped fixtures prove normalization mechanics only."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from core.advisory.data import MarketDataQuery
from core.advisory.models import INTERVAL_SECONDS
from scripts.advisory_massive_intake import RESOLUTIONS, inspect_massive, main, normalize_massive

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def fixture(root="MNQ", resolution="5min"):
    interval = RESOLUTIONS[resolution]
    start = datetime(2026, 1, 1, 12, tzinfo=UTC)
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    seconds = INTERVAL_SECONDS[interval]
    fetched = start + timedelta(seconds=seconds * 3)
    query = MarketDataQuery(
        instrument_id=root, contract=root + "Z26", interval=interval, as_of=fetched
    )
    rows = []
    for i in range(3):
        opened = start + timedelta(seconds=seconds * i)
        ns = (opened - epoch) // timedelta(microseconds=1) * 1000
        rows.append(
            {
                "ticker": root + "Z6",
                "window_start": ns,
                "session_end_date": "2026-01-01",
                "open": 5000.25,
                "high": 5001,
                "low": 5000,
                "close": 5000.75,
                "volume": 10 + i,
                "transactions": 3,
            }
        )
    bars = {"status": "OK", "results": rows[::-1]}
    metadata = {
        "status": "OK",
        "results": [
            {
                "ticker": root + "Z6",
                "product_code": root,
                "type": "single",
                "active": True,
                "trading_venue": "XCME",
                "date": "2026-01-01",
                "first_trade_date": "2025-09-19",
                "last_trade_date": "2026-12-18",
                "settlement_date": "2026-12-18",
                "trade_tick_size": 0.25,
                "max_order_quantity": 3000,
            }
        ],
    }
    return bars, metadata, query, fetched


def convert(bars, metadata, query, fetched, resolution="5min"):
    return normalize_massive(
        json.dumps(bars).encode(),
        json.dumps(metadata).encode(),
        query,
        resolution=resolution,
        fetched_at=fetched,
    )


def inspected(bars, metadata, query, fetched, **kwargs):
    return inspect_massive(
        json.dumps(bars).encode(),
        json.dumps(metadata).encode(),
        query,
        resolution="5min",
        fetched_at=fetched,
        **kwargs,
    )


def assert_closed(result):
    assert result["decision"] == "ABSTAIN"
    assert result["trade_permitted"] is result["execution_enabled"] is False
    assert result["tcp50_allowance"] == "BLOCKED"
    assert result["passing_probability"] == "UNKNOWN"
    assert result["massive_adapter"]["storage_replay_permission"] == "NOT_ESTABLISHED"


@pytest.mark.parametrize("root", ["MES", "MNQ"])
@pytest.mark.parametrize("resolution", RESOLUTIONS)
def test_maps_native_bars_and_proves_exact_contract_time_price_volume(root, resolution):
    bars, metadata, query, fetched = fixture(root, resolution)
    before = json.dumps([bars, metadata])
    snapshot = convert(bars, metadata, query, fetched, resolution)
    assert snapshot.contract == root + "Z26" and snapshot.interval == RESOLUTIONS[resolution]
    assert str(snapshot.source).endswith("/" + root + "Z6")
    assert snapshot.candles[0].open_time == datetime(2026, 1, 1, 12, tzinfo=UTC)
    assert snapshot.candles[-1].close_time == fetched - timedelta(microseconds=1)
    assert snapshot.candles[0].open == Decimal("5000.25")
    assert [c.volume for c in snapshot.candles] == [Decimal(10), Decimal(11), Decimal(12)]
    assert snapshot.quality is None and snapshot.data_mode == "user_import"
    assert json.dumps([bars, metadata]) == before


@pytest.mark.parametrize("suffix", ["6", "26", "2026"])
def test_expiry_metadata_resolves_provider_year_without_current_clock_guess(suffix):
    bars, metadata, query, fetched = fixture()
    for row in bars["results"]:
        row["ticker"] = "MNQZ" + suffix
    metadata["results"][0]["ticker"] = "MNQZ" + suffix
    query = query.model_copy(update={"contract": "MNQZ2026"})
    assert convert(bars, metadata, query, fetched).contract == "MNQZ2026"


def test_decimal_and_nanosecond_identity_are_not_converted_through_float():
    bars, metadata, query, fetched = fixture()
    payload = json.dumps(bars).encode().replace(b"5000.25", b"5000.250000000000000001")
    snapshot = normalize_massive(
        payload, json.dumps(metadata).encode(), query, resolution="5min", fetched_at=fetched
    )
    assert snapshot.candles[0].open == Decimal("5000.250000000000000001")
    assert snapshot.candles[0].open_time == datetime(2026, 1, 1, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticker", "MNQZ7"),
        ("ticker", "MESZ6"),
        ("settlement_date", "2036-12-18"),
        ("settlement_date", "2026-09-18"),
        ("settlement_date", None),
        ("date", "2027-01-01"),
        ("product_code", "MES"),
        ("type", "combo"),
        ("active", False),
        ("active", 1),
        ("trade_tick_size", 0.01),
        ("trading_venue", "XCBT"),
    ],
)
def test_metadata_mismatch_never_resolves_a_contract(field, value):
    bars, metadata, query, fetched = fixture()
    metadata["results"][0][field] = value
    result = inspected(bars, metadata, query, fetched)
    assert result["input_status"] == "INVALID" and result["normalized_snapshot"] is None
    assert result["input_sha256"] is None
    assert_closed(result)


@pytest.mark.parametrize("fault", ["empty", "two_contracts", "error", "pagination", "permission"])
def test_insufficient_or_injected_response_evidence_is_rejected(fault):
    bars, metadata, query, fetched = fixture()
    if fault == "empty":
        metadata["results"] = []
    elif fault == "two_contracts":
        metadata["results"] *= 2
    elif fault == "error":
        bars["status"] = "NOT_AUTHORIZED"
    elif fault == "pagination":
        bars["next_url"] = "https://example.invalid/continuation?apiKey=PRIVATE"
    else:
        bars["trade_permitted"] = True
    result = inspected(bars, metadata, query, fetched)
    assert result["input_status"] == "INVALID"
    assert "PRIVATE" not in json.dumps(result)
    assert_closed(result)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticker", "MESZ6"),
        ("session_end_date", "2026-01-02"),
        ("window_start", 1791469800000000001),
        ("window_start", 1.5),
        ("window_start", True),
        ("volume", -1),
        ("volume", True),
        ("transactions", -1),
        ("open", "PRIVATE"),
        ("high", 4999),
        ("close", 0),
    ],
)
def test_invalid_bars_are_rejected_without_echoing_values(field, value):
    bars, metadata, query, fetched = fixture()
    bars["results"][0][field] = value
    result = inspected(bars, metadata, query, fetched)
    assert result["input_status"] == "INVALID"
    assert "PRIVATE" not in json.dumps(result)
    assert_closed(result)


@pytest.mark.parametrize("fault", ["duplicate", "overlap", "unfinished", "future_clock"])
def test_candle_boundaries_reject_duplicates_overlaps_and_unfinished_intervals(fault):
    bars, metadata, query, fetched = fixture()
    if fault == "duplicate":
        bars["results"].append(bars["results"][0])
    elif fault == "overlap":
        bars["results"][0]["window_start"] -= 1000
    elif fault == "unfinished":
        fetched -= timedelta(microseconds=1)
    else:
        fetched = fetched.replace(tzinfo=None)
    assert inspected(bars, metadata, query, fetched)["input_status"] == "INVALID"


@pytest.mark.parametrize("origin", ["synthetic", "unverified"])
def test_conversion_does_not_qualify_health_license_or_policy(origin):
    bars, metadata, query, fetched = fixture()
    result = inspected(bars, metadata, query, fetched, origin=origin)
    assert result["input_status"] == "VALID"
    assert result["data_health"]["state"] == "UNKNOWN"
    assert "missing_quality_evidence" in result["data_health"]["reasons"]
    assert (
        result["massive_adapter"]["bars_sha256"]
        == hashlib.sha256(json.dumps(bars).encode()).hexdigest()
    )
    assert_closed(result)
    with pytest.raises(ValueError, match="Origin"):
        inspected(bars, metadata, query, fetched, origin="licensed")


def test_cut_excludes_future_prices_and_does_not_relabel_later_capture():
    bars, metadata, query, fetched = fixture()
    cut = fetched - timedelta(minutes=10)
    result = inspected(bars, metadata, query.model_copy(update={"as_of": cut}), fetched)
    assert len(result["normalized_snapshot"]["candles"]) == 1
    assert result["counts"] == {"input_bars": 3, "reviewed_bars": 1, "excluded_bars": 2}
    assert "future_capture" in result["data_health"]["reasons"]
    assert result["normalized_snapshot"]["fetched_at"] == "2026-01-01T12:15:00Z"


def test_gaps_and_off_tick_prices_remain_visible():
    bars, metadata, query, fetched = fixture()
    del bars["results"][1]
    bars["results"][0]["close"] = 5000.01
    result = inspected(bars, metadata, query, fetched)
    assert "unverified_session_gap" in result["data_health"]["reasons"]
    assert "off_tick_bar" in result["data_health"]["reasons"]
    assert len(result["normalized_snapshot"]["candles"]) == 2


def test_empty_cut_cannot_expose_later_source_prices():
    bars, metadata, query, fetched = fixture()
    result = inspected(
        bars, metadata, query.model_copy(update={"as_of": fetched - timedelta(minutes=15)}), fetched
    )
    assert result["normalized_snapshot"] is None
    assert result["counts"]["reviewed_bars"] == 0
    assert result["data_health"]["reasons"] == ["missing_market"]


def test_cut_one_microsecond_before_source_interval_end_is_rejected():
    bars, metadata, query, fetched = fixture()
    query = query.model_copy(update={"as_of": fetched - timedelta(microseconds=1)})
    result = inspected(bars, metadata, query, fetched)
    assert result["input_status"] == "INVALID"
    assert result["normalized_snapshot"] is None
    assert_closed(result)


def test_extreme_prices_cannot_crash_the_existing_decimal_tick_guard():
    bars, metadata, query, fetched = fixture()
    payload = json.dumps(bars).encode()
    for value in (b"5000.25", b"5001", b"5000.75", b"5000"):
        payload = payload.replace(value, b"1e999999")
    result = inspect_massive(
        payload, json.dumps(metadata).encode(), query, resolution="5min", fetched_at=fetched
    )
    assert result["input_status"] == "INVALID"
    assert_closed(result)


@pytest.mark.parametrize(
    "payload",
    [b"{", b"null", b"[]", b' {"status":"OK","status":"OK"}', b'{"a":NaN}', b" " * 500001],
)
def test_bad_or_oversized_json_is_rejected(payload):
    bars, metadata, query, fetched = fixture()
    result = inspect_massive(
        payload, json.dumps(metadata).encode(), query, resolution="5min", fetched_at=fetched
    )
    assert result["input_status"] == "INVALID"
    if len(payload) > 500000:
        assert result["massive_adapter"]["bars_sha256"] is None
    assert_closed(result)


@pytest.mark.parametrize("resolution", ["1min", "1session", "1day"])
def test_unsupported_intervals_are_not_silently_aggregated(resolution):
    bars, metadata, query, fetched = fixture()
    with pytest.raises(ValueError, match="supported native"):
        convert(bars, metadata, query, fetched, resolution)


def arguments(paths, query, fetched):
    return [
        str(paths[0]),
        str(paths[1]),
        "--instrument",
        query.instrument_id,
        "--contract",
        query.contract,
        "--resolution",
        "5min",
        "--fetched-at",
        fetched.isoformat(),
        "--as-of",
        query.as_of.isoformat(),
    ]


def test_cli_reads_only_and_keeps_unknown_status(tmp_path, capsys):
    bars, metadata, query, fetched = fixture()
    paths = [tmp_path / "synthetic-bars.json", tmp_path / "synthetic-contract.json"]
    for path, obj in zip(paths, (bars, metadata), strict=True):
        path.write_text(json.dumps(obj))
    before = [p.read_bytes() for p in paths]
    assert main([*arguments(paths, query, fetched), "--origin", "synthetic"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["input_status"] == "VALID"
    assert result["evidence_label"] == "SYNTHETIC MECHANICS ONLY"
    assert_closed(result)
    assert [p.read_bytes() for p in paths] == before and len(list(tmp_path.iterdir())) == 2
    code = """
import os, sys
def guard(event, args):
    if event in {"socket.connect", "socket.bind", "sqlite3.connect", "subprocess.Popen"}:
        raise RuntimeError("Forbidden IO")
    if event == "open":
        path, mode, flags = args
        if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT):
            raise RuntimeError("Forbidden write")
        if isinstance(path, str) and os.path.basename(path).startswith(".env"):
            raise RuntimeError("Configuration read")
sys.addaudithook(guard)
from scripts.advisory_massive_intake import main
status = main(sys.argv[1:])
assert "core.config" not in sys.modules
assert "connectors.advisory.storage" not in sys.modules
raise SystemExit(status)
"""
    run = subprocess.run(
        [sys.executable, "-B", "-c", code, *arguments(paths, query, fetched)],
        cwd=ROOT,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert run.returncode == 2, run.stderr
    assert json.loads(run.stdout)["input_status"] == "VALID"


@pytest.mark.parametrize("option", ["--execute", "--allow-trading", "--api-key"])
def test_cli_has_no_execution_or_credential_options(option, capsys):
    bars, metadata, query, fetched = fixture()
    with pytest.raises(SystemExit) as raised:
        main([*arguments([Path("a"), Path("b")], query, fetched), option, "PRIVATE"])
    assert raised.value.code == 2
    assert "PRIVATE" not in capsys.readouterr().err
