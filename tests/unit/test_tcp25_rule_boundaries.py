"""TCP25 financial conformance examples, never firm eligibility or market evidence.

The existing policy/event/clock suites own generic boundaries and replay checks.
These cases exercise the actual TCP25 amounts together, without widening its
daily-loss rule to isolate drawdown. No personal-cap implementation is implied.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from backtesting.evaluation import EvaluationEvent, EvaluationTape, simulate_evaluation
from core.advisory.evaluation import initial_eod_state, project_eod_session, session_clock
from core.advisory.policy import tcp25_rules

pytestmark = pytest.mark.unit
D = Decimal


def _closed_sessions(pnls):
    rules = tcp25_rules()
    state = initial_eod_state(rules)
    projection = None
    for pnl in pnls:
        net = D(pnl)
        projection = project_eod_session(
            rules,
            state,
            net_pnl=net,
            lowest_pnl=min(D(0), net),
            traded=True,
            closed=True,
        )
        state = projection.financial
    assert projection is not None
    return projection


@pytest.mark.parametrize(
    "last_pnl,expected_balance,met",
    [("437.49", "26749.99", False), ("437.50", "26750.00", True), ("437.51", "26750.01", True)],
)
def test_tcp25_net_profit_target_after_four_balanced_sessions(last_pnl, expected_balance, met):
    value = _closed_sessions(["437.50", "437.50", "437.50", last_pnl])
    assert value.financial.balance == D(expected_balance)
    assert value.financial.floor == D(25000)
    assert value.financial.trading_days == 4
    assert value.consistency_met
    assert value.targets_met is met
    assert not value.daily_loss_breached and not value.drawdown_breached


@pytest.mark.parametrize(
    "best,last,consistent",
    [("524.99", "400.01", True), ("525.00", "400.00", False), ("525.01", "399.99", False)],
)
def test_tcp25_consistency_boundary_at_exact_1750_total(best, last, consistent):
    value = _closed_sessions([best, "425", "400", last])
    assert value.financial.balance == D(26750)
    assert value.financial.best_day == D(best)
    assert value.consistency_met is consistent
    assert value.targets_met is consistent
    # Concentration delays completion; it is not a financial disqualification.
    assert not value.daily_loss_breached and not value.drawdown_breached


def test_tcp25_three_profitable_days_do_not_satisfy_consistency_at_target():
    value = _closed_sessions(["600", "600", "550"])
    assert value.financial.balance == D(26750)
    assert value.financial.trading_days == 3
    assert not value.consistency_met and not value.targets_met
    assert tcp25_rules().minimum_trading_days == 0


@pytest.mark.parametrize("loss,total", [("-400", "0"), ("-500", "-100")])
def test_tcp25_nonpositive_total_keeps_best_day_and_never_completes(loss, total):
    value = _closed_sessions(["400", loss])
    assert value.financial.balance == D(25000) + D(total)
    assert value.financial.best_day == D(400)
    assert not value.consistency_met and not value.targets_met
    assert not value.daily_loss_breached and not value.drawdown_breached


@pytest.mark.parametrize("low,breached", [("-299.99", False), ("-300", True), ("-300.01", True)])
def test_tcp25_drawdown_boundary_after_losses_without_widening_daily_limit(low, breached):
    prior = _closed_sessions(["450"] * 4 + ["-500"] * 3).financial
    assert prior.balance == D(25300) and prior.floor == D(25000)
    value = project_eod_session(
        tcp25_rules(), prior, net_pnl=D(50), lowest_pnl=D(low), traded=True, closed=True
    )
    assert value.drawdown_breached is breached
    assert not value.daily_loss_breached
    assert value.financial.balance == D(25350)
    assert value.financial.floor == D(25000)


@pytest.mark.parametrize("fee,breached", [("0.99", False), ("1", True), ("1.01", True)])
def test_tcp25_realized_loss_open_equity_and_commissions_share_daily_budget(fee, breached):
    start = datetime(2026, 10, 6, 17, tzinfo=UTC)  # 12:00 Chicago, after rule snapshot.
    fields = [
        dict(
            kind="OPEN",
            position_id="mes",
            instrument_id="MES",
            contract="MESZ26",
            side="BUY",
            quantity=1,
            price=D(5000),
            commission_usd=D(2),
        ),
        dict(kind="CLOSE", position_id="mes", price=D(4990), commission_usd=D(3)),
        dict(
            kind="OPEN",
            position_id="mnq",
            instrument_id="MNQ",
            contract="MNQZ26",
            side="BUY",
            quantity=1,
            price=D(20000),
            commission_usd=D(fee),
        ),
        dict(kind="MARK", position_id="mnq", price=D(19753)),
        dict(kind="CLOSE", position_id="mnq", price=D(20000), commission_usd=D(1)),
    ]
    tape = EvaluationTape(
        id="synthetic-tcp25-combined-loss",
        version="1",
        origin="synthetic",
        source_reference="Hand-calculated accounting example; no firm calendar/ladder evidence",
        rules=tcp25_rules(),
        policy_confirmed=True,
        fills_complete=True,
        intraday_extrema_complete=False,
        events=tuple(
            EvaluationEvent(id=f"e{i}", at=start + timedelta(minutes=i), **row)
            for i, row in enumerate(fields)
        ),
    )
    value = simulate_evaluation(tape)
    marked = value.steps[3]
    assert marked.cash_balance == D(24945) - D(fee)  # MES net loss is $55.
    assert marked.unrealized_pnl == D(-494)  # One MNQ: -247 points at $2/point.
    assert marked.session_lowest_pnl == D(-549) - D(fee)
    assert ("daily_loss_boundary" in marked.breaches) is breached
    assert "unverified_intraday_extrema" in marked.unknowns
    if breached:
        assert value.outcome == "FAIL" and len(value.steps) == 4
    else:
        assert value.outcome == "CENSORED" and len(value.steps) == 5
        assert value.steps[-1].session_net_pnl == D(-56) - D(fee)
        assert value.steps[-1].session_lowest_pnl == D(-549) - D(fee)
    assert not value.rule_exact_verified
    assert not value.trade_permitted and not value.execution_enabled


@pytest.mark.parametrize(
    "rollover", [datetime(2026, 3, 9, 22, tzinfo=UTC), datetime(2026, 11, 2, 23, tzinfo=UTC)]
)
@pytest.mark.parametrize("seconds", [-1, 0, 1])
def test_tcp25_session_rollover_before_and_after_each_dst_change(rollover, seconds):
    value = session_clock(rollover + timedelta(seconds=seconds))
    expected = "2026-03-09" if rollover.month == 3 else "2026-11-02"
    if seconds >= 0:
        expected = "2026-03-10" if rollover.month == 3 else "2026-11-03"
    assert value["session_date"] == expected
    assert value["regular_hours_closed"] is (seconds < 0)


@pytest.mark.parametrize(
    "deadline",
    [datetime(2026, 3, 9, 20, 50, tzinfo=UTC), datetime(2026, 11, 2, 21, 50, tzinfo=UTC)],
)
@pytest.mark.parametrize("seconds,closed", [(-1, False), (0, True), (1, True)])
def test_tcp25_1550_chicago_deadline_tracks_both_dst_offsets(deadline, seconds, closed):
    value = session_clock(deadline + timedelta(seconds=seconds))
    assert value["regular_hours_closed"] is closed
    assert datetime.fromisoformat(value["required_flat_by"]).astimezone(UTC) == deadline
