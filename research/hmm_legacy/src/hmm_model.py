"""Hidden Markov Model training and regime interpretation."""

from __future__ import annotations

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM


def train_hmm(
    features: np.ndarray,
    n_components: int = 3,
    covariance_type: str = "full",
    random_state: int = 42,
    n_iter: int = 500,
) -> GaussianHMM:
    """Train a Gaussian HMM on scaled financial features."""

    model = GaussianHMM(
        n_components=n_components,
        covariance_type=covariance_type,
        random_state=random_state,
        n_iter=n_iter,
        verbose=False,
    )
    model.fit(features)
    return model


def predict_states(model: GaussianHMM, features: np.ndarray) -> np.ndarray:
    """Decode the most likely hidden state for each observation."""

    return model.predict(features)


def summarize_states(frame: pd.DataFrame, state_col: str = "hidden_state") -> pd.DataFrame:
    """Build a compact statistical profile for every inferred state."""

    summary = (
        frame.groupby(state_col)
        .agg(
            days=("daily_return", "size"),
            mean_return=("daily_return", "mean"),
            return_std=("daily_return", "std"),
            mean_volatility=("volatility", "mean"),
        )
        .reset_index()
        .rename(columns={state_col: "state"})
    )
    summary["interpretation"] = interpret_states(summary)
    return summary.sort_values("state").reset_index(drop=True)


def interpret_states(summary: pd.DataFrame) -> list[str]:
    """Label states using average return and volatility."""

    median_vol = summary["mean_volatility"].median()
    labels: list[str] = []
    for row in summary.itertuples(index=False):
        if row.mean_return > 0 and row.mean_volatility <= median_vol:
            labels.append("سوق صاعد منخفض أو متوسط التقلب")
        elif row.mean_return > 0 and row.mean_volatility > median_vol:
            labels.append("سوق صاعد عالي التقلب")
        elif row.mean_return <= 0 and row.mean_volatility > median_vol:
            labels.append("سوق هابط أو حالة ضغط عالي التقلب")
        else:
            labels.append("سوق جانبي أو دفاعي منخفض التقلب")
    return labels


def attach_states(frame: pd.DataFrame, states: np.ndarray) -> pd.DataFrame:
    output = frame.copy()
    output["hidden_state"] = states.astype(int)
    return output
