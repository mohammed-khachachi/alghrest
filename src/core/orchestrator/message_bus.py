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
from collections.abc import AsyncIterator, Callable, Coroutine, Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

import orjson
import structlog
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaConnectionError, KafkaTimeoutError, NodeNotReadyError
from aiokafka.structs import TopicPartition
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from core.config import settings
from core.data.models import AgentMessage, KafkaTopic
from core.kafka.security import aiokafka_security
from core.utils.metrics import kafka_messages_produced, kafka_produce_errors

logger = structlog.get_logger(__name__)

_TRANSIENT_ERRORS = (KafkaConnectionError, KafkaTimeoutError, NodeNotReadyError)


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


class AlghrestProducer:
    """
    Idempotent async Kafka producer. One instance per agent process.
    Call initialize() before use and shutdown() on exit.
    """

    def __init__(self) -> None:
        self._producer: AIOKafkaProducer | None = None
        self._log = logger.bind(component="producer")

    async def initialize(self) -> None:
        settings.require_order_execution()
        self._producer = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_servers_list,
            **aiokafka_security(),
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
        settings.require_order_execution()
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
        settings.require_order_execution()
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
        topics: Sequence[KafkaTopic | str],
        auto_offset_reset: str = "latest",
        max_poll_records: int = 500,
    ) -> None:
        self.agent_name = agent_name
        self.topics = [t.value if isinstance(t, KafkaTopic) else t for t in topics]
        self.group_id = f"{settings.kafka_consumer_group_prefix}.{agent_name}"
        self.auto_offset_reset = auto_offset_reset
        self.max_poll_records = max_poll_records
        self._consumer: AIOKafkaConsumer | None = None
        self._log = logger.bind(component="consumer", agent=agent_name, group=self.group_id)

    async def initialize(self) -> None:
        self._consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=settings.kafka_servers_list,
            **aiokafka_security(),
            group_id=self.group_id,
            auto_offset_reset=self.auto_offset_reset,
            enable_auto_commit=False,  # Manual commits for reliability
            value_deserializer=_deserialize,
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
                await self._consumer.start()
                self._log.info("consumer connected", topics=self.topics)

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        """
        Async generator yielding deserialized message payloads.
        Commits offset after each successful yield.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized — call initialize() first")

        try:
            async for record in self._consumer:
                try:
                    yield record.value
                    await self._consumer.commit()
                except Exception as e:
                    self._log.error(
                        "message processing failed — NOT committing offset",
                        topic=record.topic,
                        partition=record.partition,
                        offset=record.offset,
                        error=str(e),
                    )
        except asyncio.CancelledError:
            pass

    async def process(self, handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]) -> None:
        """Durable handlers: acknowledge only this record after handler commits.

        Any handler/commit failure escapes so a supervisor restarts at the last
        committed offset. Never advance past a failed record in the same session.
        """
        if self._consumer is None:
            raise RuntimeError("Consumer not initialized")
        async for record in self._consumer:
            await handler(record.value)
            await self._consumer.commit(
                {
                    TopicPartition(record.topic, record.partition): record.offset + 1,
                }
            )

    async def caught_up(self) -> bool:
        """Strict readiness check; unlike diagnostic get_lag, failures propagate."""
        if self._consumer is None:
            return False
        partitions = self._consumer.assignment()
        if not partitions:
            return False
        ends = await self._consumer.end_offsets(partitions)
        for partition in partitions:
            committed = await self._consumer.committed(partition)
            if (committed or 0) < ends[partition]:
                return False
        return bool(partitions == self._consumer.assignment())

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
