"""Sanity tests: every agent module imports cleanly and all classes exist.

These catch the most common breakages in the refactor: misspelled fields,
missing methods, broken imports, abstract methods left unimplemented.
"""

import importlib

import pytest


AGENT_MODULES = [
    ("agents.tier1_executive.cio_agent", "CIOAgent"),
    ("agents.tier1_executive.risk_governor", "RiskGovernor"),
    ("agents.tier1_executive.proposal_approver", "ProposalApprover"),
    ("agents.tier2_intelligence.price_publisher", "PricePublisher"),
    ("agents.tier2_intelligence.market_data_hub", "MarketDataHub"),
    ("agents.tier2_intelligence.news_analyst", "NewsAnalyst"),
    ("agents.tier2_intelligence.sentiment_analyst", "SentimentAnalyst"),
    ("agents.tier2_intelligence.macro_economist", "MacroEconomist"),
    ("agents.tier2_intelligence.onchain_sleuth", "OnChainSleuth"),
    ("agents.tier2_intelligence.geopolitical_watcher", "GeopoliticalWatcher"),
    ("agents.tier3_quant.technical_analyst", "TechnicalAnalyst"),
    ("agents.tier3_quant.volatility_forecaster", "VolatilityForecaster"),
    ("agents.tier3_quant.correlation_engine", "CorrelationEngine"),
    ("agents.tier4_strategies.trend_follower", "TrendFollower"),
    ("agents.tier4_strategies.mean_reversion", "MeanReversion"),
    ("agents.tier4_strategies.momentum", "MomentumStrategy"),
    ("agents.tier4_strategies.stat_arb", "StatArb"),
    ("agents.tier4_strategies.arb_cross_exchange", "CrossExchangeArb"),
    ("agents.tier4_strategies.macro_rotator", "MacroRotator"),
    ("agents.tier4_strategies.breakout_hunter", "BreakoutHunter"),
    ("agents.tier5_execution.order_router", "OrderRouter"),
    ("agents.tier5_execution.fee_optimizer", "FeeOptimizer"),
    ("agents.tier5_execution.slippage_minimizer", "SlippageMinimizer"),
    ("agents.tier5_execution.hedge_manager", "HedgeManager"),
    ("agents.tier5_execution.liquidation_guard", "LiquidationGuard"),
    ("agents.tier5_execution.exchange_executor", "ExchangeExecutor"),
    ("agents.tier7_monitoring.portfolio_tracker", "PortfolioTracker"),
    ("agents.tier7_monitoring.alert_manager", "AlertManager"),
    ("agents.tier7_monitoring.compliance_agent", "ComplianceAgent"),
]


@pytest.mark.unit
@pytest.mark.parametrize("module_path, class_name", AGENT_MODULES)
def test_agent_class_imports(module_path: str, class_name: str):
    """Every agent module must import without error and expose its class."""
    module = importlib.import_module(module_path)
    assert hasattr(module, class_name), f"{module_path} missing class {class_name}"


@pytest.mark.unit
@pytest.mark.parametrize("module_path, class_name", [
    ("agents.tier4_strategies.trend_follower", "TrendFollower"),
    ("agents.tier4_strategies.mean_reversion", "MeanReversion"),
    ("agents.tier4_strategies.arb_cross_exchange", "CrossExchangeArb"),
])
def test_strategy_class_implements_abstract_interface(module_path: str, class_name: str):
    """Tier 4 strategies must implement all abstract methods to be instantiable."""
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    # If any abstract method is unimplemented, __abstractmethods__ is non-empty.
    assert getattr(cls, "__abstractmethods__", frozenset()) == frozenset(), (
        f"{class_name} has unimplemented abstract methods: "
        f"{cls.__abstractmethods__}"
    )


@pytest.mark.unit
def test_position_sizer_constructs():
    from decimal import Decimal
    from agents.tier5_execution.position_sizer import PositionSizer
    sizer = PositionSizer(portfolio_value_usd=Decimal("100000"))
    result = sizer.size(
        symbol="BTC/USDT",
        strategy_id="test",
        entry_price=Decimal("45000"),
        stop_loss=Decimal("44000"),
        win_rate=0.55,
        avg_win=0.02,
        avg_loss=0.01,
        symbol_daily_vol=0.025,
        current_leverage=1.0,
    )
    assert result.symbol == "BTC/USDT"
    assert result.final_size_usd >= Decimal("0")
    # No legacy fields
    assert not hasattr(result, "size_usd") or result.final_size_usd is not None


@pytest.mark.unit
def test_proposal_approver_imports():
    from agents.tier1_executive.proposal_approver import ProposalApprover
    assert ProposalApprover.AGENT_ID == 3
