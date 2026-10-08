-- Shared, atomic daily reservations survive worker restarts and Redis eviction.
CREATE SCHEMA IF NOT EXISTS ai;
CREATE TABLE IF NOT EXISTS ai.daily_budget (
    scope text NOT NULL,
    day date NOT NULL,
    calls integer NOT NULL CHECK (calls >= 0),
    reserved_usd numeric(18,8) NOT NULL CHECK (reserved_usd >= 0),
    PRIMARY KEY (scope, day)
);
