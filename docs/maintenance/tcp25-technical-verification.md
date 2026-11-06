# TCP25 Phase 3 — technical verification gaps

**GO for the bounded TCP25 advisory UI/accounting verification. Full trading
pipeline sign-off remains NO-GO:** one test requires prohibited execution agents
and was not run. This phase changes no application source, rule, configuration,
dependency, eligibility or execution permission.

## Browser receipt

The managed browser inventory still reports `apps=[]`, `browsers=[]`. Installed
Chrome 155 was available, while Playwright/Puppeteer were absent from the existing
project environments. The earlier managed-browser failure therefore did not prove
that local headless testing was impossible.

The [browser receipt](../../artifacts/earn2trade-tcp25-readiness/technical-verification-v1/browser-e2e-receipt.json)
records **19 passing scenarios** in actual headless Chrome using native CDP and
Node WebSocket, with no new dependencies. Each run uses a fresh temporary Chrome
profile and a loopback-only fixture host, with external DNS/background networking
disabled and a restrictive page CSP. No existing browser profile is accessed.

The real `ManualAssistant`, `EvaluationPanel` and `UserPolicyPanel` components
render and handle browser events. Complete synthetic Python TCP25 outputs supply
the fixture API. Checked states include positive personal headroom/sizing,
recorded breach, exactly ten/over-ten Micros, Mini, mixed and unsupported
exposure, unknown positions/orders, working orders, expired observations, window
close, zero monetary budget, stale responses, deliberately malformed permission
flags, request failure, legacy read-only records and sub-millisecond rejection.
Additional assertions cover disabled initial controls, loaded legacy state,
expiry while results are visible and dirty edits hiding both results/disabling
new checks. Full-page screenshots and five focused capacity images are retained.

This is component E2E on an isolated fixture page, **not** a production-auth,
packaged routing, visual-regression or external-provider certification. The
fixture API does not persist records or contact a provider. Production backend
authentication and retirement behavior remain covered by the full Python suite.
Screenshots for capped/working-order states were visually inspected. Chrome,
the fixture host and all task-specific browser processes were stopped.

## Infrastructure receipt and coverage

The [infrastructure receipt](../../artifacts/earn2trade-tcp25-readiness/technical-verification-v1/infrastructure-receipt.json)
maps every one of the previous 53 skipped tests to its current result:

| Dependency | Previously skipped | Actual current result |
| --- | ---: | --- |
| PostgreSQL accounting/funding/recovery |45 |45 passed |
| PostgreSQL AI budget |1 |1 passed; no model calls |
| PostgreSQL writer leases |2 |2 passed |
| Redis state/accounting |3 |3 passed |
| Kafka SASL messaging authentication |1 |1 passed |
| Paper runtime requiring execution agents |1 |**Still skipped by policy** |

The existing Docker daemon and cached PostgreSQL 16, Redis 7 and Kafka 4.3.1 images
were reused. Disposable containers use unique names, `--rm`, `--restart=no`,
temporary storage and loopback-only host ports. PostgreSQL/Redis use read-only
roots and tmpfs data. A private bridge with masquerading disabled supports the
host tests. The runner forbids non-loopback client socket connections. Local
Kafka is a messaging broker, not a financial broker; no exchange connection or
execution agent was started. No runtime volumes, books, endpoints or services
were reused. Temporary database passwords stay in process memory/environment,
never command arguments or evidence.

The initial `--internal` network attempt did not publish a usable host port;
its resources were removed before retrying. Browser-harness language, stale-CDP
port and precision-fixture issues were corrected without product changes.
Diagnostics distinguish those harness failures from product defects.

Full collection: **3047 passed, 1 skipped, 0 failed, 560 warnings in 157.02s**.
The unchanged aggregate statement/branch gate passed at **85.01838235% >= 70%**.
Statement coverage is 11728/13458 (**87.14519%**); branch coverage 3072/3950
(**77.77215%**). Sources remain `agents`, `core`, `connectors`, with branch=True
and unchanged omissions. Compared with Phase 2B, 52 actual infrastructure passes
replace 52 skips; the remaining skip is never counted as passed. This is not
complete execution of the agent-enabled CI workflow.

The complete frontend regression passed **243 tests across 20 files**. Ruff,
Black/isort, strict MyPy on 140 sources, architecture, TypeScript and production
build passed; Vite's existing large-chunk advisory remains. Report/cache/build
outputs were directed to `/tmp`, preserving old coverage reports.

## Warning classification and precision risk

The [warning classification](../../artifacts/earn2trade-tcp25-readiness/technical-verification-v1/warning-classification.json)
and raw warning records account for all 560 warnings without suppression:

- **556 UTC datetime deprecations:** 555 `utcnow`, 1 `utcfromtimestamp`.
  Future Python compatibility needs a separately bounded migration with
  naive/aware timestamp and serialized-contract checks; bulk replacement is unsafe.
- **2 Structlog formatting warnings:** expected lifecycle-failure logging;
  cosmetic exception-formatting noise, no financial defect demonstrated.
- **2 Pandas FutureWarnings** at `technical_analyst.py:105`: concatenating an
  empty/all-NA frame can change future dtype behavior. This is actionable
  compatibility maintenance before a dependency upgrade. Current normalization,
  deduplication and numerical tests passed. No unrelated quant code was changed.

No infrastructure failure/resource-leak warning category was present in this run.
Warnings are not evidence of trading edge or authorization to execute.

The [precision assessment](../../artifacts/earn2trade-tcp25-readiness/technical-verification-v1/precision-assessment.json)
executed **12000 deterministic checks**, including 8000 at/after expiry: **zero
expired acceptances**. Four timezone offsets and all 1000 fractional-millisecond
positions in the tested millisecond were exercised. JavaScript floors timestamp
precision to milliseconds; the exclusive comparison rejects early by less than
one millisecond rather than extending the deadline. Chrome also rejected an
actual backend envelope with one microsecond left. Conservative rejection is
retained; no production precision change was justified.

## Preservation, reproduction and remaining findings

Only this new document and the new
[evidence directory](../../artifacts/earn2trade-tcp25-readiness/technical-verification-v1/)
were added. The harness directory retains the exact browser, fixture,
infrastructure, precision, frontend and static-check scripts. Run them from the
repository root with installed project dependencies; infrastructure/browser
runs require permission to launch temporary local processes/containers. No
system software was installed and no persistent service was started.

The [preservation manifest](../../artifacts/earn2trade-tcp25-readiness/technical-verification-v1/source-manifest.json)
compares every monitored pre-existing file against the pre-run inventory.
Historical TCP25/TCP50/Phase1A/worksheet-v2/Phase2B evidence and unrelated UI
changes remain byte-identical. Credentials, private mutable stores, dependency
and cache trees, symlinks and `.git` are excluded; no blanket private-store claim
is made. Docker cleanup was independently checked: no labelled QA containers or
networks remain, and no task-specific Chrome process remains.

- **P0:** none identified in this bounded audit.
- **P1:** none identified in the TCP25 boundary/UI/accounting checks.
- **P2:** agent-based `test_paper_runtime` remains policy-skipped; UTC/Pandas
  future-compatibility maintenance remains. Packaged application/auth/browser
  integration was not claimed by the synthetic component E2E.

Firm progression/account/closing questions, qualified market/cost data,
strategy/OOS evidence and forward-run reconciliation remain separate inherited
work. Personal cap remains one Mini OR ten aggregate Micros, never both; full
Mini support stays deferred. All real results retain
`firm_eligibility=BLOCKED`, `qualified_contracts=0`,
`passing_probability=UNKNOWN`, `execution_permissions=false`,
`trade_permitted=false` and `execution_enabled=false`. Deliberately malformed
negative fixtures are explicitly labelled and rejected. Stop after reporting.
