from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from core.data.models import KafkaTopic
from core.orchestrator.message_bus import AlghrestConsumer

pytestmark = pytest.mark.asyncio


class FakeKafkaConsumer:
    def __init__(self, records: list[Any], events: list[str] | None = None) -> None:
        self.records = records
        self.events = events if events is not None else []
        self.commits: list[Any] = []
        self._index = 0

    def __aiter__(self) -> FakeKafkaConsumer:
        self._index = 0
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self.records):
            raise StopAsyncIteration
        record = self.records[self._index]
        self._index += 1
        return record

    async def commit(self, offsets: Any = None) -> None:
        self.events.append("commit")
        self.commits.append(offsets)


class FakeDlqProducer:
    def __init__(self, events: list[str] | None = None, fail: bool = False) -> None:
        self.events = events if events is not None else []
        self.fail = fail
        self.sent: list[dict[str, Any]] = []

    async def send_and_wait(
        self, topic: str, value: dict[str, Any], key: str | None = None
    ) -> None:
        self.events.append("dlq_publish")
        if self.fail:
            raise RuntimeError("DLQ unavailable")
        self.sent.append({"topic": topic, "value": value, "key": key})


def _record(
    topic: KafkaTopic,
    value: Any,
    *,
    partition: int = 0,
    offset: int = 0,
    key: str | bytes | None = "test-key",
) -> SimpleNamespace:
    return SimpleNamespace(
        topic=topic.value,
        partition=partition,
        offset=offset,
        key=key,
        value=value,
    )


def _consumer(
    records: list[Any],
    *,
    dlq_producer: FakeDlqProducer | None = None,
    events: list[str] | None = None,
    attempts: int = 3,
) -> tuple[AlghrestConsumer, FakeKafkaConsumer, FakeDlqProducer]:
    producer = dlq_producer or FakeDlqProducer(events)
    fake_consumer = FakeKafkaConsumer(records, events)
    consumer = AlghrestConsumer(
        agent_name="unit_consumer",
        topics=[records[0].topic] if records else [KafkaTopic.PROPOSALS_BUS],
        max_processing_attempts=attempts,
        dlq_producer=producer,
    )
    consumer._consumer = fake_consumer
    return consumer, fake_consumer, producer


def _committed_offset(commit_call: Any) -> int:
    offsets = list(commit_call.values())
    assert len(offsets) == 1
    return offsets[0]


async def test_poison_message_is_published_to_dlq_and_committed_after_publish() -> None:
    events: list[str] = []
    record = _record(
        KafkaTopic.PROPOSALS_BUS,
        {"proposal_id": "bad", "side": "INVALID"},
        partition=2,
        offset=41,
        key=b"proposal-41",
    )
    consumer, fake_consumer, dlq = _consumer([record], events=events, attempts=2)
    calls = 0

    async def handler(message: dict[str, Any]) -> None:
        nonlocal calls
        calls += 1
        assert message["proposal_id"] == "bad"
        raise ValueError("invalid proposal side")

    await consumer.process(handler)

    assert calls == 2
    assert events == ["dlq_publish", "commit"]
    assert len(dlq.sent) == 1
    assert dlq.sent[0]["topic"] == KafkaTopic.PROPOSALS_BUS_DLQ.value
    assert _committed_offset(fake_consumer.commits[0]) == 42


async def test_dlq_payload_contains_debugging_metadata() -> None:
    record = _record(
        KafkaTopic.RISK_ALERTS,
        {"alert_type": "KILL_SWITCH", "message": "halt"},
        partition=1,
        offset=7,
        key="risk-7",
    )
    consumer, _, dlq = _consumer([record], attempts=1)

    async def handler(_: dict[str, Any]) -> None:
        raise ValueError("risk alert schema mismatch")

    await consumer.process(handler)

    payload = dlq.sent[0]["value"]
    assert payload["original_topic"] == KafkaTopic.RISK_ALERTS.value
    assert payload["original_partition"] == 1
    assert payload["original_offset"] == 7
    assert payload["original_key"] == "risk-7"
    assert payload["original_value"]["message"] == "halt"
    assert payload["payload"] == payload["original_value"]
    assert payload["error_type"] == "ValueError"
    assert payload["error_message"] == "risk alert schema mismatch"
    assert "ValueError" in payload["stack_trace"]
    assert payload["failed_at"].endswith("Z")
    assert payload["consumer_name"] == "unit_consumer"
    assert payload["attempt_count"] == 1


async def test_transient_handler_error_retries_and_valid_messages_continue() -> None:
    records = [
        _record(KafkaTopic.ORDERS_EXECUTED, {"order_id": "one"}, offset=10),
        _record(KafkaTopic.ORDERS_EXECUTED, {"order_id": "two"}, offset=11),
    ]
    consumer, fake_consumer, dlq = _consumer(records, attempts=3)
    attempts_by_order: dict[str, int] = {}
    processed: list[str] = []

    async def handler(message: dict[str, Any]) -> None:
        order_id = str(message["order_id"])
        attempts_by_order[order_id] = attempts_by_order.get(order_id, 0) + 1
        if order_id == "one" and attempts_by_order[order_id] == 1:
            raise TimeoutError("temporary downstream timeout")
        processed.append(order_id)

    await consumer.process(handler)

    assert attempts_by_order == {"one": 2, "two": 1}
    assert processed == ["one", "two"]
    assert dlq.sent == []
    assert [_committed_offset(commit) for commit in fake_consumer.commits] == [11, 12]


async def test_dlq_publish_failure_does_not_commit_source_offset() -> None:
    record = _record(KafkaTopic.FILLS_CONFIRMED, {"fill_id": "bad"}, offset=5)
    dlq = FakeDlqProducer(fail=True)
    consumer, fake_consumer, _ = _consumer([record], dlq_producer=dlq, attempts=1)

    async def handler(_: dict[str, Any]) -> None:
        raise ValueError("bad fill payload")

    with pytest.raises(RuntimeError, match="DLQ unavailable"):
        await consumer.process(handler)

    assert fake_consumer.commits == []


async def test_stream_sends_malformed_json_to_dlq_and_continues_to_valid_message() -> None:
    events: list[str] = []
    bad_record = _record(
        KafkaTopic.ORDERS_PENDING,
        b"{not-json",
        offset=20,
        key="bad-json",
    )
    good_record = _record(
        KafkaTopic.ORDERS_PENDING,
        json.dumps({"order_id": "ok"}).encode(),
        offset=21,
        key="good-json",
    )
    consumer, fake_consumer, dlq = _consumer([bad_record, good_record], events=events)

    messages: list[dict[str, Any]] = []
    async for message in consumer.stream():
        messages.append(message)

    assert messages == [{"order_id": "ok"}]
    assert dlq.sent[0]["topic"] == KafkaTopic.ORDERS_PENDING_DLQ.value
    assert dlq.sent[0]["value"]["original_value"] == "{not-json"
    assert events == ["dlq_publish", "commit", "commit"]
    assert [_committed_offset(commit) for commit in fake_consumer.commits] == [21, 22]


async def test_existing_stream_behavior_yields_dict_payloads_and_commits() -> None:
    records = [
        _record(KafkaTopic.PROPOSALS_APPROVED, {"proposal_id": "one"}, offset=0),
        _record(KafkaTopic.PROPOSALS_APPROVED, {"proposal_id": "two"}, offset=1),
    ]
    consumer, fake_consumer, dlq = _consumer(records)

    messages: list[dict[str, Any]] = []
    async for message in consumer.stream():
        messages.append(message)

    assert messages == [{"proposal_id": "one"}, {"proposal_id": "two"}]
    assert dlq.sent == []
    assert [_committed_offset(commit) for commit in fake_consumer.commits] == [1, 2]
