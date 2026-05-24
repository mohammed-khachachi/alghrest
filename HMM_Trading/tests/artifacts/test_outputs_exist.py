from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

REQUIRED_OUTPUTS = [
    "outputs/results/hmm_regimes.csv",
    "outputs/results/state_summary.csv",
    "outputs/results/backtest_metrics.csv",
    "outputs/results/transition_matrix.csv",
    "outputs/results/run_config.json",
    "outputs/figures/01_price_regimes.png",
    "outputs/figures/02_equity_curves.png",
    "outputs/figures/03_regime_distribution.png",
    "outputs/figures/04_transition_matrix.png",
]


@pytest.mark.parametrize("filepath", REQUIRED_OUTPUTS)
def test_artifact_exists(filepath):
    full_path = PROJECT_ROOT / filepath
    assert full_path.exists(), f"Missing artifact: {filepath}"
    assert full_path.stat().st_size > 0, f"Empty artifact: {filepath}"
