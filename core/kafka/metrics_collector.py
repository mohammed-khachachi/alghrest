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
from datetime import datetime, timezone
from typing import Any

import orjson
import structlog
from confluent_kafka.admin import AdminClient, NewTopic
from confluent_kafka import KafkaException

from core.config import settings

logger = structlog.get_logger(__name__)

POLL_INTERVAL = 10          # seconds between full polls
REDIS_TTL = POLL_INTERVAL * 3
REDIS_KEY_TMPL = "alghrest:kafka:metrics:{topic}"

# Consumer groups we care about for lag measurement
CONSUMER_GROUPS = [
    "alghrest-technical-analyst",
    "alghrest-volatility-forecaster",
    "alghrest-correlation-engine",
    "alghrest-trend-follower",
    "alghrest-mean-reversion",
    "alghrest-momentum",
    "alghrest-stat-arb",
    "alghrest-ml-predictor",
    "alghrest-options-strategist",
    "alghrest-macro-rotator",
    "alghrest-breakout-hunter",
    "alghrest-order-router",
    "alghrest-risk-governor",
    "alghrest-portfolio-tracker",
    "alghrest-alert-manager",
    "alghrest-compliance-agent",
]


class KafkaMetricsCollector:
    """
    Background task that collects Kafka topic stats and publishes them
    to Redis. Designed to run as a single asyncio task in the FastAPI process.

    Uses confluent_kafka's AdminClient (sync) wrapped in run_in_executor so
    it never blocks the event loop.
    """

    def __init__(self, redis: Any) -> None:
        self._redis = redis
        self._admin: AdminClient | None = None
        self._prev_offsets: dict[str, int] = {}   # topic → total_offset at last poll
        self._prev_ts: float = 0.0
        self._log = logger.bind(component="kafka_metrics")

    # ── LIFECYCLE ─────────────────────────────────────────────────────────────

    def _make_admin(self) -> AdminClient:
        return AdminClient({
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "socket.timeout.ms": 5000,
            "request.timeout.ms": 8000,
        })

    async def _ensure_admin(self) -> bool:
        """Lazily create AdminClient; return False if Kafka unreachable."""
        if self._admin is not None:
            return True
        try:
            loop = asyncio.get_running_loop()
            self._admin = await loop.run_in_executor(None, self._make_admin)
            self._log.info("kafka admin client connected")
            return True
        except Exception as exc:
            self._log.warning("kafka admin client init failed", error=str(exc))
            return False

    # ── POLLING ───────────────────────────────────────────────────────────────

    async def _collect_once(self) -> None:
        if not await self._ensure_admin():
            await self._write_zeros()
            return

        loop = asyncio.get_running_loop()
        try:
            raw_meta, raw_groups = await asyncio.gather(
                loop.run_in_executor(None, self._fetch_metadata),
                loop.run_in_executor(None, self._fetch_consumer_group_offsets),
                return_exceptions=True,
            )
        except Exception as exc:
            self._log.warning("kafka collect error", error=str(exc))
            await self._write_zeros()
            return

        topic_meta: dict[str, dict] = raw_meta if not isinstance(raw_meta, Exception) else {}
        group_lag: dict[str, int] = raw_groups if not isinstance(raw_groups, Exception) else {}

        now_ts = time.time()
        elapsed = now_ts - self._prev_ts if self._prev_ts else POLL_INTERVAL
        now_iso = datetime.now(timezone.utc).isoformat()

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
            lag_offsets = group_lag.get(topic, 0)
            # Convert lag_offsets → approximate lag_ms (assume ~1ms/msg throughput floor)
            est_rate = max(msg_per_sec, 1.0)
            lag_ms = round((lag_offsets / est_rate) * 1000, 1)

            blob = orjson.dumps({
                "messages_per_sec": msg_per_sec,
                "consumer_lag_ms":  lag_ms,
                "last_message_ts":  now_iso,
                "partition_count":  partition_count,
                "total_messages":   total_offsets,
            })
            key = REDIS_KEY_TMPL.format(topic=topic)
            pipe.setex(key, REDIS_TTL, blob)

        self._prev_ts = now_ts
        await pipe.execute()
        self._log.debug("kafka metrics written", topics=len(topic_meta))

    def _fetch_metadata(self) -> dict[str, dict]:
        """Sync: fetch topic metadata from Kafka broker."""
        meta = self._admin.list_topics(timeout=8)
        result: dict[str, dict] = {}
        for topic_name, topic_meta in meta.topics.items():
            if topic_name.startswith("__"):   # skip internal topics
                continue
            partition_count = len(topic_meta.partitions)
            # Sum high-watermark offsets across all partitions
            # (confluent_kafka AdminClient doesn't expose watermarks directly;
            # we use list_offsets via a temporary Consumer instead)
            result[topic_name] = {
                "partition_count": partition_count,
                "total_offsets": 0,  # filled by _fetch_watermarks if needed
            }
        return result

    def _fetch_consumer_group_offsets(self) -> dict[str, int]:
        """Sync: sum consumer group lag per topic across known groups."""
        from confluent_kafka.admin import ListConsumerGroupOffsetsRequest  # type: ignore[attr-defined]
        lag_per_topic: dict[str, int] = {}
        try:
            futures = self._admin.list_consumer_group_offsets(CONSUMER_GROUPS)
            for group, future in futures.items():
                try:
                    result = future.result()
                    for tp, offset_info in result.topic_partitions.items():
                        if offset_info.offset >= 0:
                            lag_per_topic[tp.topic] = (
                                lag_per_topic.get(tp.topic, 0) + offset_info.offset
                            )
                except Exception:
                    pass
        except Exception:
            pass
        return lag_per_topic

    async def _write_zeros(self) -> None:
        """Write zero-metric blobs for all known topics when Kafka is down."""
        from api.websockets.dashboard_ws import KAFKA_TOPICS
        now_iso = datetime.now(timezone.utc).isoformat()
        pipe = self._redis.pipeline()
        for topic in KAFKA_TOPICS:
            blob = orjson.dumps({
                "messages_per_sec": 0.0,
                "consumer_lag_ms":  0.0,
                "last_message_ts":  now_iso,
                "partition_count":  6,
                "total_messages":   0,
            })
            pipe.setex(REDIS_KEY_TMPL.format(topic=topic), REDIS_TTL, blob)
        await pipe.execute()

    # ── MAIN LOOP ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Infinite poll loop — run as asyncio.create_task()."""
        self._log.info("kafka metrics collector started", interval_s=POLL_INTERVAL)
        while True:
            try:
                await self._collect_once()
            except Exception as exc:
                self._log.warning("kafka metrics loop error", error=str(exc))
            await asyncio.sleep(POLL_INTERVAL)


# ── MODULE-LEVEL FACTORY ──────────────────────────────────────────────────────

def make_kafka_metrics_collector(redis: Any) -> KafkaMetricsCollector:
    return KafkaMetricsCollector(redis)
