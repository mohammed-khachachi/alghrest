#!/usr/bin/env python3
"""
ALGHREST — Mock ML Inference Server
Simple FastAPI server that mocks the ML inference API for testing ML Predictor failover.
Provides both healthy and faulty modes to test circuit breaker functionality.
"""

import random
import time
from datetime import datetime

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


class PredictionRequest(BaseModel):
    symbol: str
    ohlcv_window: list[list[float]]  # 64 periods of [O,H,L,C,V]
    volatility: float
    trend_strength: float
    win_rate: float


class PredictionResponse(BaseModel):
    signal: str  # BULLISH, BEARISH, NEUTRAL
    confidence: float  # 0.0 to 1.0
    recommended_risk_multiplier: float  # 0.0 to 1.0
    source: str
    model_version: str
    processing_time_ms: int


app = FastAPI(
    title="ALGHREST ML Inference Server (Mock)",
    description="Mock ML inference server for testing ML Predictor failover",
    version="1.0.0",
)

# Server state for testing different scenarios
server_state = {
    "mode": "healthy",  # healthy, slow, error, intermittent
    "error_rate": 0.0,  # 0.0 to 1.0
    "response_delay": 0.0,  # seconds
    "requests_processed": 0,
    "start_time": time.time(),
}


@app.get("/")
async def root():
    """Health check endpoint."""
    uptime = int(time.time() - server_state["start_time"])
    return {
        "service": "ALGHREST ML Inference Server (Mock)",
        "status": "running",
        "mode": server_state["mode"],
        "uptime_seconds": uptime,
        "requests_processed": server_state["requests_processed"],
    }


@app.get("/health")
async def health_check():
    """Detailed health check."""
    if server_state["mode"] == "error":
        raise HTTPException(status_code=503, detail="Service unhealthy (error mode)")

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "mode": server_state["mode"],
        "error_rate": server_state["error_rate"],
        "response_delay": server_state["response_delay"],
    }


@app.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest):
    """Main ML prediction endpoint."""
    start_time = time.time()
    server_state["requests_processed"] += 1

    # Simulate different failure modes
    if server_state["mode"] == "error":
        raise HTTPException(status_code=500, detail="ML model inference failed")

    if server_state["mode"] == "intermittent" and random.random() < server_state["error_rate"]:
        raise HTTPException(status_code=500, detail="Intermittent failure")

    # Add artificial delay if configured
    if server_state["response_delay"] > 0:
        time.sleep(server_state["response_delay"])

    # Validate input
    if len(request.ohlcv_window) != 64:
        raise HTTPException(
            status_code=400, detail=f"Expected 64 OHLCV periods, got {len(request.ohlcv_window)}"
        )

    for i, bar in enumerate(request.ohlcv_window):
        if len(bar) != 5:
            raise HTTPException(
                status_code=400,
                detail=f"OHLCV bar {i} must have 5 values [O,H,L,C,V], got {len(bar)}",
            )

    # Generate mock prediction based on simple heuristics
    prediction = _generate_mock_prediction(request)

    processing_time = int((time.time() - start_time) * 1000)
    prediction["processing_time_ms"] = processing_time

    return PredictionResponse(**prediction)


@app.post("/admin/set_mode")
async def set_server_mode(mode: str, error_rate: float = 0.0, response_delay: float = 0.0):
    """Admin endpoint to change server behavior for testing."""
    valid_modes = ["healthy", "slow", "error", "intermittent"]
    if mode not in valid_modes:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {valid_modes}")

    server_state["mode"] = mode
    server_state["error_rate"] = max(0.0, min(1.0, error_rate))
    server_state["response_delay"] = max(0.0, response_delay)

    return {
        "message": f"Server mode set to '{mode}'",
        "mode": server_state["mode"],
        "error_rate": server_state["error_rate"],
        "response_delay": server_state["response_delay"],
    }


def _generate_mock_prediction(request: PredictionRequest) -> dict:
    """Generate a mock ML prediction using simple technical analysis."""

    # Extract recent price data
    ohlcv = request.ohlcv_window
    closes = [bar[3] for bar in ohlcv]  # Close prices
    volumes = [bar[4] for bar in ohlcv]  # Volumes

    # Simple trend detection
    short_ma = sum(closes[-10:]) / 10  # 10-period MA
    long_ma = sum(closes[-20:]) / 20  # 20-period MA
    closes[-1]

    # Price momentum
    price_change = (closes[-1] - closes[-5]) / closes[-5]  # 5-period change

    # Volume trend
    recent_vol = sum(volumes[-5:]) / 5
    avg_vol = sum(volumes) / len(volumes)
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0

    # Combine signals
    trend_signal = 0.0
    if short_ma > long_ma * 1.01:  # 1% above
        trend_signal += 0.4
    elif short_ma < long_ma * 0.99:  # 1% below
        trend_signal -= 0.4

    momentum_signal = min(0.5, max(-0.5, price_change * 10))

    # Volume confirmation
    volume_boost = min(0.2, (vol_ratio - 1.0) * 0.5)

    # Incorporate external signals
    volatility_penalty = request.volatility * 0.3  # Higher vol = lower confidence
    trend_strength_boost = (request.trend_strength - 0.5) * 0.3

    # Final signal calculation
    total_signal = trend_signal + momentum_signal + volume_boost + trend_strength_boost

    # Add some randomness to simulate ML model uncertainty
    noise = random.uniform(-0.1, 0.1)
    total_signal += noise

    # Generate prediction
    if total_signal > 0.3:
        signal = "BULLISH"
        confidence = min(0.95, 0.6 + abs(total_signal) * 0.7)
    elif total_signal < -0.3:
        signal = "BEARISH"
        confidence = min(0.95, 0.6 + abs(total_signal) * 0.7)
    else:
        signal = "NEUTRAL"
        confidence = 0.3 + random.uniform(0.0, 0.2)

    # Apply volatility penalty to confidence
    confidence = max(0.2, confidence - volatility_penalty)

    # Risk multiplier based on signal strength and volatility
    risk_mult = min(1.0, max(0.2, abs(total_signal) * (1.0 - request.volatility)))

    return {
        "signal": signal,
        "confidence": round(confidence, 3),
        "recommended_risk_multiplier": round(risk_mult, 3),
        "source": "mock_cnn_rl",
        "model_version": "mock-v1.0",
        "processing_time_ms": 0,  # Will be set by caller
    }


if __name__ == "__main__":
    print("🤖 Starting ALGHREST Mock ML Inference Server")
    print("=" * 50)
    print("📊 Endpoints:")
    print("  GET  /          - Service info")
    print("  GET  /health    - Health check")
    print("  POST /predict   - ML prediction")
    print("  POST /admin/set_mode - Change behavior (testing)")
    print()
    print("🧪 Test different modes:")
    print(
        "  curl -X POST http://localhost:8080/admin/set_mode -H 'Content-Type: application/json' -d '{\"mode\":\"error\"}'"
    )
    print(
        '  curl -X POST http://localhost:8080/admin/set_mode -H \'Content-Type: application/json\' -d \'{"mode":"intermittent", "error_rate":0.3}\''
    )
    print(
        '  curl -X POST http://localhost:8080/admin/set_mode -H \'Content-Type: application/json\' -d \'{"mode":"slow", "response_delay":5.0}\''
    )
    print(
        "  curl -X POST http://localhost:8080/admin/set_mode -H 'Content-Type: application/json' -d '{\"mode\":\"healthy\"}'"
    )
    print()
    print("🚀 Server starting on http://localhost:8080")
    print("=" * 50)

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
