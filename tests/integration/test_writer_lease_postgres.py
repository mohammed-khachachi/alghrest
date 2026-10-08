"""Opt-in real lease tests: SELECT/session locks only, no schema or financial writes."""

import asyncio
import os
from uuid import uuid4

import pytest

from core.accounting.repository import Ledger
from core.execution.contracts import RecoveryBlockedError
from core.execution.store import ExecutionStore

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("kind", ["accounting", "execution"])
async def test_real_concurrent_writer_checks_and_exclusion(kind):
    dsn = os.getenv("WRITER_LEASE_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set WRITER_LEASE_TEST_DATABASE_URL for SELECT-only lease verification")
    book_id = f"lease-verification:{uuid4()}"
    first = await Ledger.connect(dsn, book_id)
    writer = first if kind == "accounting" else ExecutionStore(first)
    other = None
    error = RuntimeError if kind == "accounting" else RecoveryBlockedError
    try:
        second = await Ledger.connect(dsn, book_id)
        other = second if kind == "accounting" else ExecutionStore(second)
        await writer.claim_writer()
        with pytest.raises(error, match="Another"):
            await other.claim_writer()
        await asyncio.gather(*(writer.check_writer() for _ in range(100)))
        await writer.close()
        # Releasing the first session must relinquish its advisory lock.
        await other.claim_writer()
        await asyncio.gather(*(other.check_writer() for _ in range(20)))
    finally:
        await writer.close()
        if other is not None:
            await other.close()
