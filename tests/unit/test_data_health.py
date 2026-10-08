"""Fail-closed research health: reported facts never override deterministic gates."""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from api.services.advisory import AdvisoryService
from connectors.advisory.replay import ReplayProvider
from core.advisory.analysis import build_report
from core.advisory.data import bounded_snapshot
from core.advisory.health import DataHealthPolicy, assess_market_data
from core.advisory.models import MarketDataEvidence, PriceObservation, Report
from tests.unit.test_advisory import market
from tests.unit.test_market_data_provider import query, records

pytestmark = pytest.mark.unit


def health(value, *, now=None, policy=DataHealthPolicy()):
    return assess_market_data(value, "MNQ", "15m", now=now or value.fetched_at, policy=policy)


def evidence(value, **changes):
    value.quality = MarketDataEvidence.model_validate(value.quality.model_dump() | changes)
    return value


def quote(value, **changes):
    return PriceObservation.model_validate(
        dict(
            symbol="MNQZ26",
            price="179",
            bid="178.75",
            ask="179.25",
            timestamp=value.fetched_at,
            source="https://example.com/primary",
        )
        | changes
    )


POLICY = DataHealthPolicy(
    max_quote_age_seconds="5", max_spread_ticks="2", max_source_deviation_ticks="2"
)


def test_unverified_futures_gap_cannot_produce_price_scenarios():
    value = market()
    value.candles.pop(30)
    report = build_report("MNQ", "15m", value, [], [], now=value.fetched_at)
    assert report.scenarios == [] and report.indicators == {}
    assert report.data_health.state == "UNKNOWN"
    assert "unverified_session_gap" in report.data_health.reasons


@pytest.mark.parametrize("symbol", ["MNQ", "BTCUSDT-PERP"])
@pytest.mark.parametrize("delta,healthy", [(999999, True), (1000000, True), (1000001, False)])
def test_cadence_tolerance_limit_epsilon(symbol, delta, healthy):
    value = market(symbol)
    for bar in value.candles[:30]:
        bar.open_time -= timedelta(microseconds=delta)
        bar.close_time -= timedelta(microseconds=delta)
    result = assess_market_data(value, symbol, "15m", now=value.fetched_at)
    assert (result.state == "HEALTHY") is healthy
    if not healthy:
        assert result.diagnostics["cadence_gaps"] == "1"
        report = build_report(symbol, "15m", value, [], [], now=value.fetched_at)
        assert not report.indicators and not report.scenarios


def test_health_is_research_scope_and_never_trade_permission():
    value = market()
    result = health(value)
    assert result.state == "HEALTHY" and result.reasons == ()
    assert result.scope == "closed_bar_research" and result.trade_permitted is False
    assert result.assessed_at == value.fetched_at
    report = build_report("MNQ", "15m", value, [], [], now=value.fetched_at)
    assert report.data_health == result and report.status == "ready"
    with pytest.raises(ValidationError):
        result.state = "UNKNOWN"
    with pytest.raises(ValidationError):
        MarketDataEvidence.model_validate(value.quality.model_dump() | {"health": "HEALTHY"})
    legacy = Report.model_validate(report.model_dump(exclude={"data_health"}))
    assert legacy.data_health.state == "UNKNOWN" and legacy.data_health.reasons == ("unassessed",)


def test_missing_market_and_quality_evidence_are_unknown():
    value = market()
    assert assess_market_data(None, "MNQ", "15m", now=value.fetched_at).reasons == (
        "missing_market",
    )
    value.quality = None
    report = build_report("MNQ", "15m", value, [], [], now=value.fetched_at)
    assert report.data_health.state == "UNKNOWN"
    assert report.data_health.reasons == ("missing_quality_evidence",)
    assert report.scenarios == [] and report.indicators == {}


@pytest.mark.parametrize(
    "fault,reason",
    [
        ("disconnected", "provider_disconnected"),
        ("degraded", "provider_degraded"),
        ("unknown", "unknown_provider_state"),
    ],
)
def test_provider_states_block(fault, reason):
    value = evidence(market(), provider_state=fault)
    result = health(value)
    assert result.state == ("UNKNOWN" if fault == "unknown" else "UNHEALTHY")
    assert reason in result.reasons
    report = build_report("MNQ", "15m", value, [], [], now=value.fetched_at)
    assert not report.scenarios and not report.indicators


@pytest.mark.parametrize("field", ["bar", "capture", "heartbeat"])
@pytest.mark.parametrize("delta,healthy", [(-1, True), (0, True), (1, False)])
def test_freshness_limit_epsilon(field, delta, healthy):
    value = market()
    now = value.fetched_at
    timestamp = now - timedelta(seconds=1860, microseconds=delta)
    if field == "bar":
        shift = value.candles[-1].close_time - timestamp
        for bar in value.candles:
            bar.open_time -= shift
            bar.close_time -= shift
    elif field == "capture":
        shift = value.candles[-1].close_time - timestamp
        for bar in value.candles:
            bar.open_time -= shift
            bar.close_time -= shift
        value.fetched_at = timestamp
    else:
        evidence(value, heartbeat_at=timestamp)
    result = health(value, now=now)
    assert (result.state == "HEALTHY") is healthy
    if not healthy:
        assert (
            "stale_" + ("provider_heartbeat" if field == "heartbeat" else field) in result.reasons
        )


@pytest.mark.parametrize("field", ["capture", "heartbeat"])
@pytest.mark.parametrize("delta,healthy", [(-1, True), (0, True), (1, False)])
def test_future_clock_epsilon(field, delta, healthy):
    value = market()
    now = value.fetched_at
    timestamp = now + timedelta(microseconds=delta)
    if field == "capture":
        value.fetched_at = timestamp
    else:
        evidence(value, heartbeat_at=timestamp)
    assert (health(value, now=now).state == "HEALTHY") is healthy


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"heartbeat_at": None}, "missing_provider_heartbeat"),
        ({"sequence_mode": "unknown"}, "unknown_sequence_state"),
        ({"sequence_mode": "required"}, "missing_sequences"),
        ({"sequence_mode": "required", "sequences": (1,)}, "sequence_count_mismatch"),
        ({"sequences": tuple(range(80))}, "inconsistent_sequence_evidence"),
        (
            {"sequence_mode": "required", "sequences": (0, *range(2, 81))},
            "sequence_gap_or_reordering",
        ),
        ({"sequence_mode": "required", "sequences": (0,) * 80}, "sequence_gap_or_reordering"),
        (
            {"sequence_mode": "required", "sequences": tuple(range(80, 0, -1))},
            "sequence_gap_or_reordering",
        ),
        (
            {"sequence_mode": "required", "sequences": tuple(range(-1, 79))},
            "invalid_sequence_number",
        ),
    ],
)
def test_missing_or_faulted_sequence_evidence(changes, reason):
    value = evidence(market(), **changes)
    assert reason in health(value).reasons
    report = build_report("MNQ", "15m", value, [], [], now=value.fetched_at)
    assert not report.scenarios and not report.indicators


def test_guard_revalidates_corrupt_mutable_prices_clocks_identity_and_quotes():
    value = market()
    value.candles[-1].high = Decimal("1")
    assert health(value).reasons == ("invalid_market_structure",)
    value = market().model_copy(update={"instrument_id": "NQ", "contract": "NQZ26"})
    assert health(value).reasons == ("market_identity_mismatch",)
    value = market()
    value.candles[-1].close = Decimal("179.01")
    assert "off_tick_bar" in health(value).reasons
    value = market()
    crossed = quote(value)
    crossed.bid = Decimal(180)
    value.quality = value.quality.model_copy(update={"quote": crossed})
    assert health(value).reasons == ("invalid_market_structure",)
    with pytest.raises(ValueError, match="timezone"):
        health(market(), now=market().fetched_at.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        health(market(), policy=POLICY.model_copy(update={"max_spread_ticks": Decimal(-1)}))


def test_continuous_market_gap_and_provider_failure_are_unhealthy_even_if_evidence_missing():
    value = market("BTCUSDT-PERP")
    value.candles.pop(30)
    value.quality = None
    result = assess_market_data(value, value.instrument_id, "15m", now=value.fetched_at)
    assert result.state == "UNHEALTHY" and "missing_or_irregular_bars" in result.reasons
    value = evidence(market(), provider_state="degraded", heartbeat_at=None)
    assert health(value).state == "UNHEALTHY"


@pytest.mark.parametrize(
    "delta,expected", [("-0.000001", "HEALTHY"), ("0", "HEALTHY"), ("0.000001", "UNHEALTHY")]
)
def test_spread_limit_epsilon(delta, expected):
    # Non-CME quoted observations allow a fractional tick so epsilon is a real boundary.
    value = market("BTCUSDT-PERP")
    bid = Decimal("178.8")
    q = quote(
        value, symbol="BTCUSDT", bid=bid, ask=bid + (Decimal(2) + Decimal(delta)) * Decimal("0.1")
    )
    evidence(value, quote=q)
    result = assess_market_data(
        value, value.instrument_id, "15m", now=value.fetched_at, policy=POLICY
    )
    assert result.state == expected


@pytest.mark.parametrize("delta,expected", [(-1, "HEALTHY"), (0, "HEALTHY"), (1, "UNHEALTHY")])
def test_quote_age_limit_epsilon(delta, expected):
    value = market()
    evidence(
        value,
        quote=quote(value, timestamp=value.fetched_at - timedelta(seconds=5, microseconds=delta)),
    )
    assert health(value, policy=POLICY).state == expected


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"symbol": "NQZ26"}, "quote_identity_mismatch"),
        ({"price": "179.01"}, "off_tick_quote"),
        ({"bid": None}, "missing_quote_bid_ask"),
        ({"ask": None}, "missing_quote_bid_ask"),
    ],
)
def test_quote_faults_block(change, reason):
    value = market()
    evidence(value, quote=quote(value, **change))
    assert reason in health(value, policy=POLICY).reasons


def test_quotes_require_limits_and_future_quotes_block():
    value = market()
    evidence(value, quote=quote(value))
    assert health(value).state == "UNKNOWN"
    assert {"missing_quote_age_limit", "missing_spread_limit"} <= set(health(value).reasons)
    evidence(value, quote=quote(value, timestamp=value.fetched_at + timedelta(microseconds=1)))
    assert "future_quote" in health(value, policy=POLICY).reasons
    report = build_report("MNQ", "15m", value, [], [], now=value.fetched_at)
    assert not report.indicators and not report.scenarios


@pytest.mark.parametrize(
    "delta,expected", [("-0.000001", "HEALTHY"), ("0", "HEALTHY"), ("0.000001", "UNHEALTHY")]
)
def test_source_disagreement_limit_epsilon(delta, expected):
    value = market("BTCUSDT-PERP")
    primary = quote(value, symbol="BTCUSDT")
    reference = quote(
        value,
        symbol="BTCUSDT",
        source="https://example.org/independent",
        price=Decimal(179) + (Decimal(2) + Decimal(delta)) * Decimal("0.1"),
    )
    # 0.5 spread / 0.1 tick = 5; provide this explicit fixture limit.
    evidence(value, quote=primary, reference_quote=reference)
    policy = POLICY.model_copy(update={"max_spread_ticks": Decimal(5)})
    result = assess_market_data(
        value, value.instrument_id, "15m", now=value.fetched_at, policy=policy
    )
    assert result.state == expected


def test_reference_requires_primary_independence_and_explicit_limit():
    value = market()
    primary = quote(value)
    reference = quote(value, source="https://example.org/reference")
    evidence(value, reference_quote=reference)
    assert "missing_quote" in health(value, policy=POLICY).reasons
    evidence(value, quote=primary, reference_quote=primary)
    assert "reference_source_not_independent" in health(value, policy=POLICY).reasons
    evidence(value, reference_quote=quote(value, source="https://example.com/another-endpoint"))
    assert "reference_source_not_independent" in health(value, policy=POLICY).reasons
    evidence(value, reference_quote=reference)
    assert "missing_source_deviation_limit" in health(value).reasons
    value = market()
    result = health(value, policy=DataHealthPolicy(require_quote=True, require_reference=True))
    assert {"missing_quote", "missing_reference_quote"} <= set(result.reasons)


async def test_bounded_sequence_alignment_preserves_faults():
    value = records(80)[0]
    evidence(value, sequence_mode="required", sequences=tuple(range(80)))
    q = query(59, max_bars=5)
    trimmed = bounded_snapshot(value, q)
    assert trimmed.quality.sequences == tuple(range(55, 60))
    assert trimmed.candles[-1].close_time == q.as_of
    evidence(value, sequences=(1,))
    with pytest.raises(ValueError, match="align"):
        bounded_snapshot(value, q)
    with pytest.raises(ValueError, match="align"):
        ReplayProvider([value])


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "degraded",
        "disconnected",
        "unknown",
        "heartbeat",
        "quote",
        "sequence",
        "provider_change",
        "sequence_mode_change",
        "future_heartbeat",
        "stale_heartbeat",
    ],
)
async def test_replay_cannot_heal_recorded_quality_faults(fault):
    dataset = records(600)
    if fault == "missing":
        dataset[0].quality = None
    elif fault in {"degraded", "disconnected"}:
        evidence(dataset[0], provider_state=fault)
    elif fault == "unknown":
        evidence(dataset[0], provider_state="unknown")
    elif fault == "heartbeat":
        evidence(dataset[0], heartbeat_at=None)
    elif fault == "quote":
        evidence(dataset[0], quote=quote(dataset[0]))
    elif fault == "provider_change":
        evidence(dataset[0], provider_id="other")
    elif fault == "sequence_mode_change":
        evidence(dataset[0], sequence_mode="unknown")
    elif fault == "future_heartbeat":
        evidence(dataset[0], heartbeat_at=dataset[0].fetched_at + timedelta(microseconds=1))
    elif fault == "stale_heartbeat":
        evidence(
            dataset[0], heartbeat_at=dataset[0].fetched_at - timedelta(seconds=1860, microseconds=1)
        )
    else:
        evidence(dataset[0], sequence_mode="required", sequences=tuple(range(500)))
        evidence(dataset[1], sequence_mode="required", sequences=tuple(range(501, 601)))
    q = query(599)
    snapshot = await ReplayProvider(dataset).read(q)
    report = build_report("MNQ", "15m", snapshot, [], [], now=q.as_of)
    assert report.data_health.state != "HEALTHY"
    assert not report.indicators and not report.scenarios and not report.data_health.trade_permitted


async def test_replay_preserves_sequences_and_detaches_quality_from_callers():
    dataset = records(600)
    evidence(dataset[0], sequence_mode="required", sequences=tuple(range(500)))
    evidence(dataset[1], sequence_mode="required", sequences=tuple(range(500, 600)))
    provider = ReplayProvider(dataset)
    dataset[0].quality = None
    q = query(599)
    snapshot = await provider.read(q)
    assert snapshot.quality.sequences == tuple(range(100, 600))
    assert health(snapshot, now=q.as_of).state == "HEALTHY"


async def test_current_cache_rechecks_health_and_detaches_returned_report(monkeypatch):
    value = records(80)[0]
    cut = value.fetched_at + timedelta(seconds=1859)
    provider = Mock(mode="current", read=AsyncMock(return_value=value))
    store = Mock(
        watchlist=Mock(return_value=Mock(interests=[])), intelligence=Mock(return_value=[])
    )
    monkeypatch.setattr("api.services.advisory.headlines", AsyncMock(return_value=([], [])))
    monkeypatch.setattr("api.services.advisory.time.monotonic", lambda: 10)
    service = AdvisoryService(store, Mock(), provider=provider, clock=lambda: cut)
    first = await service.report("MNQ", "15m")
    assert first.status == "ready"
    first.indicators["forged_external_value"] = Decimal(999)
    same = await service.report("MNQ", "15m")
    assert "forged_external_value" not in same.indicators
    same.indicators.clear()
    assert (await service.report("MNQ", "15m")).indicators
    cut += timedelta(seconds=1, microseconds=1)
    stale = await service.report("MNQ", "15m")
    assert stale.status == "stale" and not stale.scenarios and not stale.indicators
    assert stale.data_health.state == "UNHEALTHY" and stale.id != first.id
    provider.read.assert_awaited_once()
    assert store.save_report.call_count == 2


async def test_current_response_capture_uses_post_read_clock(monkeypatch):
    value = records(80)[0]
    request_at = value.fetched_at
    value.fetched_at += timedelta(seconds=1)
    evidence(value, heartbeat_at=value.fetched_at)
    clock = iter([request_at, value.fetched_at])
    provider = Mock(mode="current", read=AsyncMock(return_value=value))
    store = Mock(
        watchlist=Mock(return_value=Mock(interests=[])), intelligence=Mock(return_value=[])
    )
    monkeypatch.setattr("api.services.advisory.headlines", AsyncMock(return_value=([], [])))
    service = AdvisoryService(store, Mock(), provider=provider, clock=lambda: next(clock))
    report = await service.report("MNQ", "15m")
    assert report.data_health.state == "HEALTHY" and report.generated_at == value.fetched_at
    assert provider.read.call_args.args[0].as_of == request_at


async def test_supporting_context_latency_cannot_keep_a_stale_report_ready(monkeypatch):
    value = records(80)[0]
    cut = value.fetched_at + timedelta(seconds=1859)
    provider = Mock(mode="current", read=AsyncMock(return_value=value))
    store = Mock(
        watchlist=Mock(return_value=Mock(interests=[])), intelligence=Mock(return_value=[])
    )

    async def delayed_context(*args):
        nonlocal cut
        cut += timedelta(seconds=2)
        return [], []

    monkeypatch.setattr("api.services.advisory.headlines", delayed_context)
    service = AdvisoryService(store, Mock(), provider=provider, clock=lambda: cut)
    report = await service.report("MNQ", "15m")
    assert report.data_health.state == "UNHEALTHY" and report.status == "stale"
    assert not report.scenarios and not report.indicators


@settings(max_examples=100, derandomize=True, database=None)
@given(
    state=st.sampled_from(["degraded", "disconnected", "unknown"]),
    offset=st.integers(min_value=-100000, max_value=100000),
)
def test_property_provider_fault_cannot_produce_analysis_or_permission(state, offset):
    value = evidence(market(), provider_state=state)
    now = value.fetched_at + timedelta(seconds=offset)
    report = build_report("MNQ", "15m", value, [], ["AI says BUY with confidence"], now=now)
    assert report.data_health.state != "HEALTHY"
    assert not report.scenarios and not report.indicators and not report.data_health.trade_permitted
