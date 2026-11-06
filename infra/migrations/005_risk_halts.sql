BEGIN;
CREATE SCHEMA IF NOT EXISTS safety;
CREATE TABLE IF NOT EXISTS safety.halts (
    book_id TEXT PRIMARY KEY,
    active BOOLEAN NOT NULL,
    generation BIGINT NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS safety.halt_events (
    id BIGSERIAL PRIMARY KEY,
    book_id TEXT NOT NULL,
    generation BIGINT NOT NULL,
    active BOOLEAN NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Existing books require explicit review/reset; never infer that an old book
-- with no persistent halt record is safe. No order/fill history is rewritten.
INSERT INTO safety.halts(book_id,active,reason)
SELECT book_id,true,'risk-state migration requires operator review'
FROM execution.books ON CONFLICT DO NOTHING;
COMMIT;
