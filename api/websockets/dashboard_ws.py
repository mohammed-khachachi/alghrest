"""
ALGHREST — Dashboard WebSocket Manager
Streams live system data to all connected dashboard clients.

Channels:
  portfolio.snapshot  — KPI cards + PnL chart (1 s)
  agents.heartbeats   — 32-agent grid (1 s)
  positions.updates   — open/closed positions (2 s)
  kafka.metrics       — topic throughput + lag (2 s)
  risk.alerts         — real-time alerts (pub/sub)
  system.status       — header badge (5 s)
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import orjson
import structlog
from fastapi import WebSocket, WebSocketDisconnect
from redis.asyncio import Redis

from core.config import settings
from core.orchestrator.state_manager import state_manager

logger = structlog.get_logger(__name__)

# Redis keys
_KAFKA_METRICS_KEY = "alghrest:kafka:metrics:{topic}"
_PNL_HISTORY_KEY = "alghrest:portfolio:pnl_history"
_RISK_LIMITS_KEY = "alghrest:risk:limits"


# ── AGENT ROSTER ─────────────────────────────────────────────────────────────

AGENTS: list[dict[str, Any]] = [
    {"id": 1,  "name": "CIO Agent",            "tier": 1},
    {"id": 2,  "name": "Risk Governor",         "tier": 1},
    {"id": 3,  "name": "Market Data Hub",       "tier": 2},
    {"id": 4,  "name": "News Analyst",          "tier": 2},
    {"id": 5,  "name": "Sentiment Analyst",     "tier": 2},
    {"id": 6,  "name": "Macro Economist",       "tier": 2},
    {"id": 7,  "name": "Geopolitical Watcher",  "tier": 2},
    {"id": 8,  "name": "On-Chain Sleuth",       "tier": 2},
    {"id": 9,  "name": "Technical Analyst",     "tier": 3},
    {"id": 10, "name": "Volatility Forecaster", "tier": 3},
    {"id": 11, "name": "Correlation Engine",    "tier": 3},
    {"id": 12, "name": "Trend Follower",        "tier": 4},
    {"id": 13, "name": "Mean Reversion",        "tier": 4},
    {"id": 14, "name": "Momentum",              "tier": 4},
    {"id": 15, "name": "Stat Arb",              "tier": 4},
    {"id": 16, "name": "ML Predictor",          "tier": 4},
    {"id": 17, "name": "Options Strategist",    "tier": 4},
    {"id": 18, "name": "Macro Rotator",         "tier": 4},
    {"id": 19, "name": "Breakout Hunter",       "tier": 4},
    {"id": 20, "name": "Order Router",          "tier": 5},
    {"id": 21, "name": "Position Sizer",        "tier": 5},
    {"id": 22, "name": "Slippage Minimizer",    "tier": 5},
    {"id": 23, "name": "Hedge Manager",         "tier": 5},
    {"id": 24, "name": "Fee Optimizer",         "tier": 5},
    {"id": 25, "name": "Liquidation Guard",     "tier": 5},
    {"id": 26, "name": "Yield Farmer",          "tier": 6},
    {"id": 27, "name": "DEX Arbitrageur",       "tier": 6},
    {"id": 28, "name": "MEV Hunter",            "tier": 6},
    {"id": 29, "name": "Bridge Strategist",     "tier": 6},
    {"id": 30, "name": "Portfolio Tracker",     "tier": 7},
    {"id": 31, "name": "Alert Manager",         "tier": 7},
    {"id": 32, "name": "Compliance Agent",      "tier": 7},
]

KAFKA_TOPICS = [
    "prices.realtime",
    "news.tagged",
    "sentiment.scored",
    "onchain.signals",
    "macro.regime",
    "indicators.computed",
    "patterns.detected",
    "volatility.forecast",
    "correlation.matrix",
    "proposals.bus",
    "orders.approved",
    "orders.executed",
    "fills.confirmed",
    "portfolio.state",
    "risk.alerts",
    "rl.param.updates",
]

RISK_LIMITS_STATIC = [
    {"name": "Max Daily Drawdown",   "threshold":  7.0,   "unit": "%"},
    {"name": "Max Monthly Drawdown", "threshold": 12.0,   "unit": "%"},
    {"name": "Max Leverage",         "threshold":  3.0,   "unit": "x"},
    {"name": "Daily VaR",            "threshold": 500.0,  "unit": "USD"},
    {"name": "Max Single Asset",     "threshold":  5.0,   "unit": "%"},
    {"name": "Max Sector Exposure",  "threshold": 20.0,   "unit": "%"},
    {"name": "Consecutive Losses",   "threshold":  5.0,   "unit": "trades"},
    {"name": "Min Sharpe (90d)",     "threshold":  0.5,   "unit": "ratio"},
]


# ── MANAGER ──────────────────────────────────────────────────────────────────

class DashboardWebSocketManager:
    """
    Manages all connected dashboard WebSocket clients.
    Broadcasts structured channel messages to subscribers.
    """

    def __init__(self) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._start_time = time.time()
        self._log = logger.bind(component="dashboard_ws")

    # ── CONNECTION LIFECYCLE ─────────────────────────────────────────────────

    async def connect(self, ws: WebSocket) -> str:
        await ws.accept()
        conn_id = str(uuid.uuid4())[:8]
        self._connections[conn_id] = ws
        self._log.info("dashboard client connected", conn_id=conn_id, total=len(self._connections))
        return conn_id

    def disconnect(self, conn_id: str) -> None:
        self._connections.pop(conn_id, None)
        self._log.info("dashboard client disconnected", conn_id=conn_id, total=len(self._connections))

    # ── BROADCAST ────────────────────────────────────────────────────────────

    async def broadcast(self, channel: str, data: dict[str, Any]) -> None:
        message = orjson.dumps({
            "channel": channel,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        dead: list[str] = []
        for conn_id, ws in self._connections.items():
            try:
                await ws.send_bytes(message)
            except Exception:
                dead.append(conn_id)
        for conn_id in dead:
            self.disconnect(conn_id)

    async def send_to(self, conn_id: str, channel: str, data: dict[str, Any]) -> None:
        ws = self._connections.get(conn_id)
        if ws is None:
            return
        try:
            await ws.send_bytes(orjson.dumps({
                "channel": channel,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }))
        except Exception:
            self.disconnect(conn_id)

    # ── DATA BUILDERS ────────────────────────────────────────────────────────

    async def _build_portfolio_snapshot(self) -> dict[str, Any]:
        portfolio = await state_manager.get_portfolio()
        pnl_history_raw = await state_manager.redis.lrange(_PNL_HISTORY_KEY, 0, 288)  # 24h at 5min

        pnl_history = []
        for entry in pnl_history_raw:           # lrange returns oldest-first; no reversal needed
            try:
                pnl_history.append(orjson.loads(entry))
            except Exception:
                pass

        if portfolio:
            return {
                "daily_pnl_usd":   float(portfolio.daily_pnl),
                "daily_pnl_pct":   round(float(portfolio.daily_pnl) / float(portfolio.total_capital) * 100, 3)
                                   if portfolio.total_capital else 0.0,
                "portfolio_value": float(portfolio.total_capital),
                "open_positions":  len(portfolio.positions),
                "unrealized_pnl":  float(portfolio.unrealized_pnl),
                "leverage":        round(portfolio.leverage, 3),
                "pnl_history":     pnl_history,
            }
        return {
            "daily_pnl_usd": 0.0,
            "daily_pnl_pct": 0.0,
            "portfolio_value": 0.0,
            "open_positions": 0,
            "unrealized_pnl": 0.0,
            "leverage": 0.0,
            "pnl_history": pnl_history,
        }

    async def _build_agents_heartbeats(self) -> dict[str, Any]:
        healths = await state_manager.get_all_agent_healths()
        health_map = {h.agent_id: h for h in healths}
        now = datetime.now(timezone.utc)

        agents_out = []
        for agent_def in AGENTS:
            agent_id: int = agent_def["id"]
            health = health_map.get(agent_id)
            if health:
                heartbeat_secs = (now - health.last_heartbeat.replace(tzinfo=timezone.utc)).total_seconds()
                total = health.messages_processed + health.messages_failed
                error_rate = round(health.messages_failed / total * 100, 2) if total > 0 else 0.0
                agents_out.append({
                    "agent_id":          agent_id,
                    "agent_name":        health.agent_name,
                    "tier":              health.tier,
                    "status":            health.status.value,
                    "messages_processed": health.messages_processed,
                    "last_heartbeat_secs": round(heartbeat_secs, 1),
                    "memory_mb":         health.memory_mb or 0.0,
                    "error_rate_pct":    error_rate,
                    "latency_p99_ms":    health.latency_p99_ms or 0.0,
                    "logs":              ([health.last_error] if health.last_error else []),
                })
            else:
                agents_out.append({
                    "agent_id":           agent_id,
                    "agent_name":         agent_def["name"],
                    "tier":               agent_def["tier"],
                    "status":             "SHUTDOWN",
                    "messages_processed": 0,
                    "last_heartbeat_secs": -1,
                    "memory_mb":          0.0,
                    "error_rate_pct":     0.0,
                    "latency_p99_ms":     0.0,
                    "logs":               [],
                })

        active = sum(1 for a in agents_out if a["status"] == "RUNNING")
        return {"agents": agents_out, "active_count": active, "total_count": 32}

    async def _build_positions_update(self) -> dict[str, Any]:
        portfolio = await state_manager.get_portfolio()
        if not portfolio:
            return {"open_positions": [], "closed_trades": [], "long_exposure": 0.0,
                    "short_exposure": 0.0, "net_delta": 0.0}

        long_exp = short_exp = 0.0
        positions_out = []
        for pos in portfolio.positions:
            notional = float(pos.size * pos.current_price)
            if pos.side.value == "BUY":
                long_exp += notional
            else:
                short_exp += notional
            age_seconds = (datetime.now(timezone.utc) - pos.opened_at.replace(tzinfo=timezone.utc)).total_seconds()
            positions_out.append({
                "symbol":          pos.symbol,
                "side":            pos.side.value,
                "size":            float(pos.size),
                "entry_price":     float(pos.entry_price),
                "current_price":   float(pos.current_price),
                "unrealized_pnl":  float(pos.unrealized_pnl),
                "unrealized_pnl_pct": round(pos.unrealized_pnl_pct, 3),
                "strategy":        pos.strategy_id,
                "exchange":        pos.exchange.value,
                "opened_at":       pos.opened_at.isoformat(),
                "age_seconds":     round(age_seconds),
            })

        closed_raw = await state_manager.redis.lrange("alghrest:trades:closed_today", 0, 49)
        closed_trades = []
        for raw in closed_raw:
            try:
                closed_trades.append(orjson.loads(raw))
            except Exception:
                pass

        return {
            "open_positions": positions_out,
            "closed_trades":  closed_trades,
            "long_exposure":  round(long_exp, 2),
            "short_exposure": round(short_exp, 2),
            "net_delta":      round(long_exp - short_exp, 2),
        }

    async def _build_kafka_metrics(self) -> dict[str, Any]:
        topics_out = []
        for topic in KAFKA_TOPICS:
            raw = await state_manager.redis.get(_KAFKA_METRICS_KEY.format(topic=topic))
            if raw:
                try:
                    data = orjson.loads(raw)
                    topics_out.append({
                        "name":             topic,
                        "messages_per_sec": data.get("messages_per_sec", 0.0),
                        "consumer_lag_ms":  data.get("consumer_lag_ms", 0.0),
                        "last_message_ts":  data.get("last_message_ts", ""),
                        "partition_count":  data.get("partition_count", 6),
                        "total_messages":   data.get("total_messages", 0),
                    })
                    continue
                except Exception:
                    pass
            topics_out.append({
                "name":             topic,
                "messages_per_sec": 0.0,
                "consumer_lag_ms":  0.0,
                "last_message_ts":  "",
                "partition_count":  6,
                "total_messages":   0,
            })
        return {"topics": topics_out}

    async def _build_system_status(self) -> dict[str, Any]:
        kill_switch = await state_manager.is_kill_switch_active()
        reason = await state_manager.get_kill_switch_reason() if kill_switch else None
        env = settings.environment

        if kill_switch:
            status = "HALTED"
        elif env == "live":
            status = "LIVE"
        else:
            status = "PAPER"

        return {
            "status":              status,
            "kill_switch_active":  kill_switch,
            "kill_switch_reason":  reason,
            "environment":         env,
            "uptime_seconds":      round(time.time() - self._start_time),
        }

    async def _build_risk_limits(self) -> dict[str, Any]:
        risk = await state_manager.get_risk_metrics()
        limits_out = []
        if risk:
            current_values = {
                "Max Daily Drawdown":   round(risk.daily_drawdown_pct * 100, 2),
                "Max Monthly Drawdown": round(risk.monthly_drawdown_pct * 100, 2),
                "Max Leverage":         round(risk.current_leverage, 2),
                "Daily VaR":            float(risk.var_95_1d) if risk.var_95_1d else 0.0,
                "Consecutive Losses":   0.0,
                "Min Sharpe (90d)":     risk.sharpe_90d or 0.0,
            }
        else:
            current_values = {}

        for limit in RISK_LIMITS_STATIC:
            current = current_values.get(limit["name"], 0.0)
            threshold = limit["threshold"]
            pct = current / threshold if threshold else 0.0
            if pct >= 1.0:
                ls = "BREACHED"
            elif pct >= 0.8:
                ls = "WARNING"
            else:
                ls = "OK"
            limits_out.append({
                "name":      limit["name"],
                "current":   current,
                "threshold": threshold,
                "unit":      limit["unit"],
                "status":    ls,
                "pct":       round(pct * 100, 1),
            })
        return {"limits": limits_out}

    # ── FULL SNAPSHOT ────────────────────────────────────────────────────────

    async def send_full_snapshot(self, conn_id: str) -> None:
        """Send all channel data immediately on connect."""
        tasks = [
            ("portfolio.snapshot", self._build_portfolio_snapshot()),
            ("agents.heartbeats",  self._build_agents_heartbeats()),
            ("positions.updates",  self._build_positions_update()),
            ("kafka.metrics",      self._build_kafka_metrics()),
            ("system.status",      self._build_system_status()),
            ("risk.limits",        self._build_risk_limits()),
        ]
        results = await asyncio.gather(*[t for _, t in tasks], return_exceptions=True)
        for i, (channel, _) in enumerate(tasks):
            result = results[i]
            if isinstance(result, Exception):
                self._log.warning("snapshot build failed", channel=channel, error=str(result))
                continue
            await self.send_to(conn_id, channel, result)

    # ── BACKGROUND BROADCAST LOOPS ───────────────────────────────────────────

    async def run_portfolio_loop(self) -> None:
        """Broadcast portfolio + agent data every 1 s."""
        while True:
            try:
                portfolio_data, agents_data = await asyncio.gather(
                    self._build_portfolio_snapshot(),
                    self._build_agents_heartbeats(),
                    return_exceptions=True,
                )
                if not isinstance(portfolio_data, Exception):
                    await self.broadcast("portfolio.snapshot", portfolio_data)
                if not isinstance(agents_data, Exception):
                    await self.broadcast("agents.heartbeats", agents_data)
            except Exception as exc:
                self._log.warning("portfolio loop error", error=str(exc))
            await asyncio.sleep(1.0)

    async def run_positions_kafka_loop(self) -> None:
        """Broadcast positions + kafka metrics every 2 s."""
        while True:
            try:
                pos_data, kafka_data = await asyncio.gather(
                    self._build_positions_update(),
                    self._build_kafka_metrics(),
                    return_exceptions=True,
                )
                if not isinstance(pos_data, Exception):
                    await self.broadcast("positions.updates", pos_data)
                if not isinstance(kafka_data, Exception):
                    await self.broadcast("kafka.metrics", kafka_data)
            except Exception as exc:
                self._log.warning("positions/kafka loop error", error=str(exc))
            await asyncio.sleep(2.0)

    async def run_system_status_loop(self) -> None:
        """Broadcast system status every 5 s."""
        while True:
            try:
                status_data = await self._build_system_status()
                await self.broadcast("system.status", status_data)
            except Exception as exc:
                self._log.warning("system status loop error", error=str(exc))
            await asyncio.sleep(5.0)

    async def run_risk_alerts_pubsub(self) -> None:
        """Subscribe to Redis pub/sub and forward risk alerts in real-time."""
        pubsub = state_manager.redis.pubsub()
        await pubsub.subscribe("alghrest:risk:alerts")
        self._log.info("risk alerts pub/sub subscribed")
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = orjson.loads(message["data"])
                alert_payload = {
                    "alert": {
                        "alert_id":        data.get("alert_id", ""),
                        "severity":        _map_risk_level(data.get("risk_level", "INFO")),
                        "timestamp":       data.get("timestamp", datetime.now(timezone.utc).isoformat()),
                        "message":         data.get("message", ""),
                        "affected_agent":  str(data.get("source_agent_id", "")),
                        "alert_type":      data.get("alert_type", ""),
                        "triggered_value": data.get("triggered_value", 0.0),
                        "threshold_value": data.get("threshold_value", 0.0),
                    }
                }
                await self.broadcast("risk.alerts", alert_payload)
            except Exception as exc:
                self._log.warning("risk alert parse error", error=str(exc))


def _map_risk_level(level: str) -> str:
    mapping = {"CRITICAL": "CRITICAL", "HIGH": "CRITICAL", "MEDIUM": "WARNING", "LOW": "INFO"}
    return mapping.get(level.upper(), "INFO")


# ── MODULE-LEVEL SINGLETON ────────────────────────────────────────────────────

dashboard_ws_manager = DashboardWebSocketManager()


# ── FASTAPI ENDPOINT ─────────────────────────────────────────────────────────

async def dashboard_websocket_endpoint(websocket: WebSocket) -> None:
    """
    GET /ws/dashboard
    On connect: send full system snapshot.
    Then stream deltas at appropriate intervals via shared background loops.
    """
    conn_id = await dashboard_ws_manager.connect(websocket)
    try:
        await dashboard_ws_manager.send_full_snapshot(conn_id)
        # Keep alive — background loops handle broadcasting
        while True:
            try:
                # Absorb any client-sent messages (ping/pong, control frames)
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                pass  # Normal — no client messages expected
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("dashboard WS error", conn_id=conn_id, error=str(exc))
    finally:
        dashboard_ws_manager.disconnect(conn_id)


async def start_background_loops() -> None:
    """Launch all broadcast loops as asyncio background tasks."""
    asyncio.create_task(dashboard_ws_manager.run_portfolio_loop(), name="ws-portfolio-loop")
    asyncio.create_task(dashboard_ws_manager.run_positions_kafka_loop(), name="ws-positions-loop")
    asyncio.create_task(dashboard_ws_manager.run_system_status_loop(), name="ws-status-loop")
    asyncio.create_task(dashboard_ws_manager.run_risk_alerts_pubsub(), name="ws-risk-pubsub")
    logger.info("dashboard WebSocket background loops started")
