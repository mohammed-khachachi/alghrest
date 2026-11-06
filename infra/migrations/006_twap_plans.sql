BEGIN;
CREATE TABLE IF NOT EXISTS execution.plans (
    book_id TEXT NOT NULL REFERENCES execution.books(book_id),
    parent_id UUID NOT NULL,
    fingerprint TEXT NOT NULL,
    request JSONB NOT NULL,
    slices INTEGER NOT NULL CHECK (slices BETWEEN 1 AND 1000),
    next_slice INTEGER NOT NULL DEFAULT 0,
    allocated NUMERIC NOT NULL DEFAULT 0,
    next_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','complete','blocked')),
    reason TEXT,
    PRIMARY KEY(book_id,parent_id)
);
CREATE TABLE IF NOT EXISTS execution.slices (
    book_id TEXT NOT NULL,
    parent_id UUID NOT NULL,
    slice INTEGER NOT NULL,
    client_order_id UUID NOT NULL,
    request JSONB NOT NULL,
    PRIMARY KEY(book_id,parent_id,slice),
    UNIQUE(book_id,client_order_id),
    FOREIGN KEY(book_id,parent_id) REFERENCES execution.plans(book_id,parent_id)
);
COMMIT;
