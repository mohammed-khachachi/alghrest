from pathlib import Path


REQUIRED_OUTPUT_FILES = [
    Path("outputs/results/hmm_regimes.csv"),
    Path("outputs/results/state_summary.csv"),
    Path("outputs/results/backtest_metrics.csv"),
    Path("outputs/results/transition_matrix.csv"),
    Path("outputs/figures/01_price_regimes.png"),
    Path("outputs/figures/02_equity_curves.png"),
    Path("outputs/figures/03_regime_distribution.png"),
    Path("outputs/figures/04_transition_matrix.png"),
]


def test_pipeline_outputs_exist(project_root):
    for relative_path in REQUIRED_OUTPUT_FILES:
        path = Path(project_root) / relative_path
        hint = f"Run `python main.py` from the HMM_Trading project root to generate {relative_path}."

        assert path.exists(), f"Missing pipeline output: {path}. {hint}"
        assert path.is_file(), f"Pipeline output is not a file: {path}. {hint}"
        assert path.stat().st_size > 0, f"Pipeline output is empty: {path}. {hint}"
