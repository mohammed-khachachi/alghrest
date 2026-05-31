"""Repository for persisting mapped Kafka events into TimescaleDB."""

from __future__ import annotations

from typing import Any

from core.persistence.database import TimescaleSessionManager, timescale_session_manager
from core.persistence.events import PersistenceStatement, build_persistence_statements


class TimescalePersistenceRepository:
    """Executes persistence statements in a single transaction per Kafka event."""

    def __init__(self, session_manager: TimescaleSessionManager | None = None) -> None:
        self._session_manager = session_manager or timescale_session_manager

    async def persist_kafka_message(self, message: dict[str, Any]) -> int:
        statements = build_persistence_statements(message)
        if not statements:
            return 0

        async with self._session_manager.session() as session:
            try:
                for statement in statements:
                    await self._execute(session, statement)
                await session.commit()
            except Exception:
                rollback = getattr(session, "rollback", None)
                if rollback is not None:
                    await rollback()
                raise

        return len(statements)

    async def close(self) -> None:
        await self._session_manager.dispose()

    @staticmethod
    async def _execute(session: Any, statement: PersistenceStatement) -> None:
        await session.execute(_sql_text(statement.sql), statement.params)


def _sql_text(sql: str) -> Any:
    try:
        from sqlalchemy import text
    except ImportError:
        return sql
    return text(sql)
