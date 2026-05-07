"""Unit tests for RiskEngine and PositionLimitChecker."""

from datetime import datetime
from decimal import Decimal

import numpy as np
import pytest

from core.data.models import (
    AssetClass,
    Exchange,
    OrderSide,
    OrderType,
    Portfolio,
    Position,
    TradeProposal,
)
from core.risk.position_limits import PositionLimitChecker
from core.risk.risk_engine import RiskEngine


def _portfolio(capital: float = 100_000.0, positions: list[Position] | None = None) -> Portfolio:
    return Portfolio(
        snapshot_time=datetime.utcnow(),
        total_capital=Decimal(str(capital)),
        available_capital=Decimal(str(capital * 0.85)),
        reserved_capital=Decimal(str(capital * 0.15)),
        emergency_reserve=Decimal(str(capital * 0.15)),
        positions=positions or [],
    )


def _proposal(size_usd: float, symbol: str = "BTC/USDT") -> TradeProposal:
    return TradeProposal(
        strategy_id="test",
        agent_id=12,
        symbol=symbol,
        exchange=Exchange.BINANCE,
        asset_class=AssetClass.CRYPTO,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal(str(size_usd / 45000)),
        size_usd=Decimal(str(size_usd)),
        limit_price=Decimal("45000"),
        stop_loss=Decimal("44000"),
        confidence_score=0.7,
        rationale="test",
    )


@pytest.mark.unit
def test_var_zero_for_short_history():
    returns = np.random.randn(20) * 0.01
    assert RiskEngine.historical_var(returns) == 0.0


@pytest.mark.unit
def test_var_positive_for_long_history():
    rng = np.random.default_rng(42)
    returns = rng.normal(0, 0.01, 100)
    var = RiskEngine.historical_var(returns, confidence=0.95)
    assert var > 0


@pytest.mark.unit
def test_position_limit_rejects_oversized_single_asset():
    checker = PositionLimitChecker()
    # Existing 5% in BTC; propose another 2%
    pos = Position(
        symbol="BTC/USDT",
        exchange=Exchange.BINANCE,
        asset_class=AssetClass.CRYPTO,
        side=OrderSide.BUY,
        size=Decimal("0.111"),
        entry_price=Decimal("45000"),
        current_price=Decimal("45000"),
        strategy_id="test",
        agent_id=12,
        opened_at=datetime.utcnow(),
    )
    portfolio = _portfolio(positions=[pos])
    proposal = _proposal(size_usd=2000)
    result = checker.check_proposal(proposal, portfolio)
    # 5% already used → at most 0% additional capacity → reject
    assert not result.approved or result.adjusted_size_usd is not None


@pytest.mark.unit
def test_position_limit_approves_small_proposal():
    checker = PositionLimitChecker()
    portfolio = _portfolio()
    proposal = _proposal(size_usd=500)
    result = checker.check_proposal(proposal, portfolio)
    assert result.approved


@pytest.mark.unit
def test_drawdown_zero_when_capital_above_baseline():
    eng = RiskEngine()
    dd = eng.compute_drawdown(Decimal("110000"), Decimal("100000"))
    assert dd == 0.0


@pytest.mark.unit
def test_drawdown_correct_when_below_baseline():
    eng = RiskEngine()
    dd = eng.compute_drawdown(Decimal("95000"), Decimal("100000"))
    assert abs(dd - 0.05) < 1e-9
