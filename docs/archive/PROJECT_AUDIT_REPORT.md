# ALGHREST Repository Audit Report

**Audit date:** 2026-09-22  
**Repository path:** `/home/xsabo/Projects/MY project/alghrest-main`  
**Overall assessment:** Not runnable as a complete platform and not ready for paper or live trading

## Executive assessment

The repository contains a substantial trading-platform prototype: 36 agent classes, an event-driven execution design, a FastAPI backend, a React dashboard, risk and backtesting code, Docker infrastructure, monitoring configuration, ML experiments, and an independent HMM research project.

The current snapshot is not a working release. The most serious defect is the absence of `core/data/models.py`. Sixty-three Python files import that module, including the base agent, execution pipeline, API, risk components, backtesting engine, scripts, and tests. Restoring the shared model definitions is the first required action.

The repository also overstates several capabilities. Docker Compose defines 37 services but only 20 agent containers. The ML inference server does not load the included CNN or PPO weights. The dashboard data providers are deterministic mocks. Tier 6 DeFi agents are skeletons. The API and infrastructure lack the controls needed for public or live deployment.

The source is valuable and recoverable. All 164 Python files parse successfully, agent IDs are unique, Compose syntax is valid, the Kafka initializer defines 18 topics, and the dashboard has a coherent component structure. A staged repair can produce a credible development environment, but readiness claims must remain conservative until clean-environment tests pass.

## Scope and method

The audit covered the baseline inventory of 319 files. Source, configuration, tests, scripts, documentation, structured data, generated images, model artifacts, PDFs, and DOCX content were examined with format-appropriate checks.

Generated caches created during syntax checks are not part of the baseline inventory. Dependency folders such as `node_modules` were absent. Model weights, lockfiles, PDFs, PNGs, and the DOCX were inventoried and inspected without attempting to reverse engineer binary model internals.

The audit used:

- Full file inventory, size, extension, and line-count analysis.
- Python AST parsing for all Python files.
- Python byte-compilation.
- Internal-import resolution checks.
- Agent ID, inheritance, lifecycle, kill-switch, and Compose coverage analysis.
- Kafka topic reference analysis.
- JSON and notebook parsing.
- Markdown link validation.
- Bash and plain JavaScript syntax checks.
- Docker Compose configuration rendering.
- Environment-variable drift analysis.
- Duplicate-file hashing.
- PDF text extraction and visual review of all 17 pages.
- DOCX XML inspection, text extraction, metadata review, and visual review of all nine pages.
- Visual review of both generated HMM figures.
- Focused review of Python packaging, CI, Docker, API, dashboard, ML, Kubernetes, Terraform, Nginx, and HMM project files.

The audit did not install project dependencies, download packages, contact external APIs, start infrastructure, place orders, or execute live integrations.

## Inventory

### Baseline file counts

| Category | Count |
|---|---:|
| Total files | 319 |
| Python | 164 |
| Markdown | 59 |
| React TSX | 26 |
| TypeScript | 10 |
| JSON | 12 |
| YAML or YML | 8 |
| JavaScript | 3 |
| HTML | 3 |
| PowerShell | 3 |
| Terraform | 2 |
| Shell | 2 |
| Notebooks | 2 |
| PNG images | 2 |
| PDF documents | 2 |
| DOCX documents | 1 |
| Model weight files | 2 |

### Source volume

| Area | Files reviewed | Approximate text lines |
|---|---:|---:|
| `agents/` | 46 | 9,723 |
| `dashboard/` | 74 | 7,603 |
| Root `tests/` | 18 | 5,953 |
| `project_site/` | 3 | 3,470 |
| `alghrest-test/HMM_Trading/` | 49 | 3,457 |
| `core/` | 20 | 2,580 |
| `scripts/` | 10 | 2,498 |
| `project/` text sources | 11 | 2,169 |
| `infra/` text sources | 10 | 1,433 |
| `api/` | 7 | 1,093 |
| `connectors/` | 8 | 860 |
| `ml/` Python sources | 5 | 394 |
| `mcp/` Python sources | 2 | 344 |
| All reviewed text formats | — | 49,191 |
| Python only | 164 | 26,804 |

There are 146 root test functions and 27 test functions in the maintained HMM subproject.

## Readiness summary

| Target | Status | Reason |
|---|---|---|
| Static source inspection | Pass with findings | Python parses; structured files and scripts validate |
| Lightweight dashboard demo | Plausible but unverified | Designed to use mock providers; dependencies are absent |
| Root unit tests | Blocked | Poetry and pytest absent; shared models package missing |
| Full local agent runtime | Failed readiness | Fatal internal import and dependency drift |
| Docker development stack | Configuration valid, runtime unverified | Partial agent coverage and runtime import failures |
| Paper trading | Not ready | Core runtime broken; mocks and incomplete integrations remain |
| Live trading | Prohibited | No validated baseline, incomplete safety, mock logic, no production hardening |
| HMM research project | Structurally healthy, execution unverified | Separate dependencies are absent |

## Critical findings

### C1 Shared data model package is missing

The repository documentation identifies `core/data/models.py` as the central source of Pydantic models and the `KafkaTopic` enum, but `core/data/` does not exist.

Impact:

- 63 Python files import `core.data.models`.
- `agents/base_agent.py` cannot initialize.
- All seven agent tiers are affected.
- The API, state manager, message bus, risk engine, exchange connector, backtesting engine, scripts, and tests are affected.
- Docker containers built from this snapshot cannot run the application.

Required action:

1. Recover `core/data/__init__.py` and `core/data/models.py` from the authoritative repository or backup.
2. Validate every exported enum, model, constant, field type, and serialization contract against tests and Kafka consumers.
3. Run `tests/unit/test_models.py` first, then the complete unit suite.
4. Do not recreate the file from documentation alone unless no authoritative copy exists.

### C2 Runtime dependency definitions do not match source imports

The project has three dependency paths: Poetry, root `requirements.txt` used by the Dockerfile, and `requirements-lite.txt`.

Confirmed drift:

- `agents/base_agent.py` imports `psutil`, but `pyproject.toml` does not declare it.
- `sentiment_analyst.py` imports `asyncpraw`, while Poetry declares `praw`.
- Docker installs `requirements.txt`, which omits packages used by configured agents, including `pandas_ta` and `statsmodels`.
- The full Poetry project declares many packages that the Docker image does not install.
- The API container runs an additional unpinned `pip install` every time it starts.
- Root Python is constrained to 3.12, while the audit host provides Python 3.14.7.

Impact:

A restored models file would not be enough to produce a reproducible local or container runtime.

Required action:

- Make `pyproject.toml` and `poetry.lock` the authoritative dependency set.
- Use Poetry export or an equivalent locked build artifact for containers.
- Replace startup-time installation with image-build installation.
- Add explicit dependency groups for API, agents, ML, backtesting, and development if separate images are desired.
- Test from a clean Python 3.12 environment.

### C3 ML inference is demonstrative, not trained inference

`ml/inference/server.py` instantiates a new `CandlestickCNN` but leaves weight loading commented out. It also leaves PPO loading commented out and returns a fixed heuristic risk multiplier.

Although `ml/weights/cnn_btc_usdt.pth` and `ml/weights/ppo_position_sizer.zip` exist, the server does not use them.

Impact:

- Predictions come from randomly initialized CNN weights.
- Results are non-deterministic and not meaningful trading signals.
- The README and historical audit previously described the ML path as complete.
- The service is not included in Compose.
- Its default port 8080 conflicts with Kafka UI.

Required action:

- Validate weight provenance and compatibility.
- Load models during a controlled startup hook.
- Fail readiness when weights cannot load.
- Version model metadata and preprocessing.
- Add deterministic inference tests.
- Move the service to a non-conflicting port and add it to a dedicated profile.

### C4 The platform is unsafe for paper or live claims

The repository contains multiple explicit or implicit mocks:

- All four Tier 6 DeFi agents contain skeleton logic.
- Crypto, forex, and equity dashboard providers use deterministic random walks.
- Holdings are static mock data.
- The ML RL decision is mocked and the CNN is untrained at runtime.
- The mock dashboard roster is stale and does not reflect real agent IDs.
- Kubernetes and Terraform do not describe a complete deployment.
- API authentication, authorization, rate limiting, and TLS are absent.
- Kafka and Redis use plaintext local connections.
- Compose exposes infrastructure ports on the host.
- Default development passwords are present in `.env.example` and Compose fallbacks.

Required action:

Keep `ENVIRONMENT=development` and `ENABLE_DEFI_AGENTS=false`. Do not enable paper or live trading until the critical and high findings are resolved and independently verified.

## High findings

### H1 Compose covers only part of the agent roster

Source contains 36 concrete agent classes. Compose defines 20 agent services.

Notable omissions include:

- Six Tier 2 intelligence agents other than Price Publisher.
- All three Tier 3 quant agents.
- ML Predictor.
- All four Tier 6 DeFi agents, appropriately omitted while unsafe.
- Auditor and Copy Trading agents.

This is not necessarily wrong for a supported subset, but current documentation calls it a full agent stack.

Required action:

Define explicit Compose profiles such as `infra`, `core-agents`, `strategies`, `monitoring`, and `experimental`. Document the supported minimum topology and dependencies for each profile.

### H2 Eight agent loops lack the documented kill-switch guard

A static review found no direct `await self.is_halted()` check in the `run()` methods of:

- ProposalApprover
- RiskGovernor
- GeopoliticalWatcher
- MarketDataHub
- OnChainSleuth
- PricePublisher
- SentimentAnalyst
- CorrelationEngine

Some data-producing or risk-governance agents may need different halt semantics, but this differs from the repository instruction that every agent includes the guard.

Required action:

Specify expected behavior per agent category, implement it consistently, and add contract tests. Risk and cancellation components must continue the minimum activity required to make a halt safe.

### H3 Kafka topic references drift from topic provisioning

The Kafka initializer creates 18 topics. Runtime Copy Trading code references `STRATEGY_SIGNALS` and `ORDERS_FILLED`, neither of which is present in `infra/init/kafka-init.sh`. Tests also reference legacy names such as `MARKET_DATA` and `ANALYSIS_TECHNICAL`.

The missing `KafkaTopic` enum prevents a definitive enum-to-initializer comparison.

Required action:

After restoring models, generate a single topic manifest and test that the enum, initializer, consumers, producers, dashboards, and documentation agree.

### H4 Local `mcp` package shadows the installed MCP dependency

The repository contains a top-level `mcp/` package while `pyproject.toml` depends on the external `mcp` package. `mcp/claude_model_manager/server.py` inserts the repository root at the front of `sys.path` and then imports `mcp.server.fastmcp`.

That import resolves the local package first, where `server.fastmcp` does not exist.

Required action:

Rename the local package, for example to `alghrest_mcp/`, or package the server with an entry point that cannot shadow the dependency.

### H5 Environment template and Settings have drifted

Variables in `.env.example` but not represented in `Settings` include:

- `CNN_MODEL_PATH`
- `RL_MODEL_PATH`
- `SOLANA_PRIVATE_KEY`
- `TIMESCALE_URL`
- `PAGERDUTY_SERVICE_ID`
- `GRAFANA_ADMIN_USER` and `GRAFANA_ADMIN_PASSWORD`
- Vault, Pinecone, Stripe, and eToro variables
- `POSTGRES_PASSWORD`

Settings absent from the example include:

- `PAGERDUTY_INTEGRATION_KEY`
- `TELEGRAM_CHAT_ID`

Required action:

Separate application settings from infrastructure-only environment values, validate required values by runtime profile, and generate reference documentation from the typed settings schema.

### H6 Deployment scaffolds contain stale assumptions

Examples:

- The Kubernetes market-data manifest labels MarketDataHub as agent ID 3 and Prometheus port 9203; source assigns ID 5.
- The same manifest invokes the module with `python -m` even though agent startup is centralized in `run_agent.py`.
- Terraform provisions VPC, EKS, and Redis only; Kafka and TimescaleDB are comments.
- Nginx serves HTTP only and proxies the Vite development server.
- No Kubernetes namespace, ConfigMap, Secret, Kafka, database, ingress, certificates, or agent set is provided.

Required action:

Label these files experimental until rebuilt and validated in a disposable environment.

### H7 Historical reports contain claims contradicted by the current tree

The nine-page `alghrest-diagnostic-report.docx` is visually readable but no longer reliable as a status source. It says the coverage gate is disabled, CI/CD is absent, ML is complete, Alembic migrations exist operationally, and several agent completion percentages are established. The current tree contradicts several of these statements.

The DOCX also has a dangling Tier 6 table header at the bottom of page 3, large unused areas on pages 4 through 8, no substantive comments or tracked changes, and anonymous metadata.

Required action:

Archive it as historical or replace it with a dated report derived from repeatable checks.

## Medium findings

### M1 Dashboard mock roster is stale

`api/mock_server.py` advertises 32 agents with an older ID mapping. It omits current agents, includes the nonexistent Options Strategist, treats Position Sizer as a runtime agent, and assigns names and IDs that differ from source.

Required action:

Generate mock roster data from a shared static manifest that is also tested against source IDs.

### M2 Frontend quality gates are incomplete

The dashboard has `dev`, `build`, and `preview` scripts but no lint, format, unit-test, component-test, or end-to-end-test scripts. No frontend test files were found.

Required action:

Add ESLint, Prettier, Vitest with React Testing Library, and a small Playwright smoke suite. Validate WebSocket reconnect and schema rejection behavior.

### M3 Database migration documentation is inaccurate

Alembic is declared as a dependency and older documentation says to run `alembic upgrade head`. There is no `alembic.ini` and no migration directory. Database creation currently relies on `infra/init/timescale-init.sql`.

Required action:

Choose SQL initialization or Alembic as the supported migration strategy and document only executable commands.

### M4 Container reproducibility and hardening need work

- Root Docker image runs as root.
- Dependencies are broad minimums rather than locked versions.
- Compose uses `timescale/timescaledb:latest-pg16`.
- Dashboard image uses `npm install` instead of `npm ci`.
- API startup installs packages at runtime.
- Health and resource policies are inconsistent.
- Many host ports are exposed.

Required action:

Pin images by version or digest, install locked dependencies at build time, run as non-root, add read-only filesystems where practical, and restrict network exposure.

### M5 Repository governance files are absent

The snapshot has no:

- `LICENSE`
- `CONTRIBUTING.md`
- `CODE_OF_CONDUCT.md`
- `.editorconfig`
- `.pre-commit-config.yaml`
- `Makefile` or task runner

The README previously claimed a proprietary license without a license file.

Required action:

Add only the governance files and license terms approved by the repository owner.

### M6 The repository contains overlapping HMM trees

There are two HMM implementations:

- `alghrest-test/HMM_Trading/`, with tests, configuration, layered source, documentation, and local instructions.
- `project/`, an older implementation with duplicate report and PDF content.

The Stanford PDFs are byte-identical. `project/HMM_Trading_Report.md` and `project/reports/HMM_Trading_Report.md` are also identical.

Required action:

Treat `alghrest-test/HMM_Trading/` as the maintained project, then archive or remove the older tree after confirming no unique behavior is needed.

### M7 No repository metadata is present in the supplied directory

The project directory contains no `.git` entry, so branch, commit, tracked changes, and worktree cleanliness could not be verified.

Required action:

Confirm whether this is an exported snapshot. Initialize or restore version control before substantial repairs.

## Subsystem assessment

### Agents and orchestration

Strengths:

- All 36 concrete agent classes have unique IDs.
- Every concrete agent implements `initialize()`, `run()`, and `shutdown()`.
- Tier 4 classes inherit `BaseStrategy`.
- Base lifecycle, heartbeat, metrics, and Redis/Kafka abstractions are coherent.
- The order pipeline has explicit anti-reentry flags for optimization and child orders.

Risks:

- The shared model layer is absent.
- Kill-switch behavior is inconsistent.
- Compose runs only a subset.
- Several intelligence integrations depend on external services without a complete degraded-mode contract.
- Broad exception handling and silent `pass` blocks can hide health failures.

### Risk and execution

Strengths:

- Code exists for position limits, risk metrics, drawdown response, kill switch, liquidation monitoring, order routing, slippage handling, fee optimization, cancellation, and fill publication.
- Unit and integration tests target critical behavior, including cancellation and crash scenarios.

Risks:

- Tests could not run.
- Live safety depends on the missing model contracts.
- API and infrastructure controls do not establish a production security boundary.
- Strategy validation thresholds are useful but cannot establish operational safety alone.

### API

Strengths:

- Clear health, metrics, portfolio, risk, agent, signal, quote, and WebSocket surfaces.
- Pydantic/FastAPI structure and localhost CORS allowlists are reasonable for development.
- Production and mock apps share quote routes.

Risks:

- The production API cannot import.
- Authentication and authorization are absent.
- WebSockets accept clients without authentication.
- Error handling is broad in several loops.
- The API container mutates its environment at startup by installing packages.

### Dashboard

Strengths:

- Eight routed pages.
- Shared quote polling through TanStack Query.
- Central Zustand store and Zod-based message types.
- Error boundaries, loading skeletons, and reconnect UI exist.
- Visual components cover portfolio, positions, agents, Kafka, and risk.

Risks:

- Dependencies are absent, so the production build was not verified.
- No automated frontend quality gate exists.
- Demo agent data is stale.
- The Vite dev server and external Yahoo proxy are used in development configuration.
- The root Compose/Nginx path is development-oriented rather than a production build.

### Machine learning

Strengths:

- CNN and Gymnasium environment definitions exist.
- Training scripts and two weight artifacts are present.
- The agent-side HTTP boundary is a good deployment seam.

Risks:

- Inference ignores both weight artifacts.
- Input normalization and model-version contracts are not enforced.
- The RL result is hard-coded.
- No Compose service or model health endpoint exists.
- The weight files were not executable-audited and should be treated as untrusted binary artifacts until provenance is verified.

### Infrastructure and observability

Strengths:

- Compose configuration renders successfully.
- Kafka is a three-broker cluster with explicit topics.
- Redis, TimescaleDB, Prometheus, Grafana, exporters, Kafka UI, API, dashboard, and Nginx are represented.
- Kafka initialization is idempotent and its Bash syntax passes.

Risks:

- Full runtime was not started.
- Security is development-grade.
- Kubernetes and Terraform are incomplete.
- Static IP allocation increases maintenance cost.
- Documentation conflates service count with agent count.
- ML orchestration is missing.

### Tests and CI

Strengths:

- 146 root test functions cover models, risk, execution, price publishing, portfolio tracking, imports, prompt caching, Kafka, Redis, API/dashboard integration, backtesting, crash handling, and ML failover.
- Coverage is configured with a 70% gate.
- GitHub Actions defines lint, unit, integration, security, scheduled backtest, and performance jobs.

Risks:

- The suite cannot collect without the shared model package.
- The audit environment lacks Poetry, pytest, Ruff, Black, isort, and mypy.
- The Codecov step points to `htmlcov/coverage.xml`, while current pytest configuration does not generate that XML file.
- Several CI claims in historical reports are stale.
- A clean CI run is required before coverage figures are credible.

### HMM research assets

The maintained HMM project has clear local instructions, layered pipeline modules, configuration, unit/integration/artifact tests, and a research disclaimer.

The 17-page Stanford reference is a January 2026 draft appendix by Daniel Jurafsky and James H. Martin. It covers Markov chains, HMM definitions, likelihood, the forward algorithm, Viterbi decoding, forward-backward/Baum-Welch training, and historical references. All pages render cleanly. The PDF is not tagged for accessibility and has blank title/author metadata fields.

The two generated HMM figures render clearly. They show:

- Market regimes labeled as states 0, 1, and 2 across the S&P 500 series.
- A backtest in which the HMM strategy ends materially below buy and hold.

The charts need source/date/methodology annotations if used outside the research project.

### Documentation

Strengths:

- Architecture, risk limits, execution pipeline, developer commands, HMM boundaries, and lightweight mode are documented.
- Root and subproject instructions communicate safety concerns.

Risks:

- Documentation had repeated 32/36-agent drift.
- README paths referenced missing files and directories.
- Historical reports state completion without repeatable evidence.
- `AGENTS.md` and `CLAUDE.md` have drift despite one claiming the other is canonical.
- Four relative links in bundled documentation under `dashboard/.agents/skills/` point to intentionally absent example/reference files.
- Root deployment documentation includes commands for missing migration files.

The root README was replaced during this audit with a status-first guide that discloses blockers and separates the safe mock path from the blocked full runtime.

## Validation results

| Check | Result | Notes |
|---|---|---|
| Python AST parse | Pass | 164 of 164 files parsed |
| Python byte-compile | Pass | Syntax only; dependencies not imported |
| Agent ID uniqueness | Pass | 36 IDs, no duplicates |
| Agent lifecycle methods | Pass | All concrete agent classes define required methods |
| Direct kill-switch guard | Fail | Absent in eight run methods |
| Internal import resolution | Fail | `core.data.models` missing; MCP shadowing also identified |
| JSON and notebooks | Pass | 14 documents parsed |
| Markdown relative links | Pass with exceptions | Repository-authored docs pass; four bundled skill-document examples reference absent files |
| Kafka init Bash syntax | Pass | 18 topics provisioned |
| Plain JavaScript syntax | Pass | `project_site/app.js` |
| Docker Compose render | Pass with example environment | 37 services; validated with `.env.example` temporarily staged as `.env` |
| Root import smoke test | Blocked | First failure was missing `structlog`; static resolution also proves models missing |
| Ruff | Blocked | Poetry unavailable |
| Root pytest | Blocked | Poetry/pytest unavailable and models missing |
| Dashboard build | Blocked | `node_modules` absent; `tsc` unavailable |
| PDF visual review | Pass | All 17 pages readable and unclipped |
| DOCX visual review | Pass with defects | Readable; stale content and poor pagination |
| HMM figures | Pass | Both images readable |

## Prioritized remediation

### Phase 0 Recover a runnable baseline

1. Restore the shared models package from an authoritative source.
2. Create a Python 3.12 environment.
3. Reconcile and lock dependencies.
4. Make import smoke tests and model tests pass.
5. Build the root and dashboard containers without startup-time installs.

Exit criterion: a clean checkout can install, import, and run the unit suite.

### Phase 1 Establish trustworthy quality gates

1. Run and fix Ruff, Black, isort, and mypy.
2. Run root unit tests with coverage.
3. Correct CI coverage artifacts.
4. Add dashboard lint and tests.
5. Run HMM tests in its separate environment.
6. Publish machine-readable test and coverage reports.

Exit criterion: required CI jobs pass from a clean checkout.

### Phase 2 Restore runtime contracts

1. Reconcile all Kafka topics.
2. Define per-agent kill-switch behavior.
3. Correct the mock roster and agent manifest.
4. Add Compose profiles and missing production-capable services.
5. Load and validate ML weights or label the service purely experimental.
6. Add integration tests for every supported profile.

Exit criterion: the development topology starts, reports healthy, processes a synthetic proposal end to end, and halts safely.

### Phase 3 Harden for controlled paper trading

1. Add API authentication, authorization, rate limiting, and audit logging.
2. Add TLS/authentication for Kafka, Redis, and ingress.
3. Remove default credentials and adopt a secrets manager.
4. Pin images and dependencies.
5. Run containers as non-root with reduced privileges.
6. Define database migrations, backup, restore, and retention.
7. Add failure injection and recovery tests.
8. Validate exchange testnet controls and withdrawal-disabled credentials.

Exit criterion: an independent review approves a limited, monitored paper-trading deployment.

### Phase 4 Evaluate live readiness

Live use requires evidence beyond passing tests:

- Model and strategy governance.
- Reproducible backtests with leakage controls.
- Testnet execution history.
- Reconciliation and idempotency proof.
- Kill-switch and disaster-recovery drills.
- Security review and secret rotation.
- Operational ownership and on-call procedures.
- Compliance and legal review for target jurisdictions.

No live-readiness date should be set until those controls exist.

## Recommended professional environment

A maintainable target environment should include:

- `.python-version` pinned to Python 3.12.
- Poetry as the root source of truth, with exported locked requirements for images.
- Separate dependency groups or images for API, core agents, quant/ML, backtesting, and development.
- `.editorconfig` and pre-commit hooks.
- Ruff, Black, isort, mypy, pytest, coverage, Bandit, and dependency scanning.
- ESLint, Prettier, Vitest, React Testing Library, and Playwright for the dashboard.
- Compose profiles for infrastructure, development, monitoring, and experimental services.
- A non-live default with fail-closed configuration validation.
- Generated agent/topic/config manifests checked in CI.
- A documented migration, backup, restore, and incident-response process.
- A root license and contribution policy approved by the owner.

## Conclusion

ALGHREST has a broad architecture and meaningful implementation work, but the current snapshot is an integration-incomplete prototype. The missing shared models package is a fatal blocker, and documentation previously hid that fact behind production-grade language. The project should now be managed as a recovery effort: restore the core contract, establish a clean build, make tests authoritative, then reintroduce runtime components behind explicit development profiles.

The updated README reflects that status and provides a safe mock-dashboard path without implying that the full trading system is operational.
