# ALGHREST TCP25 readiness — Phase 1A, 2026-10-18

The current intended evaluation is **Earn2Trade TCP25, USD25,000**, with a
**USD1,750 target**. The user's separate personal cap is **one Mini OR ten
Micros in aggregate, never both simultaneously**, combined with stricter
verified firm and financial limits. Historical TCP25/TCP50 evidence is retained.

This checkpoint adds only two documents, one financial-boundary test file and
the nine approved records under
[`rules-accounting-v1/`](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/).
Production calculations, personal worksheet, configuration, dependencies and
historical evidence are unchanged. No services, agents, purchases, broker
mutations or forward experiments are authorized by this checkpoint.

**Positive firm qualification: BLOCKED where required evidence is unresolved.**
**Passing probability and trading edge: UNKNOWN.** No engineering result is a
market-performance or evaluation-passing claim. AI proposes, deterministic rules
validate, human decides; both trade/execution permission remain false.

## Current evidence status

| Dimension | Status | Evidence / remaining limitation |
| --- | --- | --- |
| Public TCP25 amounts | VERIFIED public | Current TCP25 Evaluation block independently supports 25,000 / 1,750 / 550 daily loss / 1,500 EOD drawdown / up to three contracts. |
| Accounting conformance | VERIFIED engineering | 690 targeted tests passed, including 27 new cases; zero failures/errors/skips. Synthetic examples, not firm certification. |
| Assigned rule applicability | PARTIAL | Actual purchase version, platform/terms and advisory-use applicability absent. |
| Firm progression/exposure | BLOCKED | Exact current bands, fractional/negative PnL, fee basis, downward changes and order-transition semantics unqualified. |
| Personal cap | DOCUMENTED_NOT_IMPLEMENTED | Exclusive one Mini / ten Micros specification; runtime still has legacy 20-Micro behavior. |
| Personal account worksheet | NOT_ALIGNED | Backend and frontend defaults still use 50,000 / 3,000 / 1,100 / 2,000. No existing account is rewritten. |
| MES/MNQ data/costs | PARTIAL / UNKNOWN | Previously retained samples are distinct from synthetic tests; qualified coverage/corrections/quotes and assigned costs remain missing. No raw market data inspected or acquired here. |
| Frozen intraday strategy / OOS edge | MISSING | Existing registered strategy is daily; no new strategy selection, tuning, holdout access or market-performance run. |
| Rule-exact evaluation outcomes | NOT_ESTABLISHED | Existing synthetic PASS/FAIL/CENSORED mechanics are preserved. No qualified attempt counts or future probability produced. |
| Forward reconciliation | BLOCKED | Prior synthetic SOL deployment soak failed; writer-lease correction is not reconciliation of its terminal state. No restart or certification. |

See the [rules register](earn2trade-tcp25-rules-register.md) for source URLs,
retrieval window, applicability, interpretations, personal controls and remaining
questions. Public text captures are normalized source records, not raw origin
HTML archives or assigned-account contracts. Historical chart bytes were not
freshly acquired. No TCP50 daily-loss, drawdown or progression setting supplies a
TCP25 rule.

## Validation and preservation

The new [test file](../../tests/unit/test_tcp25_rule_boundaries.py) adds 27 cases
for TCP25 target/consistency, combined realized/open/commission losses, drawdown
under unchanged daily rules, and both Chicago DST offsets. Existing tests are
reused without editing. No executable personal-cap checker is introduced.

The [verification receipt](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/verification.json)
is the authoritative result record, including diagnostic failures, final counts,
warnings, exact commands and check scope. The
[manifest](../../artifacts/earn2trade-tcp25-readiness/rules-accounting-v1/source-manifest.json)
records before/after identities, the exact twelve new paths and exclusions.
Existing public sources/artifacts and coverage outputs are compared to the
pre-edit baseline. Private mutable stores, credentials, dependency trees and
symlinks are excluded; no blanket private-database preservation claim is made.

Tests use `--no-cov` with configured addopts overridden and caches/temporary
outputs in `/tmp`. No full-suite or 70% coverage-gate result is claimed.
Service-backed integration validation requires separate authorization. Formatting
and lint apply to the new test; architecture and evidence/link checks have their
scope recorded in the receipt. No unrelated dashboard or OpenTerminal changes
are attributed to this increment.

Final targeted run: **690 passed in 30.80s**, with zero failures/errors/skips and
no warnings reported. The 27 new cases and the separate 116-case risk diagnostic
are subsets of this result, not additional passes. Ruff, Black check, isort check
and architecture checks passed. The initial sandbox run emitted four failure
markers and stalled; it was interrupted (exit 130) before a failure traceback or
final JUnit report. Its cause is not established by that partial log. A bounded
risk diagnostic and the complete selected suite passed outside the sandbox,
without starting services. Both the incomplete and final evidence are retained;
no reproducible financial defect was found by the completed targeted suite.

## Smallest next implementation proposal — separate approval required

First align the **existing MES/MNQ worksheet branch** to TCP25, with the Mini
branch remaining unsupported until its exact symbol universe is agreed. This
gives useful ten-Micro behavior without silently adding ES or widening the
instrument catalog. A later Mini-capable increment must enforce the same
exclusive policy; the documented one-Mini option is not discarded.

Proposed production scope for that next increment:

- `src/core/advisory/user_policy.py`: versioned TCP25 personal-cap assessment;
  ten aggregate Micros; any Mini/mixed/unknown unsupported exposure blocks new
  Micro capacity. Preserve old schema meaning and replay behavior.
- `src/core/advisory/user_risk.py`: TCP25 worksheet terms, ten-Micro ceiling,
  explicit rule identity and independent firm-qualification status; retain
  costs, remaining-budget limits, freshness and fail-closed behavior.
- `src/api/advisor.py`: explicit compatible exposure of the new personal version
  if its public adapter requires a schema change; preserve old stored records.
- `dashboard/src/lib/userPolicy.ts`, `dashboard/src/lib/userRisk.ts`: matching
  versioned validators; distinguish historical 20-Micro results from current
  ten-Micro results instead of relabelling old payloads.
- `dashboard/src/components/advisory/EvaluationPanel.tsx` and
  `dashboard/src/components/advisory/UserPolicyPanel.tsx`: TCP25 defaults and
  honest current/historical personal-cap labels. Preserve existing local UI work.

Proposed tests: existing `tests/unit/test_user_policy.py`,
`tests/unit/test_user_advisory_risk.py`, `tests/unit/test_advisory_api.py`,
`dashboard/tests/user-policy.test.ts` and `dashboard/tests/user-risk.test.ts`;
targeted accounting/policy/risk/replay and browser validation as appropriate.
Before approval, inspect the current adapter/UI diff and freeze the exact
compatibility approach and artifact allowlist. No account migration, `.env`
change, default firm progression, order path or service startup is implied.

Changes to hashed production sources require new versioned envelopes from exact
captured inputs; historical bytes/hashes must never be patched. Keep firm
qualification blocked where progression, account terms, data or costs are
unknown. If a financial defect appears, preserve its failing evidence and seek
a separately bounded correction; it is not included in this Phase 1A.

Stop for review after the final receipt. No subsequent phase is authorized here.
