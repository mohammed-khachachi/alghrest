# Layout migration verification — 2026-09-26

| Check | Result |
|---|---|
| Application unit suite | 183 passed, including architecture boundary regression tests |
| Local Kafka/PostgreSQL/Redis paper replay test | 1 passed; isolated synthetic test scope was cleaned |
| Independent HMM suite | 27 passed after generating its expected outputs |
| HMM main pipeline | Completed in its own environment, using the existing synthetic-data fallback |
| Source distribution and wheel | Both built; six runtime packages only, no research, credentials, or model assets |
| Installation outside checkout | All six packages imported from an installed wheel; operational modules also imported from the editable installation |
| Monitoring dependency separation | Zero-metric fallback wrote the expected topics without importing the API; API and collector share the same list |
| Import boundaries and new-file Ruff checks | Passed |
| Poetry lock consistency | Passed; Poetry 2 reports existing metadata deprecation warnings |
| Both Compose manifests | `docker compose config --quiet` passed |
| Preservation | 66 unchanged research/model files verified by SHA-256; Compose manifests, lockfile, main runner, and dashboard dependency files unchanged |
| Current documentation links | No missing local targets in the checked overview/architecture/workflow pages |

## Commands and scope

```powershell
python scripts/check_architecture.py
python -m pytest tests/unit --no-cov -q
# Dedicated local paper environment only:
$env:PAPER_RUNTIME_TESTS = '1'
python -m pytest tests/integration/test_paper_runtime.py --no-cov -q
```

Research validation used a separate Python environment inside `research/hmm_trading/`:

```powershell
python main.py
python -m pytest tests/
```

The research artifact test requires outputs from `main.py`; the first run before output generation reported one missing-output failure. After generating outputs, all 27 tests passed. No HMM math or research source changed. Original reports and references were preserved. Application import failures caused by missing dependencies in the temporary test environment were resolved by installing the declared dependencies, without changing their source modules.

Application verification used explicit `--no-cov` diagnostic runs. The default 70% coverage gate is unchanged; this migration does not claim a full-suite coverage pass. The full production Docker image, full Poetry dependency installation, repository-wide lint/type checks, and live exchange operations were not exercised. The dashboard source was not changed or rebuilt. These checks establish layout, packaging, and selected runtime compatibility, not production trading readiness.

See [migration and cleanup record](structure-migration.md) for backup and removal details.
