"""Explicit paper deposits with one atomic journal/cash/venue/performance commit."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from typing import Any, Literal

import structlog
from pydantic import AwareDatetime, Field, TypeAdapter

from core.accounting import performance
from core.accounting.models import CashBalance, PositiveMoney, StrictModel, key
from core.accounting.repository import Ledger
from core.accounting.valuation import Valuation
from core.config import settings
from core.data.models import Exchange
from core.execution.contracts import AccountScope, balance_differences, native_balances

log = structlog.get_logger(__name__)


class Deposit(StrictModel):
    exchange: Exchange
    account_id: str = Field(default="default", min_length=1)
    currency: Literal["USDT"] = "USDT"
    amount: PositiveMoney
    reference: str = Field(min_length=1, max_length=200, pattern=r"^\S(?:.*\S)?$")

    def fingerprint(self) -> str:
        data = self.model_dump(mode="json")
        number = format(self.amount, "f")
        data["amount"] = number.rstrip("0").rstrip(".") if "." in number else number
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


class DepositReceipt(StrictModel):
    book_id: str
    deposit: Deposit
    applied: bool
    applied_at: AwareDatetime
    revision: int
    balance_before: Decimal
    balance_after: Decimal
    value_usd: PositiveMoney
    units_issued: PositiveMoney
    unit_price: PositiveMoney


class PaperDeposits:
    def __init__(self, ledger: Ledger, state: Any) -> None:
        self.ledger = ledger
        self.state = state

    async def register(self, deposit: Deposit, *, apply: bool = False) -> DepositReceipt:
        if settings.environment != "paper_trading" or not self.ledger.book_id.startswith(
            "paper_trading:"
        ):
            raise ValueError("Deposits require an explicit paper_trading book")
        configured = TypeAdapter(list[AccountScope]).validate_python(settings.execution_accounts)
        account_key = key(deposit.exchange.value, deposit.account_id)
        if account_key not in {a.key for a in configured}:
            raise ValueError("Deposit account is not configured")
        async with self.ledger.locked_state() as (conn, book, _opening):
            existing = await conn.fetchrow(
                """SELECT fingerprint,receipt FROM accounting.deposits
                WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND reference=$4""",
                self.ledger.book_id,
                deposit.exchange.value,
                deposit.account_id,
                deposit.reference,
            )
            if existing:
                if existing["fingerprint"] != deposit.fingerprint():
                    raise ValueError("Deposit reference conflicts with its durable receipt")
                receipt = DepositReceipt.model_validate_json(existing["receipt"])
            else:
                saved = await conn.fetchval(
                    "SELECT accounts FROM execution.books WHERE book_id=$1", self.ledger.book_id
                )
                if (
                    saved is None
                    or TypeAdapter(list[AccountScope]).validate_json(saved) != configured
                ):
                    raise ValueError("Configured account scope differs from durable paper book")
                # Order preparation also locks the book first. Paper fills lock
                # these account rows; holding all of them freezes venue inventory.
                rows = await conn.fetch(
                    "SELECT * FROM execution.paper_accounts WHERE book_id=$1 ORDER BY exchange,account_id FOR UPDATE",
                    self.ledger.book_id,
                )
                expected = native_balances(book)
                actual = {
                    key(r["exchange"], r["account_id"]): {
                        c: Decimal(v) for c, v in json.loads(r["balances"]).items()
                    }
                    for r in rows
                }
                if (
                    set(actual) != {a.key for a in configured}
                    or any(balance_differences(expected.get(k, {}), actual[k], {}) for k in actual)
                    or set(expected) - set(actual)
                ):
                    raise ValueError("Paper balances differ from ledger; reconcile before deposit")
                if await conn.fetchval(
                    """SELECT EXISTS(SELECT 1 FROM execution.orders WHERE book_id=$1 AND phase NOT IN ('complete','rejected'))
                    OR EXISTS(SELECT 1 FROM execution.paper_orders WHERE book_id=$1
                    AND payload->>'status' IN ('OPEN','PENDING','PARTIALLY_FILLED'))""",
                    self.ledger.book_id,
                ):
                    raise ValueError("Pending or uncertain orders block deposits")
                if await conn.fetchval(
                    """SELECT EXISTS(SELECT 1 FROM execution.fills e WHERE book_id=$1 AND NOT EXISTS (
                    SELECT 1 FROM accounting.fills f WHERE f.book_id=e.book_id AND f.exchange=e.exchange
                    AND f.account_id=e.account_id AND f.symbol=e.symbol AND f.trade_id=e.trade_id
                    AND f.fingerprint=e.fingerprint)) OR EXISTS(
                    SELECT 1 FROM execution.paper_fills p WHERE book_id=$1 AND NOT EXISTS (
                    SELECT 1 FROM accounting.fills f WHERE f.book_id=p.book_id AND f.exchange=p.exchange
                    AND f.account_id=p.account_id AND f.symbol=p.symbol AND f.trade_id=p.payload->>'exchange_trade_id'))""",
                    self.ledger.book_id,
                ):
                    raise ValueError("Unaccounted fills block deposits")
                now = datetime.now(UTC)
                valuation = Valuation(
                    self.state,
                    now,
                    settings.accounting_usd_pegs,
                    settings.accounting_mark_max_age_seconds,
                )
                portfolio = await valuation.portfolio(self.ledger.book_id, book, [])
                perf = performance.observe(
                    await performance.load(conn, self.ledger.book_id),
                    self.ledger.book_id,
                    book,
                    portfolio.total_capital + portfolio.unrealized_pnl,
                    now,
                )
                if perf.unit_price <= 0:
                    raise ValueError("Nonpositive performance index blocks funding")
                with localcontext() as ctx:
                    ctx.prec = 50
                    value = deposit.amount * await valuation.usd(
                        deposit.exchange.value, deposit.currency
                    )
                    issued = value / perf.unit_price
                    perf.units += issued
                    cash = CashBalance(
                        exchange=deposit.exchange,
                        account_id=deposit.account_id,
                        currency=deposit.currency,
                        amount=Decimal(0),
                    )
                    before = book.cash.get(cash.key, cash).amount
                    cash.amount = before + deposit.amount
                    book.cash[cash.key] = cash
                    actual[account_key][deposit.currency] = (
                        actual[account_key].get(deposit.currency, Decimal(0)) + deposit.amount
                    )
                    book.revision += 1
                    perf.revision = book.revision
                receipt = DepositReceipt(
                    book_id=self.ledger.book_id,
                    deposit=deposit,
                    applied=apply,
                    applied_at=now,
                    revision=book.revision,
                    balance_before=before,
                    balance_after=cash.amount,
                    value_usd=value,
                    units_issued=issued,
                    unit_price=perf.unit_price,
                )
                if apply:
                    await conn.execute(
                        """INSERT INTO accounting.deposits(book_id,exchange,account_id,reference,fingerprint,receipt,applied_at)
                        VALUES($1,$2,$3,$4,$5,$6::jsonb,$7)""",
                        self.ledger.book_id,
                        deposit.exchange.value,
                        deposit.account_id,
                        deposit.reference,
                        deposit.fingerprint(),
                        receipt.model_dump_json(),
                        now,
                    )
                    await conn.execute(
                        "UPDATE accounting.books SET state=$2::jsonb,updated_at=now() WHERE book_id=$1",
                        self.ledger.book_id,
                        book.model_dump_json(),
                    )
                    await conn.execute(
                        "UPDATE execution.paper_accounts SET balances=$4::jsonb WHERE book_id=$1 AND exchange=$2 AND account_id=$3",
                        self.ledger.book_id,
                        deposit.exchange.value,
                        deposit.account_id,
                        json.dumps({c: str(v) for c, v in actual[account_key].items()}),
                    )
                    await performance.save(conn, perf)
                    await conn.execute(
                        """UPDATE execution.books SET ready=false,verified_until=NULL,
                        report='{"reason":"deposit committed; fresh snapshot and reconciliation required"}'::jsonb,
                        updated_at=now() WHERE book_id=$1""",
                        self.ledger.book_id,
                    )
        if apply:
            # Cash is already committed. A cache outage must never suggest a
            # new reference/reapplication; replay the original receipt instead.
            try:
                await self.state.invalidate_portfolio()
                await self.state.redis.delete(f"alghrest:reconciliation:{self.ledger.book_id}")
            except Exception:
                log.warning(
                    "deposit_committed_cache_invalidation_failed",
                    book_id=self.ledger.book_id,
                    reference=deposit.reference,
                )
        return receipt
