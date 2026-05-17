# HMM_Trading Architecture

## 1. Purpose

HMM_Trading is an independent research and educational project for detecting market regimes with Hidden Markov Models. It demonstrates a reproducible workflow for loading market data, engineering observations, fitting a Gaussian HMM, interpreting hidden states, running a simple educational backtest, and exporting results.

It is not a live trading system. It does not place orders, manage capital, or provide financial advice. All outputs should be treated as research artifacts that require careful interpretation.

## 2. Position Inside the Monorepo

ALGHREST is the root project. HMM_Trading is an independent subproject located at:

```text
alghrest-test/HMM_Trading/
```

HMM_Trading is not a separate Git repository and it is not a Git submodule. It lives inside the monorepo as a self-contained project with its own tests, `pyproject.toml`, `requirements.txt`, generated outputs, reports, and documentation.

Do not mix HMM_Trading runtime assumptions with the root ALGHREST application. The subproject should remain isolated until an explicit integration boundary is implemented.

## 3. High-Level Pipeline

The pipeline starts from `main.py`, loads configuration, and delegates execution to `src/pipeline/runner.py`. The runner coordinates reference extraction, data loading, model training, analysis, reporting, and output generation.

```text
main.py
-> src/core/config.py
-> src/pipeline/runner.py
-> src/references/
-> src/data/
-> src/models/
-> src/analysis/
-> src/reporting/
-> outputs/
```

```text
main.py
  └── load_config("configs/default.json")
      └── runner.run(config)
          ├── locate/extract Stanford HMM PDF
          ├── load market data or synthetic fallback
          ├── compute features
          ├── train Gaussian HMM
          ├── decode market regimes
          ├── interpret regimes
          ├── run educational backtest
          ├── generate charts
          └── export CSV/JSON outputs
```

## 4. Directory Structure

```text
HMM_Trading/
├── main.py
├── pyproject.toml
├── requirements.txt
├── configs/
├── src/
│   ├── core/
│   ├── data/
│   ├── models/
│   ├── analysis/
│   ├── reporting/
│   ├── references/
│   └── pipeline/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── artifacts/
├── references/
├── outputs/
├── reports/
└── docs/
```

`configs/` stores runtime configuration. `src/` contains the pipeline implementation. `tests/` contains unit, integration, and artifact checks. `references/` stores source reference material used by the project. `outputs/` contains generated CSV, JSON, text, and chart artifacts. `reports/` contains human-readable report material. `docs/` contains developer documentation.

## 5. Core Modules

`main.py` is the executable entry point for running the full workflow from the command line.

`src/core/config.py` loads project configuration from JSON files.

`src/core/paths.py` centralizes project-root path resolution.

`src/pipeline/runner.py` orchestrates the end-to-end HMM workflow and returns a small result summary.

`src/data/loader.py` loads market data, using live download when available and synthetic fallback data when needed.

`src/data/synthetic.py` generates deterministic synthetic OHLCV data for offline or sandboxed runs.

`src/models/features.py` computes market features and builds the scaled observation matrix used by the HMM.

`src/models/hmm.py` trains the Gaussian HMM, decodes hidden states, and builds model summaries.

`src/analysis/regime.py` interprets decoded states as market regimes and builds regime time series.

`src/analysis/backtest.py` builds simple signals and runs the educational backtest.

`src/reporting/exporter.py` writes tabular metrics and configuration outputs.

`src/reporting/visualization.py` generates charts from prices, regimes, backtest results, and transition matrices.

`src/references/finder.py` locates the Stanford HMM PDF reference inside the project.

`src/references/extractor.py` extracts text from the selected reference PDF.

## 6. Configuration

`configs/default.json` is the primary configuration source for the pipeline. Important keys include:

- `ticker`
- `start`
- `end`
- `n_states`
- `covariance_type`
- `n_iter`
- `random_state`
- `transaction_cost`
- `feature_cols`
- `regime_thresholds`

Do not store secrets in configuration files. HMM_Trading configuration should remain portable and safe to commit.

## 7. Testing Architecture

The test suite is scoped to the HMM_Trading subproject.

`tests/unit/` checks focused behavior for feature engineering, HMM helpers, signal construction, and backtesting.

`tests/integration/test_pipeline_smoke.py` runs a shortened end-to-end pipeline smoke test and verifies the returned result shape.

`tests/artifacts/test_outputs_exist.py` verifies that required generated output files exist and are non-empty after a prior pipeline run.

`tests/conftest.py` provides shared fixtures such as the project root, default configuration, synthetic OHLCV data, and feature matrices.

Useful commands:

```powershell
python -m pytest tests/
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/artifacts/
```

## 8. Outputs and Artifacts

`outputs/` is ignored by Git because it contains generated artifacts, not source code. These files are regenerated by running the pipeline.

Core generated files include:

- `outputs/results/hmm_regimes.csv`
- `outputs/results/state_summary.csv`
- `outputs/results/backtest_metrics.csv`
- `outputs/results/transition_matrix.csv`
- `outputs/figures/01_price_regimes.png`
- `outputs/figures/02_equity_curves.png`
- `outputs/figures/03_regime_distribution.png`
- `outputs/figures/04_transition_matrix.png`

## 9. Integration Boundary with ALGHREST

Integration with the root ALGHREST project should be gradual and explicit.

Level 1 -- File-based CSV integration:
Root ALGHREST reads `outputs/results/*.csv` generated by HMM_Trading.

Level 2 -- CLI integration:
Root ALGHREST runs `HMM_Trading/main.py` as a subprocess and consumes generated outputs.

Level 3 -- Python API integration:
Root ALGHREST imports a packaged HMM module after the subproject has a stable public API.

Level 1 is the best starting point because it creates a clear contract without coupling the root application to HMM_Trading internals.

## 10. Development Workflow

Run HMM_Trading commands from the subproject root:

```powershell
cd D:\My_PTOJECT\alghrest-test\alghrest-test\HMM_Trading
python -m pytest tests/
python main.py
```

Do not run the HMM test suite from the root project. Do not use the root virtual environment inside HMM_Trading. Do not use an HMM_Trading virtual environment inside the root ALGHREST project.

## 11. Design Principles

- Independence
- Reproducibility
- Small modules
- Clear pipeline orchestration
- Generated outputs are not source code
- Tests before integration
- CSV contract before Python API coupling

## 12. Limitations

HMM_Trading is educational and research-oriented. The backtest is intentionally simple and is not production-grade. Results are not financial advice.

Live market data access can fail, especially in offline or sandboxed environments. The project includes a synthetic fallback so the pipeline can still run.

HMM regimes require careful interpretation. Hidden states are statistical clusters, not guaranteed economic truths.

## 13. Future Work

- `docs/testing.md`
- `docs/outputs.md`
- README update
- HMM-specific CI workflow
- CSV adapter in root ALGHREST
- Package HMM_Trading later if Python API integration becomes necessary
