#!/usr/bin/env python3
"""
ALGHREST — Redis Seed Script
Populates Redis with a full realistic snapshot so the dashboard shows
live-looking data immediately, even before real agents are running.

Usage:
    python scripts/seed_redis.py                     # seed db=2 @ localhost:6379
    python scripts/seed_redis.py --flush             # wipe alghrest:* first
    REDIS_URL=redis://host:6379 python scripts/seed_redis.py

Data written matches the exact Pydantic models in core/data/models.py so the
state_manager.get_portfolio() / get_agent_health() calls parse without errors.
"""
from __future__ import annotations

import argparse
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

try:
    import redis as redis_sync
    import orjson
except ImportError:
    print("ERROR: Install redis and orjson first:  pip install redis orjson")
    sys.exit(1)

# ── CONFIG ────────────────────────────────────────────────────────────────────

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")
REDIS_DB  = int(os.environ.get("REDIS_DB", "2"))   # db=2 = state DB (matches settings)

random.seed(42)   # reproducible


# ── HELPERS ───────────────────────────────────────────────────────────────────

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()

def jdump(obj: object) -> bytes:
    return orjson.dumps(obj)

def hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


# ── STATIC DATA ───────────────────────────────────────────────────────────────

# All 32 agents — mirrors AGENT_ROSTER in dashboard src/types/ws.ts
AGENTS = [
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

# Exchange enum values from core/data/models.py — must be lowercase
OPEN_POSITIONS = [
    {"symbol": "BTC/USDT",  "side": "BUY",  "size": 0.12,  "entry": 67_800.0, "current": 68_450.0, "strategy": "trend_follower",  "exchange": "binance", "agent_id": 12, "age": 5400},
    {"symbol": "ETH/USDT",  "side": "BUY",  "size": 1.85,  "entry":  3_420.0, "current":  3_390.0, "strategy": "mean_reversion",  "exchange": "binance", "agent_id": 13, "age": 3600},
    {"symbol": "SOL/USDT",  "side": "BUY",  "size": 14.0,  "entry":    172.5, "current":    178.2, "strategy": "momentum",        "exchange": "bybit",   "agent_id": 14, "age": 2700},
    {"symbol": "AVAX/USDT", "side": "SELL", "size": 28.0,  "entry":     38.9, "current":     37.5, "strategy": "stat_arb",        "exchange": "bybit",   "agent_id": 15, "age": 1800},
    {"symbol": "ARB/USDT",  "side": "BUY",  "size": 420.0, "entry":      1.24,"current":      1.31,"strategy": "breakout_hunter", "exchange": "binance", "agent_id": 19, "age": 900},
]

CLOSED_TRADES = [
    {"symbol": "BNB/USDT",   "side": "BUY",  "size": 1.5,    "entry_price": 420.00, "exit_price": 429.00, "realized_pnl":  148.22, "pnl_pct":  2.1, "strategy": "momentum",        "secs_ago": 3600},
    {"symbol": "MATIC/USDT", "side": "SELL", "size": 250.0,  "entry_price":   0.88, "exit_price":   0.91, "realized_pnl":  -62.50, "pnl_pct": -0.9, "strategy": "mean_reversion",  "secs_ago": 5400},
    {"symbol": "LINK/USDT",  "side": "BUY",  "size": 85.0,   "entry_price":  18.20, "exit_price":  21.85, "realized_pnl":  310.25, "pnl_pct":  4.4, "strategy": "breakout_hunter", "secs_ago": 7200},
    {"symbol": "DOT/USDT",   "side": "BUY",  "size": 120.0,  "entry_price":   7.40, "exit_price":   7.17, "realized_pnl":  -28.00, "pnl_pct": -0.4, "strategy": "trend_follower",  "secs_ago": 9000},
    {"symbol": "ADA/USDT",   "side": "SELL", "size": 1800.0, "entry_price":   0.46, "exit_price":   0.45, "realized_pnl":   82.50, "pnl_pct":  1.2, "strategy": "stat_arb",        "secs_ago": 10800},
    {"symbol": "UNI/USDT",   "side": "BUY",  "size": 45.0,   "entry_price":   9.50, "exit_price":   9.16, "realized_pnl":  -15.00, "pnl_pct": -0.2, "strategy": "ml_predictor",    "secs_ago": 12600},
    {"symbol": "ATOM/USDT",  "side": "BUY",  "size": 95.0,   "entry_price":   7.40, "exit_price":   9.55, "realized_pnl":  204.00, "pnl_pct":  2.9, "strategy": "macro_rotator",   "secs_ago": 14400},
    {"symbol": "FIL/USDT",   "side": "SELL", "size": 60.0,   "entry_price":   5.50, "exit_price":   5.43, "realized_pnl":   38.00, "pnl_pct":  0.5, "strategy": "momentum",        "secs_ago": 16200},
    {"symbol": "OP/USDT",    "side": "BUY",  "size": 200.0,  "entry_price":   1.65, "exit_price":   1.60, "realized_pnl":   -9.50, "pnl_pct": -0.1, "strategy": "stat_arb",        "secs_ago": 18000},
    {"symbol": "INJ/USDT",   "side": "BUY",  "size": 35.0,   "entry_price":  28.00, "exit_price":  33.00, "realized_pnl":  175.00, "pnl_pct":  2.5, "strategy": "breakout_hunter", "secs_ago": 19800},
]


# ── SEEDER ────────────────────────────────────────────────────────────────────

def seed(r: redis_sync.Redis, flush: bool = False) -> None:
    if flush:
        keys = r.keys("alghrest:*")
        if keys:
            r.delete(*keys)
            print(f"  Flushed {len(keys)} alghrest:* keys")

    pipe = r.pipeline()

    # ── 1. PORTFOLIO SNAPSHOT ─────────────────────────────────────────────────
    # Matches core.data.models.Portfolio (all required fields present)
    capital      = 10_250.0
    daily_pnl    = 423.75
    reserved     = sum(p["size"] * p["current"] for p in OPEN_POSITIONS)
    emergency    = round(capital * 0.15, 2)       # 15% untouchable reserve
    available    = round(capital - reserved - emergency, 2)

    # Build Position objects matching core.data.models.Position
    positions = []
    for p in OPEN_POSITIONS:
        unr = round((p["current"] - p["entry"]) * p["size"] * (1 if p["side"] == "BUY" else -1), 4)
        unr_pct = round((p["current"] / p["entry"] - 1) * 100 * (1 if p["side"] == "BUY" else -1), 4)
        positions.append({
            "position_id":    str(uuid4()),
            "symbol":         p["symbol"],
            "exchange":       p["exchange"],        # lowercase — matches Exchange enum value
            "asset_class":    "CRYPTO",
            "side":           p["side"],            # "BUY" | "SELL" — plain string
            "size":           str(p["size"]),       # Decimal accepts numeric strings
            "entry_price":    str(p["entry"]),
            "current_price":  str(p["current"]),
            "strategy_id":    p["strategy"],
            "agent_id":       p["agent_id"],
            "opened_at":      ago(p["age"]),
            "updated_at":     ago(random.randint(10, 120)),
        })

    portfolio = {
        "snapshot_time":     now_iso(),
        "total_capital":     str(capital),
        "available_capital": str(max(0.0, available)),
        "reserved_capital":  str(round(reserved, 2)),
        "emergency_reserve": str(emergency),
        "daily_pnl":         str(daily_pnl),
        "positions":         positions,
    }
    pipe.set("alghrest:portfolio:current", jdump(portfolio), ex=86400)
    print("  ✓ Portfolio snapshot")

    # ── 2. PNL HISTORY (48 × 10-min points = 8 h) ────────────────────────────
    # Format: {time: "HH:MM", value: float}  — matches frontend PnlPointSchema
    pipe.delete("alghrest:portfolio:pnl_history")
    base_pnl = 0.0
    pnl_points = []
    for i in range(47, -1, -1):
        ts = datetime.now(timezone.utc) - timedelta(minutes=i * 10)
        base_pnl += random.gauss(9.0, 25.0)
        pnl_points.append(jdump({
            "time":  hhmm(ts),
            "value": round(base_pnl, 2),
        }))
    pipe.rpush("alghrest:portfolio:pnl_history", *pnl_points)
    print(f"  ✓ PnL history ({len(pnl_points)} points)")

    # ── 3. AGENT HEARTBEATS ───────────────────────────────────────────────────
    # Matches core.data.models.AgentHealth (all required fields)
    start_epoch = int(time.time()) - 7200   # all agents "started" 2 h ago
    for i, agent in enumerate(AGENTS):
        if i == 7:                          # Agent 8: On-Chain Sleuth — DEGRADED
            status = "DEGRADED"
            last_error = "High memory usage: 892 MB threshold exceeded"
            mem = 892.0
        elif i == 28:                       # Agent 29: Bridge Strategist — SHUTDOWN
            status = "SHUTDOWN"
            last_error = "DeFi module not yet deployed (v0.3 pending)"
            mem = 0.0
        else:
            status = "RUNNING"
            last_error = None
            mem = round(random.uniform(120.0, 640.0), 1)

        uptime = int(time.time()) - start_epoch + random.randint(-60, 60)
        heartbeat = {
            "agent_id":           agent["id"],
            "agent_name":         agent["name"],
            "tier":               agent["tier"],
            "status":             status,          # plain AgentStatus enum value
            "start_time":         ago(uptime),
            "last_heartbeat":     ago(random.randint(1, 8)),
            "uptime_seconds":     uptime,
            "messages_processed": random.randint(1_200, 48_000),
            "messages_failed":    random.randint(0, 12),
            "error_count":        random.randint(0, 5),
            "last_error":         last_error,
            "latency_p50_ms":     round(random.uniform(2.0, 20.0), 1),
            "latency_p99_ms":     round(random.uniform(8.0, 85.0), 1),
            "memory_mb":          mem,
            "cpu_pct":            round(random.uniform(0.5, 12.0), 1),
        }
        key = f"alghrest:agent:health:{agent['id']}"
        pipe.setex(key, 86400, jdump(heartbeat))
    print("  ✓ Agent heartbeats (32 agents, 30 RUNNING / 1 DEGRADED / 1 SHUTDOWN)")

    # ── 4. CLOSED TRADES ──────────────────────────────────────────────────────
    # Format matches frontend ClosedTradeSchema: {symbol, side, size,
    #   entry_price, exit_price, realized_pnl, pnl_pct, strategy, closed_at}
    pipe.delete("alghrest:trades:closed_today")
    for trade in CLOSED_TRADES:
        pipe.rpush("alghrest:trades:closed_today", jdump({
            "symbol":       trade["symbol"],
            "side":         trade["side"],
            "size":         trade["size"],
            "entry_price":  trade["entry_price"],
            "exit_price":   trade["exit_price"],
            "realized_pnl": trade["realized_pnl"],
            "pnl_pct":      trade["pnl_pct"],
            "strategy":     trade["strategy"],
            "closed_at":    ago(trade["secs_ago"]),
        }))
    print(f"  ✓ Closed trades ({len(CLOSED_TRADES)} trades)")

    # ── 5. KAFKA TOPIC METRICS ────────────────────────────────────────────────
    # Realistic throughput: high-frequency topics get more msgs/sec
    topic_rates = {
        "prices.realtime":     (850.0,  2.1),
        "news.tagged":         ( 12.0, 45.0),
        "sentiment.scored":    (  8.5, 38.0),
        "onchain.signals":     ( 22.0, 15.0),
        "macro.regime":        (  0.5, 120.0),
        "indicators.computed": ( 45.0,  8.0),
        "patterns.detected":   ( 18.0, 22.0),
        "volatility.forecast": (  6.0, 55.0),
        "correlation.matrix":  (  0.8, 95.0),
        "proposals.bus":       (  3.5, 280.0),
        "orders.approved":     (  1.2, 490.0),
        "orders.executed":     (  1.0, 510.0),
        "fills.confirmed":     (  0.9, 540.0),
        "portfolio.state":     (  0.3, 1800.0),
        "risk.alerts":         (  0.1, 6000.0),
        "rl.param.updates":    (  0.05, 12000.0),
    }
    for topic in KAFKA_TOPICS:
        rate, lag = topic_rates.get(topic, (5.0, 100.0))
        msg_per_sec = round(rate + random.uniform(-rate * 0.15, rate * 0.15), 2)
        lag_ms      = round(lag  + random.uniform(-lag  * 0.20, lag  * 0.20), 1)
        pipe.setex(f"alghrest:kafka:metrics:{topic}", 86400, jdump({
            "messages_per_sec": max(0.0, msg_per_sec),
            "consumer_lag_ms":  max(0.0, lag_ms),
            "last_message_ts":  ago(random.randint(0, 3)),
            "partition_count":  6,
            "total_messages":   random.randint(10_000, 5_000_000),
        }))
    print(f"  ✓ Kafka topic metrics ({len(KAFKA_TOPICS)} topics)")

    # ── 6. RISK METRICS ───────────────────────────────────────────────────────
    # Matches core.data.models.RiskMetrics (all required fields)
    risk = {
        "timestamp":            now_iso(),
        "total_capital":        str(capital),
        "available_capital":    str(max(0.0, available)),
        "daily_pnl":            str(daily_pnl),
        "daily_drawdown_pct":   0.028,     # 2.8% of 7% daily limit
        "monthly_drawdown_pct": 0.041,     # 4.1% of 12% monthly limit
        "current_leverage":     1.87,
        "var_95_1d":            str(218.50),
        "sharpe_90d":           1.84,
        "sortino_90d":          2.31,
        "open_positions":       len(OPEN_POSITIONS),
    }
    pipe.set("alghrest:risk:current", jdump(risk), ex=86400)
    print("  ✓ Risk metrics")

    # ── 7. KILL SWITCH — ensure inactive ──────────────────────────────────────
    pipe.delete("alghrest:kill_switch:active")
    print("  ✓ Kill switch cleared (inactive)")

    # ── EXECUTE ALL ───────────────────────────────────────────────────────────
    pipe.execute()


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Redis with ALGHREST test data")
    parser.add_argument("--flush", action="store_true",
                        help="Delete all alghrest:* keys before seeding")
    parser.add_argument("--redis-url", default=REDIS_URL,
                        help=f"Redis URL (default: {REDIS_URL})")
    parser.add_argument("--db", type=int, default=REDIS_DB,
                        help=f"Redis database index (default: {REDIS_DB})")
    args = parser.parse_args()

    print(f"\nALGHREST Redis Seeder")
    print(f"  Redis : {args.redis_url} / db={args.db}")
    print(f"  Flush : {args.flush}\n")

    try:
        r = redis_sync.from_url(args.redis_url, db=args.db, decode_responses=False)
        r.ping()
    except Exception as exc:
        print(f"ERROR: Cannot connect to Redis at {args.redis_url}\n  {exc}")
        sys.exit(1)

    start = time.time()
    seed(r, flush=args.flush)
    elapsed = round((time.time() - start) * 1000)

    print(f"\n✅ Seed complete in {elapsed} ms")
    print(f"   Dashboard : http://localhost:5173")
    print(f"   Via Nginx : http://localhost")
    print(f"   API docs  : http://localhost:8000/docs\n")


if __name__ == "__main__":
    main()
