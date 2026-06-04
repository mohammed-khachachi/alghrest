"""Agent 38 — Kafka to TimescaleDB persistence writer."""

from __future__ import annotations

import asyncio

import structlog

from agents.base_agent import BaseAgent
from core.data.models import AgentConfig
from core.persistence import PERSISTED_TOPICS, TimescalePersistenceRepository

log = structlog.get_logger(__name__)


class PersistenceWriter(BaseAgent):
    """
    Tier 7 sink that consumes Kafka event envelopes and persists them to
    TimescaleDB tables already provisioned by ``infra/init/timescale-init.sql``.
    """

    AGENT_ID = 38

    def __init__(
        self,
        config: AgentConfig | None = None,
        repository: TimescalePersistenceRepository | None = None,
    ) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=7,
            name="PersistenceWriter",
            config=config,
        )
        self._repository = repository or TimescalePersistenceRepository()
        self._consumer = None
        self._events_seen = 0
        self._statements_written = 0
        self._events_skipped = 0

    async def initialize(self) -> None:
        log.info(
            "persistence_writer.initialized",
            topics=[topic.value for topic in PERSISTED_TOPICS],
        )

    async def run(self) -> None:
        self._consumer = self.make_consumer(PERSISTED_TOPICS, auto_offset_reset="earliest")
        await self._consumer.initialize()

        async for message in self._consumer.stream():
            while await self.is_halted():
                await asyncio.sleep(30)
            await self._persist_message(message)

    async def shutdown(self) -> None:
        if self._consumer is not None:
            await self._consumer.shutdown()
        close = getattr(self._repository, "close", None)
        if close is not None:
            await close()
        log.info(
            "persistence_writer.shutdown",
            events_seen=self._events_seen,
            statements_written=self._statements_written,
            events_skipped=self._events_skipped,
        )

    async def _persist_message(self, message: object) -> None:
        self._events_seen += 1
        topic = self._message_topic(message)
        try:
            if not isinstance(message, dict):
                raise TypeError(f"Kafka message must be a dict, got {type(message).__name__}")
            statements = await self._repository.persist_kafka_message(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._events_skipped += 1
            self.record_processing_error(topic, type(exc).__name__)
            log.warning(
                "persistence_writer.persist_failed",
                topic=topic,
                error=str(exc),
            )
            return

        if statements == 0:
            self._events_skipped += 1
        else:
            self._statements_written += statements
        log.debug(
            "persistence_writer.persisted",
            topic=topic,
            statements=statements,
        )

    @staticmethod
    def _message_topic(message: object) -> str:
        if isinstance(message, dict):
            return str(message.get("topic", "unknown"))
        return "unknown"
