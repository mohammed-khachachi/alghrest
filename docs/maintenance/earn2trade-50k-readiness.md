## Capability mission registry — VERIFICATION PASSED; DOCKER RESTORATION PENDING (2026-10-13T09:50:34.090864+00:00)

The approved **23 paths** are implemented: five existing files changed, three new source/test files and fifteen archive/evidence files. Exact paths and before/after identities are in `artifacts/advisory-capability-registry-v1/source-manifest.json`; commands, diagnostics, replay and containment results are in `verification.json`. The five originals were archived byte-for-byte before edits and tests.

A single static mission registry covers all **40 non-package agent/helper source files**: **25 PLANNED, 5 CONTEXT_ONLY, 2 SUPPORT_ONLY and 8 EXCLUDED**. Each entry names its intended report role, required inputs, planned output and acceptance criteria. These states describe a migration contract, not observed runtime or completed adaptation. The existing five read-only context topics remain unchanged. Unsuitable on-chain and cross-exchange analysis, execution, copying and all four DeFi roles are explicitly excluded; suitable execution-path calculations are only candidates for later isolated extraction.

Authenticated `GET /assistant-api/capabilities` reads current source identities without importing or starting agents, using the existing middleware. Its registry always states `NOT_OBSERVED`, `NOT_ASSESSED`, `all_agents_integrated=false`, `trade_permitted=false` and `execution_enabled=false`. Missing, redirected, unmapped or changed source evidence is rejected; stale envelopes are preserved rather than patched. Renamed/duplicated roles, reconstructed positive flags and hypothetical confirmation cannot convert the catalog to a qualified signal. Verification repeats whole-file source checks per request; there is no persistent verification cache. Pre-existing API function bodies/signatures and test fixtures are unchanged; financial arithmetic, briefing evidence fields, the MES/MNQ-only **20 Micro total cap**, current **$1,100 daily-loss setting**, and official TCP50 blocked eligibility remain unchanged.

Verification: **2746 full-suite tests passed, zero failures/errors/skips, 562 warnings; coverage 84.47% against the unchanged 70% gate**. Focused tests: **400 passed, zero skips, 36 warnings**, overlapping with the full suite and not added to it. Ruff, Black check, isort check, strict MyPy (130 source files), all six architecture packages and TypeScript passed. isort's 13 configured file exclusions are disclosed. Dashboard source is unchanged; no new frontend/browser functionality was introduced or certified. Initial focused tests stalled in sandbox TestClient setup; a bounded 20-second diagnostic failed there, and the same API case passed outside the sandbox in 1.09 seconds. The focused and full receipts are the final successful runs; original diagnostics remain in /tmp and their details/commands are preserved in this receipt.

Fresh public verification passed for existing futures run/edge/walk envelopes with path replay, strict source hashes and exact comparison. The three legacy TCP25 outcomes remain separately **PASS, FAIL and CENSORED — SYNTHETIC MECHANICS ONLY**. Three unchanged briefing examples reopened and independently replayed successfully; their source identity set is unaffected, so they were not regenerated or rewritten. The new registry was serialized, reopened and independently verified. The inventory is a code/migration map, not trading-edge evidence.

All **1570 prior public artifact files**, five original archives and **137 existing htmlcov/.coverage files** were preserved. The monitored public-file inventory records only the approved 23 paths as changed/created. Credentials, private root data, private dependency/tool directories and database sidecars are excluded; this public inventory is not a claim of byte-level preservation of private mutable databases. Coverage data, explicit HTML destination `/tmp/alghrest-capability-registry/htmlcov`, JSON/XML reports, test temporary files, Hypothesis storage and tool caches stayed in /tmp; bytecode and pytest cache writes were disabled. Published JUnit copies remove hostname attributes and redact userinfo in one synthetic URL parameter from an existing redirect-denial test; originals remain in /tmp. The first independent secret-pattern scan flagged that synthetic parameter, which was redacted before final re-verification. The historical htmlcov exception cannot be certified retroactively because its earlier bytes were not hashed; earlier missing SQLite WAL/SHM files remain unreconciled. This increment does not hide either limitation.

After renewed explicit user authorization, only existing isolated PostgreSQL/Redis/Kafka quality services were started, then stopped. Docker service is still active/socket active; restoring its prior inactive service state requires the user’s local sudo stop command. The automated noninteractive stop failed because a password was required; test ports15432/16379/19092 are closed. Existing assistant8011/dashboard5173 remain available and were not restarted. The new API was tested in isolated TestClient applications; the user's existing API is not certified as reloaded. No broker mutation, order/cancellation/liquidation/copying, purchase, external message, paid model call, .env edit, failed-soak restart or new holdout access occurred.

Code, tests and evidence verification passed; this capability-registry increment is not fully closed until Docker restoration is independently confirmed. It does not complete adaptation of all agents, qualify a 5m/15m strategy, resolve permitted market-data coverage, or complete forward Paper evaluations. The staged mission remains evidence-led MES/MNQ reports for human decisions; current session briefings remain WAIT/NO_TRADE. Passing probability **UNKNOWN**. The compatible broader Goal remains **BLOCKED** in the tool, with no unsupported resume or completion claimed. **Stop for human review before further implementation or deployment.** The next bounded proposal should define qualified 5m/15m conditional-analysis inputs and deterministic invalidation/target rules before adapting strategy contributions.

---

## Workflow unification — VERIFIED; review checkpoint (2026-10-13T01:56:45.552958+00:00)

The approved **33 paths** are implemented: nine existing files changed, one new application module and 23 new evidence/archive files. The exact scope, before/after identities and preservation checks are in `artifacts/architecture-workflow-unification-v1/source-manifest.json`; exact commands and results are in `verification.json`. The nine original files were archived byte-for-byte **before edits and tests**. Historical sections below describe their own dated increments.

`src/api/services/briefings.py` now owns context collection and the report workflow: capture selected reviewed observation/account revisions, collect read-only context, recheck, calculate and save. Existing HTTP functions and signatures remain compatible adapters, including `_collect_context`. No route imports another route's helper. Financial arithmetic, source clocks, serialized evidence fields, the MES/MNQ-only **20 Micro total cap** and the current **$1,100** daily-loss setting are unchanged; the later $1,200 example has not been substituted.

Root cause corrected: cancelling `asyncio.to_thread` did not stop its SQLite writer. Three deterministic before probes returned “not saved” and then committed a report. The original regression failed before the correction. A request-local commit guard now cancels/rolls back a write that has not crossed its commit decision and checks its original monotonic deadline at that decision. A commit already underway is not claimed to be interruptible: its response explicitly reports an uncertain outcome and directs the user to history. A known committed record whose display fails is reported as saved. Each request gets a fresh guard; it is neither reusable evidence nor a persistent verification cache. The existing commit-time revision checks remain inside the transaction.

Verification: **2719 full-suite tests passed, zero failures/errors/skips, 562 warnings; coverage 84.43% with the unchanged 70% gate**. Focused regressions: **74 passed**, overlapping with the full suite, not added to it. All six frontend suites passed **110 cases**. Ruff, Black check, isort check, strict MyPy (**128 source files**), six-package architecture, TypeScript and production build passed. Browser checks: **12 passed** against the actual isolated API/store, including pre-commit timeout, commit uncertainty, delivery failure, preserved selection/history, authentication and mobile layout. The mobile screenshot was inspected. Browser inputs, empty context, fixed source clock, shortened test deadline and fault barriers were synthetic instrumentation; production remains at its existing 30-second deadline. The first browser harness attempt observed an old result before the retry finished; it was corrected to await the actual POST response and re-run successfully. Its failed receipt is retained in controls; the production build retains the Browserslist age warning.

Fresh public replay passed for the existing futures **run, edge and walk** artifacts. Legacy TCP25 outcomes were independently verified and reported separately as **PASS, FAIL and CENSORED — SYNTHETIC MECHANICS ONLY**. Three briefing examples were regenerated from their exact original inputs, clocks and cost/configuration/result fields; only new IDs and current source identities differ. Old changed-source envelopes are rejected, preserved and never patched. Three new envelopes and six actual temporary saved records were independently reopened in a separate process with strict source checks and exact replay. Trade and execution permission remained false; historical age was displayed without renewing the source price time.

Only the approved paths were written in the monitored public-file inventory; previous artifacts and current htmlcov/.coverage were preserved by byte comparison. Credentials, root private data, database sidecars, dependency/tool private directories are excluded from that public inventory. Coverage data, explicit HTML destination `/tmp/alghrest-workflow-unification/htmlcov`, JSON/XML reports, test temporary files, Hypothesis storage, build/browser files and caches stayed in /tmp; bytecode and pytest cache writes were disabled. Published JUnit copies remove hostname attributes; originals remain in /tmp. The **historical htmlcov exception cannot be certified retroactively** because earlier bytes were not captured. Earlier disappeared SQLite WAL/SHM files remain unreconciled. Current preservation does not erase either limitation.

Cleanup was independently checked after the user's stop: Docker service **inactive**, socket **active**, matching its baseline; PostgreSQL/Redis/Kafka test ports and temporary API18114/UI15176 ports closed. Existing assistant8011/dashboard5173 remain available and were not restarted. Verification used isolated servers; the already-running user API has not been certified as reloaded with this change. No orders, broker mutations, purchases, external messages, paid-model calls, .env changes, failed-soak restart or new holdout access occurred.

This is engineering completion of this increment only. The report still offers **WAIT/NO_TRADE**, official TCP50 positive eligibility remains blocked, and no complete agent integration, qualified 5m/15m strategy, live-data entitlement, forward evaluation or trading edge is certified. Passing probability **UNKNOWN**. Goal tool status remains **BLOCKED**; no unsupported resume or overall completion is claimed. **Stop for human review before further implementation or deployment.** Next work needs a separate bounded scope: define qualified 5m/15m conditional analysis and acceptance evidence, then integrate only useful read-only capabilities.

---

# ALGHREST Earn2Trade TCP50 readiness

## Evaluation-focused briefing — verified review checkpoint (2026-10-13T00:44:38.545693+00:00)

The approved **29 paths** are implemented: five existing files updated and 24 new files. This increment joins a selected, saved and reviewed chart observation with its exact revision, a personal account revision, published news/events and a capability contribution map in one append-only session briefing. It does not claim that all agents ran. The API rechecks the observation, review and account before committing; changed inputs are rejected. Saved records retain full inputs, source clocks and code identities. Reopening repeats strict whole-file source hashes and exact deterministic replay; mismatched records are rejected without rewriting their provenance or using a persistent verification cache.

The report offers **WAIT/NO_TRADE only**, with explicit reasons. REVIEWABLE means the captured evidence can be reviewed, not market readiness or trade permission. Printed prices, indicators, levels and user hypotheses remain separate; only same-contract, same-time printed prices are compared for conflict. Missing candle history is not invented. News/calendar coverage remains partial and event risk UNKNOWN. Agent summaries are bounded, timestamped, instrument-related read-only context; no confidence score or consensus is inferred from the number of agents. Execution, DeFi and copying remain disabled. Personal rules, existing calculations and the total **20 Micro MES/MNQ** exposure cap are unchanged. The existing daily-loss calculation remains **$1,100**; the user's later $1,200 example is not silently substituted. Official TCP50 eligibility remains separate and blocked.

Verification: **2708 full-suite tests passed, 0 failures/errors/skips, 562 warnings; coverage 84.38% against the unchanged 70% gate**. Focused regressions: **193 passed**, overlapping with the full suite and not added to it. Frontend suites: 15 briefing, 12 news/events, 10 observations, 30 user-policy and 26 user-risk cases passed, without skips. Ruff, Black check, isort check, strict MyPy (127 source files), six-package architecture checks, TypeScript and the production build passed. Build retained its Browserslist age warning. Final browser workflow: 12 checks passed, plus a fresh real-clock mobile check with the menu fully closed and actual pointer access to the saved report. Browser inputs and empty published context were injected synthetic fixtures, not a live market connection. Earlier harness/style/command transcription failures are disclosed in the receipt.

Fresh public replay verified existing futures run, edge and walk envelopes with source checks and exact comparison. Legacy TCP25 simulation outcomes remain separately **PASS, FAIL and CENSORED**, all synthetic mechanics only. Three new briefing fixtures (current WAIT, stale INCOMPLETE/WAIT, same-time conflict NO_TRADE) were reopened and independently replayed; saved stores were reopened in a separate process. All prior public artifact bytes and the five byte-for-byte before archives are checked in the final source manifest. Existing htmlcov (136 files) and .coverage are compared to the current before baseline. The historical htmlcov exception cannot be certified retroactively because prior bytes were not captured; the earlier missing SQLite WAL/SHM bytes remain unreconciled. Neither limitation is repaired or hidden by this increment.

Coverage data and HTML/JSON/XML reporters, pytest temporary files, Hypothesis storage, build/browser outputs and tool caches were redirected to /tmp; bytecode and pytest cache writes disabled. Only approved evidence files are published. JUnit hostname attributes are removed from published copies, with original receipts retained in /tmp. Exact commands, source identities, output containment and secret scan results are in `artifacts/earn2trade-50k-readiness/evaluation-focused-briefing-v1/verification.json` and `source-manifest.json`.

Cleanup verified: isolated PostgreSQL/Redis/Kafka and temporary API18112/UI15174 ports closed. Docker service inactive/socket active, matching the initial state. Existing user assistant8011/dashboard5173 remain available and were not restarted. The new workflow was verified on isolated servers; the already-running user API does not expose new routes until a later restart after review. No orders, broker mutations, purchases, external messages, paid model calls, .env edits, failed-soak restart or new holdout access occurred.

**Review checkpoint:** stop before further implementation or activation. The smallest next proposal is a separately scoped conditional-analysis stage with defined 5m/15m inputs, invalidation/target rules and honest gaps; financial changes and agent adaptations need their own scopes. Passing probability **UNKNOWN**. Tests, synthetic replay and this research briefing do not prove trading edge or guarantee passing. Goal was newly created after lookup returned null; no unsupported resume or overall completion is claimed.

---

## Cleanup follow-up — RESTORED (2026-10-12T23:21:49.764698+00:00)

After the user's local stop command, independent systemctl verification confirms
Docker service **inactive** and socket **active**, matching the captured prior state.
All isolated test/API/UI ports are closed. No Docker API was called during verification.
The separately requested assistant API8011 and UI5173 remain listening without Docker.
Cleanup is complete; stop for human review. Earlier authentication blockers below are
historical and retained. Test results, source identities and readiness limitations are
unchanged; passing probability UNKNOWN. No source edits or Goal lifecycle changes.

---


## News/events context — 2026-10-12 review checkpoint

The authorized **29-path** increment is implemented. An authenticated read-only
MES/MNQ context endpoint and an independent Arabic panel show headline publication,
actual retrieval/attempt clocks, deterministic relevance reasons, source failures,
and partial official schedules. Manual refresh and optional visible-page 5/15-minute
refresh do not modify observation prices or their timestamps. Late responses cannot
replace a newer instrument selection. Coverage stays **partial**, event risk **UNKNOWN**,
and both permission flags **false**. No calendar is supplied to the financial event guard.
Public FeedCache/headlines signatures and existing serialized evidence are preserved;
MES now excludes unrelated crypto headlines consistently with MNQ.

Verified: **2682 full-suite tests, zero failures/skips, 562 warnings**;
**84.216357%** coverage, unchanged **70%** gate. **267 focused** tests overlap
the full suite; counts are not added. Frontend **12 context / 10 observation / 30 cap /
26 personal-risk** tests pass. Ruff, Black, isort, strict MyPy (124 files), architecture,
TypeScript and build pass. isort keeps 13 configured file exclusions. Full warnings are
DeprecationWarning/FutureWarning; the build retains outdated Browserslist-data warning.
**17 browser checks** pass with intercepted synthetic context and a separate local
API/database; Google-font requests were blocked. Fixtures prove mechanics only.

Fresh run/edge/walk public replay repeats strict whole-file source checks and exact
comparison. Legacy TCP25 examples replay separately as **PASS / FAIL / CENSORED**.
Nothing was rehashed or rewritten to mask mismatch. Five byte archives match the
original baseline. Details, commands and all 29 paths are in this stage's manifest and
verification receipt under `artifacts/earn2trade-50k-readiness/news-events-v1/`.

Sources: FOMC and BEA direct captures parsed 16 and 13 entries. FOMC dates do not
provide exact meeting hours; BEA printed wall times retain an unknown timezone.
BLS direct feed/calendar availability varies between timeout and HTTP403; the
independent calendar capture returned403. No refusal was bypassed. These schedules
are always partial, not a complete economic-calendar or an entry-clearance signal.

The execution environment restarted and removed earlier /tmp receipts. They were
reproduced; earlier observed results are not presented as surviving archived reports.
Two SQLite auxiliaries included in the old baseline (`artifacts/advisory/research.sqlite3-wal`
and `.sqlite3-shm`) are now absent. Their disappearance cannot be timed/attributed from
available evidence and byte preservation of them is **UNKNOWN**. They are runtime
sidecars, not research envelopes. The separately requested assistant startup backs up
the current main journal to a private /tmp copy; this cannot reconstruct absent prior
sidecars or certify journal history. No other public baseline path is missing/changed
outside scope. Prior htmlcov/.coverage bytes are preserved for this increment; the
historical htmlcov exception remains uncertifiable because earlier bytes were not hashed.

Test containers are stopped and isolated ports closed. Docker daemon restoration to
its prior inactive state is **BLOCKED pending local interactive authentication**;
socket was and remains active. User was asked to stop only docker.service.
Following the user's separate “run my project” request, the advisory API8011 and
UI5173 remain available without Docker/Kafka/broker or trading agents. Runtime key,
launchers/caches and current-journal backup are private /tmp files; no .env change.
Temporary test API18112/UI15174 will be stopped independently.

Stop for human review before analysis/recommendation work. Personal **20 Micro**
policy and closed official TCP50 gate are unchanged. Price data, complete calendar,
historical decision-context storage, qualified trading evidence and forward paper
outcomes remain unresolved. **Passing probability UNKNOWN; no trading-edge claim.**
Goal lookup returned null; no Goal was resumed or completed. Heartbeat not reactivated.


## Observation workflow — 2026-10-12 review checkpoint

The authorized **24-path** increment adds an authenticated input/review/history
panel to the existing manual assistant. Users can paste JSON or enter a dated
MES/MNQ observation, correct values, save append-only revisions and explicitly
review one saved revision. Original input and corrected versions remain separate.
Unknown values stay null; missing, future, contradictory and stale timestamps are
handled explicitly. The source remains **user-reported**, including after review.
No candle series, market qualification, trade permission or new advice is inferred.

Engineering checks **PASS**: **2645 full-suite tests, zero failures/skips**, **562
warnings**, **83.926775%** combined coverage with the unchanged **70%** gate.
The 42 focused tests overlap the full suite and are not added to that count.
Frontend: **10 observation + 30 cap + 26 personal-risk tests**; TypeScript and
production build passed. Ruff, Black (252 files), isort (13 configured exclusions),
strict MyPy (121 files, including the new routes) and architecture checks passed.
The build retains the existing outdated Browserslist-data warning.

**13 browser checks passed** with synthetic inputs in a fresh isolated profile:
manual/pasted input, malformed confirmation, inert text, stale data, save/review,
correction, two-tab conflict, old/latest reopen, delayed response, lost connection,
mobile layout and authentication. Existing Google-font requests were blocked;
no market-provider requests were made. A fresh process reopened both saved
revisions after the temporary API stopped. Raw screenshots remain temporary.

Fresh public replay/source-hash/exact-comparison checks passed for the existing
futures run, edge and walk artifacts. Legacy TCP25 simulations were independently
replayed: **PASS, FAIL and CENSORED** remain separate synthetic mechanics examples.
Their bytes were not changed. The new observation verifier rejects mismatched
whole-file source hashes; no persistent verification cache was introduced.

Preservation: all **1493 prior public artifact files**, **136 existing htmlcov
files** and the existing `.coverage` matched the before baseline. Three approved
before-files are byte-for-byte archives. All generated test caches, build, browser
profile/database and reports were directed to `/tmp`; only approved evidence was
copied back. Final containment results and exclusions are in the manifest. The
historical htmlcov exception still cannot be certified retrospectively.

Operational status: test containers and temporary API/UI are stopped; test ports
are closed. **Docker restoration verified at 2026-10-12T10:32:35.887437+00:00**: service inactive/socket
active matches the prior state after the user ran the stop command. Independent
systemctl and listening-socket checks confirmed restoration without contacting
Docker API. The earlier authentication blocker is preserved in receipt history.
This increment is verified and stopped for review; no new tests/services started
for cleanup. The heartbeat was paused at the original checkpoint. That checkpoint
recorded Goal PAUSED; the cleanup get_goal returned no Goal. No Goal lifecycle
change or broader-project completion is claimed.

Personal 20-Micro rules, financial arithmetic, official TCP50 gate and all prior
public interfaces remain unchanged. TCP50 positive allowances remain **BLOCKED**.
This stage does not settle the later personal 1100/1200 daily-limit or 20-Micro/
2-Mini clarification. News/events, evidence-supported conditional analysis,
account/risk integration and prospective DEMO evaluation remain later stages.
**Passing probability: UNKNOWN. No trading-edge claim.**

Evidence and exact commands:
[`verification.json`](../../artifacts/earn2trade-50k-readiness/observation-workflow-v1/verification.json),
[`source-manifest.json`](../../artifacts/earn2trade-50k-readiness/observation-workflow-v1/source-manifest.json),
and [the exact scope and continuation plan](advisory-completion-plan.md).
Earlier sandbox and temporary-harness failures are disclosed in verification;
only the final checks above are certified. Stop here for human review.

## Numeric input correction — 2026-10-11

The user approved a separate **19-file** increment: seven existing source/test/document
files and twelve new evidence files under
[`personal-numeric-validation-v1/`](../../artifacts/earn2trade-50k-readiness/personal-numeric-validation-v1/).
The two review findings are corrected:

- Equivalent decimal spellings such as `05000` and `5000`, different zero/scale
  spellings and backend Decimal exponent notation compare by exact decimal value.
  No binary floating-point rounding or tolerance is used for request identity.
  Different amounts, account revisions and other request fields remain rejected;
  original serialized response fields are preserved.
- Entry/stop tick-validation arithmetic that raises `decimal.InvalidOperation`
  becomes a controlled validation error. The authenticated API returns **422**
  for the reproduced oversized prices, instead of an unhandled exception.

Personal rules and financial arithmetic are unchanged: MES/MNQ only, **20 gross
Micro** across positions/orders, strict **<30%** consistency, <=1% per-trade risk,
07:00 inclusive–14:00 exclusive UTC, declared reviewed costs/buffer and confirmed
flat account for a positive new size. Results remain advisory with both execution
flags false. This correction does not certify external-program compliance.

Verification: **2603 full-suite tests passed, zero failures/skips**, with **562
warnings** and **83.7163%** combined coverage against the unchanged 70% gate.
The **384 focused tests overlap** the full suite. Frontend: 30 cap tests and
26 personal-risk tests passed; source/test type checks and production build passed.
Three real backend-serialized synthetic cases (leading zeros, tiny fee, zero fee)
passed the frontend public validator. Ruff, Black check, isort check, strict MyPy
and architecture passed; isort retained 13 configured exclusions. The old
Browserslist dataset warning remains. No new browser/live-market validation is claimed.

Initial regression failures are retained as red-before-green evidence. A sandbox
FastAPI TestClient attempt timed out; the isolated host fixture run passed.
Temporary harness Node type-resolution and Vite module-path errors were corrected
only under /tmp; no dependency/configuration files changed. All exact commands,
failures and final results are preserved in the new evidence.

The original personal example embedded in `user-personal-plan-v1/verification.json`
remains byte-for-byte preserved but is now **superseded for current-source
verification**: its old user_risk.py hash must be rejected. The new
`synthetic-personal-assessment.json` was generated by the public calculation from
the exact captured original profile, sessions, request and historical clock.
Independent reopen/public replay confirms all serialized fields and numerical
outcomes are identical except the legitimate source-hash change: budget $250,
loss per contract $53.25, **4 Micro**, estimated loss $213. This is **SYNTHETIC
MECHANICS ONLY**, not a current trading recommendation or edge/probability evidence.
Existing futures run/edge/walk and legacy TCP25 **PASS**, **FAIL**, **CENSORED**
artifacts were independently replayed with exact/source checks, without rewriting
old bytes, accessing new holdout data or introducing a persistent verification cache.

All **1491 prior public artifacts** and **137 existing coverage reports/data**
match the captured before hashes. Both previous documents are archived byte-for-byte.
Coverage, pytest/Hypothesis/tool caches and build outputs were directed to /tmp,
with an explicit HTML reporter destination. The final manifest verifies retained
changes against the approved paths. Private/credential files are excluded from
published identities. The historical unbaselined htmlcov overwrite remains UNKNOWN;
the earlier seven-file Hypothesis exception is retained in the historical record.

Only the existing isolated local quality services were used; test containers are
stopped. **Docker restoration verified:** docker.service is inactive and
docker.socket is active, matching the observed initial state. The user stopped
the daemon locally; a subsequent systemctl-only check confirmed both states
without contacting the Docker socket. No trading agents or failed soak were started.

The broader Goal remains **PAUSED** and incomplete. Passing probability remains
**UNKNOWN**; qualified market-data, strategy-edge and complete forward-paper
requirements are not resolved by these engineering tests. The earlier sections
below describe their original increments and evidence identities.

## Personal rules and flat-account planning — 2026-10-11

The user approved exactly **24 files**: eleven application/test/document paths
and thirteen evidence files in [`user-personal-plan-v1/`](../../artifacts/earn2trade-50k-readiness/user-personal-plan-v1/).
This increment follows **the user's own rules**; external TCP50 progression/fee
clarification is not a prerequisite for this personal arithmetic workflow.
It does not certify a firm's evaluation. The broader Goal remains **PAUSED**,
unfinished, and TCP50 has not been purchased. Legacy firm allowances remain
blocked independently; their modules/serialized fields are unchanged.

The personal workflow now owns current journal/revision/account checks, exact
Decimal financial projection, retained breaches and fresh flat-account sizing.
Terms: $50,000 start, $3,000 objective, $1,100 daily loss, $2,000 EOD drawdown,
best day **strictly less than 30%**, dated MES/MNQ only, shared gross **20 Micro**,
entry **07:00 inclusive–14:00 exclusive UTC**. Reviewed user costs and a positive
buffer are required. The shared EOD/account/risk arithmetic is reused; no old
journal is silently migrated or relabeled. Consistency gates completion, not
every early profitable entry. No minimum trading days are invented. Open
exposure still gets the independent cap check; missing stop/contingent risk
makes the full new-size worksheet UNKNOWN. No order or liquidation is triggered.

| Verification | Current increment result |
| --- | --- |
| Focused Python | 380 passed, zero failures/skips; overlaps the full suite |
| Full repository suite | 2599 passed, zero failures/skips; 562 non-failing warnings |
| Unchanged 70% combined coverage gate | 83.7130% passed; engineering coverage only |
| Ruff / Black / isort / strict MyPy / architecture | Passed; Black 248 files, MyPy 118 source files; isort's configured exclusions report 13 files skipped |
| Frontend regressions | 30 existing cap cases and 22 personal-risk cases passed; no skips |
| Frontend production + test types / build | Passed; temporary build/cache destinations; Browserslist age warning retained |
| Synthetic desktop/mobile browser | 13 scenarios passed, no page exceptions; explicit journal creation, exact MES example, stale/missing/mismatched/changed inputs, open exposure, races, expiry and failed recalculation |
| Existing futures run / edge / walk | Fresh public replay, whole-file source checks and exact comparisons passed; old bytes preserved |
| Legacy TCP25 simulation examples | PASS, FAIL and CENSORED each independently replayed unchanged; historical source-mismatched envelopes rejected |
| Prior public artifacts / private sample files / reports | 1,471 / 9 / 137 baseline files preserved byte-for-byte; both before-documents archived |

The independent synthetic MES example has $250 budget, $53.25 loss per contract,
**4 Micro**, and $213 estimated stop loss. The declared $2 round-trip fee and
0.25-point slippage are **SYNTHETIC MECHANICS ONLY**, not verified market fees.
The result remains `trade_permitted=false`, `execution_enabled=false`,
`firm_compliance=NOT_ASSESSED` and `passing_probability=UNKNOWN`.

Validation history is preserved in the evidence log: early sandbox TestClient
attempts stalled; isolated host tests resolved that limitation. An initial full
run used the advisory-only profile where mocked lifecycle tests require the
general test profile. A succeeding full run skipped three opt-ins. Enabling them
exposed a test-harness DSN construction error for writer leases; correcting only
the temporary environment produced the final zero-skip run above. Kafka auth
used a disposable local broker, and writer-lease checks used SELECT/session locks
on the local quality database. No `.env` or repository configuration was changed.
These intermediate failures/skips are not combined with final passing counts.
Temporary Vite harness setup/locator problems were also corrected without
changing dependencies or suppressing checks.

Coverage reporters/data and maintained test caches stayed under `/tmp`, including
explicit `--cov-report=html:/tmp/alghrest-user-personal-plan-v1/htmlcov`.
**Transient containment exception:** the collect-only diagnostic omitted the
Hypothesis redirect and created seven ignored `.hypothesis/constants/` files.
Independent filesystem birth times prove all seven were created after this
increment's baseline. Their exact bytes were preserved in the temporary review
directory and only those verified-new outputs were removed. This is disclosed,
not presented as a no-write run. No out-of-scope regular-file differences remain
in the scoped byte baseline; additional hidden-cache directories had an mtime
audit, not a retrospective byte baseline. The earlier unbaselined historical
htmlcov overwrite remains **UNKNOWN**; current 137 report identities match the
new before baseline, which cannot certify the older exception.

Isolated test containers and temporary advisory/dashboard fixtures were stopped.
Docker restoration: **RESTORED — daemon and socket independently verified inactive**. Earlier stopped containers,
private account stores and the failed soak were not restarted. No purchase,
provider message, broker mutation, strategy tuning or new holdout access occurred.

See [personal workflow and calculations](user-advisory-policy.md) and
[verification](../../artifacts/earn2trade-50k-readiness/user-personal-plan-v1/verification.json)
for exact paths, commands, before/after identities, captured synthetic inputs and
limits. Qualified current futures data, real contract metadata/corrections,
realistic observed execution costs, untouched OOS edge, a defined evaluation
horizon and complete forward evaluations remain unresolved. This increment does
not establish trading edge or passing probability. **Stop for review.**

## Preserved MES/MNQ data-quality review — 2026-10-11

The user approved exactly eleven files: two document updates and nine new
evidence files in
[`futures-data-quality-review-v1/`](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/).
Both documents' previous bytes are archived before edits. Source, configuration,
tests, policy, permission restrictions and private data remain unchanged. The
broader readiness Goal remains **PAUSED**; this increment does not complete it.

This preserves the **2026-10-10** read-only findings, with fresh local identity,
archive, replay and containment checks during preservation. Public text and the
provider mailbox were not re-read on October 11. The earlier no-reply observation
at October 10 01:48:34 UTC remains valid at its original checkpoint; the subsequent
FirstRateData reply received at **02:38:44 UTC** states OHLCV only, no historical
Bid/Ask or event-level trades for these products, and corrections overwrite
archives without version/changelog manifests. No historical dated-contract/outage
inventory was supplied. Its affirmative metadata wording conflicts with the
[official FAQ](https://firstratedata.com/about/FAQ) inspected October 10; this is
**UNRESOLVED**, not an inferred typo or a qualified metadata dataset.

| Observed historical sample | Native minute rows | Complete 5-minute buckets in weekday 07:00–14:00 UTC | Absent candidate minutes in that window |
| --- | ---: | ---: | ---: |
| MESH26 | 128,848 | 6,086 | 98,961 |
| MNQH26 | 142,658 | 6,554 | 87,401 |

These counts concern genuine historical provider samples, not synthetic prices.
Each recorded row passes all twelve structural/numeric/time checks. The weekday
window is a disclosed audit assumption, not a historical exchange holiday
calendar. Missing minutes are **UNCLASSIFIED**; no-trade minutes, filtering and
feed loss are not distinguished. Do not fill gaps or infer a loss percentage.
Incomplete five-minute buckets are excluded; only completed candles are used.
Both files end at March 20, 2026 13:30 UTC exclusive close, so they do not provide
current data or qualified multiyear active-contract history.

| Readiness item | Status in this review | Remaining acceptance evidence |
| --- | --- | --- |
| Preserved snapshot identity and recorded-row validity | VERIFIED for retained samples | Matching ZIP/CSV/receipt identities and repeatable full-file checks |
| Closed-bar aggregation and original-cut replay | VERIFIED mechanics | Exact original snapshot/count/health comparison; no gap filling |
| Active-contract metadata and calendar | PARTIAL | Inspectable dated metadata resolving the provider/FAQ conflict and historical sessions |
| Coverage and missing-minute classification | MISSING | Authoritative no-trade/outage and coverage evidence |
| Vendor correction/as-of history | MISSING | Version evidence, or separately reviewed limitations of immutable local capture |
| Bid/Ask and event-level execution | BLOCKED for this product | Another qualified source or a separately reviewed conservative method |
| Assigned MES/MNQ commissions, fees and slippage | MISSING | Applicable dated cost schedule and a validated execution-cost method |
| Untouched OOS edge and complete forward evaluations | MISSING in this review | Qualified history, frozen methodology, horizon, validated prospective rules and reproducible forward evidence |

The [report](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/read-only-review.md),
[methodology notebook](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/methodology.ipynb),
[source manifest](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/source-manifest.json)
and [verification receipt](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/verification.json)
retain identities, commands, dates, warnings/limitations and exact scope.
The copied October 10 focused regression report records **64 passed, zero
failures/errors/skips, 0.72s**; no warnings appear in that log. It was not rerun
or combined with overlapping old test counts. Full suite, static checks, coverage
gate and strategy/evaluation simulations were not run in this documentation
increment. Existing futures/edge/walk artifacts are preserved by byte identity;
no new semantic verification of those envelopes is claimed here.

Local retention and internal research use follow the accepted
[FirstRateData license](https://firstratedata.com/about/license); interpreting
offline replay as internal research is an explicitly stated inference, not
authorization for live broker/exchange use. Raw data and correspondence stay
private. The archived October 10 audit initially used a mismatched JSON serializer;
only the audit was corrected to the original Pydantic serializer. No historical
hash, provenance or numerical outcome was patched.

Current htmlcov and .coverage identities are baselined for this increment. The
historical unbaselined htmlcov overwrite remains **UNKNOWN** and cannot be
retroactively certified. No .env edit, services, purchase, new agreement, download,
mail sending, tuning, new holdout access or failed-soak restart occurred.
No new PASS, FAIL or CENSORED simulation outcomes were generated.
**Official TCP50 positive allowances remain BLOCKED; passing probability UNKNOWN.**
The separate personal 20-Micro cap is not firm progression approval. Recheck public
rules and assigned terms at purchase. Stop for review before further work.

Updated: 2026-10-11. Target: **TCP50, $50,000, evaluation phase**.
Purchase status: **NOT PURCHASED**. Actual purchase date: none.

The current approved dashboard increment presents the independent user-defined
MES/MNQ-only 20-Micro exposure check and adds manual exposure evidence entry.
Its results describe personal limits only; the firm allowance gate is unchanged.

The objective is evidence-backed readiness and an honest assessment, with the
system advisory-only and human-controlled. The preceding approved 17-file increment
archives the October 10 engineering results and two user-provided Arabic rule
screenshots, with two document updates and fifteen new evidence files. It keeps
TCP50 positive allowances blocked. The preceding CME metadata and sample-timestamp
review records the human-confirmed **07:00–14:00 UTC/GMT** research window; runtime
configuration is unchanged. The earlier increment independently
reviewed the FirstRateData converter and preserved the two explicitly authorized
free samples in private local storage.
The preceding source increment implements individual-contract minute validation
and closed five-minute conversion; it remains a preflight that always abstains. The prior
Massive adapter uses synthetic fixtures; its separately observed REST access does
not resolve Massive retention/replay permission.
Earlier research verifies proposed source-data providers and corrects
pricing/licensing assumptions. The preceding
engineering increment added an offline MES/MNQ data preflight and tests. The earlier
seven-file increment archived public progression evidence and its unresolved
semantics. The TCP50 gate correction remains in force; its source, tests and
historical receipts are unchanged. The earlier 21-file policy increment verified
the public target/risk prerequisite.
It does not establish trading edge, estimate passing probability, certify an
evaluation, or guarantee passing.

The earlier progression-capture receipt recorded a BLOCKED Goal at its own
checkpoint. At an earlier implementation checkpoint, `get_goal` returned no Goal;
the compatible overall readiness objective was created without a token budget.
That implementation checkpoint reported ACTIVE. The October 9 `get_goal` read
returns BLOCKED; no supported agent resume was claimed. The objective remains
unfinished, and new public provider facts do not establish user entitlement.

## User-policy dashboard — separate approved 15-file increment, 2026-10-10

Completed the separately approved UI scope: four existing files updated, three
new source/test files, eight new evidence outputs. Both maintained documents were
archived byte-for-byte before edits/tests. The source manifest and
[verification receipt](../../artifacts/earn2trade-50k-readiness/user-policy-dashboard-v1/verification.json)
list all fifteen exact paths and before/after identities. Existing local work was
preserved. The compatible broader Goal remains **PAUSED**; no unsupported resume
or overall completion is claimed.

The assistant now shows a separate Arabic USER POLICY panel, with only MES/MNQ,
one gross 20-Micro cap and 07:00 inclusive–14:00 exclusive UTC/GMT. Manual journal
entry accepts all reported positions and working orders, including unsupported
roots, and exact cash/unrealized/equity strings. Separate coverage reviews preserve
unknown versus confirmed flat. Row/evidence edits revoke confirmations/results;
loading evidence never renews its timestamp. The existing backend Decimal
reconciliation and all financial/risk rules are unchanged. Delayed account/check
responses are ignored; positive displays expire and do not revive on clock rollback.
No order controls, persistent verification cache, quote polling or permission
relaxation was added. Personal capacity never enters the legacy firm worksheet.

| Requirement affected by this increment | Status and acceptance evidence |
| --- | --- |
| Manual personal-cap UI mechanics | VERIFIED for approved synthetic tests; exact shared count, preserved unsupported rows, unknown/flat distinction, expiry and races |
| Advisory isolation | VERIFIED for the focused paths: false permission fields validated, unchanged backend boundaries, no execution control; broader readiness remains PARTIAL |
| Exact account inputs | PARTIAL: manual entry and existing Decimal reconciliation verified; broker authenticity and input completeness are human responsibilities |
| Official TCP50 progression/positive allowance | BLOCKED independently; this personal check is not firm qualification |
| Qualified data, strategy edge, forward evaluation or passing probability | Not advanced by UI tests; passing probability UNKNOWN |

Fresh checks: **30 frontend regression passes**, **90 focused existing backend/API
passes**, zero failures and skips; strict dashboard and new-test TypeScript checks
and the normal production Vite build passed. **24 browser scenarios/observations**
passed, including desktop/mobile RTL without horizontal overflow, manual 10 MES +
9 MNQ saving, exact money reconciliation, 20/21 caps, unsupported Mini, missing/stale
inputs, outside-hours, wrong authentication, failure, dirty changes, account/load
races and expiry. All browser accounts/clock/results are **SYNTHETIC MECHANICS
ONLY** in an isolated temporary fixture. No Docker, trading agents, broker/data
calls, actual-account seeding or failed soak was started. Temporary loopback API
and Vite processes were stopped after QA.

The final Vite build has a Browserslist-age warning. An initial build from the
wrong working directory also warned about Tailwind content; the correct dashboard
build passed with its existing configuration. Initial test configuration errors,
fixture bootstrap/auth-origin errors and the sandbox-blocked TestClient attempt
were corrected only in `/tmp` and are disclosed. Bundled installed Node types were
used for strict test checking without adding dependencies. No new full Python
suite, coverage gate, Ruff/Black/isort/MyPy or architecture run is claimed here;
the preceding core increment's 2566-pass suite, 83.55% coverage and static checks
are historical. Their reports are preserved, and the 70% gate is unchanged.

Fresh public synthetic futures run/edge/walk path replay, whole-file source checks
and exact comparisons passed again for this request. Legacy TCP25 **PASS**, **FAIL**
and **CENSORED** replays passed separately; historical source-mismatched envelopes
were rejected. No affected backend sources changed, so no envelope regeneration
was needed. Earlier artifacts, private samples and current ignored htmlcov/.coverage
were preserved. The historical HTML reporter exception cannot be retroactively
certified because prior bytes were never captured. Builds, test data/reports and
caches stayed under `/tmp`; no out-of-scope regular-file writes were found by the
final inventory. Protected/dependency directories are excluded from the byte
inventory, and this limitation is recorded.

See [manual steps](user-advisory-policy.md#dashboard-manual-workflow--2026-10-10)
and [synthetic browser evidence](../../artifacts/earn2trade-50k-readiness/user-policy-dashboard-v1/browser-review.json).
Stop for review before expanding scope. Qualified futures data/costs, untouched
OOS/walk/holdout evidence, forward paper evaluations, failed-soak reconciliation
and official progression semantics remain unresolved. At purchase recheck public
rules against assigned terms. No trading-edge claim or probability estimate.

## User-defined Micro ceiling — approved 15-file increment, 2026-10-10

The user explicitly selected **Micro only**, MES and MNQ, with a fixed shared
ceiling of **20 gross contracts**. They approved the revised 15-file scope and
the conservative counting of all positions and working orders without netting.
This adds a separate USER POLICY exposure check; it does not encode or verify
Earn2Trade progression semantics. The personal check does not wait for firm
progression verification. Its status is WITHIN_CAP/BLOCKED/UNKNOWN, with
`firm_compliance=NOT_ASSESSED`, `passing_probability=UNKNOWN`, and both
`trade_permitted` and `execution_enabled` always false.

The new authenticated endpoint is
`POST /assistant-api/evaluations/{evaluation_id}/user-policy-check`.
It reads one existing journal snapshot and recomputes gross exposure each request.
Only dated MES/MNQ contracts are eligible; Mini/other exposure is blocked rather
than ignored. The personal entry window is 07:00 inclusive to 14:00 exclusive UTC.
The existing net journal/account reconciliation and 1,800-second evidence ceiling
are reused. Missing, stale, unconfirmed or incomplete account evidence has no
positive capacity. Net costs are not deducted again. No personal assessments are
saved, no persistent cache is added, and no orders or automated reductions exist.
See the [manual API guide](user-advisory-policy.md).

Existing policy/risk/evaluation/model/configuration source files and public
interfaces are unchanged. The existing TCP50 allowance gate remains independent;
a personal-cap result cannot become a firm assessment or positive risk record.
Existing synthetic envelopes retain their strict whole-file source checks.
There were no affected shared simulation sources, so no legacy envelopes needed
regeneration. Earlier evidence was preserved rather than rewritten.

Fresh verification: **611 focused passes**, 0 skips,
36 warnings; **2566 full-suite passes**,
0 skips, 562 warnings; no test failures/errors.
Focused tests overlap the full suite and are not added together. Combined
statement/branch coverage is **83.55%**, with the unchanged
70% gate. Ruff, Black, isort, strict MyPy (118 source files) and architecture checks
passed. Installed dependency consistency passed for 411 packages. Poetry lock
verification remains BLOCKED because the CLI is absent. Initial MyPy and isort
findings were repaired; a system-Python bootstrap failed before tests and was
rerun with the existing project Python 3.12 environment. These attempts are
recorded in [checks.log](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/checks.log).

Public path replay/source/exact comparisons passed for the synthetic futures run,
edge and walk. Legacy TCP25 PASS, FAIL and CENSORED replay passed separately;
historical source-mismatched envelopes were rejected. Reuse stayed request-scoped.
These are SYNTHETIC MECHANICS ONLY, not trading-edge or passing-probability evidence.
The isolated PostgreSQL/Redis/Kafka quality containers were returned to their
prior stopped states and the authentication-test container was removed. Docker
was initially inactive; the user started it locally because sudo requires a
password. Daemon restoration is recorded separately in the receipt.

Reports, HTML, coverage data, pytest temporary files, Hypothesis and tool caches
were redirected to /tmp; the HTML destination was explicitly overridden. The
current checkout htmlcov/.coverage baseline and earlier artifacts/private samples
are verified in the [receipt](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/verification.json). The previous htmlcov
exception still cannot be retroactively certified because its prior bytes were
not captured. Protected/private paths are excluded from published manifests.

The [source manifest](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/source-manifest.json),
[focused XML](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/focused-tests.xml), [focused log](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/focused-tests.log),
[full XML](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/full-tests.xml), [full log](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/full-tests.log),
[coverage JSON](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/coverage.json), and byte-identical
[readiness archive](../../artifacts/earn2trade-50k-readiness/user-policy-cap-v1/readiness-before.md) preserve this increment.

The broader Goal was observed PAUSED and was neither resumed, overwritten nor
completed. This bounded increment was separately authorized. Stop for review:
no dashboard change, deployment, purchases, strategy tuning, real holdout access
or failed-soak restart. Qualified real-data/OOS/forward-paper evidence remains
missing; the broader readiness matrix is not upgraded by this personal calculator.

## Engineering evidence and Arabic rule screenshots — approved 17-file checkpoint, 2026-10-10

The original bytes of both maintained documents are archived in
[readiness-before.md](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/readiness-before.md)
and [futures-data-access-before.md](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/futures-data-access-before.md).
All earlier evidence and private samples are preserved. This increment archives
already completed engineering checks; it does not rerun the full suite, static
checks or services. It independently reopens their results and repeats public
artifact replay for the current request.

### Archived engineering results and current source identities

All **294 source/configuration/test identities** in the original October 10
[quality source manifest](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/quality-source-manifest.json)
match the current worktree. All **38 delivered report identities** match the
original temporary delivery manifest. The
[quality verification receipt](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/quality-verification.json)
and its copied reports preserve their original bytes, dates and limitations.

| Original October 10 engineering check | Independently reopened result |
| --- | --- |
| Full unit/integration suite | 2,506 passed; zero failures, errors or skips; 562 warnings |
| Focused advisory/TCP50/futures regressions | 544 passed; zero failures/errors/skips; overlaps full suite and is not added |
| Combined statement/branch coverage | 83.43100320915306%; unchanged 70% gate, branch measurement enabled |
| Ruff, Black, isort, architecture | Passed; isort excluded 13 files, distinct from zero pytest skips |
| Strict MyPy | Passed for 117 source files |
| Dashboard types and canonical production build | Passed; canonical build ran from `dashboard/` |
| Installed dependency compatibility | `uv pip check` passed for 411 packages |
| Initial `python -m pip check` attempt | BLOCKED because pip is absent; uv provided the compatibility check |
| `poetry check --lock` | BLOCKED because the Poetry CLI is absent; no installation performed |

Exact commands, exit codes and check logs are preserved in
[static-checks.json](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/static-checks.json)
and [static-checks.log](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/static-checks.log).
Full/focused XML and logs and coverage JSON are in the same directory. The suite's
562 warnings are principally deprecations. The canonical dashboard build warns
about six-month-old Browserslist data and the deliberately external output path.
An earlier root-directory build had a Tailwind content warning; it is recorded
but is not the canonical build relied upon.

The original run redirected HTML, coverage data, reports and caches outside the
checkout; its before/after check preserved existing `.coverage` and 136 htmlcov
files. Its quality services were restored to their prior stopped states. The
human subsequently started the manual UI separately; that dated restoration
receipt does not certify the present state of all user processes. No services
are started or stopped by this preservation increment. The earlier unbaselined
htmlcov overwrite remains **UNKNOWN** and cannot be retroactively certified.
The earlier delivery manifest did not include coverage JSON; this increment
checks its copied bytes and original verified totals and captures its current
whole-file identity without changing historical provenance.

### Screenshots, public rules and external clarification

The two byte-preserved PNGs are **USER-PROVIDED SCREENSHOTS**, not independently
retrieved primary assets or authenticated account terms:
[progression](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/user-provided-progression.png)
and [consistency](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/user-provided-consistency.png).
PNG integrity and identities pass. Their displayed TCP50 evaluation bands agree
with the previously captured primary chart: $0–$1,500 → 2 standard contracts,
$1,501–$2,000 → 4, $2,001+ → 6. The current
[official progression text](https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path)
describes current balance/profit, total open positions and qualifying micros.
It does not supply the missing negative-profit, fractional-boundary, precise
progression accounting, mixed-size rounding or exact lower-band handling cases.
Do not infer thresholds, encode bands or treat six as an unconditional allowance.

The current
[consistency article](https://help.earn2trade.com/en/articles/3849975-what-is-the-maintain-consistency-rule)
requires every day's contribution to be strictly less than 30% of total PnL.
At a $900 best day, total profit must exceed $3,000; at $1,200, it must exceed
$4,000. Equality is insufficient. This is an evaluation completion condition;
exceeding the proportion does not itself immediately fail the evaluation.
These screenshots corroborate public rule wording, not strategy performance.
Public planning rules must still be rechecked at purchase.

A read-only check at **2026-10-10 01:48:34 UTC** found no incoming clarification
in either authorized FirstRateData/Earn2Trade inquiry thread or bounded sender/
date search. The one earlier Earn2Trade promotional message is not clarification.
This absence claim is limited to those checks. No raw mailbox messages, individual
account identifiers or credentials are published; no message is sent again.
Contract activation/first trade, corrections/as-of versions, data absence
interpretation, qualified Bid/Ask and assigned MES/MNQ fees remain unresolved.

### Fresh replay, readiness and review limits

The [fresh replay receipt](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/replay-results.json)
records public futures run/edge/walk path replay, strict whole-file source checks
and exact serialized comparisons for this request. Legacy TCP25 **PASS**, **FAIL**
and **CENSORED** are separately verified; three older source-mismatched envelopes
are rejected. These remain **SYNTHETIC MECHANICS ONLY — LEGACY TCP25**. There is no
persistent verification cache and no provenance patching or numerical change.

The [publication verification receipt](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/verification.json)
records exact scope, archives, report identities, privacy checks and containment.
Source/configuration/tests, policy interfaces and financial calculations remain
unchanged. Qualified OOS edge, executable TCP50 simulation, complete forward
evaluations and failed-soak reconciliation remain incomplete; the readiness
matrix below retains its PARTIAL/MISSING/BLOCKED statuses. Engineering coverage
is not trading success, a readiness completion percentage or passing probability.

The original quality receipt's BLOCKED Goal observation remains unchanged. The
current Goal was recreated with the same overall objective after `get_goal`
returned none; its latest observation is **ACTIVE and unfinished**. No unsupported
resume or completion is claimed. Stop for review before further implementation.
**TCP50 positive allowances remain BLOCKED; passing probability UNKNOWN.**

## CME metadata and timestamp evidence — approved 10-file increment, 2026-10-10

The October 9 read-only review is now preserved after approval of the exact
two-document/eight-evidence scope. Both previous documents were archived
byte-for-byte before editing. The preceding manifests remain unchanged; their
after-document identities resolve to the new archives. This is metadata and
mechanics evidence, with no policy, source, configuration or test changes.

### Verified references and the confirmed research window

The existing catalog agrees with CME outright specifications: MES has a 0.25-point
tick, $5 per point and $1.25 per tick; MNQ has a 0.25-point tick, $2 per point and
$0.50 per tick. These references do not authenticate vendor prices. [MES rules,
35301/35302.B–C](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/IV/350/353/353.pdf),
[MNQ rules, 36101/36102.B–C](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/IV/350/361.pdf).

The live FAQ's 16:15–16:30 New York halt wording is superseded by the
[June 11, 2021 filing, effective trade date June 28](https://www.cmegroup.com/market-regulation/rule-filings/2021/6/21-244R_1.pdf).
Its Exhibit A explicitly lists MES and MNQ. The former interval is not a scheduled
closure for these 2024–2026 samples; regulatory and event-dependent halts are
separate. The precise January 9, 2025 exceptional closure is recorded, but the
full historical product-specific holiday/status calendar remains **PARTIAL**.

The [official expiration calendar](https://www.cmegroup.com/trading/equity-index/rolldates.html)
confirms March 20, 2026. Rules and the
[CME fact card](https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf)
imply the H26 terminal boundary of 09:30 EDT / 13:30 UTC. Both samples' final
minute starts at 13:29 UTC and completes at 13:30. This is temporal compatibility,
not an independently captured H26 activation/first-trade or security-definition
record. A customary roll date is not a vendor adjustment instruction.

The user confirmed **07:00–14:00 UTC/GMT fixed**, not Morocco local time.
Monday–Friday is an explicit audit assumption, not an enabled policy. Count only
five consecutive native minutes completing by 14:00: the 13:55–14:00 group may
qualify, whereas a group starting at 14:00 cannot. No bars were added or filled;
only the interior of each observed source span was measured.

| Preserved dated sample | Native rows checked | Native rows in UTC window | Fully observed five-minute groups | Candidate-open absent minute slots in window |
| --- | ---: | ---: | ---: | ---: |
| MES H26 | 128,848 | 37,509 | 6,086 | 98,961 |
| MNQ H26 | 142,658 | 42,349 | 6,554 | 87,401 |

Absences cannot distinguish no trades, vendor filtering and feed loss. These
counts are neither completeness percentages nor independent trade counts. A
single deferred H26 contract is not qualified active-contract multi-year history.
Corrections/as-of versions, Bid/Ask, exact assigned costs and complete historical
matching calendars remain unresolved. No correspondence was accessed or sent in
this increment; earlier statements about unsent drafts describe their own dated
checkpoints, not the current provider inbox.

### Current readiness matrix and acceptance criteria

All rows are assessed at this October 10 documentation checkpoint. Supporting
commands, whole-file identities and fresh replay results are in the new
[verification receipt](../../artifacts/earn2trade-50k-readiness/cme-metadata-review/verification.json)
and [source manifest](../../artifacts/earn2trade-50k-readiness/cme-metadata-review/source-manifest.json).

| Requirement | Status | Current evidence / gap | Acceptance criterion |
| --- | --- | --- | --- |
| Advisory isolation and runtime reliability | PARTIAL | No runtime change; preserved safety evidence; failed soak unreconciled | Reconciled reproducible advisory operation and complete forward runs |
| TCP50 policy, accounting and exposure | PARTIAL; positive allowances BLOCKED | Existing semantic gate unchanged; exact progression semantics unresolved | Independently verified boundaries/accounting/mixed exposure and separate scope approval |
| Qualified futures data, provenance and realistic costs | PARTIAL | ZIP/member identities, full-row checks and CME metadata agree; coverage/corrections/quotes/costs unqualified | Qualified dated multi-contract history, complete sessions/corrections and assigned costs/marks |
| Strategy performance on untouched OOS data | MISSING | No strategy run on these samples; no trading-edge evidence | Frozen strategy/cost configuration and sufficient untouched OOS evidence |
| Chronological walk-forward and holdout protection | PARTIAL | Fresh synthetic walk replay and exact comparison; no new holdout access | Qualified chronological folds and preserved untouched holdout with access provenance |
| Intraday selected-firm evaluation simulation | PARTIAL | Legacy TCP25 mechanics replay only; exact TCP50 rules/marks/costs incomplete | Complete rule/mark/execution-exact TCP50 simulation with validated costs |
| Pass/fail estimates, uncertainty and failure reasons | MISSING; probability UNKNOWN | No qualified attempts or validated evaluation horizon | Sufficient qualified paths/horizon, separate PASS/FAIL/CENSORED and stated uncertainty |
| Complete forward paper evaluations and reproducibility | MISSING | Metadata reproducibility is not a forward evaluation attempt | Complete reproducible advisory-only attempts and state reconciliation |

### Verification, preservation and review checkpoint

Original acquisition and private preservation identities, ZIP CRC and exact
CSV-member comparisons pass. Full-row validation finds zero invalid OHLC,
off-tick prices, negative volumes or ambiguous/nonchronological timestamps.
The saved notebook preserves inspectable definitions and bounded aggregate
outputs; its execution and inspection limits are recorded in the receipt.

Fresh public verification repeats path replay, strict current-source checks and
exact complete serialized comparisons for the existing synthetic MES run, edge
and walk. Existing legacy TCP25 **PASS**, **FAIL** and **CENSORED** are verified
separately; all three older source-hash-mismatched envelopes are rejected. These
remain **SYNTHETIC MECHANICS ONLY — LEGACY TCP25**, not TCP50 passing estimates.
No hashed implementation changed, so no simulation regeneration or provenance
rewrite was needed. Verification reuse remains request-scoped.

Before-file identities include the existing coverage outputs and the nine
authorized private files. Earlier artifacts, test reports and private inputs are
preserved; final counts and exact scope differences are in the receipt. No full
suite, static checks or coverage run is claimed for this documentation-only
increment. Historical engineering results below retain their dates and are not
new certifications. **Historical htmlcov preservation remains UNKNOWN** because
the earlier overwritten bytes were never baselined; this cannot be repaired
retroactively. No additional coverage output was generated here.

Official core references were reopened through public web text on October 10;
the detailed original research is dated October 9. No raw PDF/HTML capture or
whole-document checksum is claimed for text-only retrieval. Private rows, account
correspondence and credentials are excluded from public evidence.

Next priorities: resolve provider mapping/activation, corrections, coverage and
Bid/Ask; reconcile historical matching calendars and assigned costs; then present
a narrow executable policy/research scope. No purchase is authorized or inferred.
No services, trading agents, deployment, failed soak, new holdout access or strategy
tuning. Stop for review. **TCP50 positive allowances BLOCKED; passing probability
UNKNOWN; overall Goal remains BLOCKED**, with no unsupported resume/completion.

New evidence directory:
[`cme-metadata-review/`](../../artifacts/earn2trade-50k-readiness/cme-metadata-review/).
The older sections below are historical increments with their original dates.

## Independent review and private preservation — approved 19-file increment, 2026-10-09

The two-axis read-only review found **zero actionable Standards findings and zero
blocking Spec findings** in the preceding 15-file converter increment. Its source,
tests, configuration, financial arithmetic and original evidence are unchanged.
The one wording clarification is inclusive end minus a microsecond rather than a
second; the true exclusive completion gate is correct. Details and review limits:
[read-only-review.md](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/read-only-review.md).

The user separately approved exactly **19 paths**: nine private preserved data/
metadata files, edits to this report and the two existing data-access/provider
notes, and seven new public archive/review/research/identity receipts. The three
previous documents were archived byte-for-byte before these edits. Earlier
source-manifest after-document hashes now resolve to those new archives; original
receipts/hashes were not patched. Public manifests omit private directory
inventories and credentials. No source/test/configuration or `.gitignore` change.

### Durable local storage and qualification limits

Copies of the two original ZIPs, their H26 minute CSV members, original license/
FAQ HTML, retrieval and consent receipts, plus a new private source manifest are
stored in the private local folder `data/private/firstrate/2026-10-09-free-samples/`.
The existing `/data/` ignore covers it. Directory mode 0700 and file mode 0600
protect access; original temporary files remain intact. All eight copied streams
match original SHA256/bytes; ZIP CRC and every captured member identity match,
and extracted CSVs exactly match archive members. Copies do not rewrite the
original acquisition clock or turn retrieval into an earlier historical observation.

This is durable local storage instead of reliance on /tmp, not an off-machine
backup or protection against disk loss. Reopening and reparsing the private copies
at the original explicit cut reproduces the prior selected-snapshot identities,
counts and health exactly. They remain **UNHEALTHY / ABSTAIN** (stale bars/capture,
unknown session gaps and missing quality evidence); source authenticity and full
exchange/correction coverage are still partial. Real provider samples prove intake
mechanics, not strategy edge or evaluation success. No raw price/volume rows are
published in public receipts or added to Git; actual raw files are private/ignored.

### Fresh public-rule and cost assessment

Official sources were freshly inspected on October 9. The
[July update](https://www.earn2trade.com/blog/earn2trade-evaluation-rules-profit-split-update/)
(published July 6, updated July 10, 2026) applies to purchases on/after July 6;
the older March TCP explainer's ten-day statement cannot override it. TCP50 is
not purchased; all planning rules and assigned costs must be rechecked at purchase.
The printed 2/4/6 bands still do not resolve negative profit, fractional-dollar
boundaries, exact progression PnL/fees or mixed-size/netting/order exposure.
The semantic positive-allowance gate remains unchanged and closed.

The [daily-loss article](https://help.earn2trade.com/en/articles/3395926-how-is-my-daily-loss-calculated)
(August 27, 2024) specifies open/closed PnL and commissions over the Central-time
trading day; that does not define the progression algorithm. The
[EOD article](https://help.earn2trade.com/en/articles/5372687-how-does-end-of-day-drawdown-work)
(February 1, 2022) says uploaded Rithmic thresholds take effect when processed and
requires dashboard/provider threshold synchronization. A future forward evaluation
must capture that reconciliation/lag, not assume local arithmetic is the applied
firm floor. No authenticated threshold evidence was inspected.

Freshly matched [commission charts](https://help.earn2trade.com/en/articles/2425493-what-is-the-commission-on-earn2trade-evaluations)
(August 10, 2026 article) omit MES/MNQ. The generic micro range is an example, not
a universal ceiling; other platform micro entries exceed it. Exact MES/MNQ
commissions, full components, spread/slippage and bid/ask equity marks remain
UNKNOWN/unqualified. No retail fees or another instrument substituted for them.
The [cited research note](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/tcp50-rule-cost-research.md)
records exact boundary/aggregation questions, effective-date uncertainty, source
hash limits and **unsent** firm/data-provider clarification drafts. No support
message, account activation, purchase or agreement acceptance occurred here.

### Verification, current readiness and next dependency

The parent reran **64 converter regressions: all passed, zero failures/errors/
skips, 0.67 seconds, no coverage**. This overlaps the earlier 384-focused and
2,506-full engineering reports; counts are not summed. The old full result remains
83.43100320915306% above unchanged 70%, with 562 recorded warnings; no new full
suite/static-check/coverage certification is claimed for documentation/copy work.
Fresh public futures run/edge/walk replay, source checks and exact comparisons
passed again. Legacy TCP25 PASS, FAIL and CENSORED verified separately; all three
old hash-mismatched envelopes were rejected. No persistent verification cache.
No services, runtime agents, live orders, DeFi, deployment, failed soak or new
holdout/strategy work was started. Current coverage identities remain protected;
the earlier unbaselined HTML preservation limitation stays historically UNKNOWN.

All eight readiness dimensions below remain at their disclosed PARTIAL/MISSING
statuses: local sample storage and review do not close exchange completeness,
exact rule/cost semantics, qualified untouched OOS or forward attempts. Next
external dependency is precise current official rule/cost clarification and
qualified data/mark coverage, then an exact approved policy/research scope.
The drafts were not sent; correspondence needs explicit authorization. No purchase
or paid data is a prerequisite inferred from this inspection. Stop for review.
The Goal tool still returned BLOCKED; no supported resume or completion was claimed.
**TCP50 positive allowances BLOCKED; passing probability UNKNOWN.**

This increment's archived documents, current identities and containment/reopening
checks are in
[verification.json](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/verification.json)
and [source-manifest.json](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/source-manifest.json).

## FirstRateData offline intake — approved 15-file increment, 2026-10-09

The following section records the prior source increment before private persistence.
Its original document bytes are preserved in this increment's readiness archive.

Scope: new `scripts/advisory_firstrate_intake.py` and
`tests/unit/test_advisory_firstrate_intake.py`; this report plus
`futures-data-access.md` and `futures-data-provider-options.md`; exactly ten new
receipts under `artifacts/earn2trade-50k-readiness/firstrate-intake/`.
Before-file identities and the byte-for-byte previous report were captured before
edits/tests. Raw samples remain private in their authorized temporary directory.
No account, purchase, subscription, trading agent, deployment, DeFi or failed soak
was started. Only isolated quality-test infrastructure is used for checks.

The user accepted the [provider license](https://firstratedata.com/about/license)
for the two free downloads and separately approved conversion/tests/review.
[FirstRate Data](https://firstratedata.com) is the source. This establishes the
scope of the permitted sample work, not authenticated firm rules or qualified
exchange completeness. No persistent verification or permission cache is added.

### Resulting behavior and sample findings

Only explicitly dated MES/MNQ individual-contract six-column minute CSVs are
accepted. All rows are checked for source format, numerical/tick/OHLC/volume,
chronology, byte/row limits, Eastern/DST and completion by the reported receipt.
Continuous and daily/settlement files are rejected. Five-minute buckets require
all five consecutive minutes and a fully elapsed **exclusive** completion boundary
at the query cut, before serializing inclusive ends. Missing rows remain missing;
no calendar, quality evidence, quote or heartbeat is invented. The requested
latest window is capped at 500 candles and all incomplete/after-cut/limit exclusions
are counted. Public imports, signatures, financial arithmetic, serialized evidence
fields and core schemas are unchanged. All converted results retain ABSTAIN,
false trade/execution permissions and a blocked TCP50 allowance.

| Provider sample | Native minute rows | Complete 5m buckets | Incomplete buckets | Selected |
| --- | ---: | ---: | ---: | ---: |
| MESH26 | 128,848 | 20,778 | 12,137 | 500 |
| MNQH26 | 142,658 | 22,705 | 12,586 | 500 |

Both outputs are **UNHEALTHY**: stale bars/receipt, unverified session gaps and
missing quality evidence. The latest samples end March 20, 2026. The source ZIP,
member and extracted CSV hashes match. Reopened private output was independently
reparsed and compared as complete JSON. Public quality evidence contains only
counts, dates, hashes and unresolved guards, not raw price/volume records.
Classification: **REAL PROVIDER SAMPLE — NOT QUALIFIED TRADING EDGE OR PASSING
PROBABILITY**. No strategy tuning or new holdout access occurred. No seed or trading
cost configuration applies to deterministic conversion; costs remain unqualified.

The [provider FAQ](https://firstratedata.com/about/FAQ) defines Eastern starts,
omitted no-trade minutes and daily settlements. Daily off-tick closes cannot be
classified as corruption without independent settlement evidence. CME tick/point
specifications and final sample timestamps were consistent in the preceding
read-only research, but official historical settlement-price matching remains
unverified. The existing breakout research helper only supports daily candles;
this five-minute import does not create or qualify an intraday strategy.

[Earn2Trade's public commissions article](https://help.earn2trade.com/en/articles/2425493-what-is-the-commission-on-earn2trade-evaluations)
(August 10, 2026) says costs are assigned during setup and can change. Its three
reviewed platform charts do not list MES/MNQ; no exact rate is inferred from ES/NQ
or another micro. [Its asset guidance](https://help.earn2trade.com/en/articles/3320460-what-assets-can-i-trade)
(September 15, 2023) states Rithmic open equity uses Bid/Ask. OHLCV alone cannot
validate exact intraday account marks or fills. These are prospective public
inputs, not authenticated account evidence; recheck all rules/costs at purchase.

### Current readiness dimensions and acceptance criteria

| Requirement | Status | Evidence / limit | Acceptance needed |
| --- | --- | --- | --- |
| Advisory isolation/runtime reliability | PARTIAL | Pure offline converter, no-network/no-write/no-settings fresh-process regression; failed soak remains unreconciled | Separate reproducible advisory operation and reconciled forward runs |
| Correct TCP50 policy/accounting/exposure | PARTIAL; positive allowances BLOCKED | Generic semantic gate and regression suites preserved; progression semantics incomplete | Independently verified exact boundaries/accounting/mixed sizing and separate approval |
| Qualified futures data/provenance/costs | PARTIAL | Two permitted provider samples, byte identities and full-row validation; no independent coverage/correction proof, quotes or assigned costs | Qualified dated multi-contract data, sessions/corrections and realistic costs/marks |
| Untouched out-of-sample strategy performance | MISSING | No strategy run on these samples; synthetic artifacts remain mechanics only | Frozen strategy/costs and adequate untouched OOS evidence |
| Chronological walk-forward/holdout protection | PARTIAL | Existing mechanics replay and source checks; no new holdout access | Qualified chronological folds and preserved untouched holdout |
| Firm-rule intraday evaluation simulation | PARTIAL | Legacy TCP25 PASS/FAIL/CENSORED mechanics only; bid/ask and exact TCP50 semantics missing | Complete rule/mark/execution-exact TCP50 simulation with validated costs |
| Pass/fail estimates/uncertainty/failure reasons | MISSING; probability UNKNOWN | No qualified attempts or defined validated horizon; no success percentage | Sufficient qualified attempt data/horizon, all outcome categories and uncertainty |
| Complete forward paper evaluations/reproducibility | MISSING | Quality tests are engineering checks, not forward evaluation attempts | Reproducible complete advisory-only attempts and reconciliation |

### Verification and review checkpoint

Final focused suite: **384 passed, zero failures/errors/skips, 5.68 seconds**.
It covers the new CSV cases plus existing offline intake, Massive adapter, generic/
wrapper policy and risk regressions. The new fresh-process test rejects network,
settings/.env/store/broker imports and file writes. The initial sandbox diagnostic
was interrupted after two existing asyncio.to_thread service tests timed out;
it reported 220 passes/two failures and is preserved in the checks log. The final
run used normal thread support and passed without changing those tests.

Required full suite: **2,506 passed, zero failures/errors/skips, 562 warnings,
187.92 seconds**. Combined statement/branch coverage: **83.43100320915306%**, above
the unchanged 70% gate and original source/omit configuration. The authentication
and SELECT-only writer-lease opt-ins were enabled, so none of the three optional
checks skipped. Warnings are principally existing datetime/deprecation warnings,
recorded in full-tests.log; none were hidden or converted into trading claims.
Focused and full counts overlap and are not summed.

Repository Ruff, Black check (243 files), isort check (13 configuration-skipped
files), architecture (six packages) and strict MyPy (118 sources, including the
new script) pass. Current tests are engineering evidence only. The three existing
isolated paper PostgreSQL/Redis/Kafka containers were started for the suite and
restored to their original stopped states; the loopback ephemeral Kafka-auth
fixture was removed. No failed-soak or deployment containers were started.
Post-test containment found only the five approved source/test/documentation
paths before receipt publication, no deletions, no private-file changes, and all
137 existing htmlcov/.coverage file identities preserved.

Reproduction: `checks.log` records exact commands/environment destinations, service
state restoration, initial diagnostics and fresh artifact replay. `focused-tests.xml`
and `full-tests.xml` independently confirm counts/skips; `coverage.json` records
measured totals. `source-manifest.json` records before/after identities and allowed
paths; `verification.json` captures independent reopening/preservation checks.
The ten approved receipt files are listed in that manifest. The pre-increment
report is archived byte-for-byte as `readiness-before.md`.

The previous unbaselined HTML coverage overwrite remains historically UNKNOWN;
its original bytes cannot be recovered or retroactively certified. Current run
baselines include existing ignored `htmlcov/` and `.coverage`; explicit HTML,
JSON/XML/data, pytest/Hypothesis/temp and tool-cache destinations are under /tmp.
Bytecode and pytest cache writes are disabled. The capture excludes dependency/
tool metadata directories and symlinks and keeps private identities unpublished.
Only the approved receipts are copied into the repository after reopening checks.

Current source identities still match the existing futures run/edge/walk and
legacy simulation envelopes: no regeneration is needed because their hashed
modules did not change. Fresh public verification repeats path replay, source
checks and exact full JSON comparisons. PASS, FAIL and CENSORED legacy TCP25
examples are reported separately; older hash-mismatched envelopes are rejected,
never patched. Earlier receipts retain their historical hashes; the former report
identity resolves to the new byte-identical `readiness-before.md` archive.

At approval time `get_goal` returned BLOCKED. The goal tool has no agent resume
operation, so no supported activation is claimed. The broader objective remains
unfinished; this increment is not marked complete as overall readiness.
Stop for user review before expanding scope, storage, strategy work or deployment.
**TCP50 positive allowances remain BLOCKED. Passing probability UNKNOWN.**

## Massive offline normalization — 2026-10-09

Approved scope is exactly four repository files: new
`scripts/advisory_massive_intake.py`, new
`tests/unit/test_advisory_massive_intake.py`, this maintained report and
`docs/maintenance/futures-data-access.md`. Existing core/provider/risk/policy
imports, signatures, serialized evidence, financial calculations and holdout
boundaries are unchanged. Existing snapshot, bounded-window and health components
are reused. No persistent verification cache or runtime integration is introduced.

The adapter reads existing aggregates and point-in-time contract responses,
resolves a one-digit provider year using matching expiry metadata, preserves
Decimal prices/integer timestamps, and returns the bounded existing preflight.
Its native intervals start at five minutes; the separate three-bar one-minute
access probe is insufficient and is not silently aggregated. Missing source
quality remains UNKNOWN, even after structurally valid conversion. TCP50 remains
BLOCKED; the output always abstains and disables trading/execution.
See [inputs, usage and limitations](futures-data-access.md#massive-offline-adapter--2026-10-09).

Authenticated browser observations on October 9 confirmed **Futures Basic,
Individual, $0/month** and four limited REST HTTP 200/OK responses for MESZ6/MNQZ6
contract metadata and three one-minute bars per contract on October 8. The legal
page showed **No agreements**, not a grant of retention/replay rights. The
authorized support question was submitted; its observed checkpoint showed
**Waiting for a teammate**. Anna's later reply, supplied by the user and
independently read in the authenticated conversation on October 9, says published
terms control and support does not provide individual-use-case authorizations or
modify the agreement. Both linked terms were freshly reopened. This supersedes
the waiting checkpoint without supplying a separate permission grant. The
[clause references and next review](futures-data-access.md#verified-account-access-unresolved-rights)
are recorded separately. No keys, contact details or raw provider rows are
preserved in this increment. No new account, agreement, purchase, subscription
change or paid data request occurred.

Engineering is PARTIAL; small account data access is VERIFIED for that probe only;
storage/replay licensing is NOT ESTABLISHED. Qualified history, costs, strategy
OOS/holdout evidence, forward evaluations and operational readiness remain missing
or partial as separately recorded below. Passing probability remains UNKNOWN.

Before edits/tests, byte-identical copies of both documentation files and whole-file
SHA256/mode identities were captured in `/tmp/alghrest-massive-offline-segcw58z/`.
The baseline includes 2,462 public regular files, 1,214 prior public artifacts,
136 current HTML coverage files and `.coverage`. Private identities are compared
without publishing credentials or private paths. Test evidence is kept in this
temporary directory to respect the four-file repository scope; it must be
preserved elsewhere before temporary-file cleanup if permanent receipts are needed.
The earlier HTML overwrite cannot be retrospectively certified because its prior
bytes were not hashed; this limitation remains visible.

### Verified results for this increment

- Final focused regressions: **353 passed, zero failures/errors/skips**, 8.72
  seconds, including **64 new adapter cases**. Tests cover both micros, native
  resolutions, exact prices/times, expiry/year relationships, malformed and
  paginated input, missing quality, duplicate/overlapping/unfinished bars, empty
  and earlier cuts, credential-safe errors and subprocess-wide isolation traps.
- Final full isolated suite: **2,442 passed, zero failures/errors/skips**, 145.01
  seconds, **562 non-failing warnings**, principally existing deprecations.
  Aggregate statement/branch coverage is **83.43100320915306%** against the
  unchanged **70%** gate over agents/core/connectors. This is software coverage,
  not readiness or a passing probability. Focused/full counts overlap and are
  not summed. The Kafka authentication and two real writer-lease tests were
  explicitly enabled; no skips were suppressed.
- Ruff, Black (241 files), isort, strict MyPy (118 source files, including both
  intake scripts) and all six application architecture boundaries pass. The
  isort log reports nine configured file exclusions; these are not pytest skips.
  The
  full run also confirmed unchanged whole-file identities for **238 Python
  source/test files** throughout its execution. Existing financial/evidence
  modules are byte-identical to the before baseline; source-hash verification
  remains strict. No old envelopes or provenance fields were patched, and no
  affected financial evidence required regeneration. Earlier artifact replay
  results below remain dated historical results, not new replay certifications.
- The separately reproduced synthetic CLI input normalizes three native
  five-minute bars exactly, reports `missing_quality_evidence`, remains UNKNOWN,
  ABSTAIN/BLOCKED, and exits **2 as intended**. No source-quality evidence,
  historical clock, quote, exchange session, cost or permission is fabricated.
- Initial failures are retained: a 60-second sandboxed threaded asyncio timeout,
  Ruff import/exception/type-union style findings, two MyPy annotations and a
  temporary full-suite launcher import-path error. The resolved final checks
  above supersede those attempts; the failed launcher restored service states.
- Only the existing isolated paper PostgreSQL/Redis/Kafka infrastructure was
  temporarily started for quality tests and restored to the same stopped
  container identities. The SASL test used its existing disposable loopback
  broker fixture. No trading agents, deployment services or failed soak were run.

Temporary receipts include `commands.jsonl`, `full-frozen-command.json`,
`focused-release.log`, `focused-release.xml`, `full-frozen.log`,
`full-frozen-tests.xml`, `coverage.json`, `coverage.xml`, `source-stability.json`,
`test-source-identities.json`, `services.json`, static-check logs, the synthetic
inputs/CLI diagnostic, `source-manifest.json` and `verification.json`.
The full runner and local service-lifecycle wrapper are retained there as well;
they contain no embedded credentials. All coverage data, HTML/JSON/XML reports,
pytest temporary paths, Hypothesis storage, tool caches and generated bytecode
policy were directed outside the checkout. The configured HTML reporter was
explicitly overridden with
`--cov-report=html:/tmp/alghrest-massive-offline-segcw58z/htmlcov`; pytest cache and
bytecode writes were disabled. Final containment confirms exactly the two
approved new files and two documentation edits, no deletions, and preservation
of all **1,214 earlier public artifacts**, 136 current HTML coverage files,
`.coverage` and baselined private files. No out-of-scope regular-file write was
found among the inventoried paths. Dependency/tool metadata directories and
symlinks remain excluded; no universal filesystem audit is claimed.

Goal readback remains **BLOCKED**. No unsupported resume or broader Goal
completion is claimed. This increment is complete and stopped for review.
Next external review is a clause-based assessment of Massive's published terms,
incorporated CME agreement and applicable subscriber facts for retention,
automated replay and prospective TCP50 use; no bespoke support authorization or
paid upgrade is presumed. Next research needs qualified history, defined costs, protected
chronological OOS/holdout design and forward paper evidence. TCP50 positive
allowances remain blocked pending independently verified and separately approved
progression semantics. Passing probability stays UNKNOWN; no trading edge is
claimed.

## Earlier proposed source-data providers — 2026-10-09

The user's new list is a candidate-source lead, not evidence that data is now
available or licensed. [The verified comparison](futures-data-provider-options.md)
separates public capability, current fee evidence, unknown grant/quote facts and
data suitability. Databento historical-only usage pricing can be considered
independently of a live subscription or Earn2Trade API credentials. IBKR's quoted
CME non-professional fees are publicly documented but carry account/API prerequisites.
FirstRateData's $199.95 acquisition figure and a current official $25 Tradovate
API price remain unverified in the successfully retrieved sources.

The universal “under 24 hours means an additional non-display fee” assertion is
not adopted. Exchange and provider definitions, user classification and supported
use matter; the note documents the primary-source distinctions. No exemption,
license category or fee was assigned to the user. Continuous series cannot replace
dated raw-contract identity and causal roll evidence in financial simulations.

Documentation-only scope: this maintained report, new
`docs/maintenance/futures-data-provider-options.md`, and three new evidence files
under `artifacts/earn2trade-50k-readiness/provider-options-research/`:
`readiness-before.md`, `source-manifest.json`, `verification.json`.
Before-file identities and a byte-identical report archive were captured before
edits. Source/configuration/tests, earlier artifacts, private files and current
coverage reports are preserved. No provider signup, agreement acceptance, credit
activation, data download, purchase, account connection, message, runtime test or
service startup occurred. Historical HTML preservation remains UNKNOWN.

At that documentation-only checkpoint, the next useful external evidence was an eligible provider's specific permitted-use
confirmation and a quote/sample scope; the question draft was UNSENT. No
provider had been selected or activated. The later Massive observation and sent
support inquiry above supersede that access snapshot. TCP50 allowances remain BLOCKED and
passing probability UNKNOWN; research does not establish strategy edge.

## Offline intake and independent readiness dimensions — 2026-10-08

The current workspace is `/home/xsabo/Projects/MY project/alghrest-main`.
`git status`/branch discovery fails because Git metadata is not usable here;
no branch, clean-tree or commit provenance is asserted. Before-file SHA256/mode
identities and a byte-identical copy of this report were captured before edits
and tests. Root AGENTS/CLAUDE and quality/migration documentation were inspected.
The source API maps both TCP25 and TCP50; research Compose selects
`earn2trade_tcp50`. TCP25 remains legacy compatibility, not this user's target.
No `.env` values are published or changed; no running deployment is certified.

The audit found existing provider-neutral snapshot requests, local replay,
data-health/event guards, deterministic risk, policy verification, advisory-only
capabilities, backtesting and a review API. It found no local data-intake CLI.
The selected increment adds that entry point rather than duplicating these
components. `scripts/advisory_intake.py` inspects an existing MES/MNQ snapshot with
an explicit contract and clock, returns source-byte identity, window counts and
quality reasons, and always abstains from trading. Structural/quality success
cannot qualify licensing, evaluation compliance, costs or strategy edge.

See [usage, provider evidence and unsent support inquiries](futures-data-access.md).
The command imports no settings, storage or broker module. A fresh-process audit
test rejects network connections, database access, writes and `.env` reads.
Invalid/missing data, stale clocks, duplicate bars/JSON keys, mismatched contract,
off-tick prices and injected permission/options remain rejected or unassessable.
Existing imports/signatures, serialized evidence, financial arithmetic, policy
gates and holdout behavior are unchanged. No provider integration was enabled.

| Dimension | Current status | Exact blocker / unblocked work |
| --- | --- | --- |
| Engineering readiness | PARTIAL | Tested local preflight now usable; approved-data onboarding and bounded advisory operation remain unverified |
| Market-data access and licensing | PARTIAL | Small Massive Basic REST probe works; recording/replay rights and suitable qualified history remain missing; synthetic mechanics remain usable for engineering |
| Evaluation-rule verification | PARTIAL / TCP50 allowances BLOCKED | Printed bands are recorded, but negative profit, cents, accounting, mixed micros and downward transitions remain unresolved; recheck at purchase |
| Strategy validation | MISSING | No qualified untouched OOS edge, realistic assigned costs or sufficient evaluation paths |
| Live advisory readiness | CANNOT ASSESS | Fresh permitted feed, assigned account observations and forward operational evidence missing; failed soak still unreconciled |

### Current verification

- New CLI diagnostics: **28 passed** initially. Final focused regressions:
  **693 passed, zero skipped/failed, 36 deprecation warnings**, 11.63 seconds.
- Required full isolated suite: **2,375 passed, 3 skipped, zero failures/errors,
  562 warnings**, 140.61 seconds. Coverage **83.42402678945166%**, unchanged 70%
  gate and source configuration. Focused/full counts overlap and are not summed.
- Skips: real Kafka authentication needs `KAFKA_AUTH_TESTS=1`; two SELECT-only
  accounting/execution writer-lease checks need `WRITER_LEASE_TEST_DATABASE_URL`.
  These checks were unverified by that full-suite run; the separate follow-up
  below exercises all three opt-ins. The existing full suite was not weakened.
- Ruff, Black check (239 repository files), isort, strict MyPy (117 sources,
  including the new CLI), architecture (six packages) pass. Two initial Ruff
  list-concatenation findings in the new tests were corrected. A sandboxed focused
  attempt timed out after 60 seconds in a threaded path; its failure log is kept
  separate from the successful normally threaded rerun.
- Fresh public run/edge/walk replay, source checks and exact JSON comparisons
  pass. Existing regenerated legacy TCP25 examples pass separately as **PASS**,
  **FAIL**, **CENSORED**; all retain `rule_exact_verified=false`. Three older
  source-mismatched envelopes are rejected. No shared evidence source changed,
  so no historical envelope was rewritten or regeneration needed. Verification
  reuse remains request-scoped; no persistent cache was added.
- Only existing isolated local PostgreSQL/Redis/Kafka were temporarily started;
  identical container IDs were restored to their prior stopped states. No agents,
  trading services, deployment or failed soak were started.

### Evidence and containment

The new directory
[`offline-intake/`](../../artifacts/earn2trade-50k-readiness/offline-intake/)
contains: `readiness-before.md`, `source-manifest.json`, `verification.json`,
`commands.json`, `focused-tests.xml`, `focused-tests.log`, `full-tests.xml`,
`full-tests.log`, `coverage.json`, `checks.log`, `diagnostic-timeout.log`,
`initial-tests.log`, `replay.py`, `replay-results.json`, `synthetic-MNQ-snapshot.json`, and
`synthetic-MNQ-preflight.json`. The last two are **SYNTHETIC MECHANICS ONLY**.
The new source/test/documentation files are `scripts/advisory_intake.py`,
`tests/unit/test_advisory_intake.py`, and `docs/maintenance/futures-data-access.md`;
this maintained report is the only pre-existing file changed.

Before baseline: **2,432 public regular files**, including **1,188 earlier public
artifact files**, **136 HTML coverage files**, and `.coverage`. Dependencies,
tool metadata, symlinks and private directories are excluded from published
identities; applicable private files were compared without publishing them.
All coverage data/reports, pytest temporary files, Hypothesis storage, bytecode
policy and tool caches were contained outside the checkout. In particular the
HTML reporter was explicitly overridden with
`--cov-report=html:/tmp/alghrest-offline-intake-nkph7hya/htmlcov`.
No retrospective claim is made about the earlier HTML overwrite whose prior
bytes were not captured. The prior three Hypothesis additions remain preserved.
Current preservation, output identities, exact commands and limitations are in
the new [manifest](../../artifacts/earn2trade-50k-readiness/offline-intake/source-manifest.json)
and [verification receipt](../../artifacts/earn2trade-50k-readiness/offline-intake/verification.json).

Next practical milestone: inspect a small permitted MES/MNQ sample and its
provenance through this command, then plan chronological qualification using the
existing replay engine. The smallest user input is an existing provider/dataset
name and available dates, or confirmation that none is available; no credentials
are needed. Provider support drafts are UNSENT. API permissions and TCP50
semantics are separate dependencies. Passing probability remains **UNKNOWN**.

## Optional quality checks follow-up — 2026-10-08

The three tests skipped by the preceding full suite were independently runnable
without licensed market data, provider approval or completed TCP50 progression
rules. A bounded follow-up enabled the existing test opt-ins and passed **3 tests,
zero failures/skips, no reported warnings**, in **5.68 seconds**:

- Kafka SASL wire test: anonymous and wrong-key connections rejected, authenticated
  publish/consume accepted, using a disposable local broker and synthetic message.
- Accounting writer lease: concurrent checks on one owner succeed, another owner
  is excluded, and releasing the session permits the next owner.
- Execution writer lease: the same session ownership/exclusion/release behavior.

The lease tests issue SELECT/session advisory-lock operations against the isolated
`alghrest_quality` database, without financial or schema writes. Only the existing
paper PostgreSQL container was started, then restored to its prior stopped state.
Redis and the existing paper Kafka remained stopped. The authentication fixture
used the already-cached `apache/kafka:4.3.1` image, a loopback-only ephemeral port,
no mounted runtime volumes and an isolated topic; its temporary container was
confirmed removed. Test credentials were generated in memory and not published.

No source, configuration or tests changed. The historical full-suite receipt still
accurately records **2,375 passed / 3 skipped** and **83.42402678945166%** coverage.
This focused `--no-cov` follow-up is a separate three-test result, not a rerun of
the full coverage gate or permission to sum overlapping run counts. The failed
564-cycle soak remains unreconciled and was neither restarted nor certified.
No provider connection, live account, new holdout access or trading action occurred.

Evidence is in
[`optional-quality-checks/`](../../artifacts/earn2trade-50k-readiness/optional-quality-checks/):
`readiness-before.md`, `run_checks.py`, `commands.json`, `tests.xml`, `tests.log`,
`source-manifest.json`, and `verification.json`. The previous maintained report
was archived byte-for-byte before this documentation edit. The prior intake
manifest remains a historical snapshot; its report hash matches this new archive,
not the subsequently updated maintained report. All prior artifact bytes and
existing source/configuration/tests are preserved. Coverage/cache/temp output was
redirected outside the checkout; the earlier historical HTML preservation gap
remains UNKNOWN. Current output containment and source identities are recorded in
the [new receipt](../../artifacts/earn2trade-50k-readiness/optional-quality-checks/verification.json).

Engineering validation has advanced, while licensed data, complete selected rules,
qualified OOS strategy evidence and forward advisory operation remain incomplete.
TCP50 positive allowances remain BLOCKED; passing probability remains UNKNOWN.

**User update, 2026-10-08:** the user explicitly confirmed that no MES/MNQ data is
currently available. Dataset availability is therefore a confirmed external gap,
not merely absence from the inspected default store. No provider was selected and
no purchase, subscription, trial or agreement was authorized. The next external
step is to clarify an eligible source and permitted recording/replay/analysis use
using the [unsent provider inquiries](futures-data-access.md#unsent-inquiries-for-the-user).
Software testing can continue with labelled synthetic inputs, but qualified
strategy validation and passing-probability estimation cannot advance without
suitable permitted data. A provider response or already-permitted data source is
the next useful input; no credentials are needed.

## Official progression evidence capture, 2026-10-08 UTC

The [official TCP progression article](https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path)
was freshly captured at 2026-10-08T10:15:48.095652Z. Its linked original chart
was inspected independently twice, using the **TCP50 Evaluation** block.
The literal printed rows are:

| Printed evaluation profit range | Printed maximum contracts |
| --- | ---: |
| $0–$1,500 | 2 |
| $1,501–$2,000 | 4 |
| $2,001+ | 6 |

These are public prospective limits, not an assigned-account receipt or a
complete executable schedule. The article describes aggregate open contracts,
real-time account balance/profit, immediate evaluation failure if the limit is
exceeded, and up to ten listed qualifying micros counting as one standard.
It lists MES, MNQ, MYM, M2K, MGC, MCL, M6B, M6E and MHG.

**Complete progression semantics remain PARTIAL.** The inspected source does
not resolve negative profit, fractional-dollar profits strictly between
$1,500/$1,501 or $2,000/$2,001, the exact progression balance/PnL accounting
formula, or mixed-contract rounding. No continuous thresholds, lower loss-band
permission, rounding rule or grace period was inferred. The current lower-bound
policy model requires coverage down to the initial drawdown floor and assesses
equity at the stop; extending this chart below its stated $0 profit would invent
missing firm rules. TCP50 READY eligibility and positive allowances remain blocked.

The article displays July 6, 2026; the chart has no separate effective date.
The [official rule-update announcement](https://www.earn2trade.com/blog/earn2trade-evaluation-rules-profit-split-update/)
was published July 6 and updated July 10, 2026. It applies its enforcement change
to purchases on/after July 6, 2026. That date does not independently establish
when the numerical chart thresholds became effective. TCP50 is not purchased;
recheck public and assigned rules at purchase.

The [captured article](../../artifacts/earn2trade-50k-readiness/tcp50-progression-research/official-progression.html)
and [original chart](../../artifacts/earn2trade-50k-readiness/tcp50-progression-research/official-progression-chart.png)
retain exact source bytes. Chart SHA256:
`569e6734757d66d11d83700322db9a5b61af482e4130ae64dcac17a8d2cd83c0`.
The two independent chart downloads match byte-for-byte; the captured HTML
links to that same chart path. HTML includes the public CDN's temporary signed
image URL; this is a public asset link, not a user/account credential.
Raw rule-update retrieval returned HTTP 406, while the primary page was readable
and verified through the web tool. No raw-byte hash or archived HTML is claimed
for that corroborating announcement. This limitation is recorded separately.

This increment changes only this maintained report and creates six evidence files
under `artifacts/earn2trade-50k-readiness/tcp50-progression-research/`:

1. `readiness-before.md` — byte-identical before-report archive.
2. `official-progression.html` — original public article bytes.
3. `official-progression-chart.png` — original linked chart bytes.
4. `official-progression.json` — literal transcription, source/date identities,
   independent inspection, public applicability and unresolved cases.
5. `source-manifest.json` — before/after identities and preservation evidence.
6. `verification.json` — source relationship, PNG integrity, transcription,
   archive/link/sensitive-pattern checks and output-containment results.

The [public evidence record](../../artifacts/earn2trade-50k-readiness/tcp50-progression-research/official-progression.json),
[manifest](../../artifacts/earn2trade-50k-readiness/tcp50-progression-research/source-manifest.json)
and [verification receipt](../../artifacts/earn2trade-50k-readiness/tcp50-progression-research/verification.json)
record fresh checks for this evidence capture. The preserved before baseline has
2,426 public regular files, including 1,182 older public artifacts, all 136
current HTML coverage files and root `.coverage`. Private identities are withheld.
Reopened output hashes, article/chart linkage, PNG integrity, literal agreement
and local documentation links pass. No out-of-scope regular-file changes were
found. Historical HTML preservation remains UNKNOWN because its earlier
before-bytes were never hashed; the prior three Hypothesis-cache additions are
preserved as part of this increment's before baseline, not retroactively excused.
Symlinks and excluded dependency, private and bytecode directories are outside
the inventory. Source/configuration/tests, `.env`, earlier evidence and receipts
remain unchanged. No runtime tests, services or failed soak were started.

The numerical tests and simulation replays below belong to previous increments;
they were not rerun or reused as fresh outcome verification in this public-source
capture. No performance outcomes were consumed and no simulation source hashes
changed. These archival receipts are not a runtime verification cache and cannot
unlock policy eligibility. Passing probability remains UNKNOWN; this work adds
no trading-edge evidence or trading permissions.

Before proposing executable bands, obtain official clarification of the unresolved
cases above, then separately review the runtime file scope. No support message
was sent and no authenticated account was accessed. Stop for review after this
documentation/evidence increment; the broader readiness Goal remains unfinished.

## TCP50 gate correction, verified 2026-10-08 UTC

The reported bypass was independently reproduced against pre-edit source using
deterministic synthetic inputs: generic `EODPolicy(tcp50_rules(), controls)`
produced READY, `verify_policy_assessment` accepted it, and its allowance admitted
10 MNQ contracts from hypothetical confirmed bands. `TCP50Policy` returned
UNKNOWN with no allowance for those same inputs. The cause was a restriction
implemented only in the API-selected wrapper, while generic producers and
verification treated captured hypothetical bands as sufficient evidence.

The shared policy now identifies unresolved TCP50 by **Trader Career Path plus
$50,000 initial capital**, in either rules or the related account profile.
Mutable policy IDs/versions do not identify eligibility. Generic assessments
remain UNKNOWN/BLOCKED; READY reconstruction/serialization and direct verification
reject forged TCP50 assessments. Generic allowance validation uses the same gate;
the wrapper preserves its existing downgrade-to-UNKNOWN behavior.

Risk qualification now requires a reproducible READY policy assessment joined to
the account, journal revision, current balance, allowance policy identity and
assessment clock. An allowance alone has no program/initial-capital fields, so a
missing assessment cannot establish a non-TCP50 exception and remains UNKNOWN.
Serialized positive decisions and saved-record verification enforce these
requirements; copied qualification flags cannot bypass revalidation. All public
imports/signatures and serialized field declarations are preserved. Financial
formulas are unchanged; TCP25 regressions and a synthetic non-TCP50 EOD control
retain their prior arithmetic. TCP25 current equity of $50,000 does not change
its original $25,000 program semantics. No bands were implemented or inferred.

| Current correction check | Verified result |
| --- | --- |
| Focused advisory/policy/evidence suites | 976 passed, 0 failed/errors/skips, 36 deprecation warnings, 36.07 seconds |
| Required complete repository suite | 2,347 passed, 0 failed/errors, 3 skipped, 562 warnings, 156.64 seconds |
| Engineering coverage | 83.41007395004884%; unchanged 70% gate; not trading success |
| Ruff / Black check / isort check | PASS; Black checks 235 files |
| Strict MyPy / architecture | PASS; 116 source files / all six application packages |
| Public run / edge / walk artifact verification | Fresh source checks, path replay and exact comparisons PASS; bytes unchanged |
| Legacy evaluation tapes | Separate PASS / FAIL / CENSORED replay exactly; old mismatched envelopes rejected |

Focused and full counts overlap and are not summed. Skips remain the optional
real Kafka authentication check (`KAFKA_AUTH_TESTS=1`) and two SELECT-only
PostgreSQL writer-lease checks (`WRITER_LEASE_TEST_DATABASE_URL`); those real
authentication/lease prerequisites are not certified. Warning details and exact
commands are retained in the logs and receipt. Development red tests reproduced
the generic bypass, missing assessment, and detached positive-record joins.
Sandbox worker-thread diagnostics stalled; authoritative suites used normal
local thread support. Early fixture assertions were corrected before those runs.
Only the existing isolated PostgreSQL/Redis/Kafka quality services were started;
their original exited state and container identities were restored. No trading
agent, deployment or failed soak was started.

The before baseline covered 2,411 public regular files, including all 136 current
`htmlcov/` files and root `.coverage`, before edits/tests. All 1,170 earlier public
artifacts and the privately compared files remained byte/mode identical; private
identities are withheld. The readiness report is archived byte-for-byte in the
new `readiness-before.md`. Each regenerated example is **SYNTHETIC MECHANICS ONLY
— LEGACY TCP25**: original tape, costs, configuration, events, steps, numerical
outcome and fields remain identical; only `shared_source_sha256` differs.
They were reopened and independently verified. No provenance was patched.
Verification reuse remains request-scoped; no persistent verification cache exists.

The full-suite command explicitly uses
`--cov-report=html:/tmp/alghrest-tcp50-policy-gate-fix/htmlcov`; coverage data,
JSON/XML, pytest temporary directories and authoritative-suite Hypothesis/tool
caches are also directed to `/tmp`. Existing HTML and `.coverage` match this
increment's before hashes. **Historical HTML preservation remains UNKNOWN:** the
earlier increment never hashed its prior generated bytes; this cannot be repaired
or retroactively certified.

**Current containment exception:** a diagnostic pytest collection command omitted
the Hypothesis storage override and created three ignored constant-cache files:
`.hypothesis/constants/06e65e58d566f3aa`,
`.hypothesis/constants/3db9a83c782e15c6`, and
`.hypothesis/constants/b5dc44006839e714`. They are preserved, identified in the
manifest, and not deleted or altered outside scope. No other out-of-scope regular
file additions, removals or byte/mode changes were found. Therefore an exact
17-path-only worktree claim is **not** made. Symlinks and excluded dependency,
private and bytecode directories are outside the inventory; bytecode generation
and pytest cache writes were disabled. `pyproject.toml` is unchanged.

The exact authorized correction scope is these five modified existing paths:

1. `src/core/advisory/policy.py`
2. `src/core/advisory/risk.py`
3. `tests/unit/test_evaluation_policy.py`
4. `tests/unit/test_advisory_risk.py`
5. `docs/maintenance/earn2trade-50k-readiness.md`

These twelve new paths share prefix
`artifacts/earn2trade-50k-readiness/tcp50-policy-gate-fix/`:

1. `readiness-before.md`
2. `source-manifest.json`
3. `verification.json`
4. `focused-tests.xml`
5. `focused-tests.log`
6. `checks.log`
7. `full-tests.xml`
8. `full-tests.log`
9. `coverage.json`
10. `mechanics/legacy-tcp25-conditional-pass.json`
11. `mechanics/legacy-tcp25-daily-fail.json`
12. `mechanics/legacy-tcp25-censored.json`

The [correction receipt](../../artifacts/earn2trade-50k-readiness/tcp50-policy-gate-fix/verification.json)
and [source manifest](../../artifacts/earn2trade-50k-readiness/tcp50-policy-gate-fix/source-manifest.json)
record whole-file identities, commands/results, preserved evidence, and the
containment exception. All outputs were staged/verified before publication into
these approved paths and reopened afterward. The broader Goal still reports
BLOCKED; its tools expose no supported agent resume or objective edit. It has not
been marked complete; no active Goal was available to pause at this checkpoint.
Stop for review. **TCP50 positive allowances remain blocked; passing probability
UNKNOWN; no trading-edge claim.** The readiness gaps below remain unresolved.

## Confirmed target and prospective applicability

Current public rules were reviewed at 2026-10-07T14:44:14Z. Their effective
purchase-date version is separate from retrieval/build dates. **Recheck rules
when purchasing**, retain the actual purchase date, and compare assigned terms
before treating the policy as account-confirmed.

| Public TCP50 evaluation parameter | Reviewed value | Evidence status |
| --- | --- | --- |
| Virtual starting balance | $50,000 | VERIFIED public evaluation data |
| Profit target | $3,000 | VERIFIED current linked TCP50 evaluation data and rendering path |
| EOD drawdown distance | $2,000 | VERIFIED public evaluation data and TCP comparison |
| Daily loss limit | $1,100 | VERIFIED public evaluation data and TCP comparison |
| Absolute standard-contract ceiling | Up to six | VERIFIED ceiling; no initial/universal allowance |
| Fixed minimum trading days | None; model value zero | VERIFIED prospective purchase-date update |
| Consistency | Each day's contribution strictly below 30% of total PnL | VERIFIED public evaluation rule |
| Progression chart / complete executable semantics | PARTIAL | Printed TCP50 2/4/6 rows verified; negative profit, fractional boundaries and exact accounting/rounding unresolved; no inferred/default bands |
| Assigned floor, margin, fees, calendar, platform terms | MISSING | No authenticated account before purchase |

The [current official product page](https://www.earn2trade.com/trader-career-path)
initially renders TCP25 in text extraction. Its freshly retrieved linked
[plan-data asset](https://www.earn2trade.com/_next/static/chunks/088_ythjijpd8.js)
explicitly identifies TCP50's Evaluation entry. The actual TCP50
[selector](https://www.earn2trade.com/_next/static/chunks/0tsxyqu5bf8dg.js)
uses that entry in evaluation mode; the
[specification renderer](https://www.earn2trade.com/_next/static/chunks/0c7ravcyylcpb.js)
maps its capital, goal, EOD drawdown, daily loss and ceiling to the evaluation
card. This was independently reviewed from fresh downloaded public bytes,
without executing website JavaScript. It resolves the earlier indexed-card
uncertainty; it is not a browser-observed purchase or authenticated account.

The [official TCP comparison](https://www.earn2trade.com/blog/introducing-tcp10/)
was published 2024-07-01 and updated 2025-10-10; it corroborates the explicit
TCP50 capital/risk limits. The numerical effective date is not stated.
The [July rule update](https://www.earn2trade.com/blog/earn2trade-evaluation-rules-profit-split-update/)
was published 2026-07-06 and updated 2026-07-10, applying to purchases on/after
2026-07-06. It removes the fixed ten-day minimum and makes progression excess
an immediate evaluation failure. The [evaluation overview](https://help.earn2trade.com/en/articles/5941958-what-are-the-evaluation-rules)
corroborates this. Four profitable days follow from consistency rather than a
separate fixed minimum. [Consistency help](https://help.earn2trade.com/en/articles/3849975-what-is-the-maintain-consistency-rule)
specifies the strict threshold; concentration delays qualification.

The [official-rule receipt](../../artifacts/earn2trade-50k-readiness/tcp50-policy/official-rules.json)
records source URLs, whole-file source hashes, data/rendering trace, retrieval
limitations, dates, and unresolved evidence. Static asset names identify the
retrieved website build, not the effective date of assigned account rules.
GAU50, TCP25, funded growth targets, and subscription discounts are not substitutes.

[Daily loss](https://help.earn2trade.com/en/articles/3395926-how-is-my-daily-loss-calculated)
includes realized and unrealized PnL and commissions; touching the limit fails.
Sessions use America/Chicago and 17:00 CT rollover, including DST.
The [EOD floor](https://help.earn2trade.com/en/articles/5372687-how-does-end-of-day-drawdown-work)
rises with higher closing balances, never retreats, caps at starting balance,
and constrains open equity intraday. The computed initial $48,000 floor is public
arithmetic, not an assigned-floor receipt; platform/dashboard synchronization is
still required. Equality remains a failure boundary.

The [TCP progression source](https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path)
covers aggregate open exposure and real-time balance. It lists ten-to-one micro
exceptions for MES, MNQ, MYM, M2K, MGC, MCL, M6B, M6E and MHG.
Exact bands, mixed-root rounding, netting and working-order reservation semantics
remain unverified. The policy retains the existing bounded research universe;
it does not add all firm-eligible products.

[Approved trading times](https://help.earn2trade.com/en/articles/3224526-are-there-any-restrictions-on-when-i-can-trade-in-my-evaluation-account)
cover positions and working orders, instrument-specific restrictions, holidays
and exchange closures. [Commissions](https://help.earn2trade.com/en/articles/2425493-what-is-the-commission-on-earn2trade-evaluations)
depend on assigned platform/instrument terms. Generic prices, zero fees and
synthetic costs cannot replace assigned fees or realistic spread/slippage.

## Implemented behavior and preserved boundaries

`tcp50_rules()` and `TCP50Policy` reuse the existing EOD engine.
The `earn2trade_tcp50` settings value selects the policy in the advisory API;
the isolated research Compose configuration uses that restrictive profile.
Legacy TCP25 imports, signatures, rules and behavior remain supported.
Existing serialized models and generic EOD arithmetic are unchanged.

Exact progression semantics remain unresolved, so the reusable policy adds
`unverified_tcp50_progression_limits`, retains UNKNOWN/BLOCKED status and
prevents positive allowances. A caller-supplied confirmed flag or synthetic
table cannot clear this guard. A detached READY assessment, renamed policy,
missing assessment or saved positive risk record also cannot bypass it.
Removing the guard requires a separately verified,
reviewed progression implementation; no default six-contract permission exists.

The API creates no journal or session on startup, retains account-role and
approved-strategy gates, preserves missing-evidence blocking, and offers no
order endpoint. Existing profiles are not rescaled. The three-journal A/B/C
AccountPlan requirement remains unresolved for a single evaluation; no journals
were fabricated and no gate disabled. Default server evidence readers remain
unconfigured.

The selected advisory profile denies startup and order-capable side effects
across development, paper and live environments. The general default remains
unchanged; local loaded settings are still paper_trading/general with DeFi false.
The updated research Compose file was not deployed. It retains loopback access,
separate research storage, no credential mount or trading network, empty advisory
Kafka configuration, and container restrictions.

No order, cancellation, liquidation, copying, purchase, paid data, broker or
funded-account action occurred. `.env`, credentials, local research-store state,
unrelated source, existing artifacts, and the failed deployment soak were
preserved. Isolated paper infrastructure is used only for quality tests; no
agents or soak process were started. The broader readiness Goal remains unfinished.

## Readiness matrix

VERIFIED means the entire stated criterion is evidenced for its stated scope.
PARTIAL means tested foundations exist with material gaps. MISSING means no
qualifying evidence was found in inspected sources. BLOCKED means required
external/account evidence or a scoped workflow decision prevents completion.
Engineering tests do not establish readiness or a trading success percentage.

| Requirement | Status | Current evidence and gap, reviewed 2026-10-07 | Acceptance criterion |
| --- | --- | --- | --- |
| Advisory isolation and runtime reliability | PARTIAL | `core/config.py`, `api/advisor.py`, research Compose, capability/architecture tests cover TCP25/TCP50 across environments. No deployed selected advisory runtime or complete forward operational evidence. Existing soak remains failed at 564 cycles. | Verified advisory launch and bounded reproducibility; reconcile failed financial soak separately before any newly authorized soak |
| Correct account policy, accounting and exposure | BLOCKED | Public target/risk inputs and printed progression rows verified; TCP50 selection and threshold tests pass in the earlier increment. Continuous progression semantics and assigned accounting/floor/margin/calendar/fees missing; no default-store journals/sessions in the earlier inspected baseline. Single-account support unresolved. | Purchase-date/assigned rules, synchronized accounting, verified bands/exposure, and a scoped single-account workflow without bypass |
| Qualified futures data, provenance and realistic costs | MISSING | Default research store has zero imports; saved futures examples are synthetic. Guarded provider/health/replay modules are foundations. | Licensed qualified futures history, session/roll/quality/extrema/bid-ask evidence, source/code identities and realistic assigned costs |
| Strategy performance on untouched OOS data | MISSING | No qualified untouched strategy results found; synthetic edge statistics are mechanics only. | Freeze strategy/cost/config before OOS, adequate trade/regime sample, cost/drawdown sensitivities and justified uncertainty |
| Chronological walk-forward and holdout protection | PARTIAL | Existing chronological/disjoint/development-only window and causal-cut tests pass; synthetic walk verifies against current source. Real holdout access/selection provenance absent. | Current-code qualified chronological artifacts plus precommit/access/selection evidence protecting final holdout |
| Intraday selected-firm evaluation simulation | PARTIAL | Shared fills/marks/orders/EOD/fees mechanics and legacy PASS/FAIL/CENSORED exact replay pass. `rule_exact_verified=false`; complete selected rules/data and netting/mark semantics unverified. | Qualified complete intraday tape, exact rules/costs/exposure/deadlines/synchronization, valid netting/common marks and explicit censoring |
| Pass/fail estimates, uncertainty and failure reasons | MISSING | No qualified evaluation distribution or defined horizon; bootstrap mean intervals are not passing probabilities. | Defined horizon/stopping/sampling assumptions, sufficient qualified paths, separate PASS/FAIL/CENSORED, calibrated uncertainty and failure attribution |
| Complete forward paper evaluations and operational reproducibility | MISSING | No forward evaluations in default journal; paper quality tests do not certify the failed soak. | Complete reproducible forward paper attempts with all observations/decisions/reconciliation and preserved failures |

Default SQLite was inspected using `mode=ro` and `PRAGMA query_only=ON`:
evaluations 0, sessions 0, imports 0, reports 3, intelligence 0.
Evidence scope is the inspected local files and store; inaccessible private/provider
evidence is not assumed nonexistent elsewhere.

**Passing probability: UNKNOWN.** Qualified data, a defined evaluation horizon,
fully validated selected rules/account inputs and uncertainty evidence are
insufficient. No readiness completion percentage is reported. Coverage and test
counts describe engineering only.

## Prior 21-file increment verification and provenance (historical)

Earlier focused suite: **959 passed, zero failed/skipped, 36 warnings, 29.69 seconds**.
The thirteen selected suites cover capabilities, policy/API, journal/events,
futures verification/research/edge/walk, architecture, account profiles/account
observations and deterministic risk. This is one current run, not an addition
of earlier overlapping baseline counts.

Earlier required full suite: **2,330 passed, three skipped, zero failures/errors,
562 warnings, 155.48 seconds**. Coverage: **83.38693888966579%**, above the unchanged
70% engineering gate. Focused and full suites overlap and are not summed.
The three skips are optional real-broker Kafka authentication and two PostgreSQL
SELECT-only writer-lease checks; their prerequisites remain unvalidated here.
The first wrapper attempt failed before pytest because the isolated database was
stopped. Existing PostgreSQL/Redis/Kafka test services were temporarily started
for the successful run and restored to their original stopped state afterward.

**Incidental generated-output exception:** despite the command-line coverage
redirection, the configured HTML reporter also refreshed the existing ignored
`htmlcov/` directory (136 files). Its before-bytes were not hashed, so preservation
of that prior generated report cannot be claimed. It was retained rather than
deleted or reconstructed. The root `.coverage` file has a modification time predating this increment;
its before-bytes were not included in the manifest.
This exception does not change source, strategy or saved research evidence, but
means this task cannot claim that only the approved 21 paths changed anywhere
in the worktree. It is explicitly recorded for user review.

Repository Ruff, Black check (235 files), isort check, architecture (six packages)
and strict MyPy (116 sources) pass. Initial new-test fixture chronology/equity
errors were corrected without changing the EOD engine. A sandboxed API/thread
diagnostic timed out and was interrupted; the authoritative focused run used
normal thread support. These diagnostics remain distinct from final results.

Changing `policy.py` invalidates saved evaluation envelopes under existing strict
whole-file hashes. The three historical parents in
`artifacts/tcp25-goal/evaluation-events/` are preserved. New copies are regenerated
from each exact captured EvaluationTape with `simulate_evaluation`, independently
reopened with `verify_evaluation_simulation`, and compared as complete JSON.
Tape/configuration, events, costs, steps, outcomes and serialized fields are
identical; only `shared_source_sha256` differs. Old envelopes are rejected.

The regenerated examples are **SYNTHETIC MECHANICS ONLY — LEGACY TCP25**:
one conditional PASS, one daily-boundary FAIL, and one CENSORED case.
They are separate illustrative outcomes, not sampled attempts or a success rate.
The seeds/sample sizes/costs inside prior futures evidence remain unchanged.

Unchanged approved futures run, edge and walk artifacts each passed fresh public
verification: path replay, source checks and exact full serialized comparison.
Verification reuse remains internal to the current request; separate requests
repeat all checks. No persistent verification cache or holdout change was added.

The earlier readiness document was archived byte-for-byte as
[readiness-before.md](../../artifacts/earn2trade-50k-readiness/tcp50-policy/readiness-before.md)
before updating this maintained document. Earlier receipts are immutable
historical snapshots: their former document hash resolves to that archive.
All 543 older artifacts and earlier receipt/futures files are preserved.
The hypothetical opposing-position/mixed-age mark probe remains historical and
unsupported; no valid authenticated broker-statement bug or rule-exact simulator
is certified. Its remediation requires a separate scope.

Git metadata is unavailable; whole-file identities are used without inventing
history. The artifact directory remains ignored by the existing Git rules.
No publication or ignore-rule change was made.

## Prior 21-file increment reproduction and files (historical)

Run from the repository root with the existing Python 3.12 environment. Logs
record actual commands. Focused tests use `--no-cov -p no:cacheprovider` with
temporary storage. Full tests use `scripts.test_with_services`, the dedicated
quality database/local paper stack and the configured 70% gate; coverage files,
hypothesis storage and basetemp are redirected to /tmp before copying the listed
outputs; the disclosed HTML reporter exception still occurred. No credentials
appear in these commands or artifacts.

To reproduce each legacy regeneration:

```python
import json
from pathlib import Path
from backtesting.evaluation import (
    EvaluationSimulation, EvaluationTape,
    simulate_evaluation, verify_evaluation_simulation,
)
for label in ("conditional-pass", "daily-fail", "censored"):
    parent = Path("artifacts/tcp25-goal/evaluation-events") / f"synthetic-{label}.json"
    original = json.loads(parent.read_text())
    new = simulate_evaluation(EvaluationTape.model_validate(original["tape"]))
    assert new.model_dump(mode="json")["tape"] == original["tape"]
    assert new.model_dump(mode="json")["steps"] == original["steps"]
    assert verify_evaluation_simulation(new).model_dump(mode="json") == new.model_dump(mode="json")
    # Preserve parent. Save only into the separately approved new mechanics paths.
```

The 21 approved source/document/evidence paths are:

1. `src/core/config.py`
2. `src/core/advisory/policy.py`
3. `src/api/advisor.py`
4. `docker-compose.advisor.yml`
5. `tests/unit/test_advisory_capabilities.py`
6. `tests/unit/test_evaluation_policy.py`
7. `tests/unit/test_advisory_api.py`
8. `docs/maintenance/earn2trade-50k-readiness.md`
9. `artifacts/earn2trade-50k-readiness/tcp50-policy/readiness-before.md`
10. `artifacts/earn2trade-50k-readiness/tcp50-policy/official-rules.json`
11. `artifacts/earn2trade-50k-readiness/tcp50-policy/source-manifest.json`
12. `artifacts/earn2trade-50k-readiness/tcp50-policy/verification.json`
13. `artifacts/earn2trade-50k-readiness/tcp50-policy/focused-tests.xml`
14. `artifacts/earn2trade-50k-readiness/tcp50-policy/focused-tests.log`
15. `artifacts/earn2trade-50k-readiness/tcp50-policy/checks.log`
16. `artifacts/earn2trade-50k-readiness/tcp50-policy/full-tests.xml`
17. `artifacts/earn2trade-50k-readiness/tcp50-policy/full-tests.log`
18. `artifacts/earn2trade-50k-readiness/tcp50-policy/coverage.json`
19. `artifacts/earn2trade-50k-readiness/tcp50-policy/mechanics/legacy-tcp25-conditional-pass.json`
20. `artifacts/earn2trade-50k-readiness/tcp50-policy/mechanics/legacy-tcp25-daily-fail.json`
21. `artifacts/earn2trade-50k-readiness/tcp50-policy/mechanics/legacy-tcp25-censored.json`

The [verification receipt](../../artifacts/earn2trade-50k-readiness/tcp50-policy/verification.json),
[source manifest](../../artifacts/earn2trade-50k-readiness/tcp50-policy/source-manifest.json),
[focused XML](../../artifacts/earn2trade-50k-readiness/tcp50-policy/focused-tests.xml),
[focused log](../../artifacts/earn2trade-50k-readiness/tcp50-policy/focused-tests.log),
[checks log](../../artifacts/earn2trade-50k-readiness/tcp50-policy/checks.log),
[full XML](../../artifacts/earn2trade-50k-readiness/tcp50-policy/full-tests.xml),
[full log](../../artifacts/earn2trade-50k-readiness/tcp50-policy/full-tests.log) and
[coverage evidence](../../artifacts/earn2trade-50k-readiness/tcp50-policy/coverage.json)
provide historical source/command/result identities and explicit limits. These
earlier evaluation envelopes now fail strict current-source checks after the
gate correction; retain them unchanged and use the new independently replayed
examples above. The public-rule receipt remains a dated prospective source,
not authenticated purchase evidence or a fresh 2026-10-08 rule retrieval.

## Review checkpoint and priorities

Stop for user review after this bounded increment. No expansion, deployment,
strategy tuning, holdout access or execution work is authorized by its completion.

Next scoped priorities: verify exact TCP50 progression limits/boundaries and
exposure semantics; resolve the single-account workflow; qualify licensed futures
data and realistic costs; repair or reject unsupported simulator tapes through
separate review; freeze and validate untouched OOS/walk/holdout; then complete
forward paper attempts before estimating pass/fail distributions and uncertainty.
At purchase, recheck public rules and reconcile authenticated assigned terms.
Do not restart or certify the failed soak without reconciliation and separate
authorization.
