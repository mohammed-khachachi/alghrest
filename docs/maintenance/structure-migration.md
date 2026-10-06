# Structure migration — 2026-09-26

A verified snapshot was created before moving or deleting files. Local `.env`, environments, assistant state, and Git internals were excluded.

Backup: `/tmp/alghrest-before-structure-20260926.tar.gz` (341 files). SHA-256 inventory: `/tmp/alghrest-before-structure-20260926.sha256.json`. Copy the archive to permanent storage before the temporary directory is cleared.

## Moves

| Previous location | New location |
|---|---|
| `agents` | `src/agents` |
| `api` | `src/api` |
| `backtesting` | `src/backtesting` |
| `connectors` | `src/connectors` |
| `core` | `src/core` |
| `ml` | `src/ml` |
| `ml/weights` | `artifacts/models` |
| `alghrest-test/HMM_Trading` | `research/hmm_trading` |
| `project` | `research/hmm_legacy` |
| `project_site` | `examples/project-site` |
| `dashboard_preview.html` | `examples/dashboard-preview.html` |
| `deployment_guide.md` | `docs/runbooks/deployment.md` |
| `diagnostic-prompt.md` | `docs/maintenance/audit-prompt.md` |
| `XXsabo/README.md` | `docs/archive/legacy-readme.md` |
| `INTEGRATION_TESTS_SUMMARY.md` | `docs/archive/INTEGRATION_TESTS_SUMMARY.md` |
| `ML_FAILOVER_NEWS_FIXES_SUMMARY.md` | `docs/archive/ML_FAILOVER_NEWS_FIXES_SUMMARY.md` |
| `PROJECT_COMPLETION_AUDIT.md` | `docs/archive/PROJECT_COMPLETION_AUDIT.md` |
| `SECURITY_FIXES_SUMMARY.md` | `docs/archive/SECURITY_FIXES_SUMMARY.md` |
| `PROJECT_AUDIT_REPORT.md` | `docs/archive/PROJECT_AUDIT_REPORT.md` |
| `infrastructure_validation_report.md` | `docs/archive/infrastructure_validation_report.md` |
| `alghrest-diagnostic-report.docx` | `docs/archive/alghrest-diagnostic-report.docx` |

## Removed files

| File | Reason |
|---|---|
| `README.md.orig` | Obsolete editor backup; current README is canonical. |
| `tests/pytest.ini` | Conflicting, invalid secondary pytest configuration; pyproject.toml is canonical. |
| `skills-lock.json` | Exact duplicate of dashboard/skills-lock.json; root .agents directory is empty. |
| `research/hmm_legacy/HMM_Trading_Report.md` | Exact duplicate of reports/HMM_Trading_Report.md in the same research project. |

The empty `alghrest-test/` and `XXsabo/` directories were removed after moving their contents. Disposable Python/tool caches and generated coverage HTML are cleaned separately. Research outputs, references, configs, and unique reports are preserved.

## Compatibility

Run `poetry install` or reinstall an existing environment with `python -m pip install --no-deps -e .`. The local application and diagnostic test environments were reinstalled during verification. Import paths remain `agents`, `core`, `connectors`, `api`, `backtesting`, and `ml`. Shell entry points use module invocation where appropriate. Model output paths now use `artifacts/`.

The installed package and container exclude research, static examples, and model assets. Root pytest settings remain authoritative and retain the 70% gate. Runtime credentials, paper database volumes, imported balances, and risk limits were not modified.

## Recovery

Extract the backup into a separate directory to inspect original files; do not extract it over an active checkout. The manifest records original file checksums. This workspace did not respond as a valid Git repository during the migration, so no commit or Git-based rollback is claimed.

## Generated-file cleanup

Removed 51 cache/report paths (25,216,384 bytes), including Python bytecode caches, pytest/Ruff/mypy caches, `htmlcov/`, and `.coverage`. Environments, dependency directories, research outputs, model assets, and recovery evidence were preserved.

Validation results: [structure-validation.md](structure-validation.md).
