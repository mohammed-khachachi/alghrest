-- Regular PostgreSQL tables: uniqueness must not depend on a hypertable timestamp.
BEGIN;
CREATE SCHEMA IF NOT EXISTS accounting;
CREATE TABLE IF NOT EXISTS accounting.books (
    book_id TEXT PRIMARY KEY,
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    opening JSONB NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS accounting.fills (
    book_id TEXT NOT NULL REFERENCES accounting.books(book_id),
    exchange TEXT NOT NULL,
    account_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    trade_id TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    fingerprint TEXT NOT NULL,
    payload JSONB NOT NULL,
    realized JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('applied', 'before_opening')),
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (book_id, exchange, account_id, symbol, trade_id)
);
CREATE INDEX IF NOT EXISTS accounting_fill_replay
    ON accounting.fills (book_id, exchange, account_id, symbol, occurred_at, trade_id);
CREATE INDEX IF NOT EXISTS accounting_fill_pnl
    ON accounting.fills (book_id, occurred_at) WHERE status = 'applied';
CREATE TABLE IF NOT EXISTS accounting.opening_covered_messages (
    book_id TEXT NOT NULL REFERENCES accounting.books(book_id),
    message_id UUID NOT NULL,
    payload JSONB NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (book_id, message_id)
);
COMMIT;
