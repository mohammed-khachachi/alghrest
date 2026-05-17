"""
ALGHREST — Market Crash Kill Switch Integration Test
====================================================

This test simulates a rapid market crash scenario to validate:
1. Kill switch activation speed under extreme drawdown
2. Order cancellation effectiveness across all exchanges
3. System-wide halt compliance
4. Risk threshold escalation timing
5. Recovery procedures

Test Scenarios:
- Flash crash: 15% drop in 5 minutes
- Black swan: 25% drop in 30 minutes
- Systematic failure: Multiple asset correlation breakdown
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
import structlog

from agents.tier1_executive.risk_governor import RiskGovernor
from agents.tier5_execution.exchange_executor import ExchangeExecutor
from core.data.models import (
    AlertType,
    Exchange,
    KafkaTopic,
    KillSwitchEvent,
    OHLCVBar,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    RiskMetrics,
    Timeframe,
    TradeProposal,
)
from core.orchestrator.state_manager import StateManager
from core.risk.kill_switch import KillSwitch
from core.risk.risk_engine import RiskEngine

logger = structlog.get_logger(__name__)


class MarketCrashSimulator:
    """Simulates extreme market conditions for kill switch testing."""

    def __init__(self):
        self.initial_portfolio_value = Decimal("1000000")  # $1M portfolio
        self.crash_scenarios = {
            "flash_crash": {"drop_pct": 0.15, "duration_minutes": 5},
            "black_swan": {"drop_pct": 0.25, "duration_minutes": 30},
            "systematic_failure": {"drop_pct": 0.35, "duration_minutes": 60},
        }

    def generate_crash_prices(
        self,
        scenario: str,
        symbols: List[str] = None
    ) -> List[OHLCVBar]:
        """Generate price bars simulating market crash."""
        if symbols is None:
            symbols = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT"]

        config = self.crash_scenarios[scenario]
        drop_pct = config["drop_pct"]
        duration = config["duration_minutes"]

        # Generate minute-by-minute price drops
        bars = []
        base_prices = {"BTC/USDT": 45000, "ETH/USDT": 3000, "BNB/USDT": 300, "SOL/USDT": 100}

        for minute in range(duration):
            # Exponential decay for realistic crash pattern
            progress = minute / duration
            current_drop = drop_pct * (1 - (1 - progress) ** 2)

            for symbol in symbols:
                base_price = base_prices.get(symbol, 1000)
                crashed_price = base_price * (1 - current_drop)

                # Add volatility spikes
                volatility = 0.02 * (1 + progress * 3)  # Increasing volatility
                low = crashed_price * (1 - volatility)
                high = crashed_price * (1 + volatility)

                bar = OHLCVBar(
                    symbol=symbol,
                    timeframe=Timeframe.M1,
                    timestamp=datetime.utcnow() + timedelta(minutes=minute),
                    open=Decimal(str(crashed_price * 1.01)),
                    high=Decimal(str(high)),
                    low=Decimal(str(low)),
                    close=Decimal(str(crashed_price)),
                    volume=Decimal("1000000"),  # High volume during crash
                    is_closed=True,
                )
                bars.append(bar)

        return bars

    def calculate_portfolio_impact(
        self,
        initial_positions: List[Position],
        price_bars: List[OHLCVBar]
    ) -> Dict[str, Decimal]:
        """Calculate portfolio value impact from crash prices."""
        impacts = {}

        # Group bars by symbol for latest prices
        latest_prices = {}
        for bar in price_bars:
            latest_prices[bar.symbol] = bar.close

        for position in initial_positions:
            if position.symbol in latest_prices:
                new_price = latest_prices[position.symbol]
                old_value = position.size * position.current_price
                new_value = position.size * new_price
                impacts[position.symbol] = new_value - old_value

        return impacts


@pytest.fixture
def crash_simulator():
    return MarketCrashSimulator()


@pytest.fixture
def mock_portfolio_with_positions():
    """Portfolio with significant positions across multiple assets."""
    positions = [
        Position(
            symbol="BTC/USDT",
            size=Decimal("10"),  # 10 BTC @ $45k = $450k
            current_price=Decimal("45000"),
            unrealized_pnl=Decimal("0"),
            entry_price=Decimal("45000"),
            side=OrderSide.BUY,
        ),
        Position(
            symbol="ETH/USDT",
            size=Decimal("100"),  # 100 ETH @ $3k = $300k
            current_price=Decimal("3000"),
            unrealized_pnl=Decimal("0"),
            entry_price=Decimal("3000"),
            side=OrderSide.BUY,
        ),
        Position(
            symbol="SOL/USDT",
            size=Decimal("1000"),  # 1000 SOL @ $100 = $100k
            current_price=Decimal("100"),
            unrealized_pnl=Decimal("0"),
            entry_price=Decimal("100"),
            side=OrderSide.BUY,
        ),
    ]

    return Portfolio(
        snapshot_time=datetime.utcnow(),
        total_capital=Decimal("1000000"),  # $1M total
        available_capital=Decimal("150000"),  # $150k cash
        reserved_capital=Decimal("150000"),
        emergency_reserve=Decimal("150000"),
        positions=positions,
    )


@pytest.fixture
def mock_open_orders():
    """Multiple open orders across exchanges to test cancellation."""
    orders = []
    exchanges = [Exchange.BINANCE, Exchange.COINBASE, Exchange.KRAKEN]

    for i, exchange in enumerate(exchanges):
        for j in range(5):  # 5 orders per exchange
            order = Order(
                order_id=uuid4(),
                client_order_id=uuid4(),
                exchange_order_id=f"EX-{exchange.value}-{i}-{j}",
                symbol="BTC/USDT",
                exchange=exchange,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=Decimal("0.1"),
                price=Decimal("45000"),
                status=OrderStatus.OPEN,
                strategy_id="momentum",
                agent_id=12,
            )
            orders.append(order)

    return orders


class TestMarketCrashKillSwitch:
    """Integration tests for kill switch under extreme market conditions."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_flash_crash_kill_switch_activation(
        self,
        crash_simulator: MarketCrashSimulator,
        mock_portfolio_with_positions: Portfolio
    ):
        """Test kill switch activation during 15% flash crash in 5 minutes."""

        # Setup
        kill_switch = KillSwitch()
        risk_engine = RiskEngine()

        # Generate flash crash scenario
        crash_bars = crash_simulator.generate_crash_prices("flash_crash")

        # Track kill switch activations
        activation_events = []

        async def mock_close_positions(reason: str) -> int:
            activation_events.append({
                "timestamp": datetime.utcnow(),
                "reason": reason,
                "portfolio_value": mock_portfolio_with_positions.total_capital
            })
            return len(mock_portfolio_with_positions.positions)

        # Simulate price updates and measure response time
        start_time = datetime.utcnow()

        for i, bar in enumerate(crash_bars):
            # Update portfolio with crashed prices
            for position in mock_portfolio_with_positions.positions:
                if position.symbol == bar.symbol:
                    position.current_price = bar.close

            # Recalculate portfolio value
            new_total = sum(
                pos.size * pos.current_price
                for pos in mock_portfolio_with_positions.positions
            ) + mock_portfolio_with_positions.available_capital

            old_total = mock_portfolio_with_positions.total_capital
            mock_portfolio_with_positions.total_capital = new_total

            # Calculate drawdown
            drawdown_pct = float((old_total - new_total) / old_total)

            # Create risk metrics
            risk_metrics = RiskMetrics(
                timestamp=datetime.utcnow(),
                total_capital=new_total,
                available_capital=mock_portfolio_with_positions.available_capital,
                daily_drawdown_pct=drawdown_pct,
                weekly_drawdown_pct=drawdown_pct,
                monthly_drawdown_pct=drawdown_pct,
            )

            # Check kill switch
            event = await kill_switch.check(
                metrics=risk_metrics,
                on_close_all_positions=mock_close_positions
            )

            if event:
                response_time = (datetime.utcnow() - start_time).total_seconds()
                logger.info(
                    "kill_switch_activated",
                    scenario="flash_crash",
                    response_time_seconds=response_time,
                    drawdown=drawdown_pct,
                    trigger_reason=event.trigger_reason
                )
                break

        # Assertions
        assert len(activation_events) > 0, "Kill switch should have activated during flash crash"
        assert activation_events[0]["reason"].startswith("Daily drawdown")

        # Response time should be under 30 seconds for flash crash
        response_time = (datetime.utcnow() - start_time).total_seconds()
        assert response_time < 30, f"Kill switch response too slow: {response_time}s"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_order_cancellation_speed(
        self,
        mock_open_orders: List[Order]
    ):
        """Test order cancellation speed across multiple exchanges."""

        # Setup exchange executor with mock connectors
        executor = ExchangeExecutor()

        # Mock connectors for different exchanges
        mock_connectors = {}
        for exchange in [Exchange.BINANCE, Exchange.COINBASE, Exchange.KRAKEN]:
            connector = MagicMock()
            connector.cancel_order = AsyncMock(return_value=True)
            mock_connectors[exchange] = connector

        executor._connector = MagicMock()
        executor._connector.get = lambda ex: mock_connectors[ex]
        executor.publish = AsyncMock()

        # Track open orders
        executor._tracked_orders = {
            order.exchange_order_id: (order, datetime.utcnow())
            for order in mock_open_orders
        }

        # Measure cancellation speed
        start_time = datetime.utcnow()
        await executor._cancel_all_tracked_orders("market_crash_test")
        cancellation_time = (datetime.utcnow() - start_time).total_seconds()

        # Assertions
        assert executor._cancelled_by_kill_switch == len(mock_open_orders)
        assert len(executor._tracked_orders) == 0  # All orders cancelled
        assert cancellation_time < 5.0, f"Order cancellation too slow: {cancellation_time}s"

        # Verify all exchanges were called
        for connector in mock_connectors.values():
            assert connector.cancel_order.await_count >= 5  # 5 orders per exchange

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_kill_switch_escalation_levels(
        self,
        crash_simulator: MarketCrashSimulator,
        mock_portfolio_with_positions: Portfolio
    ):
        """Test all 4 escalation levels during systematic market failure."""

        kill_switch = KillSwitch()
        escalation_events = []

        # Mock alert functions to track escalations
        async def mock_telegram_alert(msg: str):
            escalation_events.append({"level": "alert", "message": msg})

        async def mock_pause_strategy(reason: str):
            escalation_events.append({"level": "pause", "reason": reason})

        async def mock_close_positions(reason: str) -> int:
            escalation_events.append({"level": "kill_switch", "reason": reason})
            return 5

        # Patch alert functions
        with patch("core.utils.alerts.send_telegram_alert", mock_telegram_alert):

            # Simulate escalating drawdown
            drawdown_levels = [0.02, 0.04, 0.08, 0.15]  # 2%, 4%, 8%, 15%

            for drawdown in drawdown_levels:
                risk_metrics = RiskMetrics(
                    timestamp=datetime.utcnow(),
                    total_capital=mock_portfolio_with_positions.total_capital,
                    available_capital=mock_portfolio_with_positions.available_capital,
                    daily_drawdown_pct=drawdown,
                    weekly_drawdown_pct=drawdown,
                    monthly_drawdown_pct=drawdown,
                )

                await kill_switch.check(
                    metrics=risk_metrics,
                    on_pause_strategy=mock_pause_strategy,
                    on_close_all_positions=mock_close_positions
                )

        # Verify escalation progression
        event_types = [event["level"] for event in escalation_events]

        # Should have alerts at 3%, pause at 5%, kill switch at 12%+
        assert "alert" in event_types, "Should trigger alert level"
        assert "pause" in event_types, "Should trigger strategy pause"
        assert "kill_switch" in event_types, "Should trigger full kill switch"

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_system_wide_halt_compliance(self):
        """Test that all agents respect kill switch state."""

        # Mock state manager with active kill switch
        state_manager = MagicMock()
        state_manager.is_kill_switch_active = AsyncMock(return_value=True)

        # Test various agent types
        from agents.base_agent import BaseAgent

        class TestAgent(BaseAgent):
            def __init__(self):
                super().__init__(agent_id=999, name="test", tier=1)
                self.state = state_manager

            async def initialize(self): pass
            async def run(self): pass
            async def shutdown(self): pass

        agent = TestAgent()

        # Verify halt detection
        is_halted = await agent.is_halted()
        assert is_halted == True, "Agent should detect active kill switch"

        # Verify state manager was called
        state_manager.is_kill_switch_active.assert_awaited_once()

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_kill_switch_recovery_procedures(self):
        """Test system recovery after kill switch reset."""

        kill_switch = KillSwitch()

        # Activate kill switch
        await kill_switch._trigger(
            reason="test_recovery",
            drawdown_pct=0.15,
            scope="system",
            cro_agent_id=2
        )

        assert kill_switch.is_active == True
        assert "test_recovery" in kill_switch.active_reason

        # Reset kill switch
        await kill_switch.reset(authorized_by="integration_test")

        assert kill_switch.is_active == False
        assert kill_switch.active_reason is None


# =============================================================================
# PERFORMANCE BENCHMARKS
# =============================================================================

class TestKillSwitchPerformance:
    """Performance benchmarks for kill switch response times."""

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_kill_switch_latency_benchmark(self):
        """Benchmark kill switch decision latency under load."""

        kill_switch = KillSwitch()

        # Create high-volume risk metrics
        risk_metrics = RiskMetrics(
            timestamp=datetime.utcnow(),
            total_capital=Decimal("10000000"),  # $10M portfolio
            available_capital=Decimal("1000000"),
            daily_drawdown_pct=0.15,  # Trigger kill switch
            weekly_drawdown_pct=0.15,
            monthly_drawdown_pct=0.15,
        )

        async def mock_close_positions(reason: str) -> int:
            # Simulate closing 1000 positions
            await asyncio.sleep(0.01)  # 10ms per batch
            return 1000

        # Measure response time
        start_time = datetime.utcnow()

        event = await kill_switch.check(
            metrics=risk_metrics,
            on_close_all_positions=mock_close_positions
        )

        response_time = (datetime.utcnow() - start_time).total_seconds()

        assert event is not None, "Kill switch should trigger"
        assert response_time < 1.0, f"Kill switch too slow: {response_time}s"
        assert event.positions_closed == 1000

    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_concurrent_order_cancellation(self):
        """Test order cancellation performance under high load."""

        executor = ExchangeExecutor()

        # Create 1000 mock orders across exchanges
        large_order_set = []
        for i in range(1000):
            exchange = [Exchange.BINANCE, Exchange.COINBASE, Exchange.KRAKEN][i % 3]
            order = Order(
                order_id=uuid4(),
                client_order_id=uuid4(),
                exchange_order_id=f"LOAD-{i}",
                symbol="BTC/USDT",
                exchange=exchange,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=Decimal("0.01"),
                price=Decimal("45000"),
                status=OrderStatus.OPEN,
                strategy_id="load_test",
                agent_id=12,
            )
            large_order_set.append(order)

        # Mock fast connectors
        mock_connector = MagicMock()
        mock_connector.cancel_order = AsyncMock(return_value=True)

        executor._connector = MagicMock()
        executor._connector.get = MagicMock(return_value=mock_connector)
        executor.publish = AsyncMock()

        executor._tracked_orders = {
            order.exchange_order_id: (order, datetime.utcnow())
            for order in large_order_set
        }

        # Measure cancellation performance
        start_time = datetime.utcnow()
        await executor._cancel_all_tracked_orders("performance_test")
        cancellation_time = (datetime.utcnow() - start_time).total_seconds()

        # Performance assertions
        orders_per_second = len(large_order_set) / cancellation_time
        assert orders_per_second > 100, f"Cancellation rate too slow: {orders_per_second}/sec"
        assert executor._cancelled_by_kill_switch == 1000