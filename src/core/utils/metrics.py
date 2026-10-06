"""
ALGHREST — Prometheus Metrics Registry
Central definitions for all system-wide metrics. Import and use these in agents.
"""

from __future__ import annotations

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info, start_http_server

# ── SYSTEM INFO ─────────────────────────────────────────────────────────────
system_info = Info("alghrest_system", "ALGHREST system metadata")

# ── AGENT METRICS ───────────────────────────────────────────────────────────
agent_status = Gauge(
    "alghrest_agent_status",
    "Current agent status (1=RUNNING, 0=other)",
    ["agent_id", "agent_name", "tier"],
)

agent_messages_processed = Counter(
    "alghrest_agent_messages_processed_total",
    "Total messages successfully processed by agent",
    ["agent_id", "agent_name", "topic"],
)

agent_messages_failed = Counter(
    "alghrest_agent_messages_failed_total",
    "Total messages that failed processing",
    ["agent_id", "agent_name", "topic", "error_type"],
)

agent_processing_latency = Histogram(
    "alghrest_agent_processing_latency_seconds",
    "Time to process one message",
    ["agent_id", "agent_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0],
)

agent_memory_mb = Gauge(
    "alghrest_agent_memory_mb",
    "Agent process memory usage in MB",
    ["agent_id", "agent_name"],
)

# ── KAFKA METRICS ────────────────────────────────────────────────────────────
kafka_messages_produced = Counter(
    "alghrest_kafka_messages_produced_total",
    "Total messages published to Kafka",
    ["topic", "agent_id"],
)

kafka_messages_consumed = Counter(
    "alghrest_kafka_messages_consumed_total",
    "Total messages consumed from Kafka",
    ["topic", "consumer_group"],
)

kafka_consumer_lag = Gauge(
    "alghrest_kafka_consumer_lag",
    "Consumer group lag per topic-partition",
    ["topic", "partition", "consumer_group"],
)

kafka_produce_errors = Counter(
    "alghrest_kafka_produce_errors_total",
    "Total Kafka produce errors",
    ["topic", "error_type"],
)

# ── PORTFOLIO METRICS ────────────────────────────────────────────────────────
portfolio_total_capital = Gauge(
    "alghrest_portfolio_total_capital",
    "Total portfolio capital in USD",
)

portfolio_daily_pnl = Gauge(
    "alghrest_portfolio_daily_pnl",
    "Daily realized + unrealized PnL in USD",
)

portfolio_unrealized_pnl = Gauge(
    "alghrest_portfolio_unrealized_pnl",
    "Unrealized PnL across all open positions",
)

portfolio_open_positions = Gauge(
    "alghrest_portfolio_open_positions",
    "Number of currently open positions",
)

portfolio_leverage = Gauge(
    "alghrest_portfolio_leverage",
    "Current portfolio leverage",
)

# ── RISK METRICS ─────────────────────────────────────────────────────────────
risk_daily_drawdown_pct = Gauge(
    "alghrest_risk_daily_drawdown_pct",
    "Current daily drawdown as decimal (0.05 = 5%)",
)

risk_current_leverage = Gauge(
    "alghrest_risk_current_leverage",
    "Current portfolio leverage",
)

risk_var_95 = Gauge(
    "alghrest_risk_var_95_usd",
    "1-day 95% Value at Risk in USD",
)

risk_alerts_fired = Counter(
    "alghrest_risk_alerts_total",
    "Total risk alerts fired",
    ["alert_type", "risk_level"],
)

kill_switch_triggers = Counter(
    "alghrest_kill_switch_triggers_total",
    "Total kill switch activations",
    ["scope", "reason"],
)

# ── TRADING METRICS ──────────────────────────────────────────────────────────
trade_proposals_submitted = Counter(
    "alghrest_trade_proposals_submitted_total",
    "Trade proposals submitted by strategy agents",
    ["strategy_id"],
)

trade_proposals_approved = Counter(
    "alghrest_trade_proposals_approved_total",
    "Trade proposals approved by CIO",
    ["strategy_id"],
)

trade_proposals_rejected = Counter(
    "alghrest_trade_proposals_rejected_total",
    "Trade proposals rejected",
    ["strategy_id", "reason"],
)

orders_executed = Counter(
    "alghrest_orders_executed_total",
    "Total orders executed",
    ["exchange", "side", "order_type"],
)

execution_slippage_bps = Histogram(
    "alghrest_execution_slippage_bps",
    "Order execution slippage in basis points",
    ["exchange", "symbol"],
    buckets=[1, 2, 5, 10, 20, 50, 100, 200],
)

strategy_pnl = Gauge(
    "alghrest_strategy_pnl_usd",
    "Cumulative PnL per strategy",
    ["strategy_id"],
)

strategy_win_rate = Gauge(
    "alghrest_strategy_win_rate",
    "Rolling win rate per strategy (0-1)",
    ["strategy_id"],
)

strategy_sharpe = Gauge(
    "alghrest_strategy_sharpe_90d",
    "90-day rolling Sharpe ratio",
    ["strategy_id"],
)

# ── MARKET DATA METRICS ──────────────────────────────────────────────────────
price_updates_received = Counter(
    "alghrest_price_updates_total",
    "Total OHLCV bar updates received",
    ["exchange", "symbol", "timeframe"],
)

websocket_reconnections = Counter(
    "alghrest_websocket_reconnections_total",
    "WebSocket reconnection attempts",
    ["exchange"],
)

# ── CLAUDE / LLM METRICS ─────────────────────────────────────────────────────
# Track token usage per kind to monitor prompt-cache hit rate (kind=cache_read
# is the cheap one; kind=cache_create is paid once then amortised; kind=regular
# is uncached input).
claude_input_tokens = Counter(
    "alghrest_claude_input_tokens_total",
    "Claude API input tokens billed",
    ["model", "agent_id", "kind"],
)

claude_output_tokens = Counter(
    "alghrest_claude_output_tokens_total",
    "Claude API output tokens billed",
    ["model", "agent_id"],
)

claude_calls = Counter(
    "alghrest_claude_calls_total",
    "Claude API calls",
    ["model", "agent_id", "outcome"],
)


# ── DEFI METRICS ─────────────────────────────────────────────────────────────
defi_total_staked_usd = Gauge(
    "alghrest_defi_staked_usd",
    "Total value staked across DeFi protocols",
    ["protocol", "chain"],
)

defi_yield_apy = Gauge(
    "alghrest_defi_yield_apy",
    "Current APY for active DeFi positions",
    ["protocol", "pool"],
)

mev_profit_usd = Counter(
    "alghrest_mev_profit_usd_total",
    "Total MEV profit in USD",
    ["opportunity_type"],
)


def start_metrics_server(port: int, host: str = "0.0.0.0") -> None:
    """Start Prometheus HTTP server on given port. Call once per agent process."""
    start_http_server(port, addr=host, registry=REGISTRY)
