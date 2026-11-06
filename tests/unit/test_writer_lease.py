"""A session lease cannot run overlapping operations or release an active check."""

import asyncio
from unittest.mock import AsyncMock

import asyncpg
import pytest

from core.accounting.repository import Ledger
from core.execution.contracts import RecoveryBlockedError
from core.execution.store import ExecutionStore
from core.resilience import (
    CircuitState,
    DatabaseCircuitBreaker,
    DatabaseCircuitOpenError,
    ExponentialBackoffPolicy,
)

pytestmark = pytest.mark.unit


class ExclusiveConnection:
    """Fault-injection connection with asyncpg's one-operation-at-a-time contract."""

    def __init__(self):
        self.active = 0
        self.maximum = 0
        self.closed = False
        self.checks = 0
        self.entered = asyncio.Event()
        self.resume = asyncio.Event()
        self.resume.set()
        self.granted = True
        self.claim_error = None
        self.check_error = None

    def is_closed(self):
        return self.closed

    async def operation(self):
        if self.active:
            raise asyncpg.InterfaceError(
                "cannot perform operation: another operation is in progress"
            )
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        self.entered.set()
        try:
            await self.resume.wait()
            await asyncio.sleep(0)
        finally:
            self.active -= 1

    async def fetchval(self, sql, *_args):
        assert sql == "SELECT pg_try_advisory_lock($1)"
        await self.operation()
        if self.claim_error:
            raise self.claim_error
        return self.granted

    async def execute(self, sql):
        assert sql == "SELECT 1"
        await self.operation()
        if self.check_error:
            raise self.check_error
        self.checks += 1
        return "SELECT 1"


@pytest.fixture(params=["accounting", "execution"])
def writer(request):
    connection = ExclusiveConnection()
    pool = AsyncMock()
    pool.acquire.return_value = connection

    async def release(lease):
        assert lease is connection
        assert not lease.active, "Released a connection during an active operation"

    pool.release.side_effect = release
    ledger = Ledger(pool, "lease-test")
    if request.param == "accounting":
        return ledger, pool, connection, RuntimeError
    return ExecutionStore(ledger), pool, connection, RecoveryBlockedError


async def test_simultaneous_checks_never_overlap_on_shared_connection(writer):
    store, pool, connection, _error = writer
    await store.claim_writer()
    await asyncio.gather(*(store.check_writer() for _ in range(50)))
    assert connection.checks == 50
    assert connection.maximum == 1
    pool.acquire.assert_awaited_once()
    await store.close()
    pool.release.assert_awaited_once()


async def test_close_waits_for_active_check_and_queued_checks_fail_closed(writer):
    store, pool, connection, error = writer
    await store.claim_writer()
    connection.entered.clear()
    connection.resume.clear()
    checking = asyncio.create_task(store.check_writer())
    await connection.entered.wait()
    closing = asyncio.create_task(store.close())
    queued = asyncio.create_task(store.check_writer())
    await asyncio.sleep(0)
    pool.release.assert_not_awaited()
    connection.resume.set()
    await checking
    await closing
    with pytest.raises(error, match="lease lost"):
        await queued
    pool.release.assert_awaited_once()


async def test_repeated_claim_cannot_replace_or_leak_owned_session(writer):
    store, pool, connection, error = writer
    await store.claim_writer()
    with pytest.raises(error, match="already"):
        await store.claim_writer()
    assert store._lease is connection
    pool.acquire.assert_awaited_once()
    await store.close()


async def test_failed_claim_releases_acquired_connection(writer):
    store, pool, connection, _error = writer
    connection.claim_error = asyncpg.ConnectionDoesNotExistError("connection dropped")
    with pytest.raises(asyncpg.ConnectionDoesNotExistError):
        await store.claim_writer()
    assert store._lease is None
    pool.release.assert_awaited_once()
    await store.close()
    pool.release.assert_awaited_once()


async def test_cancelled_claim_releases_session_and_allows_retry(writer):
    store, pool, connection, _error = writer
    connection.resume.clear()
    claiming = asyncio.create_task(store.claim_writer())
    await connection.entered.wait()
    claiming.cancel()
    with pytest.raises(asyncio.CancelledError):
        await claiming
    assert store._lease is None
    assert connection.active == 0
    pool.release.assert_awaited_once()
    connection.resume.set()
    await store.claim_writer()
    await store.check_writer()
    await store.close()
    assert pool.release.await_count == 2


async def test_denied_claim_cannot_be_used_as_writer(writer):
    store, pool, connection, error = writer
    connection.granted = False
    with pytest.raises(error, match="Another"):
        await store.claim_writer()
    with pytest.raises(error, match="lease lost"):
        await store.check_writer()
    assert connection.checks == 0
    pool.release.assert_awaited_once()
    await store.close()


async def test_missing_or_closed_lease_blocks_check(writer):
    store, _pool, connection, error = writer
    with pytest.raises(error, match="lease lost"):
        await store.check_writer()
    await store.claim_writer()
    connection.closed = True
    with pytest.raises(error, match="lease lost"):
        await store.check_writer()
    assert connection.checks == 0
    await store.close()


async def test_cancelled_check_releases_mutex_for_next_check(writer):
    store, _pool, connection, _error = writer
    await store.claim_writer()
    connection.entered.clear()
    connection.resume.clear()
    checking = asyncio.create_task(store.check_writer())
    await connection.entered.wait()
    checking.cancel()
    with pytest.raises(asyncio.CancelledError):
        await checking
    connection.resume.set()
    await store.check_writer()
    assert connection.checks == 1
    assert connection.maximum == 1
    await store.close()


async def test_check_connection_failure_propagates_without_ownership_reacquisition(writer):
    store, pool, connection, _error = writer
    await store.claim_writer()
    connection.check_error = asyncpg.ConnectionDoesNotExistError("connection dropped")
    with pytest.raises(asyncpg.ConnectionDoesNotExistError):
        await store.check_writer()
    pool.acquire.assert_awaited_once()
    await store.close()


async def test_concurrent_claims_acquire_one_session_and_refuse_second_owner(writer):
    store, pool, connection, error = writer
    first = asyncio.create_task(store.claim_writer())
    second = asyncio.create_task(store.claim_writer())
    outcomes = await asyncio.gather(first, second, return_exceptions=True)
    assert sum(result is None for result in outcomes) == 1
    assert sum(isinstance(result, error) for result in outcomes) == 1
    pool.acquire.assert_awaited_once()
    assert store._lease is connection
    await store.close()


def test_circuit_breaker_transitions_closed_open_half_open_closed():
    now = [100.0]
    breaker = DatabaseCircuitBreaker(
        "test-db",
        failure_threshold=2,
        recovery_timeout=5.0,
        half_open_max_calls=1,
        clock=lambda: now[0],
    )
    assert breaker.state == CircuitState.CLOSED
    breaker.check()

    breaker.record_failure(asyncpg.ConnectionDoesNotExistError("drop 1"))
    assert breaker.state == CircuitState.CLOSED
    breaker.record_failure(asyncpg.ConnectionDoesNotExistError("drop 2"))
    assert breaker.state == CircuitState.OPEN

    with pytest.raises(DatabaseCircuitOpenError, match="is OPEN"):
        breaker.check()

    # Advance clock past recovery_timeout -> HALF_OPEN
    now[0] += 5.5
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.check()  # consumes the single half-open probe slot
    with pytest.raises(DatabaseCircuitOpenError, match="HALF_OPEN"):
        breaker.check()

    # Failed probe re-opens immediately
    breaker.record_failure(asyncpg.ConnectionDoesNotExistError("probe failed"))
    assert breaker.state == CircuitState.OPEN

    # Advance clock again and succeed -> CLOSED
    now[0] += 6.0
    assert breaker.state == CircuitState.HALF_OPEN
    breaker.check()
    breaker.record_success()
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


async def test_exponential_backoff_retries_transient_errors_and_trips_breaker():
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    policy = ExponentialBackoffPolicy(
        base_delay=0.05,
        max_delay=0.5,
        max_attempts=3,
        jitter_ratio=0.0,
        sleep=fake_sleep,
    )
    breaker = DatabaseCircuitBreaker("test-backoff", failure_threshold=2, recovery_timeout=10.0)
    calls = 0

    async def flaky_op() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise asyncpg.ConnectionDoesNotExistError("transient reset")
        return "recovered"

    result = await policy.run(flaky_op, circuit_breaker=breaker)
    assert result == "recovered"
    assert calls == 3
    assert delays == [0.05, 0.1]
    assert breaker.state == CircuitState.CLOSED

    # Non-transient error does not retry
    non_transient_calls = 0

    async def bad_query() -> None:
        nonlocal non_transient_calls
        non_transient_calls += 1
        raise ValueError("syntax or domain error")

    with pytest.raises(ValueError, match="syntax or domain error"):
        await policy.run(bad_query, circuit_breaker=breaker)
    assert non_transient_calls == 1


async def test_ensure_writer_automatically_recovers_dropped_session_lease(writer):
    store, pool, first_conn, _error = writer
    second_conn = ExclusiveConnection()
    pool.acquire.side_effect = [first_conn, second_conn]

    released: list[ExclusiveConnection] = []

    async def release(lease):
        assert not lease.active, "Released a connection during an active operation"
        released.append(lease)

    pool.release.side_effect = release

    await store.claim_writer()
    assert store._lease is first_conn

    # Simulate underlying PostgreSQL session drop
    first_conn.closed = True
    await store.ensure_writer()

    assert store._lease is second_conn
    assert first_conn in released
    assert pool.acquire.await_count == 2

    # Subsequent ensure_writer probes liveness on the recovered lease without re-acquiring
    await store.ensure_writer()
    assert second_conn.checks == 1
    assert pool.acquire.await_count == 2
    await store.close()
