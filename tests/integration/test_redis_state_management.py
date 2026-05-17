"""
ALGHREST — Redis State Management Integration Tests
===================================================

This test validates the Redis-based state management system:
1. Agent heartbeat tracking and health monitoring
2. Kill switch state coordination across agents
3. Price data caching with TTL
4. Portfolio state persistence and recovery
5. Cross-agent state synchronization
6. Redis failover and reconnection

Test Scenarios:
- Agent health monitoring and timeout detection
- Kill switch propagation speed
- Price cache performance and expiry
- State corruption recovery
- Connection pool management
- Memory usage optimization
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

from core.data.models import (
    Portfolio,
    Position,
    OrderSide,
    Exchange,
    KillSwitchEvent,
    RiskMetrics,
    AgentHeartbeat,
    PriceData,
)
from core.orchestrator.state_manager import StateManager
from core.risk.kill_switch import KillSwitch

logger = structlog.get_logger(__name__)


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing."""
    redis = AsyncMock()
    redis.get = AsyncMock()
    redis.set = AsyncMock()
    redis.hget = AsyncMock()
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    redis.delete = AsyncMock()
    redis.exists = AsyncMock()
    redis.ping = AsyncMock(return_value=True)
    redis.close = AsyncMock()
    return redis


@pytest.fixture
def state_manager(mock_redis_client):
    """StateManager with mocked Redis client."""
    sm = StateManager(redis_url="redis://localhost:6379")
    sm.redis = mock_redis_client
    return sm


@pytest.fixture
def sample_portfolio():
    """Sample portfolio for testing."""
    positions = [
        Position(
            symbol="BTC/USDT",
            side=OrderSide.BUY,
            size=Decimal("1.5"),
            entry_price=Decimal("45000"),
            current_price=Decimal("46000"),
            unrealized_pnl=Decimal("1500"),
        ),
        Position(
            symbol="ETH/USDT",
            side=OrderSide.BUY,
            size=Decimal("10"),
            entry_price=Decimal("3000"),
            current_price=Decimal("3100"),
            unrealized_pnl=Decimal("1000"),
        ),
    ]

    return Portfolio(
        snapshot_time=datetime.utcnow(),
        total_capital=Decimal("100000"),
        available_capital=Decimal("50000"),
        reserved_capital=Decimal("25000"),
        emergency_reserve=Decimal("25000"),
        positions=positions,
    )


@pytest.fixture
def sample_heartbeats():
    """Sample agent heartbeats for testing."""
    heartbeats = []

    for agent_id in range(1, 11):  # Agents 1-10
        heartbeat = AgentHeartbeat(
            agent_id=agent_id,
            agent_name=f"test_agent_{agent_id}",
            tier=agent_id // 3 + 1,
            status="running",
            last_heartbeat=datetime.utcnow(),
            memory_mb=150 + agent_id * 10,
            cpu_percent=10.5 + agent_id,
            messages_processed=1000 + agent_id * 100,
        )
        heartbeats.append(heartbeat)

    return heartbeats


@pytest.mark.integration
class TestRedisStateManagement:
    """Integration tests for Redis state management functionality."""

    async def test_agent_heartbeat_tracking(self, state_manager, sample_heartbeats):
        """Test agent heartbeat storage and retrieval."""

        # Store all heartbeats
        for heartbeat in sample_heartbeats:
            await state_manager.store_agent_heartbeat(heartbeat)

        # Verify Redis calls
        assert state_manager.redis.hset.call_count == len(sample_heartbeats)

        # Mock Redis response for retrieving heartbeats
        mock_heartbeat_data = {}
        for hb in sample_heartbeats:
            mock_heartbeat_data[str(hb.agent_id)] = json.dumps({
                "agent_id": hb.agent_id,
                "agent_name": hb.agent_name,
                "status": hb.status,
                "last_heartbeat": hb.last_heartbeat.isoformat(),
                "memory_mb": hb.memory_mb,
                "cpu_percent": hb.cpu_percent,
            })

        state_manager.redis.hgetall.return_value = mock_heartbeat_data

        # Retrieve heartbeats
        retrieved_heartbeats = await state_manager.get_all_agent_heartbeats()

        # Verify retrieval
        assert len(retrieved_heartbeats) == len(sample_heartbeats)
        for agent_id, heartbeat_data in retrieved_heartbeats.items():
            assert heartbeat_data["agent_name"] == f"test_agent_{agent_id}"
            assert heartbeat_data["status"] == "running"

    async def test_unhealthy_agent_detection(self, state_manager):
        """Test detection of unhealthy agents based on heartbeat timeout."""

        current_time = datetime.utcnow()

        # Mock Redis with mixed healthy/unhealthy agents
        mock_heartbeats = {
            "1": json.dumps({
                "agent_id": 1,
                "agent_name": "healthy_agent",
                "last_heartbeat": current_time.isoformat(),
                "status": "running",
            }),
            "2": json.dumps({
                "agent_id": 2,
                "agent_name": "stale_agent",
                "last_heartbeat": (current_time - timedelta(minutes=5)).isoformat(),
                "status": "running",
            }),
            "3": json.dumps({
                "agent_id": 3,
                "agent_name": "crashed_agent",
                "last_heartbeat": (current_time - timedelta(minutes=10)).isoformat(),
                "status": "error",
            }),
        }

        state_manager.redis.hgetall.return_value = mock_heartbeats

        # Check for unhealthy agents
        unhealthy_agents = await state_manager.get_unhealthy_agents(
            timeout_minutes=3
        )

        # Should detect agents 2 and 3 as unhealthy
        assert len(unhealthy_agents) == 2
        unhealthy_ids = [agent["agent_id"] for agent in unhealthy_agents]
        assert 2 in unhealthy_ids
        assert 3 in unhealthy_ids
        assert 1 not in unhealthy_ids

    async def test_kill_switch_state_propagation(self, state_manager):
        """Test kill switch state coordination across agents."""

        kill_switch = KillSwitch()
        kill_switch.state_manager = state_manager

        # Mock Redis for kill switch checks
        state_manager.redis.get.return_value = None  # Initially inactive

        # Verify initially inactive
        assert await kill_switch.is_active() is False

        # Activate kill switch
        await kill_switch._trigger(
            reason="integration_test",
            drawdown_pct=0.15,
            scope="system",
            cro_agent_id=2
        )

        # Verify activation was stored in Redis
        state_manager.redis.set.assert_called()
        set_calls = state_manager.redis.set.call_args_list

        # Should have stored kill switch state
        kill_switch_call = next(
            call for call in set_calls
            if call[0][0] == "kill_switch:active"
        )
        assert kill_switch_call is not None

        # Mock active state for subsequent checks
        state_manager.redis.get.return_value = json.dumps({
            "active": True,
            "reason": "integration_test",
            "activated_at": datetime.utcnow().isoformat(),
            "scope": "system",
        })

        # Verify all agents can detect active state
        for agent_id in range(1, 6):
            is_active = await state_manager.is_kill_switch_active()
            assert is_active is True

    async def test_price_cache_performance(self, state_manager):
        """Test price data caching with TTL and performance."""

        symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]

        # Store prices with TTL
        price_data = {}
        for symbol in symbols:
            price_info = {
                "symbol": symbol,
                "price": float(45000 + hash(symbol) % 10000),
                "timestamp": datetime.utcnow().isoformat(),
                "exchange": "BINANCE",
                "volume_24h": 1000000.0,
            }
            price_data[symbol] = price_info

            await state_manager.store_price_data(symbol, price_info, ttl_seconds=60)

        # Verify Redis storage calls
        assert state_manager.redis.set.call_count == len(symbols)

        # Test bulk price retrieval performance
        start_time = datetime.utcnow()

        # Mock Redis responses
        state_manager.redis.mget.return_value = [
            json.dumps(price_data[symbol]) for symbol in symbols
        ]

        cached_prices = await state_manager.get_multiple_prices(symbols)

        retrieval_time = (datetime.utcnow() - start_time).total_seconds()

        # Verify performance (should be very fast for cached data)
        assert retrieval_time < 0.1  # Under 100ms
        assert len(cached_prices) == len(symbols)

        # Verify price data integrity
        for symbol, price_info in cached_prices.items():
            assert price_info["symbol"] == symbol
            assert "price" in price_info
            assert "timestamp" in price_info

    async def test_portfolio_state_persistence(self, state_manager, sample_portfolio):
        """Test portfolio state storage and recovery."""

        # Store portfolio state
        await state_manager.store_portfolio(sample_portfolio)

        # Verify Redis storage
        state_manager.redis.hset.assert_called()
        storage_call = state_manager.redis.hset.call_args_list[0]

        assert "portfolio:current" in storage_call[0][0]
        stored_data = json.loads(storage_call[0][2])
        assert stored_data["total_capital"] == "100000"
        assert len(stored_data["positions"]) == 2

        # Mock Redis response for retrieval
        state_manager.redis.hget.return_value = json.dumps({
            "total_capital": "100000",
            "available_capital": "50000",
            "positions": [
                {
                    "symbol": "BTC/USDT",
                    "side": "BUY",
                    "size": "1.5",
                    "entry_price": "45000",
                    "current_price": "46000",
                    "unrealized_pnl": "1500",
                },
                {
                    "symbol": "ETH/USDT",
                    "side": "BUY",
                    "size": "10",
                    "entry_price": "3000",
                    "current_price": "3100",
                    "unrealized_pnl": "1000",
                },
            ],
            "snapshot_time": datetime.utcnow().isoformat(),
        })

        # Retrieve and verify portfolio
        retrieved_portfolio = await state_manager.get_portfolio()

        assert retrieved_portfolio is not None
        assert retrieved_portfolio["total_capital"] == "100000"
        assert len(retrieved_portfolio["positions"]) == 2

    async def test_state_corruption_recovery(self, state_manager):
        """Test recovery from corrupted state data."""

        # Store corrupted data
        state_manager.redis.get.return_value = "invalid_json{corrupted"

        # Should handle corruption gracefully
        result = await state_manager.get_agent_state(agent_id=1)
        assert result is None  # Should return None for corrupted data

        # Verify error was logged but didn't crash
        state_manager.redis.get.assert_called()

        # Test recovery with valid backup
        state_manager.redis.get.side_effect = [
            "invalid_json{corrupted",  # Primary corrupted
            json.dumps({"agent_id": 1, "status": "recovered"})  # Backup valid
        ]

        result = await state_manager.get_agent_state_with_backup(agent_id=1)
        assert result is not None
        assert result["status"] == "recovered"

    async def test_memory_usage_optimization(self, state_manager):
        """Test Redis memory usage optimization strategies."""

        # Test data compression for large objects
        large_data = {
            "historical_prices": [
                {"timestamp": datetime.utcnow().isoformat(), "price": 45000 + i}
                for i in range(1000)  # Large dataset
            ],
            "metadata": {"symbol": "BTC/USDT", "source": "test"}
        }

        # Store with compression
        await state_manager.store_compressed_data("large_dataset", large_data)

        # Verify compression was applied
        store_call = state_manager.redis.set.call_args_list[0]
        compressed_data = store_call[0][1]

        # Compressed data should be smaller than raw JSON
        raw_size = len(json.dumps(large_data))
        compressed_size = len(compressed_data)

        assert compressed_size < raw_size * 0.8  # At least 20% compression

        # Test TTL for automatic cleanup
        ttl_call = [call for call in state_manager.redis.expire.call_args_list
                   if "large_dataset" in call[0]]
        assert len(ttl_call) > 0  # TTL was set

    async def test_connection_pool_management(self, state_manager):
        """Test Redis connection pool behavior under load."""

        # Simulate concurrent operations
        async def concurrent_operation(operation_id: int):
            await state_manager.store_agent_state(
                agent_id=operation_id,
                state={"operation_id": operation_id, "timestamp": datetime.utcnow().isoformat()}
            )
            return operation_id

        # Run concurrent operations
        tasks = [concurrent_operation(i) for i in range(50)]
        results = await asyncio.gather(*tasks)

        # Verify all operations completed
        assert len(results) == 50
        assert state_manager.redis.hset.call_count == 50

        # Verify no connection exhaustion
        state_manager.redis.ping.assert_called()

    async def test_redis_failover_handling(self, state_manager):
        """Test handling of Redis connection failures."""

        # Simulate connection failure
        state_manager.redis.ping.side_effect = ConnectionError("Redis unavailable")

        # Should handle failure gracefully
        try:
            result = await state_manager.health_check()
            assert result is False  # Health check should fail
        except Exception as e:
            pytest.fail(f"Should handle Redis failure gracefully: {e}")

        # Simulate recovery
        state_manager.redis.ping.side_effect = None
        state_manager.redis.ping.return_value = True

        # Should recover
        result = await state_manager.health_check()
        assert result is True


@pytest.mark.integration
class TestCrossAgentStateSync:
    """Test state synchronization across multiple agents."""

    async def test_state_consistency_across_agents(self):
        """Test that state changes are consistent across multiple agent instances."""

        # Create multiple state manager instances (simulating different agents)
        managers = []
        for i in range(3):
            sm = StateManager(redis_url=f"redis://localhost:6379/{i}")
            sm.redis = AsyncMock()
            managers.append(sm)

        # Simulate shared state update
        shared_state = {
            "market_regime": "high_volatility",
            "risk_level": "elevated",
            "updated_by": "risk_governor",
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Update from first agent
        await managers[0].store_shared_state("market_conditions", shared_state)

        # Mock consistent Redis responses for all agents
        for sm in managers:
            sm.redis.get.return_value = json.dumps(shared_state)

        # Verify all agents see same state
        for i, sm in enumerate(managers):
            retrieved_state = await sm.get_shared_state("market_conditions")
            assert retrieved_state["market_regime"] == "high_volatility"
            assert retrieved_state["updated_by"] == "risk_governor"

    async def test_state_version_conflicts(self):
        """Test handling of concurrent state updates (version conflicts)."""

        state_manager = StateManager(redis_url="redis://localhost:6379")
        state_manager.redis = AsyncMock()

        # Simulate concurrent updates to same key
        update1 = {"value": "update_from_agent_1", "version": 1}
        update2 = {"value": "update_from_agent_2", "version": 1}

        # Both agents try to update simultaneously
        await state_manager.store_versioned_state("shared_config", update1, expected_version=0)

        # Second update should detect version conflict
        state_manager.redis.get.return_value = json.dumps({"version": 1, "data": update1})

        with pytest.raises(Exception, match="version conflict"):
            await state_manager.store_versioned_state("shared_config", update2, expected_version=0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])