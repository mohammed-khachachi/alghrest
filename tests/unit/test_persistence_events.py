"""Unit tests for Kafka event to TimescaleDB mapping."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from core.data.models import (
    AssetClass,
    Exchange,
    Fill,
    KafkaTopic,
    OrderBook,
    OrderBookLevel,
    OrderSide,
    OrderType,
    TradeProposal,
    TradeProposalStatus,
)
from core.persistence.events import PERSISTED_TOPICS, build_persistence_statements


def _envelope(
    topic: KafkaTopic,
    payload: dict,
    message_type: str,
    source_agent_id: int = 12,
) -> dict:
    return {
        "message_id": str(uuid4()),
        "source_agent_id": source_agent_id,
        "topic": topic.value,
        "message_type": message_type,
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }


@pytest.mark.unit
def test_persisted_topics_include_phase_one_pipeline_topics():
    assert KafkaTopic.PRICES_REALTIME in PERSISTED_TOPICS
    assert KafkaTopic.PROPOSALS_BUS in PERSISTED_TOPICS
    assert KafkaTopic.PROPOSALS_APPROVED in PERSISTED_TOPICS
    assert KafkaTopic.ORDERS_PENDING in PERSISTED_TOPICS
    assert KafkaTopic.ORDERS_EXECUTED in PERSISTED_TOPICS
    assert KafkaTopic.FILLS_CONFIRMED in PERSISTED_TOPICS
    assert KafkaTopic.RISK_ALERTS in PERSISTED_TOPICS


@pytest.mark.unit
def test_approved_proposal_maps_to_trade_proposals_and_forces_status():
    proposal = TradeProposal(
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
        rationale="unit test",
    )

    statements = build_persistence_statements(
        _envelope(
            KafkaTopic.PROPOSALS_APPROVED,
            proposal.model_dump(mode="json"),
            "TradeProposalApproved",
        )
    )

    assert len(statements) == 1
    stmt = statements[0]
    assert stmt.table == "trading.trade_proposals"
    assert stmt.params["proposal_id"] == str(proposal.proposal_id)
    assert stmt.params["status"] == TradeProposalStatus.APPROVED.value
    assert stmt.params["strategy_id"] == "trend_follower"
    assert stmt.params["size_usd"] == Decimal("4500")


@pytest.mark.unit
def test_order_book_snapshot_derives_depth_spread_and_imbalance():
    book = OrderBook(
        symbol="ETH/USDT",
        exchange=Exchange.BINANCE,
        timestamp=datetime.utcnow(),
        bids=[
            OrderBookLevel(price=Decimal("100"), size=Decimal("2")),
            OrderBookLevel(price=Decimal("99"), size=Decimal("1")),
        ],
        asks=[OrderBookLevel(price=Decimal("101"), size=Decimal("3"))],
    )

    statements = build_persistence_statements(
        _envelope(
            KafkaTopic.PRICES_REALTIME,
            book.model_dump(mode="json"),
            "order_book",
        )
    )

    stmt = statements[0]
    assert stmt.table == "market_data.order_book_snapshots"
    assert stmt.params["mid_price"] == Decimal("100.5")
    assert stmt.params["bid_depth"] == Decimal("3")
    assert stmt.params["ask_depth"] == Decimal("3")
    assert stmt.params["imbalance"] == Decimal("0")
    assert json.loads(stmt.params["bids"])[0]["price"] == "100"


@pytest.mark.unit
def test_fill_with_exchange_native_id_is_stable_uuid_for_existing_schema():
    order_id = uuid4()
    fill = Fill(
        fill_id="binance-trade-abc",
        order_id=order_id,
        exchange_order_id="EX-1",
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        fill_size=Decimal("0.01"),
        fill_price=Decimal("45100"),
        fee=Decimal("0.5"),
    )
    message = _envelope(KafkaTopic.FILLS_CONFIRMED, fill.model_dump(mode="json"), "Fill")

    first = build_persistence_statements(message)[0]
    second = build_persistence_statements(message)[0]

    assert first.table == "trading.fills"
    assert UUID(first.params["fill_id"])
    assert first.params["fill_id"] == second.params["fill_id"]
    assert first.params["order_id"] == str(order_id)


@pytest.mark.unit
def test_portfolio_tracker_metrics_map_to_portfolio_snapshot():
    payload = {
        "nav": 100_500.25,
        "available_capital": 80_000,
        "unrealized_pnl": 500.25,
        "daily_pnl": 125.5,
        "open_positions": 3,
        "leverage": 1.25,
        "timestamp": "2026-05-31T12:00:00",
    }

    stmt = build_persistence_statements(
        _envelope(KafkaTopic.PORTFOLIO_STATE, payload, "PortfolioSnapshot")
    )[0]

    assert stmt.table == "performance.portfolio_snapshots"
    assert stmt.params["total_capital"] == Decimal("100500.25")
    assert stmt.params["available_capital"] == Decimal("80000")
    assert stmt.params["realized_pnl_day"] == Decimal("125.5")
    assert stmt.params["open_positions"] == 3


@pytest.mark.unit
def test_kill_switch_event_routes_to_kill_switch_table():
    payload = {
        "event_id": str(uuid4()),
        "reason": "drawdown halt",
        "source_agent_id": 2,
        "drawdown_pct": "0.27",
        "scope": "system",
    }

    stmt = build_persistence_statements(
        _envelope(KafkaTopic.RISK_ALERTS, payload, "KillSwitchEvent", source_agent_id=2)
    )[0]

    assert stmt.table == "risk.kill_switch_events"
    assert stmt.params["trigger_reason"] == "drawdown halt"
    assert stmt.params["triggered_by_agent"] == 2
    assert stmt.params["drawdown_pct"] == Decimal("0.27")
