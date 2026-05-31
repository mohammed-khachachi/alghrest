"""Async TimescaleDB session lifecycle.

SQLAlchemy is imported lazily so unit tests can import the persistence package
without a live database driver installed.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from core.config import settings


class TimescaleSessionManager:
    """Owns the async SQLAlchemy engine used by persistence writers."""

    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or settings.database_url
        self._engine: Any | None = None
        self._sessionmaker: Any | None = None

    def _get_sessionmaker(self) -> Any:
        if self._sessionmaker is None:
            from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

            self._engine = create_async_engine(
                self.database_url,
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=10,
            )
            self._sessionmaker = async_sessionmaker(
                self._engine,
                expire_on_commit=False,
            )
        return self._sessionmaker

    @asynccontextmanager
    async def session(self) -> AsyncIterator[Any]:
        maker = self._get_sessionmaker()
        async with maker() as session:
            yield session

    async def dispose(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._sessionmaker = None


timescale_session_manager = TimescaleSessionManager()
