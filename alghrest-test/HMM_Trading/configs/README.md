# Configuration

`default.json` contains the baseline HMM trading experiment settings.

- `ticker`: Market symbol used for data retrieval.
- `start` / `end`: Date range for the historical sample.
- `n_states`: Number of hidden market regimes in the HMM.
- `n_iter`: Maximum number of HMM training iterations.
- `random_state`: Seed used to make model fitting reproducible.
- `feature_cols`: Feature columns used as the HMM input matrix.
- `regime_thresholds`: Return and volatility thresholds used when labeling regimes.
