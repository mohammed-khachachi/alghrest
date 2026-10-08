# TCP25 migration evidence — 2026-10-05

The persistent goal remains active. The read-only first iteration is preserved
in `artifacts/tcp25-goal/isolation/first-iteration.md`. Git metadata is unavailable
in this checkout: status, diff, log, branches and remotes cannot be verified.
The earlier recovery archive and current phase checkpoints preserve source
content without resetting or discarding local work. No credentials were copied
into the phase evidence, and the operating `.env` was not changed.

## Import isolation

The existing architecture checker now traverses relative/transitive imports,
package initializers, producer aliases, and literal dynamic imports. Unresolved
dynamic imports and uninspectable wildcard sources block the advisory graph.
Local schema wildcard re-exports remain inspected. The checker parses source;
it does not execute imported fixtures or sandbox arbitrary Python reflection.

Eight negative regressions failed before the fixes. All 41 isolation cases now
pass, as does the real application graph. The checkpoint, patch, and verification
are in `artifacts/tcp25-goal/isolation/`.

## Runtime capability boundary

Settings now separates `OPERATING_PROFILE` from `ENVIRONMENT`.
`earn2trade_tcp25` denies order-capable operations even in live mode; `general`
retains existing behavior. No order topic, new service, database, or agent was
added. The isolated assistant still uses the existing pure advisory code and its
separate store; it cannot import execution/state components.

Denial precedes side effects at legacy agent startup/publication, Kafka producer
initialization/publication, executor initialization/submission, exchange
connection/creates/cancels, paper initialization/matching/cancellation, recovery
processing/outbox publication, and trading API startup. The launcher denies
paper/full startup before subprocess invocation. Research Compose fixes the
advisory profile; full Compose propagates the selected profile to every agent.
The actual `.env` and running services remain unchanged. Operators select the
profile before launching a separate process; running services need a deliberate
restart to use new code/configuration.

Evidence:

- 149 capability cases pass across development, paper and live environments.
  Blocked cases assert untouched broker/database/Kafka/subprocess collaborators.
- 24 existing advisory/API cases pass under the advisory profile.
- 762 unit cases pass; 86 mocked integration cases pass and 51 service-dependent
  cases skip with external opt-ins absent.
- Aggregate branch-aware coverage is 72.52%, passing the configured 70% gate.
  This is not near-complete coverage of all financial behavior.
- Ruff, Black, isort, application architecture checks and strict MyPy pass.
- Before-file hashes and the reviewed patch are preserved in
  `artifacts/tcp25-goal/capabilities/`. Test logs and coverage are copied there.

No broker orders were submitted/cancelled, no agents were started, and no
runtime database was changed by this phase. Test databases are temporary.

## Completion gates and next evidence

G1 has static graph and runtime-denial evidence for the current application
entry points. G2 has source preservation, but Git identity cannot be recovered
from the empty metadata. G3–G13 remain unresolved. G14 is incremental: the
architecture and profile runbook now describe the implemented boundary.

The recorded paper soak failed after roughly 22 hours with overlapping operations
on the accountant's shared asyncpg writer-lease connection. The shared-session
overlap has now been reproduced against real PostgreSQL
and corrected in both stores. SELECT-only tests confirm concurrency, exclusion,
and release/reacquisition; 20 fault-injection unit cases cover lifecycle failures.
The soak has not been restarted and its final state remains unreconciled. See
[the recorded correction](deployment-soak.md#5-october-shared-writer-lease-correction).

The current manual evaluation journal is not broker-authenticated state, does
not model all futures exposure, and does not implement versioned TCP25 policies
or a rule-exact simulator. There is no qualified multi-market OOS dataset or
positive-edge/pass-probability evidence. The existing report's `ready` status
means analysis is available; it is not approval to trade. Account B is not ready.

## Advisory journal integrity

The existing manual journal now reads profile and sessions from one SQLite
transaction. It checks stored account/day identities against database keys,
validates the complete session timeline before exposing financial state, and
revalidates model values before writes. Invalid records are rejected rather than
skipped or repaired. Existing finalized-history and loss-minimum rules remain.
No schema, financial risk limit, new database, or API contract was introduced.

Eleven new negative cases failed against the pre-fix implementation. A separate
snapshot regression also failed against the preserved pre-fix store. The 29
current evaluation cases pass, including concurrent writers preserving the worst
intraday loss, malformed payloads, invalid numeric model copies, account
separation, and a commit injected between the profile and session reads.
The patch, checkpoints and logs are in
`artifacts/tcp25-goal/journal-integrity/`.

The latest combined suite passes 883 tests, skips 53 service-dependent cases with
opt-ins absent, and reaches 73.08% branch-aware coverage. The two SELECT-only real
PostgreSQL lease cases passed separately. Ruff, Black, isort, architecture checks,
the configured strict MyPy command, and the changed advisory store's type check
pass. Sandbox-only async test stalls are preserved in the diagnostic log; the
same mocked suite passes outside the sandbox.

G3 remains incomplete. The manual journal is now more defensively validated,
but it still relies on user-entered observations and lacks a complete futures
position/exposure state. The next foundation is an explicit authoritative
account observation and its trust/freshness/exposure requirements, reusing this
journal rather than treating spot balances or nominal capital as futures equity.
Licensed historical Tier-1 data and verifiable strategy edge remain unavailable;
no statistical trading-readiness conclusion is justified.

## Explicit account observation — 2026-10-05

The existing journal/session path now owns optional, versioned account evidence:
account identity, source/reference, observation time, currency, cash, unrealized
PnL, equity, costs/confirmation, positions and working orders. Evidence is
immutable after validation; source confirmation is reported metadata, not broker
authentication. The domain has no provider, AI, broker, Redis or execution import.
No additional service or database was added.

Equity must equal cash plus unrealized PnL, and position PnL must reconcile to the
account total. Identities cannot duplicate. Each observation must match its
session timestamp, journal account and journal equity in USD. Internal model
copies are revalidated. Assessment uses an explicit clock and freshness budget;
missing, unconfirmed, stale or incomplete evidence cannot reach evaluation
sizing. A caller cannot substitute nominal capital or a fabricated existing
contract count. Existing per-trade, daily-loss and drawdown constraints remain.

The API persists observations through the existing session transaction. The
browser form collects an explicit manual flat-account check, clears confirmation
when economic inputs change, and retains a saved non-trading day's flag. Unsaved
account/session changes clear sizing and block recalculation until saved. A
revision check discards delayed sizing responses after input/account changes.
Legacy sessions remain readable with UNKNOWN account state; planning now requires the
new evidence. Known state means reported state is internally reconciled. It is
separate from trading permission, broker authentication, market-data health and
strategy approval.

Non-flat positions/orders can be recorded for any named contract. Their sizing
is deliberately blocked until contract-aware exposure risk and progression
limits are verified. This is an unfinished dependency of the full multi-market
architecture, not the final supported workflow.

Evidence:

- The original missing-state sizing test failed before the guard was implemented.
- 57 focused account/evaluation tests pass, with 100% branch-aware coverage for
  both modules. Two property tests exercise 180 reproducible examples of missing
  coverage and bounded sizing. Coverage does not prove broker-data authenticity.
- Seven API cases pass, including persisted unknown-state denial, explicit
  complete-state sizing, and rejection of nominal-capital substitution.
- The combined mocked suite passes 912 tests, skips 53 service-dependent cases,
  and reaches 73.52% aggregate coverage. Financial runtime state is unchanged.
- Ruff, Black, isort, architecture checks, strict MyPy, and the dashboard build
  pass. Existing Browserslist age notification remains.
- Browser verification uses a disposable loopback preview with synthetic read-only
  fixtures. The account form renders; confirmation starts unchecked and clears
  after cash edits; non-trading session status stays unchecked. Draft edits
  disable sizing. A delayed synthetic sizing response renders normally, then a
  second response is discarded when the account changes while it is pending.
  The preview is stopped and the temporary tab closed. No financial record was submitted there.

Before-file hashes, the reviewed patch, tests/coverage and a synthetic UI capture
are in `artifacts/tcp25-goal/account-observation/`.
G3 is strengthened but not complete: manual-source completeness cannot be
broker-authenticated yet, and non-flat risk lacks verified contract metadata.
The next coherent action is to extend the existing instrument catalog with
source-verified Tier-1/Tier-2 contract specifications, then use them for exposure
risk. Replay/provider/data-health work remains required before recommendations.
G7 and later statistical gates remain unsupported by qualified historical data.

## Multi-market contract catalog — 2026-10-05

The existing isolated advisory catalog now contains all requested Tier-1 and
Tier-2 instruments. It retains legacy NQ, crypto and index entries. No separate
market classes, registry service, broker integration or database was added.
Instrument and specification models are frozen; the active catalog exposes an
immutable mapping. Legacy serialized instrument records without new metadata
remain readable, but cannot validate new futures contract identities.

Each active futures instrument carries specification version
`cme-outright-2026-10-05`, review date, official sources, venue, research tier,
quote unit, settlement type, month-code family and exposure group. The existing
Decimal tick and point-value fields remain the operative sizing parameters;
tick value is their product. Equity-index products share a conservative exposure
group; this label is not an estimated correlation coefficient.

| Root | Tier | Outright tick | USD per quoted price unit | USD per tick | Month family |
| --- | --- | --- | --- | --- | --- |
| MES | 1 | 0.25 | 5 | 1.25 | HMUZ |
| MYM | 1 | 1 | 0.5 | 0.5 | HMUZ |
| MNQ | 1 | 0.25 | 2 | 0.5 | HMUZ |
| MGC | 1 | 0.1 | 10 | 1 | GJMQVZ |
| M2K | 2 | 0.1 | 5 | 0.5 | HMUZ |
| MCL | 2 | 0.01 | 100 | 1 | FGHJKMNQUVXZ |
| M6E | 2 | 0.0001 | 12500 | 1.25 | HMUZ |
| M6B | 2 | 0.0001 | 6250 | 0.625 | HMUZ |
| MHG | 2 | 0.0005 | 2500 | 1.25 | FGHJKMNQUVXZ |

Source evidence:

- Equity multipliers, outright increments, month families and settlement:
  [CME Micro E-mini fact card](https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf).
  Legacy NQ economics:
  [CME NQ overview](https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.html).
- Gold economics and physical settlement:
  [COMEX chapter 120](https://www.cmegroup.com/rulebook/COMEX/1a/120.pdf);
  month family:
  [CME gold fact card](https://www.cmegroup.com/trading/metals/files/fact-card-gold-futures-options.pdf).
- Oil economics and cash settlement:
  [NYMEX chapter 309](https://www.cmegroup.com/rulebook/NYMEX/3/309.pdf);
  monthly family:
  [CME Micro WTI FAQ](https://www.cmegroup.com/education/articles-and-reports/micro-wti-crude-oil-futures-faq).
- Copper economics and cash settlement:
  [COMEX chapter 914](https://www.cmegroup.com/rulebook/COMEX/9/914.pdf);
  monthly family:
  [CME Micro Copper fact card](https://www.cmegroup.com/education/files/micro-copper-futures-factcard.pdf).
  The 2023 metals product guide contains conflicting delivery/termination text;
  the current rulebook controls these fields.
- FX economics and physical settlement:
  [CME 2026 FX guide](https://www.cmegroup.com/markets/fx/fx-product-guide);
  EUR month family:
  [CME M6E specifications](https://www.cmegroup.com/markets/fx/g10/e-micro-euro/specs);
  GBP quarterly family:
  [CME listing notice](https://www.cmegroup.com/rulebook/files/S_5524.pdf).
  The latter is historical evidence of the contract family, not confirmation
  of the currently listed GBP maturities.

Import identity now uses each instrument's month family, exact root, and an
ASCII two- or four-digit year. Continuous aliases, wrong roots, wrong family
months and three-digit years are rejected. This fixes the old blanket quarterly
assumption for gold, oil and copper. This syntax check cannot establish actual
listing, expiry, roll selection, liquidity or data entitlement. Those require
dated contract/provider metadata before recommendations.

Sizing uses each instrument's own tick rather than a Nasdaq-specific error
message. Internal model copies are revalidated at the financial worksheet entry
point; seven failing regression cases exposed the missing input validation
before the fix. The validated financial field subset preserves the existing
EvaluationPlan subtype. Stops remain structural inputs; quantity floors to
integer contracts and becomes zero when the risk cannot fit one contract.

Verification and reviewed patch are recorded in
`artifacts/tcp25-goal/contract-catalog/`. The focused advisory suite covers
catalog economics, every permitted month family, aliases/wrong roots, fractional
tick values, immutability, serialization/legacy compatibility, risk boundaries,
180 reproducible property examples, and monthly API import/report round-trips.
No runtime financial records or broker state were changed.

The final mocked regression suite passes 953 tests, skips 53 service-dependent
cases, and reaches 73.68% aggregate branch-aware coverage. The focused advisory
suite passes 123 cases. Its coverage has no missing lines or branches in the
new metadata validation, tick-value and contract-identity functions, or the
financial sizing function. Account/evaluation modules retain 100% focused
branch-aware coverage. Ruff, Black, isort, architecture checks and strict MyPy
over 102 source files pass. The broader direct connectors type-check still
reports 17 existing errors in the untouched ccxt connector; this phase does not
claim repository-wide typing cleanliness.

Remaining dependencies: this catalog does not supply TCP25 progression weights,
instrument eligibility, margin, expiry calendars, fees or market-data health.
The evaluation planner still supports its existing NQ/MNQ route and blocks
non-flat exposure; expansion belongs to the replaceable policy/exposure phase.
The historical positive-price schema also needs an explicit energy price-domain
decision before claiming support for every historical energy regime.
No strategy is promoted and no pass probability is inferred from specifications.
Existing Nasdaq-focused dashboard wording and default watchlist remain; a
ranked PRIMARY/BACKUP session choice has not been implemented.
G3–G13 remain incomplete. Next: adapt the existing data/import path into an
explicit replay/provider contract and fail-closed data-health assessment using
these instrument identities.

## Provider boundary and candle replay — 2026-10-05

The dashboard mock QuoteProvider was inspected again. Its float quote/daily-bar
contracts lack intraday close timestamps and dated futures identity; it remains
isolated demo behavior. The advisory path reuses its existing Decimal
MarketSnapshot/Candle contracts, public GET adapter, import store and report math.

The new core MarketDataProvider protocol accepts a frozen MarketDataQuery:
instrument, interval, explicit aware as-of clock, optional dated-contract pin,
and a maximum of 500 returned bars. AdvisoryMarketData routes the existing
public crypto reads or isolated imported snapshots through this boundary.
The research service accepts an injected provider/clock and no longer makes
vendor-specific market-fetch decisions itself. No service/database/vendor
integration was added.

ReplayProvider accepts ordered archived snapshot chunks, including streams
longer than one 500-bar window. It retains serialized bars independently of
caller mutation, rejects duplicates/overlap/order/source disagreement, and
requires a contract pin if eligible dated streams are ambiguous. A replay read
uses a binary-search cut and returns only completed candles in the bounded
window. Missing data stays missing. Its reconstructed fetched_at is the virtual
cut, not evidence that the archive was originally captured at that moment.
Source vintage/entitlement and actual listing/expiry are not established.

Replay feeds the same build_report function through the same service path.
Live derivatives, free-text observations, current news and live agent context
are excluded because they can reveal information after the historical cut.
Replay bypasses current-source cache and refresh throttling; current-source
cache/rate limits remain. Current news/context timestamps are filtered against
the decision cut. Provider faults or identity/provenance mismatches produce an
unavailable report with no price scenarios. Report construction revalidates
nested candle data, fixing a reproduced mutation-bypass case.

Evidence:

- 33 provider/replay cases include a 640-bar chunked stream, explicit contract
  isolation, no live IO/context during replay, source faults, current cache
  behavior, and exact closing-time boundaries.
- 100 reproducible property examples change future prices while checking that
  earlier snapshots, indicators and scenarios remain identical.
- 156 focused advisory cases pass. Core data contracts, ReplayProvider and
  service composition each have 100% branch-aware coverage in that suite;
  account/evaluation modules retain 100%.
- The full mocked suite passes 986 tests, skips 53 service-dependent cases,
  and reaches 73.97% aggregate coverage. Ruff, Black, isort, architecture checks
  and strict MyPy over 104 source files pass.
- Restricted-thread test launches stalled, were identified as the two owned
  pytest processes, and were terminated before rerunning with thread support.
  One read-only status check and one test launch required retries after automatic
  approval review timed out. These were not source/test failures.

Hashes, the reviewed patch, red regression, final tests and coverage are recorded
in `artifacts/tcp25-goal/replay-provider/`. No runtime financial records,
brokers, agents or trading services were changed.

This is research-feature replay parity, not G9 completion: strategy/risk/policy/
advice replay, dataset versioning, historical context and decision-ledger parity
remain. G4 also remains incomplete: provider heartbeat, sequences, quote/spread
health, session-aware gaps and source agreement need a proper fail-closed guard.
The next immediate clock-hardening check is UTC instant normalization, including
the repeated local hour at daylight-saving transitions, before extending the
market-data health assessment. No edge or TCP25 pass probability is claimed.

## UTC instant normalization — 2026-10-05

The next clock check reproduced two faults across the repeated Chicago hour:
the old bounded snapshot included a closing bar about 45 minutes beyond its
requested cut, and the old account guard reported KNOWN at 3,600 seconds of
elapsed age with a 1,800-second budget. Preserved pre-change classes reproduce
both behaviors with corrected, valid fold-specific fixtures. The initial test
fixture also exposed Python local-time arithmetic resetting its fold; the final
fixture specifies each instant explicitly and its absolute order is verified.

A shared UTCDateTime type now first validates awareness, then normalizes to the
same UTC instant. Candle times, observations, snapshot capture, news/report
times, provider queries and evaluation-session timestamps use it. Explicit
research/evaluation clocks and account age arithmetic also normalize to UTC.
No timezone information is guessed for naive input. Chicago session-date
conversion remains explicit, and its rules/thresholds are unchanged.
Stored offsets remain readable; no existing financial rows were rewritten.
Future, stale, ordering and timestamp-equality checks now operate on elapsed
instants instead of ambiguous repeated wall times.

Evidence in `artifacts/tcp25-goal/utc-clock/`:

- Fourteen clock cases cover both folds, spring/fall transitions, candle ranges,
  future-bar cuts, account freshness at epsilon/exact boundaries, session/account
  instant equality and equivalent-offset feature results.
- 100 reproducible property examples compare age decisions under equivalent
  UTC/fixed-offset clocks.
- 170 focused advisory cases pass. Account/evaluation, provider contracts,
  replay adapter and service composition retain 100% branch-aware coverage.
  The shared timestamp normalization function has no missing lines/branches.
- The full mocked suite passes 1,000 tests, skips 53 service-dependent cases,
  and reaches 73.99% aggregate coverage. Repository Ruff passes; changed-file
  Black/isort, architecture checks and strict MyPy over 104 sources pass.
- Before-file hashes, reviewed patch, pre-change fault evidence, final tests and
  coverage are preserved. Runtime financial/broker state is unchanged.

This strengthens G3/G4/G9 but does not close them. The next coherent change is
the fail-closed market-data health assessment: provider state, sequences,
quote/spread quality, session-aware gaps and source agreement. Qualified
historical data, approved strategy edge, rule-exact simulation, statistical
pass distributions and complete paper evaluations remain required.

## Fail-closed closed-bar health — 2026-10-05

The preserved implementation allowed a missing futures candle to produce all
three numeric scenarios after only a warning. The red regression now passes:
unverified CME session gaps yield UNKNOWN and no indicators/scenarios. A new
pure health assessment reuses the existing freshness budget, UTC model
validation, catalog ticks, quote observation and provider boundary. It adds no
service, topic, broker access, database or per-market implementation.

MarketSnapshot may carry explicit reported quality facts. Missing metadata is
UNKNOWN; degraded/disconnected providers, future/stale observations, invalid
structures/prices and sequence faults block. Required sequences must align
with all source candles before trimming; order/gaps and nonnegative IDs are
checked. Continuous-source cadence faults block; CME gaps remain UNKNOWN
until supported by a verified session calendar. Provided quotes require known
identity, bid/ask, applicable tick alignment and explicit age/spread limits.
Reference sources on the same host are not treated as independent; absent
source-deviation limits or reference requirements fail closed. Guard policy
parameters, ages, provider identity, cadence/spread/source diagnostics and
reason codes are saved with a versioned health result.

HEALTHY covers **closed-bar research only**, never entry readiness. Health's
trade_permitted and Report.execution_enabled are always false. No quote/spread
SLO or execution permission is inferred from bars. User quality claims remain
reported facts, not authenticated provider/entitlement/account evidence. JSON
imports cannot supply a health/permission override. Legacy records and CSV
remain readable and stored; their missing quality blocks new numeric research.
The risk worksheet remains explicitly separate manual numeric planning, not a
recommendation or TRADE PERMITTED decision.

Replay stores detached quality alongside archived bars, slices required
sequences, and preserves missing/provider/sequence faults. Only compatible
closed-bar facts may use an archive-reader heartbeat at the virtual cut;
originally stale/future heartbeats and unsupported captured quotes remain
blocked. This is not evidence of original capture timing or faithful historical
quote replay. News/live derivatives/context remain excluded from replay.

Current report composition assesses at the final clock after supporting reads.
Cache reuse rechecks health before returning an old ready report, including
inside the refresh throttle; returned records are detached from internal cache.
The dashboard shows NO TRADE and hides levels/charts for unknown/unhealthy or
unassessed legacy reports, retaining source provenance. Failed refresh clears
the old report. A synthetic loopback fixture deliberately returns old numeric
scenarios with UNKNOWN health to verify that the UI still suppresses them.

G4 is strengthened, not complete: entry recommendations need event/quote histories,
verified session calendars, suitable explicit limits, authenticated provider
contracts and integration with account/risk/policy/approved-strategy gates.
G7/G10–G13 remain unsupported by qualified OOS data or simulated evaluations;
no statistical edge or pass-rate conclusion is claimed. The next foundation
work is to inspect session/event-risk and selection evidence contracts, retaining
NO TRADE wherever current data cannot support their decisions.

Verification completed across the 2026-10-05/06 UTC boundary:

- 244 focused advisory cases pass, including 100 reproducible provider-fault
  property examples and exact/epsilon freshness, future-clock, quote-age,
  spread, source-deviation and cadence boundaries. Guard, data contracts,
  replay, service composition and account/evaluation retain 100% branch-aware
  coverage. Fault injection verifies cache isolation, stale cache/context reads,
  unsupported quote replay and preserved bad archive heartbeats/sequences.
- The synthetic browser verifies UNKNOWN and legacy reports show no price
  charts/scenarios despite supplied numeric fields; HEALTHY research retains
  three scenarios/one chart with the research-only warning. Source provenance
  remains visible while blocked. Screenshot and fixture are preserved.
- Ruff, changed-file Black/isort, architecture checks, dashboard build and
  strict MyPy over 104 relevant source files pass. An exploratory check adding
  the untouched architecture-check script exposed two existing MyPy errors in
  that script; its runtime architecture check still passes. No unrelated source
  changes were made to silence them.
- One initial full-suite invocation lacked the repository import path and
  failed collection. Explicit PYTHONPATH=src:. with python -m pytest resolves
  the collision. A restricted-thread launch stalled and was stopped through
  its owned session; final async suites run with thread support and all
  real-service opt-ins removed. No real broker/financial record was modified.
- Git still reports no repository. The before-file copies/hashes and reviewed
  patch preserve this phase without manufacturing Git history. Evidence is
  in artifacts/tcp25-goal/data-health/. The synthetic server/tab are stopped.

The final full mocked suite passes **1,074 tests**, skips 53 opt-in service cases,
and reaches **74.61%** aggregate coverage. Final logs, XML and coverage files
are recorded with hashes and the verification summary in the phase evidence.

## Internal economic-event guard — 2026-10-06

Inspection found no existing market selector or scheduled-event guard. The
macro_economist agent reads FRED observations and classifies regimes; it does
not ingest a release schedule despite its introductory docstring. Existing
news headlines and macro summaries cannot establish complete calendar coverage.
They remain contextual inputs, not event-policy clearance.

A red regression showed that healthy bars without any calendar/policy evidence
still produced three conditional scenarios. The new pure event guard reuses the
catalog, strict schemas, UTC normalization, existing report/service path and
ReplayProvider. It introduces no trading agent, Kafka topic, vendor integration,
database or financial-state path. Immutable source revisions and server-owned
internal policy are separate from the prop-firm evaluation rules.

The guard requires explicit policy identity/version, asymmetric before/after
windows, calendar-age budget and blocked impact classes. No defaults or
statistically validated blackout durations are asserted. The zero-to-seven-day
schema bounds are input/resource bounds, not operating SLOs. Calendar evidence
includes identity/version/source, observation time, covered markets/period,
completeness and provider state. Events include identity, known-at and scheduled
instants, impact, status, source and affected markets. Duplicate/invalid roots,
future-known revisions and events outside declared coverage are rejected.

CLEAR requires complete fresh coverage of [cut - after, cut + before]. Blackout
endpoints are inclusive. Relevant unknown times/classifications, missing policy,
stale/partial coverage and provider uncertainty prevent clearance. Known
blackouts and structural/provider faults dominate uncertainty. Cancelled,
outside-window or explicitly irrelevant events do not create false blackouts.
The verdict always retains trade_permitted=false and records exact policy,
calendar revision, blocked event IDs, reasons and decision time.

Report construction gates scenarios on both data health and event clearance.
Healthy technical bar statistics remain research; ready is not entry approval.
Normal API composition has no configured event policy/calendar reader, so its
conditional price scenarios are now suppressed with UNKNOWN rather than an
implicit all-clear. The injected calendar reader is a nonblocking record seam;
no live/official calendar is synthesized, downloaded or enabled by default.
The API has no client/AI calendar-policy override. The existing report store
persists the full event assessment without schema or financial-data migration.

Replay accepts detached reported calendar revisions and returns only the latest
market-covered revision with observation time at/before the cut. Duplicate
versions or overlapping same-time revisions are rejected; future revisions
cannot alter earlier decisions. Live calendar/context IO is excluded in the
replay tests. This supports point-in-time research parity, not authenticated
historical-calendar completeness or final advice/risk/policy parity.

Current cache reuse rechecks event state, reasons, calendar revision and policy.
A separately reproduced reader-latency fault returned clear cached scenarios
after a blackout had begun. It now reassesses after calendar acquisition;
uncached reports already assess after supporting context reads. No cache/rate
limit may preserve scenarios after a newly blocked/unknown verdict. The UI
suppresses unknown, blocked and unassessed legacy scenarios even if a historical
payload retains numeric fields. Bar-health failure still dominates a clear event
result. Both warnings identify this as internal risk, separate from company rules.

G4/G5/G9/G14 gain foundation evidence; none is broadly closed by this phase.
There is still no qualified calendar adapter/ingestion workflow, validated policy
window, market selector, approved futures strategy edge, rule-exact TCP25
simulator, or pass-probability evidence. The next coherent action is to build
market-selection evidence contracts and deterministic filtering/ranking from
measured inputs, reusing these guards and the catalog. Missing edge/fit/liquidity
or eligibility evidence must yield no selected market, never a fabricated score.

Verification evidence in `artifacts/tcp25-goal/event-risk/`:

- Both the initial missing-calendar scenario regression and the later cache/
  reader-latency regression record failures on the pre-fix code paths and pass
  after the changes. 320 focused advisory cases pass; event guard, market-data
  guard/contracts, replay adapter, service composition and account/evaluation
  retain 100% branch-aware coverage. The new calendar/event/policy validators
  exercise invalid identities, duplicates, future knowledge and bad copies.
- 100 reproducible event-window examples match an independent interval oracle;
  50 additional examples show future calendar revisions cannot change past
  scenarios. The existing 100 future-price replay examples now explicitly supply
  synthetic clear calendars and check nonempty scenarios when enough bars exist.
- Exact/epsilon tests cover both blackout endpoints, asymmetric coverage,
  calendar freshness and future observation. Repeated Chicago-hour tests reject
  later-instant knowledge with an earlier wall time and preserve actual blackout
  timing. Extreme unrepresentable clock windows fail closed.
- The full mocked suite passes **1,150 tests**, skips 53 opt-in service cases,
  and reaches **75.09%** aggregate coverage. No external financial-service test
  opt-ins are enabled. Runtime financial/broker state remains unchanged.
- Ruff, changed-file Black/isort, architecture, dashboard build and strict MyPy
  over 105 relevant sources pass. The reviewed patch and before/after hashes
  preserve this phase; Git metadata remains absent.
- Synthetic browser cases verify UNKNOWN, BLOCKED and legacy event states hide
  supplied numeric scenarios while retaining healthy bar research; CLEAR retains
  three research scenarios. Unknown bar health suppresses all charts/scenarios
  even with CLEAR event state. The screenshot and five-case results are saved.
  The owned loopback fixture server and browser tab were stopped.

The goal remains active; these tests do not supply genuine edge, TCP25 fit,
qualified calendar provenance, complete replay decisions or paper evaluations.

## Guarded multi-market research selection — completed foundation

The prior backtester, correlation agent and risk engine were inspected before
this phase. They do not provide comparable, contract-aware evaluation evidence:
crypto backtest acceptance is not a rule-exact TCP25 simulation, and crypto
correlations do not establish futures independence. This phase reuses the
futures catalog, existing MarketRegime enum, provider/replay cut, both guards,
shared ATR convention, service lock/rate limit and bounded SQLite research store.

The checkpoint covers nine existing files; two justified new files contain the
selection evidence contracts/engine and its synthetic verification. No extra
agent, service, Kafka topic or database was introduced. Git metadata remains
absent; before/after hashes and the reviewed patch are preserved under
`artifacts/tcp25-goal/market-selection/`.

- The normal API compares Tier-1 MES/MYM/MNQ/MGC without a hardcoded favorite.
  Its selection policy and research reader remain unconfigured; imports alone
  cannot qualify a market. Missing/invalid evidence yields no nomination.
- Server-owned, versioned selection policy requires explicit market limits,
  cohort, sample sizes and path/tail/failure/cost ceilings. Only reported APPROVED
  research with positive net OOS expectancy lower bound, disjoint periods,
  cost/walk-forward/holdout evidence, matching regime and all sixteen losing-run
  estimates can qualify. Synthetic research cannot nominate a current market.
- Evaluation-fit evidence is separate from edge, references the exact edge
  revision, and records seed, simulator/policy/cost versions, confidence level,
  horizon, trial counts including censoring, probability bounds, breach risks,
  pass-time percentiles and expected cost. Incomparable cohorts, missing actual
  passes, unverified dependence/rules/costs and excessive risk block nomination.
  These contracts validate reported facts; they do not compute, authenticate or
  certify edge, strategy approval, bounds or rule-exact simulation.
- Bar-volume liquidity, quote spread and shared ATR are explicitly measured in
  contracts/minute and ticks. Quotes enrich detached bar evidence without
  removing heartbeat/sequence/source faults or conflicting book evidence. Data
  and event guards use the same final clock after source acquisition. No missing
  metric is replaced by zero. Limits are supplied configuration, not calibrated
  defaults or newly claimed SLOs.
- Qualified candidates use a documented deterministic lexicographic order:
  pass lower bound, failure upper bound, cost, p95/median days, net edge lower
  bound, tail risk, five-loss path risk, variance, spread, liquidity and root tie
  break. This is an explicit research ordering, not a validated risk optimizer.
  At most one primary and one backup are exposed. Equity-index products share
  one catalog exposure group; the default configured backup mode requires a
  different group. An optional same-group alternative carries a warning and
  simultaneous use is always prohibited. Different groups are not proof of
  empirical independence; this is not yet a portfolio correlation guard.
- Replay reads only research revisions available at the cut, rejects duplicate
  or ambiguous identities and detaches nested source models. Synthetic replay
  traverses the same selector/guards/service/storage path and reproduces all
  comparison fields except generated UUID. Current comparisons remain bounded
  and serial. Stored selections preserve input evidence, policy/guard states,
  derived metrics, reasons and outcome; corrupted identities, permissions and
  backup exposure fail validation. The research store retains only 100 records
  and uses the current catalog: it is not the complete financial decision ledger.
- Read-only comparison and record GET endpoints enforce the existing access
  boundary. The dashboard displays every root's guard states and block reasons,
  hides blocked or incompatible nominees and discards a late response after an
  interval change. It offers no policy/evidence override or execution action.
- The full mocked suite passes **1,270 tests**, skips 53 explicit service opt-ins
  and reaches **76.40%** aggregate coverage. Selector, account/evaluation,
  data/event guards, provider contracts, replay and service each retain **100%**
  branch-aware coverage. Sixty reproducible generated ranking cases establish
  input-order independence without permitting trading or execution. Threshold,
  source-fault, future/stale evidence, storage corruption/retention and API tests
  cover negative edge despite a high pass rate and censored/no-pass trials.
- Repository Ruff, changed-file Black/isort, strict MyPy over 34 relevant sources,
  architecture checks and dashboard build pass. Synthetic browser evidence covers
  missing evidence, qualified replay, spoofed blocked nominees and late responses;
  the final screenshot verifies table spacing. No live financial/broker state,
  actual .env or real account was changed. Preview resources were stopped.

The goal remains active. G7/G8/G10/G11/G12/G13 still lack actual qualified data
and statistical/evaluation evidence. G3/G5/G6/G9/G14 require further integration:
this selector neither permits a trade nor proves policy compliance or financial
readiness. The next foundation is to connect structural sizing, authoritative
account observation and correlated exposure into one deterministic advisory risk
decision, reusing existing worksheet/evaluation rules before adding new policy
abstractions or strategy approvals. No real recommendations are enabled by this
phase.

## Deterministic advisory structural-risk gate — completed foundation

The prior goal turn made progress by adding the guarded market selector. This
phase inspected that current code and the journal, account checker, worksheet,
legacy NQ/MNQ plan and autonomous risk modules before edits. The reusable Decimal
worksheet already computes stop-based risk and integer futures sizing. The
journal supplies one durable account snapshot; its restrictions remain in the
existing evaluation module. Spot notional checks and return-statistic fallback
zeros are not suitable substitutes for unknown futures stop exposure.

Seven existing files were checkpointed, including the evaluation module before
its shared restrictions and validation fix. Two new files are justified: the
provider/AI/execution-independent risk contracts and calculator, and meaningful
financial verification. No new database, agent, Kafka topic, live adapter or
runtime service was introduced. The reviewed patch, before/after hashes and
reports are under `artifacts/tcp25-goal/advisory-risk/`. Git metadata is still
absent; no reset/clean/initialization or local-work deletion occurred.

- Structural input contains market/dated contract, BUY/SELL side, entry,
  invalidation, known-at time, source/basis and strategy revision. It contains no
  requested quantity, account equity, risk percentage or policy allowance.
  AI proposals cannot supply those controls. Wrong-side or off-tick stops block;
  entry must remain within an explicitly supplied quote tolerance. The stop is
  never moved to fit the budget.
- Server-owned risk evidence supplies an explicit configuration, halt state,
  strategy/account loss history and generic policy allowance. No default reader
  is enabled. Missing/invalid evidence yields NO TRADE and zero suggested size;
  unknown budgets and costs stay null rather than being fabricated as zero.
  Reported facts and version labels do not authenticate approval or calculate
  genuine strategy edge, margin or rule-exact evaluation compliance.
- The same selector/data/event guards are rerun at the final decision clock.
  Only a currently nominated primary/backup can enter sizing. Risk configuration
  must match the selected strategy/revision/risk percentage and cost model;
  slippage cannot understate the reported research/measurement assumptions.
  Replay and current account observation sources cannot be mixed.
- The service reads the existing durable account journal, hashes the complete
  profile/session snapshot and joins both policy allowance and strategy history
  to that exact account/revision. It rereads after source acquisition, so an
  intervening journal update blocks old limits rather than mixing snapshots.
  Identity/currency/equity/PnL/completeness/time validation reuses account_state.
  Historical journal breaches, stale/missing sessions, old rule reviews and
  regular-hour closures use the shared evaluation restriction function. A READY
  reader cannot erase a known journal breach. No TCP25 ratios or rules were
  introduced in the generic risk calculator.
- Sizing reuses the worksheet: structural distance, point value, explicit
  round-trip fees and slippage form per-contract loss; percentage budget is then
  limited by daily/drawdown remaining amounts minus a positive safety buffer and
  an integer contract cap assessed at the exact invalidation. Below one contract
  yields NO TRADE without changing the stop. The 1% risk, five-loss pause and
  25% drawdown rails cannot be softened by configuration; stricter values are
  allowed. Drawdown boundaries compare equity differences against the peak
  directly, avoiding rounded-ratio boundary decisions.
- Correlated futures exposure checks both positions and working orders in this
  account, including opposite sides. Equity-index products share their catalog
  exposure group. Other open exposure remains unknown because current evidence
  lacks validated position stop risk. Qualified sizing currently requires flat,
  complete observed state; neither reductions nor independent group membership
  are assumed to release risk. Accounts are not combined or copied.
- QUALIFIED is one **structural risk gate**, with advice WAIT; blocked/unknown
  checks say NO TRADE. `trade_permitted` and `execution_enabled` are always false.
  Structure validity, authenticated strategy promotion, full evaluation policy,
  calendar/margin/expiry and account-profile permissions still need integration.
  Suggested stop loss is an estimate, not a guarantee against gaps or execution
  effects. This phase does not establish Account B readiness or complete G5/G6.
- The protected POST risk-decision endpoint accepts structure and a saved
  comparison ID; existing GET access exposes its immutable result. Saved checks
  include account/revision, source and refreshed selections, all reported risk
  inputs, known-state assessment, amounts, reasons and outcome. Positive records
  rerun every gate at their original clock before save/read and must reproduce
  all meaningful fields; only generated comparison/decision UUIDs are excluded.
  Internal copied guard loss and altered loss history cannot return a positive
  saved check. Retention is 100 research records with the current catalog, not a
  complete financial decision ledger or historical catalog migration mechanism.
- Three reproduced legacy bypasses allowed internal EvaluationPlan copies with
  unchecked schedule, negative safety buffer or negative progression cap. Full
  plan revalidation closes them while preserving all valid planning behavior.
  Red tests also demonstrated changed-record budget/missing-guard acceptance and
  replay/current-account mixing before the fixes.
- **509 focused tests** pass, including 100 reproducible generated sizing
  scenarios checked against independent arithmetic, zero-size/one-contract
  epsilon boundaries, exact 25% drawdown, five-loss pauses, all nine research
  roots, opposite-side exposure, source failures, acquisition latency, journal
  races, durable corruption/retention, AI field injection and API faults.
  Risk, selector, account/evaluation, data/event guards, replay and service each
  have **100% branch-aware coverage**. Existing storage's remaining focused gaps
  concern legacy journal paths covered by the broader suite.
- The full mocked suite passes **1,377 tests**, skips 53 explicit service opt-ins
  and reaches **77.22%** aggregate coverage. Real-service opt-ins were removed.
  Repository Ruff, changed-file Black/isort, architecture, strict MyPy over 108
  sources and dependency consistency pass. No UI change or new preview was
  needed; no runtime broker/financial state or actual .env was changed.

The goal remains active. The next foundation is the replaceable evaluation
policy/allowance adapter, reusing the journal's verified behavior and checking
current official TCP25 rules before encoding any new rule. No genuine licensed
futures/OOS evidence, measured loss/path distributions, approved real strategy,
rule-exact simulator/Monte Carlo or completed paper evaluations were supplied.
These synthetic checks do not close G7/G8/G10/G11/G12/G13. Full financial-state,
portfolio risk, policy, decision ledger/replay and operational gates also remain
incomplete; no real recommendation or execution has been enabled.

## Replaceable evaluation policy (2026-10-06)

The journal, generic structural sizing, selector and bounded research storage
already existed. This phase reuses their account/EOD arithmetic and adds one
policy implementation behind an injected `EvaluationPolicy` port. The nine
pre-existing source/document paths were checkpointed before editing; two new
paths implement and test the policy. Source review, red/green regressions,
coverage, quality checks and the complete diff are in
`artifacts/tcp25-goal/evaluation-policy/`.

- `TCP25Policy` carries immutable public rules under
  `tcp25-eod-public-2026-10-06`: 25,000 initial USD, 1,750 target, 550 daily loss,
  1,500 EOD drawdown, strict 30% consistency, up to three standard contracts and
  ten eligible micros per standard. The reviewed July 2026 FAQ and current
  product page specify no minimum trading-day count; the older March blog's
  ten-day description conflicts. Existing profiles are preserved, and financial
  parameter mismatch blocks. The source-review artifact links all seven
  official pages and records the unresolved account-specific progression table.
- No progression balance thresholds are inferred. Confirmed, version-matched
  progression evidence, actual margin capacity, synchronized account floor and
  complete exchange-calendar evidence are required. The production default
  supplies no such reader and returns UNKNOWN. Synthetic tables remain confined
  to tests; their confirmation fields do not authenticate account entitlement.
- The policy uses the durable journal's daily/EOD/consistency calculations and
  sticky intraday breaches. A positive snapshot requires complete flat account
  state. Consistency extends evaluation rather than becoming a hard loss
  failure. `TARGETS_RECORDED` describes reported journal goals, not an Earn2Trade
  certificate. Funded trailing-drawdown rules are outside this implementation.
- Capacity is checked at the fixed invalidation with estimated round-trip costs.
  Integer size must fit progression at the post-stop balance, actual reported
  margin and strict daily/floor boundaries. An independent generated oracle
  checks the piecewise capacity, including zero capacity. Remaining generic
  risk budgets and positive safety buffers may reduce this capacity further.
- Calendar evidence can impose an earlier flat deadline; it cannot extend the
  shared firm 15:50 Chicago cutoff. Complete coverage with no open window blocks
  holidays/closures. These are reported calendar facts, not a licensed adapter.
  Internal economic-event policy stays separate from firm rules.
- The service computes the policy allowance itself, replacing reader-supplied
  capacity. It retains original halt/history timestamps and rereads the account
  after either evidence reader, so an intervening journal update cannot reuse
  old evidence. Malformed internal model copies are revalidated before stop-cost
  arithmetic. Missing or invalid facts cannot produce positive size.
- Immutable policy checks capture original clock, financial journal, account
  revision, rules, controls and reported source snapshots. Positive checks rerun
  at the original clock before save/read; altered amounts, identity or policy
  configurations fail. The existing SQLite store adds one table with 100-record
  research retention; this is not the complete financial decision ledger.
- Protected API endpoints expose the configured rule version, compute a policy
  check from an existing journal plus structural request, and retrieve the saved
  result. Client risk/equity/capacity injection is rejected. An alternate
  synthetic EOD configuration uses the same port and sizing integration.
  General personal-capital and other drawdown policies still require separate
  implementations. The risk engine contains no TCP25 ratios or balance bands.
- READY and QUALIFIED remain intermediate checks. Final advice is WAIT or
  NO TRADE, and both permission flags remain false. No order route, broker
  integration, new service/topic or dependency was added. The policy freshness
  controls explicitly reuse existing journal ceilings (1800 seconds/30 days);
  they are not calibrated production SLOs.

This is a tested G6 foundation, not a complete rule-exact simulator or proof of
account readiness. G7/G8/G10/G11/G12/G13 still require licensed historical data,
qualified positive OOS edge, path distributions, simulations and complete paper
evaluations. The official account progression table remains an external input;
no remaining statistical or account limit is guessed. The next independent
foundation is isolated account roles and reserve locking, followed by strategy
registry/interface validation. The goal remains active.

Verification: the final mocked suite passes **1,474 tests**, with 53 real-service
opt-ins skipped and **78.56%** aggregate branch-aware coverage. Policy, risk,
account/evaluation, data/event guards, selector, replay and advisory service each
have **100% statement and branch coverage**. The earlier combined focused run
passed 535 tests; the final malformed-input regression and eight related service
checks pass after pre-arithmetic revalidation. Repository Ruff, changed-file
Black/isort, architecture boundaries, strict MyPy over 109 source files and
active requirement metadata for 411 installed distributions pass. No runtime
broker/account state or actual environment secrets were changed.

## Isolated initial account roles (2026-10-06)

The existing journal already isolates financial histories and the selector
already captures strategy, risk, edge/fit and dataset versions. No champion,
challenger or reserve permissions existed. This phase extends the account domain
and existing settings table, then applies the role gate to both account sizing
routes. Ten existing files were checkpointed; one new test file verifies the
behavior. Evidence and the reviewed patch are under
`artifacts/tcp25-goal/account-profiles/`.

- One explicit plan maps logical B/A/C slots to three distinct financial journal
  IDs. Names do not infer roles. B is champion, A stays shadow-only while B's
  workflow is unproven, and C remains locked. There is no unlock, promotion,
  assignment or copying API. The initial schema cannot claim proven workflow
  or silently enable reserve/copying behavior.
- B needs an exact per-market assignment: strategy/version, risk ID/version,
  evaluation policy/version, cost model, edge/fit IDs/versions and dataset hash.
  Server-owned installation joins assignments to qualified reported saved
  comparisons; source time/key identity is validated through the shared store
  helper. The research record supplies risk ID but lacks a risk-version field;
  that declared version is joined to the actual risk configuration at decision
  time. A future authoritative registry must authenticate parameter/version
  provenance rather than trusting labels.
- No best actual configuration is selected by this phase. Genuine approval,
  globally highest validated pass probability, workflow proof and evidence-based
  promotion remain unresolved. A test explicitly demonstrates that reported
  historical labels can satisfy metadata checks without authenticating licensed
  data or statistical results. READY is an intermediate identity gate, never
  proof of genuine edge or trading permission.
- The plan contains no balances, PnL or dollar budgets. All financial amounts
  come from the requested journal alone. Account, sessions and plan are read from
  one SQLite transaction, and reacquired after either source reader. A revision
  change during acquisition cannot reuse an old configuration assignment.
- Plan writes reuse the existing settings table and `BEGIN IMMEDIATE`. Updates
  require the prior SHA256 revision, a new version and later known-at time;
  journal/slot bindings, plan identity and synthetic/reported scope are immutable.
  Idempotent writes are allowed. Competing initializers cannot overwrite one
  another. Missing/corrupt journal references or comparison records are rejected
  without fallback or automatic repair. Actual runtime storage is not modified.
- Final risk checks record the plan, requested configuration, role, reason set
  and plan revision. Missing/invalid assignments, current/synthetic mixing,
  unbound accounts, A and C force zero size. All previous financial/data/event
  and policy gates still apply. Saved positive checks reproduce at the original
  clock. Role-scoped checks use `role-scoped-structural-risk-v2`; removing their
  role provenance cannot silently turn them into legacy unscoped calculations.
- Three red API regressions reproduced positive legacy planner size for B/A/C
  without role/configuration checks. The account-scoped legacy route now denies
  role-enforced planning because its request lacks strategy/research identity.
  Pure general worksheet arithmetic remains verified when no role plan is bound.
  Other red tests reproduced lost saved role scope and a comparison time/key
  mismatch during assignment; both now fail closed.
- The default advisory service requires a plan, with none installed implicitly.
  GET account-plan exposes bounded configuration metadata/revision only. Client
  role/plan/permission/workflow injection is rejected. B, A and C never combine
  balances or copy trades; no producer, execution dependency, new agent, topic,
  database, dependency or frontend polling loop was added.

Account B is not ready. Licensed futures/OOS evidence and the official account
progression table remain external inputs. G7/G8/G10/G11/G12/G13 are not achieved,
and full decision-ledger, governance, replay and operations work remain. The next
foundation is strategy/interface and registry inspection, reusing actual strategy
calculations while preventing reported APPROVED labels from replacing validated
registry evidence. The goal remains active.

Final verification: **1,528 mocked tests pass**, with 53 service opt-ins skipped,
511 warnings and **79.01%** aggregate branch-aware coverage. Account, risk,
policy/evaluation, data/event guards, selector, replay and advisory service each
retain **100% statement and branch coverage**. The combined focused run passed
580 cases before the last route/boundary additions; all later cases pass in the
full suite. Eighty reproducible generated balance/role scenarios, exact timestamp
epsilon checks, concurrent initializers, mid-read updates and three red/green
provenance/route regressions protect the new behavior. Ruff, Black/isort,
architecture, strict MyPy over 109 sources and active requirement consistency
for 411 installed distributions pass. No actual .env, broker orders, running
agent stack, licensed dataset or financial account state was changed.

## Shared first strategy rule and guarded experimental records (2026-10-06)

Inspection found that Tier-4 entry calculations live inside order-capable agent
classes. Most `generate_signal` hooks are empty, strategy IDs lack complete
parameter/period/version manifests, and no lifecycle registry exists. The
backtesting engine reuses recorded returns and walk-forward types but simulates
long-only percentage cash positions. That is not a futures/TCP25 simulator.
The current reuse audit identified these specific parity gaps:

- Breakout live evaluation includes the immediate preceding bar; its backtest
  skipped that bar, used shorter warmup and acted at the signal-generating close.
  Both paths treated zero average volume as confirmation. These two rule defects
  were reproduced before extraction.
- Trend backtest ignores the requested Donchian period; live stateful trailing
  exits are absent from its historical approximation. Mean-reversion backtest
  omits the live Hurst gate and short/stop behavior. Momentum backtest is a
  single-series approximation of the live cross-sectional rebalance. These
  families were inspected but not silently rewritten or declared validated.

The coherent migration moves the actual breakout range/volume calculation into
`core.strategy_signals`. Nine existing paths were checkpointed (including the
unchanged behavior-test fixture); one shared source module and one focused test
file are new. The later report-persistence changes were preserved separately
before editing. Evidence and full diff are in
`artifacts/tcp25-goal/strategy-interface/`.

- The pure kernel has a typed bar interface, frozen explicit parameters and
  frozen numeric features. It has no provider, clock, account, AI, state or order
  dependency. Code version is `range-volume-v1`; callers capture parameter values.
  No one-file-per-market implementation or new runtime agent/topic is added.
- Both the existing agent and its backtest call the same kernel. Previous N bars
  include the immediate prior bar and exclude the current signal bar; strict
  high/low crossing and inclusive volume confirmation use Decimal comparisons.
  A zero volume baseline stays unknown, invalid numeric inputs raise, and warmup
  includes N previous bars plus current observation. Legacy defaults are 20/30/2;
  they are inherited research parameters, not calibrated prop-fit settings.
- Backtest signals shift one bar before the existing next-close execution proxy.
  Only bounded warmup slices are copied, avoiding growing-prefix allocations.
  The engine still opens long positions and treats sell direction as an exit;
  ATR trails, short fills, gap/intratrade paths, futures costs/margin and exact
  evaluation rules are not implemented by this change. Earlier breakout results
  must be regenerated; behavioral/performance equivalence is not claimed.
- The existing report path captures daily experimental checks through the same
  data/event guards and kernel used by replay/current inputs. Non-daily intervals,
  unhealthy/unknown data, missing calendar/policy, insufficient warmup, unknown
  volume and computation faults expose no directional features. All nine research
  markets use the same rule. Daily synthetic fixtures do not authenticate actual
  exchange sessions, entitlement, contract listing, price plausibility or edge.
- Directional BUY/SELL fields describe experimental features. Advice remains
  WAIT/NO TRADE, lifecycle is fixed EXPERIMENT, and both permission flags remain
  false. No quantity, budget, broker proposal or approval can be added to this
  output. Registry-approved strategy recommendations remain unimplemented.
- Positive feature records reproduce guards and numeric results from captured
  source snapshots at the original clock. Red tests showed that copied future
  price clocks/incomplete calendars could previously retain positive guard tags;
  these copies now fail validation. Frozen outer objects alone are insufficient.
- Red persistence tests showed raw report save/read accepted corrupted features.
  The existing store now validates reports before writing and after parsing, and
  joins report ID/time/instrument to its stored keys. Missing old optional signal
  fields default safely. Invalid saved reports return an explicit protected API
  error. Research retention stays 100, with no new database/table; this is not a
  complete financial decision ledger or authenticated statistical approval.

The external read-only Git check confirms metadata is missing. The empty `.git`
visible inside the sandbox is a visibility artifact, not restored history. No
Git initialization, reset, cleanup or local-work discard occurred. Tests use
synthetic isolated fixtures; actual environment, accounts, broker orders and
agent runtime are unchanged. No dependency was added.

The goal remains active. This is one shared entry-rule interface, not migration
of all strategies or G7/G9/G10/G11/G12/G13 completion. The next highest-value
foundation is an authoritative versioned strategy definition/lifecycle registry
with TRAIN/VALIDATION/OOS manifests and evidence joins, so reported APPROVED labels
cannot stand in for validated immutable strategy/configuration records. Genuine
licensed futures data, official progression bands, positive OOS edge, path-risk
quantification, exact simulations and complete paper evaluations remain absent.

Final verification: **1,588 tests pass**, with 53 explicit service opt-ins skipped,
520 warnings and **79.67%** aggregate branch-aware coverage. The shared kernel
and new guarded-check/model-validation paths have **100% meaningful statement
and branch coverage**; existing analysis retains 97.99%, with one legacy
nonpositive scenario-target branch unexercised. Legacy breakout-agent coverage
is 88.89%; unrelated lifecycle/sizing/helper paths remain, so full agent or trade
parity is not claimed. Existing critical account/risk/policy/data/event/selector,
replay and advisory service paths retain 100%. The expanded focused run passed
676 cases before the final persistence additions; all later cases pass in the
full suite. Eighty reproducible generated direction/volume scenarios, epsilon
checks, prefix causality, all nine roots, position exits, copied guard faults and
save/read corruption cases protect the migrated behavior. Ruff, Black/isort,
architecture, strict MyPy over 110 source files and active requirement metadata
for 411 installed distributions pass.

## Immutable first strategy definitions and risk provenance (2026-10-06)

The previous turn made verified progress on the shared kernel and guarded report
persistence. Current inspection confirms the selector still validates *reported*
edge/fit revisions, including a reported APPROVED field. No durable strategy
parameter/version/research-split registry previously existed. These nominations
are research comparisons; their schema checks do not authenticate lifecycle,
license, code identity or positive edge.

This phase adds `core/advisory/strategies.py` for the first migrated daily
range/volume kernel. It reuses the existing typed `BreakoutParameters`, frozen
advisory evidence model, UTC comparisons and catalog validation. Definition
version is separate from kernel code version. A definition records parameters,
code version/reported SHA256, supported roots, registration clock, source and
reported/synthetic origin. Optional research plans record dataset identity/SHA256
and chronological, strictly disjoint TRAIN/VALIDATION/OOS partitions within a
research period. An absent plan remains absent. Neither a planned split nor a
reported digest proves untuned holdout, executable-code identity, licensed data,
measured metrics or statistical validation.

- Experiment admission and explicit retirement reuse the store's `settings` key;
  no agent, topic, database, SQL table, runtime service or dependency was added.
  The registry envelope stores a canonical content revision and validates every
  nested record on read. BEGIN IMMEDIATE plus compare-and-swap prevents stale
  writers; identity, parameters and plan cannot change under an existing version.
  Retirement retains the initial event and cannot revive the same version.
- Capacity is 100 versions, reusing the existing bounded research convention.
  Overflow rejects atomically without evicting definitions or retirement history.
  This is an experiment registry, not the final long-term decision ledger.
- No write/promotion HTTP endpoint exists. EXPERIMENT and RETIRED are the only
  available transitions. BACKTESTED through APPROVED require an evidence-producing
  workflow; reported status strings cannot promote a record. No actual strategy
  definition, dataset, account assignment or approval was installed.
- Structural risk now requires registry provenance by default. Missing definitions
  stay UNKNOWN; experiment/retired records stay BLOCKED. Both suggest zero contracts
  and NO TRADE, and capture the registry record and assessment clock. The v3 risk
  algorithm version prevents silently dropping that scope while retaining its
  schema. Account/financial state, account plan and strategy registry share one
  read transaction; readers overlapping a retirement cause a final reread.
- Existing v1/v2 saved partial math checks remain readable and retain WAIT with
  false permissions. Isolated arithmetic/policy fixtures explicitly disable the
  new scope. Production composition keeps it required; supplying an existing
  registry enforces it even when the isolated-math flag is false.
- Review reproduced a legacy `/plan` bypass: disabling account roles yielded a
  positive worksheet despite the required registry and missing strategy identity.
  A red HTTP 200 regression now becomes explicit HTTP 400 NO TRADE. The route reads
  the same durable context and blocks under registry scope or stored definitions.
  Standalone arithmetic remains possible only with both scopes disabled and no
  bound records; clients cannot inject either scope, approval or a registry.

Nine existing paths were preserved before edits, along with previous-phase source
hash verification. Git status/diff/log/branches/remotes still cannot be recovered:
external checks report missing Git metadata, while the sandbox shows a placeholder.
No reset, initialization, cleanup, discarded work or secret/runtime change occurred.
The initial isolated async test stalled in the sandbox; its exact live PID was
confirmed and terminated before the successful thread-enabled retry. Real service
opt-ins remain removed. Evidence is in `artifacts/tcp25-goal/strategy-registry/`.

The goal remains active. This closes a reported-approval provenance gap at risk;
it does not implement the whole strategy lifecycle or satisfy G7/G8/G9/G10/G11/
G12/G13. Other strategy families, registered-definition-driven research runs,
verified code/dataset manifests, genuine metrics, licensed futures/OOS data,
official progression bands, path-risk distributions, exact TCP25 simulations and
complete paper evaluations remain. Next is an evidence-producing historical run
for the shared rule, bound to immutable definition, split and realistic contract
costs, rather than adding a manual promotion flag or accepting claimed statistics.

Final verification: **1,647 tests pass**, 53 explicit service opt-ins are skipped,
and 520 warnings remain. Aggregate branch-aware coverage is **79.81%**. The new
strategy registry, risk, account, policy/evaluation, data/event guards, selector,
replay and advisory service each have **100% statement and branch coverage**.
Every newly added registry-store path is covered; overall store coverage is
98.96%, with two unrelated existing profile/session capacity-error paths missing.
The focused registry/API run passes 86 cases, including the repaired planner
regression; reproducible property tests exercise 80 parameter configurations.
Ruff, Black/isort, six-package architecture checks, strict MyPy over 111 sources
and active requirement consistency for 411 installed distributions pass. The
preserved nine existing files and the reviewed eleven-path diff are SHA256-backed.

## Recorded loss-streak probability tooling (2026-10-06)

The previous registry phase was verified progress. Follow-up inspection of the
actual backtest engine, shared kernel, replay provider and legacy agent found a
prerequisite for a defensible futures evidence run: the registered rule defines
entry features but lacks a complete immutable exit/fill model. The existing
engine trades long-only percentage cash; the agent uses ATR-based stateful exits,
while the historical approximation does not. Adding invented exits or treating
those cash outputs as futures edge would conceal the gap. The next action was
therefore adjusted to a required, independently verifiable foundation that can
use existing recorded net returns without claiming futures validation.

`backtesting/path_risk.py` and `BacktestEngine.loss_streaks` reuse the existing
`BacktestResult.trade_returns`, NumPy dependency/seed conventions, conservative
nonpositive-loss convention and selector's `LosingStreakEstimate` contract. There
is no parallel live risk system, registry promotion, new service/topic/database,
market adapter or dependency. Existing `monte_carlo` and `validate_all` behavior
is retained; this experimental probe is not part of the legacy go-live decision.

- The IID absorbing-state recurrence measures at least k consecutive losses
  anywhere in n trades, accounting for overlapping opportunities. It uses local
  Decimal precision 50 and bounds public work to 1,000,000 state updates. With a
  hypothetical independent loss probability of 0.5, two losses somewhere in ten
  trades have probability 0.859375; 0.25 applies only to one fixed two-trade block.
  This exact conditional model is not an estimate of actual strategy independence.
- The empirical baseline loss fraction comes from recorded net outcome signs,
  never a claimed win rate or reported maximum streak. Both baseline and block
  bootstrap produce all 16 required 2/3/4/5+ by 10/25/50/100 cells. Longest-run
  histograms include zero and the full horizon; prefix horizons share the same
  sampled paths, keeping horizon comparisons coherent.
- Non-circular blocks sample uniformly from valid contiguous starts, concatenate
  complete ordered blocks and truncate the last block. Dependence is retained
  within sampled blocks only; joins break it, and endpoints are sampled differently
  from interior observations. Explicit block length, simulations and uint64 seed
  are required. Block length 1 is an IID-resampling sensitivity case, not a default.
  No calibrated block size or confidence interval for true future risk is claimed.
- The probe validates complete history counts, finite net fractions >= -1
  and a positive period. It treats supplied sequence order as recorded order;
  absent per-trade timestamps prevent authenticating chronology. It supports at most 10,000 recorded trades and 100,000
  bootstrap paths, each at most 100 signs. Only a Boolean path matrix is retained;
  a giant integer index matrix is avoided. These are implementation bounds, not
  measured production SLOs or statistical minimum samples.
- Missing, malformed, oversized or invalid-period histories return UNKNOWN with
  no source/probability table, rather than substituting a synthetic distribution
  or false zero probabilities. Red tests reproduced copied scalar/mapping histories
  and string periods crashing or being silently normalized; they now fail closed.
  Untyped records and invalid configuration are explicit errors.
- Valid studies capture a detached backtest snapshot, content SHA256, configuration,
  algorithm version, loss convention and bootstrap method. Parsing re-computes
  source digest, all probabilities and histograms. A mutable nested legacy source
  must still be revalidated; frozen outer objects alone do not prove integrity.
  The digest is content consistency, not data authenticity, license or OOS proof.
- Every study stays EXPERIMENT with false trade/execution permissions. The scope
  explicitly identifies generic cash-backtest path risk. No study is installed as
  strategy edge, market selection, account B configuration or policy allowance.

Verification uses exhaustive binary-sequence enumeration for horizons 0..8 and
run lengths 1..5 at five probabilities; a separate Python grouping/block oracle;
all-win/all-loss support; alternating versus clustered histories with identical
loss fractions; 80 reproducible monotonicity/property scenarios; micro-probability,
net-zero/-1, count, clock and capacity boundaries; seeded round trips and copied
source/configuration/result faults. Selecting a dotted coverage module caused
NumPy `_NoValueType` failures in existing fixtures before the probe ran; selecting
the backtesting source directory passed. No dependency was changed to work around
instrumentation. Both the failure and successful verification are preserved.

Three existing files were checkpointed and previous phase hashes rechecked. Git
metadata remains unavailable; no destructive Git operation was used. No actual
runtime, environment, accounts, licensed dataset or strategy registration changed.

Final verification: **1,748 tests pass**, 53 service opt-ins skipped, 520 warnings,
and **80.40%** combined statement/branch coverage including the advisory service
and backtesting source directory. The new probe has **100% statement and branch
coverage**; legacy backtest engine coverage is 94.67%, with unrelated existing
paths remaining. Critical account/risk/policy/evaluation/data/event/selector,
strategy registry, shared kernel, replay and advisory service paths retain 100%.
The focused arithmetic/backtest run passes 158 cases. Ruff, Black/isort,
six-package architecture, strict MyPy over 112 source files and active requirements
for 411 installed distributions pass. Evidence and full reviewed diff are in
`artifacts/tcp25-goal/path-risk/`.

The goal remains active. G7/G8/G10/G11/G12/G13 still need genuine outcomes and full
verification; these synthetic mathematical checks do not quantify actual market
path risk or TCP25 pass probability. Day/regime/cross-market dependence, tail-loss
magnitudes, rule paths and evaluation economics are not modeled here. Next is a
complete shared trade-management definition for the first migrated strategy,
verified against existing behavior, before producing futures outcomes with
realistic costs and binding those outcomes to the immutable research splits.

## Shared seeded ATR and experimental trade-management rules (2026-10-06)

The loss-streak phase made verified progress. Current inspection of the breakout
agent, its tests, shared entry kernel, report guards and registry confirmed the
actual management rules: 2×ATR initial stop, proposed 3R target, close crossing the
existing trailing stop with strict inequality, and a ratchet that never loosens.
The local agent does not test its proposed target. Its `_exit` clears local intent
and records a loss for every trailing exit; it does not establish executed PnL or
emit a confirmed close fill. Those legacy limitations remain explicit.

Inspection of installed primary source (`pandas-ta 0.4.71b0`, TA-Lib absent)
confirmed the non-TA-Lib convention: first true range high-low, mean of the first
N ranges as seed, then recursive RMA with alpha 1/N. The library may otherwise
choose another backend, and its zero-range epsilon can create artificial tiny
volatility. The agent also fell back to 2% of price when its ATR column was absent,
and interpreted missing current price as zero in `should_exit`. Three regression
cases executed against preserved source reproduced all three unsafe behaviors.

The coherent extraction extends `core/strategy_signals.py`; no parallel runtime
strategy, agent, provider, topic, database or dependency was added.

- `ATRManagementParameters` pins period, bounded history window, stop multiplier,
  proposed target R, ATR method and strict-close exit rule. Nested instances are
  revalidated, and all parameters are explicit. Legacy values 14/200/2/3 are
  inherited experimental settings, not calibrated evaluation configuration.
- Seeded ATR uses local Decimal precision 50, with no epsilon or guessed price
  fraction. It recalculates from at most the declared history window. Standard
  nonflat sequences match the inspected library backend to the stated numeric
  tolerance (absolute 1e-11 / relative 1e-12); bitwise float equivalence, alternate
  backend equivalence and artificial flat-range behavior are not claimed.
- Initial geometry and trailing decisions use version `atr-close-trail-v1` and
  local precision 80. Negative, nondirectional or numerically unrepresentable
  stop/target geometry is rejected. Geometry is calculated before the legacy
  sizing read; no contract quantity or risk-budget authority enters the helper.
  Outputs are unrounded, EXPERIMENT, with false permission fields.
- An existing stop is tested before a new candidate. Equality does not exit; long
  stops only rise and short stops only fall. Unknown/invalid ATR produces NO_TRADE
  and retains the existing stop if not crossed. A known crossing can still produce
  a numerical EXIT decision, with no order capability. Missing/invalid position
  side, stop or price cannot be treated as a short position or zero-priced exit.
- The legacy agent's entry, ratchet, close-exit test and current indicator bridge
  call the shared rules. Missing ATR/invalid geometry blocks entry before reading
  allocation or mutating intent. Only the current ATR cell is populated by the
  bridge, since no other cell is consumed there. Legacy proposal serialization
  still uses float/two-decimal rounding and its existing allocation/execution
  interfaces; this is not futures tick conversion, fill/risk parity or readiness.
- Strategy definitions gain optional immutable management parameters. Adding or
  changing them needs a new definition version. Absent management is omitted by
  the definition serializer, preserving preexisting entry-only registry hashes.
  A raw old-format stored envelope was reopened without repair or revision change.
  Declared ATR history must accommodate both its seed and the strategy warmup.
- Guarded daily research reports capture management parameters, computed ATR and
  entry/stop/proposed target geometry only after the same data/event guards and
  directional kernel. Invalid/unknown management drops directional geometry and
  produces NO_TRADE. Neutral signals have no entry geometry. Positive copies must
  reproduce guards, features, ATR and geometry from captured source bars. Existing
  report save/read validation rejects corruption. Old optional reports remain
  entry-only; no registration, approval, sizing or financial account was installed.

Tests cover exact hand-derived seed updates, the installed backend at four ATR
periods and five historical cuts, bounded-window reset, prefix causality, all-flat
and corrupt inputs, both sides at stop ± epsilon/equality, unknown ATR with known
crossings, monotone stops, invalid side/price/intent state, actual indicator and
agent bridges, inherited proposal levels, 80 reproducible geometry scenarios,
local numeric-context independence, all nine research roots, replay/current
geometry parity, tampered saved reports and immutable/version/hash compatibility.

Final verification: **1,834 tests pass**, 53 service opt-ins skipped, 540 warnings,
and **80.72%** combined statement/branch coverage. Shared entry/management and
registry paths have **100% statement and branch coverage**, as do existing risk,
account, policy/evaluation, data/event, selector, path-risk, replay and advisory
service paths. New report-management validation paths are covered; full models
retain 98.05% and analysis 98.19%, with unrelated legacy branches missing. Legacy
breakout-agent coverage is 91.71%; remaining lifecycle/allocation/helper branches
are not silently claimed complete. The focused run passes 282 cases. Ruff,
Black/isort over six changed Python files, six-package architecture, strict MyPy
of 112 sources and requirement consistency for 411 distributions pass. Seven
existing files were SHA256-checkpointed before edits; source/diff/verification
are in `artifacts/tcp25-goal/trade-management/`.

Git metadata remains unavailable, with no initialization/reset/cleanup or local
work discarded. No actual .env, runtime agent stack, broker orders, account plan,
licensed dataset or registry record changed. Three old behaviors were tested
using the preserved module with mocked state/publication only.

The goal remains active. This verifies shared numerical management, not complete
trade execution or G7/G8/G9/G10/G11/G12/G13. The existing cash backtest still exits
on opposite directional signals, stays long-only and uses a next-close proxy;
no futures outcome was derived from it. Futures tick alignment, fees/spread,
slippage, gaps, intrabar stop/target ambiguity, contract/session calendars,
margin/policy and outcome accounting remain. Next is a futures research runner
that consumes these shared rules with an explicit fill/cost model and immutable
source/definition/split joins. Actual licensed/OOS evidence, official progression
bands, calibrated path risk, exact TCP25 simulations and complete paper evaluations
are still required; no positive edge or account B readiness is claimed.

## Experimental futures outcomes (2026-10-06)

The inherited cash backtest remains unchanged. `src/backtesting/futures.py`
now produces per-contract dollar and R outcomes for both directions using the
same range/volume entry, ATR geometry and strict-close trailing management as
the guarded research/agent interfaces. It reuses the replay adapter, data/event
guards, immutable strategy definition/research splits and catalog multipliers.
No agent, topic, broker integration, database, runtime endpoint or account plan
was added. This is a research fill model, not full live/backtest equivalence,
broker execution, protective intrabar stops or TCP25 simulation.

Inputs capture one dated daily contract stream, full snapshots/quality, event
calendar revisions, explicit event policy, strategy/code/parameter version,
TRAIN/VALIDATION/OOS plan, exact catalog specification and explicit fill costs.
The reported dataset hash must equal canonical ordered snapshot JSON including
quality and chunk structure, computed by `futures_dataset_digest`; raw CSV hashes
are a different convention. The rule hash must match `strategy_source_digest`.
The runner records its own hash and nine shared module hashes. These joins detect
version/data mismatches, not entitlement, origin authenticity, loaded-code
attestation, untouched holdout history or independent strategy approval.

`close-decision-next-open-v1` specifies close-known signals, following recorded
open fills, declared commission per side and adverse integer ticks per side.
Those ticks include any spread to be modeled; no extra implicit spread cost is
added. Neither zero nor synthetic costs are represented as measured broker costs.
BUY stops round down and SELL stops up. Original invalidation is preserved;
both the raw next open and its adverse fill must remain on the valid side. A
red test exposed a slippage-induced false recovery of an already invalid open;
the fixed runner rejects it. Stops ratchet monotonically, equality does not
cross, target geometry is informational, and intrabar stop/target touches do not
create fictitious fills. Close exits occur at the following open, so losses can
exceed 1R. Net PnL includes entry and exit slippage through fills and both
commissions; initial unit risk includes actual entry-to-rounded-stop distance,
exit adverse ticks and both commissions, without double-counting entry slippage.
This is risk normalization, not a guaranteed maximum loss or allowed position size.

Each split starts flat and permits earlier prices only for warmup. Trades never
consume an open outside their split. Pending final signals are skipped/censored;
open positions are censored without forced liquidation or fabricated PnL.
Unknown/unhealthy position data, unknown management and invalid exit fills also
censor. Missing calendar/event facts block entries. Event restrictions do not
hide known position exits with healthy prices. A next-open time gap exceeding
one second lacks session authority and skips entries or censors exits. The data
guard still rejects unknown historical CME session gaps. No roll, expiration,
margin, trading-hours or holiday assumptions were inferred.

The ledger records source/calendar digests, guard results, features, geometry,
management steps, actions, fill observations, closed outcomes and censor reasons.
Full calendars/policy are stored once in inputs, with compact event assessments
per decision. `COMPLETE` describes fully observed calculation under this model;
it is not evidence of edge, readiness or passing an evaluation, and can contain
no trades. `INCOMPLETE` paths must not become a supposedly unbiased trade sample.
Saved JSON must pass `await verify_futures_run(...)`, which revalidates inputs
and reruns every decision, fill, cost and outcome. Constructor validation alone
does not verify full computed paths. Changed code/catalog or tampered outcomes
are rejected rather than silently adapted to a new version.

Meaningful verification includes independent long/short PnL and R calculations
for all nine research roots, a profitable close exit, cost monotonicity and
direction symmetry, outward rounding, untouched invalidation under entry gaps,
data disconnection, explicit event exits, unknown ATR fault injection,
nonpositive exit fills, missing session authority, partial/empty splits,
partition-end entry/exit censorship, bounded archive inputs, old/new chunk
outcome parity, holdout causality, input detachment, numeric-context independence,
byte-identical reruns and corruption of outcomes, fills, decisions, dependencies,
state and input digests. The preserved synthetic MES artifact records one
negative trade in each split: -44.50 USD. It is not actual strategy evidence.

The goal remains active. G7/G8/G9/G10/G11/G12/G13 are not fully established by
synthetic outcomes. Next is measured edge/path evidence derived from these
verified net contract outcomes, separately from prop-firm fit. Actual licensed
OOS data, realistic measured costs, verified session authority, official
progression bands, rule-exact TCP25 simulation/Monte Carlo, walk-forward and
multiple complete paper evaluations remain required.

Final checks for this increment: **1,903 passed**, 53 external-service opt-ins
skipped, 540 warnings, 64.04 seconds, **81.10%** combined statement/branch coverage.
The new futures runner has 100% statements and branches. Existing critical
advisory risk/account/policy/data/event/selector/registry/shared strategy/path-risk/
replay/service paths retain 100% coverage. Ruff, Black/isort for two new Python
paths, six-package architecture, strict MyPy over 113 sources and consistency of
411 installed dependency distributions pass. The focused shared-rule/regression
run passes 315 cases. An initial full collection failed to resolve repository
`tests`/`scripts`; its output is preserved. Explicit `PYTHONPATH=src:.` with
`.venv/bin/python -m pytest` resolves it without changing source or dependencies.
The complete suite was repeated after compacting event results so calendar/policy
bodies appear only once in saved inputs. No actual environment, broker/runtime
agent, licensed data, registered strategy, account assignment or trading state
changed. Git metadata is still missing outside the sandbox; no history was
invented or reset. Two existing documentation paths were checkpointed, two new
Python paths are captured in the diff, and verification/source hashes, synthetic
JSON and command outputs are preserved under `artifacts/tcp25-goal/futures-research/`.

## Descriptive net futures statistics and shared path math (2026-10-06)

`futures_edge_analysis` first replays a captured futures run, then calculates
separate TRAIN, VALIDATION and OOS summaries from complete net contract outcomes.
The capital/allocation/mark-to-market cash metrics in the inherited backtester
remain unchanged. No arbitrary capital or drawdown percentage was invented for
the futures sample. Incomplete paths yield UNKNOWN without selecting their
completed trades; complete no-trade periods also yield UNKNOWN. This prevents
quietly dropping censored losses to manufacture an apparently profitable sample.

The versioned statistics include strict positive/negative/flat counts, win
fraction, signed mean winners/losers, mean/median/min/max R, sample variance
(n-1), standard deviation, adjusted sample skew, inverse-empirical-CDF 5%
quantile and fractional worst-5% expected shortfall loss. For n<2 variance/std
are unknown; for n<3 or zero variance skew is unknown. The adjusted skew uses
sqrt(n(n-1))/(n-2) times the population third central moment divided by the
population variance to the 3/2 power. Expected shortfall weights the boundary
observation fractionally instead of averaging a rounded-up number of trades;
positive worst-tail returns produce zero loss, with their signed quantile still
recorded. These empirical descriptions confer no tail confidence or forecast.

R and USD profit factors are distinct because per-contract structural risk can
vary by trade. No-loss and all-flat denominators are explicitly undefined/null,
not Infinity or a fabricated zero. Total net dollars, commissions and adverse
slippage dollars are retained. R expectancy is not substituted for actual
account profitability, allocation, percentage return or evaluation economics.
Closed-trade drawdown uses additive cumulative R and per-contract USD paths with
initial zero, not allocated NAV or intratrade marks. Recovery episodes retain
peak/trough indices, possible equality-or-higher recovery, last observation,
maximum depth, elapsed observed trades/calendar days and current unrecovered
depth. The initial peak timestamp is the partition start, so an initial loss
duration can include pre-trade waiting. Commission timing and intratrade risk
are not modeled by this closed-outcome path. It cannot enforce TCP25 breaches.

The preexisting absorbing IID recurrence and non-circular contiguous-block
bootstrap were extracted as `recorded_loss_run_tables`. Cash input validation
and results remain intact; the shared math now accepts finite signed Decimal
outcomes, including legitimate futures losses below -1R. Zero is conservatively
nonpositive for loss runs. Futures studies produce the same 16 horizon/run cells
and longest-run histograms, using explicit block length, simulations and seed.
A block longer than a split's history yields UNKNOWN path tables while retaining
descriptive metrics. IID probabilities are conditional on the empirical loss
fraction; bootstrap retains ordering inside blocks only, not independent block
joins, regimes, trading-day clusters or cross-market correlations. Thin samples
can produce 0/1 tables without establishing calibrated future probabilities.

`FuturesEdgeStudy` captures the source/run digest, configuration and recomputed
statistics. Saved artifacts require `verify_futures_edge_study`, which verifies
both the underlying fill/source paths and their summaries. A deliberately
self-consistent forged summary passed arithmetic construction but was rejected
when the underlying fills/PnL were replayed. Source-path verification is thus
mandatory, not replaced by a checksum or matching descriptive calculations.
The shared path module is now included among ten implementation fingerprints.
Prior phase artifacts remain pinned to their original code; they are preserved,
not silently rewritten to pass new fingerprints. The current synthetic example
is `artifacts/tcp25-goal/futures-edge/synthetic-MES-edge.json` with its full run
in `source`. Its four trades per split total -108 USD, an intentionally negative
synthetic sample, not untouched OOS data or real market evidence.

The lifecycle remains EXPERIMENT and validation state UNVALIDATED, even with
positive sample expectancy. All trade/execution permissions remain false. No
market-selector evidence, account configuration, registry promotion, real data,
broker connector, runtime endpoint, message topic, database or dependency was
installed. Licensed data and measured costs, valid holdout provenance, bootstrap
uncertainty and chronological walk-forward, exact TCP25 policy simulation,
Monte Carlo/optimization and complete paper evaluations are still required.
G7/G8/G9/G10/G11/G12/G13 remain unproven as whole gates. Next is uncertainty and
walk-forward evidence on the verified outcome workflow before approval.

Final evidence for this increment: **1,951 tests pass**, 53 real-service opt-ins
skipped, 540 warnings, 76.34 seconds and **81.35%** combined statement/branch
coverage. Futures outcomes/statistics and shared path-risk math have 100%
statement/branch coverage; existing critical advisory risk/account/policy/data/
event/selector/registry/shared strategy/replay/service modules retain 100%.
Focused statistics/futures/path regressions pass 218 cases, including 70
Fraction/path property examples, independent moment/tail/recovery calculations,
all nine roots, explicit undefined/small-sample boundaries, cash-table identity,
signed outcomes below -1R, source/result tampering, incomplete-path exclusion,
holdout causality and low numeric-context replay. Ruff, Black/isort for four
changed Python paths, six-package architecture, strict MyPy over 113 sources
and dependency consistency for 411 distributions pass. Initial automatic test
approval review timed out before starting; one authorized retry ran successfully.
An import-format correction was followed by full final verification. Five
existing files were preserved with SHA256 before edits; one test file was added.
Diff, final hashes, synthetic JSON and command outputs are in
`artifacts/tcp25-goal/futures-edge/`. Real Git metadata remains missing, with no
initialization/reset/cleanup or work discarded. No actual environment, agent
stack, broker, account state, licensed data or registered strategy changed.

## Paired mean uncertainty and fixed-rule chronological windows (2026-10-06)

The shared block-start generator now drives both the existing loss-run tables
and full-history paired bootstrap means. Existing cash sign-table/RNG behavior
is unchanged. `paired_block_bootstrap_means` samples non-circular contiguous
blocks with the same starts for R and USD, truncates the final block, and returns
means at the original history length. It uses Decimal prefix sums with pinned
precision rather than a giant observation-by-resample index matrix. Aligned
finite Decimal sequences, block feasibility and a ten-million-sampled-value
work limit are checked before allocation. This does not extend the source
history to 100 trades as the separate loss-run probe does.

`backtesting.validation` reuses the verified futures outcomes/statistics workflow
and adds explicit mean uncertainty and declared chronological windows. Its new
module is justified by this research-validation orchestration; it does not add
a strategy engine, capital/risk system, agent, broker adapter or service.
Configuration declares block length, simulations, seed, nominal confidence and
minimum observations. Two-sided percentile endpoints use probabilities (1-c)/2
and (1+c)/2 and linear interpolation at (m-1)p. The general percentile procedure
is referenced in the [SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html);
the project's sampler uses dependent blocks rather than SciPy's ordinary
resampling, and does not call SciPy or claim BCa/calibrated coverage. Bootstrap
coverage remains explicitly false/unvalidated; a positive bound cannot approve
a strategy. Non-circular blocks reweight source endpoints and only preserve
within-block ordering. Bounds are not clamped to include the empirical mean.

Incomplete/no-trade sources, declared minimum not met, oversized blocks, a
single available block and excess work produce UNKNOWN bounds. Degenerate
mean distributions and coincident percentile endpoints also produce UNKNOWN
instead of positive zero-width confidence. Source points, sample sizes, sample
standard deviation and distribution digests are retained when supported. Only
digests, not every resample, are saved; source/configuration/seed reproduce them.
Runtime NumPy and validation-source SHA256 are captured and checked. Saved
uncertainty requires replay of both underlying fills and descriptive statistics,
then recomputation of paired sampling/bounds. Arithmetic checksums alone do not
authenticate a data source, real costs, untouched holdout or code loaded elsewhere.

`FuturesWalkPlan` joins exact parent input/definition revisions and declares 2–10
windows with existing TRAIN/VALIDATION/OOS split validation. Test windows are
chronological/disjoint and training moves forward. All windows must end inside
the development TRAIN/VALIDATION region before the reserved final OOS period.
Each temporary derived experiment retains the original numeric strategy and
management parameters, costs, instrument and guarded decision/fill rules. Its
research version is derived without modifying or installing a registry entry.
Archive records are cut at each test end and future-known calendar revisions
excluded before running that fold. Prior prices remain available for causal
warmup. Every split resets positions as in the common futures runner. This is
fixed-rule walk-forward, not trained/refitted models or parameter optimization.

No failed or thin window is skipped. Its captured outcomes and UNKNOWN metrics
remain in the result. No optimistic aggregate/validation verdict is produced.
`final_holdout_scope=not_evaluated_by_this_walk` describes this tool's calculation;
it does not attest that a researcher never viewed/tuned on that data elsewhere.
Saved walks require every declared fold and its exact prefix/configuration join,
then full rerun. A self-consistent forged fill label whose statistics/envelope
hashes still matched was rejected by the complete walk replay. Changing reserved
holdout prices leaves earlier fold statistics/bounds unchanged. Entirely future
archive chunks are excluded from fold inputs rather than silently exposed.

The current artifact is `artifacts/tcp25-goal/futures-validation/synthetic-MES-walk.json`.
It has two declared test windows, each with two synthetic trades; the net mean
is negative and nominal 90% resample bounds span negative and positive R. It
reopens and reproduces exactly, but gives no actual edge/regime-robustness or
account-readiness evidence. Previous artifacts remain pinned to their old
implementation fingerprints. No actual environment, agent stack, broker, account
plan/state, licensed dataset, registry record or dependency was changed.

G7/G8/G9/G10/G11/G12/G13 remain unproven as complete gates. Actual licensed
history, measured costs, valid holdout/selection provenance and calibrated
unseen-regime evidence remain required. Next is timed evaluation-event replay
against the existing replaceable policy, before claiming rule-exact TCP25
simulation, pass/fail Monte Carlo, optimization or complete paper evaluations.

Final verification: **2,015 pass**, 53 real-service opt-ins skipped, 540 warnings,
100.35 seconds, **81.67%** combined statement/branch coverage. New validation,
paired/shared path sampling and existing critical futures/strategy/advisory
risk/account/policy/data/event/selector/registry/replay/service paths have 100%
statements and branches. Focused regressions pass 282 cases, including 50 paired
sampling property examples, independent Python block/percentile oracles,
confidence ± epsilon, zero-width/degenerate/thin boundaries, nine roots, invalid
plans, exclusion of final/future records, retained failed folds, future mutation
causality and numeric-context/saved replay checks. Ruff, Black/isort for three
changed Python paths, six-package architecture, strict MyPy over 114 sources and
dependency consistency over 411 distributions pass. One synthetic test command
was not started when automatic approval review timed out; its single retry
succeeded. Three existing files were SHA256-checkpointed; two new source/test
files are captured in the diff. Source hashes, before-files, command results,
synthetic JSON and verification are in `artifacts/tcp25-goal/futures-validation/`.
Real Git metadata is still missing outside the sandbox; no history was invented,
initialized or reset, and no local work was discarded.

### Timed evaluation-event replay increment (2026-10-06)

Reused the authoritative journal's EOD arithmetic by extracting pure
`initial_eod_state` / `project_eod_session` functions in
`src/core/advisory/evaluation.py`. Account joins, freshness, clocks and corrupt
journal checks remain in `evaluation_status`; the mathematical functions grant
no permission. Repeated intraday/floor-sync snapshots project from one prior
settled balance, preventing duplicate PnL and trading-day counts.

Added `src/backtesting/evaluation.py` for declared OPEN/MARK/CLOSE, observed
working/cleared orders, SESSION_END and FLOOR_SYNC tapes. It performs Decimal
cash/mark-to-market accounting with actual supplied entry/exit prices and explicit
nonnegative commissions. Every event checks daily loss (including open PnL and
fees), the prior EOD floor, strict consistency, aggregate micro/standard exposure,
time-valid progression evidence, margin capacity and trading/flat deadlines.
It checks exposure at a closing fill's price before removing that position.
No hedging/netting or cross-market independence is assumed for contract limits.

Floor/peak update only at explicit session finalization; no intraday trailing,
no daily reset without a finalized session, no imagined settlement event.
Synchronized account floor evidence is required before entry and conditional
PASS. Missing/unconfirmed/future policy, calendar, ladder, margin, complete fills
or intraday-extrema coverage causes CENSORED. A known observed hard violation
terminates FAIL when financial history/policy support it. Margin conflicts are
unknown account capacity, not an invented firm failure. Consistency can delay a
pass while remaining CONTINUE. Session/calendar checks reuse Chicago/DST rules
and require supplied complete calendar coverage, including early closes.

Saved runs retain full policy/evidence/event revisions, financial/event checks,
canonical tape hash and implementation/shared-source fingerprints. Construction
and saved verification rerun the complete evaluated prefix, rejecting changed
cash/inventory/reasons/result and implementation revisions. Earlier artifacts
retain old fingerprints; they are not silently adapted to new shared code.

Official public progression and EOD pages were rechecked. Real-time aggregate
position regulation and EOD-only floor updates agree with this model. Numeric
TCP25 account ladder bands are still unavailable from that public guidance.
The simulator accepts explicit replaceable supplied bands, never guesses them.
Likewise it cannot prove an assertion that recorded marks capture unseen extrema.

Three saved synthetic examples reproduce: conditional four-day PASS ($1,792
net), the same path CENSORED without ladder evidence, and FAIL at exactly $550
daily net loss. Fabricated prices, ladder, calendar and margin are explicitly
labeled. These are not multiple completed paper TCP25 evaluations. Results remain
EXPERIMENT with rule_exact_verified/trade_permitted/execution_enabled false.
No broker, journal/account writes, registry, provider integration, runtime stack,
actual account plan, license, dependency or secret changed.

G7/G8/G9/G10/G11/G12/G13 remain unproven as whole gates. The next defensible step
is causal recorded research-path/event construction with honest intraday-extrema
and policy-evidence completeness, before rule-exact pass/fail distributions,
risk optimization/economics or real Account B claims. Authenticated official
account progression/calendar/margin and licensed source data remain necessary.

Verification: **2,112 passed**, 53 explicit external-service opt-ins skipped,
540 warnings, 98.69 seconds, **82.16%** combined statement/branch coverage.
Shared EOD/journal math has 100% statements and branches. The event simulator has
100% statements and 109/110 branches (99.09%); the remaining arc is the fallthrough
of an exhaustive validated event-kind dispatch. Existing 15 critical modules
retain 100% statements/branches. Focused journal/policy/event checks pass 221 cases
with independent cash/both-side catalog oracles, Hypothesis projection examples,
epsilon boundaries, realtime closing-price ladder checks, sticky/censored failures,
missing-settlement guards, DST, malformed events and result/source tampering.
Ruff, Black/isort on all three changed Python files, strict MyPy on 115 sources,
six-package architecture checks and 411-distribution dependency consistency pass.
Three prior files are checkpointed with SHA256; two new files and the exact diff
are retained under `artifacts/tcp25-goal/evaluation-events/`. Read-only checks
again confirm real Git metadata is absent. No Git initialization/reset/clean,
local-work discard or runtime/soak restart occurred.
