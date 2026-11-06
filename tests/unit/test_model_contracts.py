"""Contracts at the model/Redis/Kafka boundaries recovered from existing callers."""

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from core.data import models
from core.data.models import (
    RISK_LIMITS,
    AgentMessage,
    Exchange,
    KafkaTopic,
    OHLCVBar,
    Order,
    OrderBook,
    OrderSide,
    OrderStatus,
    Portfolio,
    Position,
    RiskLimits,
    TradeProposal,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def proposal_data():
    return {
        "strategy_id": "test",
        "agent_id": 12,
        "symbol": "BTC/USDT",
        "exchange": "binance",
        "asset_class": "CRYPTO",
        "side": "BUY",
        "order_type": "LIMIT",
        "size": "0.01234567890123456789",
        "size_usd": "555.55555055555555505",
        "limit_price": "45000",
        "stop_loss": "44000",
        "confidence_score": 0.8,
    }


def test_proposal_survives_envelope_json_round_trip(proposal_data):
    proposal = TradeProposal(**proposal_data)
    envelope = AgentMessage(
        source_agent_id=12,
        topic=KafkaTopic.PROPOSALS_BUS,
        message_type="TradeProposal",
        payload=proposal.model_dump(),  # ML publisher uses Python mode here.
    )
    wire = json.loads(envelope.model_dump_json())
    restored = TradeProposal.model_validate(wire["payload"])
    assert restored == proposal
    assert wire["payload"]["size"] == proposal_data["size"]
    assert wire["topic"] == "proposals.bus"
    assert isinstance(restored.proposal_id, UUID)
    assert restored.exchange is Exchange.BINANCE
    assert restored.side is OrderSide.BUY
    assert "confidence" not in wire["payload"]
    assert proposal.created_at.tzinfo is None  # OrderRouter's datetime subtraction.


@pytest.mark.parametrize("field", ["agent_id", "exchange", "size_usd", "confidence_score"])
def test_legacy_proposal_cannot_silently_supply_missing_contract(proposal_data, field):
    proposal_data.pop(field)
    proposal_data.update(confidence=0.8, direction="LONG", quantity="0.1")
    with pytest.raises(ValidationError):
        TradeProposal(**proposal_data)


@pytest.mark.parametrize("confidence", [-0.01, 1.01, float("nan"), float("inf")])
def test_confidence_must_be_a_probability(proposal_data, confidence):
    proposal_data["confidence_score"] = confidence
    with pytest.raises(ValidationError):
        TradeProposal(**proposal_data)


def test_per_message_ids_and_metadata_are_independent(proposal_data):
    first, second = TradeProposal(**proposal_data), TradeProposal(**proposal_data)
    first.metadata["source"] = "test"
    assert second.metadata == {}
    assert first.proposal_id != second.proposal_id
    orders = [
        Order(
            symbol="BTC/USDT",
            exchange="binance",
            side="BUY",
            order_type="LIMIT",
            size="0.1",
            strategy_id="test",
            agent_id=12,
        )
        for _ in range(2)
    ]
    assert len({o.order_id for o in orders} | {o.client_order_id for o in orders}) == 4
    assert orders[0].filled_size == Decimal("0")
    assert orders[0].status is OrderStatus.PENDING
    assert orders[0].price is None  # SlippageMinimizer creates unpriced children.
    orders[0].algo_params["is_maker"] = True
    assert orders[1].algo_params == {}
    assert Order.model_validate({**orders[0].model_dump(mode="json"), "_child": True})


def test_bar_requires_time_and_exchange():
    bar = dict(
        symbol="BTC/USDT",
        exchange="binance",
        timeframe="1h",
        open="100",
        high="110",
        low="90",
        close="105",
        volume="1",
        timestamp=datetime(2026, 9, 22),
    )
    with pytest.raises(ValidationError):
        OHLCVBar(**bar)
    bar["time"] = bar.pop("timestamp")
    assert OHLCVBar(**bar).is_closed
    bar.pop("exchange")
    with pytest.raises(ValidationError):
        OHLCVBar(**bar)


def test_position_and_portfolio_derived_values_recompute_after_redis_round_trip():
    common = dict(
        exchange="binance",
        asset_class="CRYPTO",
        strategy_id="test",
        agent_id=12,
        opened_at=datetime(2026, 9, 22),
    )
    long = Position(
        **common,
        symbol="BTC/USDT",
        side="BUY",
        size="2",
        entry_price="100",
        current_price="110",
    )
    short = Position(
        **common,
        symbol="ETH/USDT",
        side="SELL",
        size="3",
        entry_price="100",
        current_price="90",
    )
    portfolio = Portfolio(
        snapshot_time=datetime(2026, 9, 22),
        total_capital="1000",
        available_capital="500",
        reserved_capital="350",
        emergency_reserve="150",
        positions=[long, short],
    )
    assert long.unrealized_pnl == Decimal("20")
    assert short.unrealized_pnl == Decimal("30")
    assert long.unrealized_pnl_pct == short.unrealized_pnl_pct == 10.0
    assert portfolio.total_exposure_usd == Decimal("490")
    assert portfolio.leverage == 0.49
    assert portfolio.open_position_count == 2
    wire = portfolio.model_dump(mode="json")
    wire["positions"][0]["current_price"] = "120"
    # Serialized computed values must not override recalculated risk information.
    wire["unrealized_pnl"] = "999999"
    restored = Portfolio.model_validate(json.loads(json.dumps(wire)))
    assert restored.unrealized_pnl == Decimal("70")
    assert restored.total_exposure_usd == Decimal("510")
    restored.total_capital = Decimal("0")
    assert restored.leverage == 0.0


@pytest.mark.parametrize(
    "bids,asks,expected", [([], [], None), (["100"], [], None), (["100"], ["102"], Decimal("101"))]
)
def test_order_book_price_publisher_contract(bids, asks, expected):
    book = OrderBook(
        symbol="BTC/USDT",
        exchange="binance",
        timestamp=datetime(2026, 9, 22),
        bids=[{"price": p, "size": "1"} for p in bids],
        asks=[{"price": p, "size": "1"} for p in asks],
    )
    assert book.mid_price == expected
    assert OrderBook.model_validate_json(book.model_dump_json()).mid_price == expected


def test_risk_constants_match_existing_policy_and_cannot_be_loosened():
    assert RISK_LIMITS.max_risk_per_trade == 0.01
    assert RISK_LIMITS.max_single_asset == 0.05
    assert RISK_LIMITS.max_single_sector == 0.20
    assert RISK_LIMITS.max_leverage == 3.0
    assert RISK_LIMITS.emergency_reserve_pct == 0.15
    assert RISK_LIMITS.consecutive_loss_pause == 5
    assert (
        RISK_LIMITS.daily_drawdown_alert,
        RISK_LIMITS.daily_drawdown_pause,
        RISK_LIMITS.weekly_drawdown_halt,
        RISK_LIMITS.monthly_kill_switch,
    ) == (
        0.03,
        0.05,
        0.07,
        0.12,
    )
    with pytest.raises(ValidationError):
        RiskLimits(max_risk_per_trade=0.02)
    with pytest.raises(ValidationError):
        RISK_LIMITS.max_leverage = 10


def test_topics_match_provisioning_and_package_exports_are_defined():
    initializer = Path(__file__).parents[2] / "infra/init/kafka-init.sh"
    provisioned = set(re.findall(r'^create_topic "([^"]+)"', initializer.read_text(), re.M))
    assert {topic.value for topic in KafkaTopic} == provisioned
    assert all(hasattr(models, name) for name in models.__all__)


@pytest.mark.asyncio
async def test_approval_and_routing_preserve_contract(proposal_data, monkeypatch):
    from unittest.mock import AsyncMock

    from agents.tier1_executive.proposal_approver import ProposalApprover
    from agents.tier5_execution.order_router import OrderRouter
    from core.config import settings

    approver = ProposalApprover()
    approver.authorizations = AsyncMock()
    approver.authorizations.review.return_value = None
    approver.authorizations.decide.return_value = True
    approver.state = AsyncMock()
    approver.state.is_kill_switch_active.return_value = False
    approver.state.trading_ready.return_value = True
    approver.state.get_portfolio.return_value = Portfolio(
        snapshot_time=datetime(2026, 9, 22),
        total_capital="100000",
        available_capital="85000",
        reserved_capital="15000",
        emergency_reserve="15000",
        positions=[],
    )
    approver.publish = AsyncMock()
    proposal = TradeProposal(**proposal_data, accounting_book_id=settings.accounting_book_id)
    await approver._process(proposal.model_dump(mode="json"))
    assert approver.publish.call_args.args[0] == KafkaTopic.PROPOSALS_APPROVED
    router = OrderRouter()
    from core.execution.contracts import AccountScope

    monkeypatch.setattr(
        settings,
        "execution_accounts",
        [AccountScope(exchange=proposal.exchange, symbols=[proposal.symbol])],
    )
    router.publish = AsyncMock()
    router.authorizations = AsyncMock()
    await router._route(approver.publish.call_args.kwargs["payload"])
    order = router.authorizations.bind.await_args.args[1]
    router.publish.assert_not_awaited()  # The durable outbox delivers the bound order.
    assert order.proposal_id == proposal.proposal_id
    assert order.size == proposal.size
    assert order.price == proposal.limit_price
    assert order.stop_price == proposal.stop_loss


@pytest.mark.asyncio
async def test_ml_producer_emits_its_actual_confidence():
    from agents.tier4_strategies.ml_predictor import MLPredictorAgent

    agent = MLPredictorAgent()
    try:
        proposal = await agent._create_trade_proposal(
            "BTC/USDT",
            {"signal": "BULLISH", "confidence": 0.8, "recommended_risk_multiplier": 0.5},
        )
        assert proposal is not None
        assert proposal.confidence_score == 0.8
        assert proposal.size_usd == Decimal("7.5")
        assert TradeProposal.model_validate_json(proposal.model_dump_json()) == proposal
    finally:
        await agent.http_client.aclose()


def test_technical_producer_numeric_and_missing_thresholds():
    from agents.tier3_quant.technical_analyst import TechnicalAnalyst
    from core.data.models import SignalDirection, TechnicalSignal

    for threshold in (None, 30.0):
        signal = TechnicalAnalyst._make_signal(
            "BTC/USDT",
            "1h",
            "RSI",
            25.0,
            SignalDirection.BULLISH,
            0.7,
            threshold_breached=threshold,
        )
        restored = TechnicalSignal.model_validate_json(signal.model_dump_json())
        assert restored.threshold_breached == threshold
        assert restored.trend_strength is None


def test_seeded_runtime_payloads_parse_without_contacts():
    from unittest.mock import MagicMock

    from core.data.models import AgentHealth, RiskMetrics
    from scripts.seed_redis import seed

    redis = MagicMock()
    seed(redis)
    calls = redis.pipeline.return_value
    payloads = {call.args[0]: call.args[1] for call in calls.set.call_args_list}
    portfolio = Portfolio.model_validate_json(payloads["alghrest:portfolio:current"])
    risk = RiskMetrics.model_validate_json(payloads["alghrest:risk:current"])
    assert portfolio.open_position_count > 0
    assert risk.total_capital == portfolio.total_capital
    health_payloads = [
        call.args[2]
        for call in calls.setex.call_args_list
        if call.args[0].startswith("alghrest:agent:health:")
    ]
    assert health_payloads
    for payload in health_payloads:
        assert AgentHealth.model_validate_json(payload).agent_id > 0


def test_real_backtest_result_contracts_round_trip():
    import pandas as pd

    from backtesting.engine import BacktestEngine
    from core.data.models import (
        BacktestResult,
        MonteCarloResult,
        WalkForwardResult,
        WalkForwardWindow,
    )

    engine = BacktestEngine("test", "Test", "BTC/USDT")
    bars = pd.DataFrame(
        {"close": [100.0, 105.0, 110.0]}, index=pd.date_range("2020-01-01", periods=3)
    )
    signals = pd.Series([False, False, False], index=bars.index)
    result = engine._simple_backtest(bars, signals, signals)
    assert BacktestResult.model_validate_json(result.model_dump_json()) == result
    mc = engine.monte_carlo(result)
    assert not mc.passed_validation
    assert mc.failure_reasons
    assert MonteCarloResult.model_validate_json(mc.model_dump_json()) == mc
    dates = {
        name: datetime(2026, 9, 22)
        for name in (
            "train_start",
            "train_end",
            "test_start",
            "test_end",
        )
    }
    window = WalkForwardWindow(
        window_index=0,
        **dates,
        in_sample=result.model_copy(update={"total_return_pct": 20.0}),
        out_of_sample=result.model_copy(update={"total_return_pct": 12.0}),
    )
    assert window.wf_efficiency == 0.6
    window.in_sample.total_return_pct = 0
    assert window.wf_efficiency == 0
    passing = result.model_copy(update={"passed_validation": True, "failure_reasons": []})
    wf = WalkForwardResult(
        strategy_id="test",
        windows=[window],
        avg_oos_sharpe=1.0,
        avg_oos_return_pct=12.0,
        avg_wf_efficiency=0.6,
        passed_validation=True,
        failure_reasons=[],
    )
    assert not engine.validate_all(passing, wf, mc)[0]
    # A failed stage cannot become an approval just because its reasons were omitted.
    mc.failure_reasons = []
    assert not engine.validate_all(passing, wf, mc)[0]
