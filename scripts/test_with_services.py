"""Run the complete suite against docker-compose.paper.yml without funding runtime books.

Run from the repository root: poetry run python -m scripts.test_with_services -q
Provision the isolated stack first: poetry run python -m scripts.paper provision
Pytest arguments are forwarded; its configured 70% coverage gate remains enabled.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import asyncpg

from core.config import settings
from scripts.paper_runtime import require_local_paper

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def test_environment() -> dict[str, str]:
    """Require local paper endpoints before touching the dedicated test database."""
    require_local_paper()
    database = urlsplit(settings.database_url.replace("postgresql+asyncpg:", "postgresql:"))
    async with asyncio.timeout(15):
        admin = await asyncpg.connect(urlunsplit(database._replace(path="/postgres")))
        try:
            exists = await admin.fetchval(
                "SELECT 1 FROM pg_database WHERE datname='alghrest_quality'"
            )
            if not exists:
                await admin.execute("CREATE DATABASE alghrest_quality")
        finally:
            await admin.close()
    cache = urlsplit(settings.redis_url)
    return {
        **os.environ,
        "ACCOUNTING_TEST_DATABASE_URL": urlunsplit(database._replace(path="/alghrest_quality")),
        "ACCOUNTING_TEST_REDIS_URL": urlunsplit(cache._replace(path="/14")),
        # The smoke uses a unique book/topic and Redis DB 15, cleaning its own data.
        "PAPER_RUNTIME_TESTS": "1",
    }


def main() -> int:
    environment = asyncio.run(test_environment())
    return subprocess.call(
        [sys.executable, "-m", "pytest", *sys.argv[1:]], cwd=PROJECT_ROOT, env=environment
    )


if __name__ == "__main__":
    raise SystemExit(main())
