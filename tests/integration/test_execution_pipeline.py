"""Actual agent components with finite message streams and mocked external I/O.

These checks do not validate broker delivery or the concurrent Compose topology.
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from time import monotonic
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.tier1_executive.proposal_approver import ProposalApprover
from agents.tier5_execution.exchange_executor import ExchangeExecutor
from agents.tier5_execution.fee_optimizer import FeeOptimizer
from agents.tier5_execution.order_router import OrderRouter
from agents.tier5_execution.slippage_minimizer import SlippageMinimizer
from core.data.models import (
    AgentMessage,
    Fill,
    KafkaTopic,
    Order,
    OrderStatus,
    Portfolio,
    Position,
    TradeProposal,
    TradeProposalStatus,
)
from core.orchestrator.message_bus import AlghrestProducer
from core.orchestrator.state_manager import StateManager

pytestmark = pytest.mark.integration


@pytest.fixture
def mock_state_manager():
    state = AsyncMock(spec=StateManager)
    state.is_kill_switch_active.return_value = False
    state.get_portfolio.return_value = Portfolio(
        snapshot_time=datetime.utcnow(),
        total_capital="10000",
        available_capital="8500",
        reserved_capital="1500",
        emergency_reserve="1500",
        positions=[],
    )
    state.get_json.return_value = None
    state.is_already_processed.return_value = False
    state.lock = MagicMock(return_value=AsyncMock())  # async context manager, not coroutine
    return state


@pytest.fixture
def mock_producer():
    return AsyncMock(spec=AlghrestProducer)


@pytest.fixture
def sample_trade_proposal():
    return TradeProposal(
        strategy_id="test_trend_follower",
        agent_id=12,
        symbol="BTC/USDT",
        exchange="binance",
        asset_class="CRYPTO",
        side="BUY",
        order_type="LIMIT",
        size="0.01",
        size_usd="450",
        limit_price="45000",
        stop_loss="44000",
        confidence_score=0.8,
    )


class FiniteConsumer:
    def __init__(self, messages):
        self.messages = messages
        self.initialize = AsyncMock()

    async def stream(self):
        for message in self.messages:
            yield AgentMessage.model_validate_json(message.model_dump_json()).model_dump(
                mode="json"
            )


async def consume(agent, state, producer, messages):
    agent.state = state
    agent.producer = producer
    consumer = FiniteConsumer(messages)
    with patch.object(agent, "make_consumer", return_value=consumer):
        await asyncio.wait_for(agent.run(), timeout=1)
    consumer.initialize.assert_awaited()


def envelope(proposal):
    return AgentMessage(
        source_agent_id=proposal.agent_id,
        topic=KafkaTopic.PROPOSALS_BUS,
        message_type="TradeProposal",
        payload=proposal.model_dump(mode="json"),
    )


def sent(producer, topic):
    return [c.args[1] for c in producer.send.await_args_list if c.args[0] == topic]


class TestExecutionPipeline:
    async def test_happy_path_execution(
        self, mock_state_manager, mock_producer, sample_trade_proposal, monkeypatch
    ):
        await consume(
            ProposalApprover(), mock_state_manager, mock_producer, [envelope(sample_trade_proposal)]
        )
        approved = sent(mock_producer, KafkaTopic.PROPOSALS_APPROVED)
        assert len(approved) == 1
        assert (
            TradeProposal.model_validate(approved[0].payload).status == TradeProposalStatus.APPROVED
        )
        from core.config import settings
        from core.execution.contracts import AccountScope

        monkeypatch.setattr(
            settings,
            "execution_accounts",
            [
                AccountScope(
                    exchange=sample_trade_proposal.exchange, symbols=[sample_trade_proposal.symbol]
                )
            ],
        )
        router = OrderRouter()
        await consume(router, mock_state_manager, mock_producer, approved)
        pending = sent(mock_producer, KafkaTopic.ORDERS_PENDING)
        assert len(pending) == 1
        order = Order.model_validate(pending[0].payload)
        assert order.proposal_id == sample_trade_proposal.proposal_id
        assert order.size == sample_trade_proposal.size
        assert order.stop_price == sample_trade_proposal.stop_loss
        await consume(FeeOptimizer(), mock_state_manager, mock_producer, pending)
        slippage = SlippageMinimizer()
        await consume(slippage, mock_state_manager, mock_producer, pending)
        assert slippage._active_plans == {}
        assert len(sent(mock_producer, KafkaTopic.ORDERS_PENDING)) == 1

        executor = ExchangeExecutor()
        executor.state, executor.producer = mock_state_manager, mock_producer
        from core.accounting.models import key
        from core.execution.recovery import RecoveryCoordinator

        placed = order.model_copy(
            update={"exchange_order_id": "paper-1", "status": OrderStatus.OPEN}
        )
        venue = AsyncMock()
        venue.place.return_value = placed
        executor.venues = {key(order.exchange.value, order.account_id): venue}
        executor.store = AsyncMock()
        executor.store.book_id = "integration-test"
        executor.store.seen.return_value = False
        executor.store.prepare.return_value = True
        mock_state_manager.trading_ready.return_value = True
        assert await executor._place_order(order)
        venue.place.assert_awaited_once_with(order)
        executor.store.prepare.assert_awaited_once_with(order)
        executor.store.observe.assert_awaited_once_with(order, placed)
        # Confirmed observations are dispatched from the durable outbox.
        fill = Fill(
            order_id=order.order_id,
            exchange_order_id="paper-1",
            exchange_trade_id="trade-1",
            symbol=order.symbol,
            exchange=order.exchange,
            side=order.side,
            fill_size=order.size,
            fill_price=order.price,
            timestamp=datetime.utcnow(),
            strategy_id=order.strategy_id,
        )
        executor.store.outbox.return_value = [
            {
                "id": 1,
                "topic": KafkaTopic.FILLS_CONFIRMED.value,
                "payload": fill.model_dump_json(),
                "message_type": "Fill",
            }
        ]
        recovery = RecoveryCoordinator(
            executor.store, [], executor.venues, executor.state, executor.publish
        )
        await recovery.flush()
        fills = sent(mock_producer, KafkaTopic.FILLS_CONFIRMED)
        assert len(fills) == 1
        assert Fill.model_validate(fills[0].payload) == fill
        executor.store.delivered.assert_awaited_once_with(1)

    async def test_position_limit_rejection(
        self, mock_state_manager, mock_producer, sample_trade_proposal, monkeypatch
    ):
        mock_state_manager.get_portfolio.return_value.positions = [
            Position(
                symbol="BTC/USDT",
                exchange="binance",
                asset_class="CRYPTO",
                side="BUY",
                size="0.5",
                entry_price="50000",
                current_price="50000",
                strategy_id="existing",
                agent_id=12,
                opened_at=datetime.utcnow(),
            )
        ]
        large = sample_trade_proposal.model_copy(
            update={"size": Decimal("1"), "size_usd": Decimal("45000")}
        )
        approver = ProposalApprover()
        await consume(approver, mock_state_manager, mock_producer, [envelope(large)])
        assert sent(mock_producer, KafkaTopic.PROPOSALS_APPROVED) == []
        rejected = sent(mock_producer, KafkaTopic.RISK_ALERTS)
        assert len(rejected) == 1
        assert rejected[0].message_type == "ProposalRejected"
        assert "Single-asset limit" in rejected[0].payload["message"]
        assert approver._rejected_count == 1

    async def test_kill_switch_halts_pipeline(
        self, mock_state_manager, mock_producer, sample_trade_proposal, monkeypatch
    ):
        mock_state_manager.is_kill_switch_active.return_value = True
        await consume(
            ProposalApprover(), mock_state_manager, mock_producer, [envelope(sample_trade_proposal)]
        )
        assert sent(mock_producer, KafkaTopic.PROPOSALS_APPROVED) == []
        rejected = sent(mock_producer, KafkaTopic.RISK_ALERTS)
        assert len(rejected) == 1
        assert "kill switch active" in rejected[0].payload["message"]
        mock_state_manager.get_portfolio.assert_not_awaited()

    async def test_optimization_flags_prevent_reentry(self, mock_state_manager, mock_producer):
        order = Order(
            symbol="BTC/USDT",
            exchange="binance",
            side="BUY",
            order_type="MARKET",
            size="0.01",
            price="45000",
            strategy_id="test",
            agent_id=12,
        )
        message = AgentMessage(
            source_agent_id=20,
            topic=KafkaTopic.ORDERS_PENDING,
            message_type="Order",
            payload=order.model_dump(mode="json"),
        )
        optimizer = FeeOptimizer()
        await consume(optimizer, mock_state_manager, mock_producer, [message])
        optimized = sent(mock_producer, KafkaTopic.ORDERS_PENDING)
        assert len(optimized) == 1
        assert optimized[0].payload["_optimised"] is True
        assert Order.model_validate(optimized[0].payload).time_in_force == "GTX"
        await consume(optimizer, mock_state_manager, mock_producer, optimized)
        assert len(sent(mock_producer, KafkaTopic.ORDERS_PENDING)) == 1
        child = message.model_copy(deep=True)
        child.payload.update(order_type="TWAP", _child=True)
        slippage = SlippageMinimizer()
        with patch.object(slippage, "_start_plan", new_callable=AsyncMock) as start:
            await consume(slippage, mock_state_manager, mock_producer, [child])
            start.assert_not_awaited()

    async def test_pipeline_with_ml_predictor_fallback(
        self, mock_state_manager, mock_producer, sample_trade_proposal, monkeypatch
    ):
        proposal = sample_trade_proposal.model_copy(
            update={
                "strategy_id": "ml_predictor_cnn",
                "agent_id": 16,
                "confidence_score": 0.65,
                "metadata": {"source": "fallback_technical"},
            }
        )
        await consume(ProposalApprover(), mock_state_manager, mock_producer, [envelope(proposal)])
        approved = sent(mock_producer, KafkaTopic.PROPOSALS_APPROVED)
        assert len(approved) == 1
        restored = TradeProposal.model_validate(approved[0].payload)
        assert restored.confidence_score == 0.65
        assert restored.metadata == proposal.metadata

    async def test_execution_pipeline_performance(
        self, mock_state_manager, mock_producer, sample_trade_proposal, monkeypatch
    ):
        proposals = [
            TradeProposal(
                **{
                    **sample_trade_proposal.model_dump(exclude={"proposal_id"}),
                    "strategy_id": f"test_{i}",
                    "size": "0.001",
                    "size_usd": "45",
                }
            )
            for i in range(10)
        ]
        start = monotonic()
        await consume(
            ProposalApprover(), mock_state_manager, mock_producer, [envelope(p) for p in proposals]
        )
        assert monotonic() - start < 1.0
        approved = sent(mock_producer, KafkaTopic.PROPOSALS_APPROVED)
        assert len(approved) == 10
        assert {m.payload["proposal_id"] for m in approved} == {
            str(p.proposal_id) for p in proposals
        }


async def test_agent_startup_sequence():
    for cls in (ProposalApprover, OrderRouter, FeeOptimizer):
        agent = cls()
        agent.state, agent.producer = AsyncMock(spec=StateManager), AsyncMock(spec=AlghrestProducer)
        await agent.initialize()
        assert agent.AGENT_ID > 0
        assert agent.name
