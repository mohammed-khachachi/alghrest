# Isolated deployment and recovery soak

This Linux/WSL harness runs the execution/accounting core against three Confluent
7.6.1 Kafka brokers, ZooKeeper, TimescaleDB, Redis and Prometheus. Six real agent
processes and the production API run on the host. It uses synthetic SOL prices
and a separate, explicit 150 USDT test opening balance. It does not validate
strategy profitability, external market feeds, the dashboard, or all 37 services.

## Operation

From the repository root, with the full Python environment and Docker available:

```bash
.venv/bin/python -m scripts.deployment_soak prepare
.venv/bin/python -m scripts.deployment_soak start --hours 24
.venv/bin/python -m scripts.deployment_soak status
# To end the experiment early:
.venv/bin/python -m scripts.deployment_soak stop
```

On a systemd desktop, use `start --hours 24 --inhibit-sleep` to hold a temporary
idle/sleep inhibitor for the actual worker lifetime, including recovery drills
and cleanup. No permanent power settings change. An unavailable inhibitor fails
startup rather than silently running without the requested protection. Keep the
machine powered and its lid open; explicit shutdown is not inhibited.

`prepare` stages configuration under `artifacts/deployment-soak`, with independent
credentials. Repeating it preserves credentials and the test book, and is refused
while the owned worker is running. Restarting the workload resumes the durable
test book without reseeding it; the 24-hour clock starts again after recovery
drills. Keep the machine awake for the whole experiment. A measurement gap over
five minutes invalidates continuity.

The `alghrest-soak` Compose project uses its own network and volumes. All exposed
ports bind to loopback: PostgreSQL 25432, Redis 26379, Kafka 29092–29094, API 28000,
Prometheus 29090, and agent metrics 19200 plus agent ID. External exchange,
Telegram and Anthropic credentials are not inherited. DeFi remains disabled and
the AI budget is zero. The existing `alghrest-paper` project is not modified.

The worker stops its own services on completion, interruption, or failure and
retains durable volumes and evidence. It never removes volumes automatically.
Do not copy the synthetic opening balance into the real paper portfolio.

## Evidence and acceptance

- `status.json`: current phase, process identities, completed recovery checks,
  ledger revision, cash, position, start/deadline, errors and latest sample.
- `samples.jsonl`: resource measurements, consumer lag and order latency every
  approximately two minutes during the soak.
- Individual process logs, `runner.log`, and `compose-error.log`: diagnostics.

Before the timed soak, the harness checks authenticated HTTP/WebSocket access,
all seven Prometheus targets, three Kafka replicas in sync, rejection of anonymous
and wrong-password Kafka clients, and rejection of the old database password.
It kills and restarts the accountant while replaying twenty duplicate fills,
executes an order with one broker down, then restarts the database, cache, agents
and API. Every trade checks durable order/fill/revision counts and exact cash and
position conservation, including fees. Trading must remain blocked until the
accountant reconciles after restart.

A pass requires `phase=completed`, no errors, all recovery checks, and a continuous
24-hour observation window. `starting` and `recovery_drills` do not count toward
that window. `soaking` means the experiment is still running. Never infer success
from elapsed wall time alone or from an abandoned status file.

Containers have memory limits; host processes are measured and the worker stops
if available host memory falls below 512 MiB. Kafka consumer lag above 100 after
a settled cycle fails the experiment. Container CPU percentages and host process
cumulative CPU seconds are different measures; use sample deltas for host CPU.
There is no predeclared latency performance target, so report observed latency
without claiming a speed improvement over an unmeasured baseline.

## Deployment issues found during initial execution

1. Corrected Kafka's broker setting to `KAFKA_MIN_INSYNC_REPLICAS`; the previous
   spelling did not configure the intended broker default.
2. Expanded the daily Timescale aggregate refresh policy from a one-day window
   to two days (`start_offset=3 days`, `end_offset=1 day`), allowing initialization
   to finish. Existing databases require a separately reviewed policy migration;
   changing the initialization file only affects fresh databases.
3. Staged bind mounts use a shared SELinux label in the isolated harness. Source
   repository files are not relabelled.
4. The harness starts ZooKeeper first and lets old sessions expire before broker
   startup. Brokers get 60 seconds to stop, and are stopped before ZooKeeper.
5. A broker outage triggered a native `librdkafka` assertion inside the API's
   monitoring collector. The collector now uses `aiokafka`, awaits client cleanup,
   and discovers actual application consumer groups instead of a stale hardcoded
   list. Outage/recovery and cancellation have regression tests. The native crash
   is recorded in the initial `API.log`; it was not a ledger corruption.

An additional strict MyPy pass over `src/api/` (outside the configured CI type
scope) exposed 36 existing annotation errors in four API files. The required
agents/core/backtesting and advisory connector/API type scope is checked separately. Do not
describe this as a repository-wide strict typing pass.

The full quality run after the proposal-rejection fix passed 716 tests
with one optional test skipped and 77.43% coverage; the 70% gate was retained.
The configured strict MyPy command passed for 102 source files. Ruff and the
architecture boundary checks passed, along with formatting checks for changed files.
See `artifacts/quality/deployment-tests.txt` and `deployment-coverage.json`.
This test result does not establish completion of the 24-hour deployment soak.

## 1 October timeout diagnosis and correction

The run starting at 01:29:54 UTC stopped after 137 timed cycles. Read-only inspection
found all 308 durable execution orders complete, with no pending or rejected
execution records. Kafka retained a BUY proposal at 06:56:15.449 UTC, followed
four milliseconds later by `ProposalRejected`: portfolio exchange reconciliation
was unavailable or disagreed. There was no matching approved proposal or pending
order. The harness nevertheless waited 60 seconds for a fill and recorded an
empty `TimeoutError`. Evidence is in `artifacts/deployment-soak/last-events-20261001.json`.

The approval agent now caches rejection reviews with their proposal IDs, as it
already did for approvals. Cached terminal decisions prevent a redelivered
rejected proposal from later being approved. Approval decisions are cached before
publication; uncertain publication is not automatically repeated. This is a
bounded Redis decision cache, not a replacement for durable execution/accounting.

The soak checks the correlated review while awaiting a fill. Only the two known
temporary portfolio-evidence rejection reasons can be retried, with at most three
attempts separated by five seconds and a new readiness check. A retry additionally
requires the expected unchanged ledger revision and no execution record for the
rejected proposal. Every retry uses a fresh proposal ID and traverses the normal
risk gates. Risk-limit rejections, existing execution records, identity mismatch,
missing reviews and ambiguous timeouts fail the test. Retry events remain visible
in `transient_rejections`; failure records include the operation and proposal ID.
No risk threshold or 24-hour continuity requirement is relaxed.

## 5 October shared writer-lease correction

The preserved pre-fix Ledger and ExecutionStore both reproduced the recorded
asyncpg `InterfaceError` using 100 simultaneous writer checks against the local
paper PostgreSQL service: 99 calls failed from overlapping operations on each
shared lease connection. This reproduction used only SELECT queries and random
session advisory locks, without changing financial records.

Each store now serializes lease claim/check/close operations with an asyncio
mutex. Failed or cancelled claims release their session, and repeated claims
cannot replace a held lease. Fill transactions and book-row locking retain their
existing behavior; the mutex covers only the shared lease session.

Twenty fault-injection unit cases cover overlap, close during a check, repeated
and concurrent claims, cancelled claims/checks, denied/lost leases, and driver
failures. Real PostgreSQL tests verify concurrent checks, second-writer exclusion,
and successful acquisition after release for both stores. Before-file hashes,
the reviewed patch and test evidence are in `artifacts/tcp25-goal/writer-lease/`.

This addresses a reproduced mechanism compatible with the recorded failure.
It does not complete the 24-hour soak or certify the failed run's final account
state. No soak was restarted and no in-flight proposal was executed/reconciled by
these tests. Reconciliation remains required before considering a future run.
