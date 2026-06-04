"""Roadmap item 4 — propagate ``kafka_offset`` into the persistence envelope.

These tests lock the contract end to end without a database:

    AlghrestConsumer.stream() stamps record.offset onto the envelope →
    normalize_kafka_message reads it →
    build_persistence_statements writes it into trading.trade_proposals.params

They also prove the change is backward-compatible: envelopes without an offset
still map to ``kafka_offset = None`` (the prior NULL behaviour), and bare payload
dicts (no top-level ``topic``) are never annotated.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import orjson
import pytest

from core.data.models import (
    AgentMessage,
    AssetClass,
    Exchange,
    KafkaTopic,
    OrderSide,
    OrderType,
    TradeProposal,
    TradeProposalStatus,
)
from core.orchestrator.message_bus import AlghrestConsumer
from core.persistence.events import build_persistence_statements, normalize_kafka_message


class _FakeKafkaConsumer:
    """Minimal async-iterable Kafka consumer stub for ``stream()``."""

    def __init__(self, records: list[Any]) -> None:
        self.records = records
        self._index = 0

    def __aiter__(self) -> _FakeKafkaConsumer:
        self._index = 0
        return self

    async def __anext__(self) -> Any:
        if self._index >= len(self.records):
            raise StopAsyncIteration
        record = self.records[self._index]
        self._index += 1
        return record

    async def commit(self, offsets: Any = None) -> None:
        return None


def _record(value: Any, *, topic: str, partition: int = 0, offset: int = 0) -> SimpleNamespace:
    return SimpleNamespace(topic=topic, partition=partition, offset=offset, key=None, value=value)


def _consumer(records: list[Any]) -> AlghrestConsumer:
    consumer = AlghrestConsumer(agent_name="offset_test", topics=[KafkaTopic.PROPOSALS_APPROVED])
    consumer._consumer = _FakeKafkaConsumer(records)
    return consumer


def _envelope_bytes(topic: KafkaTopic, payload: dict[str, Any]) -> bytes:
    """Serialise a real AgentMessage envelope as the producer would (bytes)."""
    envelope = AgentMessage(
        source_agent_id=12,
        topic=topic,
        message_type="TradeProposalApproved",
        payload=payload,
    ).model_dump(mode="json")
    return orjson.dumps(envelope)


def _proposal_payload() -> dict[str, Any]:
    return TradeProposal(
        strategy_id="trend_follower",
        agent_id=12,
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        asset_class=AssetClass.CRYPTO,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.10"),
        size_usd=Decimal("4500"),
        confidence_score=0.7,
        status=TradeProposalStatus.PENDING,
        rationale="offset propagation test",
    ).model_dump(mode="json")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_stamps_kafka_offset_on_envelope() -> None:
    """A real envelope record gets ``kafka_offset`` set to ``record.offset``."""
    record = _record(
        _envelope_bytes(KafkaTopic.PROPOSALS_APPROVED, _proposal_payload()),
        topic=KafkaTopic.PROPOSALS_APPROVED.value,
        offset=4242,
    )
    consumer = _consumer([record])

    messages = [message async for message in consumer.stream()]

    assert len(messages) == 1
    assert messages[0]["kafka_offset"] == 4242


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_does_not_annotate_bare_payload_dicts() -> None:
    """Bare payload dicts (no top-level ``topic``) are left untouched."""
    record = _record(
        orjson.dumps({"order_id": "ok"}),
        topic=KafkaTopic.ORDERS_PENDING.value,
        offset=7,
    )
    consumer = _consumer([record])

    messages = [message async for message in consumer.stream()]

    assert messages == [{"order_id": "ok"}]
    assert "kafka_offset" not in messages[0]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_offset_propagates_through_persistence_mapper() -> None:
    """End-to-end (DB-free): stamped offset lands in trade_proposals.params."""
    record = _record(
        _envelope_bytes(KafkaTopic.PROPOSALS_APPROVED, _proposal_payload()),
        topic=KafkaTopic.PROPOSALS_APPROVED.value,
        offset=99,
    )
    consumer = _consumer([record])

    envelope = await anext(message async for message in consumer.stream())
    statements = build_persistence_statements(envelope)

    assert len(statements) == 1
    assert statements[0].table == "trading.trade_proposals"
    assert statements[0].params["kafka_offset"] == 99


@pytest.mark.unit
def test_envelope_without_offset_maps_to_none_kafka_offset() -> None:
    """Backward compatibility: a legacy envelope with no offset stays NULL."""
    envelope = AgentMessage(
        source_agent_id=12,
        topic=KafkaTopic.PROPOSALS_APPROVED,
        message_type="TradeProposalApproved",
        payload=_proposal_payload(),
    ).model_dump(mode="json")
    assert "kafka_offset" not in envelope

    normalized = normalize_kafka_message(envelope)
    assert normalized.kafka_offset is None

    statements = build_persistence_statements(envelope)
    assert statements[0].params["kafka_offset"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_existing_envelope_offset_is_not_overwritten() -> None:
    """``setdefault`` semantics: an upstream offset on the envelope wins."""
    envelope = AgentMessage(
        source_agent_id=12,
        topic=KafkaTopic.PROPOSALS_APPROVED,
        message_type="TradeProposalApproved",
        payload=_proposal_payload(),
    ).model_dump(mode="json")
    envelope["kafka_offset"] = 99  # already stamped upstream

    record = _record(
        orjson.dumps(envelope),
        topic=KafkaTopic.PROPOSALS_APPROVED.value,
        offset=1,  # differs from the upstream value
    )
    consumer = _consumer([record])

    messages = [message async for message in consumer.stream()]

    assert messages[0]["kafka_offset"] == 99
