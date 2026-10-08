"""
test_hmm_model.py
=================
Basic sanity tests for the HMM model module.
"""

import numpy as np
import pytest

from src.models.hmm import decode_states, get_model_summary, print_model_summary, train_hmm


def _make_synthetic_observations(n: int = 300, d: int = 5, seed: int = 42) -> np.ndarray:
    """Generate synthetic observation matrix with 2 underlying regimes."""
    np.random.seed(seed)
    # Regime 1: high mean, low vol
    X1 = np.random.randn(n // 2, d) * 0.5 + 0.5
    # Regime 2: low mean, high vol
    X2 = np.random.randn(n // 2, d) * 1.5 - 0.5
    X = np.vstack([X1, X2])
    # Shuffle a bit to simulate regime switching
    idx = np.argsort(np.random.rand(n))
    return X[idx]


class TestTrainHMM:

    def test_returns_fitted_model(self):
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=2, n_iter=50, verbose=False)
        assert model is not None

    def test_transition_matrix_rows_sum_to_one(self):
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=3, n_iter=50, verbose=False)
        row_sums = model.transmat_.sum(axis=1)
        np.testing.assert_allclose(row_sums, np.ones(3), atol=1e-6,
            err_msg="Each row of the transition matrix must sum to 1")

    def test_initial_probs_sum_to_one(self):
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=3, n_iter=50, verbose=False)
        np.testing.assert_allclose(model.startprob_.sum(), 1.0, atol=1e-6,
            err_msg="Initial state distribution must sum to 1")

    def test_correct_number_of_states(self):
        X = _make_synthetic_observations(200, 4)
        for n in [2, 3, 4]:
            model = train_hmm(X, n_states=n, n_iter=30, verbose=False)
            assert model.n_components == n


class TestDecodeStates:

    def test_states_same_length_as_input(self):
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=3, n_iter=50, verbose=False)
        states = decode_states(model, X, verbose=False)
        assert len(states) == len(X), \
            "Viterbi output must have same length as observation sequence"

    def test_states_are_valid_indices(self):
        n_states = 3
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=n_states, n_iter=50, verbose=False)
        states = decode_states(model, X, verbose=False)
        assert states.min() >= 0
        assert states.max() < n_states, \
            "All state indices must be in [0, n_states-1]"

    def test_all_states_appear(self):
        """With enough data and 3 states, all should appear at least once."""
        X = _make_synthetic_observations(500, 5)
        model = train_hmm(X, n_states=3, n_iter=100, verbose=False)
        states = decode_states(model, X, verbose=False)
        unique = set(states.tolist())
        assert len(unique) >= 2, "At least 2 distinct states should be decoded"


class TestModelSummary:

    def test_summary_has_required_keys(self):
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=3, n_iter=50, verbose=False)
        states = decode_states(model, X, verbose=False)
        summary = get_model_summary(model, states)
        for key in ["transition_matrix", "means", "state_counts", "initial_probs"]:
            assert key in summary, f"Missing key in model summary: {key}"

    def test_transition_matrix_shape(self):
        n = 3
        X = _make_synthetic_observations(300, 5)
        model = train_hmm(X, n_states=n, n_iter=50, verbose=False)
        states = decode_states(model, X, verbose=False)
        summary = get_model_summary(model, states)
        assert summary["transition_matrix"].shape == (n, n)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
