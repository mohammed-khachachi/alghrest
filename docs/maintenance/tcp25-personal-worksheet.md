# TCP25 personal worksheet v2

Status: **VERIFIED engineering checkpoint**, **BLOCKED firm eligibility**,
**UNKNOWN trading edge and passing probability**. AI proposes, deterministic
rules validate, human decides. No service, agent, external data/model request,
broker operation, purchase or forward run is part of this increment.

The personal worksheet uses USD 25,000 starting balance, USD 1,750 target,
USD 550 daily loss and USD 1,500 EOD drawdown. These amounts reuse the existing
TCP25 policy; the independently captured official sources and unresolved
interpretations remain in the unchanged
[Phase1A register](earn2trade-tcp25-rules-register.md). This increment does not
re-verify provider terms or certify an assigned account.

The personal exposure policy is **one Mini OR ten Micros in aggregate, never
both simultaneously**. Full Mini support remains deferred. This branch accepts
dated MES/MNQ contracts only and sums open contracts gross across instruments,
directions and expiries, without netting. Known Mini, mixed or unsupported
exposure blocks new Micro capacity. Unknown position/order coverage or any
working order, including a protective order, gives no positive capacity. The
personal cap does not replace firm progression; any qualified firm constraint
must also apply, with the stricter limit controlling. Unresolved firm limits
mean `qualified_contracts=0`, even when personal headroom is positive.

## Calculation and evidence contract

New inputs/outputs use `schema_version=2`,
`policy_id=tcp25-mes-mnq-ten-micro-v1` and a SHA256 `policy_revision` derived
from the explicit terms. Algorithms are `tcp25-personal-rules-v1`,
`tcp25-personal-status-v1`, `tcp25-personal-micro-cap-v1` and
`tcp25-personal-plan-v1`. These are personal rules, not a new firm-policy version.
Account revisions bind the full captured profile and ordered session ledger.
Capacity and plan requests require both expected revisions; conflicts return 409.

The status wrapper reuses the existing validated journal/accounting projection.
Profiles with different amounts, program, evaluation stage, minimum days or
consistency terms are read-only in the personal UI. No stored profile, session,
schema or historical result is migrated or relabelled. A compatible TCP25 record
must be selected/created explicitly; there is no fallback to legacy calculations.
The canonical creation field remains `minimum_trading_days`.

Sizing is a **flat-account personal monetary scenario**. Known open Micro
positions may support a headroom check, but their unmodelled stop risk prevents
new monetary sizing. Entry and stop must differ and align with the instrument
tick. Costs require an explicit reviewed user declaration or synthetic reference;
zero costs are accepted only when explicitly declared, never silently assumed.
No quotes or costs are obtained externally. The risk budget is the nonnegative
minimum of equity times the requested risk percentage (at most 1%), daily loss
remaining minus the explicit safety buffer, and drawdown remaining minus that
buffer. Quantity is floored from budget/loss-per-contract and capped at 10.
Stops are not moved to increase size. Existing journal PnL is already net of
costs; proposed-trade costs are included in loss per contract, not subtracted
again from historical PnL.

Personal entry time remains 07:00 inclusive to 14:00 exclusive UTC; observations
expire after 1800 seconds, at the window close, or at their earlier freshness
deadline. Shared Chicago/DST session accounting is reused. Rules review must be
current, coverage known, reported balances reconciled, the session open/fresh,
and recorded breaches absent. Personal consistency remains strictly below 30%
and the personal minimum-day setting is 0; this does not resolve assigned firm
applicability. There is no automatic closing or account synchronization.

New evidence captures source hashes, exact inputs and generation clock. Its
validator replays the deterministic result and rejects altered output, source,
policy or revision identity. Current-use validation also checks expiry/current
account revision. Saved evidence can remain replayable after its capacity has
expired; it is never renewed by replay. All results retain
`firm_compliance=NOT_ASSESSED`, `firm_eligibility=BLOCKED`,
`passing_probability=UNKNOWN`, `trade_permitted=false`,
`execution_enabled=false` and `qualified_contracts=0`.

## Compatibility and retirement

| Surface | New requests | Historical behavior |
| --- | --- | --- |
| `/assistant-api/tcp25/personal/rules` | Authenticated GET; explicit v2 personal terms | Separate from legacy terms |
| `/assistant-api/tcp25/personal/evaluations/{id}/status` | Authenticated GET; v2 wrapper | Original profile/session values retained; mismatched terms read-only |
| Same prefix, `/capacity` and `/plan` | Authenticated POST, v2 and matching revisions required | No legacy fallback or conversion |
| `/assistant-api/evaluations/{id}/user-policy-check` and `/personal-plan` | Retired POST returns 409 | Legacy GET/rules/status and offline v1 schemas/replay retained |
| `/assistant-api/briefings` | Every legacy creation POST returns 409 | Authenticated history/detail GET and stored briefing replay retained |
| Existing hashed legacy domain sources | Unchanged | Historical source identities remain intact |
| Capability registry | Fresh code-identity envelope retained separately | Old envelopes preserved; stale source identities cannot become current by relabelling |

The retirement guard lives in `src/api/advisor.py`, after existing authentication
and explicit-client checks and before body buffering, request-model parsing,
context collection, workflow construction, external calls, calculations or
writes. Auth 401 and missing-client 403 behavior remain. Canonical, trailing and
multiple trailing slash, query, encoded-name, mounted/root-path, malformed body,
oversized body and all three operating-profile requests are covered. The 409
response is non-cacheable. Neither client-side avoidance nor a test bypass
controls this guard. The personal UI exposes only historical briefings; a new
TCP25 briefing implementation is deferred. Capability definitions remain a
static catalog, not runtime certification that a retired route can create output.

## Exact scope and verification

Seven new application/test/document paths:

- `src/core/advisory/tcp25_personal.py`
- `src/api/routes/tcp25_personal.py`
- `dashboard/src/lib/tcp25Personal.ts`
- `tests/unit/test_tcp25_personal.py`
- `tests/unit/test_tcp25_personal_api.py`
- `dashboard/tests/tcp25-personal.test.ts`
- `docs/maintenance/tcp25-personal-worksheet.md`

Eight existing modified paths:

- `src/api/advisor.py`
- `dashboard/src/components/advisory/EvaluationPanel.tsx`
- `dashboard/src/components/advisory/UserPolicyPanel.tsx`
- `dashboard/src/pages/ManualAssistant.tsx`
- `dashboard/src/i 18n/messages.json`
- `tests/unit/test_advisory_api.py`
- `tests/unit/test_advisory_briefings.py`
- `dashboard/tests/language.test.ts`

The [evidence directory](../../artifacts/earn2trade-tcp25-readiness/personal-worksheet-v2/)
contains exactly 17 named outputs and eight byte-for-byte `before/` archives.
The [receipt](../../artifacts/earn2trade-tcp25-readiness/personal-worksheet-v2/verification.json)
records commands, counts, diagnostic failures, limitations and preservation;
the [manifest](../../artifacts/earn2trade-tcp25-readiness/personal-worksheet-v2/source-manifest.json)
identifies all approved paths/hashes and inventory exclusions. The patch is
relative to the archived working files, preserving existing local UI/i 18n work
rather than attributing it to this phase. Every pre-existing translation entry
remains unchanged; new TCP25 copy and aliases belong only to the dashboard.

Validation covers financial examples and boundaries, revisions, unsafe exposure,
retired-route bypasses, authentication, actual backend JSON/TypeScript contract
compatibility, legacy history and independent replay. Backend: 1138 passing
targeted tests (36 existing datetime deprecation warnings). Frontend: 238 passing
tests across 20 files. Ruff, Black/isort, strict MyPy on 140 sources, six-package
architecture, TypeScript, production build and whitespace checks pass. Initial
failing guard tests, an inconsistent synthetic fixture and a missing new
translation alias were corrected within this scope; their logs are retained.
No reproducible shared financial-calculation defect was found. Initial MyPy
package-discovery ambiguity was resolved with explicit package bases, without
changing repository configuration. Node subprocess sandbox denial required an
authorized local retry. Build output/caches/test stores stay under `/tmp`.

Tests use `--no-cov` and override configured addopts for this targeted run.
No full-suite, integration-stack or 70% coverage-gate result is claimed. No server
or browser was started; interactive rendering and deployed runtime behavior are
**NOT_OBSERVED**. Engineering tests and synthetic examples do not establish an
edge or evaluation-passing probability.

## Remaining blockers and checkpoint

Assigned TCP25 progression, order transitions, threshold interpretations,
account terms and closing calendar remain unresolved. Qualified MES/MNQ
data/costs, a frozen intraday experiment/OOS evaluation, and the failed forward
run's reconciliation are separate unfinished research phases. Original failure
evidence and Phase1A remain unchanged. Full Mini support and TCP25 briefing
generation need separately approved scopes. The next bounded research action
is to resolve assigned-account progression and exposure semantics against the
unchanged rules register before implementing any positive firm qualification.

Stop for review. No new run, service restart or subsequent phase is authorized.
