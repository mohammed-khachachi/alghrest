BEGIN;
CREATE TABLE IF NOT EXISTS execution.authorizations (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    proposal_id UUID NOT NULL,
    authorization_id UUID NOT NULL,
    decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED')),
    proposal JSONB NOT NULL,
    proposal_hash TEXT NOT NULL,
    review JSONB NOT NULL,
    approved_revision BIGINT,
    root_request JSONB,
    root_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(book_id,proposal_id),
    UNIQUE(book_id,authorization_id)
);
CREATE TABLE IF NOT EXISTS execution.authorization_denials (
    id BIGSERIAL PRIMARY KEY,
    book_id TEXT NOT NULL,
    proposal_id UUID,
    client_order_id UUID,
    reason TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMIT;
