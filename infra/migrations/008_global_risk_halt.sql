BEGIN;
-- Existing execution installations require explicit global operator review.
-- A fresh, empty paper installation starts without a global restriction.
INSERT INTO safety.halts(book_id,active,reason)
SELECT '__alghrest_global__',EXISTS(SELECT 1 FROM execution.books),
       'global risk authority initialization; review existing execution books'
ON CONFLICT DO NOTHING;
UPDATE execution.plans SET state='blocked',reason='legacy plan requires durable authorization review'
WHERE state='active' AND request->>'authorization_id' IS NULL;
COMMIT;
