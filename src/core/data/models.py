"""Shared contracts recovered from producers, consumers, SQL, and regression tests.

Money and quantities remain Decimal in Python and serialize as decimal strings
in Pydantic's JSON mode. Enum instances remain available to callers using .value.
See docs/model-restoration.md for evidence and unresolved legacy contracts.
"""

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field

from core.data.performance import Performance


def _utcnow() -> datetime:
    # Existing routers and strategy loops subtract naive datetime.utcnow().
    return datetime.now(UTC).replace(tzinfo=None)


class KafkaTopic(StrEnum):
    """Exactly the topics provisioned by infra/init/kafka-init.sh."""

    PRICES_REALTIME = "prices.realtime"
    NEWS_TAGGED = "news.tagged"
    SENTIMENT_SCORED = "sentiment.scored"
    ONCHAIN_SIGNALS = "onchain.signals"
    MACRO_REGIME = "macro.regime"
    INDICATORS_COMPUTED = "indicators.computed"
    PATTERNS_DETECTED = "patterns.detected"
    VOLATILITY_FORECAST = "volatility.forecast"
    CORRELATION_MATRIX = "correlation.matrix"
    PROPOSALS_BUS = "proposals.bus"
    PROPOSALS_APPROVED = "proposals.approved"
    ORDERS_PENDING = "orders.pending"
    ORDERS_APPROVED = "orders.approved"
    ORDERS_EXECUTED = "orders.executed"
    FILLS_CONFIRMED = "fills.confirmed"
    PORTFOLIO_STATE = "portfolio.state"
    RISK_ALERTS = "risk.alerts"
    RL_PARAM_UPDATES = "rl.param.updates"


class Exchange(StrEnum):
    BINANCE = "binance"
    BYBIT = "bybit"
    COINBASE = "coinbase"
    KRAKEN = "kraken"
    OKX = "okx"
    ALPACA = "alpaca"
    OPENBB = "openbb"


class AssetClass(StrEnum):
    CRYPTO = "CRYPTO"
    EQUITY = "EQUITY"
    FOREX = "FOREX"
    MACRO = "MACRO"


class Timeframe(StrEnum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1d"
    W1 = "1w"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"
    TWAP = "TWAP"
    VWAP = "VWAP"


class OrderStatus(StrEnum):
    PENDING = "PENDING"
    OPEN = "OPEN"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class TradeProposalStatus(StrEnum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SignalDirection(StrEnum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    STRONG_BULLISH = "STRONG_BULLISH"
    STRONG_BEARISH = "STRONG_BEARISH"


class TradeDirection(StrEnum):
    """Legacy direction used only by disabled DeFi skeletons."""

    LONG = "LONG"


class MarketRegime(StrEnum):
    RISK_ON = "RISK_ON"
    NEUTRAL = "NEUTRAL"
    RISK_OFF = "RISK_OFF"
    CRISIS = "CRISIS"


class VolatilityRegime(StrEnum):
    CALM = "CALM"
    NORMAL = "NORMAL"
    VOLATILE = "VOLATILE"
    CRISIS = "CRISIS"


class Chain(StrEnum):
    ETHEREUM = "ethereum"


class AgentStatus(StrEnum):
    INITIALIZING = "INITIALIZING"
    RUNNING = "RUNNING"
    DEGRADED = "DEGRADED"
    PAUSED = "PAUSED"
    ERROR = "ERROR"
    SHUTDOWN = "SHUTDOWN"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertType(StrEnum):
    CONNECTIVITY_LOSS = "CONNECTIVITY_LOSS"
    CONSECUTIVE_LOSSES = "CONSECUTIVE_LOSSES"
    DRAWDOWN_ALERT = "DRAWDOWN_ALERT"
    DRAWDOWN_PAUSE = "DRAWDOWN_PAUSE"
    DRAWDOWN_HALT = "DRAWDOWN_HALT"
    LEVERAGE_LIMIT = "LEVERAGE_LIMIT"
    POSITION_LIMIT = "POSITION_LIMIT"
    SANCTIONS_HIT = "SANCTIONS_HIT"
    WASH_TRADE_RISK = "WASH_TRADE_RISK"


class AgentConfig(BaseModel):
    agent_id: int
    agent_name: str
    tier: int


class AgentHealth(AgentConfig):
    status: AgentStatus
    start_time: datetime
    last_heartbeat: datetime
    uptime_seconds: float
    messages_processed: int = 0
    messages_failed: int = 0
    error_count: int = 0
    last_error: str | None = None
    latency_p50_ms: float | None = None
    latency_p99_ms: float | None = None
    memory_mb: float | None = None
    cpu_pct: float | None = None


class AgentHeartbeat(AgentConfig):
    """Legacy Redis test payload; distinct from the runtime AgentHealth contract."""

    status: str
    last_heartbeat: datetime
    memory_mb: float
    cpu_percent: float
    messages_processed: int


class AgentMessage(BaseModel):
    message_id: UUID = Field(default_factory=uuid4)
    source_agent_id: int
    topic: KafkaTopic
    message_type: str
    payload: dict[str, Any]


class OHLCVBar(BaseModel):
    time: datetime
    symbol: str
    exchange: Exchange
    timeframe: Timeframe
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal = Decimal("0")
    quote_volume: Decimal = Decimal("0")
    trade_count: int = 0
    vwap: Decimal | None = None
    is_closed: bool = True


class OrderBookLevel(BaseModel):
    price: Decimal
    size: Decimal


class OrderBook(BaseModel):
    symbol: str
    exchange: Exchange
    timestamp: datetime
    bids: list[OrderBookLevel]
    asks: list[OrderBookLevel]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_bid(self) -> Decimal | None:
        return self.bids[0].price if self.bids else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def best_ask(self) -> Decimal | None:
        return self.asks[0].price if self.asks else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def mid_price(self) -> Decimal | None:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2


class MarketState(BaseModel):
    # Only these three attributes have consumers; no fabricated aggregate schema.
    prices: dict[str, Decimal]
    symbol: str
    price: float


class TradeProposal(BaseModel):
    accounting_book_id: str | None = None
    proposal_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    strategy_id: str
    agent_id: int
    symbol: str
    exchange: Exchange
    account_id: str = Field(default="default", min_length=1)
    asset_class: AssetClass
    side: OrderSide
    order_type: OrderType
    size: Decimal
    size_usd: Decimal
    limit_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    confidence_score: float = Field(ge=0, le=1)
    rationale: str | None = None
    status: TradeProposalStatus = TradeProposalStatus.PENDING
    rejection_reason: str | None = None
    expires_at: datetime | None = None
    urgency: str | None = None
    adjusted_size_usd: Decimal | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class TradeProposalReview(BaseModel):
    accounting_book_id: str | None = None
    proposal_id: UUID
    reviewer_agent_id: int
    decision: TradeProposalStatus
    reason: str
    risk_score: float = Field(ge=0, le=1)
    adjusted_size_usd: Decimal | None = None


class Order(BaseModel):
    accounting_book_id: str | None = None
    authorization_id: UUID | None = None
    order_id: UUID = Field(default_factory=uuid4)
    client_order_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    exchange_order_id: str | None = None
    proposal_id: UUID | None = None
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
    fees: Decimal = Decimal("0")
    strategy_id: str
    agent_id: int
    algo_params: dict[str, Any] = Field(default_factory=dict)
    account_id: str = "default"


class FillFee(BaseModel):
    currency: str = Field(min_length=1)
    amount: Decimal = Field(allow_inf_nan=False)


class Fill(BaseModel):
    fill_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    exchange_order_id: str
    symbol: str
    exchange: Exchange
    side: OrderSide
    fill_size: Decimal
    fill_price: Decimal
    fee: Decimal = Decimal("0")
    fee_currency: str = "USDT"
    timestamp: datetime
    is_maker: bool = False
    strategy_id: str | None = None
    # Exchange trade IDs can be scoped to a market; never use the random fill_id
    # as an accounting idempotency key. None supports reading legacy messages.
    exchange_trade_id: str | None = None
    account_id: str = "default"
    agent_id: int = 0
    fees: list[FillFee] | None = None  # authoritative when present (including [])
    accounting_book_id: str | None = None


class Position(BaseModel):
    position_id: UUID = Field(default_factory=uuid4)
    symbol: str
    exchange: Exchange
    asset_class: AssetClass
    side: OrderSide
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    strategy_id: str
    agent_id: int
    opened_at: datetime
    updated_at: datetime = Field(default_factory=_utcnow)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    account_id: str = "default"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unrealized_pnl(self) -> Decimal:
        direction = 1 if self.side == OrderSide.BUY else -1
        return (self.current_price - self.entry_price) * self.size * direction

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unrealized_pnl_pct(self) -> float:
        if self.entry_price == 0:
            return 0.0
        direction = 1 if self.side == OrderSide.BUY else -1
        return float((self.current_price / self.entry_price - 1) * 100 * direction)


class ClosedTrade(BaseModel):
    """Persisted trade contract from trading.closed_trades in timescale-init.sql."""

    trade_id: UUID = Field(default_factory=uuid4)
    closed_at: datetime
    opened_at: datetime
    symbol: str
    exchange: Exchange
    asset_class: AssetClass
    side: OrderSide
    size: Decimal
    entry_price: Decimal
    exit_price: Decimal
    realized_pnl: Decimal
    fees: Decimal = Decimal("0")
    net_pnl: Decimal
    pnl_pct: float | None = None
    holding_seconds: int | None = None
    strategy_id: str
    agent_id: int
    close_reason: str | None = None


class Portfolio(BaseModel):
    snapshot_time: datetime
    total_capital: Decimal
    available_capital: Decimal
    reserved_capital: Decimal
    emergency_reserve: Decimal
    daily_pnl: Decimal = Decimal("0")
    weekly_pnl: Decimal = Decimal("0")
    positions: list[Position]
    accounting_book_id: str | None = None
    accounting_revision: int | None = None
    performance: Performance | None = None
    # Native currency balances; derived USD amounts above remain compatible.
    cash_balances: list[dict[str, Any]] = Field(default_factory=list)
    cash_currency_exposure_usd: Decimal = Decimal("0")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unrealized_pnl(self) -> Decimal:
        return sum((p.unrealized_pnl for p in self.positions), Decimal("0"))

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_exposure_usd(self) -> Decimal:
        return self.cash_currency_exposure_usd + sum(
            (abs(p.size * p.current_price) for p in self.positions), Decimal("0")
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def open_position_count(self) -> int:
        return len(self.positions)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def leverage(self) -> float:
        if self.total_capital <= 0:
            return 0.0
        return float(self.total_exposure_usd / self.total_capital)


class PositionSizingResult(BaseModel):
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
    constraints_applied: list[str]


class RiskLimits(BaseModel):
    """Hard ceilings from CIO policy, kill-switch code, and correlation engine."""

    model_config = ConfigDict(frozen=True)

    max_risk_per_trade: float = Field(default=0.01, gt=0, le=0.01)
    max_single_asset: float = Field(default=0.05, gt=0, le=0.05)
    max_single_sector: float = Field(default=0.20, gt=0, le=0.20)
    max_leverage: float = Field(default=3.0, gt=0, le=3.0)
    emergency_reserve_pct: float = Field(default=0.15, ge=0.15, le=1)
    consecutive_loss_pause: int = Field(default=5, gt=0, le=5)
    daily_drawdown_alert: float = Field(default=0.03, gt=0, le=0.03)
    daily_drawdown_pause: float = Field(default=0.05, gt=0, le=0.05)
    weekly_drawdown_halt: float = Field(default=0.07, gt=0, le=0.07)
    monthly_kill_switch: float = Field(default=0.12, gt=0, le=0.12)
    max_correlation_allowed: float = Field(default=0.85, gt=0, le=0.85)


RISK_LIMITS = RiskLimits()


class RiskMetrics(BaseModel):
    timestamp: datetime
    total_capital: Decimal
    available_capital: Decimal
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
    effective_n: float | None = None
    sharpe_90d: float | None = None
    sortino_90d: float | None = None


class RiskAlert(BaseModel):
    alert_type: AlertType
    risk_level: RiskLevel
    source_agent_id: int
    message: str
    triggered_value: float
    threshold_value: float
    affected_strategy_ids: list[str] = Field(default_factory=list)
    recommended_action: str


class KillSwitchEvent(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    triggered_at: datetime = Field(default_factory=_utcnow)
    triggered_by_agent: int
    trigger_reason: str
    drawdown_pct: float
    scope: str
    positions_closed: int = 0
    capital_preserved: Decimal


class _Signal(BaseModel):
    signal_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=_utcnow)
    source_agent_id: int
    symbol: str | None = None
    direction: SignalDirection
    confidence: float = Field(ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TechnicalSignal(_Signal):
    timeframe: Timeframe
    indicator: str
    indicator_value: float
    threshold_breached: float | None
    trend_strength: float | None


class VolatilitySignal(_Signal):
    regime: VolatilityRegime
    realized_vol_1d: float
    realized_vol_7d: float
    realized_vol_30d: float
    forecast_1d: float
    forecast_7d: float
    forecast_30d: float
    garch_model: str
    hurst_exponent: float | None


class CorrelationUpdate(BaseModel):
    source_agent_id: int
    window_days: int
    symbols: list[str]
    correlation_matrix: dict[str, dict[str, float]]
    cointegrated_pairs: list[tuple[str, str, float]]
    high_correlation_pairs: list[tuple[str, str, float]]
    effective_n: float


class NewsItem(BaseModel):
    news_id: UUID = Field(default_factory=uuid4)
    headline: str
    summary: str | None
    source: str
    url: str | None
    published_at: datetime
    direction: SignalDirection
    impact_score: float
    categories: list[str]
    entities: list[str]
    affected_symbols: list[str]


class NewsSignal(_Signal):
    headline: str
    summary: str | None
    source: str
    url: str | None
    impact_score: float
    categories: list[str]
    entities: list[str]
    affected_symbols: list[str]
    published_at: datetime


class SentimentScore(BaseModel):
    symbol: str
    timestamp: datetime
    source: str
    score: float = Field(ge=-1, le=1)
    volume: int
    positive_count: int
    negative_count: int
    neutral_count: int


class SentimentSignal(_Signal):
    source: str
    sentiment_score: float = Field(ge=-1, le=1)
    volume_mentions: int


class MacroSignal(_Signal):
    indicator_name: str
    actual_value: float | None
    regime: MarketRegime
    country: str


class GeopoliticalSignal(_Signal):
    region: str
    event_type: str
    risk_index: float
    affected_assets: list[str]
    data_source: str


class WhaleAlert(BaseModel):
    chain: Chain
    asset: str
    amount: Decimal
    amount_usd: Decimal
    from_address: str
    to_address: str
    from_label: str
    to_label: str
    tx_hash: str
    block_number: int
    timestamp: datetime
    is_exchange_inflow: bool
    is_exchange_outflow: bool


class OnChainSignal(_Signal):
    metric: str
    value: float
    previous_value: float | None = None
    change_24h_pct: float | None = None
    whale_threshold_usd: Decimal | None = None
    chain: Chain
    addresses_involved: list[str] = Field(default_factory=list)
    data_source: str


class PerformanceMetrics(BaseModel):
    """Fractional metrics produced by the integration suite's mock engine."""

    total_return: float
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    total_trades: int
    avg_trade_return: float
    trades_per_year: float


class BacktestResult(BaseModel):
    model_config = ConfigDict(ser_json_inf_nan="strings")

    strategy_id: str
    strategy_name: str
    symbol: str
    timeframe: Timeframe
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    max_drawdown_duration_days: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    profit_factor: float
    avg_return_per_trade_pct: float
    avg_winning_trade_pct: float
    avg_losing_trade_pct: float
    largest_winner_pct: float
    largest_loser_pct: float
    max_consecutive_losses: int
    avg_holding_hours: float
    trades_per_year: float
    passed_validation: bool
    failure_reasons: list[str]
    # Net closed-trade PnL / entry cost including fees; fractions, not percentages.
    # None preserves legacy payloads, which cannot qualify for empirical Monte Carlo.
    trade_returns: list[float] | None = None


class WalkForwardWindow(BaseModel):
    window_index: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    in_sample: BacktestResult
    out_of_sample: BacktestResult

    @computed_field  # type: ignore[prop-decorator]
    @property
    def wf_efficiency(self) -> float:
        # tests/integration/test_backtesting_validation.py computes OOS / IS return.
        if self.in_sample.total_return_pct <= 0:
            return 0.0
        return self.out_of_sample.total_return_pct / self.in_sample.total_return_pct


class WalkForwardResult(BaseModel):
    strategy_id: str
    windows: list[WalkForwardWindow]
    avg_oos_sharpe: float
    avg_oos_return_pct: float
    avg_wf_efficiency: float
    passed_validation: bool
    failure_reasons: list[str]


class MonteCarloResult(BaseModel):
    strategy_id: str
    simulations: int
    var_95: float
    var_99: float
    cvar_95: float
    ruin_probability: float
    median_return_pct: float
    percentile_5_return_pct: float
    percentile_95_return_pct: float
    passed_validation: bool
    failure_reasons: list[str]


__all__ = [
    "RISK_LIMITS",
    "AgentConfig",
    "AgentHealth",
    "AgentHeartbeat",
    "AgentMessage",
    "AgentStatus",
    "AlertType",
    "AssetClass",
    "BacktestResult",
    "Chain",
    "ClosedTrade",
    "CorrelationUpdate",
    "Exchange",
    "Fill",
    "FillFee",
    "GeopoliticalSignal",
    "KafkaTopic",
    "KillSwitchEvent",
    "MacroSignal",
    "MarketRegime",
    "MarketState",
    "MonteCarloResult",
    "NewsItem",
    "NewsSignal",
    "OHLCVBar",
    "OnChainSignal",
    "Order",
    "OrderBook",
    "OrderBookLevel",
    "OrderSide",
    "OrderStatus",
    "OrderType",
    "PerformanceMetrics",
    "Portfolio",
    "Position",
    "PositionSizingResult",
    "RiskAlert",
    "RiskLevel",
    "RiskLimits",
    "RiskMetrics",
    "SentimentScore",
    "SentimentSignal",
    "SignalDirection",
    "TechnicalSignal",
    "Timeframe",
    "TradeDirection",
    "TradeProposal",
    "TradeProposalReview",
    "TradeProposalStatus",
    "VolatilityRegime",
    "VolatilitySignal",
    "WalkForwardResult",
    "WalkForwardWindow",
    "WhaleAlert",
]
