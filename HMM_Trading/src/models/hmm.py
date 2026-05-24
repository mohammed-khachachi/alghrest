"""
hmm_model.py
============
Trains and evaluates a Gaussian Hidden Markov Model on market data.

Theoretical grounding (Stanford HMM / Rabiner 1989):
------------------------------------------------------
  - GaussianHMM solves Problem 3 (Learning) via Baum-Welch (EM).
  - After training, it solves Problem 2 (Decoding) via Viterbi.
  - The model is fully unsupervised: no regime labels are provided.

Key parameters:
  n_components    — number of hidden states (market regimes)
  covariance_type — "full" allows full covariance between features
  n_iter          — Baum-Welch EM iterations
  random_state    — reproducibility seed
"""

import numpy as np
import pandas as pd
import warnings
from typing import Tuple, Dict, Optional

from hmmlearn.hmm import GaussianHMM


def train_hmm(
    X: np.ndarray,
    n_states: int = 3,
    covariance_type: str = "full",
    n_iter: int = 200,
    random_state: int = 42,
    verbose: bool = True,
) -> GaussianHMM:
    """
    Train a Gaussian HMM on observation matrix X.

    This implements Baum-Welch (Expectation-Maximization) to learn:
      - π  : initial state distribution
      - A  : transition probability matrix (n_states × n_states)
      - B  : Gaussian emission distributions (μ_i, Σ_i) for each state i

    Parameters
    ----------
    X               : np.ndarray (T, n_features)  — observation matrix
    n_states        : int  — number of hidden market regimes
    covariance_type : str  — 'full', 'diag', 'tied', 'spherical'
    n_iter          : int  — maximum Baum-Welch iterations
    random_state    : int  — random seed for reproducibility

    Returns
    -------
    Fitted GaussianHMM model
    """
    if verbose:
        print(f"\n[HMM] Training GaussianHMM:")
        print(f"      n_states        = {n_states}")
        print(f"      covariance_type = {covariance_type}")
        print(f"      n_iter          = {n_iter}")
        print(f"      observations    = {X.shape[0]:,}  (trading days)")
        print(f"      features        = {X.shape[1]}  (per observation)")

    model = GaussianHMM(
        n_components=n_states,
        covariance_type=covariance_type,
        n_iter=n_iter,
        random_state=random_state,
        verbose=False,
    )

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model.fit(X)

    if verbose:
        score = model.score(X)
        print(f"[HMM] Training complete.")
        print(f"[HMM] Log-likelihood on training data: {score:.2f}")
        if hasattr(model, 'monitor_') and model.monitor_:
            converged = model.monitor_.converged
            iters = len(model.monitor_.history)
            print(f"[HMM] Converged: {converged}  (after {iters} iterations)")

    return model


def decode_states(
    model: GaussianHMM,
    X: np.ndarray,
    verbose: bool = True
) -> np.ndarray:
    """
    Apply Viterbi algorithm to find the most likely hidden state sequence.

    From Stanford HMM theory (Problem 2 — Decoding):
      Q* = argmax_{Q} P(Q | O, λ)
    where Q* is the optimal sequence of hidden market regimes.

    Parameters
    ----------
    model : fitted GaussianHMM
    X     : np.ndarray (T, n_features)

    Returns
    -------
    np.ndarray of shape (T,) — predicted state index for each day
    """
    log_prob, states = model.decode(X, algorithm="viterbi")
    if verbose:
        print(f"[VITERBI] Decoded {len(states):,} states. "
              f"Log P(O|λ) = {log_prob:.2f}")
    return states


def get_model_summary(
    model: GaussianHMM,
    states: np.ndarray,
    feature_names: list = None,
) -> Dict:
    """
    Extract and return model parameters in a structured dictionary.

    Returns
    -------
    dict with keys:
      'transition_matrix'  : DataFrame (n_states × n_states)
      'means'              : DataFrame of emission means
      'state_counts'       : Series — number of days per state
      'initial_probs'      : array  — π vector
      'log_likelihood'     : float
    """
    n = model.n_components
    feature_names = feature_names or [f"feature_{i}" for i in range(model.n_features)]

    # Transition matrix A
    trans_df = pd.DataFrame(
        model.transmat_,
        index=[f"State_{i}" for i in range(n)],
        columns=[f"State_{i}" for i in range(n)]
    )

    # Emission means
    means_df = pd.DataFrame(
        model.means_,
        index=[f"State_{i}" for i in range(n)],
        columns=feature_names
    )

    # State frequency counts
    state_counts = pd.Series(states).value_counts().sort_index()
    state_counts.index = [f"State_{i}" for i in state_counts.index]

    return {
        "transition_matrix": trans_df,
        "means": means_df,
        "state_counts": state_counts,
        "initial_probs": model.startprob_,
        "log_likelihood": model.score(X) if False else None,  # avoid re-scoring here
        "n_states": n,
        "covariance_type": model.covariance_type,
    }


def print_model_summary(model: GaussianHMM, states: np.ndarray, feature_names: list = None) -> None:
    """Print a formatted model summary to stdout."""
    summary = get_model_summary(model, states, feature_names)
    n = summary["n_states"]

    print("\n" + "=" * 60)
    print("  HMM MODEL SUMMARY")
    print("=" * 60)

    print(f"\n[INITIAL STATE DISTRIBUTION π]")
    for i, p in enumerate(summary["initial_probs"]):
        print(f"  State_{i}: {p:.4f}")

    print(f"\n[TRANSITION MATRIX A]")
    print(summary["transition_matrix"].to_string())

    print(f"\n[EMISSION MEANS]")
    print(summary["means"].to_string())

    print(f"\n[STATE FREQUENCY]")
    total = summary["state_counts"].sum()
    for state, cnt in summary["state_counts"].items():
        print(f"  {state}: {cnt:,} days  ({100*cnt/total:.1f}%)")

    print("=" * 60)


if __name__ == "__main__":
    from src.data.loader import download_data
    from src.models.features import get_feature_matrix

    df = download_data("^GSPC", "2015-01-01", "2023-12-31")
    X_data, dates, scaler = get_feature_matrix(df)
    model = train_hmm(X_data, n_states=3)
    states = decode_states(model, X_data)
    print_model_summary(model, states)
