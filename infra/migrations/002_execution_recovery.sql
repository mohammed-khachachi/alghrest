BEGIN;
CREATE SCHEMA IF NOT EXISTS execution;
CREATE TABLE IF NOT EXISTS execution.books (
    book_id TEXT PRIMARY KEY REFERENCES accounting.books(book_id),
    accounts JSONB NOT NULL,
    ready BOOLEAN NOT NULL DEFAULT false,
    verified_revision BIGINT,
    verified_until TIMESTAMPTZ,
    report JSONB NOT NULL DEFAULT '{"reason":"not reconciled"}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS execution.orders (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    client_order_id UUID NOT NULL,
    exchange TEXT NOT NULL,
    account_id TEXT NOT NULL,
    exchange_order_id TEXT,
    fingerprint TEXT NOT NULL,
    request JSONB NOT NULL,
    current_order JSONB NOT NULL,
    phase TEXT NOT NULL CHECK (phase IN ('submitting','uncertain','working','complete','rejected')),
    cancel_requested BOOLEAN NOT NULL DEFAULT false,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(book_id,client_order_id),
    UNIQUE(book_id,exchange,account_id,exchange_order_id)
);
CREATE TABLE IF NOT EXISTS execution.cursors (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    exchange TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    version BIGINT NOT NULL DEFAULT 0,
    cursor JSONB,
    through_ms BIGINT NOT NULL DEFAULT 0,
    last_full_ms BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY(book_id,exchange,account_id,symbol)
);
CREATE TABLE IF NOT EXISTS execution.fills (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    exchange TEXT NOT NULL, account_id TEXT NOT NULL, symbol TEXT NOT NULL, trade_id TEXT NOT NULL,
    exchange_order_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL, payload JSONB NOT NULL,
    PRIMARY KEY(book_id,exchange,account_id,symbol,trade_id)
);
CREATE INDEX IF NOT EXISTS execution_order_fills
    ON execution.fills(book_id,exchange,account_id,exchange_order_id);
CREATE TABLE IF NOT EXISTS execution.outbox (
    id BIGSERIAL PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    event_key TEXT NOT NULL, topic TEXT NOT NULL, message_type TEXT NOT NULL,
    payload JSONB NOT NULL, delivered_at TIMESTAMPTZ,
    UNIQUE(book_id,event_key)
);
CREATE INDEX IF NOT EXISTS execution_pending_outbox ON execution.outbox(book_id,id)
    WHERE delivered_at IS NULL;
-- Independent simulated venue state: never rebuilt from the changing ledger.
CREATE TABLE IF NOT EXISTS execution.paper_accounts (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    exchange TEXT NOT NULL, account_id TEXT NOT NULL,
    balances JSONB NOT NULL,
    PRIMARY KEY(book_id,exchange,account_id)
);
CREATE TABLE IF NOT EXISTS execution.paper_orders (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    client_order_id UUID NOT NULL, payload JSONB NOT NULL,
    PRIMARY KEY(book_id,client_order_id)
);
CREATE TABLE IF NOT EXISTS execution.paper_fills (
    sequence BIGSERIAL PRIMARY KEY,
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    exchange TEXT NOT NULL, account_id TEXT NOT NULL, symbol TEXT NOT NULL,
    payload JSONB NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS paper_fill_identity
    ON execution.paper_fills(book_id,exchange,account_id,symbol,(payload->>'exchange_trade_id'));
COMMIT;
