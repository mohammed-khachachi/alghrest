BEGIN;
-- Additive: opening balances and all existing fill journals remain immutable.
CREATE TABLE IF NOT EXISTS accounting.performance (
    book_id TEXT PRIMARY KEY REFERENCES accounting.books(book_id) ON DELETE CASCADE,
    state JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS accounting.deposits (
    book_id TEXT NOT NULL REFERENCES accounting.books(book_id) ON DELETE CASCADE,
    exchange TEXT NOT NULL,
    account_id TEXT NOT NULL,
    reference TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    receipt JSONB NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (book_id, exchange, account_id, reference)
);
COMMIT;
