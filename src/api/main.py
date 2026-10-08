"""
ALGHREST — FastAPI Application
REST + WebSocket API for the dashboard and external integrations.
Prometheus metrics exposed at /metrics.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from api.routes.quotes import router as quotes_router
from api.security import AccessTokenMiddleware
from api.websockets.dashboard_ws import dashboard_websocket_endpoint, start_background_loops
from core.config import settings
from core.orchestrator.state_manager import state_manager
from core.telegram.bot_manager import telegram_bot
from core.utils.logging import configure_logging

configure_logging(settings.log_level, settings.environment)
try:
    from core.kafka.metrics_collector import make_kafka_metrics_collector
    from core.kafka.pnl_history_writer import pnl_history_writer

    _KAFKA_AVAILABLE = True
except ImportError:
    make_kafka_metrics_collector = None  # type: ignore[assignment]
    pnl_history_writer = None  # type: ignore[assignment]
    _KAFKA_AVAILABLE = False

logger = structlog.get_logger(__name__)

# ── WEBSOCKET CONNECTION MANAGER ─────────────────────────────────────────────


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections = [c for c in self._connections if c != ws]

    async def broadcast(self, data: dict[str, Any]) -> None:
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = ConnectionManager()


# ── APPLICATION LIFECYCLE ─────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    settings.require_order_execution()
    logger.info("ALGHREST API starting", environment=settings.environment)

    await state_manager.initialize()
    logger.info("state manager connected")

    tasks = await start_background_loops()
    try:
        if _KAFKA_AVAILABLE:
            kafka_collector = make_kafka_metrics_collector(state_manager.redis)
            tasks.append(asyncio.create_task(kafka_collector.run(), name="kafka-metrics-collector"))
            tasks.append(asyncio.create_task(pnl_history_writer.run(), name="pnl-history-writer"))
        else:
            logger.warning("Kafka dependencies unavailable; monitoring collectors disabled")

        telegram_bot.attach_redis(state_manager.redis)
        tasks.append(asyncio.create_task(telegram_bot.start(), name="telegram-bot"))
        logger.info("background tasks started")
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await telegram_bot.stop()
        finally:
            await state_manager.shutdown()
        logger.info("ALGHREST API shutdown")


# ── APP INSTANCE ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="ALGHREST Trading System API",
    description="32-agent autonomous trading system — REST + WebSocket API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.api_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(AccessTokenMiddleware, service="api")


app.include_router(quotes_router)


@app.get("/health/live", include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


# ── HEALTH ENDPOINTS ──────────────────────────────────────────────────────────


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    kill_switch_active = await state_manager.is_kill_switch_active()
    return {
        "status": "degraded" if kill_switch_active else "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "kill_switch_active": kill_switch_active,
        "environment": settings.environment,
        "version": "0.1.0",
    }


@app.get("/health/ready", tags=["System"])
async def readiness_check() -> dict:
    """Kubernetes readiness probe."""
    try:
        await state_manager.redis.ping()
        return {"ready": True}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {e}") from e


@app.get("/metrics", tags=["System"])
async def prometheus_metrics() -> Response:
    """Prometheus scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ── PORTFOLIO ENDPOINTS ───────────────────────────────────────────────────────


@app.get("/api/v1/portfolio", response_model=None, tags=["Portfolio"])
async def get_portfolio() -> dict:
    """Current portfolio state — positions, capital, PnL."""
    portfolio = await state_manager.get_portfolio()
    if not portfolio:
        return {
            "message": "Portfolio data not yet available — system may be initializing",
            "snapshot_time": datetime.utcnow().isoformat(),
        }
    return portfolio.model_dump(mode="json")


@app.get("/api/v1/portfolio/positions", tags=["Portfolio"])
async def get_positions() -> dict:
    portfolio = await state_manager.get_portfolio()
    if not portfolio:
        return {"positions": []}
    return {
        "positions": [p.model_dump(mode="json") for p in portfolio.positions],
        "count": len(portfolio.positions),
        "total_exposure_usd": float(portfolio.total_exposure_usd),
    }


# ── RISK ENDPOINTS ────────────────────────────────────────────────────────────


@app.get("/api/v1/risk", response_model=None, tags=["Risk"])
async def get_risk_metrics() -> dict:
    """Current risk metrics snapshot from CRO agent."""
    metrics = await state_manager.get_risk_metrics()
    if not metrics:
        return {"message": "Risk metrics not yet available"}
    return metrics.model_dump(mode="json")


@app.get("/api/v1/risk/kill-switch", tags=["Risk"])
async def get_kill_switch_status() -> dict:
    active = await state_manager.is_kill_switch_active()
    reason = await state_manager.get_kill_switch_reason() if active else None
    return {"active": active, "reason": reason}


# ── AGENT ENDPOINTS ───────────────────────────────────────────────────────────


@app.get("/api/v1/agents", tags=["Agents"])
async def get_all_agents() -> dict:
    """Health status of all 32 agents."""
    healths = await state_manager.get_all_agent_healths()
    return {
        "agents": [h.model_dump(mode="json") for h in healths],
        "total": len(healths),
        "running": sum(1 for h in healths if h.status.value == "RUNNING"),
        "errors": sum(1 for h in healths if h.status.value == "ERROR"),
    }


@app.get("/api/v1/agents/{agent_id}", tags=["Agents"])
async def get_agent_health(agent_id: int) -> dict:
    health = await state_manager.get_agent_health(agent_id)
    if not health:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found or not reporting")
    return health.model_dump(mode="json")


# ── SIGNALS ENDPOINTS ─────────────────────────────────────────────────────────


@app.get("/api/v1/signals/sentiment/{symbol}", tags=["Signals"])
async def get_sentiment(symbol: str) -> dict:
    """Latest sentiment signal for a symbol."""
    cached = await state_manager.get_cached_signal(symbol.upper(), "sentiment")
    if not cached:
        return {"symbol": symbol, "message": "No sentiment data available"}
    return {"symbol": symbol, **cached}


@app.get("/api/v1/signals/macro", tags=["Signals"])
async def get_macro_regime() -> dict:
    """Current macro regime classification."""
    cached = await state_manager.get_cached_signal("GLOBAL", "macro_regime")
    if not cached:
        return {"message": "Macro regime not yet computed"}
    return cached


# ── WEBSOCKET — LIVE FEED ─────────────────────────────────────────────────────


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket) -> None:
    await dashboard_websocket_endpoint(websocket)


@app.websocket("/ws/live")
async def websocket_live_feed(websocket: WebSocket) -> None:
    """
    Real-time dashboard feed.
    Pushes portfolio + risk updates every 5 seconds.
    """
    await ws_manager.connect(websocket)
    logger.info("WebSocket client connected", client=str(websocket.client))

    try:
        while True:
            portfolio = await state_manager.get_portfolio()
            risk = await state_manager.get_risk_metrics()
            kill_switch = await state_manager.is_kill_switch_active()

            payload: dict[str, Any] = {
                "timestamp": datetime.utcnow().isoformat(),
                "kill_switch_active": kill_switch,
            }

            if portfolio:
                payload["portfolio"] = {
                    "total_capital": float(portfolio.total_capital),
                    "daily_pnl": float(portfolio.daily_pnl),
                    "unrealized_pnl": float(portfolio.unrealized_pnl),
                    "open_positions": portfolio.open_position_count,
                    "leverage": round(portfolio.leverage, 3),
                }

            if risk:
                payload["risk"] = {
                    "daily_drawdown_pct": round(risk.daily_drawdown_pct * 100, 3),
                    "current_leverage": round(risk.current_leverage, 3),
                    "var_95_usd": float(risk.var_95_1d or 0),
                    "sharpe_90d": risk.sharpe_90d,
                }

            await websocket.send_json(payload)
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
        logger.info("WebSocket client disconnected")
    except Exception as e:
        ws_manager.disconnect(websocket)
        logger.warning("WebSocket error", error=str(e))


@app.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket) -> None:
    """Real-time price feed proxy (subscribe to Redis pub/sub)."""
    await ws_manager.connect(websocket)
    try:
        pubsub = state_manager.redis.pubsub()
        await pubsub.subscribe("alghrest:prices:*")
        async for message in pubsub.listen():
            if message["type"] == "message":
                import orjson

                data = orjson.loads(message["data"])
                await websocket.send_json(data)
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)


# ── STARTUP ENTRY POINT ───────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_level=settings.log_level.lower(),
        access_log=True,
    )
