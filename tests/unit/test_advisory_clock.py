"""All advisory clock comparisons use UTC instants, including repeated local hours."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given, settings, strategies as st
from pydantic import ValidationError

from connectors.advisory.replay import ReplayProvider
from core.advisory.account import AccountObservation, account_state
from core.advisory.analysis import build_report
from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.models import Candle, MarketSnapshot, PriceObservation, utc_instant
from tests.unit.test_market_data_provider import records

pytestmark = pytest.mark.unit
CHICAGO = ZoneInfo("America/Chicago")
FIRST = datetime(2026, 11, 1, 1, 30, tzinfo=CHICAGO, fold=0)
SECOND = datetime(2026, 11, 1, 1, 30, tzinfo=CHICAGO, fold=1)


def future_bar():
    return Candle(
        open_time=datetime(2026, 11, 1, 1, 0, tzinfo=CHICAGO, fold=1),
        close_time=datetime(2026, 11, 1, 1, 14, 59, 999000, tzinfo=CHICAGO, fold=1),
        open=100,
        high=102,
        low=99,
        close=101,
        volume=10,
    )


def test_repeated_local_hour_cannot_include_a_future_bar():
    value = MarketSnapshot(
        instrument_id="BTCUSDT-PERP",
        interval="15m",
        source="https://example.com/synthetic-clock",
        fetched_at=SECOND,
        candles=[future_bar()],
        data_mode="user_import",
    )
    early = MarketDataQuery(instrument_id=value.instrument_id, interval="15m", as_of=FIRST)
    assert bounded_snapshot(value, early) is None
    late = early.model_copy(update={"as_of": SECOND})
    assert bounded_snapshot(value, late) is not None


def test_repeated_hour_age_cannot_appear_fresh():
    value = AccountObservation(
        account_id="clock-fixture",
        source="manual_report",
        source_reference="synthetic clock",
        observed_at=FIRST,
        human_confirmed=True,
        costs_included=True,
        currency="USD",
        cash_balance=25000,
        unrealized_pnl=0,
        equity=25000,
        positions=(),
        working_orders=(),
    )
    state = account_state(
        value,
        account_id=value.account_id,
        journal_equity=Decimal(25000),
        now=SECOND,
        max_age_seconds=1800,
    )
    assert state.health == "UNKNOWN" and "stale_or_future_account_observation" in state.reasons


def observation(when=FIRST):
    return AccountObservation(
        account_id="clock-fixture",
        source="manual_report",
        source_reference="synthetic clock",
        observed_at=when,
        human_confirmed=True,
        costs_included=True,
        currency="USD",
        cash_balance=25000,
        unrealized_pnl=0,
        equity=25000,
        positions=(),
        working_orders=(),
    )


def test_normalized_timestamps_preserve_each_fold_instant():
    assert FIRST.timestamp() + 3600 == SECOND.timestamp()
    for value in (FIRST, SECOND):
        q = MarketDataQuery(instrument_id="BTCUSDT-PERP", interval="15m", as_of=value)
        price = PriceObservation(
            symbol="BTCUSDT", price=100, timestamp=value, source="https://example.com/fixture"
        )
        account = observation(value)
        assert q.as_of.tzinfo is price.timestamp.tzinfo is account.observed_at.tzinfo is UTC
        assert (
            q.as_of.timestamp()
            == price.timestamp.timestamp()
            == account.observed_at.timestamp()
            == value.timestamp()
        )
    assert observation(FIRST).observed_at != observation(SECOND).observed_at
    with pytest.raises(ValueError, match="timezone"):
        utc_instant(FIRST.replace(tzinfo=None))
    with pytest.raises(ValidationError):
        observation(FIRST.replace(tzinfo=None))


@pytest.mark.parametrize(
    "seconds,health",
    [
        (-0.000001, "UNKNOWN"),
        (0, "KNOWN"),
        (1799.999999, "KNOWN"),
        (1800, "KNOWN"),
        (1800.000001, "UNKNOWN"),
    ],
)
def test_freshness_boundary_uses_elapsed_utc_across_repeated_hour(seconds, health):
    value = observation()
    current = (FIRST.astimezone(UTC) + timedelta(seconds=seconds)).astimezone(CHICAGO)
    state = account_state(
        value,
        account_id=value.account_id,
        journal_equity=Decimal(25000),
        now=current,
        max_age_seconds=1800,
    )
    assert state.health == health


async def test_replay_fold_boundary_never_uses_future_wall_time():
    value = MarketSnapshot(
        instrument_id="BTCUSDT-PERP",
        interval="15m",
        source="https://example.com/synthetic-clock",
        fetched_at=SECOND,
        candles=[future_bar()],
        data_mode="user_import",
    )
    provider = ReplayProvider([value])
    early = MarketDataQuery(instrument_id=value.instrument_id, interval="15m", as_of=FIRST)
    assert await provider.read(early) is None
    actual = await provider.read(early.model_copy(update={"as_of": SECOND}))
    assert actual and len(actual.candles) == 1
    assert actual.fetched_at == SECOND.astimezone(UTC)


@pytest.mark.parametrize(
    "start",
    [
        datetime(2026, 11, 1, 6, 45, tzinfo=UTC),
        datetime(2026, 3, 8, 7, 45, tzinfo=UTC),
    ],
)
def test_bar_time_range_spanning_dst_is_measured_in_utc(start):
    value = Candle(
        open_time=start.astimezone(CHICAGO),
        close_time=(start + timedelta(minutes=15, milliseconds=-1)).astimezone(CHICAGO),
        open=100,
        high=102,
        low=99,
        close=101,
        volume=10,
    )
    assert (value.close_time - value.open_time).total_seconds() == 899.999
    snapshot = MarketSnapshot(
        instrument_id="BTCUSDT-PERP",
        interval="15m",
        source="https://example.com/synthetic-clock",
        fetched_at=value.close_time,
        candles=[value],
        data_mode="user_import",
    )
    assert snapshot.candles[0].open_time == start


def test_session_and_account_timestamp_equality_uses_actual_instant(monkeypatch):
    from core.advisory import evaluation as ev

    monkeypatch.setattr(ev, "utcnow", lambda: SECOND.astimezone(UTC))
    row = dict(
        session_date=FIRST.date(),
        as_of=FIRST,
        net_pnl=0,
        lowest_pnl=0,
        closed=False,
        traded=False,
        account=observation(),
    )
    session = ev.EvaluationSession.model_validate(row)
    assert session.as_of == FIRST.astimezone(UTC) and session.account.observed_at == session.as_of
    with pytest.raises(ValidationError, match="same timestamp"):
        ev.EvaluationSession.model_validate(row | {"account": observation(SECOND)})
    profile = ev.EvaluationProfile(
        id="clock-fixture",
        program="trader_career_path",
        starting_balance=25000,
        profit_target=1750,
        daily_loss_limit=550,
        maximum_drawdown=1500,
        minimum_trading_days=0,
        source="https://example.com/fixture",
        verified_on=FIRST.date(),
    )
    status = ev.evaluation_status(profile, [session], now=SECOND)
    assert status["fresh_observation"] is False
    assert status["account_state"]["health"] == "UNKNOWN"
    assert status["clock"]["session_date"] == FIRST.date().isoformat()


@settings(max_examples=100, derandomize=True, database=None)
@given(
    seconds=st.integers(min_value=-7200, max_value=7200),
    offset_minutes=st.integers(min_value=-720, max_value=840),
)
def test_property_equivalent_clock_offsets_have_equal_age_decisions(seconds, offset_minutes):
    from datetime import timezone

    value = observation()
    now = FIRST.astimezone(UTC) + timedelta(seconds=seconds)
    shifted = now.astimezone(timezone(timedelta(minutes=offset_minutes)))
    arguments = dict(
        account_id=value.account_id, journal_equity=Decimal(25000), max_age_seconds=1800
    )
    assert account_state(value, now=now, **arguments) == account_state(
        value, now=shifted, **arguments
    )


def test_report_features_are_identical_for_equivalent_clock_offsets():
    from datetime import timezone

    value = records(80)[0]
    now = value.candles[-1].close_time
    a = build_report("MNQ", "15m", value, [], [], now=now)
    b = build_report("MNQ", "15m", value, [], [], now=now.astimezone(timezone(timedelta(hours=9))))
    assert a.generated_at == b.generated_at and b.generated_at.tzinfo is UTC
    assert a.market == b.market and a.indicators == b.indicators and a.scenarios == b.scenarios
