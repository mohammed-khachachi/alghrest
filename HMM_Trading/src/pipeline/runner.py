"""
Pipeline runner for the HMM Market Regime Detection workflow.

This module exposes the full HMM trading workflow as a callable function.
"""

import warnings

from src.core.paths import PROJECT_ROOT
from src.references.finder import find_repo_root, print_search_report
from src.references.extractor import extract_pdf_text
from src.data.loader import load_data
from src.models.features import compute_features, get_feature_matrix
from src.models.hmm import train_hmm, decode_states, get_model_summary, print_model_summary
from src.analysis.regime import interpret_regimes, build_regime_series
from src.analysis.backtest import build_signal, run_backtest
from src.reporting.visualization import generate_all_charts
from src.reporting.exporter import save_dataframe, save_metrics, save_json
from src.core.logging import section, log


ROOT = PROJECT_ROOT

warnings.filterwarnings("ignore")


def run(config: dict) -> dict:
    """Run the HMM trading pipeline and return a small result summary."""
    run_config = dict(config)

    print("\n" + "█" * 60)
    print("  HMM MARKET REGIME DETECTION")
    print("  Based on Stanford Hidden Markov Models Framework")
    print("█" * 60)

    # ──────────────────────────────────────────────────────────────
    # STEP 1: Locate Stanford HMM PDF
    # ──────────────────────────────────────────────────────────────
    section("STEP 1: Locating Stanford HMM PDF")
    repo_root = find_repo_root(ROOT)
    stanford_pdf = print_search_report(repo_root)

    # ──────────────────────────────────────────────────────────────
    # STEP 2: Extract theoretical content
    # ──────────────────────────────────────────────────────────────
    section("STEP 2: Extracting HMM Theoretical Content")
    hmm_text = extract_pdf_text(stanford_pdf)
    log(f"HMM theory content ready ({len(hmm_text):,} characters)")

    # Print a short conceptual summary
    print("\n[THEORY] Key HMM Concepts mapped to Trading:")
    print("  • Hidden State       → Market Regime (Bull/Bear/Sideways/High-Vol)")
    print("  • Observation        → Daily return, volatility, volume, MA ratio")
    print("  • Transition Matrix  → Probability of regime changes")
    print("  • Emission (Gaussian)→ Return distribution per regime")
    print("  • Viterbi Algorithm  → Best regime sequence over history")
    print("  • Baum-Welch (EM)    → Unsupervised learning from market data")

    # ──────────────────────────────────────────────────────────────
    # STEP 3: Download Market Data
    # ──────────────────────────────────────────────────────────────
    section(f"STEP 3: Downloading Market Data — {run_config['ticker']}")
    df = load_data(
        ticker=run_config["ticker"],
        start=run_config["start"],
        end=run_config["end"],
    )

    # ──────────────────────────────────────────────────────────────
    # STEP 4: Feature Engineering (Observations)
    # ──────────────────────────────────────────────────────────────
    section("STEP 4: Engineering HMM Observation Features")
    X, dates, scaler = get_feature_matrix(
        df,
        feature_cols=run_config["feature_cols"],
        config=run_config,
    )
    feat_df = compute_features(df, config=run_config).loc[dates]

    # ──────────────────────────────────────────────────────────────
    # STEP 5: Train HMM (Baum-Welch)
    # ──────────────────────────────────────────────────────────────
    section("STEP 5: Training Gaussian HMM (Baum-Welch / EM)")
    model = train_hmm(
        X,
        n_states=run_config["n_states"],
        covariance_type=run_config["covariance_type"],
        n_iter=run_config["n_iter"],
        random_state=run_config["random_state"],
    )

    # ──────────────────────────────────────────────────────────────
    # STEP 6: Decode States (Viterbi)
    # ──────────────────────────────────────────────────────────────
    section("STEP 6: Decoding Market Regimes (Viterbi Algorithm)")
    states = decode_states(model, X)
    print_model_summary(model, states, feature_names=run_config["feature_cols"])

    # ──────────────────────────────────────────────────────────────
    # STEP 7: Interpret Regimes
    # ──────────────────────────────────────────────────────────────
    section("STEP 7: Interpreting Market Regimes")
    stats_df, labels = interpret_regimes(feat_df, states, df, config=run_config)
    regime_df = build_regime_series(dates, states, labels)

    # ──────────────────────────────────────────────────────────────
    # STEP 8 & 9: Signal Generation + Backtest
    # ──────────────────────────────────────────────────────────────
    section("STEP 8-9: Generating Signals & Running Educational Backtest")
    signal_df = build_signal(
        regime_df, labels,
        transaction_cost=run_config["transaction_cost"],
        stats_df=stats_df,
    )
    results_df, metrics = run_backtest(
        df, signal_df,
        transaction_cost=run_config["transaction_cost"],
        config=run_config,
    )

    # ──────────────────────────────────────────────────────────────
    # STEP 10: Save Outputs
    # ──────────────────────────────────────────────────────────────
    section("STEP 10: Saving Results")

    # Transition matrix
    summary = get_model_summary(model, states, run_config["feature_cols"])
    trans_df = summary["transition_matrix"]
    save_dataframe(trans_df, "results", "transition_matrix.csv")

    # Regime states per day
    save_dataframe(regime_df, "results", "hmm_regimes.csv")

    # Regime statistics
    save_dataframe(stats_df, "results", "state_summary.csv")

    # Backtest results
    save_dataframe(results_df[["close", "signal", "regime_label",
                               "strat_equity", "bnh_equity"]],
                   "results", "backtest_results.csv")

    # Metrics
    save_metrics(metrics, "backtest_metrics.csv")

    # Config
    save_json(run_config, "run_config.json")

    # ──────────────────────────────────────────────────────────────
    # STEP 11: Generate Charts
    # ──────────────────────────────────────────────────────────────
    section("STEP 11: Generating Charts")
    generate_all_charts(
        df_price=df,
        regime_df=regime_df,
        labels=labels,
        stats_df=stats_df,
        results_df=results_df,
        trans_df=trans_df,
        ticker=run_config["ticker"],
    )

    # ──────────────────────────────────────────────────────────────
    # STEP 12: Final Terminal Report
    # ──────────────────────────────────────────────────────────────
    section("STEP 12: FINAL SUMMARY REPORT")
    strat_total = metrics["Strategy_total_return"] * 100
    bnh_total   = metrics["BuyHold_total_return"]   * 100
    strat_sharpe = metrics["Strategy_sharpe"]
    bnh_sharpe   = metrics["BuyHold_sharpe"]
    strat_dd     = metrics["Strategy_max_drawdown"] * 100
    bnh_dd       = metrics["BuyHold_max_drawdown"]  * 100

    print(f"""
  Ticker        : {run_config['ticker']}
  Period        : {run_config['start']} → {run_config['end']}
  HMM States    : {run_config['n_states']}
  Observations  : {len(X):,} trading days

  ┌─────────────────────────────────────────────────┐
  │              PERFORMANCE COMPARISON              │
  ├──────────────────────┬──────────────┬────────────┤
  │ Metric               │   Strategy   │ Buy & Hold │
  ├──────────────────────┼──────────────┼────────────┤
  │ Total Return         │  {strat_total:>9.1f}%  │ {bnh_total:>8.1f}%  │
  │ Sharpe Ratio         │  {strat_sharpe:>9.2f}   │ {bnh_sharpe:>8.2f}   │
  │ Max Drawdown         │  {strat_dd:>9.1f}%  │ {bnh_dd:>8.1f}%  │
  └──────────────────────┴──────────────┴────────────┘

  Market Regimes Detected:
""")
    for sid, lbl in labels.items():
        row = stats_df.loc[sid]
        print(f"    State {sid} [{lbl}]: "
              f"{row['pct_of_time']:.1f}% of time, "
              f"avg return {row['mean_daily_ret']*100:+.3f}%/day")

    print(f"""
  Output Files:
    outputs/results/hmm_regimes.csv
    outputs/results/state_summary.csv
    outputs/results/backtest_metrics.csv
    outputs/results/transition_matrix.csv
    outputs/figures/01_price_regimes.png
    outputs/figures/02_equity_curves.png
    outputs/figures/03_regime_distribution.png
    outputs/figures/04_transition_matrix.png
    outputs/theory/stanford_hmm_extracted.txt

  Report:
    reports/HMM_Trading_Report.md

  ⚠  DISCLAIMER: This is an educational research project.
     Results are in-sample and NOT financial advice.
""")

    print("█" * 60)
    print("  Pipeline completed successfully!")
    print("█" * 60)

    return {
        "status": "success",
        "n_observations": len(X),
        "n_states": run_config["n_states"],
        "regime_labels": labels,
        "metrics": metrics,
        "labels": labels,
    }
