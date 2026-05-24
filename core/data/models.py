"""Shared Pydantic data contracts used across agents, risk, API, and tests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AlghrestModel(BaseModel):
    """Base model with permissive payload compatibility for Kafka/Redis messages."""

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        extra="allow",
        populate_by_name=True,
    )


class KafkaTopic(str, Enum):
    PRICES_REALTIME = "prices.realtime"
    MARKET_DATA = "market.data"
    NEWS_TAGGED = "news.tagged"
    SENTIMENT_SCORED = "sentiment.scored"
    ONCHAIN_SIGNALS = "onchain.signals"
    MACRO_REGIME = "macro.regime"
    INDICATORS_COMPUTED = "indicators.computed"
    PATTERNS_DETECTED = "patterns.detected"
    VOLATILITY_FORECAST = "volatility.forecast"
    CORRELATION_MATRIX = "correlation.matrix"
    ANALYSIS_TECHNICAL = "analysis.technical"
    STRATEGY_SIGNALS = "strategy.signals"
    PROPOSALS_BUS = "proposals.bus"
    PROPOSALS_APPROVED = "proposals.approved"
    ORDERS_PENDING = "orders.pending"
    ORDERS_APPROVED = "orders.approved"
    ORDERS_EXECUTED = "orders.executed"
    ORDERS_FILLED = "orders.filled"
    FILLS_CONFIRMED = "fills.confirmed"
    PORTFOLIO_STATE = "portfolio.state"
    RISK_ALERTS = "risk.alerts"
    RL_PARAM_UPDATES = "rl.param.updates"


class AgentStatus(str, Enum):
    INITIALIZING = "INITIALIZING"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DEGRADED = "DEGRADED"
    ERROR = "ERROR"
    STOPPED = "STOPPED"
    SHUTDOWN = "SHUTDOWN"


class Exchange(str, Enum):
    BINANCE = "binance"
    BYBIT = "bybit"
    COINBASE = "coinbase"
    KRAKEN = "kraken"
    OKX = "okx"
    ALPACA = "alpaca"
    DERIBIT = "deribit"
    IBKR = "ibkr"


class AssetClass(str, Enum):
    CRYPTO = "crypto"
    EQUITY = "equity"
    FOREX = "forex"
    COMMODITY = "commodity"
    OPTION = "option"
    DEFI = "defi"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


TradeDirection = OrderSide


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TWAP = "TWAP"
    VWAP = "VWAP"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class SignalDirection(str, Enum):
    STRONG_BULLISH = "STRONG_BULLISH"
    BULLISH = "BULLISH"
    NEUTRAL = "NEUTRAL"
    BEARISH = "BEARISH"
    STRONG_BEARISH = "STRONG_BEARISH"


class MarketRegime(str, Enum):
    RISK_ON = "RISK_ON"
    RISK_OFF = "RISK_OFF"
    NEUTRAL = "NEUTRAL"
    CRISIS = "CRISIS"
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


class VolatilityRegime(str, Enum):
    CALM = "CALM"
    NORMAL = "NORMAL"
    VOLATILE = "VOLATILE"
    CRISIS = "CRISIS"


class AlertType(str, Enum):
    POSITION_LIMIT = "POSITION_LIMIT"
    DRAWDOWN_WARNING = "DRAWDOWN_WARNING"
    DRAWDOWN_ALERT = "DRAWDOWN_ALERT"
    DRAWDOWN_PAUSE = "DRAWDOWN_PAUSE"
    DRAWDOWN_HALT = "DRAWDOWN_HALT"
    LEVERAGE_LIMIT = "LEVERAGE_LIMIT"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    CONNECTIVITY_LOSS = "CONNECTIVITY_LOSS"
    KILL_SWITCH = "KILL_SWITCH"
    WASH_TRADE_RISK = "WASH_TRADE_RISK"
    SANCTIONS_HIT = "SANCTIONS_HIT"
    COMPLIANCE = "COMPLIANCE"
    SYSTEM = "SYSTEM"


class RiskLevel(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Chain(str, Enum):
    ETHEREUM = "ethereum"
    ARBITRUM = "arbitrum"
    OPTIMISM = "optimism"
    POLYGON = "polygon"
    BASE = "base"
    SOLANA = "solana"


class TradeProposalStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class AgentConfig(AlghrestModel):
    agent_id: int
    agent_name: str
    tier: int
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentHealth(AlghrestModel):
    agent_id: int
    agent_name: str
    tier: int
    status: AgentStatus
    start_time: datetime | None = None
    last_heartbeat: datetime | None = None
    uptime_seconds: int = 0
    messages_processed: int = 0
    messages_failed: int = 0
    memory_mb: float | None = None
    latency_p99_ms: float | None = None
    last_error: str | None = None


class AgentHeartbeat(AlghrestModel):
    agent_id: int
    agent_name: str = ""
    status: AgentStatus = AgentStatus.RUNNING
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentMessage(AlghrestModel):
    message_id: UUID = Field(default_factory=uuid4)
    source_agent_id: int
    topic: KafkaTopic | str
    message_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class OHLCVBar(AlghrestModel):
    time: datetime
    symbol: str
    exchange: Exchange
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    is_closed: bool = True

    @model_validator(mode="before")
    @classmethod
    def _legacy_timestamp(cls, data: Any) -> Any:
        if isinstance(data, dict) and "time" not in data and "timestamp" in data:
            data = dict(data)
            data["time"] = data.pop("timestamp")
        return data


class PriceData(AlghrestModel):
    symbol: str
    price: Decimal
    exchange: Exchange = Exchange.BINANCE
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    volume: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MarketData(AlghrestModel):
    symbol: str
    price: Decimal
    volume: Decimal = Decimal("0")
    exchange: Exchange = Exchange.BINANCE
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrderBookLevel(AlghrestModel):
    price: Decimal
    size: Decimal


class OrderBook(AlghrestModel):
    symbol: str
    exchange: Exchange
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    bids: list[OrderBookLevel] = Field(default_factory=list)
    asks: list[OrderBookLevel] = Field(default_factory=list)


class MarketState(AlghrestModel):
    symbol: str = ""
    exchange: Exchange = Exchange.BINANCE
    timeframe: Timeframe = Timeframe.H1
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    price: Decimal | None = None
    ohlcv: list[OHLCVBar] = Field(default_factory=list)
    indicators: dict[str, Any] = Field(default_factory=dict)
    signals: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Position(AlghrestModel):
    position_id: UUID = Field(default_factory=uuid4)
    symbol: str
    exchange: Exchange = Exchange.BINANCE
    asset_class: AssetClass = AssetClass.CRYPTO
    side: OrderSide
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    strategy_id: str = ""
    agent_id: int = 0
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def market_value(self) -> Decimal:
        return self.size * self.current_price

    @property
    def unrealized_pnl_pct(self) -> float:
        basis = self.size * self.entry_price
        if basis == 0:
            return 0.0
        return float(self.unrealized_pnl / basis)


class Portfolio(AlghrestModel):
    snapshot_time: datetime = Field(default_factory=datetime.utcnow)
    total_capital: Decimal
    available_capital: Decimal
    reserved_capital: Decimal = Decimal("0")
    emergency_reserve: Decimal = Decimal("0")
    positions: list[Position] = Field(default_factory=list)
    daily_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_exposure_usd(self) -> Decimal:
        return sum((p.market_value for p in self.positions), Decimal("0"))

    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    @property
    def leverage(self) -> float:
        if self.total_capital == 0:
            return 0.0
        return float(self.total_exposure_usd / self.total_capital)


class RiskLimits(AlghrestModel):
    max_risk_per_trade: float = 0.01
    max_portfolio_drawdown: float = 0.25
    max_single_asset: float = 0.05
    max_single_sector: float = 0.20
    max_leverage: float = 3.0
    max_correlation_allowed: float = 0.85
    consecutive_loss_pause: int = 5
    hot_wallet_max_pct: float = 0.05


RISK_LIMITS = RiskLimits()


class RiskMetrics(AlghrestModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_capital: Decimal = Decimal("0")
    available_capital: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")
    var_95_1d: Decimal | None = None
    var_99_1d: Decimal | None = None
    cvar_95_1d: Decimal | None = None
    daily_drawdown_pct: float = 0.0
    weekly_drawdown_pct: float = 0.0
    monthly_drawdown_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    current_leverage: float = 0.0
    open_positions: int = 0
    position_concentration: dict[str, float] = Field(default_factory=dict)
    effective_n: float = 0.0
    sharpe_90d: float | None = None
    sortino_90d: float | None = None


class TradeProposal(AlghrestModel):
    proposal_id: UUID = Field(default_factory=uuid4)
    strategy_id: str
    agent_id: int = 0
    symbol: str
    exchange: Exchange = Exchange.BINANCE
    asset_class: AssetClass = AssetClass.CRYPTO
    side: OrderSide
    order_type: OrderType = OrderType.MARKET
    size: Decimal
    size_usd: Decimal = Decimal("0")
    limit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    confidence_score: float = 0.0
    rationale: str = ""
    status: TradeProposalStatus = TradeProposalStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    urgency: str = "normal"
    adjusted_size_usd: Decimal | None = None
    rejection_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "confidence_score" not in data and "confidence" in data:
            data["confidence_score"] = data.pop("confidence")
        if "limit_price" not in data and "entry_price" in data:
            data["limit_price"] = data.pop("entry_price")
        if "size" not in data and "quantity" in data:
            data["size"] = data.pop("quantity")
        if "side" not in data and "direction" in data:
            direction = str(data.pop("direction")).upper()
            data["side"] = OrderSide.SELL if direction in {"SELL", "SHORT", "BEARISH"} else OrderSide.BUY
        return data


class TradeProposalReview(AlghrestModel):
    proposal_id: UUID
    reviewer_agent_id: int
    decision: TradeProposalStatus
    reason: str = ""
    risk_score: float = 0.0
    adjusted_size_usd: Decimal | None = None
    reviewed_at: datetime = Field(default_factory=datetime.utcnow)


class Order(AlghrestModel):
    order_id: UUID = Field(default_factory=uuid4)
    client_order_id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID | None = None
    exchange_order_id: str | None = None
    symbol: str
    exchange: Exchange
    side: OrderSide
    order_type: OrderType
    size: Decimal
    price: Decimal | None = None
    stop_price: Decimal | None = None
    time_in_force: str = "GTC"
    status: OrderStatus = OrderStatus.PENDING
    filled_size: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    strategy_id: str
    agent_id: int
    algo_params: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _legacy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        if "size" not in data and "quantity" in data:
            data["size"] = data.pop("quantity")
        if "filled_size" not in data and "filled_quantity" in data:
            data["filled_size"] = data.pop("filled_quantity")
        return data


class Fill(AlghrestModel):
    fill_id: str = Field(default_factory=lambda: str(uuid4()))
    order_id: UUID
    exchange_order_id: str
    symbol: str
    exchange: Exchange
    side: OrderSide
    fill_size: Decimal
    fill_price: Decimal
    fee: Decimal = Decimal("0")
    fee_currency: str = "USD"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    strategy_id: str = ""
    is_maker: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class PositionSizingResult(AlghrestModel):
    symbol: str
    strategy_id: str
    entry_price: Decimal
    stop_loss: Decimal
    total_capital: Decimal
    kelly_fraction_raw: float
    kelly_size_usd: Decimal
    quarter_kelly_size_usd: Decimal
    vol_adjusted_size_usd: Decimal
    final_size_usd: Decimal
    final_size_units: Decimal
    risk_amount_usd: Decimal
    risk_pct_of_capital: float
    constraints_applied: list[str] = Field(default_factory=list)


class BacktestResult(AlghrestModel):
    strategy_name: str = ""
    strategy_id: str = ""
    symbol: str = ""
    timeframe: Timeframe = Timeframe.D1
    start_date: datetime | None = None
    end_date: datetime | None = None
    initial_capital: Decimal = Decimal("0")
    final_capital: Decimal = Decimal("0")
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    trades_per_year: float = 0.0
    avg_trade_return_pct: float = 0.0
    performance_metrics: PerformanceMetrics | None = None
    trades: list[dict[str, Any]] = Field(default_factory=list)
    signals_generated: int = 0
    data_quality_score: float = 0.0
    failure_reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class WalkForwardWindow(AlghrestModel):
    window_id: int = 0
    train_start: datetime | None = None
    train_end: datetime | None = None
    test_start: datetime | None = None
    test_end: datetime | None = None
    in_sample: BacktestResult = Field(default_factory=BacktestResult)
    out_of_sample: BacktestResult = Field(default_factory=BacktestResult)
    best_params: dict[str, Any] = Field(default_factory=dict)

    @property
    def wf_efficiency(self) -> float:
        if self.in_sample.sharpe_ratio == 0:
            return 0.0
        return self.out_of_sample.sharpe_ratio / self.in_sample.sharpe_ratio


class WalkForwardResult(AlghrestModel):
    strategy_name: str = ""
    strategy_id: str = ""
    symbol: str = ""
    num_windows: int = 0
    windows: list[WalkForwardWindow] = Field(default_factory=list)
    window_results: list[dict[str, Any]] = Field(default_factory=list)
    in_sample_performance: PerformanceMetrics | None = None
    out_of_sample_performance: float = 0.0
    walk_forward_efficiency: float = 0.0
    avg_oos_sharpe: float = 0.0
    avg_wf_efficiency: float = 0.0
    passed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)


class MonteCarloResult(AlghrestModel):
    strategy_id: str = ""
    symbol: str = ""
    num_simulations: int = 0
    simulations: int = 0
    final_capitals: list[float] = Field(default_factory=list)
    ruin_probability: float = 0.0
    var_95: float = 0.0
    percentile_95_var: float = 0.0
    cvar_95: float = 0.0
    median_terminal_return: float = 0.0
    confidence_intervals: dict[str, float] = Field(default_factory=dict)
    passed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)


class PerformanceMetrics(AlghrestModel):
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_trades: int = 0
    avg_trade_return: float = 0.0
    trades_per_year: float = 0.0


class AnalysisResult(AlghrestModel):
    symbol: str = ""
    signal: SignalDirection = SignalDirection.NEUTRAL
    confidence: float = 0.0
    source_agent_id: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    indicators: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BaseSignal(AlghrestModel):
    source_agent_id: int = 0
    symbol: str | None = None
    direction: SignalDirection = SignalDirection.NEUTRAL
    confidence: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TechnicalSignal(BaseSignal):
    indicators: dict[str, Any] = Field(default_factory=dict)


class VolatilitySignal(BaseSignal):
    regime: VolatilityRegime = VolatilityRegime.NORMAL
    forecast_volatility: float | None = None


class MacroSignal(BaseSignal):
    regime: MarketRegime = MarketRegime.NEUTRAL


class SentimentSignal(BaseSignal):
    sentiment_score: float = 0.0


class NewsSignal(BaseSignal):
    headline: str | None = None
    source: str | None = None


class OnChainSignal(BaseSignal):
    chain: Chain = Chain.ETHEREUM


class GeopoliticalSignal(BaseSignal):
    region: str | None = None


class CorrelationUpdate(AlghrestModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbols: list[str] = Field(default_factory=list)
    matrix: list[list[float]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SentimentScore(AlghrestModel):
    symbol: str
    source: str = ""
    score: float
    volume: int = 0
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class NewsItem(AlghrestModel):
    headline: str
    source: str = ""
    url: str | None = None
    published_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str = ""
    direction: SignalDirection = SignalDirection.NEUTRAL
    impact_score: float = 0.0
    categories: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    affected_symbols: list[str] = Field(default_factory=list)


class WhaleAlert(AlghrestModel):
    chain: Chain = Chain.ETHEREUM
    symbol: str = ""
    amount: Decimal = Decimal("0")
    amount_usd: Decimal = Decimal("0")
    from_address: str | None = None
    to_address: str | None = None
    exchange_inflow: bool = False
    exchange_outflow: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClosedTrade(AlghrestModel):
    trade_id: str = Field(default_factory=lambda: str(uuid4()))
    symbol: str
    exchange: Exchange = Exchange.BINANCE
    side: OrderSide
    size: Decimal
    entry_price: Decimal
    exit_price: Decimal
    pnl: Decimal = Decimal("0")
    opened_at: datetime | None = None
    closed_at: datetime = Field(default_factory=datetime.utcnow)
    strategy_id: str = ""
    agent_id: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(AlghrestModel):
    plan_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    order_type: OrderType
    slices: int = 1
    duration_minutes: int = 0
    participation_rate: float | None = None
    child_orders: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionResult(AlghrestModel):
    plan_id: UUID | None = None
    order_id: UUID
    status: OrderStatus
    filled_size: Decimal = Decimal("0")
    avg_fill_price: Decimal | None = None
    slippage_bps: float | None = None
    fills: list[Fill] = Field(default_factory=list)
    completed_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class KillSwitchEvent(AlghrestModel):
    event_id: UUID = Field(default_factory=uuid4)
    triggered_by: str = ""
    reason: str
    risk_level: RiskLevel = RiskLevel.CRITICAL
    alert_type: AlertType = AlertType.KILL_SWITCH
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    ttl_seconds: int = 86400
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskAlert(AlghrestModel):
    alert_id: UUID = Field(default_factory=uuid4)
    alert_type: AlertType
    risk_level: RiskLevel = RiskLevel.MEDIUM
    message: str
    symbol: str | None = None
    strategy_id: str | None = None
    agent_id: int | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _legacy_severity(cls, data: Any) -> Any:
        if isinstance(data, dict) and "risk_level" not in data and "severity" in data:
            data = dict(data)
            data["risk_level"] = data.get("severity")
        return data
