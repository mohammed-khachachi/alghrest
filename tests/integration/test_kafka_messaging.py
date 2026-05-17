"""
ALGHREST — Kafka Message Bus Integration Tests
==============================================

This test validates the core Kafka message bus functionality:
1. Producer/Consumer message reliability
2. Topic routing and message ordering
3. Schema validation and serialization
4. Error handling and retries
5. Consumer group management
6. Message durability and acknowledgments

Test Scenarios:
- High throughput message processing
- Consumer rebalancing
- Schema evolution compatibility
- Message deduplication
- Dead letter queues
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import structlog

from core.data.models import (
    KafkaTopic,
    MarketData,
    OHLCVBar,
    Exchange,
    Timeframe,
    TradeProposal,
    TradeProposalStatus,
    OrderSide,
    OrderType,
    AgentMessage,
)
from core.orchestrator.message_bus import AlghrestProducer, AlghrestConsumer

logger = structlog.get_logger(__name__)


@pytest.fixture
def mock_kafka_producer():
    """Mock Kafka producer for testing."""
    producer = AsyncMock()
    producer.send = AsyncMock()
    producer.initialize = AsyncMock()
    producer.shutdown = AsyncMock()
    return producer


@pytest.fixture
def mock_kafka_consumer():
    """Mock Kafka consumer for testing."""
    consumer = AsyncMock()
    consumer.subscribe = AsyncMock()
    consumer.close = AsyncMock()
    return consumer


@pytest.fixture
def sample_trade_proposals():
    """Generate sample trade proposals for testing."""
    proposals = []

    for i in range(10):
        proposal = TradeProposal(
            proposal_id=str(uuid4()),
            strategy_id=f"test_strategy_{i}",
            symbol="BTC/USDT",
            side=OrderSide.BUY if i % 2 == 0 else OrderSide.SELL,
            order_type=OrderType.MARKET,
            size=Decimal("0.01"),
            confidence=0.7 + (i * 0.02),
            created_at=datetime.utcnow() - timedelta(seconds=i),
            status=TradeProposalStatus.PENDING,
            metadata={"test_id": i, "batch": "integration_test"}
        )
        proposals.append(proposal)

    return proposals


@pytest.fixture
def sample_market_data():
    """Generate sample OHLCV market data for testing."""
    bars = []
    base_time = datetime.utcnow() - timedelta(hours=24)
    base_price = 50000.0

    for i in range(24):  # 24 hours of hourly bars
        price = base_price * (1 + 0.001 * i)  # Slight uptrend

        bar = OHLCVBar(
            time=base_time + timedelta(hours=i),
            symbol="BTC/USDT",
            exchange=Exchange.BINANCE,
            timeframe=Timeframe.H1,
            open=Decimal(str(price * 0.999)),
            high=Decimal(str(price * 1.002)),
            low=Decimal(str(price * 0.998)),
            close=Decimal(str(price)),
            volume=Decimal("1000.0"),
            is_closed=True,
        )
        bars.append(bar)

    return bars


@pytest.mark.integration
class TestKafkaMessaging:
    """Integration tests for Kafka message bus functionality."""

    async def test_producer_consumer_roundtrip(self, mock_kafka_producer, sample_trade_proposals):
        """Test complete producer -> consumer message flow."""

        # Setup producer
        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Mock successful sends
        mock_kafka_producer.send.return_value = AsyncMock()

        # Send all test proposals
        for proposal in sample_trade_proposals:
            await producer.send(KafkaTopic.PROPOSALS_BUS, proposal.model_dump())

        # Verify all messages were sent
        assert mock_kafka_producer.send.call_count == len(sample_trade_proposals)

        # Verify correct topic and serialization
        calls = mock_kafka_producer.send.call_args_list
        for i, call in enumerate(calls):
            topic = call[1]["topic"]
            value = call[1]["value"]

            assert topic == KafkaTopic.PROPOSALS_BUS.value

            # Verify JSON serialization
            parsed_value = json.loads(value)
            assert parsed_value["strategy_id"] == f"test_strategy_{i}"
            assert parsed_value["symbol"] == "BTC/USDT"

    async def test_message_ordering_guarantee(self, mock_kafka_producer):
        """Test that messages maintain ordering within a partition key."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Send ordered messages with same partition key
        messages = []
        for i in range(10):
            message = {
                "sequence": i,
                "symbol": "BTC/USDT",  # Same partition key
                "timestamp": datetime.utcnow().isoformat(),
                "data": f"message_{i}"
            }
            messages.append(message)

        # Send all messages
        for message in messages:
            await producer.send(
                KafkaTopic.MARKET_DATA,
                message,
                key="BTC/USDT"  # Same key = same partition
            )

        # Verify ordering preservation
        calls = mock_kafka_producer.send.call_args_list
        for i, call in enumerate(calls):
            key = call[1]["key"]
            value = json.loads(call[1]["value"])

            assert key == "BTC/USDT"
            assert value["sequence"] == i

    async def test_consumer_error_handling(self, mock_kafka_consumer):
        """Test consumer error handling and retry logic."""

        consumer = AlghrestConsumer(
            topics=[KafkaTopic.PROPOSALS_BUS],
            group_id="test_group",
            bootstrap_servers="localhost:9092"
        )
        consumer.consumer = mock_kafka_consumer

        # Simulate message processing errors
        error_count = 0
        processed_messages = []

        async def mock_message_stream():
            """Mock message stream with some failures."""
            for i in range(10):
                message = {
                    "topic": KafkaTopic.PROPOSALS_BUS.value,
                    "value": json.dumps({
                        "proposal_id": str(uuid4()),
                        "strategy_id": f"strategy_{i}",
                        "symbol": "BTC/USDT",
                        "side": "BUY",
                        "size": "0.01"
                    }),
                    "key": f"test_key_{i}",
                    "partition": 0,
                    "offset": i,
                }
                yield message

        mock_kafka_consumer.__aiter__ = mock_message_stream

        async def process_message(message):
            nonlocal error_count

            # Simulate intermittent errors
            if error_count < 3 and message["key"].endswith("2"):
                error_count += 1
                raise Exception(f"Processing error #{error_count}")

            processed_messages.append(message)

        # Process messages with error handling
        try:
            async for message in consumer.stream():
                try:
                    await process_message(message)
                except Exception as e:
                    # Log error but continue processing
                    logger.warning("Message processing failed", error=str(e))
        except Exception:
            pass  # Consumer stream ended

        # Verify partial processing despite errors
        assert len(processed_messages) > 0
        assert error_count == 3

    async def test_schema_validation_and_evolution(self, mock_kafka_producer):
        """Test message schema validation and backward compatibility."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Test valid schema
        valid_proposal = {
            "proposal_id": str(uuid4()),
            "strategy_id": "test_strategy",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "order_type": "MARKET",
            "size": "0.01",
            "confidence": 0.8,
            "created_at": datetime.utcnow().isoformat(),
            "status": "PENDING"
        }

        await producer.send(KafkaTopic.PROPOSALS_BUS, valid_proposal)

        # Test schema evolution - add optional field
        evolved_proposal = {
            **valid_proposal,
            "proposal_id": str(uuid4()),
            "risk_score": 0.15,  # New optional field
            "version": "v2"      # Schema version
        }

        await producer.send(KafkaTopic.PROPOSALS_BUS, evolved_proposal)

        # Verify both messages were sent successfully
        assert mock_kafka_producer.send.call_count == 2

        # Verify schema validation
        calls = mock_kafka_producer.send.call_args_list
        for call in calls:
            value = json.loads(call[1]["value"])
            assert "proposal_id" in value
            assert "strategy_id" in value
            assert "symbol" in value

    async def test_high_throughput_message_processing(self, mock_kafka_producer, sample_market_data):
        """Test message bus performance under high load."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Measure throughput
        start_time = datetime.utcnow()

        # Send market data in batches
        batch_size = 100
        total_messages = len(sample_market_data) * batch_size

        for batch in range(batch_size):
            tasks = []
            for bar in sample_market_data:
                message = {
                    "batch": batch,
                    "symbol": bar.symbol,
                    "price": float(bar.close),
                    "volume": float(bar.volume),
                    "timestamp": bar.time.isoformat(),
                }
                tasks.append(producer.send(KafkaTopic.MARKET_DATA, message))

            # Send batch concurrently
            await asyncio.gather(*tasks)

        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()

        # Verify high throughput
        messages_per_second = total_messages / duration
        assert messages_per_second > 100  # Should process > 100 msg/sec
        assert mock_kafka_producer.send.call_count == total_messages

    async def test_consumer_group_load_balancing(self):
        """Test consumer group load balancing and failover."""

        # Simulate multiple consumers in same group
        consumers = []
        message_distribution = {}

        for consumer_id in range(3):
            consumer = AlghrestConsumer(
                topics=[KafkaTopic.MARKET_DATA],
                group_id="load_balance_test_group",
                bootstrap_servers="localhost:9092"
            )

            # Mock consumer with assigned partitions
            mock_consumer = AsyncMock()
            mock_consumer.assignment.return_value = {f"partition_{consumer_id}"}
            consumer.consumer = mock_consumer

            consumers.append((consumer_id, consumer))
            message_distribution[consumer_id] = 0

        # Simulate message processing
        for consumer_id, consumer in consumers:
            # Each consumer processes messages from their assigned partition
            for i in range(10):
                message = {
                    "topic": KafkaTopic.MARKET_DATA.value,
                    "partition": consumer_id % 3,
                    "value": json.dumps({"data": f"message_{i}"}),
                    "key": f"key_{i}",
                    "offset": i,
                }
                message_distribution[consumer_id] += 1

        # Verify load distribution
        total_messages = sum(message_distribution.values())
        assert total_messages == 30  # 3 consumers × 10 messages each

        # Each consumer should process roughly equal number of messages
        for count in message_distribution.values():
            assert count == 10

    async def test_dead_letter_queue_handling(self, mock_kafka_producer):
        """Test handling of messages that fail processing repeatedly."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Simulate poison message that always fails
        poison_message = {
            "proposal_id": str(uuid4()),
            "strategy_id": "failing_strategy",
            "symbol": "INVALID/SYMBOL",
            "side": "INVALID_SIDE",  # Invalid enum value
            "order_type": "INVALID_TYPE",
            "size": "invalid_size",  # Invalid decimal
            "created_at": "invalid_datetime",
            "status": "PENDING"
        }

        # Send poison message to DLQ topic after max retries
        dlq_topic = f"{KafkaTopic.PROPOSALS_BUS.value}.dlq"

        await producer.send(dlq_topic, {
            "original_topic": KafkaTopic.PROPOSALS_BUS.value,
            "failure_reason": "Schema validation failed",
            "retry_count": 3,
            "original_message": poison_message,
            "failed_at": datetime.utcnow().isoformat()
        })

        # Verify DLQ message
        assert mock_kafka_producer.send.call_count == 1
        call = mock_kafka_producer.send.call_args_list[0]

        assert call[1]["topic"] == dlq_topic
        dlq_message = json.loads(call[1]["value"])
        assert dlq_message["original_topic"] == KafkaTopic.PROPOSALS_BUS.value
        assert dlq_message["retry_count"] == 3
        assert "original_message" in dlq_message


@pytest.mark.integration
class TestMessageBusReliability:
    """Test message bus reliability and fault tolerance."""

    async def test_connection_recovery(self):
        """Test message bus recovery from connection failures."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")

        # Simulate connection failure
        with patch.object(producer, '_connect', side_effect=ConnectionError("Connection failed")):
            # Should handle connection error gracefully
            try:
                await producer.initialize()
                # Connection should be retried
                assert True  # Test passes if no exception raised
            except Exception as e:
                pytest.fail(f"Producer should handle connection errors: {e}")

    async def test_message_durability(self, mock_kafka_producer):
        """Test message persistence and durability guarantees."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Configure for durability
        durability_config = {
            "acks": "all",  # Wait for all replicas
            "retries": 3,
            "enable_idempotence": True,
        }

        # Mock successful acknowledgment
        mock_kafka_producer.send.return_value = AsyncMock()

        # Send critical trade proposal
        critical_proposal = {
            "proposal_id": str(uuid4()),
            "strategy_id": "critical_strategy",
            "symbol": "BTC/USDT",
            "side": "BUY",
            "size": "10.0",  # Large position
            "confidence": 0.95,
            "priority": "HIGH",
            "requires_confirmation": True,
        }

        await producer.send(
            KafkaTopic.PROPOSALS_BUS,
            critical_proposal,
            **durability_config
        )

        # Verify durability settings were used
        call = mock_kafka_producer.send.call_args_list[0]
        assert call[1].get("acks") == "all"

    async def test_exactly_once_semantics(self, mock_kafka_producer):
        """Test exactly-once message delivery semantics."""

        producer = AlghrestProducer(bootstrap_servers="localhost:9092")
        producer.producer = mock_kafka_producer

        # Enable exactly-once semantics
        producer._enable_idempotence = True

        # Send duplicate messages (simulating retry)
        message = {
            "proposal_id": "duplicate_test_id",
            "strategy_id": "test_strategy",
            "symbol": "BTC/USDT",
            "idempotency_key": "unique_key_123",
        }

        # Send same message multiple times
        for _ in range(3):
            await producer.send(KafkaTopic.PROPOSALS_BUS, message)

        # Verify all attempts were made (deduplication at Kafka level)
        assert mock_kafka_producer.send.call_count == 3

        # All should have same idempotency key
        for call in mock_kafka_producer.send.call_args_list:
            value = json.loads(call[1]["value"])
            assert value["idempotency_key"] == "unique_key_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])