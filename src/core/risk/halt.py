"""Authoritative, book-scoped halt state and generation-checked operator resets."""

from __future__ import annotations

import hmac
from typing import Any

from core.config import settings

GLOBAL_HALT_BOOK = "__alghrest_global__"


async def halted(conn: Any, book_id: str, *, require_initialized: bool = False) -> bool:
    identifiers = sorted({book_id, GLOBAL_HALT_BOOK})
    rows = await conn.fetch(
        "SELECT book_id,active FROM safety.halts WHERE book_id=ANY($1::text[]) ORDER BY book_id FOR SHARE",
        identifiers,
    )
    if len(rows) != len(identifiers):
        if require_initialized:
            raise RuntimeError("Book/global halt authority has not been initialized")
        return True
    return any(row["active"] for row in rows)


class RiskHaltStore:
    def __init__(self, pool: Any, book_id: str) -> None:
        self.pool, self.book_id = pool, book_id

    async def status(self) -> dict[str, Any]:
        row = await self.pool.fetchrow("SELECT * FROM safety.halts WHERE book_id=$1", self.book_id)
        if row is None:
            raise RuntimeError("Authoritative halt state has not been initialized")
        return dict(row)

    async def is_active(self) -> bool:
        async with self.pool.acquire() as conn, conn.transaction():
            return await halted(conn, self.book_id, require_initialized=True)

    async def activate(self, reason: str, actor: str = "risk-control") -> None:
        async with self.pool.acquire() as conn, conn.transaction():
            await self.activate_in_transaction(conn, reason, actor)

    async def activate_in_transaction(
        self, conn: Any, reason: str, actor: str = "risk-control"
    ) -> None:
        """Persist halt and audit atomically with a caller's broker mutation."""
        if not reason.strip() or not actor.strip():
            raise ValueError("Halt requires an actor and reason")
        generation = await conn.fetchval(
            """INSERT INTO safety.halts(book_id,active,reason,generation)
                   VALUES($1,true,$2,1) ON CONFLICT(book_id) DO UPDATE
                   SET active=true,reason=$2,generation=safety.halts.generation+1,updated_at=now()
                   RETURNING generation""",
            self.book_id,
            reason,
        )
        await conn.execute(
            """INSERT INTO safety.halt_events(book_id,generation,active,actor,reason)
                   VALUES($1,$2,true,$3,$4)""",
            self.book_id,
            generation,
            actor,
            reason,
        )

    async def reset(
        self, *, actor: str, reason: str, authorization: str, expected_generation: int
    ) -> None:
        authority = (
            settings.risk_global_reset_token
            if self.book_id == GLOBAL_HALT_BOOK
            else settings.risk_reset_token
        )
        token = authority.get_secret_value()
        if not token or not hmac.compare_digest(token, authorization):
            raise PermissionError("Authorized operator reset token is required")
        if not actor.strip() or not reason.strip():
            raise ValueError("Reset requires a named operator and reason")
        async with self.pool.acquire() as conn, conn.transaction():
            generation = await conn.fetchval(
                """UPDATE safety.halts SET active=false,reason=$3,updated_at=now()
                   WHERE book_id=$1 AND generation=$2 RETURNING generation""",
                self.book_id,
                expected_generation,
                reason,
            )
            if generation is None:
                raise RuntimeError("Halt generation changed; operator must review current state")
            await conn.execute(
                """INSERT INTO safety.halt_events(book_id,generation,active,actor,reason)
                   VALUES($1,$2,false,$3,$4)""",
                self.book_id,
                generation,
                actor,
                reason,
            )
