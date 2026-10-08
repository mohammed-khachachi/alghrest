"""Manual research contracts, price evidence and conditional scenarios."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError

from connectors.advisory.intelligence import TOPICS, normalize
from connectors.advisory.market import PublicMarkets
from connectors.advisory.news import headlines
from connectors.advisory.storage import AdvisoryStore
from core.advisory.analysis import build_report, risk_worksheet
from core.advisory.imports import CSVImport
from core.advisory.models import (
    Candle,
    EconomicCalendar,
    EventRiskPolicy,
    MarketDataEvidence,
    MarketSnapshot,
    RiskWorksheet,
    Watchlist,
)

pytestmark = pytest.mark.unit


def market(symbol="MNQ", count=80, age=0, volume=10):
    now = datetime.now(UTC) - timedelta(seconds=age)
    bars = []
    for i in range(count):
        start = now - timedelta(minutes=15 * (count - i))
        bars.append(
            Candle(
                open_time=start,
                close_time=start + timedelta(minutes=15, milliseconds=-1),
                open=100 + i,
                high=102 + i,
                low=99 + i,
                close=101 + i,
                volume=volume,
            )
        )
    return MarketSnapshot(
        instrument_id=symbol,
        interval="15m",
        source="https://example.com/chart",
        fetched_at=now,
        candles=bars,
        data_mode="user_import",
        contract="MNQZ26" if symbol == "MNQ" else None,
        quality=MarketDataEvidence(
            provider_id="explicit-synthetic-test-fixture",
            provider_state="active",
            heartbeat_at=now,
            sequence_mode="not_applicable",
        ),
    )


def clear_event_context(now, symbol="MNQ"):
    """Explicit synthetic policy/calendar, never a live release schedule or recommended SLO."""
    return dict(
        calendar=EconomicCalendar(
            id="synthetic-empty-calendar",
            version="fixture-v1",
            source="https://example.com/synthetic-calendar",
            observed_at=now,
            coverage_start=now - timedelta(days=1),
            coverage_end=now + timedelta(days=1),
            covered_markets=(symbol,),
            complete=True,
            provider_state="active",
            events=(),
        ),
        event_policy=EventRiskPolicy(
            id="synthetic-research-risk",
            version="fixture-v1",
            before_seconds=600,
            after_seconds=300,
            max_calendar_age_seconds=600,
            blocked_impacts=("high",),
        ),
    )


def test_report_keeps_provenance_math_and_separates_instrument():
    value = market()
    report = build_report("MNQ", "15m", value, [], [], **clear_event_context(value.fetched_at))
    assert report.status == "ready" and not report.execution_enabled
    assert report.market.source == value.source and report.probabilities == "not_calibrated"
    assert report.indicators["atr14"] == 3
    assert report.indicators["rsi14_simple"] == 100
    assert report.indicators["support20"] == 158
    assert len(report.scenarios) == 3
    up, down, _ = report.scenarios
    assert up.trigger < up.targets[0] < up.targets[1] and up.invalidation < up.trigger
    assert down.targets[1] < down.targets[0] < down.trigger < down.invalidation
    assert all(s.trigger % Decimal("0.25") == 0 for s in report.scenarios)
    with pytest.raises(ValueError, match="identity"):
        build_report("NQ", "15m", value, [], [])


@pytest.mark.parametrize(
    "value,status",
    [(None, "unavailable"), (market(age=3600), "stale"), (market(count=20), "insufficient")],
)
def test_missing_stale_short_data_never_generates_price_scenarios(value, status):
    report = build_report("MNQ", "15m", value, [], [])
    assert report.status == status and not report.scenarios


def test_zero_volume_flat_prices_and_continuous_market_gaps():
    value = market(volume=0)
    assert "rolling_vwap96" not in build_report("MNQ", "15m", value, [], []).indicators
    for bar in value.candles:
        bar.open = bar.high = bar.low = bar.close = Decimal(100)
    assert build_report("MNQ", "15m", value, [], []).status == "insufficient"
    value = market("BTCUSDT-PERP")
    value.candles.pop(30)
    assert build_report("BTCUSDT-PERP", "15m", value, [], []).status == "insufficient"


@pytest.mark.parametrize(
    "change",
    [
        dict(contract="NQZ26"),
        dict(contract="MNQ1!"),
        dict(instrument_id="FAKE"),
        dict(interval="1h"),
        dict(candles=[]),
    ],
)
def test_import_identity_contract_and_duration_are_checked(change):
    with pytest.raises(ValidationError):
        MarketSnapshot.model_validate(market().model_dump() | change)


def test_csv_rejects_ambiguous_dates_unfinished_duplicate_and_invalid_prices():
    request = dict(
        instrument_id="MNQ", interval="15m", source="https://example.com", contract="MNQZ26"
    )
    header = "time,open,high,low,close,volume\n"
    row = "2026-09-01T10:00:00Z,100,102,99,101,20\n"
    assert CSVImport(**request, csv=header + row).market().candles[0].close == 101
    for bad in (
        row.replace("Z", ""),
        row + row,
        row.replace("2026", "2099"),
        row.replace("100,102", "105,102"),
        row.replace("100,102", "NaN,102"),
    ):
        with pytest.raises((ValueError, ValidationError)):
            CSVImport(**request, csv=header + bad).market()
    with pytest.raises(ValueError, match="columns"):
        CSVImport(**request, csv="a,b\n1,2").market()


def test_worksheet_contract_point_values_fees_and_no_index_orders():
    request = dict(
        instrument_id="MNQ",
        account_value=50000,
        risk_percent="0.5",
        entry=20000,
        stop=19990,
        fees_per_unit=2,
        slippage_points=1,
    )
    result = risk_worksheet(RiskWorksheet(**request))
    assert result["loss_per_unit"] == "24" and result["size"] == "10"
    assert Decimal(result["estimated_loss_at_stop"]) <= Decimal(result["risk_budget"])
    assert risk_worksheet(RiskWorksheet(**(request | {"instrument_id": "NQ"})))["size"] == "1"
    for update in ({"instrument_id": "NASDAQ100"}, {"stop": 20000}):
        with pytest.raises(ValueError):
            risk_worksheet(RiskWorksheet(**(request | update)))
    with pytest.raises(ValidationError):
        RiskWorksheet(**(request | {"risk_percent": "1.01"}))


def test_storage_watchlist_reports_and_imports_survive_reopen(tmp_path):
    path = str(tmp_path / "research.sqlite3")
    store = AdvisoryStore(path)
    assert store.watchlist().instruments[:2] == ["NQ", "MNQ"]
    watchlist = Watchlist(instruments=["MNQ"], interests=["inflation"])
    store.set_watchlist(watchlist)
    value = market()
    store.import_market(value)
    report = build_report("MNQ", "15m", value, [], [])
    store.save_report(report)
    reopened = AdvisoryStore(path)
    assert reopened.watchlist() == watchlist
    assert reopened.market("MNQ", "15m") == value
    assert reopened.market("NQ", "15m") is None
    assert reopened.history()[0]["id"] == report.id
    assert reopened.report(report.id)["execution_enabled"] is False
    assert reopened.report("missing") is None
    for i in range(105):
        report.id = str(i)
        store.save_report(report)
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM reports").fetchone()[0] == 100
    with pytest.raises(Exception, match="closed database"):
        db.execute("SELECT 1")


def test_intelligence_allowlist_freshness_deduplication_and_redaction(tmp_path):
    value = {
        "timestamp": datetime.now(UTC).isoformat(),
        "payload": {
            "symbol": "MNQ",
            "summary": "Rates",
            "api_key": "never expose",
            "order": {"size": 20},
        },
    }
    normalized = normalize(value, "news.tagged")
    assert (
        normalized
        and "never expose" not in normalized["summary"]
        and "order" not in normalized["summary"]
    )
    assert normalize(value, "orders.pending") is None
    assert not any("order" in t or "fill" in t for t in TOPICS)
    assert normalize(value | {"timestamp": "2020-01-01T10:00:00+00:00"}, "news.tagged") is None
    assert normalize(value | {"timestamp": "2026-09-28T10:00:00"}, "news.tagged") is None
    store = AdvisoryStore(str(tmp_path / "a.db"))
    store.save_intelligence(normalized)
    store.save_intelligence(normalized)
    assert len(store.intelligence()) == 1


async def test_sources_use_public_get_and_keep_fx_price_and_timestamp():
    now = datetime.now(UTC)
    calls = []

    def respond(request):
        calls.append(request)
        if "coinbase" in request.url.host:
            return httpx.Response(
                200,
                json={"price": "0.9987", "bid": "0.9986", "ask": "0.9988", "time": now.isoformat()},
            )
        return httpx.Response(
            200, json={"lastPrice": "100", "closeTime": int(now.timestamp() * 1000)}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        feed = PublicMarkets(client)
        assert (await feed.spot("SOL/USDT")).price == 100
        fx = await feed.tether_usd()
        assert fx.price == Decimal("0.9987") and fx.timestamp == now
        assert all(c.method == "GET" and "authorization" not in c.headers for c in calls)


async def test_futures_closed_bars_only_and_optional_derivatives_fail_explicitly():
    value = market("BTCUSDT-PERP")
    rows = [
        [
            int(b.open_time.timestamp() * 1000),
            str(b.open),
            str(b.high),
            str(b.low),
            str(b.close),
            str(b.volume),
            int(b.close_time.timestamp() * 1000),
        ]
        for b in value.candles
    ]
    rows.append(
        [
            int(datetime.now(UTC).timestamp() * 1000),
            "1",
            "1",
            "1",
            "1",
            "1",
            int((datetime.now(UTC) + timedelta(minutes=15)).timestamp() * 1000),
        ]
    )
    client = AsyncMock()
    client.get.side_effect = [
        httpx.Response(200, json=rows, request=httpx.Request("GET", "https://example.com")),
        httpx.ConnectError("source down"),
    ]
    result = await PublicMarkets(client).snapshot("BTCUSDT-PERP", "BTCUSDT", "15m")
    assert len(result.candles) == 80 and result.derivatives == {} and result.observations


async def test_news_returns_headlines_provenance_and_source_outages():
    from email.utils import format_datetime

    now = format_datetime(datetime.now(UTC))
    xml = f"<rss><channel><item><title>Federal Reserve rates</title><link>https://example.com/news</link><pubDate>{now}</pubDate></item><item><title>Old</title><link>https://example.com/old</link><pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate></item></channel></rss>"

    def respond(request):
        return httpx.Response(503 if "sec.gov" in request.url.host else 200, text=xml)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        news, errors = await headlines(client, "MNQ", ["rates"])
    assert len(news) == 1 and news[0].title == "Federal Reserve rates"
    assert len(errors) == 1 and "SEC" in errors[0]


def test_actual_agent_envelopes_supply_legacy_utc_signal_time_and_market_scope():
    from api.services.advisory import relevant
    from core.data.models import AgentMessage, KafkaTopic, MacroSignal, NewsSignal

    signal = MacroSignal(
        source_agent_id=8,
        direction="NEUTRAL",
        confidence=0.5,
        indicator_name="CPI",
        actual_value=3.1,
        regime="RISK_ON",
        country="US",
    )
    envelope = AgentMessage(
        source_agent_id=8,
        topic=KafkaTopic.MACRO_REGIME,
        message_type="macro_signal",
        payload=signal.model_dump(mode="json"),
    )
    normalized = normalize(envelope.model_dump(mode="json"), "macro.regime")
    assert normalized and normalized["symbol"] == "" and "3.1" in normalized["summary"]
    assert relevant(normalized, "MNQ")
    news = NewsSignal(
        source_agent_id=6,
        direction="NEUTRAL",
        confidence=0.5,
        symbol=None,
        headline="Bitcoin news",
        summary="Crypto only",
        source="example",
        url="https://example.com",
        impact_score=5,
        categories=[],
        entities=[],
        affected_symbols=["BTC/USDT"],
        published_at=datetime.now(UTC),
    )
    envelope.payload = news.model_dump(mode="json")
    normalized = normalize(envelope.model_dump(mode="json"), "news.tagged")
    assert normalized and relevant(normalized, "BTCUSDT") and not relevant(normalized, "MNQ")
    assert "Bitcoin news" in normalized["summary"]
