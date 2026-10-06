"""A session lease cannot run overlapping operations or release an active check."""

import asyncio
from unittest.mock import AsyncMock

import asyncpg
import pytest

from core.accounting.repository import Ledger
from core.execution.contracts import RecoveryBlockedError
from core.execution.store import ExecutionStore

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
