"""
ALGHREST — Kafka Metrics Collector
Polls the Kafka Admin API every POLL_INTERVAL seconds and writes per-topic
metrics to Redis so the dashboard WebSocket can serve them without hitting
Kafka directly from every client connection.

Redis key schema:
    alghrest:kafka:metrics:{topic}  →  JSON blob, TTL = POLL_INTERVAL * 3

Metric blob shape (matches dashboard_ws._build_kafka_metrics expectations):
    {
        "messages_per_sec": float,
        "consumer_lag_ms":  float,   # proxy: lag_offsets / estimated_rate
        "last_message_ts":  str,     # ISO-8601
        "partition_count":  int,
        "total_messages":   int,     # latest_offset summed across partitions
    }
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import orjson
import structlog
from aiokafka import AIOKafkaConsumer, TopicPartition
from aiokafka.admin import AIOKafkaAdminClient

from core.config import settings
from core.kafka.security import aiokafka_security

logger = structlog.get_logger(__name__)

POLL_INTERVAL = 10  # seconds between full polls
REDIS_TTL = POLL_INTERVAL * 3
REDIS_KEY_TMPL = "alghrest:kafka:metrics:{topic}"


class KafkaMetricsCollector:
    """
    Background task that collects Kafka topic stats and publishes them
    to Redis. Designed to run as a single asyncio task in the FastAPI process.

    Uses the same asynchronous Kafka client as the agents. No native admin
    threads run inside the API process; shutdown awaits both client closures.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._admin: AIOKafkaAdminClient | None = None
        self._reader: AIOKafkaConsumer | None = None
        self._prev_offsets: dict[str, int] = {}  # topic → total_offset at last poll
        self._prev_ts: float = 0.0
        self._log = logger.bind(component="kafka_metrics")

    # ── LIFECYCLE ─────────────────────────────────────────────────────────────

    async def _ensure_admin(self) -> bool:
        if self._admin is not None and self._reader is not None:
            return True
        try:
            options = {
                "bootstrap_servers": settings.kafka_servers_list,
                "request_timeout_ms": 8000,
                **aiokafka_security(),
            }
            self._admin = AIOKafkaAdminClient(**options)
            self._reader = AIOKafkaConsumer(enable_auto_commit=False, **options)
            await self._admin.start()
            await self._reader.start()
            return True
        except BaseException as exc:
            await self.close()
            if not isinstance(exc, Exception):
                raise
            self._log.warning("kafka admin client init failed", error=str(exc))
            return False

    async def close(self) -> None:
        admin, reader = self._admin, self._reader
        self._admin = None
        self._reader = None
        try:
            if reader is not None:
                await reader.stop()
        finally:
            if admin is not None:
                await admin.close()

    # ── POLLING ───────────────────────────────────────────────────────────────

    async def _collect_once(self) -> None:
        if not await self._ensure_admin():
            await self._write_zeros()
            return

        try:
            topic_meta = await self._fetch_metadata()
            end_offsets = {
                (topic, partition): offset
                for topic, meta in topic_meta.items()
                for partition, offset in meta["end_offsets"].items()
            }
            group_lag = await self._fetch_consumer_group_offsets(end_offsets)
        except Exception as exc:
            self._log.warning("kafka collect error", error=str(exc))
            await self._write_zeros()
            return

        now_ts = time.time()
        elapsed = now_ts - self._prev_ts if self._prev_ts else POLL_INTERVAL
        now_iso = datetime.now(UTC).isoformat()

        pipe = self._redis.pipeline()
        for topic, meta in topic_meta.items():
            total_offsets: int = meta.get("total_offsets", 0)
            partition_count: int = meta.get("partition_count", 0)

            # Estimate messages/sec from offset delta
            prev = self._prev_offsets.get(topic, total_offsets)
            delta = max(0, total_offsets - prev)
            msg_per_sec = round(delta / elapsed, 2) if elapsed > 0 else 0.0
            self._prev_offsets[topic] = total_offsets

            # Lag: total unread offsets for all consumer groups on this topic
            lag_offsets = group_lag.get(topic)
            # Convert lag_offsets → approximate lag_ms (assume ~1ms/msg throughput floor)
            est_rate = max(msg_per_sec, 1.0)
            lag_ms = round((lag_offsets / est_rate) * 1000, 1) if lag_offsets is not None else None

            blob = orjson.dumps(
                {
                    "messages_per_sec": msg_per_sec,
                    "consumer_lag_ms": lag_ms,
                    "last_message_ts": now_iso,
                    "partition_count": partition_count,
                    "total_messages": total_offsets,
                    "available": True,
                }
            )
            key = REDIS_KEY_TMPL.format(topic=topic)
            pipe.setex(key, REDIS_TTL, blob)

        self._prev_ts = now_ts
        await pipe.execute()
        self._log.debug("kafka metrics written", topics=len(topic_meta))

    async def _fetch_metadata(self) -> dict[str, dict[str, Any]]:
        """Fetch end offsets without subscribing or creating a consumer group."""
        if self._admin is None or self._reader is None:
            raise RuntimeError("Kafka admin client is not initialized")
        metadata = await self._admin.describe_topics()
        result: dict[str, dict[str, Any]] = {}
        partitions: list[TopicPartition] = []
        for topic in metadata:
            name = topic["topic"]
            if name.startswith("__") or topic["error_code"]:
                continue
            if any(p["error_code"] for p in topic["partitions"]):
                raise RuntimeError("Kafka partition metadata unavailable")
            result[name] = {
                "partition_count": len(topic["partitions"]),
                "total_offsets": 0,
                "end_offsets": {},
            }
            partitions.extend(TopicPartition(name, p["partition"]) for p in topic["partitions"])
        if partitions:
            for tp, offset in (await self._reader.end_offsets(partitions)).items():
                if offset < 0:
                    raise ValueError("Kafka returned an invalid end offset")
                result[tp.topic]["end_offsets"][tp.partition] = offset
                result[tp.topic]["total_offsets"] += offset
        return result

    async def _fetch_consumer_group_offsets(
        self, end_offsets: dict[tuple[str, int], int]
    ) -> dict[str, int]:
        """Discover actual application groups and sum end minus committed offsets."""
        if self._admin is None:
            raise RuntimeError("Kafka admin client is not initialized")
        lag_per_topic: dict[str, int] = {}
        unknown_topics: set[str] = set()
        for group, _protocol in await self._admin.list_consumer_groups():
            if not group.startswith(settings.kafka_consumer_group_prefix + "."):
                continue
            # A failed group query invalidates this poll rather than reporting
            # an incomplete aggregate as a healthy low lag.
            offsets = await self._admin.list_consumer_group_offsets(group)
            for tp, committed in offsets.items():
                end = end_offsets.get((tp.topic, tp.partition))
                if end is None:
                    continue
                if committed.offset < 0:
                    unknown_topics.add(tp.topic)
                else:
                    lag_per_topic[tp.topic] = lag_per_topic.get(tp.topic, 0) + max(
                        0, end - committed.offset
                    )
        return {topic: lag for topic, lag in lag_per_topic.items() if topic not in unknown_topics}

    async def _write_zeros(self) -> None:
        """Write zero-metric blobs for all known topics when Kafka is down."""
        from core.kafka.topics import KAFKA_TOPICS

        pipe = self._redis.pipeline()
        for topic in KAFKA_TOPICS:
            blob = orjson.dumps(
                {
                    "messages_per_sec": 0.0,
                    "consumer_lag_ms": None,
                    "last_message_ts": None,
                    "partition_count": 0,
                    "available": False,
                    "total_messages": 0,
                }
            )
            pipe.setex(REDIS_KEY_TMPL.format(topic=topic), REDIS_TTL, blob)
        await pipe.execute()

    # ── MAIN LOOP ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Infinite poll loop — run as asyncio.create_task()."""
        self._log.info("kafka metrics collector started", interval_s=POLL_INTERVAL)
        try:
            while True:
                try:
                    async with asyncio.timeout(25):
                        await self._collect_once()
                except Exception as exc:
                    self._log.warning("kafka metrics loop error", error=str(exc))
                    await self._write_zeros()
                await asyncio.sleep(POLL_INTERVAL)
        finally:
            await self.close()


# ── MODULE-LEVEL FACTORY ──────────────────────────────────────────────────────


def make_kafka_metrics_collector(redis: Any) -> KafkaMetricsCollector:
    return KafkaMetricsCollector(redis)
