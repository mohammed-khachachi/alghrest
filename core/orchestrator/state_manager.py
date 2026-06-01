"""
ALGHREST — Redis State Manager
Shared state across all agents: portfolio snapshot, agent health,
risk metrics, and distributed coordination primitives.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, AsyncIterator, Optional

import orjson
import structlog
from redis.asyncio import Redis, ConnectionPool
from redis.asyncio.lock import Lock

from core.config import settings
from core.data.models import AgentHealth, AgentStatus, Portfolio, RiskMetrics

logger = structlog.get_logger(__name__)

# Redis key namespaces
_NS_AGENT_HEALTH = "alghrest:agent:health:{agent_id}"
_NS_AGENT_STATUS = "alghrest:agent:status:{agent_id}"
_NS_PORTFOLIO    = "alghrest:portfolio:current"
_NS_RISK         = "alghrest:risk:current"
_NS_DEDUP        = "alghrest:dedup:{key}"
_NS_LOCK         = "alghrest:lock:{name}"
_NS_SIGNAL       = "alghrest:signal:latest:{symbol}:{signal_type}"
_NS_KILL_SWITCH  = "alghrest:kill_switch:active"


class StateManager:
    """
    Singleton Redis client shared across all coroutines within a process.
    One connection pool per agent process.
    """

    def __init__(self) -> None:
        self._pool: Optional[ConnectionPool] = None
        self._redis: Optional[Redis] = None
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
        self._log.info("state manager connected", url=settings.redis_url)

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

    async def get_agent_health(self, agent_id: int) -> Optional[AgentHealth]:
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
        return [
            AgentHealth.model_validate(orjson.loads(v))
            for v in values
            if v is not None
        ]

    async def set_agent_status(self, agent_id: int, status: AgentStatus) -> None:
        key = _NS_AGENT_STATUS.format(agent_id=agent_id)
        await self.redis.set(key, status.value, ex=120)

    # ── PORTFOLIO STATE ────────────────────────────────────────────────────────

    async def set_portfolio(self, portfolio: Portfolio) -> None:
        data = orjson.dumps(portfolio.model_dump(mode="json"))
        await self.redis.set(_NS_PORTFOLIO, data, ex=300)

    async def get_portfolio(self) -> Optional[Portfolio]:
        raw = await self.redis.get(_NS_PORTFOLIO)
        if raw:
            return Portfolio.model_validate(orjson.loads(raw))
        return None

    # ── RISK METRICS ──────────────────────────────────────────────────────────

    async def set_risk_metrics(self, metrics: RiskMetrics) -> None:
        data = orjson.dumps(metrics.model_dump(mode="json"))
        await self.redis.set(_NS_RISK, data, ex=120)

    async def get_risk_metrics(self) -> Optional[RiskMetrics]:
        raw = await self.redis.get(_NS_RISK)
        if raw:
            return RiskMetrics.model_validate(orjson.loads(raw))
        return None

    # ── KILL SWITCH ───────────────────────────────────────────────────────────

    async def activate_kill_switch(self, reason: str, ttl_seconds: int = 86400) -> None:
        await self.redis.setex(_NS_KILL_SWITCH, ttl_seconds, reason.encode())
        self._log.critical("kill switch activated", reason=reason)

    async def is_kill_switch_active(self) -> bool:
        return await self.redis.exists(_NS_KILL_SWITCH) > 0

    async def deactivate_kill_switch(self) -> None:
        await self.redis.delete(_NS_KILL_SWITCH)
        self._log.warning("kill switch deactivated")

    async def get_kill_switch_reason(self) -> Optional[str]:
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
            try:
                await lock.release()
            except Exception:
                pass

    # ── LATEST SIGNAL CACHE ───────────────────────────────────────────────────

    async def cache_signal(self, symbol: str, signal_type: str, data: dict[str, Any], ttl: int = 3600) -> None:
        key = _NS_SIGNAL.format(symbol=symbol, signal_type=signal_type)
        await self.redis.setex(key, ttl, orjson.dumps(data))

    async def get_cached_signal(self, symbol: str, signal_type: str) -> Optional[dict[str, Any]]:
        key = _NS_SIGNAL.format(symbol=symbol, signal_type=signal_type)
        raw = await self.redis.get(key)
        return orjson.loads(raw) if raw else None

    # ── PUB/SUB ───────────────────────────────────────────────────────────────

    async def publish(self, channel: str, data: dict[str, Any]) -> None:
        await self.redis.publish(channel, orjson.dumps(data))

    # ── GENERIC K/V ──────────────────────────────────────────────────────────

    async def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        data = orjson.dumps(value)
        if ttl:
            await self.redis.setex(key, ttl, data)
        else:
            await self.redis.set(key, data)

    async def get_json(self, key: str) -> Optional[Any]:
        raw = await self.redis.get(key)
        return orjson.loads(raw) if raw else None

    async def set_json_nx(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set `key` to JSON `value` only if it does not already exist (SET NX).
        Returns True if the key was written (did not exist), False otherwise.
        Used for idempotent decision records (e.g. routing decisions).
        """
        data = orjson.dumps(value)
        if ttl:
            result = await self.redis.set(key, data, ex=ttl, nx=True)
        else:
            result = await self.redis.set(key, data, nx=True)
        return result is not None

    async def delete_key(self, key: str) -> None:
        """Delete a key (no-op if it does not exist)."""
        await self.redis.delete(key)

    async def acquire_lease(self, key: str, owner: str, ttl_seconds: int) -> bool:
        """
        Acquire a short-lived ownership lease, or renew it if we already own it.

        Returns True if `owner` now holds the lease, False if another owner does.
        The lease auto-expires after `ttl_seconds`, so a dead owner is released
        without manual cleanup. Used to give one executor replica exclusive fill
        polling of an order without blocking the others permanently.
        """
        acquired = await self.redis.set(key, owner.encode(), ex=ttl_seconds, nx=True)
        if acquired:
            return True
        current = await self.redis.get(key)
        if current is not None and current.decode() == owner:
            # Renew our own lease so we keep polling across sweeps.
            await self.redis.set(key, owner.encode(), ex=ttl_seconds)
            return True
        return False

    async def release_lease(self, key: str, owner: str) -> None:
        """Release a lease only if we still own it (avoids dropping another's)."""
        current = await self.redis.get(key)
        if current is not None and current.decode() == owner:
            await self.redis.delete(key)

    async def scan_keys(self, pattern: str) -> list[str]:
        """
        Non-blocking enumeration of keys matching `pattern` using SCAN
        (never the blocking KEYS command). Returns decoded string keys.
        Used to recover durable execution state on startup.
        """
        keys: list[str] = []
        async for raw in self.redis.scan_iter(match=pattern, count=100):
            keys.append(raw.decode() if isinstance(raw, (bytes, bytearray)) else raw)
        return keys

    # ── LIFECYCLE ────────────────────────────────────────────────────────────

    async def shutdown(self) -> None:
        if self._redis:
            await self._redis.aclose()
        if self._pool:
            await self._pool.disconnect()
        self._log.info("state manager disconnected")


# Module-level singleton — imported by agents
state_manager = StateManager()
