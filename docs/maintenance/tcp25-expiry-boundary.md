# TCP25 Phase 2B — capacity expiry boundary

Technical verdict: **GO for this bounded local remediation**. This is not a
production/runtime, firm-qualification or trading acceptance. Browser E2E is
blocked and 53 service-backed tests were skipped; those checks are not certified.

## Root cause and precise semantics

The inherited account and session freshness checks accept age **<=1800 seconds**.
TCP25 limits expiry to the minimum of generation+1800 seconds, the observation's
timestamp+1800 seconds and the personal 14:00 UTC window close. At age exactly
1800, the shared checks still report fresh/known state, allowing `WITHIN_CAP` or
`CALCULATED` with `expires_at == generated_at`. Frontend/current-use checks
already use the exclusive deadline and reject such results.

The deterministic pre-fix probe reproduced the zero-lifetime positive result.
The minimized regression run failed 24 cases and passed 22 before the fix.
An earlier test run also exposed three future-date fixture errors; those were
corrected by pinning the test clock, without changing production date validation.
Both diagnostic logs are retained.

The production diff is two lines in
[`tcp25_personal.py`](../../src/core/advisory/tcp25_personal.py): if the computed
deadline is <=generation, add `personal_capacity_expired` to unknown reasons
before capacity classification or monetary sizing. Shared accounting and legacy
sources are unchanged. No expiry is extended or rounded forward to manufacture
usable capacity. Other existing blocking conditions still take precedence.

The usable interval is **[generated_at, expires_at)**. For a fresh, otherwise
eligible personal observation, generation must precede observation+1800 seconds:

| Observation age | Personal capacity / monetary plan |
| --- | --- |
| 1799 seconds | Positive personal result; one second remains |
| 1799.999999 seconds | Positive backend result; one microsecond remains |
| 1800 seconds | UNKNOWN; remaining capacity null, personal size0 |
| 1800.000001 or1801 seconds | UNKNOWN; no positive capacity or size |

Expired deadlines remain visible in UNKNOWN/BLOCKED evidence. They never carry
a positive usable result. Python comparisons retain microseconds and normalize
aware clocks to UTC. JavaScript `Date.parse` has millisecond resolution; it can
conservatively discard the last sub-millisecond interval, but does not extend the
deadline. No frontend production change was needed.

## Exact changed source/test/document paths

- `src/core/advisory/tcp25_personal.py`: two-line expiry guard, shared by the
  versioned personal capacity and plan branches.
- `tests/unit/test_tcp25_personal.py`: 46 additional cases across both branches,
  1799/1800/1801, one microsecond on each side, offsets -12/0/+05:30/+14, date
  rollover, and the entry-window close under both Chicago DST offsets.
- `tests/unit/test_tcp25_personal_api.py`: six direct authenticated endpoint
  cases covering capacity and plan at1799/1800/1801.
- `dashboard/tests/tcp25-personal.test.ts`: five additional tests for exclusive
  display expiry, precision/offsets, and actual post-fix Python JSON envelopes.
- `docs/maintenance/tcp25-expiry-boundary.md`: this report.

Four byte-for-byte before archives and the exact patch are under the new
[evidence directory](../../artifacts/earn2trade-tcp25-readiness/capacity-expiry-boundary-v1/).
No frontend production, legacy domain, API route, account schema, configuration,
dependency or firm-rule assumption changed. Schema/policy/algorithm names remain
unchanged; the exact source digest identifies the patched implementation.

## Verification actually executed

| Check | Actual result |
| --- | --- |
| Boundary unit module |83 passed; subset of the runs below |
| Relevant backend/API regression |355 passed; no failures/skips |
| Frontend regression |243 passed across20 files |
| Full Python test collection with coverage |2995 passed,53 skipped,0 failed;560 non-failing warnings;166.05s |
| Configured aggregate statement/branch gate |**82.1806066% >=70%: PASS** |
| Statement coverage |11376/13458 =84.52965% |
| Branch coverage |2930/3950 =74.17722% |
| Changed TCP25 module aggregate coverage |91.92825%; not100% |
| Static/build checks |Ruff, Black/isort, strict MyPy on140 sources, six-package architecture, TypeScript, Vite production build, whitespace checks: PASS |
| Replay/source compatibility |12 current boundary envelopes and4 unchanged legacy personal/briefing records replayed;3 prior-v2 envelopes correctly rejected as current after source digest changed |
| Browser E2E |**NOT EXECUTED / BLOCKED**: browser inventory empty; selecting `iab` returned “Browser is not available: iab” |

The gate used the existing `agents`, `core`, `connectors` sources, branch=True,
omissions and70% threshold. Only report/cache/test-store paths were redirected
to `/tmp`; repository configuration and old coverage reports remain unchanged.
The whole `tests` collection ran without a test selector or new exclusions.
No infrastructure opt-ins were enabled. The53 skipped cases require disposable
PostgreSQL/Redis, isolated Kafka/paper infrastructure or writer-lease PostgreSQL.
This is a real coverage-gate execution, **not** a complete service-backed CI run.
Existing deprecation warnings and Vite's chunk-size advisory remain unsuppressed.

Both backend runs explicitly cleared service-test opt-ins and denied TCP/UDP
socket connections; neither recorded a connection attempt. No services,
execution agents, broker connections, external market/model calls or trades
were started. The unavailable browser was detected before starting a fixture host.

## Preservation, findings and acceptance limits

The [verification receipt](../../artifacts/earn2trade-tcp25-readiness/capacity-expiry-boundary-v1/verification.json)
records exact commands, diagnostics and results. The
[manifest](../../artifacts/earn2trade-tcp25-readiness/capacity-expiry-boundary-v1/source-manifest.json)
compares the pre-edit inventory and all before archives. Existing historical
TCP25/TCP50/Phase1A/worksheet-v2 artifacts and unrelated local UI changes are
preserved. Private mutable data, credentials, dependency/cache trees and symlinks
are excluded from that public-file inventory; no blanket private-store claim is made.

Earlier v2 envelopes retain their original bytes/hashes. They are not relabelled
or patched to match the new source. Their expected current-source rejection is
distinct from corruption: the new boundary examples capture their own complete
inputs and replay under the patched source. Legacy hashed implementations and
their directly checked historical personal/briefing records remain unchanged.

Remaining findings, limited to this boundary-remediation audit:

- **P0:** none identified.
- **P1:** the positive zero-lifetime response is resolved; no open P1 boundary
  defect identified by the completed checks.
- **P2:** browser E2E unavailable;53 infrastructure cases unexecuted; frontend
  millisecond precision conservatively rejects some sub-millisecond lifetimes.
  These are visible validation/precision limits, not authorization to widen scope.

Assigned firm progression/account/closing rules, qualified market/cost evidence,
strategy edge and failed-forward-run reconciliation remain unresolved inherited
work. Personal exposure remains one Mini OR ten aggregate Micros, never both;
full Mini support stays deferred. All checks retain `firm_eligibility=BLOCKED`,
`qualified_contracts=0`, `passing_probability=UNKNOWN`, `trade_permitted=false`
and `execution_enabled=false` (`execution_permissions=false`). Test results do
not change those decisions. Stop after verification; no subsequent phase starts.
