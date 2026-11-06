"""Synthetic signal and risk boundaries; no historical performance testing."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backtesting.mes5m_signals import ResearchState, SyntheticWindow, propose_signal
from core.advisory.models import Candle

pytestmark = pytest.mark.unit
START = datetime(2026, 1, 6, 7, tzinfo=UTC)
DECISION = START + timedelta(minutes=65)


def bars():
    return tuple(
        Candle(
            open_time=START + timedelta(minutes=5 * i),
            close_time=START + timedelta(minutes=5 * (i + 1), microseconds=-1),
            open="5000",
            high="5001" if i < 12 else "5002",
            low="4999",
            close="5000" if i < 12 else "5001.25",
            volume="100" if i < 12 else "150",
        )
        for i in range(13)
    )


def ready(**changes):
    return ResearchState(
        exposure="FLAT", calendar_status="VERIFIED_SYNTHETIC", path_complete=True, **changes
    )


def test_signal_uses_closed_history_and_schedules_entry_sixty_seconds_later():
    result = propose_signal(SyntheticWindow(candles=bars()), at=DECISION, state=ready())
    assert result.decision == "SYNTHETIC_PLAN"
    assert result.side == "BUY"
    assert result.stop == Decimal("4998.75")
    assert result.target == Decimal("5006.25")
    assert result.scheduled_entry_at == datetime(2026, 1, 6, 8, 6, tzinfo=UTC)
    assert result.time_exit_at == datetime(2026, 1, 6, 9, 6, tzinfo=UTC)
    assert result.projected_risk_usd == Decimal("31.50")
    assert result.research_quantity == 1
    assert result.qualified_contracts == 0 and result.execution_permissions is False


@pytest.mark.parametrize(
    "delta,available,expected",
    [
        (59, True, "NOT_DUE"),
        (60, True, "SCHEDULED_SYNTHETIC_ONLY"),
        (60, False, "INCOMPLETE"),
        (60, None, "INCOMPLETE"),
        (61, True, "INCOMPLETE"),
    ],
)
def test_entry_timing_does_not_infer_fills_from_missing_or_late_information(
    delta, available, expected
):
    from backtesting.mes5m_signals import entry_timing_status

    plan = propose_signal(SyntheticWindow(candles=bars()), at=DECISION, state=ready())
    assert (
        entry_timing_status(
            plan, at=DECISION + timedelta(seconds=delta), previous_minute_available=available
        )
        == expected
    )
    assert plan.fill_observed is False and plan.performance_observation_valid is False


def test_historical_windows_and_future_information_are_rejected():
    with pytest.raises(PermissionError, match="Historical signal"):
        propose_signal(
            SyntheticWindow(origin="real_provider_sample", candles=bars()),
            at=DECISION,
            state=ready(),
        )
    with pytest.raises(ValueError, match="Future information"):
        propose_signal(
            SyntheticWindow(candles=bars()), at=DECISION - timedelta(microseconds=1), state=ready()
        )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"calendar_status": "UNKNOWN"}, "unknown_calendar"),
        ({"exposure": "UNKNOWN"}, "nonflat_or_unknown_exposure"),
        ({"exposure": "WORKING_ORDERS"}, "nonflat_or_unknown_exposure"),
        ({"exposure": "OPEN"}, "nonflat_or_unknown_exposure"),
        ({"exposure": "MINI"}, "nonflat_or_unknown_exposure"),
        ({"exposure": "MIXED"}, "nonflat_or_unknown_exposure"),
        ({"path_complete": False}, "incomplete_exposure_path"),
        ({"executed_entries": 2}, "daily_entry_limit"),
        ({"consecutive_losses": 5}, "loss_pause_no_automatic_resume"),
        ({"day_net_pnl": "-200"}, "no_risk_budget"),
    ],
)
def test_unsafe_state_cannot_create_a_plan(change, reason):
    state = ResearchState.model_validate(ready().model_dump() | change)
    plan = propose_signal(SyntheticWindow(candles=bars()), at=DECISION, state=state)
    assert plan.decision == "ABSTAIN" and reason in plan.reasons
    assert plan.research_quantity == 0


def test_gap_and_daily_reset_require_thirteen_new_bars():
    original = bars()
    for window in [original[1:], original[:5] + original[6:]]:
        plan = propose_signal(SyntheticWindow(candles=window), at=DECISION, state=ready())
        assert plan.decision == "ABSTAIN" and "warmup_or_gap_reset" in plan.reasons
    previous_day = original[0].model_copy(update={"open_time": START - timedelta(days=1)})
    with pytest.raises(ValueError, match="Invalid synthetic session"):
        propose_signal(
            SyntheticWindow(candles=(previous_day, *original[1:])), at=DECISION, state=ready()
        )


@pytest.mark.parametrize(
    "close,volume,expected",
    [
        ("5001", "150", "ABSTAIN"),
        ("5001.25", "149", "ABSTAIN"),
        ("5001.25", "150", "SYNTHETIC_PLAN"),
    ],
)
def test_breakout_is_strict_and_volume_threshold_inclusive(close, volume, expected):
    original = bars()
    current = original[-1].model_copy(update={"close": Decimal(close), "volume": Decimal(volume)})
    plan = propose_signal(
        SyntheticWindow(candles=(*original[:-1], current)), at=DECISION, state=ready()
    )
    assert plan.decision == expected


def test_short_geometry_and_budget_equality():
    original = bars()
    current = original[-1].model_copy(update={"low": Decimal("4998"), "close": Decimal("4998.75")})
    window = SyntheticWindow(candles=(*original[:-1], current))
    plan = propose_signal(window, at=DECISION, state=ready(day_net_pnl=Decimal("-163.50")))
    assert plan.side == "SELL" and plan.stop == Decimal("5002.25")
    assert plan.target == Decimal("4991.75")
    assert plan.projected_risk_usd == Decimal("36.50")
    blocked = propose_signal(window, at=DECISION, state=ready(day_net_pnl=Decimal("-163.51")))
    assert blocked.decision == "ABSTAIN"


@pytest.mark.parametrize("operation", ["entry", "mark", "exit"])
def test_missing_exposure_is_sticky_and_never_a_valid_performance_observation(operation):
    from backtesting.mes5m_signals import ExposurePath, record_unavailable

    path = ExposurePath(status="OPEN_REPORTED", last_event_at=DECISION)
    incomplete = record_unavailable(path, at=DECISION, operation=operation)
    again = record_unavailable(incomplete, at=DECISION + timedelta(seconds=1), operation="exit")
    assert again.status == "INCOMPLETE" and again.missing_data
    assert again.performance_observation_valid is False
    with pytest.raises(ValueError):
        ExposurePath.model_validate(again.model_dump() | {"status": "CLOSED_REPORTED"})
