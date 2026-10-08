"""Numerical invariants and event handling of the production quant agents."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from agents.tier3_quant import (
    correlation_engine as correlation,
    technical_analyst as technical,
    volatility_forecaster as volatility,
)
from core.data.models import Timeframe, VolatilityRegime
from tests.factories import FiniteConsumer, bar

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "ind,indicator,direction",
    [
        ({"RSI_14": 20}, "RSI", "BULLISH"),
        ({"RSI_14": 80}, "RSI", "BEARISH"),
        ({"MACDh_12_26_9": 1, "MACDh_12_26_9_prev": -1}, "MACD_CROSS", "BULLISH"),
        ({"MACDh_12_26_9": -1, "MACDh_12_26_9_prev": 1}, "MACD_CROSS", "BEARISH"),
        ({"BBU_20_2.0": 120, "BBL_20_2.0": 106}, "BBANDS_LOWER", "BULLISH"),
        ({"BBU_20_2.0": 104, "BBL_20_2.0": 90}, "BBANDS_UPPER", "BEARISH"),
        ({"STOCHk_14_3_3": 0, "STOCHd_14_3_3": 0}, "STOCH", "BULLISH"),
        ({"STOCHk_14_3_3": 90, "STOCHd_14_3_3": 90}, "STOCH", "BEARISH"),
        (
            {"EMA_20": 110, "EMA_50": 100, "EMA_20_prev": 90, "EMA_50_prev": 100},
            "EMA_GOLDEN_CROSS",
            "STRONG_BULLISH",
        ),
        (
            {"EMA_20": 90, "EMA_50": 100, "EMA_20_prev": 110, "EMA_50_prev": 100},
            "EMA_DEATH_CROSS",
            "STRONG_BEARISH",
        ),
        ({"ADX_14": 40, "DMP_14": 40, "DMN_14": 20}, "ADX_TREND", "BULLISH"),
        ({"ADX_14": 40, "DMP_14": 20, "DMN_14": 40}, "ADX_TREND", "BEARISH"),
        ({"CCI_14_0.015": -150}, "CCI", "BULLISH"),
        ({"CCI_14_0.015": 150}, "CCI", "BEARISH"),
    ],
)
def test_indicator_extremes_and_crossovers(ind, indicator, direction):
    agent = technical.TechnicalAnalyst()
    agent._compute_indicators = MagicMock(return_value=ind)
    signals = agent._compute_and_detect(pd.DataFrame({"close": [105]}), "BTC/USDT", "1h")
    assert len(signals) == 1
    assert signals[0].indicator == indicator and signals[0].direction.value == direction
    assert 0 <= signals[0].confidence <= 1


@pytest.mark.parametrize(
    "ind",
    [{}, {"RSI_14": float("nan")}, {"RSI_14": 50, "MACDh_12_26_9": 0, "MACDh_12_26_9_prev": 0}],
)
def test_no_signal_for_missing_nan_or_neutral_values(ind):
    agent = technical.TechnicalAnalyst()
    agent._compute_indicators = MagicMock(return_value=ind)
    assert agent._compute_and_detect(pd.DataFrame({"close": [100]}), "BTC/USDT", "1h") == []
    agent._compute_indicators.side_effect = ValueError("invalid series")
    assert agent._compute_and_detect(pd.DataFrame({"close": [100]}), "BTC/USDT", "1h") == []


def test_current_pandas_ta_computes_indicators_and_previous_values():
    agent = technical.TechnicalAnalyst()
    x = 100 + np.arange(250) * 0.1 + np.sin(np.arange(250))
    df = pd.DataFrame(
        {"open": x, "high": x + 2, "low": x - 2, "close": x, "volume": 1000},
        index=pd.date_range("2025-01-01", periods=250),
    )
    result = agent._compute_indicators(df)
    assert 0 <= result["RSI_14"] <= 100
    assert result["EMA_20"] > result["EMA_50"]
    assert "MACDh_12_26_9_prev" in result
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]


async def test_technical_stream_filters_and_deduplicates_bars(monkeypatch):
    agent = technical.TechnicalAnalyst()
    with pytest.raises(RuntimeError):
        await agent.run()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = False
    agent.publish = AsyncMock()
    monkeypatch.setattr(technical, "MIN_BARS", 2)
    expected = agent._make_signal(
        "BTC/USDT", "1h", "RSI", 20, technical.SignalDirection.BULLISH, 0.7
    )
    agent._compute_and_detect = MagicMock(return_value=[expected])
    now = datetime.utcnow()
    candles = [bar(time=now), bar(time=now, close=106), bar(time=now + timedelta(hours=1))]
    consumer = FiniteConsumer(
        [
            {"message_type": "other"},
            {"message_type": "ohlcv", "payload": {}},
            *[
                {"message_type": "ohlcv", "payload": value.model_dump(mode="json")}
                for value in candles
            ],
            {"message_type": "ohlcv", "payload": bar(is_closed=False).model_dump(mode="json")},
            {
                "message_type": "ohlcv",
                "payload": bar(timeframe=Timeframe.M1).model_dump(mode="json"),
            },
        ]
    )
    monkeypatch.setattr(agent, "make_consumer", lambda *a, **kw: consumer)
    await agent.initialize()
    await agent.run()
    assert len(agent._bars[("BTC/USDT", "1h")]) == 2
    assert agent.publish.await_count == 1
    await agent.shutdown()
    consumer.shutdown.assert_awaited_once()


@pytest.mark.parametrize(
    "value,regime", [(0.05, "CALM"), (0.15, "NORMAL"), (0.3, "VOLATILE"), (0.6, "CRISIS")]
)
def test_volatility_regime_uses_fractional_units(value, regime):
    assert volatility.VolatilityForecaster._classify_regime(value).value == regime


def test_realized_and_forecast_volatility_share_units():
    agent = volatility.VolatilityForecaster()
    prices = 100 * np.exp(np.cumsum(np.random.default_rng(4).normal(0, 0.01, 100)))
    agent._fit_garch = MagicMock(return_value=0.15)
    agent._fit_egarch = MagicMock(return_value=0.16)
    signal = agent._compute_volatility_signal("BTC/USDT", prices.tolist())
    assert signal is not None
    assert signal.realized_vol_30d == pytest.approx(
        np.diff(np.log(prices))[-30:].std() * np.sqrt(252)
    )
    assert signal.realized_vol_1d > 0
    assert signal.forecast_1d == 0.15
    agent._fit_egarch.assert_not_called()
    assert agent._compute_volatility_signal("BTC/USDT", [100] * 5) is None
    agent._fit_garch.side_effect = ValueError("bad data")
    assert agent._compute_volatility_signal("BTC/USDT", prices.tolist()) is None


@pytest.mark.parametrize("method", ["_fit_garch", "_fit_egarch"])
def test_garch_forecast_converts_variance_and_handles_failure(monkeypatch, method):
    factory = MagicMock()
    factory.return_value.fit.return_value.forecast.return_value.variance.values = np.array([[4.0]])
    monkeypatch.setattr(volatility, "arch_model", factory)
    compute = getattr(volatility.VolatilityForecaster, method)
    assert compute(np.ones(100)) == pytest.approx(2 * np.sqrt(252) / 100)
    factory.side_effect = RuntimeError("convergence")
    assert compute(np.ones(100)) is None


@pytest.mark.parametrize(
    "regime,long,short,direction",
    [
        ("CRISIS", 0.5, 0.5, "STRONG_BEARISH"),
        ("VOLATILE", 0.3, 0.3, "BEARISH"),
        ("NORMAL", 0.2, 0.3, "BEARISH"),
        ("CALM", 0.1, 0.05, "BULLISH"),
        ("NORMAL", 0.2, 0.2, "NEUTRAL"),
    ],
)
def test_volatility_direction(regime, long, short, direction):
    assert (
        volatility.VolatilityForecaster._regime_to_direction(
            VolatilityRegime(regime), long, short
        ).value
        == direction
    )


def test_hurst_handles_short_constant_and_variable_histories():
    compute = volatility.VolatilityForecaster._hurst_exponent
    assert compute(np.ones(5)) is None
    assert compute(np.ones(100)) is None
    assert 0 <= compute(np.random.default_rng(4).normal(size=200)) <= 1


async def test_correlation_daily_ingestion_replaces_same_day_and_filters(monkeypatch):
    agent = correlation.CorrelationEngine()
    with pytest.raises(RuntimeError):
        await agent._price_collection_loop()
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = False
    now = datetime.utcnow()
    candles = [
        bar(time=now, timeframe=Timeframe.D1),
        bar(time=now, timeframe=Timeframe.D1, close=106),
        bar(),
    ]
    consumer = FiniteConsumer(
        [
            {"message_type": "other"},
            {"message_type": "ohlcv", "payload": {}},
            *[{"message_type": "ohlcv", "payload": b.model_dump(mode="json")} for b in candles],
        ]
    )
    monkeypatch.setattr(agent, "make_consumer", lambda *a, **kw: consumer)
    await agent.initialize()
    await agent._price_collection_loop()
    assert agent._daily_prices["BTC/USDT"] == [(now, 106)]
    await agent.shutdown()


def test_correlation_aligns_dates_and_detects_concentrated_exposure(monkeypatch):
    agent = correlation.CorrelationEngine()
    assert agent._compute_all_correlations() is None
    dates = pd.date_range("2025-01-01", periods=100)
    prices = np.exp(np.cumsum(np.random.default_rng(3).normal(0, 0.01, 100))) * 100
    agent._daily_prices["BTC/USDT"] = list(zip(dates, prices, strict=True))
    agent._daily_prices["ETH/USDT"] = list(zip(dates, prices * 2, strict=True))
    agent._test_cointegration = MagicMock(return_value=5)
    result = agent._compute_all_correlations()
    assert result.correlation_matrix["BTC/USDT"]["ETH/USDT"] == pytest.approx(1)
    assert len(result.high_correlation_pairs) == 1
    assert result.effective_n == pytest.approx(1)
    assert result.cointegrated_pairs
    agent._daily_prices["ETH/USDT"] = list(zip(dates + pd.Timedelta(days=200), prices, strict=True))
    assert agent._compute_all_correlations() is None


def test_effective_bet_count_and_cointegration_failure(monkeypatch):
    compute = correlation.CorrelationEngine._compute_effective_n
    assert compute(np.ones((20, 1))) == 1
    assert compute(np.random.default_rng(2).normal(size=(10000, 3))) == pytest.approx(3, abs=0.02)
    monkeypatch.setattr(correlation, "coint", lambda *a: (0, 0.9, []))
    assert correlation.CorrelationEngine._test_cointegration(np.arange(100), np.arange(100)) is None
    monkeypatch.setattr(correlation, "coint", MagicMock(side_effect=ValueError("invalid")))
    assert correlation.CorrelationEngine._test_cointegration(np.arange(100), np.arange(100)) is None
