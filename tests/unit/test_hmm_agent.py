"""
tests/unit/test_hmm_agent.py
==============================
Unit tests for HMMAgent and HMMAdapter.

Infrastructure stubs (aiokafka, redis, orjson, tenacity, …) are injected
by tests/unit/conftest.py before any test module is loaded, so the agent
classes can be imported without a running Kafka / Redis stack.

Covered cases:
  1. HMMAgent can be imported.
  2. HMMAgent has the correct tier (4) and agent_id (37).
  3. HMMAgent source does NOT reference live exchange/order-execution classes.
  4. Regime-to-signal mapping is correct for bullish / bearish / neutral labels.
  5. Confidence scoring: sideways = low; high-vol < low-vol.
  6. Missing HMM config falls back to defaults (HMMAdapterError NOT raised).
  7. Bad HMM_Trading root raises HMMAdapterError gracefully.
  8. ohlcv_bars_to_dataframe produces expected DataFrame shape and columns.
  9. Empty bar list raises HMMAdapterError.
  10. generate_signal returns None when the model is not ready.
  11. should_exit flips BUY→exit on BEARISH regime.
  12. should_exit does NOT exit BUY on BULLISH regime.
  13. should_exit flips SELL→exit on BULLISH regime.
  14. should_exit returns False when no regime has been inferred yet.
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

# ── Pure adapter imports (no agents.* chain) ─────────────────────────────────
from agents.tier4_strategies.hmm.adapter import (
    HMMAdapter,
    HMMAdapterError,
    regime_to_confidence,
    regime_to_signal_direction,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bar(*, close: float = 50_000.0, ts: datetime | None = None):
    """Return a minimal OHLCVBar-like mock."""
    bar = MagicMock()
    bar.is_closed = True
    bar.time = ts or datetime(2024, 1, 1, tzinfo=timezone.utc)
    bar.open   = Decimal(str(close * 0.99))
    bar.high   = Decimal(str(close * 1.01))
    bar.low    = Decimal(str(close * 0.98))
    bar.close  = Decimal(str(close))
    bar.volume = Decimal("1000")
    return bar


@contextmanager
def _patch_infra():
    """
    Patch Kafka / Redis / Prometheus constructors so HMMAgent.__init__
    doesn't actually connect to anything.
    """
    with (
        patch("agents.base_agent.AlghrestProducer", return_value=AsyncMock()),
        patch("agents.base_agent.state_manager", new=AsyncMock()),
        patch("agents.base_agent.start_metrics_server", return_value=None),
        patch("agents.base_agent.configure_logging", return_value=None),
    ):
        yield


# ── 1. Import ─────────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_hmm_agent_importable():
    from agents.tier4_strategies.hmm_agent import HMMAgent
    assert HMMAgent is not None


@pytest.mark.unit
def test_hmm_subpackage_importable():
    from agents.tier4_strategies.hmm import HMMAgent
    assert HMMAgent is not None


# ── 2. Tier and agent_id ──────────────────────────────────────────────────────

@pytest.mark.unit
def test_hmm_agent_class_constants():
    from agents.tier4_strategies.hmm_agent import HMMAgent
    assert HMMAgent.AGENT_ID == 37
    assert HMMAgent.strategy_id == "hmm_regime_detection"


@pytest.mark.unit
def test_hmm_agent_instance_tier():
    from agents.tier4_strategies.hmm_agent import HMMAgent
    with _patch_infra():
        agent = HMMAgent()
    assert agent.tier == 4
    assert agent.agent_id == 37


# ── 3. No live execution references ──────────────────────────────────────────

_AGENT_SRC = (
    Path(__file__).resolve().parents[2]
    / "agents" / "tier4_strategies" / "hmm" / "agent.py"
).read_text(encoding="utf-8")

_ADAPTER_SRC = (
    Path(__file__).resolve().parents[2]
    / "agents" / "tier4_strategies" / "hmm" / "adapter.py"
).read_text(encoding="utf-8")

_FORBIDDEN = ["ccxt", "exchange_executor", "binance_connector", "execute_order"]


@pytest.mark.unit
@pytest.mark.parametrize("keyword", _FORBIDDEN)
def test_agent_has_no_live_execution_keyword(keyword: str):
    assert keyword not in _AGENT_SRC, (
        f"agent.py must not contain '{keyword}' (no live execution)."
    )


@pytest.mark.unit
@pytest.mark.parametrize("keyword", _FORBIDDEN)
def test_adapter_has_no_live_execution_keyword(keyword: str):
    assert keyword not in _ADAPTER_SRC, (
        f"adapter.py must not contain '{keyword}'."
    )


# ── 4. Regime-to-signal mapping ───────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.parametrize("label, expected", [
    ("Bullish / Low-Vol",       "BULLISH"),
    ("Bullish / Moderate-Vol",  "BULLISH"),
    ("Bullish / High-Vol",      "BULLISH"),
    ("Bearish / Low-Vol",       "BEARISH"),
    ("Bearish / High-Vol",      "BEARISH"),
    ("Sideways / Moderate-Vol", "NEUTRAL"),
    ("Sideways / Low-Vol",      "NEUTRAL"),
    ("Unknown",                 "NEUTRAL"),
])
def test_regime_to_signal_direction(label: str, expected: str):
    assert regime_to_signal_direction(label) == expected


# ── 5. Confidence scoring ─────────────────────────────────────────────────────

@pytest.mark.unit
def test_sideways_confidence_is_low():
    assert regime_to_confidence("Sideways / Moderate-Vol") == pytest.approx(0.30)


@pytest.mark.unit
def test_high_vol_confidence_lower_than_low_vol():
    assert regime_to_confidence("Bullish / Low-Vol") > regime_to_confidence("Bullish / High-Vol")


@pytest.mark.unit
@pytest.mark.parametrize("label", [
    "Bullish / Low-Vol",
    "Bearish / High-Vol",
    "Sideways / Moderate-Vol",
    "Unknown",
])
def test_confidence_in_range(label: str):
    c = regime_to_confidence(label)
    assert 0.0 <= c <= 1.0, f"Out of range for '{label}': {c}"


# ── 6 & 7. Adapter config / error handling ────────────────────────────────────

@pytest.mark.unit
def test_missing_config_uses_defaults(tmp_path):
    """HMMAdapter falls back to built-in defaults when config file is absent."""
    adapter = HMMAdapter(config_path=tmp_path / "nonexistent.json")
    assert "n_states" in adapter.config
    assert "feature_cols" in adapter.config
    assert adapter.config["n_states"] > 0


@pytest.mark.unit
def test_bad_hmm_root_raises_adapter_error(tmp_path):
    """Pointing at a nonexistent HMM_Trading root → HMMAdapterError on use."""
    adapter = HMMAdapter(hmm_trading_root=tmp_path / "no_hmm_here")
    with pytest.raises(HMMAdapterError):
        adapter.load_data()


# ── 8 & 9. ohlcv_bars_to_dataframe ───────────────────────────────────────────

@pytest.mark.unit
def test_bars_to_dataframe_shape_and_columns():
    adapter = HMMAdapter()
    bars = [
        _make_bar(close=50_000.0 + i * 100,
                  ts=datetime(2024, 1, i + 1, tzinfo=timezone.utc))
        for i in range(5)
    ]
    df = adapter.ohlcv_bars_to_dataframe(bars)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert len(df) == 5
    assert df["close"].iloc[0] == pytest.approx(50_000.0, rel=1e-3)


@pytest.mark.unit
def test_empty_bars_raises_adapter_error():
    adapter = HMMAdapter()
    with pytest.raises(HMMAdapterError):
        adapter.ohlcv_bars_to_dataframe([])


# ── 10. generate_signal returns None when model not ready ─────────────────────

@pytest.mark.unit
def test_generate_signal_none_when_model_not_ready():
    from agents.tier4_strategies.hmm_agent import HMMAgent

    with _patch_infra():
        agent = HMMAgent()

    assert not agent._model_ready
    assert agent._last_regime is None

    result = asyncio.get_event_loop().run_until_complete(
        agent.generate_signal(MagicMock())
    )
    assert result is None


# ── 11-14. should_exit logic ──────────────────────────────────────────────────

def _make_agent_with_regime(regime: str):
    from agents.tier4_strategies.hmm_agent import HMMAgent
    with _patch_infra():
        agent = HMMAgent()
    agent._last_regime = regime
    agent._model_ready = True
    return agent


@pytest.mark.unit
def test_should_exit_buy_on_bearish_regime():
    from core.data.models import OrderSide
    agent = _make_agent_with_regime("Bearish / High-Vol")
    pos = MagicMock()
    pos.side = OrderSide.BUY
    result = asyncio.get_event_loop().run_until_complete(
        agent.should_exit(pos, MagicMock())
    )
    assert result is True


@pytest.mark.unit
def test_no_exit_buy_on_bullish_regime():
    from core.data.models import OrderSide
    agent = _make_agent_with_regime("Bullish / Low-Vol")
    pos = MagicMock()
    pos.side = OrderSide.BUY
    result = asyncio.get_event_loop().run_until_complete(
        agent.should_exit(pos, MagicMock())
    )
    assert result is False


@pytest.mark.unit
def test_should_exit_sell_on_bullish_regime():
    from core.data.models import OrderSide
    agent = _make_agent_with_regime("Bullish / Low-Vol")
    pos = MagicMock()
    pos.side = OrderSide.SELL
    result = asyncio.get_event_loop().run_until_complete(
        agent.should_exit(pos, MagicMock())
    )
    assert result is True


@pytest.mark.unit
def test_should_exit_false_when_no_regime():
    from core.data.models import OrderSide
    from agents.tier4_strategies.hmm_agent import HMMAgent
    with _patch_infra():
        agent = HMMAgent()  # _last_regime is None
    pos = MagicMock()
    pos.side = OrderSide.BUY
    result = asyncio.get_event_loop().run_until_complete(
        agent.should_exit(pos, MagicMock())
    )
    assert result is False
