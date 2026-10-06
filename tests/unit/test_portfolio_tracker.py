"""Funding-adjusted, completed UTC daily observations and restart-safe metrics."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.tier7_monitoring.portfolio_tracker import PortfolioTracker
from core.accounting.models import BookState
from core.accounting.performance import PerformanceUnavailableError, observe
from core.data.performance import Performance
from tests.factories import portfolio, with_performance

pytestmark = pytest.mark.unit


def sample(returns):
    now = datetime(2026, 1, 1, tzinfo=UTC)
    book = BookState()
    perf = observe(None, "test", book, Decimal(150), now)
    nav = Decimal(150)
    for offset, change in enumerate(returns, start=1):
        nav *= Decimal(str(1 + change))
        perf = observe(perf, "test", book, nav, now + timedelta(days=offset))
    # Current intraday value must not enter daily Sharpe.
    perf = observe(perf, "test", book, nav, now + timedelta(days=len(returns) + 1))
    value = portfolio(
        total_capital=nav,
        snapshot_time=perf.observed_at,
        accounting_book_id="test",
        accounting_revision=0,
        performance=perf,
    )
    return value


@pytest.mark.parametrize("count", [0, 1, 19, 20, 60, 200])
def test_metrics_sample_threshold_and_calendar_sharpe(count):
    returns = np.random.default_rng(42).normal(0.001, 0.01, count)
    value = sample(returns)
    metrics = PortfolioTracker()._compute_metrics(value)
    selected = returns[-90:]
    assert metrics["daily_returns_observed"] == min(count, 90)
    if count < 20:
        assert metrics["sharpe_90d"] is metrics["sortino_90d"] is None
    else:
        expected = selected.mean() / selected.std(ddof=1) * np.sqrt(365.25)
        assert metrics["sharpe_90d"] == pytest.approx(round(expected, 3))
        downside = np.sqrt(np.mean(np.minimum(selected, 0) ** 2))
        assert metrics["sortino_90d"] == pytest.approx(
            round(selected.mean() / downside * np.sqrt(365.25), 3)
        )


@pytest.mark.parametrize("returns", [np.zeros(30), np.linspace(0.01, 0.03, 30)])
def test_no_downside_or_constant_series_is_not_invented(returns):
    metrics = PortfolioTracker()._compute_metrics(sample(returns))
    assert metrics["sortino_90d"] is None
    if not returns.any():
        assert metrics["sharpe_90d"] is None


def test_gap_does_not_become_a_daily_return():
    value = sample([0.01, 0.02, 0.03, 0.04])
    del value.performance.daily_closes[datetime(2026, 1, 3).date()]
    assert value.performance.daily_returns() == pytest.approx([0.01, 0.04])


def test_funding_does_not_change_drawdown_or_daily_returns():
    value = sample([-0.1])
    before = PortfolioTracker()._compute_metrics(value)
    value.total_capital += Decimal(150)
    value.performance.units += Decimal(150) / value.performance.unit_price
    after = PortfolioTracker()._compute_metrics(value)
    assert before["drawdown_pct"] == after["drawdown_pct"] == 10
    assert before["daily_returns_observed"] == after["daily_returns_observed"]
    assert after["nav"] == 285
    assert value.daily_pnl == value.weekly_pnl == 0


@pytest.mark.parametrize("fault", ["missing", "book", "revision", "timestamp"])
def test_unverified_performance_fails_closed(fault):
    value = with_performance(portfolio())
    if fault == "missing":
        value.performance = None
    elif fault == "book":
        value.performance.book_id = "foreign"
    elif fault == "revision":
        value.performance.revision += 1
    else:
        value.performance.observed_at -= timedelta(seconds=1)
    with pytest.raises(PerformanceUnavailableError):
        PortfolioTracker()._compute_metrics(value)


async def test_tracker_uses_book_cache_and_never_restores_legacy_redis_peaks():
    tracker = PortfolioTracker()
    tracker.state = AsyncMock()
    tracker.publish = AsyncMock()
    tracker.state.get_portfolio.return_value = sample([-0.1])
    await tracker.initialize()
    await tracker._snapshot()
    await tracker.shutdown()
    tracker.state.redis.get.assert_not_awaited()
    tracker.state.set_json.assert_awaited_once()
    assert tracker.state.set_json.await_args.args[0] == "portfolio_tracker:test:latest"
    assert tracker.publish.await_args.kwargs["payload"]["drawdown_pct"] == 10
    tracker.state.get_portfolio.return_value = None
    await tracker._snapshot()
    assert tracker.publish.await_count == 1


def test_restart_and_period_rollovers_keep_last_close_reference():
    now = datetime(2026, 5, 31, 23, 59, tzinfo=UTC)  # Sunday before month/week boundary
    book = BookState()
    perf = observe(None, "test", book, Decimal(150), now)
    perf = observe(perf, "test", book, Decimal(135), now + timedelta(seconds=30))
    restored = Performance.model_validate_json(perf.model_dump_json())
    perf = observe(restored, "test", book, Decimal("121.5"), now + timedelta(minutes=2))
    assert perf.peak == 1
    assert perf.drawdown() == 0.19
    assert perf.day.unit_price == perf.week.unit_price == perf.month.unit_price == Decimal("0.9")
    assert perf.drawdown(perf.month.unit_price) == 0.1
    assert perf.week.start == perf.month.start == datetime(2026, 6, 1).date()


def test_legacy_history_clock_reversal_and_foreign_history_are_not_reset():
    now = datetime.now(UTC)
    with pytest.raises(PerformanceUnavailableError):
        observe(None, "test", BookState(revision=1), Decimal(100), now)
    with pytest.raises(PerformanceUnavailableError):
        observe(None, "test", BookState(), Decimal(0), now)
    p = observe(None, "test", BookState(), Decimal(100), now)
    for book_id, revision, timestamp in [
        ("foreign", 0, now),
        ("test", 0, now - timedelta(seconds=1)),
    ]:
        with pytest.raises(PerformanceUnavailableError):
            observe(p, book_id, BookState(revision=revision), Decimal(100), timestamp)
    bankrupt = observe(p, "test", BookState(), Decimal(0), now)
    assert bankrupt.drawdown() == 1
    assert (
        observe(bankrupt, "test", BookState(), Decimal(-1), now + timedelta(days=1)).drawdown() > 1
    )
