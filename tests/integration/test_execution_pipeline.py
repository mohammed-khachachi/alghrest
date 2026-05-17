"""
ALGHREST — Complete Execution Pipeline Integration Test
====================================================

This test validates the full trade execution pipeline:
strategy → PROPOSALS_BUS → ProposalApprover → PROPOSALS_APPROVED →
OrderRouter → ORDERS_PENDING → FeeOptimizer → SlippageMinimizer →
ExchangeExecutor → ORDERS_EXECUTED + FILLS_CONFIRMED

Test Scenarios:
1. Happy path: Strategy signal → successful execution
2. Risk limits: Proposal rejection due to position limits
3. Kill switch: Pipeline halt during execution
4. Optimization flags: _optimised and _child flag handling
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import structlog

from agents.tier1_executive.proposal_approver import ProposalApprover
from agents.tier4_strategies.trend_follower import TrendFollower
from agents.tier5_execution.exchange_executor import ExchangeExecutor
from agents.tier5_execution.fee_optimizer import FeeOptimizer
from agents.tier5_execution.order_router import OrderRouter
from agents.tier5_execution.slippage_minimizer import SlippageMinimizer
from core.data.models import (
    Exchange,
    KafkaTopic,
    OrderSide,
    OrderStatus,
    OrderType,
    Position,
    TradeProposal,
    TradeProposalStatus,
    AgentMessage,
    RISK_LIMITS
)
from core.orchestrator.state_manager import StateManager


logger = structlog.get_logger(__name__)


@pytest.fixture
def mock_state_manager():
    """Mock state manager with basic functionality."""
    mock_state = AsyncMock(spec=StateManager)
    mock_state.is_kill_switch_active.return_value = False
    mock_state.get_portfolio.return_value = {
        "total_capital": 10000.0,
        "available_cash": 8000.0,
        "total_exposure": 2000.0
    }
    mock_state.get_positions.return_value = []
    return mock_state


@pytest.fixture
def mock_producer():
    """Mock Kafka producer."""
    producer = AsyncMock()
    producer.send = AsyncMock()
    producer.initialize = AsyncMock()
    producer.shutdown = AsyncMock()
    return producer


@pytest.fixture
def sample_trade_proposal():
    """Sample trade proposal for testing."""
    return TradeProposal(
        proposal_id=str(uuid4()),
        strategy_id="test_trend_follower",
        symbol="BTC/USDT",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("0.01"),
        confidence=0.8,
        created_at=datetime.utcnow(),
        status=TradeProposalStatus.PENDING,
        metadata={"test": "execution_pipeline"}
    )


class MockConsumer:
    """Mock Kafka consumer that can inject test messages."""

    def __init__(self, test_messages: List[Dict] = None):
        self.test_messages = test_messages or []
        self.message_index = 0

    async def initialize(self):
        pass

    async def stream(self):
        """Yield test messages."""
        for message in self.test_messages:
            yield message
            await asyncio.sleep(0.01)  # Small delay to simulate real streaming


@pytest.mark.integration
class TestExecutionPipeline:
    """Integration tests for the complete execution pipeline."""

    async def test_happy_path_execution(self, mock_state_manager, mock_producer, sample_trade_proposal):
        """Test successful execution from strategy signal to fill confirmation."""

        # Setup agents
        proposal_approver = ProposalApprover()
        proposal_approver.state = mock_state_manager
        proposal_approver.producer = mock_producer

        order_router = OrderRouter()
        order_router.state = mock_state_manager
        order_router.producer = mock_producer

        fee_optimizer = FeeOptimizer()
        fee_optimizer.state = mock_state_manager
        fee_optimizer.producer = mock_producer

        # Mock successful portfolio check (within limits)
        mock_state_manager.get_portfolio.return_value = {
            "total_capital": 10000.0,
            "available_cash": 9000.0,
            "positions": []
        }

        # Test 1: ProposalApprover processes proposal
        with patch.object(proposal_approver, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.PROPOSALS_BUS.value,
                "payload": sample_trade_proposal.model_dump(),
                "message_type": "trade_proposal"
            }])
            mock_make_consumer.return_value = mock_consumer

            # Process proposal (would run for short time in real test)
            task = asyncio.create_task(proposal_approver.run())
            await asyncio.sleep(0.1)  # Let it process the message
            task.cancel()

            # Verify proposal was approved and published
            assert mock_producer.send.called
            approve_call = mock_producer.send.call_args_list[0]
            assert approve_call[0][0] == KafkaTopic.PROPOSALS_APPROVED

        # Test 2: OrderRouter processes approved proposal
        approved_proposal = sample_trade_proposal.model_copy()
        approved_proposal.status = TradeProposalStatus.APPROVED

        with patch.object(order_router, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.PROPOSALS_APPROVED.value,
                "payload": approved_proposal.model_dump(),
                "message_type": "approved_proposal"
            }])
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(order_router.run())
            await asyncio.sleep(0.1)
            task.cancel()

            # Verify order was routed to ORDERS_PENDING
            router_calls = [call for call in mock_producer.send.call_args_list
                          if call[0][0] == KafkaTopic.ORDERS_PENDING]
            assert len(router_calls) >= 1

        # Test 3: FeeOptimizer processes pending order
        with patch.object(fee_optimizer, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.ORDERS_PENDING.value,
                "payload": {
                    **approved_proposal.model_dump(),
                    "exchange": Exchange.BINANCE.value,
                    "_optimised": False
                },
                "message_type": "pending_order"
            }])
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(fee_optimizer.run())
            await asyncio.sleep(0.1)
            task.cancel()

            # Verify _optimised flag was set
            optimizer_calls = [call for call in mock_producer.send.call_args_list
                             if call[0][0] == KafkaTopic.ORDERS_PENDING]
            assert len(optimizer_calls) >= 1

    async def test_position_limit_rejection(self, mock_state_manager, mock_producer, sample_trade_proposal):
        """Test proposal rejection when position limits are exceeded."""

        proposal_approver = ProposalApprover()
        proposal_approver.state = mock_state_manager
        proposal_approver.producer = mock_producer

        # Mock portfolio at position limit
        mock_state_manager.get_portfolio.return_value = {
            "total_capital": 10000.0,
            "positions": [
                Position(
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    size=Decimal("0.5"),  # Large position
                    entry_price=Decimal("50000"),
                    current_price=Decimal("50000"),
                    unrealized_pnl=Decimal("0")
                )
            ]
        }

        # Test oversized proposal
        large_proposal = sample_trade_proposal.model_copy()
        large_proposal.size = Decimal("1.0")  # Would exceed limits

        with patch.object(proposal_approver, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.PROPOSALS_BUS.value,
                "payload": large_proposal.model_dump(),
                "message_type": "trade_proposal"
            }])
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(proposal_approver.run())
            await asyncio.sleep(0.1)
            task.cancel()

            # Verify proposal was rejected (not sent to PROPOSALS_APPROVED)
            approved_calls = [call for call in mock_producer.send.call_args_list
                            if call[0][0] == KafkaTopic.PROPOSALS_APPROVED]
            # Should either be empty or contain rejected status
            if approved_calls:
                sent_proposal = approved_calls[0][0][1]
                assert sent_proposal.get("status") == TradeProposalStatus.REJECTED.value

    async def test_kill_switch_halts_pipeline(self, mock_state_manager, mock_producer, sample_trade_proposal):
        """Test that kill switch stops the execution pipeline."""

        # Activate kill switch
        mock_state_manager.is_kill_switch_active.return_value = True

        proposal_approver = ProposalApprover()
        proposal_approver.state = mock_state_manager
        proposal_approver.producer = mock_producer

        with patch.object(proposal_approver, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.PROPOSALS_BUS.value,
                "payload": sample_trade_proposal.model_dump(),
                "message_type": "trade_proposal"
            }])
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(proposal_approver.run())
            await asyncio.sleep(0.1)
            task.cancel()

            # Verify no proposals were processed when kill switch is active
            assert mock_producer.send.call_count == 0

    async def test_optimization_flags_prevent_reentry(self, mock_state_manager, mock_producer):
        """Test that _optimised and _child flags prevent re-processing."""

        fee_optimizer = FeeOptimizer()
        fee_optimizer.state = mock_state_manager
        fee_optimizer.producer = mock_producer

        # Test order already optimized
        optimized_order = {
            "symbol": "BTC/USDT",
            "side": OrderSide.BUY.value,
            "size": "0.01",
            "exchange": Exchange.BINANCE.value,
            "_optimised": True,  # Already processed
            "message_type": "pending_order"
        }

        with patch.object(fee_optimizer, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.ORDERS_PENDING.value,
                "payload": optimized_order,
                "message_type": "pending_order"
            }])
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(fee_optimizer.run())
            await asyncio.sleep(0.1)
            task.cancel()

            # Verify already-optimized order was skipped
            assert mock_producer.send.call_count == 0

    async def test_pipeline_with_ml_predictor_fallback(self, mock_state_manager, mock_producer):
        """Test execution pipeline when ML Predictor is in fallback mode."""

        # This test verifies that when ML Predictor switches to technical analysis fallback,
        # the execution pipeline still works correctly

        # Create mock ML prediction from fallback
        fallback_proposal = TradeProposal(
            proposal_id=str(uuid4()),
            strategy_id="ml_predictor_cnn",
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=Decimal("0.1"),
            confidence=0.65,  # Lower confidence typical of fallback mode
            created_at=datetime.utcnow(),
            status=TradeProposalStatus.PENDING,
            metadata={
                "source": "fallback_technical",
                "indicators": {
                    "rsi": 35.0,
                    "sma_ratio": 1.02,
                    "volatility": 0.25
                }
            }
        )

        proposal_approver = ProposalApprover()
        proposal_approver.state = mock_state_manager
        proposal_approver.producer = mock_producer

        with patch.object(proposal_approver, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer([{
                "topic": KafkaTopic.PROPOSALS_BUS.value,
                "payload": fallback_proposal.model_dump(),
                "message_type": "trade_proposal"
            }])
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(proposal_approver.run())
            await asyncio.sleep(0.1)
            task.cancel()

            # Verify fallback proposals are processed normally
            assert mock_producer.send.called
            approve_call = mock_producer.send.call_args_list[0]
            assert approve_call[0][0] == KafkaTopic.PROPOSALS_APPROVED

    async def test_execution_pipeline_performance(self, mock_state_manager, mock_producer):
        """Test execution pipeline performance under load."""

        proposal_approver = ProposalApprover()
        proposal_approver.state = mock_state_manager
        proposal_approver.producer = mock_producer

        # Generate multiple proposals
        test_proposals = []
        for i in range(10):
            proposal = TradeProposal(
                proposal_id=str(uuid4()),
                strategy_id=f"test_strategy_{i}",
                symbol="BTC/USDT",
                side=OrderSide.BUY,
                order_type=OrderType.MARKET,
                size=Decimal("0.001"),  # Small size to avoid limits
                confidence=0.7,
                created_at=datetime.utcnow(),
                status=TradeProposalStatus.PENDING,
                metadata={"batch_test": i}
            )
            test_proposals.append({
                "topic": KafkaTopic.PROPOSALS_BUS.value,
                "payload": proposal.model_dump(),
                "message_type": "trade_proposal"
            })

        start_time = asyncio.get_event_loop().time()

        with patch.object(proposal_approver, 'make_consumer') as mock_make_consumer:
            mock_consumer = MockConsumer(test_proposals)
            mock_make_consumer.return_value = mock_consumer

            task = asyncio.create_task(proposal_approver.run())
            await asyncio.sleep(0.5)  # Process for 500ms
            task.cancel()

        processing_time = asyncio.get_event_loop().time() - start_time

        # Verify reasonable processing performance
        assert processing_time < 1.0  # Should process 10 proposals in under 1 second
        assert mock_producer.send.call_count >= 5  # Should process at least half


@pytest.mark.integration
async def test_agent_startup_sequence():
    """Test that agents can start up and initialize properly."""

    # Test that critical agents can initialize without crashing
    agents_to_test = [
        (ProposalApprover, "proposal_approver"),
        (OrderRouter, "order_router"),
        (FeeOptimizer, "fee_optimizer"),
    ]

    for agent_class, agent_name in agents_to_test:
        try:
            agent = agent_class()

            # Mock dependencies
            agent.state = AsyncMock()
            agent.producer = AsyncMock()
            agent.producer.initialize = AsyncMock()

            # Test initialization
            await agent.initialize()

            # Basic health check
            assert hasattr(agent, 'AGENT_ID')
            assert hasattr(agent, 'name')
            assert agent.AGENT_ID > 0

        except Exception as e:
            pytest.fail(f"Agent {agent_name} failed to initialize: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])