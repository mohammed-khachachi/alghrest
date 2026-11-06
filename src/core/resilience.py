"""Database session resilience: exponential backoff, circuit breakers, and transient fault classification."""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

import asyncpg
import structlog

log = structlog.get_logger(__name__)

T = TypeVar("T")

_TRANSIENT_ASYNCPG_ERRORS: tuple[type[BaseException], ...] = (
    asyncpg.PostgresConnectionError,
    asyncpg.InterfaceError,
    asyncpg.CannotConnectNowError,
    asyncpg.TooManyConnectionsError,
    asyncpg.InternalServerError,
)


class CircuitState(StrEnum):
    """States of the database session circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class DatabaseCircuitOpenError(RuntimeError):
    """Raised when the database session circuit breaker is open and fast-failing requests."""


def is_transient_db_error(exc: BaseException) -> bool:
    """Return True if `exc` represents a recoverable database connection or session drop."""
    if isinstance(exc, asyncio.CancelledError | DatabaseCircuitOpenError):
        return False
    if isinstance(exc, _TRANSIENT_ASYNCPG_ERRORS):
        return True
    if isinstance(exc, ConnectionError | TimeoutError | OSError):
        return True
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "connection is closed",
            "connection was closed",
            "connection does not exist",
            "pool is closed",
            "writer lease lost",
            " underlying connection ",
            "connection reset",
            "server closed the connection",
        )
    )


class DatabaseCircuitBreaker:
    """
    State-machine circuit breaker protecting database session recovery.

    - `CLOSED`: normal operation; transient failures increment `failure_count`.
    - `OPEN`: tripped after `failure_threshold` consecutive failures; fast-fails for
      `recovery_timeout` seconds.
    - `HALF_OPEN`: permits up to `half_open_max_calls` probe attempts; a successful
      probe closes the circuit, while a failed probe re-opens it immediately.
    """

    def __init__(
        self,
        name: str = "postgres",
        *,
        failure_threshold: int = 3,
        recovery_timeout: float = 5.0,
        half_open_max_calls: int = 1,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")
        if half_open_max_calls < 1:
            raise ValueError("half_open_max_calls must be >= 1")
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self._clock = clock
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float | None = None
        self._half_open_in_flight: int = 0

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and self._opened_at is not None
            and self._clock() - self._opened_at >= self.recovery_timeout
        ):
            self._state = CircuitState.HALF_OPEN
            self._half_open_in_flight = 0
        return self._state

    def check(self) -> None:
        """Raise `DatabaseCircuitOpenError` if the circuit currently forbids execution."""
        current = self.state
        if current == CircuitState.OPEN:
            raise DatabaseCircuitOpenError(
                f"Database circuit breaker '{self.name}' is OPEN "
                f"(failures={self._failure_count})"
            )
        if current == CircuitState.HALF_OPEN:
            if self._half_open_in_flight >= self.half_open_max_calls:
                raise DatabaseCircuitOpenError(
                    f"Database circuit breaker '{self.name}' is HALF_OPEN and probe is in flight"
                )
            self._half_open_in_flight += 1

    def record_success(self) -> None:
        """Reset failure counters and close the circuit after a healthy operation."""
        was_non_closed = self._state != CircuitState.CLOSED
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = None
        self._half_open_in_flight = 0
        if was_non_closed:
            log.info("db.circuit_breaker.closed", breaker=self.name)

    def record_failure(self, exc: BaseException | None = None) -> None:
        """Record a failed recovery attempt and trip the circuit if threshold is reached."""
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = self._clock()
            self._half_open_in_flight = 0
            log.warning(
                "db.circuit_breaker.opened",
                breaker=self.name,
                failures=self._failure_count,
                recovery_timeout=self.recovery_timeout,
                error=str(exc) if exc else None,
            )


class ExponentialBackoffPolicy:
    """Exponential backoff runner integrated with `DatabaseCircuitBreaker`."""

    def __init__(
        self,
        *,
        base_delay: float = 0.05,
        max_delay: float = 2.0,
        max_attempts: int = 3,
        jitter_ratio: float = 0.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        if base_delay < 0 or max_delay < 0 or max_attempts < 1:
            raise ValueError("Invalid exponential backoff parameters")
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_attempts = max_attempts
        self.jitter_ratio = jitter_ratio
        self._sleep = sleep

    def delay_for_attempt(self, attempt: int) -> float:
        factor = float(1 << max(0, attempt))
        raw = min(self.max_delay, self.base_delay * factor)
        if self.jitter_ratio > 0 and raw > 0:
            jitter = raw * self.jitter_ratio * random.random()
            return min(self.max_delay, raw + jitter)
        return raw

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        circuit_breaker: DatabaseCircuitBreaker | None = None,
        is_retryable: Callable[[BaseException], bool] = is_transient_db_error,
        on_retry: Callable[[int, BaseException], Awaitable[None]] | None = None,
    ) -> T:
        if circuit_breaker is not None:
            circuit_breaker.check()
        last_exc: BaseException | None = None
        for attempt in range(self.max_attempts):
            try:
                result = await operation()
                if circuit_breaker is not None:
                    circuit_breaker.record_success()
                return result
            except BaseException as exc:
                if not is_retryable(exc):
                    if (
                        circuit_breaker is not None
                        and circuit_breaker.state == CircuitState.HALF_OPEN
                    ):
                        circuit_breaker.record_failure(exc)
                    raise
                last_exc = exc
                if attempt + 1 >= self.max_attempts:
                    break
                if on_retry is not None:
                    await on_retry(attempt, exc)
                await self._sleep(self.delay_for_attempt(attempt))
        if circuit_breaker is not None:
            circuit_breaker.record_failure(last_exc)
        assert last_exc is not None
        raise last_exc
