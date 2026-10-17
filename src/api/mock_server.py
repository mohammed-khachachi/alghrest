import asyncio
import contextlib
import random
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.routes.quotes import router as quotes_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(manager.run_loops(), name="mock-dashboard")
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(quotes_router)

# Full 32 Agents
AGENTS = [
    {"id": 1, "name": "CIO Agent", "tier": 1},
    {"id": 2, "name": "Risk Governor", "tier": 1},
    {"id": 3, "name": "Market Data Hub", "tier": 2},
    {"id": 4, "name": "News Analyst", "tier": 2},
    {"id": 5, "name": "Sentiment Analyst", "tier": 2},
    {"id": 6, "name": "Macro Economist", "tier": 2},
    {"id": 7, "name": "Geopolitical Watcher", "tier": 2},
    {"id": 8, "name": "On-Chain Sleuth", "tier": 2},
    {"id": 9, "name": "Technical Analyst", "tier": 3},
    {"id": 10, "name": "Volatility Forecaster", "tier": 3},
    {"id": 11, "name": "Correlation Engine", "tier": 3},
    {"id": 12, "name": "Trend Follower", "tier": 4},
    {"id": 13, "name": "Mean Reversion", "tier": 4},
    {"id": 14, "name": "Momentum", "tier": 4},
    {"id": 15, "name": "Stat Arb", "tier": 4},
    {"id": 16, "name": "ML Predictor", "tier": 4},
    {"id": 17, "name": "Options Strategist", "tier": 4},
    {"id": 18, "name": "Macro Rotator", "tier": 4},
    {"id": 19, "name": "Breakout Hunter", "tier": 4},
    {"id": 20, "name": "Order Router", "tier": 5},
    {"id": 21, "name": "Position Sizer", "tier": 5},
    {"id": 22, "name": "Slippage Minimizer", "tier": 5},
    {"id": 23, "name": "Hedge Manager", "tier": 5},
    {"id": 24, "name": "Fee Optimizer", "tier": 5},
    {"id": 25, "name": "Liquidation Guard", "tier": 5},
    {"id": 26, "name": "Yield Farmer", "tier": 6},
    {"id": 27, "name": "DEX Arbitrageur", "tier": 6},
    {"id": 28, "name": "MEV Hunter", "tier": 6},
    {"id": 29, "name": "Bridge Strategist", "tier": 6},
    {"id": 30, "name": "Portfolio Tracker", "tier": 7},
    {"id": 31, "name": "Alert Manager", "tier": 7},
    {"id": 32, "name": "Compliance Agent", "tier": 7},
]


class MockDashboardManager:
    def __init__(self):
        self.connections: list[WebSocket] = []
        self.pnl = 1000.0
        self.history = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.connections:
            self.connections.remove(ws)

    async def broadcast(self, channel: str, data: dict):
        message = {
            "channel": channel,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        for ws in self.connections:
            with contextlib.suppress(Exception):
                await ws.send_json(message)

    async def run_loops(self):
        while True:
            await asyncio.sleep(1)

            # 1. Portfolio
            self.pnl += random.uniform(-1500, 1800)
            self.history.append({"time": datetime.now(UTC).isoformat(), "value": self.pnl})
            if len(self.history) > 50:
                self.history.pop(0)

            await self.broadcast(
                "portfolio.snapshot",
                {
                    "daily_pnl_usd": self.pnl - 100000,
                    "daily_pnl_pct": (self.pnl - 100000) / 1000,
                    "portfolio_value": self.pnl,
                    "open_positions": 0,
                    "unrealized_pnl": 0.0,
                    "leverage": 0.0,
                    "pnl_history": self.history,
                },
            )

            # 2. Agents
            agents_out = []
            for a in AGENTS:
                # 90% chance running, 5% degraded, 5% error
                status = random.choices(["RUNNING", "DEGRADED", "ERROR"], weights=[90, 5, 5])[0]
                agents_out.append(
                    {
                        "agent_id": a["id"],
                        "agent_name": a["name"],
                        "tier": a["tier"],
                        "status": status,
                        "messages_processed": random.randint(10000, 500000),
                        "last_heartbeat_secs": random.uniform(0, 2),
                        "memory_mb": random.uniform(50, 350),
                        "error_rate_pct": (
                            random.uniform(0, 1) if status == "RUNNING" else random.uniform(5, 20)
                        ),
                        "latency_p99_ms": random.uniform(10, 80),
                        "logs": [],
                    }
                )

            active = len([x for x in agents_out if x["status"] == "RUNNING"])
            await self.broadcast(
                "agents.heartbeats",
                {"agents": agents_out, "active_count": active, "total_count": 32},
            )

            # 3. System Status
            await self.broadcast(
                "system.status",
                {
                    "status": "DEMO",
                    "kill_switch_active": False,
                    "kill_switch_reason": None,
                    "environment": "demo",
                    "uptime_seconds": 3600,
                },
            )

            # 4. No account is connected; exposure must match the empty position list.
            await self.broadcast(
                "positions.updates",
                {
                    "open_positions": [],
                    "closed_trades": [],
                    "long_exposure": 0.0,
                    "short_exposure": 0.0,
                    "net_delta": 0.0,
                },
            )

            # 5. Risk limits
            await self.broadcast(
                "risk.limits",
                {
                    "limits": [
                        {
                            "name": "Max Daily Drawdown",
                            "current": random.uniform(1, 5),
                            "threshold": 7.0,
                            "unit": "%",
                            "status": "OK",
                            "pct": random.uniform(10, 70),
                        },
                        {
                            "name": "Daily VaR",
                            "current": random.uniform(100, 400),
                            "threshold": 500.0,
                            "unit": "USD",
                            "status": "OK",
                            "pct": random.uniform(20, 80),
                        },
                    ]
                },
            )


manager = MockDashboardManager()


@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


if __name__ == "__main__":
    uvicorn.run("api.mock_server:app", host="0.0.0.0", port=8000, reload=True)
