"""Exercise production Kafka wrappers using deterministic broker I/O doubles.

The real broker restart/replay contract is covered by test_paper_runtime.py.
"""

import asyncio
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import orjson
import pytest
from aiokafka.errors import KafkaConnectionError
from aiokafka.structs import TopicPartition
from tenacity import wait_none

from core.data.models import AgentMessage, KafkaTopic
from core.orchestrator import message_bus as bus

pytestmark = pytest.mark.integration


@pytest.fixture
def broker(monkeypatch):
    producer = AsyncMock()
    consumer = MagicMock()
    for method in ("start", "stop", "commit", "end_offsets", "committed"):
        setattr(consumer, method, AsyncMock())
    monkeypatch.setattr(bus, "AIOKafkaProducer", MagicMock(return_value=producer))
    monkeypatch.setattr(bus, "AIOKafkaConsumer", MagicMock(return_value=consumer))
    monkeypatch.setattr(bus, "wait_exponential", lambda **kw: wait_none())
    return producer, consumer


def message():
    return AgentMessage(
        source_agent_id=14,
        topic=KafkaTopic.PROPOSALS_BUS,
        message_type="TradeProposal",
        payload={"size": "0.01"},
    )


async def test_producer_roundtrip_configuration_ordering_and_shutdown(broker):
    transport, _ = broker
    producer = bus.AlghrestProducer()
    await producer.initialize()
    config = bus.AIOKafkaProducer.call_args.kwargs
    assert config["acks"] == "all" and config["enable_idempotence"] is True
    assert config["key_serializer"]("BTC") == b"BTC"
    assert config["key_serializer"](None) is None
    for index in range(10):
        msg = message().model_copy(update={"payload": {"sequence": index}})
        await producer.send(KafkaTopic.PROPOSALS_BUS, msg, key="BTC")
    calls = transport.send_and_wait.await_args_list
    assert [c.kwargs["value"]["payload"]["sequence"] for c in calls] == list(range(10))
    assert all(c.args == ("proposals.bus",) and c.kwargs["key"] == "BTC" for c in calls)
    await producer.send("custom.topic", message())
    assert transport.send_and_wait.await_args.kwargs["key"] == "14"
    await producer.send_raw("custom.topic", {"raw": True})
    assert transport.send_and_wait.await_args.kwargs["value"] == {"raw": True}
    await producer.shutdown()
    transport.stop.assert_awaited_once()


async def test_transient_connection_and_send_recover_without_losing_message(broker):
    transport, _ = broker
    transport.start.side_effect = [KafkaConnectionError(), None]
    transport.send_and_wait.side_effect = [KafkaConnectionError(), None]
    producer = bus.AlghrestProducer()
    await producer.initialize()
    await producer.send(KafkaTopic.PROPOSALS_BUS, message())
    assert transport.start.await_count == 2
    assert transport.send_and_wait.await_count == 2
    assert transport.send_and_wait.await_args_list[0] == transport.send_and_wait.await_args_list[1]


async def test_permanent_publish_failure_is_not_reported_as_success(broker):
    transport, _ = broker
    transport.send_and_wait.side_effect = ValueError("invalid message")
    producer = bus.AlghrestProducer()
    await producer.initialize()
    with pytest.raises(ValueError, match="invalid message"):
        await producer.send(KafkaTopic.PROPOSALS_BUS, message())
    assert transport.send_and_wait.await_count == 1


async def test_operations_before_initialization_fail_closed():
    producer = bus.AlghrestProducer()
    consumer = bus.AlghrestConsumer("test", [KafkaTopic.PROPOSALS_BUS])
    with pytest.raises(RuntimeError):
        await producer.send(KafkaTopic.PROPOSALS_BUS, message())
    with pytest.raises(RuntimeError):
        await producer.send_raw("topic", {})
    with pytest.raises(RuntimeError):
        await anext(consumer.stream())
    with pytest.raises(RuntimeError):
        await consumer.process(AsyncMock())
    assert not await consumer.caught_up()
    assert await consumer.get_lag() == {}
    await producer.shutdown()
    await consumer.shutdown()


async def test_consumer_stream_commits_after_handling_and_scopes_group(broker):
    _, transport = broker
    record = SimpleNamespace(value={"payload": {"n": 1}}, topic="topic", partition=0, offset=4)
    transport.__aiter__.return_value = [record]
    consumer = bus.AlghrestConsumer("test", ["topic"], auto_offset_reset="earliest")
    await consumer.initialize()
    options = bus.AIOKafkaConsumer.call_args.kwargs
    assert options["enable_auto_commit"] is False
    assert options["group_id"].endswith(".test")
    assert options["auto_offset_reset"] == "earliest"
    assert options["key_deserializer"](b"x") == "x"
    assert options["key_deserializer"](None) is None
    stream = consumer.stream()
    assert await anext(stream) == record.value
    transport.commit.assert_not_awaited()
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    transport.commit.assert_awaited_once()
    await consumer.shutdown()
    transport.stop.assert_awaited_once()


@pytest.mark.parametrize("failure", ["handler", "commit"])
async def test_durable_processing_never_advances_past_failed_record(broker, failure):
    _, transport = broker
    transport.__aiter__.return_value = [
        SimpleNamespace(value={"n": i}, topic="topic", partition=2, offset=i) for i in range(3)
    ]
    consumer = bus.AlghrestConsumer("test", ["topic"])
    await consumer.initialize()
    handler = AsyncMock()
    if failure == "handler":
        handler.side_effect = [None, RuntimeError("crash")]
    else:
        transport.commit.side_effect = [None, RuntimeError("crash")]
    with pytest.raises(RuntimeError, match="crash"):
        await consumer.process(handler)
    assert handler.await_count == 2
    assert transport.commit.await_args_list[0].args[0] == {TopicPartition("topic", 2): 1}
    assert transport.commit.await_count == (1 if failure == "handler" else 2)


async def test_lag_and_readiness_handle_empty_uncommitted_and_rebalance(broker):
    _, transport = broker
    consumer = bus.AlghrestConsumer("test", ["topic"])
    await consumer.initialize()
    partition = TopicPartition("topic", 0)
    transport.assignment.return_value = set()
    assert not await consumer.caught_up()
    transport.assignment.return_value = {partition}
    transport.end_offsets.return_value = {partition: 10}
    transport.committed.return_value = None
    assert await consumer.get_lag() == {"topic:0": 10}
    assert not await consumer.caught_up()
    transport.committed.return_value = 10
    assert await consumer.caught_up()
    transport.assignment.side_effect = [{partition}, set()]
    assert not await consumer.caught_up()
    transport.assignment.side_effect = None
    transport.end_offsets.side_effect = KafkaConnectionError()
    assert await consumer.get_lag() == {}
    with pytest.raises(KafkaConnectionError):
        await consumer.caught_up()


def test_envelope_serialization_and_unsupported_payload():
    identifier = uuid4()
    assert bus._deserialize(bus._serialize({"id": identifier, "size": Decimal("0.5")})) == {
        "id": str(identifier),
        "size": 0.5,
    }
    assert orjson.loads(bus._serialize(message()))["source_agent_id"] == 14
    with pytest.raises(TypeError):
        bus._serialize(object())


async def test_cancelled_stream_exits_without_commit(broker):
    _, transport = broker

    async def cancelled():
        raise asyncio.CancelledError
        yield

    transport.__aiter__.side_effect = cancelled
    consumer = bus.AlghrestConsumer("test", ["topic"])
    await consumer.initialize()
    assert [item async for item in consumer.stream()] == []
    transport.commit.assert_not_awaited()
