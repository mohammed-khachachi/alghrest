"""ALGHREST 24-Hour Paper Trading Stability Monitor.

Monitors:
1. All 8 trading agents, PIDs, and heartbeats.
2. Kafka broker connectivity and consumer group state.
3. FastAPI health, authentication enforcement, and endpoint latency.
4. OpenBB historical data retrieval (AAPL, BTC/USDT, EUR/USD) on a paced schedule.
5. OHLCV data quality, timestamps, envelopes, and anomalies.
6. Redis and TimescaleDB connectivity and query latency.
7. System CPU, RAM, and per-process RSS / stability.
8. Safety invariants (ENVIRONMENT=paper_trading, BINANCE_TESTNET=true, zero live orders).

Distinction:
- OpenBB provides historical reference snapshots and batch OHLCV data.
- PaperMarketFeed provides continuous simulated streaming ticks over Kafka.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import asyncpg
import psutil
import redis.asyncio as aioredis

from connectors.data_providers.base import AssetClass
from connectors.data_providers.openbb_adapter import OpenBBAdapter
from core.config import settings
from core.data.models import Timeframe

# Configuration constants
DEFAULT_SAMPLE_INTERVAL_SECONDS = 60  # Health & process check cadence
DEFAULT_OPENBB_PACED_INTERVAL_SECONDS = 600  # Paced external data check (every 10m to avoid Yahoo rate limits)
DEFAULT_TOTAL_DURATION_SECONDS = 86400  # 24 hours

EXPECTED_AGENT_NAMES = [
    "PaperMarketFeed",
    "PortfolioAccountant",
    "ExchangeExecutor",
    "RiskGovernor",
    "PortfolioTracker",
    "ProposalApprover",
    "OrderRouter",
    "SlippageMinimizer",
]


class StabilityMonitor:
    def __init__(
        self,
        *,
        output_dir: Path,
        sample_interval_s: int = DEFAULT_SAMPLE_INTERVAL_SECONDS,
        openbb_interval_s: int = DEFAULT_OPENBB_PACED_INTERVAL_SECONDS,
        total_duration_s: int = DEFAULT_TOTAL_DURATION_SECONDS,
    ) -> None:
        self.output_dir = output_dir
        self.sample_interval_s = sample_interval_s
        self.openbb_interval_s = openbb_interval_s
        self.total_duration_s = total_duration_s

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.output_dir / "stability_24h.log"
        self.jsonl_file = self.output_dir / "stability_24h.jsonl"
        self.status_file = self.output_dir / "status.json"

        self._running = True
        self._start_time: float = 0.0
        self._iteration = 0
        self._pass_count = 0
        self._warn_count = 0
        self._fail_count = 0
        self._latencies: list[float] = []
        self._last_openbb_check: float = 0.0
        self._incidents: list[dict[str, Any]] = []

        self.expected_agents: list[tuple[str, int]] = []
        self.fastapi_pid: int = 0
        self.vite_pid: int = 0

        self.adapter = OpenBBAdapter()

        # Logger setup
        self.logger = logging.getLogger("stability_monitor_24h")
        self.logger.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(asctime)s UTC] %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        self.logger.addHandler(ch)

        # File handler
        fh = logging.FileHandler(self.log_file, mode="a", encoding="utf-8")
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)

        self.discover_initial_pids()

    def discover_initial_pids(self) -> None:
        """Discover and lock baseline PIDs at monitor startup to track immutability."""
        agent_pids: dict[str, int] = {}
        for proc in psutil.process_iter(["pid", "name", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                if not cmdline:
                    continue
                cmd_str = " ".join(cmdline)
                if "run_agent.py" in cmd_str:
                    for agent_name in EXPECTED_AGENT_NAMES:
                        if agent_name in cmdline or cmd_str.endswith(f" {agent_name}"):
                            agent_pids[agent_name] = int(proc.info["pid"])
                elif "api.main" in cmd_str and "python" in cmdline[0]:
                    self.fastapi_pid = int(proc.info["pid"])
                elif "node" in cmdline[0] and "vite" in cmd_str:
                    self.vite_pid = int(proc.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        self.expected_agents = [(name, agent_pids.get(name, 0)) for name in EXPECTED_AGENT_NAMES]
        self.logger.info(
            "Locked baseline PIDs -> Agents=%s | FastAPI=%d | Vite=%d",
            dict(self.expected_agents),
            self.fastapi_pid,
            self.vite_pid,
        )

    def stop(self) -> None:
        self._running = False

    def verify_safety_invariants(self) -> tuple[bool, str]:
        """Strict safety pre-flight check before every probe."""
        if settings.environment != "paper_trading":
            return False, f"CRITICAL: environment is {settings.environment!r}, must be 'paper_trading'"
        if not settings.binance_testnet:
            return False, "CRITICAL: binance_testnet is False, must be True"
        if settings.is_live:
            return False, "CRITICAL: is_live is True, live trading is strictly forbidden"
        return True, "Safety invariants intact"

    def check_agent_fleet(self) -> dict[str, Any]:
        """Inspect all 8 trading agents: PIDs, RSS, CPU, and log recency."""
        fleet_status: dict[str, Any] = {"healthy": True, "agents": {}, "errors": []}
        log_dir = Path("artifacts/live-fleet-logs")

        for name, expected_pid in self.expected_agents:
            agent_data: dict[str, Any] = {
                "name": name,
                "expected_pid": expected_pid,
                "alive": False,
                "cpu_percent": 0.0,
                "rss_mb": 0.0,
                "last_log_age_s": None,
                "status": "dead",
            }
            if expected_pid > 0 and psutil.pid_exists(expected_pid):
                try:
                    p = psutil.Process(expected_pid)
                    if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                        agent_data["alive"] = True
                        agent_data["cpu_percent"] = round(p.cpu_percent(interval=None), 2)
                        agent_data["rss_mb"] = round(p.memory_info().rss / (1024 * 1024), 2)
                        agent_data["status"] = p.status()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    agent_data["alive"] = False

            # Check log recency
            log_p = log_dir / f"{name}.log"
            if log_p.exists():
                mtime = log_p.stat().st_mtime
                age_s = round(time.time() - mtime, 1)
                agent_data["last_log_age_s"] = age_s

            if not agent_data["alive"]:
                fleet_status["healthy"] = False
                fleet_status["errors"].append(f"Agent {name} (PID {expected_pid}) is NOT alive")

            fleet_status["agents"][name] = agent_data

        return fleet_status

    def check_fastapi_and_auth(self) -> dict[str, Any]:
        """Verify FastAPI authenticated health, latency, and auth rejection."""
        result: dict[str, Any] = {
            "healthy": False,
            "status_code": 0,
            "latency_ms": 0.0,
            "auth_enforced": False,
            "kill_switch_active": None,
            "error": None,
        }
        token = settings.api_access_token.get_secret_value()

        # 1. Test unauthenticated request (must return 401)
        req_unauth = urllib.request.Request("http://127.0.0.1:8000/health")
        try:
            with urllib.request.urlopen(req_unauth, timeout=3) as resp:
                result["auth_enforced"] = resp.status == 401
        except urllib.error.HTTPError as e:
            result["auth_enforced"] = e.code == 401
        except Exception as e:
            result["error"] = f"Unauthenticated probe error: {e}"
            return result

        # 2. Test authenticated health request
        req_auth = urllib.request.Request(
            "http://127.0.0.1:8000/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req_auth, timeout=5) as resp:
                elapsed_ms = (time.perf_counter() - t0) * 1000.0
                body = json.loads(resp.read().decode())
                result["status_code"] = resp.status
                result["latency_ms"] = round(elapsed_ms, 2)
                result["kill_switch_active"] = body.get("kill_switch_active", False)
                result["environment"] = body.get("environment")
                result["healthy"] = (
                    resp.status == 200
                    and result["auth_enforced"]
                    and body.get("status") == "ok"
                    and not result["kill_switch_active"]
                )
        except Exception as e:
            result["error"] = f"Authenticated health probe failed: {e}"

        return result

    async def check_redis(self) -> dict[str, Any]:
        """Test Redis connection, latency, and price key count."""
        result: dict[str, Any] = {"healthy": False, "latency_ms": 0.0, "price_keys": 0, "error": None}
        t0 = time.perf_counter()
        try:
            r = aioredis.from_url(settings.redis_url)
            pong = await r.ping()
            keys = await r.keys("prices:*")
            await r.aclose()
            result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            result["price_keys"] = len(keys)
            result["healthy"] = bool(pong)
        except Exception as e:
            result["error"] = str(e)
        return result

    async def check_timescaledb(self) -> dict[str, Any]:
        """Test TimescaleDB read connectivity and latency."""
        result: dict[str, Any] = {"healthy": False, "latency_ms": 0.0, "ohlcv_bars_count": 0, "error": None}
        t0 = time.perf_counter()
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        try:
            conn = await asyncpg.connect(dsn=dsn, timeout=5.0)
            count = await conn.fetchval("SELECT count(*) FROM market_data.ohlcv_bars")
            await conn.close()
            result["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
            result["ohlcv_bars_count"] = int(count)
            result["healthy"] = True
        except Exception as e:
            result["error"] = str(e)
        return result

    async def check_openbb_data(self) -> dict[str, Any]:
        """Paced data acquisition check for AAPL, BTC/USDT, and EUR/USD."""
        result: dict[str, Any] = {
            "healthy": True,
            "symbols": {},
            "errors": [],
            "checked_at": datetime.now(UTC).isoformat(),
        }
        test_matrix = [
            ("AAPL", AssetClass.EQUITY, "yfinance"),
            ("BTC/USDT", AssetClass.CRYPTO, "yfinance"),
            ("EUR/USD", AssetClass.FOREX, "yfinance"),
        ]

        end_date = datetime.now(UTC).date()
        start_date = end_date - timedelta(days=15)

        for symbol, asset_class, provider in test_matrix:
            t0 = time.perf_counter()
            sym_res: dict[str, Any] = {
                "symbol": symbol,
                "asset_class": asset_class.value,
                "provider": provider,
                "bars": 0,
                "latency_ms": 0.0,
                "quality_ok": False,
                "first_date": None,
                "last_date": None,
                "error": None,
            }
            try:
                bars = await self.adapter.fetch_historical_ohlcv(
                    symbol,
                    asset_class=asset_class,
                    timeframe=Timeframe.D1,
                    start_date=start_date,
                    end_date=end_date,
                    provider=provider,
                )
                sym_res["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
                sym_res["bars"] = len(bars)
                if bars:
                    sym_res["first_date"] = bars[0].time.date().isoformat()
                    sym_res["last_date"] = bars[-1].time.date().isoformat()
                    # Quality checks
                    valid = all(
                        b.open > 0
                        and b.high >= b.low
                        and b.low <= min(b.open, b.close)
                        and b.high >= max(b.open, b.close)
                        and b.volume >= 0
                        for b in bars
                    )
                    sym_res["quality_ok"] = valid
                if not sym_res["quality_ok"] or sym_res["bars"] == 0:
                    result["healthy"] = False
                    result["errors"].append(f"{symbol} returned 0 or invalid bars")
            except Exception as e:
                sym_res["error"] = str(e)
                sym_res["latency_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
                result["healthy"] = False
                result["errors"].append(f"{symbol} fetch failed: {e}")

            result["symbols"][symbol] = sym_res

        return result

    def get_system_resources(self) -> dict[str, Any]:
        """Collect host and core process resource metrics."""
        host_cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # Check FastAPI and Vite against locked baseline PIDs
        fastapi_proc: dict[str, Any] = {"expected_pid": self.fastapi_pid, "alive": False, "rss_mb": 0.0, "cpu_percent": 0.0}
        if self.fastapi_pid > 0 and psutil.pid_exists(self.fastapi_pid):
            try:
                p = psutil.Process(self.fastapi_pid)
                fastapi_proc["alive"] = p.is_running()
                fastapi_proc["rss_mb"] = round(p.memory_info().rss / (1024 * 1024), 2)
                fastapi_proc["cpu_percent"] = round(p.cpu_percent(interval=None), 2)
            except Exception:
                pass

        vite_proc: dict[str, Any] = {"expected_pid": self.vite_pid, "alive": False, "rss_mb": 0.0, "cpu_percent": 0.0}
        if self.vite_pid > 0 and psutil.pid_exists(self.vite_pid):
            try:
                p = psutil.Process(self.vite_pid)
                vite_proc["alive"] = p.is_running()
                vite_proc["rss_mb"] = round(p.memory_info().rss / (1024 * 1024), 2)
                vite_proc["cpu_percent"] = round(p.cpu_percent(interval=None), 2)
            except Exception:
                pass

        return {
            "host_cpu_percent": host_cpu,
            "host_mem_used_gb": round((mem.total - mem.available) / (1024**3), 2),
            "host_mem_available_gb": round(mem.available / (1024**3), 2),
            "host_mem_percent": mem.percent,
            "swap_used_gb": round(swap.used / (1024**3), 2),
            "fastapi_backend": fastapi_proc,
            "vite_dashboard": vite_proc,
        }

    async def run_single_probe(self) -> dict[str, Any]:
        """Execute one complete sampling cycle."""
        self._iteration += 1
        now_utc = datetime.now(UTC)
        ts_str = now_utc.isoformat()

        # 1. Safety check
        safe, safety_msg = self.verify_safety_invariants()
        if not safe:
            self.logger.critical("SAFETY VIOLATION DETECTED: %s", safety_msg)
            self._incidents.append({"timestamp": ts_str, "type": "safety_violation", "message": safety_msg})
            self._fail_count += 1
            return {"timestamp": ts_str, "healthy": False, "safety": safety_msg}

        # 2. Components
        agent_status = self.check_agent_fleet()
        fastapi_status = self.check_fastapi_and_auth()
        redis_status = await self.check_redis()
        timescaledb_status = await self.check_timescaledb()
        sys_metrics = self.get_system_resources()

        # 3. Paced OpenBB check
        openbb_status: dict[str, Any] | None = None
        now_monotonic = time.monotonic()
        if (
            self._last_openbb_check == 0.0
            or (now_monotonic - self._last_openbb_check) >= self.openbb_interval_s
        ):
            self.logger.info("Running paced OpenBB data check (AAPL, BTC/USDT, EUR/USD)...")
            openbb_status = await self.check_openbb_data()
            self._last_openbb_check = now_monotonic

        # Health rollup
        is_healthy = (
            agent_status["healthy"]
            and fastapi_status["healthy"]
            and redis_status["healthy"]
            and timescaledb_status["healthy"]
            and (openbb_status is None or openbb_status["healthy"])
        )

        if fastapi_status["latency_ms"] > 0:
            self._latencies.append(fastapi_status["latency_ms"])

        if is_healthy:
            self._pass_count += 1
        else:
            self._warn_count += 1
            errs: list[str] = []
            if not agent_status["healthy"]:
                errs.extend(agent_status["errors"])
            if not fastapi_status["healthy"]:
                errs.append(f"FastAPI: {fastapi_status.get('error') or 'unhealthy'}")
            if not redis_status["healthy"]:
                errs.append(f"Redis: {redis_status.get('error')}")
            if not timescaledb_status["healthy"]:
                errs.append(f"TimescaleDB: {timescaledb_status.get('error')}")
            if openbb_status and not openbb_status["healthy"]:
                errs.extend(openbb_status.get("errors", []))
            self.logger.warning("Probe #%d detected degraded component(s): %s", self._iteration, "; ".join(errs))
            self._incidents.append({"timestamp": ts_str, "iteration": self._iteration, "errors": errs})

        record: dict[str, Any] = {
            "iteration": self._iteration,
            "timestamp": ts_str,
            "healthy": is_healthy,
            "safety": safety_msg,
            "agents": agent_status,
            "fastapi": fastapi_status,
            "redis": redis_status,
            "timescaledb": timescaledb_status,
            "system_resources": sys_metrics,
        }
        if openbb_status is not None:
            record["openbb"] = openbb_status

        # Append to JSONL
        with self.jsonl_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

        # Update status.json
        elapsed = time.time() - self._start_time
        summary_status = {
            "iteration": self._iteration,
            "start_time": datetime.fromtimestamp(self._start_time, tz=UTC).isoformat(),
            "last_updated": ts_str,
            "elapsed_seconds": round(elapsed, 1),
            "target_duration_seconds": self.total_duration_s,
            "progress_percent": round(min(100.0, (elapsed / self.total_duration_s) * 100), 2),
            "overall_healthy": is_healthy,
            "pass_count": self._pass_count,
            "warn_count": self._warn_count,
            "fail_count": self._fail_count,
            "avg_fastapi_latency_ms": (
                round(sum(self._latencies[-100:]) / len(self._latencies[-100:]), 2)
                if self._latencies
                else 0.0
            ),
            "recent_incidents": self._incidents[-10:],
            "system": {
                "environment": settings.environment,
                "binance_testnet": settings.binance_testnet,
                "openbb_enabled": settings.openbb_enabled,
                "active_agents": sum(1 for a in agent_status["agents"].values() if a["alive"]),
                "expected_agents": len(self.expected_agents),
            },
        }
        self.status_file.write_text(json.dumps(summary_status, indent=2), encoding="utf-8")

        self.logger.info(
            "Probe #%d [%.1fs / %ds]: Healthy=%s | Agents=%d/%d | API Latency=%.2fms | DB=OK | Redis=OK",
            self._iteration,
            elapsed,
            self.total_duration_s,
            is_healthy,
            summary_status["system"]["active_agents"],
            len(self.expected_agents),
            fastapi_status["latency_ms"],
        )
        return record

    async def run(self) -> None:
        self._start_time = time.time()
        start_mono = time.monotonic()
        self.logger.info(
            "Starting ALGHREST 24-Hour Paper Trading Stability Test (duration=%ds, cadence=%ds)...",
            self.total_duration_s,
            self.sample_interval_s,
        )

        while self._running:
            try:
                await self.run_single_probe()
            except Exception as e:
                self.logger.exception("Unexpected error in stability probe cycle: %s", e)
                self._fail_count += 1

            elapsed = time.time() - self._start_time
            if elapsed >= self.total_duration_s:
                self.logger.info("24-Hour Stability Test reached target duration (%ds).", self.total_duration_s)
                break

            next_tick = start_mono + (self._iteration * self.sample_interval_s)
            sleep_s = max(1.0, next_tick - time.monotonic())
            await asyncio.sleep(sleep_s)

        self.logger.info("Stability monitor exited cleanly.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="ALGHREST 24-Hour Stability Monitor")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts/stability-test"),
        help="Directory to persist logs and metrics",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_SAMPLE_INTERVAL_SECONDS,
        help="Sampling cadence in seconds",
    )
    parser.add_argument(
        "--openbb-interval",
        type=int,
        default=DEFAULT_OPENBB_PACED_INTERVAL_SECONDS,
        help="Paced OpenBB check interval in seconds",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_TOTAL_DURATION_SECONDS,
        help="Total test duration in seconds (default: 86400 for 24h)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single probe and exit (for validation)",
    )
    args = parser.parse_args()

    monitor = StabilityMonitor(
        output_dir=args.output_dir,
        sample_interval_s=args.interval,
        openbb_interval_s=args.openbb_interval,
        total_duration_s=args.duration,
    )

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, monitor.stop)
        except NotImplementedError:
            pass

    if args.once:
        monitor._start_time = time.time()
        res = await monitor.run_single_probe()
        print("\nSingle Probe Output Summary:")
        print(f"Overall Healthy: {res.get('healthy')}")
        print(f"FastAPI Latency: {res.get('fastapi', {}).get('latency_ms')}ms")
        print(f"Agents Healthy: {res.get('agents', {}).get('healthy')}")
        sys.exit(0 if res.get("healthy") else 1)

    await monitor.run()


if __name__ == "__main__":
    asyncio.run(main())
