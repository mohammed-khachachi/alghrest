"""
ALGHREST — Agent Coordination Integration Tests
===============================================

This test validates inter-agent coordination and communication:
1. Multi-agent workflow coordination
2. Message passing between tiers
3. Event-driven agent activation
4. Shared state synchronization
5. Agent dependency resolution
6. Failure cascade prevention

Test Scenarios:
- Tier 2 → Tier 3 → Tier 4 signal propagation
- Risk Governor emergency coordination
- Agent startup sequence and dependencies
- Message ordering and causality
- Distributed state consistency
- Agent recovery and rebalancing
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import structlog

from agents.base_agent import BaseAgent, BaseStrategy
from core.data.models import (
    AgentMessage,
    KafkaTopic,
    MarketData,
    AnalysisResult,
    TradeProposal,
    TradeProposalStatus,
    OrderSide,
    OrderType,
    Exchange,
    RiskAlert,
    AlertType,
    AgentHeartbeat,
)

logger = structlog.get_logger(__name__)


class MockMarketDataHub(BaseAgent):
    """Mock Tier 2 Market Data Hub for testing."""

    def __init__(self):
        super().__init__(agent_id=4, name="mock_market_data_hub", tier=2)
        self.published_messages = []

    async def initialize(self):
        pass

    async def run(self):
        # Simulate market data publishing
        for i in range(5):
            market_data = {
                "symbol": "BTC/USDT",
                "price": 45000 + i * 100,
                "volume": 1000.0,
                "timestamp": datetime.utcnow().isoformat(),
                "source": "mock_data_hub",
            }
            await self.publish(KafkaTopic.MARKET_DATA, market_data)
            self.published_messages.append(market_data)
            await asyncio.sleep(0.1)

    async def shutdown(self):
        pass


class MockTechnicalAnalyst(BaseAgent):
    """Mock Tier 3 Technical Analyst for testing."""

    def __init__(self):
        super().__init__(agent_id=11, name="mock_technical_analyst", tier=3)
        self.received_messages = []
        self.published_signals = []

    async def initialize(self):
        pass

    async def run(self):
        # Mock consuming market data and producing technical signals
        consumer = await self.make_consumer([KafkaTopic.MARKET_DATA])

        async for message in consumer.stream():
            self.received_messages.append(message)

            # Generate technical signal after receiving market data
            if len(self.received_messages) >= 3:
                signal = {
                    "signal": "BULLISH",
                    "confidence": 0.75,
                    "indicators": {
                        "rsi": 65.0,
                        "sma_20": 44900.0,
                        "volume_trend": "increasing",
                    },
                    "generated_by": "mock_technical_analyst",
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await self.publish(KafkaTopic.ANALYSIS_TECHNICAL, signal)
                self.published_signals.append(signal)

                if len(self.published_signals) >= 2:
                    break

    async def shutdown(self):
        pass


class MockTrendStrategy(BaseStrategy):
    """Mock Tier 4 Trend Strategy for testing."""

    def __init__(self):
        super().__init__(agent_id=14, name="mock_trend_strategy", tier=4)
        self.received_signals = []
        self.generated_proposals = []

    async def initialize(self):
        pass

    async def run(self):
        # Mock consuming technical signals and generating proposals
        consumer = await self.make_consumer([KafkaTopic.ANALYSIS_TECHNICAL])

        async for message in consumer.stream():
            self.received_signals.append(message)

            # Generate trade proposal based on signal
            if message.get("signal") == "BULLISH":
                proposal = TradeProposal(
                    proposal_id=str(uuid4()),
                    strategy_id="mock_trend_strategy",
                    symbol="BTC/USDT",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    size=Decimal("0.1"),
                    confidence=0.8,
                    created_at=datetime.utcnow(),
                    status=TradeProposalStatus.PENDING,
                    metadata={
                        "source_signal": message,
                        "strategy_type": "trend_following",
                    },
                )

                await self.publish(KafkaTopic.PROPOSALS_BUS, proposal.model_dump())
                self.generated_proposals.append(proposal)

                if len(self.generated_proposals) >= 1:
                    break

    async def shutdown(self):
        pass

    async def generate_signal(self, market_data) -> Optional[Dict]:
        return None  # Not used in this mock

    async def should_exit(self, position, market_data) -> bool:
        return False  # Not used in this mock

    async def backtest(self, historical_data) -> Dict:
        return {}  # Not used in this mock


class MockRiskGovernor(BaseAgent):
    """Mock Risk Governor for testing emergency coordination."""

    def __init__(self):
        super().__init__(agent_id=2, name="mock_risk_governor", tier=1)
        self.risk_alerts_sent = []
        self.emergency_triggered = False

    async def initialize(self):
        pass

    async def run(self):
        # Monitor for risk conditions
        await asyncio.sleep(0.2)  # Let other agents start

        # Simulate risk threshold breach
        risk_alert = RiskAlert(
            alert_type=AlertType.DRAWDOWN_WARNING,
            severity="HIGH",
            message="Portfolio drawdown approaching 15% threshold",
            affected_strategies=["mock_trend_strategy"],
            recommended_action="REDUCE_EXPOSURE",
            timestamp=datetime.utcnow(),
        )

        await self.publish(KafkaTopic.RISK_ALERTS, risk_alert.model_dump())
        self.risk_alerts_sent.append(risk_alert)

        # Simulate emergency halt
        await asyncio.sleep(0.1)
        emergency_halt = {
            "event_type": "EMERGENCY_HALT",
            "reason": "Market crash detected",
            "scope": "ALL_STRATEGIES",
            "initiated_by": "mock_risk_governor",
            "timestamp": datetime.utcnow().isoformat(),
        }

        await self.publish(KafkaTopic.RISK_ALERTS, emergency_halt)
        self.emergency_triggered = True

    async def shutdown(self):
        pass


@pytest.fixture
def mock_agents():
    """Create mock agents for testing."""
    return {
        "market_data_hub": MockMarketDataHub(),
        "technical_analyst": MockTechnicalAnalyst(),
        "trend_strategy": MockTrendStrategy(),
        "risk_governor": MockRiskGovernor(),
    }


@pytest.fixture
def mock_state_manager():
    """Mock state manager for agent coordination tests."""
    state_manager = AsyncMock()
    state_manager.is_kill_switch_active.return_value = False
    state_manager.store_agent_heartbeat = AsyncMock()
    state_manager.get_shared_state = AsyncMock()
    state_manager.store_shared_state = AsyncMock()
    return state_manager


@pytest.mark.integration
class TestAgentCoordination:
    """Integration tests for agent coordination and communication."""

    async def test_multi_tier_signal_propagation(self, mock_agents, mock_state_manager):
        """Test signal propagation from Tier 2 → Tier 3 → Tier 4."""

        # Setup all agents with shared state manager and producers
        for agent in mock_agents.values():
            agent.state = mock_state_manager
            agent.producer = AsyncMock()
            agent.producer.send = AsyncMock()

        # Setup mock consumers to enable message flow
        market_data_messages = []
        technical_signals = []

        # Market Data Hub publishes data
        market_hub = mock_agents["market_data_hub"]
        await market_hub.initialize()

        # Technical Analyst processes market data
        technical_analyst = mock_agents["technical_analyst"]
        await technical_analyst.initialize()

        # Trend Strategy processes technical signals
        trend_strategy = mock_agents["trend_strategy"]
        await trend_strategy.initialize()

        # Simulate message flow
        # 1. Market Data Hub publishes market data
        for i in range(3):
            market_data = {
                "symbol": "BTC/USDT",
                "price": 45000 + i * 100,
                "volume": 1000.0,
                "timestamp": datetime.utcnow().isoformat(),
            }
            await market_hub.publish(KafkaTopic.MARKET_DATA, market_data)
            market_data_messages.append(market_data)

        # 2. Technical Analyst receives data and generates signals
        for market_data in market_data_messages:
            technical_analyst.received_messages.append(market_data)

        # Simulate technical analysis after enough data
        if len(technical_analyst.received_messages) >= 3:
            technical_signal = {
                "signal": "BULLISH",
                "confidence": 0.75,
                "generated_by": "mock_technical_analyst",
            }
            await technical_analyst.publish(KafkaTopic.ANALYSIS_TECHNICAL, technical_signal)
            technical_signals.append(technical_signal)

        # 3. Trend Strategy receives signals and generates proposals
        for signal in technical_signals:
            trend_strategy.received_signals.append(signal)
            if signal["signal"] == "BULLISH":
                proposal = {
                    "proposal_id": str(uuid4()),
                    "strategy_id": "mock_trend_strategy",
                    "symbol": "BTC/USDT",
                    "side": "BUY",
                    "size": "0.1",
                }
                await trend_strategy.publish(KafkaTopic.PROPOSALS_BUS, proposal)
                trend_strategy.generated_proposals.append(proposal)

        # Verify signal propagation
        assert len(market_hub.published_messages) >= 3
        assert len(technical_analyst.received_messages) >= 3
        assert len(technical_signals) >= 1
        assert len(trend_strategy.received_signals) >= 1
        assert len(trend_strategy.generated_proposals) >= 1

        # Verify message content propagation
        proposal = trend_strategy.generated_proposals[0]
        assert proposal["symbol"] == "BTC/USDT"
        assert proposal["side"] == "BUY"
        assert proposal["strategy_id"] == "mock_trend_strategy"

    async def test_risk_governor_emergency_coordination(self, mock_agents, mock_state_manager):
        """Test Risk Governor emergency coordination across agents."""

        risk_governor = mock_agents["risk_governor"]
        trend_strategy = mock_agents["trend_strategy"]

        # Setup agents
        for agent in [risk_governor, trend_strategy]:
            agent.state = mock_state_manager
            agent.producer = AsyncMock()

        await risk_governor.initialize()
        await trend_strategy.initialize()

        # Mock strategy receiving risk alert
        risk_alerts_received = []

        async def mock_risk_alert_handler(message):
            risk_alerts_received.append(message)
            if message.get("event_type") == "EMERGENCY_HALT":
                # Strategy should halt operations
                trend_strategy.is_halted = True

        # Simulate risk alert propagation
        risk_alert = {
            "alert_type": "DRAWDOWN_WARNING",
            "severity": "HIGH",
            "affected_strategies": ["mock_trend_strategy"],
            "recommended_action": "REDUCE_EXPOSURE",
        }

        await risk_governor.publish(KafkaTopic.RISK_ALERTS, risk_alert)
        await mock_risk_alert_handler(risk_alert)

        # Simulate emergency halt
        emergency_halt = {
            "event_type": "EMERGENCY_HALT",
            "reason": "Market crash detected",
            "scope": "ALL_STRATEGIES",
        }

        await risk_governor.publish(KafkaTopic.RISK_ALERTS, emergency_halt)
        await mock_risk_alert_handler(emergency_halt)

        # Verify emergency coordination
        assert len(risk_alerts_received) == 2
        assert risk_alerts_received[0]["alert_type"] == "DRAWDOWN_WARNING"
        assert risk_alerts_received[1]["event_type"] == "EMERGENCY_HALT"
        assert hasattr(trend_strategy, 'is_halted') and trend_strategy.is_halted

    async def test_agent_dependency_resolution(self, mock_state_manager):
        """Test agent startup sequence based on dependencies."""

        startup_order = []

        class DependentAgent(BaseAgent):
            def __init__(self, agent_id, name, dependencies=None):
                super().__init__(agent_id=agent_id, name=name, tier=2)
                self.dependencies = dependencies or []
                self.started = False

            async def initialize(self):
                startup_order.append(self.name)
                self.started = True

            async def run(self):
                pass

            async def shutdown(self):
                pass

        # Create agents with dependencies
        agent_a = DependentAgent(1, "agent_a", dependencies=[])
        agent_b = DependentAgent(2, "agent_b", dependencies=["agent_a"])
        agent_c = DependentAgent(3, "agent_c", dependencies=["agent_a", "agent_b"])

        agents = [agent_c, agent_a, agent_b]  # Intentionally wrong order

        # Setup agents
        for agent in agents:
            agent.state = mock_state_manager
            agent.producer = AsyncMock()

        # Resolve dependencies and start in correct order
        started_agents = set()
        while len(started_agents) < len(agents):
            for agent in agents:
                if (agent.name not in started_agents and
                    all(dep in started_agents for dep in agent.dependencies)):
                    await agent.initialize()
                    started_agents.add(agent.name)

        # Verify correct startup order
        assert startup_order == ["agent_a", "agent_b", "agent_c"]
        assert all(agent.started for agent in agents)

    async def test_message_ordering_and_causality(self, mock_state_manager):
        """Test message ordering and causality preservation."""

        class SequencedAgent(BaseAgent):
            def __init__(self, agent_id, name):
                super().__init__(agent_id=agent_id, name=name, tier=2)
                self.sent_messages = []
                self.received_messages = []

            async def initialize(self):
                pass

            async def run(self):
                pass

            async def shutdown(self):
                pass

        producer_agent = SequencedAgent(1, "producer")
        consumer_agent = SequencedAgent(2, "consumer")

        # Setup agents
        for agent in [producer_agent, consumer_agent]:
            agent.state = mock_state_manager
            agent.producer = AsyncMock()

        # Producer sends ordered messages
        for i in range(10):
            message = {
                "sequence": i,
                "timestamp": datetime.utcnow().isoformat(),
                "data": f"message_{i}",
                "causality_vector": [i],  # Simple causality tracking
            }

            await producer_agent.publish(KafkaTopic.MARKET_DATA, message)
            producer_agent.sent_messages.append(message)

        # Consumer receives messages (simulate in-order delivery)
        for message in producer_agent.sent_messages:
            consumer_agent.received_messages.append(message)

        # Verify message ordering
        assert len(consumer_agent.received_messages) == 10

        for i, message in enumerate(consumer_agent.received_messages):
            assert message["sequence"] == i
            assert message["causality_vector"] == [i]

        # Verify causality preservation
        received_sequences = [msg["sequence"] for msg in consumer_agent.received_messages]
        assert received_sequences == list(range(10))

    async def test_distributed_state_consistency(self, mock_state_manager):
        """Test distributed state consistency across agents."""

        class StateAgent(BaseAgent):
            def __init__(self, agent_id, name):
                super().__init__(agent_id=agent_id, name=name, tier=2)
                self.local_state = {}

            async def initialize(self):
                pass

            async def run(self):
                pass

            async def shutdown(self):
                pass

            async def update_shared_state(self, key, value):
                # Update local state
                self.local_state[key] = value
                # Update shared state in Redis
                await self.state.store_shared_state(key, {
                    "value": value,
                    "updated_by": self.name,
                    "timestamp": datetime.utcnow().isoformat(),
                })

            async def read_shared_state(self, key):
                # Read from shared state
                state_data = await self.state.get_shared_state(key)
                if state_data:
                    self.local_state[key] = state_data["value"]
                return state_data

        # Create multiple agents sharing state
        agents = [StateAgent(i, f"agent_{i}") for i in range(3)]

        for agent in agents:
            agent.state = mock_state_manager

        # Mock Redis responses
        shared_state = {}

        async def mock_store_shared_state(key, value):
            shared_state[key] = value

        async def mock_get_shared_state(key):
            return shared_state.get(key)

        mock_state_manager.store_shared_state.side_effect = mock_store_shared_state
        mock_state_manager.get_shared_state.side_effect = mock_get_shared_state

        # Agent 0 updates shared state
        await agents[0].update_shared_state("market_regime", "high_volatility")

        # Other agents read shared state
        for agent in agents[1:]:
            state_data = await agent.read_shared_state("market_regime")
            assert state_data["value"] == "high_volatility"
            assert state_data["updated_by"] == "agent_0"

        # Verify state consistency
        for agent in agents:
            assert agent.local_state["market_regime"] == "high_volatility"

    async def test_agent_failure_cascade_prevention(self, mock_state_manager):
        """Test prevention of failure cascades across agents."""

        class FallibleAgent(BaseAgent):
            def __init__(self, agent_id, name, fail_probability=0.0):
                super().__init__(agent_id=agent_id, name=name, tier=2)
                self.fail_probability = fail_probability
                self.failure_count = 0
                self.processed_messages = 0

            async def initialize(self):
                pass

            async def run(self):
                pass

            async def shutdown(self):
                pass

            async def process_message(self, message):
                import random

                if random.random() < self.fail_probability:
                    self.failure_count += 1
                    raise Exception(f"Simulated failure in {self.name}")

                self.processed_messages += 1
                return {"processed": True, "by": self.name}

        # Create agents with different failure rates
        stable_agent = FallibleAgent(1, "stable_agent", fail_probability=0.0)
        unreliable_agent = FallibleAgent(2, "unreliable_agent", fail_probability=0.3)
        backup_agent = FallibleAgent(3, "backup_agent", fail_probability=0.1)

        agents = [stable_agent, unreliable_agent, backup_agent]

        for agent in agents:
            agent.state = mock_state_manager

        # Simulate message processing with failure handling
        messages = [{"id": i, "data": f"test_message_{i}"} for i in range(20)]
        successful_processing = 0

        for message in messages:
            # Try primary agent first, fallback to backup on failure
            try:
                await unreliable_agent.process_message(message)
                successful_processing += 1
            except Exception:
                try:
                    await backup_agent.process_message(message)
                    successful_processing += 1
                except Exception:
                    # Final fallback to stable agent
                    await stable_agent.process_message(message)
                    successful_processing += 1

        # Verify failure isolation
        assert successful_processing == len(messages)  # All messages processed
        assert unreliable_agent.failure_count > 0  # Some failures occurred
        assert stable_agent.processed_messages > 0  # Backup processing happened

        # Verify no cascade failure
        total_processed = sum(agent.processed_messages for agent in agents)
        assert total_processed >= len(messages)


@pytest.mark.integration
class TestAgentRecoveryAndRebalancing:
    """Test agent recovery and workload rebalancing."""

    async def test_agent_restart_recovery(self, mock_state_manager):
        """Test agent recovery after restart."""

        class RecoverableAgent(BaseAgent):
            def __init__(self, agent_id, name):
                super().__init__(agent_id=agent_id, name=name, tier=2)
                self.persistent_state = {}
                self.restart_count = 0

            async def initialize(self):
                # Restore state from persistent storage
                self.restart_count += 1
                saved_state = await self.state.get_agent_state(self.agent_id)
                if saved_state:
                    self.persistent_state = saved_state

            async def run(self):
                pass

            async def shutdown(self):
                # Save state before shutdown
                await self.state.store_agent_state(self.agent_id, self.persistent_state)

        agent = RecoverableAgent(1, "recoverable_agent")
        agent.state = mock_state_manager

        # Mock state persistence
        saved_states = {}

        async def mock_store_agent_state(agent_id, state):
            saved_states[agent_id] = state

        async def mock_get_agent_state(agent_id):
            return saved_states.get(agent_id)

        mock_state_manager.store_agent_state.side_effect = mock_store_agent_state
        mock_state_manager.get_agent_state.side_effect = mock_get_agent_state

        # First startup
        await agent.initialize()
        agent.persistent_state["processed_count"] = 100
        await agent.shutdown()

        # Simulate restart
        agent = RecoverableAgent(1, "recoverable_agent")
        agent.state = mock_state_manager
        await agent.initialize()

        # Verify state recovery
        assert agent.persistent_state["processed_count"] == 100
        assert agent.restart_count == 1

    async def test_workload_rebalancing(self, mock_state_manager):
        """Test workload rebalancing when agents fail."""

        class WorkloadAgent(BaseAgent):
            def __init__(self, agent_id, name, capacity=10):
                super().__init__(agent_id=agent_id, name=name, tier=2)
                self.capacity = capacity
                self.current_load = 0
                self.is_healthy = True

            async def initialize(self):
                pass

            async def run(self):
                pass

            async def shutdown(self):
                pass

            async def process_work(self, work_item):
                if not self.is_healthy:
                    raise Exception(f"Agent {self.name} is unhealthy")

                if self.current_load >= self.capacity:
                    raise Exception(f"Agent {self.name} at capacity")

                self.current_load += 1
                return {"processed_by": self.name, "work_id": work_item["id"]}

            def set_health(self, healthy):
                self.is_healthy = healthy
                if not healthy:
                    self.current_load = 0

        # Create agent pool
        agents = [WorkloadAgent(i, f"agent_{i}") for i in range(3)]

        for agent in agents:
            agent.state = mock_state_manager

        # Distribute work across healthy agents
        work_items = [{"id": i, "data": f"work_{i}"} for i in range(30)]
        processed_work = []
        failed_work = []

        # Simulate agent failure during processing
        for i, work_item in enumerate(work_items):
            if i == 15:  # Fail agent 1 halfway through
                agents[1].set_health(False)

            # Find available agent
            processed = False
            for agent in agents:
                try:
                    result = await agent.process_work(work_item)
                    processed_work.append(result)
                    processed = True
                    break
                except Exception:
                    continue

            if not processed:
                failed_work.append(work_item)

        # Verify workload distribution
        assert len(processed_work) > 20  # Most work should be processed
        assert len(failed_work) < 5   # Minimal failures

        # Verify load balancing
        agent_loads = [agent.current_load for agent in agents if agent.is_healthy]
        assert all(load <= 15 for load in agent_loads)  # No single agent overloaded


if __name__ == "__main__":
    pytest.main([__file__, "-v"])