"""
ALGHREST — Redis State Manager
Shared state across all agents: portfolio snapshot, agent health,
risk metrics, and distributed coordination primitives.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Any, cast

import orjson
import structlog
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.lock import Lock

from core.config import settings
from core.data.models import AgentHealth, AgentStatus, Portfolio, RiskMetrics

logger = structlog.get_logger(__name__)

# Redis key namespaces
_NS_AGENT_HEALTH = "alghrest:agent:health:{agent_id}"
_NS_AGENT_STATUS = "alghrest:agent:status:{agent_id}"
_NS_PORTFOLIO = "alghrest:portfolio:current"
_NS_RISK = "alghrest:risk:current"
_NS_DEDUP = "alghrest:dedup:{key}"
_NS_LOCK = "alghrest:lock:{name}"
_NS_SIGNAL = "alghrest:signal:latest:{symbol}:{signal_type}"
_NS_KILL_SWITCH = "alghrest:kill_switch:active"


class StateManager:
    """
    Singleton Redis client shared across all coroutines within a process.
    One connection pool per agent process.
    """

    def __init__(self) -> None:
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None
        self._log = logger.bind(component="state_manager")

    async def initialize(self) -> None:
        self._pool = ConnectionPool.from_url(
            settings.redis_url,
            db=settings.redis_db_state,
            max_connections=20,
            socket_timeout=5.0,
            socket_connect_timeout=5.0,
            retry_on_timeout=True,
            decode_responses=False,
        )
        self._redis = Redis(connection_pool=self._pool)
        await self._redis.ping()
        self._log.info("state manager connected", database=settings.redis_db_state)

    @property
    def redis(self) -> Redis:
        if self._redis is None:
            raise RuntimeError("StateManager not initialized — call initialize() first")
        return self._redis

    # ── AGENT HEALTH ──────────────────────────────────────────────────────────

    async def set_agent_health(self, health: AgentHealth, ttl_seconds: int = 60) -> None:
        key = _NS_AGENT_HEALTH.format(agent_id=health.agent_id)
        data = orjson.dumps(health.model_dump(mode="json"))
        await self.redis.setex(key, ttl_seconds, data)

    async def get_agent_health(self, agent_id: int) -> AgentHealth | None:
        key = _NS_AGENT_HEALTH.format(agent_id=agent_id)
        raw = await self.redis.get(key)
        if raw:
            return AgentHealth.model_validate(orjson.loads(raw))
        return None

    async def get_all_agent_healths(self) -> list[AgentHealth]:
        keys = await self.redis.keys("alghrest:agent:health:*")
        if not keys:
            return []
        values = await self.redis.mget(keys)
        return [AgentHealth.model_validate(orjson.loads(v)) for v in values if v is not None]

    async def set_agent_status(self, agent_id: int, status: AgentStatus) -> None:
        key = _NS_AGENT_STATUS.format(agent_id=agent_id)
        await self.redis.set(key, status.value, ex=120)

    # ── PORTFOLIO STATE ────────────────────────────────────────────────────────

    async def set_portfolio(self, portfolio: Portfolio) -> None:
        data = orjson.dumps(portfolio.model_dump(mode="json"))
        await self.redis.set(_NS_PORTFOLIO, data, ex=300)

    async def get_portfolio(self) -> Portfolio | None:
        raw = await self.redis.get(_NS_PORTFOLIO)
        if raw:
            return Portfolio.model_validate(orjson.loads(raw))
        return None

    async def set_accounting_portfolio(self, portfolio: Portfolio) -> None:
        """Short-lived cache; the accountant's DB writer lease owns publication."""
        await self.redis.set(_NS_PORTFOLIO, portfolio.model_dump_json(), ex=15)

    async def invalidate_portfolio(self) -> None:
        await self.redis.delete(_NS_PORTFOLIO)

    async def set_reconciliation(self, report: dict[str, Any], ttl: int = 30) -> None:
        await self.set_json(f"alghrest:reconciliation:{report['book_id']}", report, ttl=ttl)

    async def trading_ready(self, portfolio: Portfolio | None = None) -> bool:
        """Missing, stale, foreign-book, or old-revision evidence blocks new risk."""
        from core.accounting.models import utc
        from core.accounting.performance import PerformanceUnavailableError, require_performance

        portfolio = portfolio or await self.get_portfolio()
        if portfolio is None or portfolio.accounting_book_id != settings.accounting_book_id:
            return False
        try:
            require_performance(portfolio)
        except PerformanceUnavailableError:
            return False
        age = (datetime.now(UTC) - utc(portfolio.snapshot_time)).total_seconds()
        if not 0 <= age <= 15:
            return False
        report = await self.get_json(f"alghrest:reconciliation:{settings.accounting_book_id}")
        if (
            not isinstance(report, dict)
            or report.get("ready") is not True
            or report.get("revision") != portfolio.accounting_revision
        ):
            return False
        try:
            age = (
                datetime.now(UTC) - utc(datetime.fromisoformat(report["checked_at"]))
            ).total_seconds()
            return (
                report.get("book_id") == settings.accounting_book_id
                and 0 <= age <= settings.execution_reconciliation_ttl
            )
        except (KeyError, TypeError, ValueError):
            return False

    async def set_accounting_mark(
        self,
        exchange: str,
        symbol: str,
        price: str,
        timestamp: str,
        epoch_ms: int,
    ) -> None:
        # Retain venue identity, decimal precision, and the actual price time.
        # Old candles must never refresh the freshness of a newer book quote.
        script = """
        local old = redis.call('GET', KEYS[1])
        if old and tonumber(cjson.decode(old).epoch_ms) > tonumber(ARGV[1]) then return 0 end
        redis.call('SET', KEYS[1], ARGV[2], 'EX', 300)
        return 1
        """
        data = orjson.dumps({"price": price, "timestamp": timestamp, "epoch_ms": epoch_ms})
        await cast(
            Awaitable[object],
            self.redis.eval(
                script, 1, f"accounting:mark:{exchange}:{symbol}", str(epoch_ms), data.decode()
            ),
        )

    # ── RISK METRICS ──────────────────────────────────────────────────────────

    async def set_risk_metrics(self, metrics: RiskMetrics) -> None:
        data = orjson.dumps(metrics.model_dump(mode="json"))
        await self.redis.set(_NS_RISK, data, ex=120)

    async def get_risk_metrics(self) -> RiskMetrics | None:
        raw = await self.redis.get(_NS_RISK)
        if raw:
            return RiskMetrics.model_validate(orjson.loads(raw))
        return None

    # ── KILL SWITCH ───────────────────────────────────────────────────────────

    async def activate_kill_switch(self, reason: str, ttl_seconds: int = 86400) -> None:
        await self.redis.setex(_NS_KILL_SWITCH, ttl_seconds, reason.encode())
        self._log.critical("kill switch activated", reason=reason)

    async def is_kill_switch_active(self) -> bool:
        return bool(await self.redis.exists(_NS_KILL_SWITCH) > 0)

    async def deactivate_kill_switch(self) -> None:
        await self.redis.delete(_NS_KILL_SWITCH)
        self._log.warning("kill switch deactivated")

    async def get_kill_switch_reason(self) -> str | None:
        raw = await self.redis.get(_NS_KILL_SWITCH)
        return raw.decode() if raw else None

    # ── IDEMPOTENCY DEDUPLICATION ─────────────────────────────────────────────

    async def is_already_processed(self, idempotency_key: str, ttl_seconds: int = 3600) -> bool:
        """
        Returns True if this key was seen recently (message already processed).
        Atomically sets the key if not present (SET NX EX pattern).
        """
        key = _NS_DEDUP.format(key=idempotency_key)
        result = await self.redis.set(key, b"1", ex=ttl_seconds, nx=True)
        # NX returns None if key already existed (already processed)
        return result is None

    # ── DISTRIBUTED LOCKS ─────────────────────────────────────────────────────

    @asynccontextmanager
    async def lock(self, name: str, timeout: float = 30.0) -> AsyncIterator[Lock]:
        """Distributed lock for critical sections (e.g., order submission)."""
        key = _NS_LOCK.format(name=name)
        lock = self.redis.lock(key, timeout=timeout, blocking_timeout=timeout)
        acquired = await lock.acquire()
        if not acquired:
            raise TimeoutError(f"Could not acquire distributed lock: {name}")
        try:
            yield lock
        finally:
            with suppress(Exception):
                await lock.release()

    # ── LATEST SIGNAL CACHE ───────────────────────────────────────────────────

    async def cache_signal(
        self, symbol: str, signal_type: str, data: dict[str, Any], ttl: int = 3600
    ) -> None:
        key = _NS_SIGNAL.format(symbol=symbol, signal_type=signal_type)
        await self.redis.setex(key, ttl, orjson.dumps(data))

    async def get_cached_signal(self, symbol: str, signal_type: str) -> dict[str, Any] | None:
        key = _NS_SIGNAL.format(symbol=symbol, signal_type=signal_type)
        raw = await self.redis.get(key)
        return orjson.loads(raw) if raw else None

    # ── PUB/SUB ───────────────────────────────────────────────────────────────

    async def publish(self, channel: str, data: dict[str, Any]) -> None:
        await self.redis.publish(channel, orjson.dumps(data))

    # ── GENERIC K/V ──────────────────────────────────────────────────────────

    async def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        data = orjson.dumps(value)
        if ttl:
            await self.redis.setex(key, ttl, data)
        else:
            await self.redis.set(key, data)

    async def get_json(self, key: str) -> Any | None:
        raw = await self.redis.get(key)
        return orjson.loads(raw) if raw else None

    # ── LIFECYCLE ────────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        if self._redis:
            await self._redis.aclose()
        if self._pool:
            await self._pool.disconnect()
        self._log.info("state manager disconnected")


# Module-level singleton — imported by agents
state_manager = StateManager()
