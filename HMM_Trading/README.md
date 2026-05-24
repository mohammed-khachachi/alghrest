# HMM_Trading

Hidden Markov Models for Quantitative Trading is an educational research pipeline for market regime detection, regime interpretation, and a simple in-sample backtest. It is **not** a live trading system and does **not** provide financial advice.

The model and its interpretation follow the Stanford CS228 / CS229 treatment of Hidden Markov Models — Baum-Welch for parameter learning and Viterbi for state decoding — applied to daily OHLCV market data.

## Quick Start

```powershell
pip install -r requirements.txt
python main.py
```

By default the pipeline trains a 3-state Gaussian HMM on `^GSPC` (S&P 500) over `2010-01-01 → 2024-12-31`, decodes regimes, runs an educational backtest, and writes results + figures into `outputs/`.

## Custom Config

Edit `configs/default.json` (see `configs/README.md` for every field), then run:

```powershell
python main.py
```

## Run with a specific config

```powershell
python main.py --config configs/default.json
```

## Run tests

```powershell
python -m pytest tests/ -v
```

Markers:

| Path | Scope |
|------|-------|
| `tests/unit/` | Fast, isolated module tests (features, HMM math, backtest). |
| `tests/integration/` | End-to-end pipeline smoke checks. |
| `tests/artifacts/` | Verifies `outputs/` files are produced after a run. |

## Add Stanford PDF

Place the file in `references/` and `src/references/finder.py` will auto-detect it. Expected names and fallback behaviour are described in `references/README.md`.

## Pipeline Overview

`main.py` calls `src.pipeline.runner.run(config)`. The runner performs 12 ordered steps:

1. Locate the Stanford HMM PDF (`src/references/finder.py`).
2. Extract its text into `outputs/extracted_text/` (`src/references/extractor.py`).
3. Download daily OHLCV market data (`src/data/loader.py`; falls back to `src/data/synthetic.py` if the ticker is unavailable).
4. Engineer observation features — log return, rolling volatility, MA ratio, volume change, intraday range (`src/models/features.py`).
5. Train a Gaussian HMM with Baum-Welch (`src/models/hmm.py`).
6. Decode the most likely state sequence via Viterbi.
7. Interpret hidden states as labelled regimes — Bullish / Bearish / Sideways / High-Vol (`src/analysis/regime.py`).
8–9. Build a regime-driven signal and run an educational backtest with transaction costs (`src/analysis/backtest.py`).
10. Persist CSVs and the resolved run config (`src/reporting/exporter.py`).
11. Render figures — price+regimes, equity curves, regime distribution, transition matrix (`src/reporting/visualization.py`).
12. Print a terminal summary report (returns, Sharpe, max drawdown, per-regime stats).

## Outputs

After a successful run the following files are produced:

```text
outputs/
|-- extracted_text/
|   `-- stanford_hmm_extracted.txt
|-- results/
|   |-- backtest_results.csv
|   |-- backtest_metrics.csv
|   |-- hmm_regimes.csv
|   |-- state_summary.csv
|   |-- transition_matrix.csv
|   `-- run_config.json
|-- figures/
|   |-- 01_price_regimes.png
|   |-- 02_equity_curves.png
|   |-- 03_regime_distribution.png
|   `-- 04_transition_matrix.png
`-- theory/
    `-- stanford_hmm_extracted.txt

reports/
`-- HMM_Trading_Report.md
```

## Project Structure

```text
HMM_Trading/
|-- configs/
|   |-- README.md
|   `-- default.json
|-- docs/
|   `-- architecture.md
|-- notebooks/
|   `-- hmm_market_regime_detection.ipynb
|-- outputs/
|   |-- extracted_text/
|   |-- figures/
|   |-- results/
|   `-- theory/
|-- references/
|   `-- README.md
|-- reports/
|-- src/
|   |-- _legacy/                  # pre-reorg modules, kept for reference only
|   |-- analysis/
|   |   |-- backtest.py
|   |   `-- regime.py
|   |-- core/
|   |   |-- config.py             # load + validate JSON config
|   |   |-- dependencies.py
|   |   |-- logging.py            # section() / log() helpers used by the runner
|   |   `-- paths.py              # PROJECT_ROOT, outputs/reports paths
|   |-- data/
|   |   |-- loader.py             # OHLCV download + synthetic fallback
|   |   `-- synthetic.py
|   |-- models/
|   |   |-- features.py           # observation matrix construction
|   |   `-- hmm.py                # train_hmm / decode_states / summary
|   |-- pipeline/
|   |   `-- runner.py             # the 12-step orchestration
|   |-- references/
|   |   |-- extractor.py          # PDF text extraction
|   |   `-- finder.py             # locate Stanford HMM PDF in repo
|   `-- reporting/
|       |-- exporter.py           # save_dataframe / save_metrics / save_json
|       `-- visualization.py
|-- tests/
|   |-- _legacy/
|   |-- artifacts/
|   |   `-- test_outputs_exist.py
|   |-- integration/
|   |   |-- test_pipeline.py
|   |   `-- test_pipeline_smoke.py
|   |-- unit/
|   |   |-- test_backtest.py
|   |   |-- test_features.py
|   |   `-- test_hmm.py
|   `-- conftest.py
|-- main.py
|-- pyproject.toml
|-- README.md
`-- requirements.txt
```

> `src/_legacy/` holds the pre-reorganization modules (`backtest.py`, `data_loader.py`, `features.py`, `file_finder.py`, `hmm_model.py`, `pdf_reader.py`, `regime_interpreter.py`, `utils.py`, `visualization.py`). They are **not imported** by the active pipeline and exist only for diffing during the migration.

## Disclaimer

This project is for educational and research purposes only. Backtest results are **in-sample**, have not been validated out-of-sample, and must not be used to make real trading decisions.
