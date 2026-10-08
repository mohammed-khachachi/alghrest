# Durable fill, position, and cash accounting

`PortfolioAccountant` (agent 37, metrics port 9237) owns the production portfolio
projection. PostgreSQL stores the opening statement, permanent fill journal, and
cash/position projection. Redis is a recoverable cache, refreshed every five
seconds with a 15-second TTL. `SYSTEM_CAPITAL_USD` never funds this ledger.

## Installation and explicit opening balances

1. Apply `infra/migrations/001_accounting.sql` and then
   `infra/migrations/002_execution_recovery.sql`, then
   `infra/migrations/003_funding_performance.sql` to the configured PostgreSQL database
   using `psql -v ON_ERROR_STOP=1 -f infra/migrations/001_accounting.sql` with your
   usual database connection settings. Compose mounts this migration for **new**
   database volumes only; existing volumes need the explicit migration. No
   Timescale extension is required for these regular PostgreSQL tables.
2. Reconcile an exchange statement at a quiet cutoff, with all executions at or
   before that timestamp included. Prepare JSON like this (illustrative amounts):

   ```json
   {
     "as_of": "2026-01-01T00:00:00Z",
     "reference": "exchange-statement-2026-01-01",
     "cash": [
       {"exchange": "binance", "account_id": "default", "currency": "USD", "amount": "10000"}
     ],
     "positions": []
   }
   ```

   Existing positions require `exchange`, `account_id`, `symbol` (`BASE/QUOTE`),
   signed `quantity`, `average_cost` (quote currency per unit), `opened_at`, and
   optionally `strategy_id` / `agent_id`. Include holdings exactly once: a base
   asset represented as a position must not also be included as opening cash.
   Empty positions is an explicit assertion that no positions exist at cutoff.
   Quote balances include proceeds/costs of those opening holdings already.
3. Select `ENVIRONMENT` and `ACCOUNTING_BOOK` (default `main`). The durable book ID
   is `<environment>:<book>`; never share a Kafka/Redis deployment across operating
   environments. The Kafka consumer group is specific to that book.
4. Run `python -m scripts.accounting open opening.json` to validate, then append
   `--apply` to create it. A primary-key constraint refuses **every** reseed.
   A future cutoff is refused. Missing books prevent accountant startup.
5. Run the price publisher and
   `python run_agent.py agents.tier7_monitoring.portfolio_accountant PortfolioAccountant`,
   or the new `agent-portfolio-accountant` Compose service. Only one accountant
   may own a book; PostgreSQL holds its writer lease. Remove any dev seed process
   that writes `alghrest:portfolio:current` from a production deployment.

USD is the reporting currency. Other currencies need a fresh venue-specific
`CURRENCY/USD` quote. Stablecoins are **not** silently equated with USD. If your
valuation policy deliberately assumes parity, configure e.g.
`ACCOUNTING_USD_PEGS='["USDT"]'`; that policy will not detect depegs. With that
setting, `CURRENCY/USDT` can also convert other currencies. The default is `[]`.
The price publisher writes decimal marks to
`accounting:mark:<exchange>:<symbol>`, independently of its legacy mixed-venue
cache. `ACCOUNTING_MARK_MAX_AGE_SECONDS` defaults to 120. Missing, stale, invalid,
or future-dated marks withhold the portfolio rather than imply zero exposure.

## Processing and recovery guarantees

- The permanent fill identity is `(book, exchange, account, symbol, exchange_trade_id)`.
  CCXT now preserves the exchange trade ID and produces a stable `fill_id`.
  Internal UUID changes do not duplicate a trade. Different economics for an
  existing identity are an error; ingestion stops without acknowledging it.
- The journal insertion, native currency cash movements, position changes,
  realized P&L, and revision increment commit in **one PostgreSQL transaction**.
  A book-row lock serializes concurrent writers. Redis deduplication is not the
  accounting authority. PostgreSQL must use durable storage and normal durable
  commit settings; back up the `accounting` schema together, including `books`.
- Kafka acknowledges only the processed partition/offset after that transaction.
  A crash after commit but before Kafka acknowledgement safely replays the fill.
  Handler or commit failures end consumption; later offsets are not acknowledged.
- Startup consumes retained history from the earliest offset for a new group.
  Fills at/before the opening cutoff are journaled as `before_opening` without
  changing holdings. Legacy messages without exchange trade IDs at/before cutoff
  are durably archived by Kafka envelope `message_id` in
  `accounting.opening_covered_messages`; they never become fabricated trades.
  Legacy messages after cutoff stop ingestion for reconciliation.
  Snapshots are withheld until assigned Kafka partitions are
  caught up. A process crash expires the cache; normal shutdown deletes it.
- Fills received late rebuild the affected market's cost basis and realized P&L
  in `(execution timestamp, exchange trade ID)` order. This also defines the
  deterministic tie break for executions with identical timestamps. The common
  chronological path updates incrementally; late repair scales with that market's
  history. Exchange-specific sequence semantics may require a future adapter.
- Accounting stays active during a kill switch. A halt blocks opening risk;
  it cannot make outstanding executions disappear.
- The executor retains terminal/cancelled orders until fetched fills cover the
  exchange's reported executed quantity. Polling continues during a halt and
  retries failed fill publication; a successful placement is not repeated merely
  because its fill delivery failed. Orders, recovery cursors, and fill delivery
  are now durable; see [execution-recovery.md](execution-recovery.md).

Use `python -m scripts.accounting show` to inspect native durable state. A JSON
array of complete `Fill` contracts can be validated and replayed with
`python -m scripts.accounting import-fills fills.json`, then `--apply`. Each row
commits separately and the command is safe to retry after interruption. This is
the recovery path for reconciled exchange history, including external/manual
trades. Keep exchange trade IDs, account IDs, quantities, execution timestamps,
and full fees intact. Never fabricate trade IDs for legacy messages. An invalid
or conflicting Kafka record needs source reconciliation before ingestion resumes.

## Accounting conventions and boundaries

Positions net by exchange/account/market across strategies; mixed attribution is
reported as `mixed`. Same-direction fills use weighted average cost; partial
closes retain remaining cost basis; reversals realize the old position and open
the remainder at the new effective price. Negative inventory is recorded so
unexpected short exposure remains visible. This is **spot inventory accounting**,
not a derivative margin, funding, or contract-multiplier engine.

Quote fees enter cost basis/proceeds; base fees change net inventory. Third-token
fees debit native cash and are expensed immediately. Rebates are negative fees.
`fees` is authoritative when present, including an explicitly empty list; legacy
`fee`/`fee_currency` is accepted otherwise. Unknown fee data is not silently
normalized into zero by the CCXT adapter. Calculations use Decimal (50-digit
precision in the fill engine), without rounding to binary floats.

For compatibility, `Portfolio.total_capital` is cash plus signed position cost;
NAV is `total_capital + unrealized_pnl`. Position prices in the shared portfolio
are converted to USD; journal prices and stored cost basis stay in native quote
currency. `daily_pnl`/`weekly_pnl` are realized P&L since UTC day/Monday boundaries,
converted at current FX, excluding unrealized returns and historical FX
attribution. Short sale proceeds are conservatively collateralized in available
capital. Negative native cash balances remain visible; this is not a broker
buying-power or pending-order reservation calculation.

Non-USD cash that is not covered by an explicit peg policy also contributes its
absolute USD value to `cash_currency_exposure_usd` and total gross exposure. This
includes third-token fee liabilities; gross exposure is intentionally not netted
against related positions. Per-symbol risk rules still need to interpret native
cash balances if they enforce currency concentration limits.

The ledger guarantees exactly-once application of **received** exchange fills.
Durable exchange-order recovery, paginated trade history, balance reconciliation,
and paper execution are described in [execution-recovery.md](execution-recovery.md).
New risk requires fresh matching reconciliation, valuation and performance evidence.
Explicit new USDT paper deposits are supported as described below. Withdrawals,
transfers, live funding and corporate actions remain unsupported; investigate
and reconcile those movements explicitly. Pending-order reservations remain a
separate feature; the executor conservatively allows only one unresolved order
per book. Stable fills recovered by the executor are tagged with their accounting
book. Untagged post-opening Kafka fills stop ingestion for source reconciliation.

## Tests

Focused checks (explicit configuration avoids `tests/pytest.ini` overriding the
root project's settings):

```powershell
python -m pytest -c pyproject.toml -o addopts='' tests/unit/test_accounting.py tests/unit/test_accounting_pipeline.py tests/unit/test_exchange_executor.py tests/unit/test_price_publisher.py tests/unit/test_models.py
$env:ACCOUNTING_TEST_DATABASE_URL = 'postgresql://test_user:test_password@127.0.0.1:5432/disposable_test_db'
python -m pytest -c pyproject.toml -o addopts='' tests/integration/test_accounting_postgres.py
$env:ACCOUNTING_TEST_REDIS_URL = 'redis://127.0.0.1:6379/15'
python -m pytest -c pyproject.toml -o addopts='' tests/integration/test_accounting_redis.py
```

Use a **disposable** database: these integration tests install the schema and
create/delete isolated test books. They exercise concurrent duplicates, rollback
after journal insertion, restart/replay, conflicting payloads, opening cutoffs,
late fills, and writer exclusion. They do not require running trading agents or
an exchange connection. The repository-wide 70% coverage gate remains unchanged;
these focused commands deliberately do not claim whole-repository coverage.

## Explicit paper deposits

Apply all three migrations in order, including
`infra/migrations/003_funding_performance.sql`. On the dedicated local paper stack,
`python -m scripts.paper provision` installs them without funding the book. Existing
openings and fills are retained. Upgrade the accountant, executor, tracker and risk
services together; older executors do not understand the performance readiness gate.

For each **new** contribution create a JSON file with a stable, unique reference:

```json
{
  "exchange": "binance",
  "account_id": "default",
  "currency": "USDT",
  "amount": "150",
  "reference": "monthly-contribution-2026-10"
}
```

```powershell
python -m scripts.paper deposit deposit.json          # full validation; no writes
python -m scripts.paper deposit deposit.json --apply  # explicitly record this contribution
```

This command supports positive USDT deposits into an explicitly configured
`paper_trading` account. It changes simulated balances only. There is no recurring
credit, withdrawal, transfer, live-exchange operation, or historical deposit replay.
The effective timestamp is generated in UTC during registration; date/time fields
in input are rejected. The monthly plan is an intent, not a deposit instruction.
Do not apply the example unless that contribution is intended now.

The receipt records the book, account, reference, timestamp, new revision, before/
after native cash, USD value, unit price, and units issued. A dry-run receipt has
`applied: false` and a projected revision/time; only the applied receipt is durable.
After a lost response, rerun the **same reference and amount**, including `--apply`.
Identical retries return the original receipt, even if prices have since expired.
Reusing the reference with different economics fails. References are unique per
book, exchange and account. Never choose a new reference simply to retry an error.

A PostgreSQL transaction locks the book then its paper accounts, checks for
unsettled fills, pending/uncertain orders and any native balance mismatch, values
the portfolio using fresh marks, and commits the deposit journal, ledger cash,
paper cash, performance units, and book revision together. New order preparation
uses the same book lock. Deposits are never fabricated as fills or opening imports.

Every committed deposit sets durable execution readiness to false and invalidates
Redis snapshots/reconciliation. A Redis outage cannot reverse or duplicate the
committed cash: the command logs a cache-invalidation warning and returns the
committed receipt. The executor's PostgreSQL revision gate still rejects old
readiness evidence. The accountant and recovery coordinator must publish fresh,
matching snapshots before new orders are allowed. No deposit clears the kill
switch or resumes a paused strategy.

## Performance independent of contributions

`accounting.performance` stores one durable unitized index per book, including
units, current/peak unit price, UTC day/week/month references and up to 366 UTC
daily observations. The accountant updates it under the book lock, including while
trading is halted. Redis and the tracker hold rebuildable caches only; legacy
unscoped raw-NAV Redis peaks are never imported.

The reporting identity is:

```text
NAV = total_capital + unrealized_pnl
unit_price = marked NAV / outstanding units
new units = deposit USD value / immediately preceding unit_price
```

For example, a 150 USD portfolio with 150 units starts at unit price 1. After a
15 USD trading loss its unit price is 0.9 and drawdown is 10%. Adding 150 USD
issues 166.666… units; NAV becomes 285 USD, while unit price remains 0.9 and
peak drawdown remains 10%. Native available cash and reserve amounts increase;
realized daily/weekly P&L does not include the contribution. USDT is converted
using a fresh USDT/USD mark unless an explicit peg policy has been configured;
it is never implicitly valued at one dollar.

Initialization is allowed only for a positive-valued, revision-zero book before
trading. A previously traded book without verified performance history is blocked;
it needs a separately reviewed historical reconstruction, not an automatic
baseline reset. Missing, stale, foreign-book or wrong-revision performance blocks
readiness. `preflight` includes `durable_performance` and snapshot/reconciliation
checks to distinguish these conditions.

Risk Governor, RiskEngine and PortfolioTracker use the same unitized index for
period losses and peak drawdown, preserving the existing 3%/5% daily, 7% weekly,
12% monthly thresholds and the 25% lifetime drawdown breaker. Periods start at UTC
midnight, Monday and month start; their reference is the last observed unit price
from the previous period. Gaps carry the last reference across restart rather than
resetting to the newly observed NAV. Missing exact boundary prices remain an
observation limitation, not synthetic market data.

Daily Sharpe/Sortino use completed UTC days only, at least 20 returns and the last
90 calendar days. Multi-day gaps are omitted from daily samples. Annualization
uses 365.25 for this crypto paper portfolio; Sharpe uses sample standard deviation,
and Sortino uses the root mean square of negative excess returns across all days.
The tracker reports unavailable estimates as null. No performance monitoring
process writes or edits the cash journal.
