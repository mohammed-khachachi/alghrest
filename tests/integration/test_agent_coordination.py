"""Agent lifecycle, shared guards and actual event envelopes across tier boundaries."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import agents.base_agent as base
from agents.tier2_intelligence.price_publisher import PricePublisher
from agents.tier4_strategies.trend_follower import TrendFollower
from core.data.models import AgentStatus, KafkaTopic, Timeframe
from tests.factories import FiniteConsumer, bar

pytestmark = pytest.mark.integration


class LifecycleAgent(base.BaseAgent):
    def __init__(self):
        super().__init__(40, 2, "lifecycle-test")
        self.initialize = AsyncMock()
        self.shutdown = AsyncMock()
        self.state = AsyncMock()
        self.producer = AsyncMock()

    async def initialize(self):
        pass

    async def run(self):
        await asyncio.Event().wait()

    async def shutdown(self):
        pass


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(base, "configure_logging", MagicMock())
    monkeypatch.setattr(base, "start_metrics_server", MagicMock())
    return LifecycleAgent()


async def test_run_failure_cancels_heartbeat_before_closing_connections(agent):
    heartbeat_started = asyncio.Event()
    heartbeat_stopped = asyncio.Event()

    async def heartbeat():
        heartbeat_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            heartbeat_stopped.set()

    async def run():
        await heartbeat_started.wait()
        raise RuntimeError("agent failure")

    agent._heartbeat_loop = heartbeat
    agent.run = run
    with pytest.raises(RuntimeError, match="agent failure"):
        await agent.start()
    assert heartbeat_stopped.is_set()
    assert agent.status == AgentStatus.SHUTDOWN
    agent.shutdown.assert_awaited_once()
    agent.producer.shutdown.assert_awaited_once()
    agent.state.shutdown.assert_awaited_once()
    agent.state.set_agent_status.assert_awaited_once_with(40, AgentStatus.RUNNING)


async def test_cancelled_agent_closes_resources_even_if_custom_shutdown_fails(agent):
    agent.shutdown.side_effect = RuntimeError("cleanup failed")
    running = asyncio.Event()

    async def run():
        running.set()
        await asyncio.Event().wait()

    agent.run = run
    task = asyncio.create_task(agent.start())
    await running.wait()
    task.cancel()
    await task
    agent.producer.shutdown.assert_awaited_once()
    agent.state.shutdown.assert_awaited_once()


async def test_startup_failure_shuts_down_partial_initialization(agent):
    agent.initialize.side_effect = ValueError("configuration")
    with pytest.raises(ValueError, match="configuration"):
        await agent.start()
    agent.producer.shutdown.assert_awaited_once()
    agent.state.shutdown.assert_awaited_once()


async def test_envelope_identity_and_error_counters(agent):
    payload = {"symbol": "BTC/USDT", "price": "100"}
    await agent.publish(KafkaTopic.PRICES_REALTIME, payload, "ohlcv")
    topic, envelope = agent.producer.send.await_args.args
    assert topic == envelope.topic == KafkaTopic.PRICES_REALTIME
    assert envelope.source_agent_id == 40 and envelope.payload == payload
    assert envelope.message_type == "ohlcv"
    await agent.publish(KafkaTopic.RISK_ALERTS, {"alert": "test"})
    assert agent.producer.send.await_args.args[1].message_type == KafkaTopic.RISK_ALERTS.value
    agent.record_processing_error("topic", "ValueError")
    health = await agent.health_check()
    assert health.messages_processed == 2 and health.messages_failed == 1
    consumer = agent.make_consumer([KafkaTopic.PRICES_REALTIME], "earliest")
    assert consumer.group_id.endswith(".lifecycle-test")
    assert consumer.auto_offset_reset == "earliest"


async def test_strategy_risk_cap_and_pause_requires_explicit_resume():
    strategy = TrendFollower()
    for _ in range(4):
        strategy.record_loss()
    assert not strategy.is_strategy_paused
    strategy.record_win()
    assert strategy._consecutive_losses == 0
    for _ in range(5):
        strategy.record_loss()
    assert strategy.is_strategy_paused
    strategy.record_win()
    assert strategy.is_strategy_paused
    strategy.resume()
    assert not strategy.is_strategy_paused
    assert strategy.risk_per_trade <= 0.01


async def test_tier2_envelope_is_consumed_by_real_strategy(monkeypatch):
    publisher = PricePublisher()
    publisher.producer = AsyncMock()
    candle = bar(timeframe=Timeframe.H4)
    await publisher.publish(KafkaTopic.PRICES_REALTIME, candle.model_dump(mode="json"), "ohlcv")
    envelope = publisher.producer.send.await_args.args[1].model_dump(mode="json")
    strategy = TrendFollower()
    strategy.state = AsyncMock()
    strategy.state.is_kill_switch_active.return_value = False
    strategy._evaluate = AsyncMock()
    consumer = FiniteConsumer(
        [
            {"message_type": "other"},
            {"message_type": "ohlcv", "payload": {}},
            envelope,
            {**envelope, "payload": bar(is_closed=False).model_dump(mode="json")},
        ]
    )
    monkeypatch.setattr(strategy, "make_consumer", lambda topics: consumer)
    await strategy.initialize()
    await strategy.run()
    strategy._evaluate.assert_awaited_once_with(candle.symbol)
    assert len(strategy._bars[candle.symbol]) == 1
    assert strategy._messages_failed == 1
    await strategy.shutdown()


async def test_halted_strategy_never_evaluates_incoming_prices(monkeypatch):
    strategy = TrendFollower()
    strategy.state = AsyncMock()
    strategy.state.is_kill_switch_active.return_value = True
    strategy._evaluate = AsyncMock()
    consumer = FiniteConsumer(
        [{"message_type": "ohlcv", "payload": bar(timeframe=Timeframe.H4).model_dump(mode="json")}]
    )
    monkeypatch.setattr(strategy, "make_consumer", lambda topics: consumer)
    monkeypatch.setattr("agents.tier4_strategies.trend_follower.asyncio.sleep", AsyncMock())
    await strategy.run()
    strategy._evaluate.assert_not_awaited()
