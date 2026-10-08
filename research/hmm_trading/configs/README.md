# HMM configuration

`default.json` is loaded by `main.py` through `src/core/config.load_config`.
Schema validation checks required keys and numeric/type constraints before
`src/pipeline/runner.run` executes. Keep secrets out of this file.

## Controls used by the current runner

| Key | Current baseline | Use |
| --- | --- | --- |
| `ticker` | `^GSPC` | Yahoo/synthetic OHLCV symbol |
| `start`, `end` | `2010-01-01`, `2024-12-31` | Requested data range |
| `n_states` | `3` | Gaussian HMM state count |
| `covariance_type` | `full` | HMM covariance form |
| `n_iter` | `300` | Maximum fitting iterations |
| `random_state` | `42` | HMM fitting seed |
| `transaction_cost` | `0.001` | Passed to signal/backtest functions |
| `feature_cols` | Five named features | Observation matrix selection |

The current features are `log_return`, `rolling_volatility`, `ma_ratio`,
`volume_change` and `intraday_range`.

## Required schema fields not wired through the runner

`trading_days_per_year`, `regime_thresholds`, `rolling_vol_window`,
`ma_fast_window` and `ma_slow_window` are required and validated. The current
runner does not pass them to the corresponding calculation functions. Changing
these fields alone does not demonstrate a changed annualization, regime label
or feature window. Those functions retain their own defaults/current logic.
Connecting these controls needs an explicit code change and meaningful tests.

`regime_thresholds` requires `return_bullish`, `return_bearish`, `vol_low` and
`vol_high`. Inspect `src/core/config.py` for validation constraints and
`src/pipeline/runner.py` for actual parameter flow. The run exports its config
to `outputs/results/run_config.json`; that records supplied metadata, not evidence that
all fields controlled the calculations.

Run and test from the [HMM project directory](../README.md) with its separate
environment. This configuration does not modify root ALGHREST risk/account rules.
