from src.analysis.backtest import build_signal, run_backtest
from src.analysis.regime import build_regime_series, interpret_regimes
from src.models.features import compute_features


def test_demo_synthetic_regime_workflow(synthetic_ohlcv, trained_model, default_config):
    """Demo: synthetic prices -> HMM regimes -> trading signals -> backtest metrics."""
    model, states, X, dates = trained_model
    feature_df = compute_features(
        synthetic_ohlcv,
        config=default_config,
        verbose=False,
    ).loc[dates]

    stats_df, labels = interpret_regimes(
        feature_df,
        states,
        synthetic_ohlcv,
        config=default_config,
        verbose=False,
    )
    regime_df = build_regime_series(dates, states, labels)
    signal_df = build_signal(regime_df, labels, stats_df=stats_df, verbose=False)
    results_df, metrics = run_backtest(
        synthetic_ohlcv,
        signal_df,
        config=default_config,
        verbose=False,
    )

    assert model.n_components == default_config["n_states"]
    assert X.shape[0] == len(dates) == len(results_df)
    assert set(stats_df.index) == set(labels)
    assert results_df["signal"].isin({0, 1}).all()
    assert {"Strategy_total_return", "BuyHold_total_return"} <= set(metrics)
