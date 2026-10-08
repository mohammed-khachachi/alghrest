# Durable execution recovery and paper setup

The executor journals intent **before** invoking a venue. PostgreSQL owns order
identity, recovery cursors, recovered fills, and the delivery outbox. Redis only
caches a short-lived reconciliation result. Restarting either process does not
reset balances, forget pending orders, or authorize another submission.

## Prepare an explicit paper book

### Isolated local infrastructure

`docker-compose.paper.yml` runs PostgreSQL 16, Redis 7 and a single Kafka broker
for local paper use. It uses its own named volumes and only publishes loopback
ports: PostgreSQL `15432`, Redis `16379`, Kafka `19092`. It does not start agents
or fund a portfolio. This is a local development topology, not the production
three-broker cluster. The regular ledger tables do not require TimescaleDB.

Use a gitignored `.env` configured for that stack, with generated local
database/Redis passwords and `ENVIRONMENT=paper_trading`. Set execution scope
only from an explicit account manifest. The local `.venv` contains the runtime
dependencies, including Kafka's LZ4 extra.

```powershell
docker compose -f docker-compose.paper.yml up -d
.\.venv\Scripts\Activate.ps1
python -m scripts.paper provision
python -m scripts.paper preflight
```

On Linux, activate with `source .venv/bin/activate`. `provision` applies both
migrations and creates the 18 required topics; it never creates opening balances.
It refuses endpoints outside the dedicated local paper profile. The single-broker
topics use replication/minimum in-sync replicas of one and seven-day retention.
`preflight` checks the actual database, account configuration, Kafka topics,
Redis, fresh portfolio/reconciliation and kill switch. It returns exit code 1
until every activation requirement passes. A healthy infrastructure is not an
active portfolio.

To stop this local infrastructure without deleting its data:

```powershell
docker compose -f docker-compose.paper.yml stop
```

Do not mix `docker-compose.paper.yml` with the main Compose file; they are
separate deployments. This local profile runs the agents on the host, where the
`.env` loopback connection addresses apply.

### Opening statement and account scope

An actual opening statement and account scope are required. No setting, including
`SYSTEM_CAPITAL_USD`, supplies missing opening balances. See [accounting.md](accounting.md)
for the opening JSON contract. Include native cash, existing positions, a UTC
cutoff and a statement reference. Do not double-count a position's base inventory
as cash. Use a quiet cutoff covering all prior fills on the input stream.

Create a separate `accounts.json` with the venues, credential/account labels and
**all spot markets to reconcile**, for example this scope (no funding amounts):

```json
[{"exchange":"binance","account_id":"default","symbols":["BTC/USDT","ETH/USDT"]}]
```

One account per exchange is supported because the current settings expose one
credential pair per exchange. Scope is immutable once attached to a book. Use
dedicated accounts for live operation; external/manual fills within the scope
are recovered too. Kraken scans account-wide spot history. Binance, Bybit and
Coinbase use the explicitly enumerated markets. Unknown open orders anywhere in
the account block readiness.

Run with your configured PostgreSQL connection. PowerShell:

```powershell
$env:ENVIRONMENT = 'paper_trading'
$env:ACCOUNTING_BOOK = 'paper-main'
$env:EXECUTION_ACCOUNTS = Get-Content -Raw accounts.json
python -m scripts.paper prepare opening.json accounts.json
python -m scripts.paper prepare opening.json accounts.json --apply
```

The dry run validates both files without connecting to a database. `--apply`
installs `001_accounting.sql` and `002_execution_recovery.sql`, imports the opening
once, and initializes the separate simulated venue balances from that opening.
Repeating this command with identical inputs preserves the current balances;
different opening data is refused. It refuses to prepare a book owned by a running
executor. It leaves the trading gate closed.

Start the following processes with the same environment, book, account scope,
database, Redis and Kafka settings:

```powershell
python run_agent.py agents.tier7_monitoring.portfolio_accountant PortfolioAccountant
python run_agent.py agents.tier5_execution.exchange_executor ExchangeExecutor
python run_agent.py agents.tier2_intelligence.price_publisher PricePublisher
```

Run them in separate terminals or as their corresponding Compose services. The
price publisher needs the market-data feed on `prices.realtime`; it does not
fetch quotes by itself. Kafka topics must already be provisioned. Compose mounts
both migrations for new database volumes; existing databases require migration
or the preparation command. Executor and accountant Compose services explicitly
use the internal database, Redis and Kafka addresses. Supply `ENVIRONMENT`,
`ACCOUNTING_BOOK` and `EXECUTION_ACCOUNTS` to their runtime environment; host shell
variables alone do not override an existing Compose service's `.env` file.

Keep paper and live Kafka/Redis deployments separate. Never start the entire
trading stack just to prepare a book. Do not start strategies until the accountant
has caught up and published a fresh, valued portfolio and reconciliation is ready.
Missing non-USD conversion marks block valuation; an optional USD peg policy must
be explicit, as described in [accounting.md](accounting.md).

```powershell
python -m scripts.paper status
python -m scripts.accounting show
```

The status command displays the last report and its check time, native ledger
revision, and unresolved orders; a stored historical `ready` value is not a fresh
authorization. The execution path independently checks expiry and revision.

## What recovery guarantees

* Each client order ID claims one durable intent. Reusing it with different
  economics is an error. Submission and recovery share a lock; a database writer
  lease excludes a second executor for the same book.
* A create request is sent once. A timeout or crash makes submission uncertain.
  Recovery looks up its exchange ID or client ID. A “not found” response is **not**
  proof that it is safe to create again. Unresolved intent blocks trading and
  requires operator investigation of venue records. There is no automatic reset,
  override-to-ready command, or blind resubmission.
* History pages, their fill events and the next cursor commit in one transaction.
  Failed transactions leave the old checkpoint. Duplicate pages are harmless;
  changing economics for an existing trade identity block recovery.
* Binance subdivides saturated time windows, failing closed on an unprovable
  single-millisecond page. Bybit and Coinbase follow native cursors. Kraken uses
  offsets and the unfiltered server count. Repeated/cyclic cursors block recovery.
* Scans overlap the previous checkpoint by one day by default and rescan from the
  explicit opening cutoff daily, recovering delayed executions outside that
  overlap. The default budget is 30 pages per market per pass; larger backlogs
  remain blocked and resume from their durable cursor. Large histories can cause
  extended reconciliation outages. Scan coverage must be recent to authorize risk.
* The outbox retries failed or ambiguous Kafka publication. Even an acknowledged
  fill is redelivered while absent from the accounting journal, including after
  Kafka retention expires. The ledger applies each stable trade identity once.
  Recovered events carry a book ID; foreign-book fills are ignored by its accountant.
* Closed/cancelled orders remain unresolved until their reported executed quantity
  is backed by recovered fills. Cancellation intent persists before the API call;
  failed cancels retry, including during a kill switch. History scans and accounting
  continue during a halt. The halt itself remains an independent execution guard.

## Reconciliation and limits

Reconciliation compares exchange native balances against ledger cash **plus signed
base inventory** across markets. It preserves unexpected assets and negative
balances. Differences, missing balances, changing balances during the scan, active
or uncertain orders, stale history, and unsettled recovered fills all block new
risk. Tolerances are zero by default; `EXECUTION_BALANCE_TOLERANCES` is an explicit
JSON currency-to-absolute-amount policy and must be finite and nonnegative.

The database gate checks the current ledger revision and a 30-second expiry inside
the order-claim transaction. The Redis gate also requires a portfolio snapshot no
older than 15 seconds with the same book and revision. Proposal approval checks
that cache gate; execution rechecks both. Every claimed submission closes the gate.
This deliberately permits **one unresolved order per book**, rather than offering
a pending-order reservation/buying-power model. Proposals/orders arriving while
blocked are rejected; they are not queued indefinitely or replayed with a new ID.

Development and paper environments use the persistent simulated venue, with no
private exchange API calls. Market and crossing limit orders fill completely at a
fresh venue mark, with quote-currency fees (`PAPER_FEE_BPS`, default 10). Non-crossing
limits remain open across restarts. Borrowed starting assets and overspending are
refused. This model does not simulate order-book depth, partial liquidity, latency,
or realistic slippage. Live connector writes independently require `ENVIRONMENT=live`;
configured Binance/Bybit testnets use sandbox URLs.

These are spot adapters, not derivatives/margin accounting. Deposits, withdrawals,
transfers, funding and corporate actions still require explicit reconciliation;
balance drift is reported, never repaired by inventing a fill or reseeding. Venue
history retention, API semantics and external account activity bound what can be
proved. A balance match cannot prove that an omitted round trip never occurred.
Use complete statement-backed openings, account scopes and history imports; if
the API cannot supply needed history, investigate/import records before enabling
risk. The changes have isolated automated tests, not live exchange certification.

Pagination references: [Binance account API](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-src/api/account),
[Bybit executions](https://bybit-exchange.github.io/docs/v5/order/execution),
[Coinbase fills](https://docs.cdp.coinbase.com/api-reference/advanced-trade-src/api/rest-src/api/orders/list-fills),
[Kraken trades history](https://docs.kraken.com/api-reference/account-data/get-trades-history).

## Verification

```powershell
python -m pytest -c pyproject.toml -o addopts='' tests/unit/test_execution_adapters.py tests/unit/test_exchange_executor.py tests/unit/test_kill_switch_cancel.py tests/unit/test_paper_setup.py
$env:ACCOUNTING_TEST_DATABASE_URL = 'postgresql://test_user:test_password@127.0.0.1:5432/disposable_test_db'
$env:ACCOUNTING_TEST_REDIS_URL = 'redis://127.0.0.1:6379/15'
python -m pytest -c pyproject.toml -o addopts='' tests/integration/test_execution_recovery.py tests/integration/test_accounting_postgres.py tests/integration/test_accounting_redis.py
```

Integration tests use real PostgreSQL transactions and Redis, synthetic explicit
openings, a persistent paper venue and controlled exchange/Kafka doubles. They
exercise lost responses, concurrent claims, rollback, restart, cursor pagination,
outbox retries, delayed fills, cancellation failures, balance drift, stale gates
and idempotent paper preparation. They do not connect to a live exchange or claim
an end-to-end production Kafka deployment test. An additional opt-in test uses
the real local paper Kafka broker, PostgreSQL and Redis to prove replay after a
failure between database commit and Kafka acknowledgement:

```powershell
$env:PAPER_RUNTIME_TESTS = '1'
python -m pytest -c pyproject.toml -o addopts='' tests/integration/test_paper_runtime.py
```

It creates a unique synthetic test book and topic, uses Redis DB 15, then removes
its records and topic. It never sends events to the runtime order/fill topics or
seeds the user's book. The repository coverage gate is unchanged; these commands
select the affected behavior explicitly.

## Funding and performance readiness

Apply migration `003_funding_performance.sql` after `001` and `002`, including on
existing volumes. Execution now requires fresh durable performance at the current
ledger revision as well as balance/history reconciliation. A deposit atomically
blocks readiness; accounting and recovery restore it only after fresh evidence.
See [paper deposit and unitized performance procedures](accounting.md#explicit-paper-deposits).

## Supervised local paper pipeline

For the dedicated Linux paper stack, after explicit opening-balance import:

```bash
python -m scripts.paper_services start
python -m scripts.paper_services status
python -m scripts.paper preflight
python -m scripts.paper_services stop
```

This supervisor uses Linux process identities and a file lock. It starts only
PaperMarketFeed, PortfolioAccountant, ExchangeExecutor, RiskGovernor,
PortfolioTracker, ProposalApprover and OrderRouter. It does not start strategies,
CIO, LLM calls or Telegram. Logs and the owned-process manifest are under
`artifacts/paper-runtime/`. Run one supervisor against a book. A child exit stops
the others and blocks execution readiness; it is not an automatic restart loop.
Stopping sends SIGINT for graceful resource cleanup, then blocks the book.
On restart, normal durable recovery and fresh valuation must re-establish readiness.

Agent 38 obtains public Binance spot marks and a timestamped Coinbase USDT/USD
conversion; stablecoins are not silently valued at one dollar. Marks expire and
missing conversion data blocks readiness. The optional `paper-feed` profile in
the main compose file adds this agent for that separate deployment topology.
Do not run the local supervisor and a container copy against the same book.

The 2026-09-28 activation readback confirmed the runtime book retained 150 USDT,
revision 0, no positions/fills/deposits. It also verified readiness turns false
on stop and returns true after recovery. The buy/sell/replay test uses a distinct
synthetic test book; no test trade is inserted in `paper-main`. Monthly funding
still requires an explicit deposit import.
