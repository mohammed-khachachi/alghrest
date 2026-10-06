"""Journal and projection commit together under a PostgreSQL book-row lock."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import asyncpg

from core.accounting.engine import apply_fill, fingerprint, identity
from core.accounting.models import BookState, OpeningBalances, key, utc
from core.data.models import Fill


class FillConflictError(ValueError):
    """A previously booked exchange identity now has different economics."""


class Ledger:
    def __init__(self, pool: asyncpg.Pool, book_id: str) -> None:
        self.pool = pool
        self.book_id = book_id
        self._lease: Any = None
        self._lease_lock = asyncio.Lock()

    @classmethod
    async def connect(cls, dsn: str, book_id: str) -> Ledger:
        pool = await asyncpg.create_pool(
            dsn.replace("postgresql+asyncpg://", "postgresql://", 1),
            min_size=1,
            max_size=4,
            command_timeout=30,
        )
        return cls(pool, book_id)

    async def claim_writer(self) -> None:
        """Only one Kafka consumer/publisher per book; DB writers still serialize."""
        async with self._lease_lock:
            if self._lease is not None:
                raise RuntimeError("Accounting writer lease already claimed")
            lease = await self.pool.acquire()
            lock_id = int.from_bytes(
                hashlib.sha256(self.book_id.encode()).digest()[:8], signed=True
            )
            try:
                if not await lease.fetchval("SELECT pg_try_advisory_lock($1)", lock_id):
                    raise RuntimeError("Another accountant owns this book")
            except BaseException:
                # Includes cancellation: an unsuccessful claim must not retain
                # a pooled session or a possibly acquired session-level lock.
                await self.pool.release(lease)
                raise
            self._lease = lease

    async def check_writer(self) -> None:
        # Fill processing and snapshot publication share this asyncpg session.
        async with self._lease_lock:
            if self._lease is None or self._lease.is_closed():
                raise RuntimeError("Accounting writer lease lost")
            await self._lease.execute("SELECT 1")

    async def close(self) -> None:
        async with self._lease_lock:
            if self._lease is not None:
                # Pool reset releases session advisory locks, including on cancellation.
                await self.pool.release(self._lease)
                self._lease = None
            await self.pool.close()

    async def open_book(self, opening: OpeningBalances) -> None:
        if opening.as_of > datetime.now(UTC):
            raise ValueError("Opening cutoff cannot be in the future")
        # Unique PK intentionally refuses every reseed, even an identical import.
        await self.pool.execute(
            "INSERT INTO accounting.books(book_id, opening, state) VALUES($1,$2::jsonb,$3::jsonb)",
            self.book_id,
            opening.model_dump_json(),
            BookState.from_opening(opening).model_dump_json(),
        )

    @asynccontextmanager
    async def locked_state(self) -> AsyncIterator[tuple[Any, BookState, OpeningBalances]]:
        async with self.pool.acquire() as conn, conn.transaction():
            row = await conn.fetchrow(
                "SELECT * FROM accounting.books WHERE book_id=$1 FOR UPDATE",
                self.book_id,
            )
            if row is None:
                raise RuntimeError("Accounting book missing: explicitly import opening balances")
            if row["schema_version"] != 1:
                raise RuntimeError("Unsupported accounting schema")
            yield (
                conn,
                BookState.model_validate_json(row["state"]),
                OpeningBalances.model_validate_json(row["opening"]),
            )

    async def load(self) -> BookState:
        async with self.locked_state() as (_, state, _opening):
            return state

    async def record(self, fill: Fill) -> bool:
        scope = identity(fill)
        digest = fingerprint(fill)
        timestamp = utc(fill.timestamp)
        if timestamp > datetime.now(UTC) + timedelta(seconds=5):
            raise ValueError("Fill execution time is in the future")
        async with self.locked_state() as (conn, state, opening):
            existing = await conn.fetchval(
                """SELECT fingerprint FROM accounting.fills
                   WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4 AND trade_id=$5""",
                self.book_id,
                *scope,
            )
            if existing is not None:
                if existing != digest:
                    raise FillConflictError(
                        "Exchange trade identity conflicts with its durable journal entry"
                    )
                return False
            status = "before_opening" if timestamp <= opening.as_of else "applied"
            realized: dict[str, Decimal] = {}
            if status == "applied":
                # Cash postings commute; cost basis must follow exchange event time.
                realized = apply_fill(state, fill)
            await conn.execute(
                """INSERT INTO accounting.fills
                   (book_id,exchange,account_id,symbol,trade_id,occurred_at,fingerprint,payload,realized,status)
                   VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10)""",
                self.book_id,
                *scope,
                timestamp,
                digest,
                fill.model_dump_json(),
                json.dumps({c: str(v) for c, v in realized.items()}),
                status,
            )
            if status == "applied":
                newer = await conn.fetchval(
                    """SELECT EXISTS(SELECT 1 FROM accounting.fills
                       WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4
                       AND status='applied' AND (occurred_at,trade_id)>($5,$6))""",
                    self.book_id,
                    *scope[:3],
                    timestamp,
                    scope[3],
                )
                if newer:
                    # Rebuild only the affected market, preserving other cash/positions.
                    rebuilt = BookState.from_opening(opening)
                    rows = await conn.fetch(
                        """SELECT payload,trade_id FROM accounting.fills
                           WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4
                           AND status='applied' ORDER BY occurred_at,trade_id""",
                        self.book_id,
                        *scope[:3],
                    )
                    for row in rows:
                        pnl = apply_fill(rebuilt, Fill.model_validate_json(row["payload"]))
                        await conn.execute(
                            """UPDATE accounting.fills SET realized=$6::jsonb
                               WHERE book_id=$1 AND exchange=$2 AND account_id=$3 AND symbol=$4 AND trade_id=$5""",
                            self.book_id,
                            *scope[:3],
                            row["trade_id"],
                            json.dumps({c: str(v) for c, v in pnl.items()}),
                        )
                    position_key = key(*scope[:3])
                    state.positions.pop(position_key, None)
                    if position_key in rebuilt.positions:
                        state.positions[position_key] = rebuilt.positions[position_key]
            state.revision += 1
            await conn.execute(
                "UPDATE accounting.books SET state=$2::jsonb,updated_at=now() WHERE book_id=$1",
                self.book_id,
                state.model_dump_json(),
            )
            return True

    async def archive_opening_covered_message(self, message: dict[str, Any], fill: Fill) -> None:
        """Legacy messages need no invented trade ID when the opening covers them."""
        message_id = UUID(message["message_id"])
        async with self.locked_state() as (conn, _state, opening):
            if utc(fill.timestamp) > opening.as_of:
                raise ValueError("Post-opening fill requires a stable exchange trade ID")
            await conn.execute(
                """INSERT INTO accounting.opening_covered_messages(book_id,message_id,payload)
                   VALUES($1,$2,$3::jsonb) ON CONFLICT DO NOTHING""",
                self.book_id,
                message_id,
                json.dumps(message),
            )

    async def pnl_since(self, conn: Any, since: datetime) -> list[Any]:
        # Aggregate in SQL: snapshot memory is bounded by days/venues/currencies,
        # not the number of executions in the current week.
        rows = await conn.fetch(
            """SELECT exchange,account_id,occurred_at,jsonb_object_agg(currency,pnl) AS realized
               FROM (
                 SELECT exchange,account_id,
                   date_trunc('day',occurred_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS occurred_at,
                   entry.key AS currency,sum(entry.value::numeric)::text AS pnl
                 FROM accounting.fills CROSS JOIN LATERAL jsonb_each_text(realized) AS entry
                 WHERE book_id=$1 AND status='applied' AND occurred_at >= $2
                 GROUP BY exchange,account_id,3,entry.key
               ) totals GROUP BY exchange,account_id,occurred_at""",
            self.book_id,
            since,
        )
        return list(rows)
