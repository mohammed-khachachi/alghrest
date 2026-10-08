# TCP50 policy implementation proposal

Prepared: 2026-10-07 UTC. Status: **PROPOSED — awaiting scope review**.

The overall objective remains evidence-backed readiness for an Earn2Trade TCP50
evaluation, with an honest assessment and advisory-only, human-controlled use.
The user confirmed **TCP50, $50,000, not purchased yet**. This proposal covers the
smallest policy and advisory-selection increment; it does not complete readiness,
establish trading edge, estimate passing probability, or guarantee passing.

The existing Codex Goal is active. Its stored objective currently describes scope
preparation. The available Goal tools can change status but cannot edit objective
text. The user's correction restores the broader readiness objective for ongoing
work; the Goal must not be marked complete when this proposal or increment ends.

This document supersedes the unconfirmed target and paused-Goal statements in the
[earlier readiness snapshot](earn2trade-50k-readiness.md). That snapshot and its
verification receipts are preserved for review. No policy implementation, runtime
configuration change, account creation, or purchase has been performed here.

## Prospective official rules and unresolved evidence

Public sources were retrieved on 2026-10-07. Retrieval dates, publication/update
dates, and effective purchase-date rules are distinct. No authenticated account
rule sheet, purchase receipt, platform configuration, or assigned floor exists in
the inspected evidence. **Recheck applicable rules when the evaluation is
purchased**, and retain the actual purchase date and assigned terms separately.

| Policy input | Official evidence | Implementation treatment |
| --- | --- | --- |
| Program and evaluation balance | TCP50, $50,000, explicitly identified by official TCP comparison/help | Prospective evaluation policy; never substitute TCP25 or a funded growth stage |
| EOD drawdown distance | $2,000 in the explicit TCP50 comparison column | Dated public evidence; confirm at implementation review and again at purchase |
| Daily loss limit | $1,100 in the same TCP50 column | Same review requirement; equality is a failure boundary |
| Standard-contract ceiling | Up to six in the same TCP50 column | An absolute ceiling, never an initial or universal allowance |
| Evaluation profit target | **UNKNOWN — NEEDS VALIDATION** | Indexed official TCP50 purchase evidence suggests $3,000, but fresh extraction defaults to TCP25; do not encode that value as verified |
| Exact progression bands and their boundaries | **UNKNOWN — NEEDS VALIDATION** | Do not infer, copy TCP25 bands, or install a default schedule |
| Fixed minimum trading days | Removed for purchases on/after 2026-07-06 | Prospective `minimum_trading_days=0`; no invented replacement minimum |
| Consistency | Each day's contribution must remain strictly below 30% of total PnL | Preserve existing strict arithmetic; excess concentration delays qualification |
| Progression breach | Immediate evaluation failure under the updated terms | Preserve fail-closed evaluation behavior; no automatic cancellation or liquidation |

The [official account comparison](https://www.earn2trade.com/blog/introducing-tcp10/)
was published 2024-07-01 and updated 2025-10-10. It explicitly distinguishes TCP50
evaluation risk amounts. The [account-size help article](https://help.earn2trade.com/en/articles/6863807-what-is-the-difference-between-the-tcp25-tcp50-and-tcp100)
also identifies TCP50's evaluation capital. These dates do not establish a new
effective date for those numerical limits.

The [July 2026 announcement](https://www.earn2trade.com/blog/earn2trade-evaluation-rules-profit-split-update/)
was published 2026-07-06, updated 2026-07-10, and applies to purchases on/after
2026-07-06. It removes the fixed ten-day requirement and makes progression-limit
breaches failures. The [evaluation overview](https://help.earn2trade.com/en/articles/5941958-what-are-the-evaluation-rules)
dated 2026-07-06 corroborates the updated evaluation rules. The four profitable
days described there follow from consistency, rather than a new fixed minimum.
[Consistency help](https://help.earn2trade.com/en/articles/3849975-what-is-the-maintain-consistency-rule)
dated 2026-05-07 specifies the strict threshold and includes daily PnL below or
above starting balance.

Fresh extraction of the [product page](https://www.earn2trade.com/trader-career-path)
and [TCP50 purchase URL](https://www.earn2trade.com/purchase?plan=TCP50) shows the
default TCP25 card. An [indexed official Arabic TCP50 purchase URL](https://www.earn2trade.com/ar/non-us/purchase?discount=5STRADING&plan=TCP50)
shows a $3,000 target, but opening that page produces TCP25. This is conflicting
corroboration, not a confirmed selected TCP50 card. No discount or purchase price
is adopted. GAU50 figures and the $50,000 LIVE growth stage are not substituted.
No configured browser was available for selecting the card; a failed shell
retrieval and aborted escalation were not bypassed.

Additional semantics remain evidence requirements:

- [Daily loss](https://help.earn2trade.com/en/articles/3395926-how-is-my-daily-loss-calculated): session-start accounting includes realized and unrealized PnL and commissions; use DST-aware America/Chicago sessions, with 17:00 CT rollover.
- [EOD floor](https://help.earn2trade.com/en/articles/5372687-how-does-end-of-day-drawdown-work): rises with higher closing balances, never retreats, caps at starting balance, and constrains open equity intraday. A calculated $48,000 initial floor is not an assigned-account receipt; dashboard/platform floor synchronization remains required.
- [Progression](https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path): total open exposure and real-time balance matter. The public ten-to-one exceptions are MES, MNQ, MYM, M2K, MGC, MCL, M6B, M6E, and MHG. Exact bands, mixed-root rounding, netting, and working-order reservation semantics remain unresolved.
- [Approved times](https://help.earn2trade.com/en/articles/3224526-are-there-any-restrictions-on-when-i-can-trade-in-my-evaluation-account): positions and working orders must be flat during applicable restricted periods. Calendar, instrument-specific restrictions, holidays, and DST require explicit evidence; this does not authorize order actions.
- [Commissions](https://help.earn2trade.com/en/articles/2425493-what-is-the-commission-on-earn2trade-evaluations): assigned platform/instrument fees remain missing before purchase. Generic micro ranges, zero costs, or synthetic assumptions cannot replace the user's fee schedule or realistic spread/slippage evidence.

## Gates and smallest useful behavior

**Before implementing a TCP50 factory:** obtain and review a fresh official
selected TCP50 evaluation profit target, and reconfirm its public risk limits.
Scope approval alone does not resolve this evidence gap. If the target remains
unresolved, keep the increment pending rather than install a guessed constant,
incomplete policy disguised as verified, or TCP25 fallback.

Exact progression bands are a gate for any positive TCP50 contract allowance and
for claiming rule-exact evaluation simulation. They need not be fabricated to
add a policy whose existing missing-evidence behavior remains UNKNOWN/BLOCKED.
Even after public bands are retrieved, authenticated account confirmation,
current margin, calendar, costs, accounting, and floor synchronization remain
separate prerequisites. No default six-contract allowance is permitted.

Once the factory evidence and scope are approved, reuse `EODRules`/`EODPolicy`:
add `tcp50_rules()` and `TCP50Policy`, select them under a restrictive
`earn2trade_tcp50` profile, and use that profile in the isolated research Compose
configuration. Preserve the general default and existing TCP25 support. Require
an explicitly matching $50,000 journal; never rescale an existing journal or
automatically create an account or session. The unrelated general-system capital
setting is not the advisory journal balance and will not be changed.

Existing account-role and approved-strategy gates stay enabled. The three-journal
A/B/C `AccountPlan` requirement does not currently model a single purchased
TCP50 evaluation; resolving that requires a later scoped design, with no fake
journals or bypass. Policy wiring alone therefore cannot establish usable,
qualified trading advice.

## Exact proposed file scope after approval

Seven source/configuration/test files would change:

| File | Bounded change |
| --- | --- |
| `src/core/config.py` | Accept `earn2trade_tcp50` in the existing settings literal; retain execution denial for every non-general profile and existing defaults |
| `src/core/advisory/policy.py` | Add reviewed prospective TCP50 rules and a thin `TCP50Policy` wrapper over the existing engine; preserve TCP25 factory/class and all existing models, signatures, and numerical behavior |
| `src/api/advisor.py` | Select TCP50 or legacy TCP25 by explicit profile, with the existing freshness/review controls and required service gates; no new endpoint, evidence reader, account mutation, or order capability |
| `docker-compose.advisor.yml` | Set isolated assistant profile to `earn2trade_tcp50`; retain loopback-only access, separate storage, no credentials/trading network, disabled advisory Kafka, and container restrictions; do not launch it |
| `tests/unit/test_advisory_capabilities.py` | Exercise both restrictive profiles across development/paper/live and verify side-effect denial and unchanged Compose isolation |
| `tests/unit/test_evaluation_policy.py` | Add TCP50 rules, mismatch, missing/stale evidence, strict loss/floor/consistency boundary and allowance cases using clearly synthetic fixtures; retain legacy cases |
| `tests/unit/test_advisory_api.py` | Cover TCP50 startup selection, existing TCP25 behavior, no automatic journal creation, missing-evidence blocking, no order endpoints, and unchanged serialized responses |

Fourteen documentation/evidence files complete the bounded increment:

1. `docs/maintenance/earn2trade-50k-readiness.md` — maintain the confirmed prospective target, separate rule evidence from account evidence, update the matrix and increment results without promoting trading readiness.
2. `artifacts/earn2trade-50k-readiness/tcp50-policy/readiness-before.md` — byte-identical archive of the earlier readiness document before its update.
3. `artifacts/earn2trade-50k-readiness/tcp50-policy/official-rules.json` — actual retrieval/publication/effective dates, primary links, target confirmation, unresolved bands, prospective applicability, and purchase recheck requirement.
4. `artifacts/earn2trade-50k-readiness/tcp50-policy/source-manifest.json` — before/after whole-file source identities, immutable parent/output hashes, preservation assertions, configuration identity; no secrets or invented Git identity.
5. `artifacts/earn2trade-50k-readiness/tcp50-policy/verification.json` — exact replay and preservation results, separate PASS/FAIL/CENSORED outcomes, failures/skips, limits, and UNKNOWN passing probability.
6. `artifacts/earn2trade-50k-readiness/tcp50-policy/focused-tests.xml` — fresh focused JUnit results.
7. `artifacts/earn2trade-50k-readiness/tcp50-policy/focused-tests.log` — focused commands and output.
8. `artifacts/earn2trade-50k-readiness/tcp50-policy/checks.log` — lint, formatting checks, strict typing, architecture, link and preservation checks.
9. `artifacts/earn2trade-50k-readiness/tcp50-policy/full-tests.xml` — fresh required repository-suite JUnit results, with skips explicit.
10. `artifacts/earn2trade-50k-readiness/tcp50-policy/full-tests.log` — full-suite command and output using the isolated quality-test stack.
11. `artifacts/earn2trade-50k-readiness/tcp50-policy/coverage.json` — repository engineering coverage evidence only, retaining the configured 70% gate.
12. `artifacts/earn2trade-50k-readiness/tcp50-policy/mechanics/legacy-tcp25-conditional-pass.json` — regenerated legacy synthetic PASS mechanics using the unchanged parent tape.
13. `artifacts/earn2trade-50k-readiness/tcp50-policy/mechanics/legacy-tcp25-daily-fail.json` — regenerated legacy synthetic FAIL mechanics using the unchanged parent tape.
14. `artifacts/earn2trade-50k-readiness/tcp50-policy/mechanics/legacy-tcp25-censored.json` — regenerated legacy synthetic CENSORED mechanics using the unchanged parent tape.

Total proposed implementation outputs: **21 files**, including seven functional
or test changes. This proposal itself is the only new repository file in the
current planning turn. No broader directory scope is approved. If meaningful
verification exposes another required source change, report it and stop for a
scope decision before expanding.

## Evidence regeneration and preservation

`backtesting/evaluation.py::_shared_sources()` hashes
`core/advisory/policy.py`, so adding TCP50 invalidates the current saved legacy
evaluation examples. Keep the originals under
`artifacts/tcp25-goal/evaluation-events/` byte-for-byte. Rebuild from their exact
captured `EvaluationTape` using `simulate_evaluation`, then verify with
`verify_evaluation_simulation` and exact complete JSON comparison. Do not repair
old hash fields, rewrite provenance, reclassify origin, or authenticate old code.
Their tape/configuration, events, costs, steps, and outcomes must be unchanged;
only current implementation identities may differ in the new envelopes.

All regenerated examples must remain **SYNTHETIC MECHANICS ONLY, LEGACY TCP25**.
They are regression evidence for shared arithmetic, not selected TCP50 strategy
or evaluation evidence. Preserve PASS, FAIL, and CENSORED separately. Do not
derive a success rate or passing probability from these hand-built cases.

The three approved futures artifacts hash different shared sources; neither
`policy.py` nor `config.py` is in their source map. Reopen them and repeat public
path replay, source checks, and exact comparisons after the increment; do not
regenerate unchanged artifacts merely to refresh timestamps. Verification remains
request-scoped, and separate requests must repeat verification. No persistent
verification cache is introduced. The old probe and earlier receipts remain
historical snapshots, with their original source identities and limits visible.

## Verification and acceptance criteria

After approval and rule confirmation:

1. Run fresh focused capability, policy, API, journal/evaluation, architecture,
   and futures-evidence tests. TCP25 imports/signatures and serialized schemas
   must remain compatible. Test equality at the $1,100 loss and EOD floor,
   unrealized PnL/fees, floor monotonicity/cap, strict consistency, and Chicago
   session/DST behavior through existing arithmetic without changing it.
2. Assert missing/old/foreign policy, ladder, margin, calendar, floor, account,
   strategy, and research evidence cannot produce qualified advice or a positive
   allowance. Fixture schedules are explicitly hypothetical, never adopted as
   official bands. Confirm both restrictive profiles deny agent startup,
   order-producing publication, create/cancel/recovery paths before side effects,
   even with `ENVIRONMENT=live` in tests.
3. Run repository Ruff, Black `--check`, isort `--check-only`, strict MyPy and
   `scripts/check_architecture.py`. Run the required full suite through
   `scripts.test_with_services` against only its isolated local paper/quality
   stack, retaining the coverage gate. Keep caches/logs/test storage in `/tmp`
   until copying the listed evidence outputs. If services or permissions are
   unavailable, report the gate as BLOCKED rather than certifying it or starting
   the deployment soak. No production services or funded runtime books touched.
4. Regenerate and independently reopen the three legacy simulations. Verify
   old simulation envelopes are rejected against changed source hashes. Repeat
   fresh public verification of all three futures examples. Verify all old
   artifacts and all out-of-scope tracked files are preserved.
5. Record actual commands, dates, configurations, source identities, results,
   skips/failures, and unresolved gaps. Keep checklist completion distinct from
   engineering coverage and trading success. Stop for review at the increment's
   completion; never mark the overall readiness Goal complete on these results.

Review commands must use the repository Python 3.12 environment and existing
test/quality tooling. No new dependency, schema migration, persistent cache,
strategy tuning, holdout access, dashboard redesign, execution implementation,
or mark/netting simulator change is proposed. Existing strict source checks,
holdout isolation, human permissions, and DeFi denial remain intact. `.env`,
credentials, account/broker state, and the failed deployment soak are protected.

## Current planning verification and remaining readiness gaps

On 2026-10-07, current source inspection confirmed that TCP50 is absent from
runtime settings/API policy selection, and that the EOD engine and models already
support the required capital/risk shape without numerical changes. Fresh
whole-file comparisons found **zero mismatches across 272 tracked source/test/doc
files, 543 historical artifacts, and the 11 checksummed approved outputs**. The
earlier verification receipt intentionally excludes its own checksum.

Public saved-evidence APIs were executed again in this request, with source
checks, replay, and exact full serialized equality: run PASS, edge PASS, walk
PASS; legacy evaluation outcomes PASS, FAIL, CENSORED each verified separately.
No unit or full service suite was rerun for this documentation-only proposal.
Previous 950 focused passes and nine later futures-verification passes are
historical, overlapping engineering evidence, not a new combined test count.

Account-policy readiness remains PARTIAL/BLOCKED pending public target validation
and account-specific evidence. Qualified futures data/costs and untouched OOS
performance remain MISSING; walk/holdout and intraday simulation foundations
remain PARTIAL. Complete forward evaluations and operational reproducibility
remain unverified; the failed soak is unchanged. The known hypothetical
opposing-position/mark-semantics probe requires its own later scope and cannot
certify rule-exact simulation. **Passing probability: UNKNOWN** — insufficient
qualified data, horizon, validated full rules/account inputs, and uncertainty
evidence. There is no readiness completion percentage in this proposal.

Next review decision: approve or revise the exact file scope, with the unresolved
TCP50 target review gate preserved. After purchase, reverify the rule version and
assigned account evidence before treating any public planning policy as
account-confirmed. Subsequent single-account, data, simulation, and forward-paper
increments require their own scope and review.
