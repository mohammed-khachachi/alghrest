"""Internal event risk: point-in-time evidence, boundaries and no AI override."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from api.services.advisory import AdvisoryService
from connectors.advisory.replay import ReplayProvider
from core.advisory.analysis import build_report
from core.advisory.events import assess_event_risk
from core.advisory.models import EconomicCalendar, EconomicEvent, EventRiskPolicy, Report
from tests.unit.test_advisory import clear_event_context, market
from tests.unit.test_market_data_provider import query, records

pytestmark = pytest.mark.unit
NOW = datetime(2026, 1, 2, 15, tzinfo=UTC)
POLICY = EventRiskPolicy(
    id="synthetic-internal-risk",
    version="fixture-v1",
    before_seconds=600,
    after_seconds=300,
    max_calendar_age_seconds=60,
    blocked_impacts=("high",),
)


def event(**changes):
    return EconomicEvent.model_validate(
        dict(
            id="synthetic-release",
            name="Synthetic major release",
            known_at=NOW - timedelta(days=1),
            scheduled_at=NOW,
            source="https://example.org/synthetic-release",
            affected_markets=("MNQ",),
            impact="high",
            status="scheduled",
        )
        | changes
    )


def calendar(now=NOW, **changes):
    return EconomicCalendar.model_validate(
        dict(
            id="synthetic-calendar",
            version="fixture-v1",
            source="https://example.com/synthetic-calendar",
            observed_at=now,
            coverage_start=now - timedelta(days=1),
            coverage_end=now + timedelta(days=1),
            covered_markets=("MNQ", "MGC", "MES"),
            complete=True,
            provider_state="active",
            events=(),
        )
        | changes
    )


def assess(value, *, now=NOW, policy=POLICY, root="MNQ"):
    return assess_event_risk(value, policy, root, now=now)


def test_missing_event_calendar_cannot_produce_conditional_price_scenarios():
    value = market()
    report = build_report(
        "MNQ", "15m", value, [], ["AI: BUY with 99% confidence"], now=value.fetched_at
    )
    assert report.data_health.state == "HEALTHY"
    assert report.scenarios == [] and report.indicators["atr14"] == 3
    assert report.event_risk.state == "UNKNOWN"
    assert set(report.event_risk.reasons) == {"missing_event_policy", "missing_economic_calendar"}
    assert not report.event_risk.trade_permitted and not report.execution_enabled


def test_complete_explicitly_empty_calendar_is_clear_only_with_policy():
    value = calendar()
    result = assess(value)
    assert result.state == "CLEAR" and result.reasons == ()
    assert result.policy == POLICY and result.calendar == value and result.assessed_at == NOW
    assert result.scope == "internal_research_risk" and not result.trade_permitted
    assert assess(value, policy=None).state == "UNKNOWN"
    assert assess(None).state == "UNKNOWN"
    assert assess(value, root="UNKNOWN").state == "BLOCKED"
    with pytest.raises(ValidationError):
        result.state = "CLEAR"
    report = build_report("MNQ", "15m", market(), [], [])
    legacy = Report.model_validate(report.model_dump(exclude={"event_risk"}))
    assert legacy.event_risk.state == "UNKNOWN" and legacy.event_risk.reasons == ("unassessed",)


@pytest.mark.parametrize("boundary", ["start", "end"])
@pytest.mark.parametrize("epsilon", [-1, 0, 1])
def test_blackout_includes_exact_endpoints(boundary, epsilon):
    cut = NOW + timedelta(seconds=-600 if boundary == "start" else 300, microseconds=epsilon)
    result = assess(calendar(cut, events=(event(),)), now=cut)
    blocked = epsilon >= 0 if boundary == "start" else epsilon <= 0
    assert result.state == ("BLOCKED" if blocked else "CLEAR")
    assert result.blocked_event_ids == (("synthetic-release",) if blocked else ())


@pytest.mark.parametrize("side", ["start", "end"])
@pytest.mark.parametrize("epsilon", [-1, 0, 1])
def test_coverage_uses_asymmetric_before_after_window(side, epsilon):
    changes = (
        {"coverage_start": NOW - timedelta(seconds=300) + timedelta(microseconds=epsilon)}
        if side == "start"
        else {"coverage_end": NOW + timedelta(seconds=600) + timedelta(microseconds=epsilon)}
    )
    result = assess(calendar(**changes))
    clear = epsilon <= 0 if side == "start" else epsilon >= 0
    assert result.state == ("CLEAR" if clear else "UNKNOWN")
    if not clear:
        assert "incomplete_event_window" in result.reasons


@pytest.mark.parametrize("epsilon,expected", [(-1, "CLEAR"), (0, "CLEAR"), (1, "UNKNOWN")])
def test_calendar_freshness_exact_boundary(epsilon, expected):
    value = calendar(observed_at=NOW - timedelta(seconds=60, microseconds=epsilon))
    assert assess(value).state == expected


@pytest.mark.parametrize("epsilon,expected", [(-1, "CLEAR"), (0, "CLEAR"), (1, "BLOCKED")])
def test_future_calendar_clock_exact_boundary(epsilon, expected):
    value = calendar(observed_at=NOW + timedelta(microseconds=epsilon))
    assert assess(value).state == expected


@pytest.mark.parametrize(
    "changes,reason,expected",
    [
        ({"complete": False}, "incomplete_calendar", "UNKNOWN"),
        ({"provider_state": "unknown"}, "unknown_calendar_provider", "UNKNOWN"),
        ({"provider_state": "degraded"}, "calendar_provider_degraded", "BLOCKED"),
        ({"provider_state": "disconnected"}, "calendar_provider_disconnected", "BLOCKED"),
        ({"covered_markets": ("MGC",)}, "uncovered_event_market", "UNKNOWN"),
    ],
)
def test_missing_coverage_or_provider_faults_block(changes, reason, expected):
    result = assess(calendar(**changes))
    assert result.state == expected and reason in result.reasons


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"scheduled_at": None}, "unknown_event_time:synthetic-release"),
        ({"impact": "unknown"}, "unknown_event_classification:synthetic-release"),
        ({"status": "unknown"}, "unknown_event_classification:synthetic-release"),
    ],
)
def test_uncertain_relevant_events_block(changes, reason):
    result = assess(calendar(events=(event(**changes),)))
    assert result.state == "UNKNOWN" and reason in result.reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"affected_markets": ("MGC",)},
        {"impact": "low"},
        {"impact": "medium"},
        {"status": "cancelled"},
        {"status": "cancelled", "scheduled_at": None},
        {"impact": "unknown", "scheduled_at": NOW + timedelta(seconds=601)},
        {"status": "unknown", "scheduled_at": NOW - timedelta(seconds=301)},
    ],
)
def test_known_irrelevant_or_cancelled_events_do_not_block(changes):
    assert assess(calendar(events=(event(**changes),))).state == "CLEAR"


@pytest.mark.parametrize(
    "changes",
    [
        {"coverage_end": NOW - timedelta(days=1)},
        {"covered_markets": ("MNQ", "MNQ")},
        {"covered_markets": ("FAKE",)},
        {"complete": "true"},
        {"events": (event(), event())},
        {"events": (event(known_at=NOW + timedelta(microseconds=1)),)},
        {"events": (event(affected_markets=("MYM",)),)},
        {"events": (event(scheduled_at=NOW + timedelta(days=2)),)},
        {"observed_at": NOW.replace(tzinfo=None)},
    ],
)
def test_calendar_rejects_duplicates_future_knowledge_unknown_scope_and_bad_clock(changes):
    with pytest.raises(ValidationError):
        calendar(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"affected_markets": ("MNQ", "MNQ")},
        {"affected_markets": ("FAKE",)},
        {"known_at": NOW.replace(tzinfo=None)},
    ],
)
def test_event_schema_rejects_unknown_identity_or_naive_knowledge(changes):
    with pytest.raises(ValidationError):
        event(**changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"before_seconds": -1},
        {"after_seconds": -1},
        {"max_calendar_age_seconds": -1},
        {"before_seconds": 604801},
        {"after_seconds": 604801},
        {"max_calendar_age_seconds": 604801},
        {"before_seconds": True},
        {"before_seconds": "10"},
        {"after_seconds": 0.5},
        {"blocked_impacts": ()},
        {"blocked_impacts": ("high", "high")},
        {"trade_permitted": True},
    ],
)
def test_policy_is_explicit_strict_bounded_and_cannot_supply_permission(changes):
    with pytest.raises(ValidationError):
        EventRiskPolicy.model_validate(POLICY.model_dump() | changes)


def test_guard_revalidates_model_copies_and_embedded_event_revisions():
    value = calendar().model_copy(update={"complete": "yes"})
    with pytest.warns(UserWarning, match="serializer warnings"):
        assert assess(value).reasons == ("invalid_economic_calendar",)
    bad_event = event().model_copy(update={"known_at": NOW + timedelta(seconds=1)})
    value = calendar().model_copy(update={"events": (bad_event,)})
    assert assess(value).state == "BLOCKED"
    policy = POLICY.model_copy(update={"before_seconds": -1})
    assert "invalid_event_policy" in assess(calendar(), policy=policy).reasons
    assert "invalid_economic_calendar" in assess({}).reasons
    assert "invalid_event_policy" in assess(calendar(), policy={}).reasons
    with pytest.raises(ValueError, match="timezone"):
        assess(calendar(), now=NOW.replace(tzinfo=None))


@pytest.mark.parametrize(
    "cut", [datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC)]
)
def test_unrepresentable_event_window_fails_closed(cut):
    start, end = (
        (cut, cut + timedelta(hours=1)) if cut.year == 1 else (cut - timedelta(hours=1), cut)
    )
    value = EconomicCalendar(
        id="extreme-clock-fixture",
        version="fixture-v1",
        source="https://example.com/calendar",
        observed_at=cut,
        coverage_start=start,
        coverage_end=end,
        covered_markets=("MNQ",),
        complete=True,
        provider_state="active",
        events=(),
    )
    result = assess(value, now=cut)
    assert result.state == "BLOCKED" and "invalid_event_clock_window" in result.reasons


def test_repeated_chicago_hour_cannot_hide_future_knowledge_or_shift_blackout():
    chicago = ZoneInfo("America/Chicago")
    observed = datetime(2026, 11, 1, 1, 50, tzinfo=chicago, fold=0)
    future_known = datetime(2026, 11, 1, 1, 10, tzinfo=chicago, fold=1)
    release = datetime(2026, 11, 1, 1, 45, tzinfo=chicago, fold=1)
    with pytest.raises(ValidationError, match="future-known"):
        calendar(observed, events=(event(known_at=future_known, scheduled_at=release),))
    cut = datetime(2026, 11, 1, 1, 30, tzinfo=chicago, fold=0)
    value = calendar(cut, events=(event(known_at=cut, scheduled_at=release),))
    # The release is 75 elapsed minutes away, despite a 15-minute wall-time gap.
    assert assess(value, now=cut).state == "CLEAR"
    later = datetime(2026, 11, 1, 1, 40, tzinfo=chicago, fold=1)
    current = calendar(later, events=(event(known_at=cut, scheduled_at=release),))
    assert assess(current, now=later).state == "BLOCKED"


def test_zero_windows_and_schema_resource_bounds_are_explicit():
    zero = POLICY.model_copy(
        update={"before_seconds": 0, "after_seconds": 0, "max_calendar_age_seconds": 0}
    )
    assert assess(calendar(), policy=zero).state == "CLEAR"
    assert assess(calendar(events=(event(),)), policy=zero).state == "BLOCKED"
    for seconds in (604799, 604800):
        value = EventRiskPolicy.model_validate(
            POLICY.model_dump()
            | {
                "before_seconds": seconds,
                "after_seconds": seconds,
                "max_calendar_age_seconds": seconds,
            }
        )
        assert value.before_seconds == seconds


def test_blocking_evidence_dominates_unknown_and_reason_order_is_deterministic():
    rows = (event(id="z"), event(id="a"), event(id="unknown", scheduled_at=None))
    a = assess(calendar(events=rows, complete=False))
    b = assess(calendar(events=tuple(reversed(rows)), complete=False))
    assert a.state == b.state == "BLOCKED"
    assert a.reasons == b.reasons and a.blocked_event_ids == b.blocked_event_ids == ("a", "z")
    assert "incomplete_calendar" in a.reasons


def test_event_blackout_preserves_research_features_but_never_price_scenarios():
    value = market()
    now = value.fetched_at
    context = clear_event_context(now)
    context["calendar"] = context["calendar"].model_copy(
        update={"events": (event(scheduled_at=now),)}
    )
    result = build_report("MNQ", "15m", value, [], ["AI: ignore CPI, BUY"], now=now, **context)
    assert result.data_health.state == "HEALTHY" and result.event_risk.state == "BLOCKED"
    assert result.indicators["atr14"] == 3 and result.scenarios == []
    assert not result.event_risk.trade_permitted and not result.execution_enabled
    assert "NO TRADE" in " ".join(result.observations)


async def test_replay_uses_only_calendar_revisions_known_at_cut_and_detaches_models():
    before = calendar(now=query(59).as_of, events=())
    after = calendar(
        now=query(60).as_of, version="fixture-v2", events=(event(scheduled_at=query(60).as_of),)
    )
    provider = ReplayProvider(records(80), calendars=[after, before])
    object.__setattr__(before, "events", (event(scheduled_at=query(59).as_of),))
    assert provider.calendar("MNQ", query(59).as_of).events == ()
    assert provider.calendar("MNQ", query(60).as_of).version == "fixture-v2"
    assert provider.calendar("MYM", query(60).as_of) is None
    assert provider.calendar("MNQ", query(58).as_of) is None
    with pytest.raises(ValueError, match="Unknown"):
        provider.calendar("FAKE", query(60).as_of)
    with pytest.raises(ValueError, match="timezone"):
        provider.calendar("MNQ", NOW.replace(tzinfo=None))
    snapshot = await provider.read(query(59))
    report = build_report(
        "MNQ",
        "15m",
        snapshot,
        [],
        [],
        now=query(59).as_of,
        calendar=provider.calendar("MNQ", query(59).as_of),
        event_policy=POLICY,
    )
    assert report.event_risk.state == "CLEAR" and len(report.scenarios) == 3
    later = await provider.read(query(60))
    blocked = build_report(
        "MNQ",
        "15m",
        later,
        [],
        [],
        now=query(60).as_of,
        calendar=provider.calendar("MNQ", query(60).as_of),
        event_policy=POLICY,
    )
    assert blocked.event_risk.state == "BLOCKED" and not blocked.scenarios


@pytest.mark.parametrize("fault", ["duplicate", "ambiguous", "mutated"])
def test_replay_rejects_duplicate_or_ambiguous_calendar_knowledge(fault):
    value = calendar()
    dataset = [value, value]
    if fault == "ambiguous":
        dataset = [value, value.model_copy(update={"version": "another-version"})]
    elif fault == "mutated":
        dataset = [value.model_copy(update={"observed_at": NOW.replace(tzinfo=None)})]
    with pytest.raises(ValueError):
        ReplayProvider([], calendars=dataset)


async def test_service_replay_uses_the_same_event_guard_without_live_calendar_io():
    cut = query(79).as_of
    value = calendar(cut, events=(event(known_at=cut, scheduled_at=cut),))
    provider = ReplayProvider(records(80), calendars=[value])
    store = Mock(save_report=Mock(), watchlist=Mock(side_effect=AssertionError("live watchlist")))
    service = AdvisoryService(
        store,
        Mock(),
        provider=provider,
        clock=lambda: cut,
        calendar_reader=provider.calendar,
        event_policy=POLICY,
    )
    result = await service.report("MNQ", "15m")
    assert result.event_risk.state == "BLOCKED" and result.scenarios == []
    assert result.event_risk.calendar == value and result.indicators["atr14"] == 3
    store.save_report.assert_called_once()
    store.watchlist.assert_not_called()


async def test_cached_clear_report_is_blocked_when_blackout_begins(monkeypatch):
    value = records(80)[0]
    cut = value.fetched_at + timedelta(seconds=10)
    release = event(known_at=value.fetched_at, scheduled_at=cut + timedelta(seconds=601))
    schedule = calendar(cut, events=(release,))
    reader = Mock(return_value=schedule)
    store = Mock(
        watchlist=Mock(return_value=Mock(interests=[])), intelligence=Mock(return_value=[])
    )
    provider = Mock(mode="current", read=AsyncMock(return_value=value))
    monkeypatch.setattr("api.services.advisory.headlines", AsyncMock(return_value=([], [])))
    monkeypatch.setattr("api.services.advisory.time.monotonic", lambda: 10)
    service = AdvisoryService(
        store,
        Mock(),
        provider=provider,
        clock=lambda: cut,
        calendar_reader=reader,
        event_policy=POLICY,
    )
    clear = await service.report("MNQ", "15m")
    assert clear.event_risk.state == "CLEAR" and len(clear.scenarios) == 3
    assert (await service.report("MNQ", "15m")).id == clear.id
    cut += timedelta(seconds=1)
    blocked = await service.report("MNQ", "15m")
    assert blocked.event_risk.state == "BLOCKED" and not blocked.scenarios
    assert blocked.id != clear.id and blocked.generated_at == cut
    provider.read.assert_awaited_once()
    # Losing calendar availability must not reuse cached clear scenarios.
    reader.side_effect = ValueError("unavailable calendar")
    unavailable = await service.report("MNQ", "15m")
    assert unavailable.event_risk.state == "UNKNOWN" and not unavailable.scenarios
    assert "missing_economic_calendar" in unavailable.event_risk.reasons


async def test_event_guard_uses_final_decision_clock_after_context_latency(monkeypatch):
    value = records(80)[0]
    cut = value.fetched_at + timedelta(seconds=10)
    schedule = calendar(
        cut, events=(event(known_at=value.fetched_at, scheduled_at=cut + timedelta(seconds=601)),)
    )
    provider = Mock(mode="current", read=AsyncMock(return_value=value))
    store = Mock(
        watchlist=Mock(return_value=Mock(interests=[])), intelligence=Mock(return_value=[])
    )

    async def delayed_context(*args):
        nonlocal cut
        cut += timedelta(seconds=1)
        return [], []

    monkeypatch.setattr("api.services.advisory.headlines", delayed_context)
    service = AdvisoryService(
        store,
        Mock(),
        provider=provider,
        clock=lambda: cut,
        calendar_reader=lambda root, now: schedule,
        event_policy=POLICY,
    )
    result = await service.report("MNQ", "15m")
    assert result.event_risk.state == "BLOCKED" and not result.scenarios


@settings(max_examples=100, derandomize=True, database=None)
@given(offset_microseconds=st.integers(min_value=-700_000_000, max_value=400_000_000))
def test_property_blackout_matches_independent_interval_oracle_and_blocks_ai(offset_microseconds):
    cut = NOW + timedelta(microseconds=offset_microseconds)
    value = calendar(cut, events=(event(),))
    result = assess(value, now=cut)
    blocked = -600_000_000 <= offset_microseconds <= 300_000_000
    assert result.state == ("BLOCKED" if blocked else "CLEAR")
    assert not result.trade_permitted


@settings(max_examples=50, derandomize=True, database=None)
@given(future_version=st.integers(min_value=1, max_value=100000))
def test_property_future_calendar_revisions_cannot_change_past_replay(future_version):
    cut = query(79).as_of
    past = calendar(cut)
    changed = calendar(
        cut + timedelta(minutes=1),
        version=f"future-{future_version}",
        events=(
            event(known_at=cut + timedelta(seconds=1), scheduled_at=cut + timedelta(minutes=1)),
        ),
    )
    a = ReplayProvider(records(80), calendars=[past])
    b = ReplayProvider(records(80), calendars=[past, changed])
    assert a.calendar("MNQ", cut) == b.calendar("MNQ", cut)

    async def reports():
        snapshots = await a.read(query(79)), await b.read(query(79))
        return [
            build_report(
                "MNQ",
                "15m",
                snapshot,
                [],
                [],
                now=cut,
                calendar=provider.calendar("MNQ", cut),
                event_policy=POLICY,
            )
            for provider, snapshot in zip((a, b), snapshots, strict=True)
        ]

    first, second = asyncio.run(reports())
    assert first.event_risk == second.event_risk and first.scenarios == second.scenarios
    assert len(first.scenarios) == len(second.scenarios) == 3


async def test_calendar_reader_latency_cannot_reuse_cached_clear_scenarios(monkeypatch):
    value = records(80)[0]
    cut = value.fetched_at + timedelta(seconds=10)
    release = event(known_at=value.fetched_at, scheduled_at=cut + timedelta(seconds=601))
    schedule = calendar(cut, events=(release,))
    delayed = False

    def reader(root, as_of):
        nonlocal cut
        if delayed:
            cut += timedelta(seconds=1)
        return schedule

    store = Mock(
        watchlist=Mock(return_value=Mock(interests=[])), intelligence=Mock(return_value=[])
    )
    provider = Mock(mode="current", read=AsyncMock(return_value=value))
    monkeypatch.setattr("api.services.advisory.headlines", AsyncMock(return_value=([], [])))
    monkeypatch.setattr("api.services.advisory.time.monotonic", lambda: 10)
    service = AdvisoryService(
        store,
        Mock(),
        provider=provider,
        clock=lambda: cut,
        calendar_reader=reader,
        event_policy=POLICY,
    )
    first = await service.report("MNQ", "15m")
    assert first.event_risk.state == "CLEAR" and len(first.scenarios) == 3
    delayed = True
    result = await service.report("MNQ", "15m")
    assert result.event_risk.state == "BLOCKED" and not result.scenarios
    provider.read.assert_awaited_once()
