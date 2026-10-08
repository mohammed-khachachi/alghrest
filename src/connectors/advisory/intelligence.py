"""One-way optional intelligence tap, with a separate Kafka consumer group."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from aiokafka import AIOKafkaConsumer

from connectors.advisory.storage import AdvisoryStore
from core.advisory.models import utcnow
from core.kafka.security import aiokafka_security

TOPICS = frozenset(
    {
        "news.tagged",
        "indicators.computed",
        "macro.regime",
        "sentiment.scored",
        "volatility.forecast",
    }
)


def normalize(message: dict[str, Any], topic: str) -> dict[str, str] | None:
    if topic not in TOPICS:
        return None
    payload = message.get("payload")
    if not isinstance(payload, dict):
        return None
    stamp = message.get("timestamp")
    legacy_signal_time = not isinstance(stamp, str)
    if legacy_signal_time:
        # AgentMessage has no timestamp; the internal _Signal contract carries
        # created_at as naive UTC. External observations still require an offset.
        stamp = payload.get("created_at")
    if not isinstance(stamp, str):
        return None
    when = datetime.fromisoformat(stamp)
    if when.tzinfo is None and legacy_signal_time:
        when = when.replace(tzinfo=UTC)
    if when.tzinfo is None:
        return None
    if not 0 <= (utcnow() - when).total_seconds() <= 3600:
        return None
    # Publish only useful, bounded fields. No orders, portfolio, secrets or raw prompts.
    allowed = (
        "symbol",
        "direction",
        "summary",
        "regime",
        "value",
        "rsi",
        "trend",
        "volatility",
        "confidence",
        "affected_symbols",
        "headline",
        "source",
        "url",
        "published_at",
        "indicator",
        "indicator_value",
        "timeframe",
        "forecast_1d",
        "forecast_7d",
        "realized_vol_1d",
        "sentiment_score",
        "volume_mentions",
        "indicator_name",
        "actual_value",
        "country",
    )
    summary = json.dumps({k: payload[k] for k in allowed if k in payload}, ensure_ascii=False)[
        :1500
    ]
    if summary == "{}":
        return None
    return {
        "id": hashlib.sha256((topic + stamp + summary).encode()).hexdigest(),
        "topic": topic,
        "timestamp": when.isoformat(),
        "summary": summary,
        "symbol": str(payload.get("symbol") or "")[:80],
        "affected_symbols": json.dumps(
            [s[:80] for s in payload.get("affected_symbols", []) if isinstance(s, str)][:30]
        ),
    }


async def consume(store: AdvisoryStore, servers: str) -> None:
    while True:
        consumer = AIOKafkaConsumer(
            *sorted(TOPICS),
            bootstrap_servers=servers,
            **aiokafka_security("advisory"),
            group_id="alghrest.manual-assistant.readonly.v1",
            enable_auto_commit=False,
            auto_offset_reset="latest",
            max_poll_records=10,
            fetch_max_bytes=262144,
            max_partition_fetch_bytes=65536,
            request_timeout_ms=10000,
        )
        try:
            await consumer.start()
            async for record in consumer:
                try:
                    value = normalize(json.loads(record.value), record.topic)
                    if value:
                        await asyncio.to_thread(store.save_intelligence, value)
                except (ValueError, TypeError):
                    pass
                await consumer.commit()
        except asyncio.CancelledError:
            raise
        except Exception:
            await asyncio.sleep(15)
        finally:
            await consumer.stop()
