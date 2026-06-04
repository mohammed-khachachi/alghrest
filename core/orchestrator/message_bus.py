"""
ALGHREST — Kafka Message Bus
Async producer/consumer base classes used by all 32 agents.

Design:
- aiokafka for native asyncio Kafka client
- Idempotent producer: acks=all + enable.idempotence=True
- LZ4 compression for all messages
- orjson for fast serialization
- Exponential backoff (tenacity) on connect failures
- Consumer: manual commits + Redis dedup for idempotent processing
- Each consumer group is named {prefix}.{agent_name} for isolation
"""

from __future__ import annotations

import asyncio
import traceback
from collections import namedtuple
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import orjson
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

try:
    from aiokafka import TopicPartition
except ImportError:  # pragma: no cover - used only by lightweight unit-test stubs
    TopicPartition = namedtuple("TopicPartition", ["topic", "partition"])  # type: ignore[misc]

from aiokafka.errors import (
    KafkaConnectionError,
    KafkaTimeoutError,
    NodeNotReadyError,
)
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from core.config import settings
from core.data.models import AgentMessage, KafkaTopic
from core.utils.metrics import kafka_messages_produced, kafka_produce_errors

logger = structlog.get_logger(__name__)

_TRANSIENT_ERRORS = (KafkaConnectionError, KafkaTimeoutError, NodeNotReadyError)
DEFAULT_MAX_PROCESSING_ATTEMPTS = 3
DLQ_TOPIC_BY_SOURCE: dict[str, str] = {
    KafkaTopic.PROPOSALS_BUS.value: KafkaTopic.PROPOSALS_BUS_DLQ.value,
    KafkaTopic.PROPOSALS_APPROVED.value: KafkaTopic.PROPOSALS_APPROVED_DLQ.value,
    KafkaTopic.ORDERS_PENDING.value: KafkaTopic.ORDERS_PENDING_DLQ.value,
    KafkaTopic.ORDERS_EXECUTED.value: KafkaTopic.ORDERS_EXECUTED_DLQ.value,
    KafkaTopic.FILLS_CONFIRMED.value: KafkaTopic.FILLS_CONFIRMED_DLQ.value,
    KafkaTopic.RISK_ALERTS.value: KafkaTopic.RISK_ALERTS_DLQ.value,
}


def _serialize(obj: Any) -> bytes:
    """orjson serializer that handles Pydantic models, UUIDs, Decimals, datetimes."""

    def _default(v: Any) -> Any:
        if isinstance(v, UUID):
            return str(v)
        if hasattr(v, "model_dump"):  # Pydantic v2
            return v.model_dump(mode="json")
        if hasattr(v, "__float__"):  # Decimal
            return float(v)
        if isinstance(v, datetime):
            return v.isoformat()
        raise TypeError(f"Not serializable: {type(v)}")

    return orjson.dumps(obj, default=_default)


def _deserialize(data: bytes) -> Any:
    return orjson.loads(data)


def _decode_key(key: Any) -> str | None:
    if key is None:
        return None
    if isinstance(key, bytes):
        return key.decode(errors="replace")
    return str(key)


def _json_safe(value: Any) -> Any:
    if isinstance(value, bytes | bytearray):
        try:
            return _deserialize(bytes(value))
        except Exception:
            return bytes(value).decode(errors="replace")
    try:
        return orjson.loads(_serialize(value))
    except Exception:
        return repr(value)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class AlghrestProducer:
    """
    Idempotent async Kafka producer. One instance per agent process.
    Call initialize() before use and shutdown() on exit.
    """

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None
        self._log = logger.bind(component="producer")

    async def initialize(self) -> None:
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_servers_list,
            value_serializer=_serialize,
            key_serializer=lambda k: k.encode() if k else None,
            acks="all",
            enable_idempotence=True,  # Exactly-once producer semantics
            compression_type="lz4",
            max_request_size=10_485_760,  # 10 MB
            request_timeout_ms=30_000,
            retry_backoff_ms=500,
        )

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(10),
        ):
            with attempt:
                await self._producer.start()
                self._log.info("producer connected", servers=settings.kafka_bootstrap_servers)

    async def send(
        self,
        topic: KafkaTopic | str,
        message: AgentMessage,
        key: str | None = None,
    ) -> None:
        """Publish an AgentMessage. Retries on transient failures."""
        if self._producer is None:
            raise RuntimeError("Producer not initialized — call initialize() first")

        topic_str = topic.value if isinstance(topic, KafkaTopic) else topic
        key = key or str(message.source_agent_id)

        payload = message.model_dump(mode="json")

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(_TRANSIENT_ERRORS),
                wait=wait_exponential(multiplier=0.5, min=0.5, max=10),
                stop=stop_after_attempt(5),
            ):
                with attempt:
                    await self._producer.send_and_wait(topic_str, value=payload, key=key)

            kafka_messages_produced.labels(
                topic=topic_str, agent_id=str(message.source_agent_id)
            ).inc()

        except Exception as e:
            kafka_produce_errors.labels(topic=topic_str, error_type=type(e).__name__).inc()
            self._log.error(
                "failed to produce message",
                topic=topic_str,
                error=str(e),
                message_id=str(message.message_id),
            )
            raise

    async def send_raw(self, topic: str, payload: dict[str, Any], key: str | None = None) -> None:
        """Publish raw dict — use for non-AgentMessage data."""
        if self._producer is None:
            raise RuntimeError("Producer not initialized")
        await self._producer.send_and_wait(topic, value=payload, key=key)

    async def shutdown(self) -> None:
        if self._producer:
            await self._producer.stop()
            self._log.info("producer stopped")


class AlghrestConsumer:
    """
    Async Kafka consumer with manual commits and idempotent processing.

    Usage:
        consumer = AlghrestConsumer(agent_name="technical_analyst", topics=[KafkaTopic.PRICES_REALTIME])
        await consumer.initialize()
        async for message in consumer.stream():
            await handle(message)
    """

    def __init__(
        self,
        agent_name: str,
        topics: list[KafkaTopic | str],
        auto_offset_reset: str = "latest",
        max_poll_records: int = 500,
        max_processing_attempts: int = DEFAULT_MAX_PROCESSING_ATTEMPTS,
        retry_backoff_seconds: float = 0.0,
        dlq_enabled: bool = True,
        dlq_topic_map: Mapping[str, str] | None = None,
        dlq_producer: Any | None = None,
    ) -> None:
        if max_processing_attempts < 1:
            raise ValueError("max_processing_attempts must be at least 1")
        self.agent_name = agent_name
        self.topics = [t.value if isinstance(t, KafkaTopic) else t for t in topics]
        self.group_id = f"{settings.kafka_consumer_group_prefix}.{agent_name}"
        self.auto_offset_reset = auto_offset_reset
        self.max_poll_records = max_poll_records
        self.max_processing_attempts = max_processing_attempts
        self.retry_backoff_seconds = retry_backoff_seconds
        self.dlq_enabled = dlq_enabled
        self.dlq_topic_map = dict(dlq_topic_map or DLQ_TOPIC_BY_SOURCE)
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: Any | None = dlq_producer
        self._owns_dlq_producer = False
        self._log = logger.bind(component="consumer", agent=agent_name, group=self.group_id)

    async def initialize(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=settings.kafka_servers_list,
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=False,  # Manual commits for reliability
            key_deserializer=lambda k: k.decode() if k else None,
            max_poll_records=self.max_poll_records,
            session_timeout_ms=30_000,
            heartbeat_interval_ms=10_000,
            max_poll_interval_ms=300_000,
            fetch_max_wait_ms=500,
        )

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(10),
        ):
            with attempt:
                if self._has_dlq_topics():
                    await self._ensure_dlq_producer()
                await self._consumer.start()
                self._log.info("consumer connected", topics=self.topics)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """
        Async generator yielding deserialized message payloads.
        Commits the exact record offset after each successful yield.

        Handler exceptions raised inside a normal ``async for`` body are not
        visible to an async generator. Use ``process()`` when the consumer
        layer must own bounded handler retries and DLQ routing.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized — call initialize() first")

        try:
            async for record in self._consumer:
                try:
                    payload = self._decode_record_value(record)
                except Exception as e:
                    await self._send_to_dlq_and_commit(record, e, self.max_processing_attempts)
                    continue

                try:
                    yield payload
                    await self._commit_record(record)
                except Exception as e:
                    self._log.error(
                        "message processing failed — NOT committing offset",
                        topic=getattr(record, "topic", None),
                        partition=getattr(record, "partition", None),
                        offset=getattr(record, "offset", None),
                        error=str(e),
                    )
        except asyncio.CancelledError:
            pass

    async def process(
        self,
        handler: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        """
        Consume records and run ``handler`` with bounded retries.

        After ``max_processing_attempts`` failures, the original record is
        published to the matching DLQ topic and the source offset is committed
        only after the DLQ publish succeeds.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized — call initialize() first")

        try:
            async for record in self._consumer:
                try:
                    payload = self._decode_record_value(record)
                except Exception as e:
                    await self._send_to_dlq_and_commit(record, e, self.max_processing_attempts)
                    continue

                await self._process_record_with_retries(record, payload, handler)
        except asyncio.CancelledError:
            pass

    async def _process_record_with_retries(
        self,
        record: Any,
        payload: dict[str, Any],
        handler: Callable[[dict[str, Any]], Awaitable[None] | None],
    ) -> None:
        last_error: Exception | None = None
        for attempt in range(1, self.max_processing_attempts + 1):
            try:
                result = handler(payload)
                if result is not None:
                    await result
                await self._commit_record(record)
                return
            except Exception as e:
                last_error = e
                if attempt >= self.max_processing_attempts:
                    break
                self._log.warning(
                    "message processing failed; retrying",
                    topic=getattr(record, "topic", None),
                    partition=getattr(record, "partition", None),
                    offset=getattr(record, "offset", None),
                    attempt=attempt,
                    max_attempts=self.max_processing_attempts,
                    error=str(e),
                )
                if self.retry_backoff_seconds > 0:
                    await asyncio.sleep(self.retry_backoff_seconds)

        if last_error is None:
            raise RuntimeError("message processing failed without an error")
        await self._send_to_dlq_and_commit(record, last_error, self.max_processing_attempts)

    def _decode_record_value(self, record: Any) -> dict[str, Any]:
        value = getattr(record, "value", None)
        decoded = _deserialize(bytes(value)) if isinstance(value, bytes | bytearray) else value
        if not isinstance(decoded, dict):
            raise TypeError(
                f"Kafka record value must deserialize to dict, got {type(decoded).__name__}"
            )
        self._annotate_kafka_offset(decoded, record)
        return decoded

    @staticmethod
    def _annotate_kafka_offset(decoded: dict[str, Any], record: Any) -> None:
        """Stamp the source Kafka offset onto AgentMessage envelopes.

        Only envelopes (dicts carrying a top-level ``topic``) are annotated so
        the persistence mapper can write a real ``kafka_offset`` instead of NULL.
        Bare payload dicts are not persistence targets and are left untouched so
        existing consumers that compare payloads by value are unaffected. Uses
        ``setdefault`` so an offset already present on the envelope wins (the
        consumer never overwrites an upstream value).
        """
        if "topic" not in decoded:
            return
        offset = getattr(record, "offset", None)
        if offset is None:
            return
        decoded.setdefault("kafka_offset", offset)

    def _has_dlq_topics(self) -> bool:
        return self.dlq_enabled and any(topic in self.dlq_topic_map for topic in self.topics)

    async def _ensure_dlq_producer(self) -> None:
        if not self.dlq_enabled:
            raise RuntimeError("DLQ handling is disabled")
        if self._dlq_producer is not None:
            return

        self._dlq_producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_servers_list,
            value_serializer=_serialize,
            key_serializer=lambda k: k.encode() if k else None,
            acks="all",
            enable_idempotence=True,
            compression_type="lz4",
            max_request_size=10_485_760,
            request_timeout_ms=30_000,
            retry_backoff_ms=500,
        )
        self._owns_dlq_producer = True

        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(_TRANSIENT_ERRORS),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            stop=stop_after_attempt(10),
        ):
            with attempt:
                await self._dlq_producer.start()
                self._log.info("dlq producer connected")

    async def _send_to_dlq_and_commit(
        self,
        record: Any,
        error: Exception,
        attempts: int,
    ) -> None:
        await self._publish_to_dlq(record, error, attempts)
        await self._commit_record(record)

    async def _publish_to_dlq(self, record: Any, error: Exception, attempts: int) -> None:
        source_topic = getattr(record, "topic", None)
        dlq_topic = self.dlq_topic_map.get(source_topic)
        if not self.dlq_enabled or dlq_topic is None:
            self._log.error(
                "message failed and no DLQ is configured; NOT committing offset",
                topic=source_topic,
                partition=getattr(record, "partition", None),
                offset=getattr(record, "offset", None),
                error=str(error),
            )
            raise error

        await self._ensure_dlq_producer()
        dlq_payload = self._build_dlq_payload(record, error, attempts)
        dlq_key = self._dlq_key(record)
        await self._dlq_producer.send_and_wait(dlq_topic, value=dlq_payload, key=dlq_key)
        self._log.error(
            "message sent to DLQ after bounded retries",
            topic=source_topic,
            dlq_topic=dlq_topic,
            partition=getattr(record, "partition", None),
            offset=getattr(record, "offset", None),
            attempts=attempts,
            error=str(error),
        )

    def _build_dlq_payload(self, record: Any, error: Exception, attempts: int) -> dict[str, Any]:
        original_value = _json_safe(getattr(record, "value", None))
        return {
            "original_topic": getattr(record, "topic", None),
            "original_partition": getattr(record, "partition", None),
            "original_offset": getattr(record, "offset", None),
            "original_key": _decode_key(getattr(record, "key", None)),
            "original_value": original_value,
            "payload": original_value,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "stack_trace": "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            ),
            "failed_at": _utc_now_iso(),
            "consumer_name": self.agent_name,
            "attempt_count": attempts,
            "max_attempts": self.max_processing_attempts,
        }

    def _dlq_key(self, record: Any) -> str:
        topic = getattr(record, "topic", "unknown")
        partition = getattr(record, "partition", "unknown")
        offset = getattr(record, "offset", "unknown")
        return f"{topic}:{partition}:{offset}"

    async def _commit_record(self, record: Any) -> None:
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized — call initialize() first")

        topic = getattr(record, "topic", None)
        partition = getattr(record, "partition", None)
        offset = getattr(record, "offset", None)
        if topic is None or partition is None or offset is None:
            await self._consumer.commit()
            return

        await self._consumer.commit({TopicPartition(topic, partition): offset + 1})

    async def get_lag(self) -> dict[str, int]:
        """Returns consumer lag per topic-partition."""
        if self._consumer is None:
            return {}
        try:
            partitions = self._consumer.assignment()
            end_offsets = await self._consumer.end_offsets(partitions)
            committed = {p: await self._consumer.committed(p) or 0 for p in partitions}
            return {f"{p.topic}:{p.partition}": end_offsets[p] - committed[p] for p in partitions}
        except Exception:
            return {}

    async def shutdown(self) -> None:
        if self._consumer:
            await self._consumer.stop()
            self._log.info("consumer stopped")
        if self._dlq_producer and self._owns_dlq_producer:
            await self._dlq_producer.stop()
            self._log.info("dlq producer stopped")
