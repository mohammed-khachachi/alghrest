"""Sourced paper FX and venue/account-specific exits."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from agents.tier2_intelligence.paper_market_feed import PaperMarketFeed
from agents.tier5_execution.order_router import OrderRouter
from core.advisory.models import PriceObservation
from core.config import settings
from core.data.models import Exchange, TradeProposalStatus
from core.execution.contracts import AccountScope
from core.risk.position_limits import PositionLimitChecker
from tests.factories import portfolio, position, proposal

pytestmark = pytest.mark.unit


def test_five_dollar_exit_on_150_book_does_not_add_five_dollars_of_risk():
    book = portfolio(
        total_capital=150,
        available_capital=0,
        emergency_reserve=30,
        positions=[position(symbol="SOL/USDT", size="0.05", current_price=100)],
    )
    sell = proposal(symbol="SOL/USDT", side="SELL", size="0.05", size_usd=5)
    assert PositionLimitChecker().check_proposal(sell, book).approved
    for changes in (
        {"exchange": Exchange.KRAKEN},
        {"account_id": "other"},
        {"size": Decimal("0.051")},
        {"size": Decimal(0)},
        {"size": Decimal("NaN")},
    ):
        assert (
            not PositionLimitChecker()
            .check_proposal(sell.model_copy(update=changes), book)
            .approved
        )
    assert (
        PositionLimitChecker()
        .check_proposal(sell.model_copy(update={"size": Decimal("0.01")}), book)
        .approved
    )


async def test_router_preserves_approved_venue_account_and_rejects_out_of_scope(monkeypatch):
    monkeypatch.setattr(
        settings,
        "execution_accounts",
        [AccountScope(exchange="binance", account_id="holding", symbols=["SOL/USDT"])],
    )
    agent = OrderRouter()
    agent.publish = AsyncMock()
    approved = proposal(
        symbol="SOL/USDT", side="SELL", account_id="holding", status=TradeProposalStatus.APPROVED
    )
    await agent._route(approved.model_dump(mode="json"))
    order = agent.publish.await_args.args[1]
    assert order["exchange"] == "binance" and order["account_id"] == "holding"
    await agent._route(approved.model_copy(update={"account_id": "other"}).model_dump(mode="json"))
    assert agent.publish.await_count == 1


async def test_paper_feed_uses_unpegged_fx_and_rejects_stale_source(monkeypatch):
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(
        settings, "execution_accounts", [AccountScope(exchange="binance", symbols=["SOL/USDT"])]
    )
    agent = PaperMarketFeed()
    agent.state = AsyncMock()
    await agent.initialize()
    now = datetime.now(UTC)
    spot = PriceObservation(
        symbol="SOL/USDT",
        price=Decimal(100),
        timestamp=now,
        source="https://data-api.binance.vision",
    )
    fx = PriceObservation(
        symbol="USDT/USD",
        price=Decimal("0.998"),
        timestamp=now,
        source="https://api.exchange.coinbase.com",
    )
    monkeypatch.setattr(
        "connectors.advisory.market.PublicMarkets.spot", AsyncMock(return_value=spot)
    )
    monkeypatch.setattr(
        "connectors.advisory.market.PublicMarkets.tether_usd", AsyncMock(return_value=fx)
    )
    try:
        await agent.refresh()
        assert agent.state.set_accounting_mark.await_count == 2
        assert agent.state.set_accounting_mark.await_args.args[2] == "0.998"
        spot.timestamp = now - timedelta(minutes=10)
        fx.timestamp = now + timedelta(minutes=1)
        await agent.refresh()
        assert agent.state.set_accounting_mark.await_count == 2
    finally:
        await agent.shutdown()
    monkeypatch.setattr(settings, "environment", "live")
    with pytest.raises(ValueError, match="paper"):
        await agent.initialize()
