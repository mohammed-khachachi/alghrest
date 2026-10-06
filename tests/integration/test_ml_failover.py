"""
ALGHREST — ML Predictor Failover Integration Test
===============================================

This test validates ML Predictor Agent 16 failover mechanisms:
1. ML server health checks and circuit breaker
2. Fallback to technical analysis when ML server fails
3. Prediction caching during outages
4. Recovery when ML server comes back online

Test Scenarios:
- Healthy ML server: Normal ML predictions
- ML server timeout: Circuit breaker activation
- ML server errors: Fallback technical analysis
- Intermittent failures: Cache utilization
- Recovery: Automatic switchback to ML
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
import pytest

from agents.tier4_strategies.ml_predictor import MLPredictorAgent
from core.data.models import Exchange, OHLCVBar, Timeframe


class MockMLServer:
    """Mock ML inference server with controllable failure modes."""

    def __init__(self):
        self.mode = "healthy"
        self.error_rate = 0.0
        self.response_delay = 0.0
        self.request_count = 0

    async def predict(self, payload: dict) -> dict:
        """Simulate ML server prediction with different failure modes."""
        self.request_count += 1

        if self.mode == "timeout":
            await asyncio.sleep(15)  # Longer than agent timeout

        if self.mode == "error":
            raise httpx.HTTPStatusError(
                "Server Error", request=None, response=MagicMock(status_code=500)
            )

        if self.mode == "intermittent" and self.request_count % 3 == 0:
            raise httpx.HTTPStatusError(
                "Intermittent Error", request=None, response=MagicMock(status_code=500)
            )

        await asyncio.sleep(self.response_delay)

        # Return mock prediction
        return {
            "signal": "BULLISH",
            "confidence": 0.75,
            "recommended_risk_multiplier": 0.8,
            "source": "mock_ml_server",
            "model_version": "test-v1.0",
        }


@pytest.fixture
def mock_ml_server():
    """Mock ML server fixture."""
    return MockMLServer()


@pytest.fixture
def sample_ohlcv_data():
    """Generate sample OHLCV data for testing."""
    bars = []
    base_price = 50000.0
    base_time = datetime.utcnow() - timedelta(hours=64)

    for i in range(64):
        # Generate realistic OHLCV data
        price = base_price * (1 + 0.01 * np.sin(i * 0.1))  # Small price movements
        volume = 1000.0 * (1 + 0.5 * np.random.random())

        bar = OHLCVBar(
            time=base_time + timedelta(hours=i),
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
            open=Decimal(str(price * 0.999)),
            high=Decimal(str(price * 1.001)),
            low=Decimal(str(price * 0.998)),
            close=Decimal(str(price)),
            volume=Decimal(str(volume)),
            is_closed=True,
            exchange=Exchange.BINANCE,
        )
        bars.append(bar)

    return bars


@pytest.fixture
async def ml_predictor_agent():
    """ML Predictor agent with mocked dependencies."""
    agent = MLPredictorAgent()
    agent.state = AsyncMock()
    agent.producer = AsyncMock()
    agent.producer.initialize = AsyncMock()
    agent.producer.send = AsyncMock()

    # Mock Redis state for volatility/technical signals
    agent.state.get_json = AsyncMock(return_value=None)
    agent.state.is_kill_switch_active = AsyncMock(return_value=False)

    yield agent
    await agent.shutdown()


@pytest.mark.integration
class TestMLPredictorFailover:
    """Integration tests for ML Predictor failover functionality."""

    async def test_healthy_ml_server_prediction(
        self, ml_predictor_agent, mock_ml_server, sample_ohlcv_data
    ):
        """Test normal ML prediction when server is healthy."""

        # Mock successful HTTP response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "signal": "BULLISH",
            "confidence": 0.85,
            "recommended_risk_multiplier": 0.9,
            "source": "cnn_rl_model",
            "model_version": "v2.1",
        }

        with patch.object(
            ml_predictor_agent.http_client, "post", return_value=mock_response
        ) as mock_post:
            # Load sample data
            for bar in sample_ohlcv_data:
                ml_predictor_agent._bars[bar.symbol].append(bar)

            # Test ML prediction
            payload = {
                "symbol": "BTC/USDT",
                "ohlcv_window": [[50000, 50100, 49900, 50000, 1000]] * 64,
                "volatility": 0.25,
                "trend_strength": 0.6,
                "win_rate": 0.55,
            }

            prediction = await ml_predictor_agent._get_ml_prediction(payload)

            # Verify successful ML prediction
            assert prediction is not None
            assert prediction["signal"] == "BULLISH"
            assert prediction["confidence"] == 0.85
            assert prediction["source"] == "cnn_rl_model"
            assert mock_post.called
            assert ml_predictor_agent._ml_server_healthy is True
            assert ml_predictor_agent._ml_server_failures == 0

    async def test_ml_server_timeout_triggers_fallback(self, ml_predictor_agent, sample_ohlcv_data):
        """Test that ML server timeout triggers technical analysis fallback."""

        # Mock timeout exception
        with patch.object(
            ml_predictor_agent.http_client, "post", side_effect=httpx.TimeoutException("Timeout")
        ):
            # Load sample data
            for bar in sample_ohlcv_data:
                ml_predictor_agent._bars[bar.symbol].append(bar)

            payload = {
                "symbol": "BTC/USDT",
                "ohlcv_window": [
                    [
                        float(bar.open),
                        float(bar.high),
                        float(bar.low),
                        float(bar.close),
                        float(bar.volume),
                    ]
                    for bar in sample_ohlcv_data
                ],
                "volatility": 0.25,
                "trend_strength": 0.6,
                "win_rate": 0.55,
            }

            prediction = await ml_predictor_agent._get_ml_prediction(payload)

            # Verify fallback was used
            assert prediction is not None
            assert prediction["source"] == "fallback_technical"
            assert "indicators" in prediction
            assert ml_predictor_agent._ml_server_failures > 0

    async def test_circuit_breaker_activation(self, ml_predictor_agent, sample_ohlcv_data):
        """Test that circuit breaker activates after multiple failures."""

        # Load sample data
        for bar in sample_ohlcv_data:
            ml_predictor_agent._bars[bar.symbol].append(bar)

        payload = {
            "symbol": "BTC/USDT",
            "ohlcv_window": [[50000, 50100, 49900, 50000, 1000]] * 64,
            "volatility": 0.25,
            "trend_strength": 0.6,
            "win_rate": 0.55,
        }

        # Mock HTTP error
        with patch.object(
            ml_predictor_agent.http_client,
            "post",
            side_effect=httpx.HTTPStatusError(
                "Server Error",
                request=None,
                response=MagicMock(status_code=500, reason_phrase="Internal Server Error"),
            ),
        ):
            # Trigger multiple failures to activate circuit breaker
            for _i in range(4):  # More than _max_failures (3)
                prediction = await ml_predictor_agent._get_ml_prediction(payload)
                assert prediction["source"] == "fallback_technical"

            # Verify circuit breaker is active
            assert ml_predictor_agent._ml_server_healthy is False
            assert ml_predictor_agent._fallback_mode is True
            assert ml_predictor_agent._ml_server_failures >= 3

    async def test_prediction_caching_reduces_load(self, ml_predictor_agent, sample_ohlcv_data):
        """Test that successful predictions are cached to reduce ML server load."""

        # Load sample data
        for bar in sample_ohlcv_data:
            ml_predictor_agent._bars[bar.symbol].append(bar)

        mock_prediction = {
            "signal": "BULLISH",
            "confidence": 0.75,
            "recommended_risk_multiplier": 0.8,
            "source": "cnn_rl_model",
        }

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_prediction

        payload = {
            "symbol": "BTC/USDT",
            "ohlcv_window": [[50000, 50100, 49900, 50000, 1000]] * 64,
            "volatility": 0.25,
            "trend_strength": 0.6,
            "win_rate": 0.55,
        }

        with patch.object(
            ml_predictor_agent.http_client, "post", return_value=mock_response
        ) as mock_post:
            # First call - should hit ML server
            prediction1 = await ml_predictor_agent._get_ml_prediction(payload)
            assert mock_post.call_count == 1
            assert prediction1["signal"] == "BULLISH"

            # Second call immediately - should use cache
            prediction2 = await ml_predictor_agent._get_ml_prediction(payload)
            assert mock_post.call_count == 1  # No additional calls
            assert prediction2["signal"] == "BULLISH"

            # Verify cache contains the prediction
            assert "BTC/USDT" in ml_predictor_agent._ml_prediction_cache

    async def test_technical_analysis_fallback_accuracy(
        self, ml_predictor_agent, sample_ohlcv_data
    ):
        """Test that technical analysis fallback produces reasonable signals."""

        # Load trending data (prices going up)
        trending_bars = []
        base_price = 50000.0
        for i in range(64):
            price = base_price * (1 + i * 0.001)  # Gradual uptrend
            bar = OHLCVBar(
                time=datetime.utcnow() - timedelta(hours=64 - i),
                symbol="BTC/USDT",
                timeframe=Timeframe.H1,
                open=Decimal(str(price * 0.999)),
                high=Decimal(str(price * 1.002)),
                low=Decimal(str(price * 0.998)),
                close=Decimal(str(price)),
                volume=Decimal("1000.0"),
                is_closed=True,
                exchange=Exchange.BINANCE,
            )
            trending_bars.append(bar)

        # Load trending data into agent
        for bar in trending_bars:
            ml_predictor_agent._bars[bar.symbol].append(bar)

        payload = {
            "symbol": "BTC/USDT",
            "ohlcv_window": [
                [
                    float(bar.open),
                    float(bar.high),
                    float(bar.low),
                    float(bar.close),
                    float(bar.volume),
                ]
                for bar in trending_bars
            ],
            "volatility": 0.15,  # Low volatility
            "trend_strength": 0.8,  # Strong trend
            "win_rate": 0.60,
        }

        prediction = await ml_predictor_agent._fallback_technical_prediction(payload)

        # A monotonic rise has RSI=100: this fallback fades overbought prices.
        assert prediction["indicators"]["rsi"] == 100
        assert prediction["signal"] == "BEARISH"
        assert 0.2 <= prediction["confidence"] <= 0.7  # Reasonable confidence range
        assert 0.2 <= prediction["recommended_risk_multiplier"] <= 1.0
        assert prediction["source"] == "fallback_technical"
        assert "indicators" in prediction
        assert "rsi" in prediction["indicators"]

    async def test_ml_server_recovery_switches_back(self, ml_predictor_agent, sample_ohlcv_data):
        """Test that agent switches back to ML when server recovers."""

        # Load sample data
        for bar in sample_ohlcv_data:
            ml_predictor_agent._bars[bar.symbol].append(bar)

        payload = {
            "symbol": "BTC/USDT",
            "ohlcv_window": [[50000, 50100, 49900, 50000, 1000]] * 64,
            "volatility": 0.25,
            "trend_strength": 0.6,
            "win_rate": 0.55,
        }

        # Phase 1: Trigger circuit breaker with failures
        with patch.object(
            ml_predictor_agent.http_client,
            "post",
            side_effect=httpx.HTTPStatusError(
                "Server Error", request=None, response=MagicMock(status_code=500)
            ),
        ):
            for _i in range(4):  # Trigger circuit breaker
                prediction = await ml_predictor_agent._get_ml_prediction(payload)
                assert prediction["source"] == "fallback_technical"

        # Verify circuit breaker is active
        assert ml_predictor_agent._ml_server_healthy is False

        # Phase 2: Server recovers - should switch back to ML
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "signal": "BEARISH",
            "confidence": 0.8,
            "recommended_risk_multiplier": 0.7,
            "source": "recovered_ml_server",
        }

        # Simulate time passage for circuit breaker reset
        ml_predictor_agent._last_failure_time = 0  # Reset for immediate retry

        with patch.object(ml_predictor_agent.http_client, "post", return_value=mock_response):
            prediction = await ml_predictor_agent._get_ml_prediction(payload)

            # Verify switched back to ML server
            assert prediction["source"] == "recovered_ml_server"
            assert ml_predictor_agent._ml_server_healthy is True
            assert ml_predictor_agent._ml_server_failures == 0

    async def test_health_check_functionality(self, ml_predictor_agent):
        """Test ML server health check functionality."""

        # Test successful health check
        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(ml_predictor_agent.http_client, "post", return_value=mock_response):
            await ml_predictor_agent._check_ml_server_health()
            assert ml_predictor_agent._ml_server_healthy is True

        # Test failed health check
        with patch.object(
            ml_predictor_agent.http_client,
            "post",
            side_effect=httpx.HTTPStatusError(
                "Health check failed", request=None, response=MagicMock(status_code=503)
            ),
        ):
            await ml_predictor_agent._check_ml_server_health()
            assert ml_predictor_agent._ml_server_healthy is False

    async def test_initialize_with_unhealthy_server(self, ml_predictor_agent):
        """Test agent initialization when ML server is unhealthy."""

        with patch.object(
            ml_predictor_agent.http_client,
            "post",
            side_effect=httpx.ConnectError("Connection failed"),
        ):
            # Should not raise exception, just log warning
            await ml_predictor_agent.initialize()
            assert ml_predictor_agent._ml_server_healthy is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
