# HMM_Trading

## Overview

HMM_Trading is an independent subproject inside the ALGHREST monorepo for detecting market regimes with Hidden Markov Models.

It is an educational and research project. It is not a live trading system, it does not place orders, and nothing in this project is financial advice. It runs independently from the root ALGHREST project.

## Position in the Monorepo

Root project: ALGHREST.

Subproject path:

```text
alghrest-test/HMM_Trading/
```

HMM_Trading is not a separate Git repository and it is not a submodule. It has its own configuration, tests, dependencies, generated outputs, and documentation.

Keep HMM_Trading changes separate from root ALGHREST changes unless an explicit integration task requires crossing that boundary.

## Quick Start

Windows PowerShell:

```powershell
cd D:\My_PTOJECT\alghrest-test\alghrest-test\HMM_Trading

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

python -m pytest tests/
python main.py
```

## Project Structure

```text
HMM_Trading/
├── main.py
├── configs/
├── src/
├── tests/
├── references/
├── outputs/
├── reports/
└── docs/
```

`main.py` is the command-line entry point. `configs/` stores pipeline configuration. `src/` contains the implementation. `tests/` contains unit, integration, and artifact checks. `references/` stores source reference material. `outputs/` contains generated artifacts. `reports/` contains report material. `docs/` contains developer documentation.

## Configuration

The main configuration file is:

```text
configs/default.json
```

Important keys:

- `ticker`
- `start`
- `end`
- `n_states`
- `covariance_type`
- `n_iter`
- `random_state`
- `transaction_cost`
- `feature_cols`

Do not put secrets in HMM_Trading configuration files.

## Running the Pipeline

Run:

```powershell
python main.py
```

This executes:

- Stanford PDF extraction
- Market data loading
- Feature engineering
- HMM training
- Regime decoding
- Educational backtest
- Chart generation
- Output export

## Testing

```powershell
python -m pytest tests/
python -m pytest tests/unit/
python -m pytest tests/integration/
python -m pytest tests/artifacts/
```

Unit tests check individual components. The integration smoke test checks the pipeline path. The artifact test verifies that core generated outputs exist and are non-empty.

## Outputs

`outputs/` contains generated artifacts and is ignored by Git.

Core outputs:

- `outputs/results/hmm_regimes.csv`
- `outputs/results/state_summary.csv`
- `outputs/results/backtest_metrics.csv`
- `outputs/results/transition_matrix.csv`
- `outputs/figures/01_price_regimes.png`
- `outputs/figures/02_equity_curves.png`
- `outputs/figures/03_regime_distribution.png`
- `outputs/figures/04_transition_matrix.png`

## Documentation

- [docs/architecture.md](docs/architecture.md)

Future documentation may include `docs/testing.md` and `docs/outputs.md`.

## Integration with ALGHREST

Integration with root ALGHREST should be gradual:

1. File-based CSV integration
2. CLI integration
3. Python API integration after packaging

Level 1 is recommended as the starting point because it lets root ALGHREST consume `outputs/results/*.csv` without coupling to HMM_Trading internals.

## Development Rules

- Always work from the HMM_Trading directory when editing this subproject.
- Do not run HMM tests from the root project.
- Do not use the root virtual environment for HMM_Trading.
- Do not use an HMM_Trading virtual environment inside root ALGHREST.
- Do not commit `outputs/`, `.venv/`, caches, or generated files.
- Keep root ALGHREST changes separate from HMM_Trading changes.

## Disclaimer

This project is for educational and research purposes. Backtest results are not production-grade trading signals. Nothing here is financial advice.
