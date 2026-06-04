"""
adapter.py — Lightweight bridge between ALGHREST and HMM_Trading.

Rules:
  - NEVER imports live-exchange or order-execution classes.
  - Adds HMM_Trading/  to sys.path ONLY within the context of load(),
    then cleans up.  No persistent sys.path mutation.
  - Falls back gracefully: if HMM_Trading is unavailable (missing deps,
    no data, …) it raises HMMAdapterError so the agent can log and skip.

Stable public API used by HMMAgent
-----------------------------------
    adapter = HMMAdapter(config_path, hmm_trading_root)
    df           = adapter.load_data()
    model, meta  = adapter.train(df)
    regime_label, confidence = adapter.detect_regime(model, df)

TODO (production hardening):
  - Cache the trained model on disk and reload on startup to avoid
    re-training every agent launch.
  - Add a scheduled weekly re-train instead of training on every startup.
  - Register this adapter in the central HMM registry once one exists.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locate HMM_Trading from *this* file's position so the path is always right
# regardless of the working directory.
# ---------------------------------------------------------------------------
_THIS_FILE = Path(__file__).resolve()
# agents/tier4_strategies/hmm/adapter.py  →  root = ../../../../
_ALGHREST_ROOT = _THIS_FILE.parents[3]
_HMM_TRADING_ROOT = _ALGHREST_ROOT / "HMM_Trading"
_DEFAULT_CONFIG = _HMM_TRADING_ROOT / "configs" / "default.json"


class HMMAdapterError(RuntimeError):
    """Raised when HMM_Trading integration fails; agent should log and skip."""


@contextlib.contextmanager
def _hmm_trading_on_path():
    """
    Temporarily add HMM_Trading/ to sys.path so that
    ``from src.models.hmm import ...`` resolves correctly.
    Removes the entry on exit to keep the global namespace clean.
    """
    root_str = str(_HMM_TRADING_ROOT)
    inserted = root_str not in sys.path
    if inserted:
        sys.path.insert(0, root_str)
    try:
        yield
    finally:
        if inserted and root_str in sys.path:
            sys.path.remove(root_str)


def _load_hmm_trading_functions():
    """
    Import the stable, reusable functions from HMM_Trading.
    Returns a namespace dict so callers can unpack only what they need.
    Raises HMMAdapterError if any import fails.
    """
    try:
        with _hmm_trading_on_path():
            from src.analysis.regime import (
                assign_regime_labels,
                compute_regime_stats,
            )
            from src.data.loader import load_data
            from src.models.features import compute_features, get_feature_matrix
            from src.models.hmm import decode_states, train_hmm
        return {
            "load_data": load_data,
            "compute_features": compute_features,
            "get_feature_matrix": get_feature_matrix,
            "train_hmm": train_hmm,
            "decode_states": decode_states,
            "compute_regime_stats": compute_regime_stats,
            "assign_regime_labels": assign_regime_labels,
        }
    except ImportError as exc:
        raise HMMAdapterError(
            f"HMM_Trading import failed — check that hmmlearn / yfinance "
            f"are installed and that HMM_Trading/ is at {_HMM_TRADING_ROOT}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Regime → ALGHREST signal helpers
# ---------------------------------------------------------------------------


def _parse_regime_label(label: str) -> tuple[str, str]:
    """
    Split a composite HMM_Trading label such as 'Bullish / Low-Vol'
    into (direction, vol_level).

    Returns
    -------
    direction : 'Bullish' | 'Bearish' | 'Sideways'
    vol_level : 'Low-Vol' | 'Moderate-Vol' | 'High-Vol' | 'Unknown'
    """
    parts = [p.strip() for p in label.split("/")]
    direction = parts[0] if parts else "Sideways"
    vol_level = parts[1] if len(parts) > 1 else "Unknown"
    return direction, vol_level


def regime_to_signal_direction(label: str) -> str:
    """
    Map a regime label to an ALGHREST SignalDirection value string.

    Bullish*  → 'BULLISH'
    Bearish*  → 'BEARISH'
    Sideways* → 'NEUTRAL'
    """
    direction, _ = _parse_regime_label(label)
    mapping = {
        "Bullish": "BULLISH",
        "Bearish": "BEARISH",
        "Sideways": "NEUTRAL",
    }
    return mapping.get(direction, "NEUTRAL")


def regime_to_confidence(label: str) -> float:
    """
    Derive a confidence score from the regime label.

    - Low-Vol Bullish/Bearish  → high confidence (0.75)
    - Moderate-Vol             → medium confidence (0.60)
    - High-Vol                 → lower confidence (0.45) because regime is noisier
    - Sideways                 → low confidence (0.30) — no-trade intent
    """
    direction, vol_level = _parse_regime_label(label)
    if direction == "Sideways":
        return 0.30

    vol_confidence = {
        "Low-Vol": 0.75,
        "Moderate-Vol": 0.60,
        "High-Vol": 0.45,
    }
    return vol_confidence.get(vol_level, 0.55)


# ---------------------------------------------------------------------------
# HMMAdapter
# ---------------------------------------------------------------------------


class HMMAdapter:
    """
    Thin adapter that delegates all HMM work to HMM_Trading functions
    while keeping the import footprint limited to this file.

    Parameters
    ----------
    config_path : Path or None
        Path to the HMM_Trading config JSON.
        Defaults to HMM_Trading/configs/default.json.
    hmm_trading_root : Path or None
        Override the auto-detected HMM_Trading root directory.
    """

    def __init__(
        self,
        config_path: Path | None = None,
        hmm_trading_root: Path | None = None,
    ) -> None:
        self._hmm_root = Path(hmm_trading_root) if hmm_trading_root else _HMM_TRADING_ROOT
        self._config_path = Path(config_path) if config_path else _DEFAULT_CONFIG
        self._config: dict[str, Any] = self._load_config()
        self._fns: dict | None = None  # lazy-loaded

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_config(self) -> dict[str, Any]:
        try:
            with open(self._config_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
            logger.debug("HMM config loaded from %s", self._config_path)
            return cfg
        except FileNotFoundError:
            logger.warning(
                "HMM config not found at %s — using built-in defaults.",
                self._config_path,
            )
            return self._default_config()

    @staticmethod
    def _default_config() -> dict[str, Any]:
        return {
            "ticker": "BTC-USD",
            "start": "2018-01-01",
            "end": "2024-12-31",
            "n_states": 3,
            "covariance_type": "full",
            "n_iter": 200,
            "random_state": 42,
            "feature_cols": [
                "log_return",
                "rolling_volatility",
                "ma_ratio",
                "volume_change",
                "intraday_range",
            ],
            "regime_thresholds": {
                "return_bullish": 0.0003,
                "return_bearish": -0.0003,
                "vol_low": 0.12,
                "vol_high": 0.22,
            },
            "rolling_vol_window": 20,
            "ma_fast_window": 10,
            "ma_slow_window": 50,
        }

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    # ── Lazy function loading ─────────────────────────────────────────────────

    def _get_fns(self) -> dict:
        if self._fns is None:
            self._fns = _load_hmm_trading_functions()
        return self._fns

    # ── Public API ────────────────────────────────────────────────────────────

    def load_data(
        self,
        ticker: str | None = None,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.DataFrame:
        """
        Download or generate OHLCV data via HMM_Trading's loader.
        Falls back to synthetic data if yfinance is unavailable.

        Returns a DataFrame with columns: open, high, low, close, volume.
        Raises HMMAdapterError on failure.
        """
        try:
            fns = self._get_fns()
            with _hmm_trading_on_path():
                df = fns["load_data"](
                    ticker=ticker or self._config.get("ticker", "BTC-USD"),
                    start=start or self._config.get("start", "2018-01-01"),
                    end=end or self._config.get("end", "2024-12-31"),
                    verbose=False,
                )
            logger.info(
                "HMM data loaded: %d rows (%s → %s)",
                len(df),
                df.index[0].date() if len(df) else "?",
                df.index[-1].date() if len(df) else "?",
            )
            return df
        except HMMAdapterError:
            raise
        except Exception as exc:
            raise HMMAdapterError(f"Data loading failed: {exc}") from exc

    def train(self, df: pd.DataFrame) -> tuple[Any, dict[str, Any]]:
        """
        Compute features and train the GaussianHMM on OHLCV data.

        Returns
        -------
        model : fitted GaussianHMM
        meta  : dict with 'states', 'dates', 'labels', 'stats_df', 'feature_cols'
        """
        try:
            fns = self._get_fns()
            with _hmm_trading_on_path():
                feature_matrix, dates, _scaler = fns["get_feature_matrix"](
                    df,
                    feature_cols=self._config.get("feature_cols"),
                    verbose=False,
                    config=self._config,
                )
                model = fns["train_hmm"](
                    feature_matrix,
                    n_states=self._config.get("n_states", 3),
                    covariance_type=self._config.get("covariance_type", "full"),
                    n_iter=self._config.get("n_iter", 200),
                    random_state=self._config.get("random_state", 42),
                    verbose=False,
                )
                states = fns["decode_states"](model, feature_matrix, verbose=False)
                feat_df = fns["compute_features"](df, verbose=False, config=self._config).loc[dates]
                stats_df = fns["compute_regime_stats"](feat_df, states, df)
                labels = fns["assign_regime_labels"](stats_df, config=self._config)

            logger.info(
                "HMM trained: %d states, %d observations. Regimes: %s",
                self._config.get("n_states", 3),
                len(feature_matrix),
                labels,
            )
            return model, {
                "states": states,
                "dates": dates,
                "labels": labels,
                "stats_df": stats_df,
                "feature_cols": self._config.get("feature_cols"),
                "scaler": _scaler,
                "X": feature_matrix,
            }
        except HMMAdapterError:
            raise
        except Exception as exc:
            raise HMMAdapterError(f"HMM training failed: {exc}") from exc

    def detect_regime(
        self,
        model: Any,
        df: pd.DataFrame,
        labels: dict[int, str],
    ) -> tuple[str, float, int]:
        """
        Infer the *current* market regime from the latest OHLCV window.

        Parameters
        ----------
        model  : fitted GaussianHMM (from train())
        df     : OHLCV DataFrame (recent bars, ≥ 60 rows recommended)
        labels : dict mapping state_id → regime label (from train())

        Returns
        -------
        regime_label : human-readable label, e.g. 'Bullish / Low-Vol'
        confidence   : float [0, 1]
        state_id     : raw HMM state integer
        """
        try:
            fns = self._get_fns()
            with _hmm_trading_on_path():
                feature_matrix, _, _ = fns["get_feature_matrix"](
                    df,
                    feature_cols=self._config.get("feature_cols"),
                    verbose=False,
                    config=self._config,
                )
                if len(feature_matrix) == 0:
                    raise HMMAdapterError("No valid feature rows after warm-up — need more data.")

                # Use model.predict for the current-regime assignment
                # (posterior decoding; lighter than full Viterbi on a long sequence)
                current_state = int(model.predict(feature_matrix)[-1])

            regime_label = labels.get(current_state, "Unknown")
            confidence = regime_to_confidence(regime_label)
            return regime_label, confidence, current_state

        except HMMAdapterError:
            raise
        except Exception as exc:
            raise HMMAdapterError(f"Regime detection failed: {exc}") from exc

    def ohlcv_bars_to_dataframe(self, bars: list) -> pd.DataFrame:
        """
        Convert a list of ALGHREST OHLCVBar objects to a plain DataFrame
        compatible with HMM_Trading feature functions.

        Parameters
        ----------
        bars : list[OHLCVBar]  — from the agent's rolling bar buffer

        Returns
        -------
        pd.DataFrame with DatetimeIndex and columns:
            open, high, low, close, volume
        """
        if not bars:
            raise HMMAdapterError("Cannot convert empty bar list to DataFrame.")

        records = [
            {
                "time": b.time,
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": float(b.volume),
            }
            for b in bars
        ]
        df = pd.DataFrame(records).set_index("time").sort_index()
        df.index = pd.DatetimeIndex(df.index)
        return df
