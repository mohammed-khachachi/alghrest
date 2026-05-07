-- =============================================================================
-- ALGHREST — TimescaleDB Initialization Script
-- Creates hypertables, indexes, and retention policies for all time-series data.
-- Runs once at first container startup via docker-entrypoint-initdb.d/
-- =============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- =============================================================================
-- SCHEMA: market_data
-- Raw and processed market data from all venues
-- =============================================================================
CREATE SCHEMA IF NOT EXISTS market_data;
CREATE SCHEMA IF NOT EXISTS trading;
CREATE SCHEMA IF NOT EXISTS risk;
CREATE SCHEMA IF NOT EXISTS agents;
CREATE SCHEMA IF NOT EXISTS intelligence;
CREATE SCHEMA IF NOT EXISTS defi;
CREATE SCHEMA IF NOT EXISTS performance;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: market_data.ohlcv_bars
-- OHLCV candles from all exchanges and timeframes
-- Hypertable partitioned by time (1 week chunks)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE market_data.ohlcv_bars (
    time            TIMESTAMPTZ     NOT NULL,
    symbol          TEXT            NOT NULL,
    exchange        TEXT            NOT NULL,
    timeframe       TEXT            NOT NULL,   -- '1m','5m','1h','4h','1d','1w'
    open            NUMERIC(28, 10) NOT NULL,
    high            NUMERIC(28, 10) NOT NULL,
    low             NUMERIC(28, 10) NOT NULL,
    close           NUMERIC(28, 10) NOT NULL,
    volume          NUMERIC(28, 10) NOT NULL DEFAULT 0,
    quote_volume    NUMERIC(28, 10)           DEFAULT 0,
    trade_count     INTEGER                   DEFAULT 0,
    vwap            NUMERIC(28, 10),
    is_closed       BOOLEAN                   DEFAULT TRUE
);

SELECT create_hypertable(
    'market_data.ohlcv_bars',
    'time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Composite index: most queries filter by symbol + exchange + timeframe
CREATE UNIQUE INDEX IF NOT EXISTS idx_ohlcv_unique
    ON market_data.ohlcv_bars (time DESC, symbol, exchange, timeframe);

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_tf
    ON market_data.ohlcv_bars (symbol, timeframe, time DESC);

CREATE INDEX IF NOT EXISTS idx_ohlcv_exchange
    ON market_data.ohlcv_bars (exchange, time DESC);

-- Retention: keep 5 years of data (walk-forward needs 5y history)
SELECT add_retention_policy(
    'market_data.ohlcv_bars',
    INTERVAL '5 years',
    if_not_exists => TRUE
);

-- Compression: compress chunks older than 7 days
ALTER TABLE market_data.ohlcv_bars SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'symbol,exchange,timeframe',
    timescaledb.compress_orderby = 'time DESC'
);

SELECT add_compression_policy(
    'market_data.ohlcv_bars',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: market_data.order_book_snapshots
-- Level-2 order book snapshots (best 10 levels each side)
-- Short retention — only needed for recent analysis
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE market_data.order_book_snapshots (
    time        TIMESTAMPTZ     NOT NULL,
    symbol      TEXT            NOT NULL,
    exchange    TEXT            NOT NULL,
    mid_price   NUMERIC(28, 10),
    spread_bps  NUMERIC(10, 4),
    bid_depth   NUMERIC(28, 10),  -- Total bid volume (top 10)
    ask_depth   NUMERIC(28, 10),  -- Total ask volume (top 10)
    imbalance   NUMERIC(8, 6),    -- (bid - ask) / (bid + ask), -1 to +1
    bids        JSONB,            -- [{price, size}, ...]
    asks        JSONB
);

SELECT create_hypertable(
    'market_data.order_book_snapshots',
    'time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_ob_symbol
    ON market_data.order_book_snapshots (symbol, exchange, time DESC);

SELECT add_retention_policy(
    'market_data.order_book_snapshots',
    INTERVAL '7 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- SCHEMA: trading
-- Orders, fills, positions, and trade history
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: trading.trade_proposals
-- All proposals from Tier 4 — immutable audit log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE trading.trade_proposals (
    proposal_id         UUID            NOT NULL DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    strategy_id         TEXT            NOT NULL,
    agent_id            INTEGER         NOT NULL,
    symbol              TEXT            NOT NULL,
    exchange            TEXT            NOT NULL,
    asset_class         TEXT            NOT NULL,
    side                TEXT            NOT NULL,   -- 'BUY' | 'SELL'
    order_type          TEXT            NOT NULL,
    size                NUMERIC(28, 10) NOT NULL,
    size_usd            NUMERIC(20, 4)  NOT NULL,
    limit_price         NUMERIC(28, 10),
    stop_loss           NUMERIC(28, 10),
    take_profit         NUMERIC(28, 10),
    confidence_score    NUMERIC(5, 4)   NOT NULL,
    rationale           TEXT,
    status              TEXT            NOT NULL DEFAULT 'PENDING',
    rejection_reason    TEXT,
    expires_at          TIMESTAMPTZ,
    kafka_offset        BIGINT,
    PRIMARY KEY (proposal_id, created_at)
);

SELECT create_hypertable(
    'trading.trade_proposals',
    'created_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_proposals_strategy
    ON trading.trade_proposals (strategy_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_proposals_status
    ON trading.trade_proposals (status, created_at DESC);

SELECT add_retention_policy(
    'trading.trade_proposals',
    INTERVAL '3 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: trading.orders
-- All orders sent to exchanges
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE trading.orders (
    order_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    client_order_id     UUID            NOT NULL,
    exchange_order_id   TEXT,
    proposal_id         UUID,
    symbol              TEXT            NOT NULL,
    exchange            TEXT            NOT NULL,
    side                TEXT            NOT NULL,
    order_type          TEXT            NOT NULL,
    size                NUMERIC(28, 10) NOT NULL,
    price               NUMERIC(28, 10),
    stop_price          NUMERIC(28, 10),
    time_in_force       TEXT            NOT NULL DEFAULT 'GTC',
    status              TEXT            NOT NULL DEFAULT 'PENDING',
    filled_size         NUMERIC(28, 10)          DEFAULT 0,
    avg_fill_price      NUMERIC(28, 10),
    fees                NUMERIC(20, 8)           DEFAULT 0,
    strategy_id         TEXT            NOT NULL,
    agent_id            INTEGER         NOT NULL,
    PRIMARY KEY (order_id, created_at)
);

SELECT create_hypertable(
    'trading.orders',
    'created_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_orders_exchange_id
    ON trading.orders (exchange_order_id, exchange);

CREATE INDEX IF NOT EXISTS idx_orders_status
    ON trading.orders (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_orders_strategy
    ON trading.orders (strategy_id, created_at DESC);

SELECT add_retention_policy(
    'trading.orders',
    INTERVAL '5 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: trading.fills
-- Immutable exchange fill records (regulatory requirement)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE trading.fills (
    fill_id             UUID            NOT NULL DEFAULT gen_random_uuid(),
    fill_time           TIMESTAMPTZ     NOT NULL,
    order_id            UUID            NOT NULL,
    exchange_order_id   TEXT            NOT NULL,
    symbol              TEXT            NOT NULL,
    exchange            TEXT            NOT NULL,
    side                TEXT            NOT NULL,
    fill_size           NUMERIC(28, 10) NOT NULL,
    fill_price          NUMERIC(28, 10) NOT NULL,
    fee                 NUMERIC(20, 8)  NOT NULL DEFAULT 0,
    fee_currency        TEXT            NOT NULL DEFAULT 'USDT',
    is_maker            BOOLEAN                  DEFAULT FALSE,
    strategy_id         TEXT,
    PRIMARY KEY (fill_id, fill_time)
);

SELECT create_hypertable(
    'trading.fills',
    'fill_time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_fills_order
    ON trading.fills (order_id, fill_time DESC);

CREATE INDEX IF NOT EXISTS idx_fills_symbol
    ON trading.fills (symbol, fill_time DESC);

-- Regulatory: keep fills for 7 years (tax/compliance)
SELECT add_retention_policy(
    'trading.fills',
    INTERVAL '7 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: trading.closed_trades
-- Aggregated completed trades (entry + exit combined)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE trading.closed_trades (
    trade_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    closed_at           TIMESTAMPTZ     NOT NULL,
    opened_at           TIMESTAMPTZ     NOT NULL,
    symbol              TEXT            NOT NULL,
    exchange            TEXT            NOT NULL,
    asset_class         TEXT            NOT NULL,
    side                TEXT            NOT NULL,
    size                NUMERIC(28, 10) NOT NULL,
    entry_price         NUMERIC(28, 10) NOT NULL,
    exit_price          NUMERIC(28, 10) NOT NULL,
    realized_pnl        NUMERIC(20, 8)  NOT NULL,
    fees                NUMERIC(20, 8)  NOT NULL DEFAULT 0,
    net_pnl             NUMERIC(20, 8)  NOT NULL,
    pnl_pct             NUMERIC(10, 6),
    holding_seconds     INTEGER,
    strategy_id         TEXT            NOT NULL,
    agent_id            INTEGER         NOT NULL,
    close_reason        TEXT,           -- 'take_profit','stop_loss','signal_exit','kill_switch'
    PRIMARY KEY (trade_id, closed_at)
);

SELECT create_hypertable(
    'trading.closed_trades',
    'closed_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_closed_trades_strategy
    ON trading.closed_trades (strategy_id, closed_at DESC);

CREATE INDEX IF NOT EXISTS idx_closed_trades_symbol
    ON trading.closed_trades (symbol, closed_at DESC);

SELECT add_retention_policy(
    'trading.closed_trades',
    INTERVAL '7 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: trading.positions_snapshots
-- Periodic snapshots of open positions (for PnL tracking)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE trading.position_snapshots (
    snapshot_time       TIMESTAMPTZ     NOT NULL,
    position_id         UUID            NOT NULL,
    symbol              TEXT            NOT NULL,
    exchange            TEXT            NOT NULL,
    side                TEXT            NOT NULL,
    size                NUMERIC(28, 10) NOT NULL,
    entry_price         NUMERIC(28, 10) NOT NULL,
    current_price       NUMERIC(28, 10) NOT NULL,
    unrealized_pnl      NUMERIC(20, 8),
    unrealized_pnl_pct  NUMERIC(10, 6),
    stop_loss           NUMERIC(28, 10),
    take_profit         NUMERIC(28, 10),
    strategy_id         TEXT,
    PRIMARY KEY (snapshot_time, position_id)
);

SELECT create_hypertable(
    'trading.position_snapshots',
    'snapshot_time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'trading.position_snapshots',
    INTERVAL '1 year',
    if_not_exists => TRUE
);

-- =============================================================================
-- SCHEMA: risk
-- Risk metrics, alerts, and kill switch events
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: risk.metrics_snapshots
-- Periodic risk metric captures (VaR, drawdown, leverage, etc.)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE risk.metrics_snapshots (
    snapshot_time           TIMESTAMPTZ     NOT NULL,
    total_capital           NUMERIC(20, 4)  NOT NULL,
    available_capital       NUMERIC(20, 4)  NOT NULL,
    unrealized_pnl          NUMERIC(20, 4)  NOT NULL DEFAULT 0,
    daily_pnl               NUMERIC(20, 4)  NOT NULL DEFAULT 0,
    weekly_pnl              NUMERIC(20, 4),
    monthly_pnl             NUMERIC(20, 4),
    var_95_1d               NUMERIC(20, 4),
    var_99_1d               NUMERIC(20, 4),
    cvar_95_1d              NUMERIC(20, 4),
    daily_drawdown_pct      NUMERIC(8, 6)   NOT NULL DEFAULT 0,
    weekly_drawdown_pct     NUMERIC(8, 6),
    monthly_drawdown_pct    NUMERIC(8, 6),
    max_drawdown_pct        NUMERIC(8, 6),
    current_leverage        NUMERIC(6, 3)   NOT NULL DEFAULT 0,
    open_positions          INTEGER         NOT NULL DEFAULT 0,
    sharpe_90d              NUMERIC(8, 4),
    sortino_90d             NUMERIC(8, 4),
    effective_n             NUMERIC(6, 2),  -- Independent bets
    PRIMARY KEY (snapshot_time)
);

SELECT create_hypertable(
    'risk.metrics_snapshots',
    'snapshot_time',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'risk.metrics_snapshots',
    INTERVAL '3 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: risk.alerts
-- Immutable audit log of all risk alerts triggered
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE risk.alerts (
    alert_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    triggered_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    alert_type          TEXT            NOT NULL,
    risk_level          TEXT            NOT NULL,
    source_agent_id     INTEGER         NOT NULL,
    message             TEXT            NOT NULL,
    triggered_value     NUMERIC(20, 6)  NOT NULL,
    threshold_value     NUMERIC(20, 6)  NOT NULL,
    auto_action_taken   TEXT,
    acknowledged        BOOLEAN                  DEFAULT FALSE,
    acknowledged_at     TIMESTAMPTZ,
    PRIMARY KEY (alert_id, triggered_at)
);

SELECT create_hypertable(
    'risk.alerts',
    'triggered_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

-- Regulatory: keep alerts for 7 years
SELECT add_retention_policy(
    'risk.alerts',
    INTERVAL '7 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: risk.kill_switch_events
-- Kill switch trigger/resolution log
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE risk.kill_switch_events (
    event_id            UUID            NOT NULL DEFAULT gen_random_uuid(),
    triggered_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    triggered_by_agent  INTEGER         NOT NULL,
    trigger_reason      TEXT            NOT NULL,
    drawdown_pct        NUMERIC(8, 6)   NOT NULL,
    scope               TEXT            NOT NULL,  -- 'strategy','tier','system'
    positions_closed    INTEGER                  DEFAULT 0,
    capital_preserved   NUMERIC(20, 4),
    resolution_notes    TEXT,
    PRIMARY KEY (event_id, triggered_at)
);

SELECT create_hypertable(
    'risk.kill_switch_events',
    'triggered_at',
    chunk_time_interval => INTERVAL '1 year',
    if_not_exists => TRUE
);

-- =============================================================================
-- SCHEMA: agents
-- Agent health monitoring and message logs
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: agents.health_log
-- Periodic health checks from all 32 agents
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE agents.health_log (
    log_time            TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    agent_id            INTEGER         NOT NULL,
    agent_name          TEXT            NOT NULL,
    tier                INTEGER         NOT NULL,
    status              TEXT            NOT NULL,
    messages_processed  BIGINT                   DEFAULT 0,
    messages_failed     BIGINT                   DEFAULT 0,
    error_count         INTEGER                  DEFAULT 0,
    last_error          TEXT,
    latency_p50_ms      NUMERIC(10, 3),
    latency_p99_ms      NUMERIC(10, 3),
    memory_mb           NUMERIC(10, 2),
    cpu_pct             NUMERIC(6, 2),
    PRIMARY KEY (log_time, agent_id)
);

SELECT create_hypertable(
    'agents.health_log',
    'log_time',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'agents.health_log',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

-- =============================================================================
-- SCHEMA: intelligence
-- Signals, news, and on-chain data
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: intelligence.signals
-- All signals from Tier 2 and Tier 3 agents
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE intelligence.signals (
    signal_id       UUID            NOT NULL DEFAULT gen_random_uuid(),
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    signal_type     TEXT            NOT NULL,  -- 'technical','sentiment','macro','onchain','pattern','vol'
    source_agent    INTEGER         NOT NULL,
    symbol          TEXT,
    direction       TEXT,           -- 'BULLISH','BEARISH','NEUTRAL','STRONG_BULLISH','STRONG_BEARISH'
    confidence      NUMERIC(5, 4),
    expires_at      TIMESTAMPTZ,
    payload         JSONB           NOT NULL,
    PRIMARY KEY (signal_id, created_at)
);

SELECT create_hypertable(
    'intelligence.signals',
    'created_at',
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_signals_type_symbol
    ON intelligence.signals (signal_type, symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_signals_payload
    ON intelligence.signals USING GIN (payload);

SELECT add_retention_policy(
    'intelligence.signals',
    INTERVAL '1 year',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: intelligence.news_items
-- News articles after NLP processing
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE intelligence.news_items (
    news_id         UUID            NOT NULL DEFAULT gen_random_uuid(),
    published_at    TIMESTAMPTZ     NOT NULL,
    processed_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    headline        TEXT            NOT NULL,
    summary         TEXT,
    source          TEXT            NOT NULL,
    direction       TEXT,
    impact_score    NUMERIC(4, 2),  -- 1.0 to 10.0
    categories      TEXT[],
    entities        TEXT[],
    affected_syms   TEXT[],
    finbert_label   TEXT,
    finbert_conf    NUMERIC(5, 4),
    url             TEXT,
    PRIMARY KEY (news_id, published_at)
);

SELECT create_hypertable(
    'intelligence.news_items',
    'published_at',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

CREATE INDEX IF NOT EXISTS idx_news_affected
    ON intelligence.news_items USING GIN (affected_syms);

SELECT add_retention_policy(
    'intelligence.news_items',
    INTERVAL '2 years',
    if_not_exists => TRUE
);

-- =============================================================================
-- SCHEMA: performance
-- Strategy and portfolio performance metrics
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: performance.portfolio_snapshots
-- Hourly portfolio value snapshots for equity curve
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE performance.portfolio_snapshots (
    snapshot_time       TIMESTAMPTZ     NOT NULL,
    total_capital       NUMERIC(20, 4)  NOT NULL,
    available_capital   NUMERIC(20, 4)  NOT NULL,
    unrealized_pnl      NUMERIC(20, 4)  NOT NULL DEFAULT 0,
    realized_pnl_day    NUMERIC(20, 4)  NOT NULL DEFAULT 0,
    realized_pnl_total  NUMERIC(20, 4)  NOT NULL DEFAULT 0,
    open_positions      INTEGER         NOT NULL DEFAULT 0,
    exposure_pct        NUMERIC(8, 6),
    leverage            NUMERIC(6, 3),
    PRIMARY KEY (snapshot_time)
);

SELECT create_hypertable(
    'performance.portfolio_snapshots',
    'snapshot_time',
    chunk_time_interval => INTERVAL '1 month',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'performance.portfolio_snapshots',
    INTERVAL '10 years',
    if_not_exists => TRUE
);

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE: performance.strategy_metrics_daily
-- Daily strategy-level performance metrics
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE performance.strategy_metrics_daily (
    metric_date         DATE            NOT NULL,
    strategy_id         TEXT            NOT NULL,
    agent_id            INTEGER         NOT NULL,
    total_trades        INTEGER         NOT NULL DEFAULT 0,
    winning_trades      INTEGER         NOT NULL DEFAULT 0,
    losing_trades       INTEGER         NOT NULL DEFAULT 0,
    gross_pnl           NUMERIC(20, 8)  NOT NULL DEFAULT 0,
    total_fees          NUMERIC(20, 8)  NOT NULL DEFAULT 0,
    net_pnl             NUMERIC(20, 8)  NOT NULL DEFAULT 0,
    return_pct          NUMERIC(10, 6),
    sharpe_rolling_90d  NUMERIC(8, 4),
    max_drawdown_pct    NUMERIC(8, 6),
    win_rate_pct        NUMERIC(8, 6),
    profit_factor       NUMERIC(8, 4),
    capital_allocated   NUMERIC(20, 4),
    status              TEXT,
    PRIMARY KEY (metric_date, strategy_id)
);

-- =============================================================================
-- CONTINUOUS AGGREGATES (TimescaleDB-specific)
-- Pre-computed rollups for dashboard queries
-- =============================================================================

-- Hourly OHLCV from 1-minute bars (saves recomputing on every dashboard load)
CREATE MATERIALIZED VIEW market_data.ohlcv_1h
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time)    AS bucket,
    symbol,
    exchange,
    FIRST(open, time)              AS open,
    MAX(high)                      AS high,
    MIN(low)                       AS low,
    LAST(close, time)              AS close,
    SUM(volume)                    AS volume,
    SUM(quote_volume)              AS quote_volume,
    SUM(trade_count)               AS trade_count
FROM market_data.ohlcv_bars
WHERE timeframe = '1m'
GROUP BY bucket, symbol, exchange
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'market_data.ohlcv_1h',
    start_offset => INTERVAL '3 hours',
    end_offset   => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour',
    if_not_exists => TRUE
);

-- Daily OHLCV aggregate
CREATE MATERIALIZED VIEW market_data.ohlcv_1d
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 day', time)     AS bucket,
    symbol,
    exchange,
    FIRST(open, time)              AS open,
    MAX(high)                      AS high,
    MIN(low)                       AS low,
    LAST(close, time)              AS close,
    SUM(volume)                    AS volume
FROM market_data.ohlcv_bars
WHERE timeframe = '1h'
GROUP BY bucket, symbol, exchange
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'market_data.ohlcv_1d',
    start_offset => INTERVAL '2 days',
    end_offset   => INTERVAL '1 day',
    schedule_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- =============================================================================
-- GRANT PERMISSIONS
-- =============================================================================
GRANT USAGE ON SCHEMA market_data, trading, risk, agents, intelligence, defi, performance
    TO alghrest;

GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA
    market_data, trading, risk, agents, intelligence, defi, performance
    TO alghrest;

GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA
    market_data, trading, risk, agents, intelligence, defi, performance
    TO alghrest;

-- Future tables created will also be accessible
ALTER DEFAULT PRIVILEGES IN SCHEMA
    market_data, trading, risk, agents, intelligence, defi, performance
    GRANT ALL ON TABLES TO alghrest;

-- =============================================================================
-- STATUS CHECK
-- =============================================================================
DO $$
BEGIN
    RAISE NOTICE 'ALGHREST TimescaleDB initialization complete.';
    RAISE NOTICE 'Hypertables created: ohlcv_bars, order_book_snapshots, trade_proposals,';
    RAISE NOTICE '  orders, fills, closed_trades, position_snapshots, metrics_snapshots,';
    RAISE NOTICE '  alerts, kill_switch_events, health_log, signals, news_items,';
    RAISE NOTICE '  portfolio_snapshots, strategy_metrics_daily';
END $$;
