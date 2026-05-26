"""
tests/unit/conftest.py
=======================
Injects lightweight stubs for all heavy infrastructure packages that ALGHREST
imports at module level.  Stubs are inserted into sys.modules BEFORE pytest
collects any test file, so agent classes can be imported in unit tests without
a running Kafka / Redis stack and without the full Poetry venv.

Only injects if the real package is absent — venv runs are unaffected.

Full import chain that must be satisfied:
  agents/__init__.py
    → agents/base_agent.py
        → core/config.py                    (pydantic_settings.BaseSettings)
        → core/orchestrator/message_bus.py  (aiokafka, orjson, tenacity)
        → core/orchestrator/state_manager.py (redis.asyncio, redis.asyncio.lock)
        → core/utils/logging.py             (structlog)
        → core/utils/metrics.py             (prometheus_client)
        → psutil
"""

from __future__ import annotations

import json as _json
import sys
import types
from unittest.mock import AsyncMock, MagicMock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mod(name: str) -> types.ModuleType:
    """Create a stub module, register it, and return it."""
    m = types.ModuleType(name)
    sys.modules[name] = m
    return m


def _ensure(name: str) -> bool:
    """Return True if the module was NOT already present (i.e. we need to stub it)."""
    try:
        __import__(name)
        return False          # real package available — don't stub
    except (ImportError, ModuleNotFoundError):
        return True           # absent — stub needed


# ─────────────────────────────────────────────────────────────────────────────
# Stub definitions
# ─────────────────────────────────────────────────────────────────────────────

def _stub_tenacity() -> None:
    if not _ensure("tenacity"):
        return
    ten = _mod("tenacity")

    def _noop_deco(*a, **kw):
        return lambda f: f

    ten.retry = _noop_deco
    ten.stop_after_attempt = MagicMock(return_value=None)
    ten.wait_exponential = MagicMock(return_value=None)
    ten.retry_if_exception_type = MagicMock(return_value=None)
    ten.wait_fixed = MagicMock(return_value=None)

    # AsyncRetrying must be usable as `async with AsyncRetrying(...) as r:`
    class _AsyncRetrying:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass
        def __call__(self, *a, **kw): return self
        def __aiter__(self): return self
        async def __anext__(self): raise StopAsyncIteration

    ten.AsyncRetrying = _AsyncRetrying
    ten.RetryError = type("RetryError", (Exception,), {})
    ten.TryAgain = type("TryAgain", (Exception,), {})


def _stub_orjson() -> None:
    if not _ensure("orjson"):
        return
    orj = _mod("orjson")
    orj.dumps = lambda v, **kw: _json.dumps(v, default=str).encode()
    orj.loads = _json.loads
    orj.OPT_NON_STR_KEYS = 0
    orj.OPT_INDENT_2 = 2
    orj.JSONDecodeError = ValueError


def _stub_aiokafka() -> None:
    for name in ("aiokafka", "aiokafka.errors"):
        if not _ensure(name):
            continue
        m = _mod(name)
        m.AIOKafkaProducer = MagicMock
        m.AIOKafkaConsumer = MagicMock
        m.KafkaConnectionError = type("KafkaConnectionError", (Exception,), {})
        m.KafkaTimeoutError = type("KafkaTimeoutError", (Exception,), {})
        m.NodeNotReadyError = type("NodeNotReadyError", (Exception,), {})


def _stub_redis() -> None:
    # redis (top-level)
    if _ensure("redis"):
        r = _mod("redis")
        r.Redis = MagicMock
        r.StrictRedis = MagicMock
        r.ConnectionError = type("RedisConnectionError", (Exception,), {})
        r.RedisError = type("RedisError", (Exception,), {})

    # redis.asyncio  — must expose Redis, ConnectionPool
    if _ensure("redis.asyncio"):
        ra = _mod("redis.asyncio")
        _FakeConnectionPool = MagicMock
        _FakeRedis = MagicMock
        ra.Redis = _FakeRedis
        ra.ConnectionPool = _FakeConnectionPool
        ra.StrictRedis = _FakeRedis

    # redis.asyncio.lock  — must expose Lock
    if _ensure("redis.asyncio.lock"):
        ral = _mod("redis.asyncio.lock")
        ral.Lock = MagicMock


def _stub_prometheus() -> None:
    if not _ensure("prometheus_client"):
        return
    prom = _mod("prometheus_client")
    # Counters, Gauges etc. return objects with .labels().inc()/.set() etc.
    _metric = MagicMock
    prom.Counter = _metric
    prom.Gauge = _metric
    prom.Histogram = _metric
    prom.Summary = _metric
    prom.Info = _metric
    prom.REGISTRY = MagicMock()
    prom.start_http_server = MagicMock(return_value=None)


def _stub_psutil() -> None:
    if not _ensure("psutil"):
        return
    ps = _mod("psutil")
    _proc = MagicMock()
    _proc.memory_info.return_value.rss = 50 * 1024 * 1024
    ps.Process = MagicMock(return_value=_proc)


def _stub_structlog() -> None:
    if not _ensure("structlog"):
        return
    sl = _mod("structlog")
    _logger = MagicMock()
    _logger.bind.return_value = _logger
    sl.get_logger = MagicMock(return_value=_logger)
    sl.configure = MagicMock()
    sl.stdlib = MagicMock()
    sl.reset_defaults = MagicMock()


def _stub_pydantic_settings() -> None:
    if not _ensure("pydantic_settings"):
        return

    ps2 = _mod("pydantic_settings")

    class _BaseSettings:
        """Minimal stand-in so core/config.py::Settings inherits from something."""
        model_config: dict = {}

        def __init_subclass__(cls, **kw):
            super().__init_subclass__(**kw)

        def __init__(self, **kw):
            # Provide default attribute values that Settings expects
            for k, v in kw.items():
                setattr(self, k, v)

    ps2.BaseSettings = _BaseSettings
    ps2.SettingsConfigDict = dict


def _stub_misc() -> None:
    """Stub any other optional packages that might be imported."""
    for name in ("anthropic", "httpx", "ta", "pandas_ta", "aioredis"):
        if _ensure(name):
            _mod(name)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def inject_stubs() -> None:
    """
    Public entry point.  Called once when conftest.py is first imported by pytest.
    Order matters: lower-level stubs must be registered before higher-level ones.
    """
    _stub_tenacity()
    _stub_orjson()
    _stub_aiokafka()
    _stub_redis()
    _stub_prometheus()
    _stub_psutil()
    _stub_structlog()
    _stub_pydantic_settings()
    _stub_misc()


# ── Run immediately on conftest load (before any test file is collected) ──────
inject_stubs()
