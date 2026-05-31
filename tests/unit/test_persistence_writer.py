"""Unit tests for Agent 38 — PersistenceWriter."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.tier7_monitoring.persistence_writer import PersistenceWriter
from core.data.models import KafkaTopic


def _build_writer(repo: MagicMock | None = None) -> PersistenceWriter:
    if repo is None:
        repository = MagicMock()
        repository.persist_kafka_message = AsyncMock(return_value=1)
        repository.close = AsyncMock()
    else:
        repository = repo
    writer = PersistenceWriter(repository=repository)
    writer.record_processing_error = MagicMock()
    return writer


@pytest.mark.unit
def test_persistence_writer_agent_id_is_unique_after_hmm_agent():
    assert PersistenceWriter.AGENT_ID == 38


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_message_counts_written_statement():
    repo = MagicMock()
    repo.persist_kafka_message = AsyncMock(return_value=1)
    repo.close = AsyncMock()
    writer = _build_writer(repo)

    message = {"topic": KafkaTopic.FILLS_CONFIRMED.value, "payload": {}}
    await writer._persist_message(message)

    repo.persist_kafka_message.assert_awaited_once_with(message)
    assert writer._events_seen == 1
    assert writer._statements_written == 1
    assert writer._events_skipped == 0
    writer.record_processing_error.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_message_counts_skipped_event():
    repo = MagicMock()
    repo.persist_kafka_message = AsyncMock(return_value=0)
    repo.close = AsyncMock()
    writer = _build_writer(repo)

    await writer._persist_message({"topic": "unknown.topic", "payload": {}})

    assert writer._events_seen == 1
    assert writer._statements_written == 0
    assert writer._events_skipped == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_message_records_error_without_reraising():
    repo = MagicMock()
    repo.persist_kafka_message = AsyncMock(side_effect=RuntimeError("db down"))
    repo.close = AsyncMock()
    writer = _build_writer(repo)

    await writer._persist_message({"topic": KafkaTopic.ORDERS_EXECUTED.value, "payload": {}})

    repo.persist_kafka_message.assert_awaited_once()
    writer.record_processing_error.assert_called_once_with(
        KafkaTopic.ORDERS_EXECUTED.value,
        "RuntimeError",
    )
    assert writer._events_seen == 1
    assert writer._statements_written == 0
    assert writer._events_skipped == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_message_records_malformed_message_without_repository_call():
    repo = MagicMock()
    repo.persist_kafka_message = AsyncMock(return_value=1)
    repo.close = AsyncMock()
    writer = _build_writer(repo)

    await writer._persist_message(None)

    repo.persist_kafka_message.assert_not_called()
    writer.record_processing_error.assert_called_once_with("unknown", "TypeError")
    assert writer._events_seen == 1
    assert writer._statements_written == 0
    assert writer._events_skipped == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_message_propagates_cancelled_error():
    repo = MagicMock()
    repo.persist_kafka_message = AsyncMock(side_effect=asyncio.CancelledError())
    repo.close = AsyncMock()
    writer = _build_writer(repo)

    with pytest.raises(asyncio.CancelledError):
        await writer._persist_message({"topic": KafkaTopic.ORDERS_EXECUTED.value, "payload": {}})

    writer.record_processing_error.assert_not_called()
    assert writer._events_seen == 1
    assert writer._statements_written == 0
    assert writer._events_skipped == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shutdown_closes_consumer_and_repository():
    repo = MagicMock()
    repo.persist_kafka_message = AsyncMock(return_value=1)
    repo.close = AsyncMock()
    writer = _build_writer(repo)
    writer._consumer = MagicMock()
    writer._consumer.shutdown = AsyncMock()

    await writer.shutdown()

    writer._consumer.shutdown.assert_awaited_once()
    repo.close.assert_awaited_once()
