"""Two books share one Redis database without sharing portfolio state."""

import os
from uuid import uuid4

import pytest
from pydantic import SecretStr

from core.config import settings
from core.orchestrator.state_manager import StateManager
from tests.factories import portfolio

pytestmark = pytest.mark.integration
pytest_plugins = ("tests.integration.test_execution_recovery",)


async def test_portfolio_publication_and_invalidation_are_book_local(monkeypatch):
    dsn = os.getenv("ACCOUNTING_TEST_REDIS_URL")
    if not dsn:
        pytest.skip("Requires disposable local Redis")
    monkeypatch.setattr(settings, "redis_url", dsn)
    token = uuid4().hex
    monkeypatch.setattr(settings, "accounting_book", f"isolation-a-{token}")
    a_id = settings.accounting_book_id
    a = StateManager()
    monkeypatch.setattr(settings, "accounting_book", f"isolation-b-{token}")
    b_id = settings.accounting_book_id
    b = StateManager()
    try:
        await a.initialize()
        await b.initialize()
        await a.set_portfolio(portfolio(accounting_book_id=a_id, total_capital="1000"))
        await b.set_portfolio(portfolio(accounting_book_id=b_id, total_capital="2000"))
        assert (await a.get_portfolio()).accounting_book_id == a_id
        assert (await b.get_portfolio()).accounting_book_id == b_id
        await a.invalidate_portfolio()
        assert await a.get_portfolio() is None
        assert (await b.get_portfolio()).accounting_book_id == b_id
    finally:
        await a.invalidate_portfolio()
        await b.invalidate_portfolio()
        await a.shutdown()
        await b.shutdown()


async def test_book_and_global_halts_have_independent_reset_authority(monkeypatch, recovery):
    from datetime import UTC, datetime

    from core.accounting.models import CashBalance, OpeningBalances
    from core.accounting.repository import Ledger
    from core.data.models import Exchange
    from core.execution.store import ExecutionStore

    r = recovery
    monkeypatch.setattr(settings, "database_url", os.environ["ACCOUNTING_TEST_DATABASE_URL"])
    monkeypatch.setattr(settings, "redis_url", os.environ["ACCOUNTING_TEST_REDIS_URL"])
    monkeypatch.setattr(settings, "risk_reset_token", SecretStr("test-book-reset"))
    monkeypatch.setattr(settings, "risk_global_reset_token", SecretStr("test-global-reset"))
    other = await Ledger.connect(settings.database_url, f"test:other-{uuid4()}")
    await other.open_book(
        OpeningBalances(
            as_of=datetime.now(UTC),
            reference="synthetic second book",
            cash=[CashBalance(exchange=Exchange.BINANCE, currency="USD", amount="1000")],
        )
    )
    other_store = ExecutionStore(other)
    await other_store.configure([r.account])
    a, b = StateManager(r.store.book_id), StateManager(other.book_id)
    try:
        await a.initialize()
        await b.initialize()
        await a.activate_kill_switch("book A only")
        assert await a.is_kill_switch_active()
        assert not await b.is_kill_switch_active()
        await a.activate_global_kill_switch("system emergency")
        assert await a.is_kill_switch_active() and await b.is_kill_switch_active()
        b_status = await (await b.halt_store()).status()
        await b.deactivate_kill_switch(
            actor="test operator",
            reason="book review cannot clear global",
            authorization="test-book-reset",
            expected_generation=b_status["generation"],
        )
        assert await b.is_kill_switch_active()
        global_status = await (await a.global_halt_store()).status()
        with pytest.raises(PermissionError):
            await a.deactivate_global_kill_switch(
                actor="test operator",
                reason="wrong authority",
                authorization="test-book-reset",
                expected_generation=global_status["generation"],
            )
        await a.deactivate_global_kill_switch(
            actor="test operator",
            reason="global review",
            authorization="test-global-reset",
            expected_generation=global_status["generation"],
        )
        assert await a.is_kill_switch_active() and not await b.is_kill_switch_active()
        a_status = await (await a.halt_store()).status()
        await a.deactivate_kill_switch(
            actor="test operator",
            reason="book review",
            authorization="test-book-reset",
            expected_generation=a_status["generation"],
        )
        assert not await a.is_kill_switch_active() and not await b.is_kill_switch_active()
    finally:
        await a.shutdown()
        await b.shutdown()
        await other.pool.execute("DELETE FROM execution.books WHERE book_id=$1", other.book_id)
        await other.pool.execute("DELETE FROM accounting.books WHERE book_id=$1", other.book_id)
        await other.close()
