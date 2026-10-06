"""Run the HMM market regime detection research project."""

from __future__ import annotations

from pathlib import Path

from src.backtest import run_regime_strategy
from src.data_loader import load_market_data
from src.features import build_features
from src.file_finder import (
    NO_STANFORD_PDF_MESSAGE,
    best_stanford_hmm_pdf,
    find_hmm_files,
    print_results,
)
from src.hmm_model import attach_states, predict_states, summarize_states, train_hmm
from src.visualization import plot_equity_curves, plot_price_regimes


PROJECT_ROOT = Path(__file__).resolve().parent
FIGURES_DIR = PROJECT_ROOT / "outputs" / "figures"
RESULTS_DIR = PROJECT_ROOT / "outputs" / "results"


def main() -> None:
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Checking optional references for a Stanford Hidden Markov Models PDF...")
    search_results = find_hmm_files(PROJECT_ROOT)
    print_results(search_results)
    selected_pdf = best_stanford_hmm_pdf(PROJECT_ROOT)
    if selected_pdf:
        print(f"Optional Stanford Hidden Markov Models PDF found: {selected_pdf.path}")
    elif search_results:
        print(NO_STANFORD_PDF_MESSAGE)

    ticker = "^GSPC"
    data = load_market_data(ticker=ticker, start="2015-01-01")
    features = build_features(data)

    model = train_hmm(features.matrix, n_components=3, covariance_type="full", random_state=42)
    states = predict_states(model, features.matrix)
    regime_frame = attach_states(features.frame, states)
    state_summary = summarize_states(regime_frame)

    backtest = run_regime_strategy(regime_frame, state_summary, transaction_cost=0.0005)

    state_summary_path = RESULTS_DIR / "state_summary.csv"
    regimes_path = RESULTS_DIR / "hmm_regimes.csv"
    metrics_path = RESULTS_DIR / "backtest_metrics.csv"

    state_summary.to_csv(state_summary_path, index=False, encoding="utf-8-sig")
    regime_frame.to_csv(regimes_path, index=True, encoding="utf-8-sig")
    backtest.metrics.to_csv(metrics_path, index=False, encoding="utf-8-sig")

    regime_plot = plot_price_regimes(
        regime_frame,
        FIGURES_DIR / "hmm_market_regimes.png",
        title=f"{ticker} - HMM Market Regimes",
    )
    equity_plot = plot_equity_curves(backtest.equity_frame, FIGURES_DIR / "hmm_backtest_equity.png")

    print("\nState summary:")
    print(state_summary.to_string(index=False))
    print("\nBacktest metrics:")
    print(backtest.metrics.to_string(index=False))
    print("\nSaved outputs:")
    print(f"- {state_summary_path}")
    print(f"- {regimes_path}")
    print(f"- {metrics_path}")
    print(f"- {regime_plot}")
    print(f"- {equity_plot}")
    print("\nEducational warning: this backtest is for research only, not financial advice.")


if __name__ == "__main__":
    main()
