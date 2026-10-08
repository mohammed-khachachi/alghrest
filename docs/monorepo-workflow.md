# Development workflow

## Application

Work from the repository root with Python 3.12. `poetry install` installs the packages in `src/`; the root `pyproject.toml` owns dependencies and lint, formatting, type, test, and coverage settings. Existing pip environments can use `python -m pip install --no-deps -e .` after installing their runtime dependencies.

```powershell
poetry run python scripts/check_architecture.py
poetry run pytest -m unit
poetry run pytest -m integration
poetry run ruff check src scripts tests
poetry run mypy src/agents/ src/core/
```

The default coverage gate is 70%. Integration tests require their documented infrastructure and opt-in variables. A focused diagnostic run can explicitly use `--no-cov`; it is not evidence that the coverage gate passed. Use `poetry run python scripts/run_tests.py --help` for the test runner. It uses the selected interpreter and the root test configuration.

Root discovery targets `tests/`, not research tests. Do not add `src.` to application imports or rely on changing `sys.path` in new application modules. Dashboard code and its package lock stay in `dashboard/`; see [lightweight development](LIGHTWEIGHT_DEV.md).

## HMM research

The current study is `research/hmm_trading/`. The older implementation is retained in [the private archive snapshot](https://github.com/mohammed-khachachi/alghrest/tree/f88e63be74c2f64ca68c5564c20863f97ca980c8/research/hmm_legacy), outside the current working tree. Work inside `research/hmm_trading/` using a separate virtual environment.

```powershell
Set-Location research/hmm_trading
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest
python main.py
python -m pytest tests/
```

HMM owns its configuration, references, outputs, and test configuration. Its local package is named `src`, unlike the root application's `src/` container directory; do not mix their import paths or environments. Keep reports and reference material. Generated outputs are ignored, and the HMM loader may use synthetic data when downloads fail, so label resulting evidence accordingly.

## Changes across projects

Runtime and research dependency graphs remain separate. A research integration requires an explicit interface and tests, described in the [integration roadmap](integration-roadmap.md). Document cross-project changes in the same review. CI currently runs application checks; run the independent research suite when moving or changing that project.

New architecture decisions belong in `docs/decisions/`. Keep current usage instructions separate from historical audit evidence. See the [layout migration record](maintenance/structure-migration.md) for old-to-new paths.
