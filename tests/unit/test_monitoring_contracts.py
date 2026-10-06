"""Regression coverage for Kafka lag and development-only audit telemetry."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import orjson
import pytest
from aiokafka import TopicPartition

from agents.tier7_monitoring.auditor_agent import AuditorAgent
from agents.tier7_monitoring.copy_trading_channel import CopyTradingAgent
from core.config import settings
from core.kafka import metrics_collector as kafka
from tests.factories import FiniteConsumer, proposal

pytestmark = pytest.mark.unit


@pytest.fixture
def collector():
    pipe = MagicMock(execute=AsyncMock())
    redis = MagicMock(pipeline=MagicMock(return_value=pipe))
    result = kafka.make_kafka_metrics_collector(redis)
    result._admin = AsyncMock()
    result._reader = AsyncMock()
    return result


async def test_metadata_uses_real_end_offsets_and_skips_internal_topics(collector):
    collector._admin.describe_topics.return_value = [
        {
            "topic": "prices",
            "error_code": 0,
            "partitions": [{"partition": 0, "error_code": 0}, {"partition": 1, "error_code": 0}],
        },
        {"topic": "__consumer_offsets", "error_code": 0},
        {"topic": "bad", "error_code": 1},
    ]
    collector._reader.end_offsets.return_value = {
        TopicPartition("prices", 0): 100,
        TopicPartition("prices", 1): 50,
    }
    data = await collector._fetch_metadata()
    assert data == {
        "prices": {"partition_count": 2, "total_offsets": 150, "end_offsets": {0: 100, 1: 50}}
    }
    assert len(collector._reader.end_offsets.call_args.args[0]) == 2


async def test_lag_is_end_minus_committed_not_committed_offset(collector):
    group = settings.kafka_consumer_group_prefix + ".reader"
    collector._admin.list_consumer_groups.return_value = [(group, "consumer"), ("foreign", "")]
    collector._admin.list_consumer_group_offsets.return_value = {
        TopicPartition("prices", 0): SimpleNamespace(offset=90),
        TopicPartition("prices", 1): SimpleNamespace(offset=55),
        TopicPartition("foreign", 0): SimpleNamespace(offset=10),
    }
    assert await collector._fetch_consumer_group_offsets(
        {("prices", 0): 100, ("prices", 1): 50}
    ) == {"prices": 10}
    collector._admin.list_consumer_group_offsets.assert_awaited_once_with(group)


async def test_uncommitted_group_offsets_are_unknown(collector):
    collector._admin.list_consumer_groups.return_value = [
        (settings.kafka_consumer_group_prefix + ".reader", "consumer")
    ]
    collector._admin.list_consumer_group_offsets.return_value = {
        TopicPartition("prices", 0): SimpleNamespace(offset=-1)
    }
    assert await collector._fetch_consumer_group_offsets({("prices", 0): 100}) == {}


async def test_poll_computes_rate_and_preserves_unknown_lag(collector, monkeypatch):
    collector._fetch_metadata = AsyncMock(
        return_value={
            "prices": {"total_offsets": 200, "partition_count": 1, "end_offsets": {0: 200}},
            "unobserved": {"total_offsets": 0, "partition_count": 1, "end_offsets": {0: 0}},
        }
    )
    collector._fetch_consumer_group_offsets = AsyncMock(return_value={"prices": 20})
    collector._prev_offsets = {"prices": 100}
    collector._prev_ts = 100
    monkeypatch.setattr(kafka.time, "time", lambda: 110)
    await collector._collect_once()
    records = {
        call.args[0]: orjson.loads(call.args[2])
        for call in collector._redis.pipeline().setex.call_args_list
    }
    assert records["alghrest:kafka:metrics:prices"]["messages_per_sec"] == 10
    assert records["alghrest:kafka:metrics:prices"]["consumer_lag_ms"] == 2000
    assert records["alghrest:kafka:metrics:unobserved"]["consumer_lag_ms"] is None
    collector._redis.pipeline().execute.assert_awaited_once()


async def test_unavailable_broker_does_not_fabricate_healthy_metrics(collector, monkeypatch):
    collector._admin = None
    monkeypatch.setattr(
        kafka, "AIOKafkaAdminClient", MagicMock(side_effect=RuntimeError("offline"))
    )
    await collector._collect_once()
    records = collector._redis.pipeline().setex.call_args_list
    assert records
    assert all(orjson.loads(call.args[2])["available"] is False for call in records)
    assert all(orjson.loads(call.args[2])["last_message_ts"] is None for call in records)
    with pytest.raises(RuntimeError):
        await collector._fetch_metadata()
    with pytest.raises(RuntimeError):
        await collector._fetch_consumer_group_offsets({})


async def test_poll_recovers_after_broker_outage(collector):
    collector._admin.describe_topics.side_effect = [
        RuntimeError("broker down"),
        [{"topic": "prices", "error_code": 0, "partitions": [{"partition": 0, "error_code": 0}]}],
    ]
    collector._reader.end_offsets.return_value = {TopicPartition("prices", 0): 10}
    collector._admin.list_consumer_groups.return_value = []
    await collector._collect_once()
    assert all(
        not orjson.loads(c.args[2])["available"]
        for c in collector._redis.pipeline().setex.call_args_list
    )
    collector._redis.pipeline().reset_mock()
    await collector._collect_once()
    assert orjson.loads(collector._redis.pipeline().setex.call_args.args[2])["available"]


async def test_collector_cancellation_closes_both_clients(collector):
    import asyncio

    admin, reader = collector._admin, collector._reader
    collector._collect_once = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await collector.run()
    reader.stop.assert_awaited_once()
    admin.close.assert_awaited_once()
    assert collector._reader is None and collector._admin is None


@pytest.mark.parametrize("environment", ["paper_trading", "live"])
async def test_auditor_refuses_synthetic_validation_outside_development(monkeypatch, environment):
    monkeypatch.setattr(settings, "environment", environment)
    agent = AuditorAgent()
    agent.state = AsyncMock()
    with pytest.raises(NotImplementedError):
        await agent.initialize()
    with pytest.raises(NotImplementedError):
        await agent._perform_walk_forward_validation()
    agent.state.activate_kill_switch.assert_not_awaited()
    agent.state.redis.hset.assert_not_awaited()


async def test_audit_demo_is_labelled_and_never_halts_trading(monkeypatch):
    monkeypatch.setattr(settings, "environment", "development")
    agent = AuditorAgent()
    agent.state = AsyncMock()
    agent.producer = AsyncMock()
    consumer = FiniteConsumer([{"message_type": "audit_request"}])
    monkeypatch.setattr(agent, "make_consumer", lambda topics: consumer)
    agent.state.is_kill_switch_active.return_value = False
    # Evaluate explicitly: the service loop is intentionally long running.
    await agent.initialize()
    await agent._perform_walk_forward_validation()
    assert agent.state.redis.hset.await_count == 32
    assert all(
        call.kwargs["mapping"]["simulated"] == "true"
        for call in agent.state.redis.hset.await_args_list
    )
    agent.state.activate_kill_switch.assert_not_awaited()
    agent.producer.send.assert_not_awaited()
    await agent.shutdown()
    consumer.shutdown.assert_awaited_once()


@pytest.mark.parametrize(
    "side,price,quote,confidence,expected",
    [
        ("BUY", "123.45", None, 0.9, "LONG"),
        ("SELL", None, {"price": "120"}, 0.9, "SHORT"),
        ("BUY", None, None, 0.9, None),
        ("BUY", None, {}, 0.9, None),
        ("BUY", None, {"price": "NaN"}, 0.9, None),
        ("BUY", "0", None, 0.9, None),
        ("BUY", "-1", None, 0.9, None),
        ("BUY", "100", None, 0.8, None),
    ],
)
async def test_copy_trading_uses_actual_price_and_filters_unusable_proposals(
    side, price, quote, confidence, expected, monkeypatch
):
    agent = CopyTradingAgent()
    await agent.broadcaster.close()
    agent.broadcaster = AsyncMock()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = False
    agent.state.get_json.return_value = quote
    p = proposal(side=side, limit_price=price, confidence_score=confidence, take_profit="150")
    consumer = FiniteConsumer([{"payload": p.model_dump(mode="json")}])
    monkeypatch.setattr(agent, "make_consumer", lambda topics: consumer)
    await agent.initialize()
    await agent.run()
    if expected:
        kwargs = agent.broadcaster.broadcast_signal.await_args.kwargs
        assert kwargs["direction"] == expected
        assert kwargs["price"] == float(price or quote["price"])
        assert kwargs["tp"] == 150 and kwargs["sl"] == 95
    else:
        agent.broadcaster.broadcast_signal.assert_not_awaited()
    await agent.shutdown()
    agent.broadcaster.close.assert_awaited_once()


async def test_copy_trading_rejects_malformed_and_halted_messages():
    agent = CopyTradingAgent()
    await agent.broadcaster.close()
    agent.broadcaster = AsyncMock()
    with pytest.raises(RuntimeError):
        await agent.run()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.side_effect = [True, False]
    agent.consumer = FiniteConsumer([{}, {}])
    await agent.run()
    assert agent._messages_failed == 1
    agent.broadcaster.broadcast_signal.assert_not_awaited()
