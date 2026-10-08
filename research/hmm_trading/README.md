# HMM_Trading

Independent educational Hidden Markov Model study inside ALGHREST. It detects
market regimes, exports charts/results and runs an illustrative backtest. Its
in-sample results do not establish out-of-sample edge or real-trading readiness.
The study does not place broker orders or influence approved root advice.

## Work in the research directory

Use `research/hmm_trading/` with its own environment, dependency file and pytest
configuration. This is part of the private ALGHREST repository, not a separate
Git repository or submodule. Its package is named `src`; do not reuse the root
application environment or run these tests from the repository root.

PowerShell, starting at the ALGHREST root:

```powershell
Set-Location research/hmm_trading
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install pytest
python main.py
python -m pytest tests/
```

The subproject metadata allows Python 3.9+; the main application requires 3.12.
Using a separate 3.12 environment keeps the workspace consistent. The research
requirements use version ranges, not a lockfile; capture installed versions for
reproducible studies. Generate outputs before the artifact test.

## Pipeline and configuration

`main.py` loads `configs/default.json` through `src/core/config.py` and calls
`src/pipeline/runner.py`. The runner locates/extracts reference material, loads
OHLCV data, computes features, fits a Gaussian HMM, decodes/interprets regimes,
builds an educational signal/backtest, and exports metrics and charts.

The data loader attempts Yahoo Finance first. On download/import failure it uses
synthetic Markov-regime data. Check the console's source/fallback messages and
label synthetic outputs explicitly; fallback is not proof of real market access.
The PDF extractor tries pypdf, then PyMuPDF, then its embedded theoretical summary.

See [configuration fields and currently wired controls](configs/README.md).
Schema validation does not mean every configuration field controls pipeline math.
The maintained Stanford PDF is in
`references/Stanford_Hidden_Markov_Models.pdf`; see [reference notes](references/README.md).

## Structure

```text
research/hmm_trading/
  main.py                 Thin command-line entry point
  configs/default.json    Configuration and schema inputs
  src/core/               Configuration, paths and logging
  src/data/               Yahoo loader and synthetic fallback
  src/models/             Features and HMM fitting/decoding
  src/analysis/           Regime interpretation and educational backtest
  src/reporting/          CSV/JSON exports and charts
  src/references/         Reference search and PDF extraction
  tests/                  Unit, integration and generated-output checks
  references/             Included source reference material
  reports/                Research report
  docs/                   Research architecture
  outputs/                Generated locally; ignored by Git
```

## Output and tests

`python main.py` writes result CSVs including `hmm_regimes.csv`,
`state_summary.csv`, `backtest_metrics.csv`, `transition_matrix.csv` and
`backtest_results.csv`, plus `outputs/results/run_config.json`, extracted text and charts.

The artifact test specifically checks these paths:

```text
outputs/results/hmm_regimes.csv
outputs/results/state_summary.csv
outputs/results/backtest_metrics.csv
outputs/results/transition_matrix.csv
outputs/figures/01_price_regimes.png
outputs/figures/02_equity_curves.png
outputs/figures/03_regime_distribution.png
outputs/figures/04_transition_matrix.png
```

From this directory, use `python -m pytest tests/` for all tests, or target
`tests/unit/`, `tests/integration/`, or `tests/artifacts/`. Missing generated
outputs cause the artifact test to fail with an instruction to run `main.py`.
Generated output files, `.venv` and caches are not committed.

## Development and root integration

Read `AGENTS.md`, `CLAUDE.md` and [research architecture](docs/architecture.md)
before changes. Preserve outputs/reports/references, keep mathematical changes
explicit, and follow scoped pipeline/test verification. Root integration remains
a separate task requiring an explicit CSV/CLI/API contract and tests; the study
is not automatically wired into ALGHREST production decisions.

See the root [research index](../README.md),
[development workflow](../../docs/monorepo-workflow.md),
[integration roadmap](../../docs/integration-roadmap.md) and
[private collaborator setup](../../docs/private-collaboration.md).
