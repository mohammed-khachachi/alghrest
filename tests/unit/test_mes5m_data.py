"""Development isolation before prices are parsed; missing is never zero."""

import hashlib
from datetime import UTC, date, datetime, timedelta

import pytest

from backtesting.mes5m_data import development_snapshot, preflight_development
from scripts.advisory_firstrate_intake import _normalize

pytestmark = pytest.mark.unit
DAY = date(2026, 1, 6)
START = datetime(2026, 1, 6, 7, tzinfo=UTC)


def fixture(count=5, skip=()):
    rows = [
        f"2026-01-06 02:{i:02d}:00,5000.00,5001.00,4999.00,5000.25,{i + 1}"
        for i in range(count)
        if i not in skip
    ]
    # Excluded prices are intentionally unparsable, including future development minutes.
    rows.extend(
        [
            "2026-01-06 03:00:00,DO_NOT_PARSE_FUTURE_PRICES",
            "2026-01-27 03:00:00,DO_NOT_PARSE_VALIDATION_PRICES",
            "2026-02-18 03:00:00,DO_NOT_PARSE_HOLDOUT_PRICES",
        ]
    )
    return ("\n".join(rows) + "\n").encode()


def snapshot(payload, cut=START + timedelta(minutes=5), day=DAY):
    return development_snapshot(
        payload,
        day=day,
        as_of=cut,
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        normalizer=_normalize,
        origin="synthetic",
    )


def test_partition_and_asof_isolation_precede_ohlcv_parsing():
    result = snapshot(fixture())
    assert len(result.candles) == 1
    assert str(result.candles[0].volume) == "15"
    assert result.observed_minutes == 5
    assert result.missing_intervals == ()
    assert result.data_status == result.calendar_status == "PARTIAL"
    with pytest.raises(PermissionError):
        snapshot(b"not even a CSV", day=date(2026, 2, 18))


@pytest.mark.parametrize("delta, count", [(-1, 0), (0, 1), (1, 1)])
def test_true_completion_precedes_inclusive_candle_close(delta, count):
    result = snapshot(fixture(), cut=START + timedelta(minutes=5, microseconds=delta))
    assert len(result.candles) == count
    assert all(c.open_time + timedelta(minutes=5) <= result.as_of for c in result.candles)


def test_missing_minute_is_explicit_and_not_a_zero_volume_candle():
    result = snapshot(fixture(skip=(2,)))
    assert result.observed_minutes == 4
    assert result.candles == ()
    assert result.unavailable_complete_5m_intervals == 1
    assert len(result.missing_intervals) == 1
    gap = result.missing_intervals[0]
    assert gap.start == START + timedelta(minutes=2)
    assert gap.end_exclusive == START + timedelta(minutes=3)
    assert gap.classification == "UNCLASSIFIED_MISSING"
    assert result.performance_observation_valid is False


def test_wholly_absent_interval_remains_unknown():
    result = snapshot(b"2026-02-18 03:00:00,\xffUNPARSED_HOLDOUT\n")
    assert not result.candles
    assert result.observed_minutes == 0  # Count of observed rows, never market volume.
    assert result.candidate_minutes == 5
    assert result.missing_intervals[0].start == START
    assert result.missing_intervals[0].end_exclusive == START + timedelta(minutes=5)
    assert result.data_status == "PARTIAL"


@pytest.mark.parametrize("bad", [b"5000.10", b"NaN", b"0", b"-5"])
def test_selected_invalid_numeric_fields_are_rejected(bad):
    with pytest.raises(ValueError):
        snapshot(fixture().replace(b"5000.00", bad, 1))


@pytest.mark.parametrize("stamp", [b"2025-11-02 01:30:00", b"2026-03-08 02:30:00"])
def test_dst_ambiguous_and_nonexistent_timestamps_are_rejected(stamp):
    with pytest.raises(ValueError, match="Ambiguous or nonexistent"):
        snapshot(stamp + b",NOT_PARSED\n")


def test_duplicate_source_timestamps_rejected_without_sorting():
    payload = fixture()
    with pytest.raises(ValueError, match="unique and increasing"):
        snapshot(payload.splitlines()[0] + b"\n" + payload)


def test_cut_must_be_aware_and_inside_development_window():
    with pytest.raises(ValueError):
        snapshot(fixture(), cut=datetime(2026, 1, 6, 7, 5))
    for cut in [START - timedelta(microseconds=1), START + timedelta(hours=7, microseconds=1)]:
        with pytest.raises(PermissionError):
            snapshot(fixture(), cut=cut)


def test_pinned_real_source_identity_cannot_be_replaced_by_a_synthetic_hash():
    payload = fixture()
    with pytest.raises(ValueError, match="preserved MES identity"):
        development_snapshot(
            payload,
            day=DAY,
            as_of=START,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
            normalizer=_normalize,
            origin="real_provider_sample",
        )


def test_preflight_is_deterministic_and_does_not_report_prices_or_performance():
    payload = fixture().replace(b"2026-01-06 03:00:00,DO_NOT_PARSE_FUTURE_PRICES\n", b"")
    kwargs = dict(
        expected_sha256=hashlib.sha256(payload).hexdigest(),
        normalizer=_normalize,
        origin="synthetic",
    )
    result = preflight_development(payload, **kwargs)
    assert result == preflight_development(payload, **kwargs)
    assert result["candidate_dates"] == 22
    assert result["observed_native_minutes"] == 5
    assert result["complete_5m_bars"] == 1
    assert result["missing_minutes"] == 9235
    assert result["validation_access"] == result["holdout_access"] == "DENIED"
    assert all("candles" not in row and "volume" not in row for row in result["days"])
    assert result["performance_evaluation_performed"] is False
    assert result["sample_sufficiency"] == "UNKNOWN"


def test_excluded_day_and_asof_future_ohlcv_are_never_decoded():
    poison = b"2025-12-25 03:00:00,\xff\xfeSECRET\n" + fixture()
    assert len(snapshot(poison).candles) == 1
