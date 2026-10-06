"""Small, valid domain fixtures shared by behavioral tests."""

from datetime import UTC, datetime
from decimal import Decimal

from core.data.models import (
    AgentHealth,
    AgentStatus,
    Exchange,
    OHLCVBar,
    Portfolio,
    Position,
    RiskMetrics,
    Timeframe,
    TradeProposal,
)


def portfolio(**changes):
    values = dict(
        snapshot_time=datetime.now(UTC),
        total_capital=Decimal("10000"),
        available_capital=Decimal("8000"),
        reserved_capital=Decimal("500"),
        emergency_reserve=Decimal("1500"),
        positions=[],
    )
    return Portfolio(**(values | changes))


def position(**changes):
    values = dict(
        symbol="BTC/USDT",
        exchange="binance",
        asset_class="CRYPTO",
        side="BUY",
        size="1",
        entry_price="100",
        current_price="105",
        strategy_id="test",
        agent_id=14,
        opened_at=datetime.now(UTC),
    )
    return Position(**(values | changes))


def proposal(**changes):
    values = dict(
        strategy_id="test",
        agent_id=14,
        symbol="BTC/USDT",
        exchange="binance",
        asset_class="CRYPTO",
        side="BUY",
        order_type="LIMIT",
        size="0.1",
        size_usd="10",
        limit_price="100",
        stop_loss="95",
        confidence_score=0.9,
    )
    return TradeProposal(**(values | changes))


def bar(**changes):
    values = dict(
        time=datetime.now(UTC),
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        timeframe=Timeframe.H1,
        open=100,
        high=110,
        low=90,
        close=105,
        volume=1000,
        is_closed=True,
    )
    return OHLCVBar(**(values | changes))


def health(**changes):
    values = dict(
        agent_id=14,
        agent_name="test",
        tier=4,
        status=AgentStatus.RUNNING,
        start_time=datetime.now(UTC),
        last_heartbeat=datetime.now(UTC),
        uptime_seconds=100,
        messages_processed=0,
        messages_failed=0,
    )
    return AgentHealth(**(values | changes))


def risk(**changes):
    values = dict(
        timestamp=datetime.now(UTC),
        total_capital=10000,
        available_capital=8000,
        daily_drawdown_pct=0,
        weekly_drawdown_pct=0,
        monthly_drawdown_pct=0,
        current_leverage=0,
        var_95_1d=0,
        var_99_1d=0,
        cvar_95_1d=0,
        portfolio_beta=1,
        sharpe_90d=None,
        sortino_90d=None,
        max_single_asset_exposure=0,
        max_sector_exposure=0,
        max_correlation=0,
    )
    return RiskMetrics(**(values | changes))


class FiniteConsumer:
    """Finite transport double: agent loops see real envelopes and terminate."""

    def __init__(self, messages=()):
        from unittest.mock import AsyncMock

        self.messages = list(messages)
        self.initialize = AsyncMock()
        self.shutdown = AsyncMock()

    async def stream(self):
        for message in self.messages:
            yield message


def with_performance(value):
    """Explicit synthetic, verified baseline for tests which require readiness."""
    from core.accounting.models import BookState
    from core.accounting.performance import observe

    value.accounting_book_id = value.accounting_book_id or "test"
    value.accounting_revision = value.accounting_revision or 0
    value.performance = observe(
        None,
        value.accounting_book_id,
        BookState(),
        value.total_capital + value.unrealized_pnl,
        value.snapshot_time,
    )
    value.performance.revision = value.accounting_revision
    return value


async def persist_snapshot(ledger, state):
    from core.accounting import performance
    from core.accounting.valuation import Valuation

    async with ledger.locked_state() as (conn, book, _opening):
        value = await Valuation(state, datetime.now(UTC), []).portfolio(ledger.book_id, book, [])
        value.performance = await performance.snapshot(conn, book, value)
    return value
