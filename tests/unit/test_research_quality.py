"""Synthetic defects, session uncertainty, per-window gating and archived evidence."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from pydantic import ValidationError

from connectors.advisory import openterminal as shared, openterminal_research as adapter
from connectors.advisory.research_journal import ResearchJournal
from connectors.advisory.storage import AdvisoryStore
from core.advisory.openterminal_research import TerminalResearch
from core.advisory.research_brief import indicator_explanations, quality_lines
from core.advisory.research_journal import ResearchSnapshot
from core.advisory.research_quality import CandleQuality, assess_candle_quality, unavailable_quality

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def series(count=80):
    return [
        {
            "time": int((NOW - timedelta(hours=count - i)).timestamp()),
            "open": 100 + i,
            "high": 102 + i,
            "low": 99 + i,
            "close": 101 + i,
            "volume": 100,
        }
        for i in range(count)
    ]


async def collect(monkeypatch, candles, *, metadata=None, status=200):
    monkeypatch.setattr(adapter, "utcnow", lambda: NOW)
    monkeypatch.setattr(shared, "utcnow", lambda: NOW)
    identity = {
        "schema_version": "openterminal-history-v1",
        "symbol": "BTC-USD",
        "requested_range": "6M",
        "provider": "binance",
        "interval": "1h",
        "interval_basis": "provider_request",
        "fetched_at": NOW.isoformat(),
        "cache_state": "fetched",
        **(metadata or {}),
    }

    def transport(request):
        if "/history/" in request.url.path:
            return httpx.Response(status, json={"metadata": identity, "candles": candles})
        if request.url.path.endswith("quotes"):
            return httpx.Response(
                200,
                json=[{"symbol": "BTC-USD", "price": 500, "currency": "USD", "source": "binance"}],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "symbol": "BTC-USD",
                    "title": "Bitcoin test fixture",
                    "link": "https://example.org/research",
                    "publisher": "Fixture",
                    "publishedAt": NOW.isoformat(),
                }
            ],
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as client:
        return await adapter.collect_terminal_research(client, "BTC-USD")


async def test_clean_continuous_series_has_supporting_counts_and_keeps_freshness_unknown(
    monkeypatch,
):
    report = await collect(monkeypatch, series())
    q = report.data_quality
    assert q.status == "usable" and q.received_candles == 80
    assert q.duplicate_timestamps == q.out_of_order_pairs == q.future_timestamps == 0
    assert q.gap_count == q.missing_intervals == q.irregular_intervals == 0
    assert q.largest_gap_seconds == 3600 and q.interval_seconds == 3600
    assert q.trend.allowed and q.momentum.allowed and q.volatility.allowed
    assert report.analysis.sma50 is not None and report.analysis.rsi14_simple is not None
    assert report.freshness == report.event_risk == "UNKNOWN"
    assert not report.trade_permitted and not report.execution_enabled


@pytest.mark.parametrize(
    "defect,field,reason",
    [
        ("duplicate", "duplicate_timestamps", "duplicate_timestamps"),
        ("reversed", "out_of_order_pairs", "out_of_order_timestamps"),
        ("future", "future_timestamps", "future_timestamps"),
        ("time", "invalid_timestamps", "invalid_timestamps"),
        ("ohlc", "invalid_candles", "invalid_candles"),
        ("volume", "invalid_candles", "invalid_candles"),
    ],
)
async def test_defects_expose_counts_without_sorting_or_repair_and_keep_other_feeds(
    monkeypatch, defect, field, reason
):
    values = series()
    if defect == "duplicate":
        values[-1]["time"] = values[-2]["time"]
    elif defect == "reversed":
        values[-2], values[-1] = values[-1], values[-2]
    elif defect == "future":
        values[-1]["time"] = int((NOW + timedelta(hours=1)).timestamp())
    elif defect == "time":
        values[-1]["time"] = None
    else:
        values[-1]["high" if defect == "ohlc" else "volume"] = -1
    original = [dict(row) for row in values]
    report = await collect(monkeypatch, values)
    q = report.data_quality
    assert q.status == "unavailable" and getattr(q, field) == 1 and reason in q.reasons
    assert (
        report.analysis is None
        and report.quote.price == Decimal(500)
        and len(report.headlines) == 1
    )
    assert next(s for s in report.sources if s.kind == "history").state == "invalid"
    assert all(not c.allowed for c in (q.trend, q.momentum, q.volatility))
    assert values == original
    assert all("حُجب" in text for _, text in indicator_explanations(None, q))


@pytest.mark.parametrize(
    "remove_index,trend_allowed,momentum_allowed",
    [(5, True, True), (40, False, True), (75, False, False)],
)
async def test_gaps_only_block_conclusions_whose_exact_trailing_window_is_affected(
    monkeypatch, remove_index, trend_allowed, momentum_allowed
):
    values = series()
    del values[remove_index]
    report = await collect(monkeypatch, values)
    q, a = report.data_quality, report.analysis
    assert q.status == "limited" and q.gap_count == q.missing_intervals == 1
    assert q.trend.allowed == trend_allowed
    assert q.momentum.allowed == q.volatility.allowed == momentum_allowed
    assert (a.sma50 is not None) == trend_allowed
    assert (a.rsi14_simple is not None) == (a.atr14_simple is not None) == momentum_allowed
    assert a.last_close == series()[-1]["close"]


@pytest.mark.parametrize("offset", [-60, 1800])
async def test_continuous_irregular_timestamp_spacing_blocks_affected_windows(monkeypatch, offset):
    values = series()
    values[-1]["time"] += offset
    report = await collect(monkeypatch, values)
    assert report.data_quality.irregular_intervals == 1
    assert report.data_quality.missing_intervals == 0
    assert not report.data_quality.momentum.allowed and report.analysis.rsi14_simple is None


async def test_stock_session_gaps_are_counted_without_inventing_missing_market_bars(monkeypatch):
    values = series()
    del values[75]
    report = await collect(monkeypatch, values, metadata={"provider": "yahoo"})
    q = report.data_quality
    assert q.status == "limited" and q.gap_count == 1
    assert q.missing_intervals is q.irregular_intervals is None
    assert q.continuity_basis == "session_unverified" and "session_calendar_unverified" in q.reasons
    assert q.trend.allowed and q.momentum.allowed and q.volatility.allowed
    assert report.analysis.rsi14_simple is not None


@pytest.mark.parametrize("interval", [None, "1M"])
async def test_unknown_and_calendar_intervals_do_not_become_fixed_seconds(monkeypatch, interval):
    report = await collect(
        monkeypatch,
        series(),
        metadata={
            "interval": interval,
            "interval_basis": "provider_request" if interval else "UNVERIFIED",
        },
    )
    q = report.data_quality
    assert q.status == "limited" and q.interval_seconds is None
    assert q.gap_count is q.missing_intervals is None
    assert q.trend.allowed


async def test_short_series_only_blocks_indicators_without_enough_samples(monkeypatch):
    report = await collect(monkeypatch, series(20))
    q, a = report.data_quality, report.analysis
    assert q.status == "limited" and q.trend.reasons == ("insufficient_samples",)
    assert a.sma20 is a.sma50 is None and a.trend == "insufficient"
    assert q.momentum.allowed and q.volatility.allowed and a.rsi14_simple is not None


async def test_reported_stale_cache_suppresses_all_conclusions_but_retains_clocks(monkeypatch):
    report = await collect(
        monkeypatch,
        series(),
        metadata={"cache_state": "stale", "fetched_at": (NOW - timedelta(minutes=5)).isoformat()},
    )
    q, a = report.data_quality, report.analysis
    assert q.status == "limited" and "stale_cache" in q.reasons
    assert a.sma20 is a.sma50 is a.rsi14_simple is a.atr14_simple is None
    assert a.last_close == series()[-1]["close"] and a.history_fetched_at == NOW - timedelta(
        minutes=5
    )
    assert all("حُجب" in text for _, text in indicator_explanations(a, q))


async def test_fetch_clock_cannot_precede_a_returned_candle(monkeypatch):
    report = await collect(
        monkeypatch, series(), metadata={"fetched_at": (NOW - timedelta(hours=2)).isoformat()}
    )
    assert report.data_quality.status == "unavailable" and report.analysis is None
    assert "inconsistent_fetch_time" in report.data_quality.reasons


async def test_unavailable_feed_has_unknown_counts_and_invalid_metadata_has_specific_reason(
    monkeypatch,
):
    report = await collect(monkeypatch, series(), status=502)
    assert report.data_quality.received_candles is report.data_quality.duplicate_timestamps is None
    assert report.data_quality.reasons == ("history_unavailable",)
    report = await collect(monkeypatch, series(), metadata={"symbol": "MSFT"})
    assert report.data_quality.reasons == ("invalid_metadata",) and report.analysis is None


async def test_quality_survives_snapshot_storage_without_reassessing_original_evidence(
    monkeypatch, tmp_path
):
    report = await collect(monkeypatch, series())
    journal = ResearchJournal(AdvisoryStore(str(tmp_path / "quality.sqlite3")))
    journal.watch("BTC-USD", True)
    snapshot = ResearchSnapshot(id="a" * 32, saved_at=NOW, report=report)
    journal.save(snapshot)
    assert journal.history("BTC-USD") == [snapshot]
    legacy = report.model_dump(mode="json")
    del legacy["data_quality"]
    old = TerminalResearch.model_validate(legacy)
    assert old.data_quality is None and old.analysis == report.analysis
    assert "لم تُفحص" in quality_lines(None)[0]
    old_payload = snapshot.model_dump(mode="json")
    old_payload["report"] = legacy
    original = json.dumps(old_payload)
    with journal.store.connect() as db:
        db.execute("UPDATE research_snapshots SET payload=? WHERE id=?", (original, snapshot.id))
    assert journal.history("BTC-USD")[0].report.data_quality is None
    journal.brief(now=NOW + timedelta(days=30))
    with journal.store.connect() as db:
        assert (
            db.execute(
                "SELECT payload FROM research_snapshots WHERE id=?", (snapshot.id,)
            ).fetchone()[0]
            == original
        )


async def test_contradictory_quality_or_exposed_blocked_metrics_are_rejected(monkeypatch):
    report = await collect(monkeypatch, series(), metadata={"cache_state": "stale"})
    value = report.model_dump(mode="json")
    value["analysis"]["rsi14_simple"] = "100"
    with pytest.raises(ValidationError):
        TerminalResearch.model_validate(value)
    value = report.data_quality.model_dump(mode="json")
    value["status"] = "usable"
    with pytest.raises(ValidationError):
        CandleQuality.model_validate(value)
    clean = (await collect(monkeypatch, series())).data_quality.model_dump(mode="json")
    for updates in ({"received_candles": 20}, {"continuity_basis": "session_unverified"}):
        with pytest.raises(ValidationError):
            CandleQuality.model_validate({**clean, **updates})
    value = (await collect(monkeypatch, series())).model_dump(mode="json")
    value["analysis"]["history_provider"] = "yahoo"
    with pytest.raises(ValidationError):
        TerminalResearch.model_validate(value)
    with pytest.raises(ValidationError):
        CandleQuality.model_validate(
            {
                **unavailable_quality("history_unavailable").model_dump(),
                "trend": {"allowed": True, "reasons": []},
            }
        )


def test_quality_never_infers_interval_or_current_freshness_from_regular_old_timestamps():
    times = tuple(NOW - timedelta(days=200 - i) for i in range(60))
    quality = assess_candle_quality(times, NOW)
    assert quality.status == "limited" and quality.interval_seconds is None
    assert "interval_unverified" in quality.reasons and quality.gap_count is None
    assert quality.trend.allowed
