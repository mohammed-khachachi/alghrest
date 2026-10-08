# Current project inventory — 2026-10-06

The private repository's default branch, `main`, is the development tree.
The current Python application lives only in `src/`. There are no old root
`agents`, `core`, `api`, `connectors`, `backtesting`, `ml`, `project`,
`alghrest-test`, `project_site` or `XXsabo` copies in the current tree.

Current contents:

- `src/`: application, advisory pipeline, accounting, risk, APIs and strategy/research tools.
- `tests/`: application regression/unit/integration tests and their helpers.
- `dashboard/`: UI source, assets, package manifest and npm lockfile.
- `infra/` and root Compose/Docker files: current configuration, SQL migrations and service definitions; scaffolds retain their documented maturity limits.
- `scripts/`: current operator and developer commands.
- `research/hmm_trading/`: independent current HMM study, own tests/dependencies and reference material.
- `artifacts/models/`: both existing local ML assets, not proof of model quality or production readiness.
- `artifacts/tcp25-goal/`: selected synthetic verification summaries/examples. One before-code fixture is deliberately retained because the opt-in comparison in `test_trade_management.py` requires it; it is not a runtime agent or a second application implementation.
- `docs/`: current guides, architectural decisions, migration records and dated verification explanations.
- `examples/` and `mcp/`: documented optional examples/scaffold.
- Root README, conventions, dependency/lock files, environment example and CI configuration.

## Historical material

Thirty-nine historical files are removed from `main` and retained in the
private branch `archive/pre-current-project-cleanup-20261006`. The exact immutable
[snapshot before cleanup](https://github.com/mohammed-khachachi/alghrest/tree/f88e63be74c2f64ca68c5564c20863f97ca980c8)
preserves all their bytes and original paths:

- Seven old summaries/descriptions in `docs/archive/`.
- Thirteen raw dated recovery files in `docs/recovery/`.
- The old root overnight report, recovery environment/inventory and dated paper-readiness JSON.
- The fifteen files in the retired `research/hmm_legacy/` study, including its old notebook and generated figures.

The identical Stanford PDF remains in the current study at
`research/hmm_trading/references/Stanford_Hidden_Markov_Models.pdf`; its retired
duplicate is recoverable in the archive. No unique retired research code is
permanently destroyed. No active application, tests, dashboard, scripts,
infrastructure, current HMM source or model bytes are changed by this cleanup.

Historical architecture decisions and dated verification explanations remain
when they explain the current structure or safety requirements. Repeated empty
`__init__.py` files are required package markers, not unnecessary duplicates.
Experimental DeFi, execution/reconciliation for non-advisory profiles and
infrastructure scaffolds are kept because they are documented components of the
whole project. Their presence does not enable advisory order execution.

## Verification and exclusions

The cleanup checks retained-file hashes, duplicate files, obsolete paths,
editor backup extensions, documentation links and architecture/import behavior.
Each file in the final GitHub tree is checked against its expected Git blob.

Actual `.env`, credentials, private keys, financial stores, private datasets,
raw operational logs, installed dependencies and caches are excluded. Retired
local paths are ignored so a later upload cannot silently reintroduce them.
The local historical files and Git history are preserved for recovery.

Use [private collaboration](../private-collaboration.md) for developer setup.
