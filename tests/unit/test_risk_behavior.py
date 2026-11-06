"""Risk math and governor boundaries use known observations, never live venues."""

from decimal import Decimal
from unittest.mock import AsyncMock

import numpy as np
import pytest

from agents.tier1_executive.risk_governor import RiskGovernor
from core.risk.risk_engine import RiskEngine
from tests.factories import portfolio, position, with_performance

pytestmark = pytest.mark.unit


def test_var_cvar_and_ratios_against_independent_calculations():
    returns = np.linspace(-0.05, 0.04, 100)
    engine = RiskEngine()
    assert engine.historical_var(returns) == pytest.approx(0.0455)
    assert engine.historical_cvar(returns) == pytest.approx(-returns[:5].mean())
    assert engine.historical_cvar(np.ones(3)) == 0
    assert engine.parametric_var(10000, 0.02, 0.99) == pytest.approx(465.2)
    assert engine.sharpe_ratio(returns) == pytest.approx(
        returns.mean() / returns.std(ddof=1) * np.sqrt(365.25)
    )
    assert engine.sortino_ratio(returns) == pytest.approx(
        returns.mean() / np.sqrt(np.mean(np.minimum(returns, 0) ** 2)) * np.sqrt(365.25)
    )
    assert engine.sharpe_ratio(np.zeros(30)) == 0
    assert engine.sharpe_ratio(np.ones(3)) == 0
    assert engine.sortino_ratio(np.ones(3)) == 0
    assert engine.sortino_ratio(np.ones(30)) == 0
    assert engine.sortino_ratio(-np.ones(30)) == pytest.approx(-np.sqrt(365.25))
    assert engine.calmar_ratio(0.2, 0.1) == 2
    assert engine.calmar_ratio(0.2, 0) == 0


def test_full_risk_snapshot_uses_durable_index_and_marked_nav():
    from tests.unit.test_portfolio_tracker import sample

    engine = RiskEngine()
    initial = engine.compute_metrics(with_performance(portfolio()))
    assert initial.daily_drawdown_pct == 0 and initial.sharpe_90d is None
    current = sample([-0.1])
    current.total_capital += Decimal(150)
    result = engine.compute_metrics(current, correlation_matrix=np.eye(2))
    assert result.max_drawdown_pct == 0.1
    assert result.monthly_drawdown_pct == 0.1
    assert result.effective_n == pytest.approx(2)
    assert result.total_capital == 285
    assert result.var_95_1d == 0


def test_diversification_and_concentration_aggregate_venues():
    engine = RiskEngine()
    assert engine.effective_n(np.empty((0, 0))) == 0
    assert engine.effective_n(np.zeros((2, 2))) == 0
    assert engine.effective_n(np.ones((2, 2))) == pytest.approx(1)
    book = portfolio(
        positions=[
            position(size="2", current_price="100"),
            position(exchange="kraken", size="3", current_price="100"),
        ]
    )
    assert engine.compute_concentration(book) == {"BTC/USDT": 0.05}
    assert engine.compute_concentration(portfolio(total_capital=0)) == {}


@pytest.fixture
def governor():
    agent = RiskGovernor()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = False
    agent.state.get_portfolio.return_value = portfolio()
    agent.publish = AsyncMock()
    return agent


@pytest.mark.parametrize(
    "daily,weekly,monthly,kind",
    [
        (0, 0, 0, None),
        (0.03, 0, 0, "DRAWDOWN_ALERT"),
        (0.05, 0, 0, "DRAWDOWN_PAUSE"),
        (0, 0.07, 0, "DRAWDOWN_HALT"),
        (0, 0, 0.12, "KillSwitchEvent"),
    ],
)
async def test_governor_thresholds_and_kill_switch_latch(governor, daily, weekly, monthly, kind):
    await governor._check_drawdown_limits(daily, weekly, monthly)
    if kind is None:
        governor.publish.assert_not_awaited()
    elif kind == "KillSwitchEvent":
        assert governor.publish.await_args.args[2] == kind
        governor.state.activate_kill_switch.assert_awaited_once()
        governor.state.is_kill_switch_active.return_value = True
        await governor._check_drawdown_limits(daily, weekly, monthly)
        assert governor.publish.await_count == 1
    else:
        assert governor.publish.await_args_list[0].args[1]["alert_type"] == kind
        if kind == "DRAWDOWN_HALT":
            assert governor.publish.await_args.args[2] == "HaltAllStrategies"


async def test_weekly_halt_persists_before_event_delivery(governor):
    async def published(*_args, **_kwargs):
        governor.state.activate_kill_switch.assert_awaited_once()

    governor.publish.side_effect = published
    await governor._halt_all_strategies()
    governor.state.activate_kill_switch.assert_awaited_once_with("weekly_drawdown_halt")


async def test_governor_uses_durable_index_and_ignores_legacy_redis_baselines(governor):
    value = with_performance(portfolio(total_capital=Decimal(285)))
    value.performance.unit_price = Decimal("0.9")
    governor.state.get_portfolio.return_value = value
    await governor.initialize()
    await governor._full_risk_scan()
    result = governor.state.set_risk_metrics.await_args.args[0]
    assert result.total_capital == 285 and result.daily_drawdown_pct == 0.1
    await governor.shutdown()
    governor.state.redis.get.assert_not_awaited()
    governor.state.redis.set.assert_not_awaited()


async def test_governor_keeps_hard_peak_drawdown_limit_and_missing_history_blocks(governor):
    from core.accounting.performance import PerformanceUnavailableError

    with pytest.raises(PerformanceUnavailableError):
        await governor._full_risk_scan()
    value = with_performance(portfolio())
    value.performance.unit_price = Decimal("0.75")
    for ref in (value.performance.day, value.performance.week, value.performance.month):
        ref.unit_price = Decimal("0.75")
    governor.state.get_portfolio.return_value = value
    await governor._full_risk_scan()
    governor.state.activate_kill_switch.assert_awaited_once()


async def test_governor_absent_state_leverage_and_concentration(governor):
    governor.state.get_portfolio.return_value = None
    await governor._full_risk_scan()
    assert await governor._get_current_capital() == 0
    governor.state.set_risk_metrics.assert_not_awaited()
    await governor._check_leverage(3)
    governor.publish.assert_not_awaited()
    await governor._check_leverage(3.1)
    assert governor.publish.await_args.args[1]["alert_type"] == "LEVERAGE_LIMIT"
    await governor._check_position_concentration(portfolio(positions=[]))
    await governor._check_position_concentration(portfolio(total_capital=0, positions=[position()]))
    await governor._check_position_concentration(portfolio(positions=[position(size="10")]))
    assert governor.publish.await_args.args[1]["alert_type"] == "POSITION_LIMIT"
    assert governor._drawdown(None, Decimal(10)) == 0
    assert governor._drawdown(Decimal(10), Decimal(11)) == 0


async def test_governor_alert_consumer_initializes_unwraps_and_closes(governor, monkeypatch):
    from tests.factories import FiniteConsumer

    consumer = FiniteConsumer(
        [{"payload": {"alert_type": "CONSECUTIVE_LOSSES", "affected_strategy_ids": ["trend"]}}]
    )
    original = consumer.stream

    async def requires_initialization():
        consumer.initialize.assert_awaited_once()
        async for value in original():
            yield value

    consumer.stream = requires_initialization
    monkeypatch.setattr(governor, "make_consumer", lambda topics: consumer)
    await governor._consume_alerts()
    consumer.shutdown.assert_awaited_once()


async def test_governor_cancels_sibling_loops_when_consumer_fails(governor, monkeypatch):
    import asyncio

    stopped = []

    async def loop():
        try:
            await asyncio.Event().wait()
        finally:
            stopped.append(True)

    async def fail():
        await asyncio.sleep(0)
        raise RuntimeError("consumer failed")

    monkeypatch.setattr(governor, "_risk_loop", loop)
    monkeypatch.setattr(governor, "_leverage_loop", loop)
    monkeypatch.setattr(governor, "_consume_alerts", fail)
    with pytest.raises(ExceptionGroup):
        await governor.run()
    assert len(stopped) == 2
