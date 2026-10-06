"""Provision the isolated local paper stack and report actual activation readiness."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import TopicAlreadyExistsError

from core.accounting.models import BookState
from core.accounting.performance import load as load_performance
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import KafkaTopic
from core.orchestrator.state_manager import StateManager


def require_local_paper() -> None:
    """This provisioning command is only for docker-compose.paper.yml."""
    db, cache = urlsplit(settings.database_url), urlsplit(settings.redis_url)
    local = {"127.0.0.1", "localhost"}
    if (
        settings.environment != "paper_trading"
        or db.hostname not in local
        or db.port != 15432
        or db.path != "/alghrest_paper"
        or cache.hostname not in local
        or cache.port != 16379
        or settings.kafka_servers_list not in (["127.0.0.1:19092"], ["localhost:19092"])
    ):
        raise ValueError(
            "Provisioning requires paper_trading and the dedicated local paper endpoints"
        )


async def migrate(ledger: Ledger) -> None:
    root = Path(__file__).resolve().parents[1]
    for name in (
        "001_accounting.sql",
        "002_execution_recovery.sql",
        "003_funding_performance.sql",
        "004_ai_budget.sql",
    ):
        await ledger.pool.execute((root / "infra/migrations" / name).read_text())


async def provision() -> dict[str, Any]:
    require_local_paper()
    ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
    try:
        await migrate(ledger)
    finally:
        await ledger.close()
    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_servers_list, request_timeout_ms=10000
    )
    try:
        await admin.start()
        existing = set(await admin.list_topics())
        created = []
        for topic in KafkaTopic:
            if topic.value in existing:
                continue
            try:
                await admin.create_topics(
                    [
                        NewTopic(
                            topic.value,
                            num_partitions=3,
                            replication_factor=1,
                            topic_configs={"min.insync.replicas": "1", "retention.ms": "604800000"},
                        )
                    ]
                )
                created.append(topic.value)
            except TopicAlreadyExistsError:
                pass  # another provisioning invocation created it concurrently
        return {
            "migrations": "applied",
            "topics_created": created,
            "topics_required": len(KafkaTopic),
            "portfolio_opening": "not created by provisioning",
        }
    finally:
        await admin.close()


async def preflight() -> dict[str, Any]:
    checks = {
        name: False
        for name in (
            "paper_environment",
            "execution_scope",
            "database_schema",
            "opening_balances",
            "durable_performance",
            "execution_configuration",
            "database_reconciliation",
            "redis",
            "kafka_topics",
            "fresh_portfolio_and_reconciliation",
            "kill_switch_clear",
        )
    }
    errors: dict[str, str] = {}
    checks["paper_environment"] = settings.environment == "paper_trading"
    checks["execution_scope"] = bool(settings.execution_accounts)
    try:
        async with asyncio.timeout(15):
            ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
            try:
                tables = await ledger.pool.fetchval(
                    "SELECT to_regclass('accounting.books') IS NOT NULL AND to_regclass('execution.books') IS NOT NULL AND to_regclass('accounting.performance') IS NOT NULL AND to_regclass('accounting.deposits') IS NOT NULL"
                )
                checks["database_schema"] = bool(tables)
                if tables:
                    record = await ledger.pool.fetchrow(
                        """SELECT b.state,e.accounts,e.ready,e.verified_revision,e.verified_until
                           FROM accounting.books b LEFT JOIN execution.books e USING(book_id)
                           WHERE b.book_id=$1""",
                        ledger.book_id,
                    )
                    if record:
                        book = BookState.model_validate_json(record["state"])
                        checks["opening_balances"] = True
                        perf = await load_performance(ledger.pool, ledger.book_id)
                        checks["durable_performance"] = (
                            perf is not None and perf.revision == book.revision
                        )
                        checks["execution_configuration"] = record[
                            "accounts"
                        ] is not None and json.loads(record["accounts"]) == [
                            a.model_dump(mode="json") for a in settings.execution_accounts
                        ]
                        checks["database_reconciliation"] = bool(
                            record["ready"]
                            and record["verified_revision"] == book.revision
                            and record["verified_until"]
                            and record["verified_until"] > datetime.now(UTC)
                        )
            finally:
                await ledger.close()
    except Exception as exc:
        errors["database"] = type(exc).__name__
    state = StateManager()
    try:
        async with asyncio.timeout(10):
            await state.initialize()
            checks["redis"] = True
            checks["fresh_portfolio_and_reconciliation"] = await state.trading_ready()
            checks["kill_switch_clear"] = not await state.is_kill_switch_active()
    except Exception as exc:
        errors["redis"] = type(exc).__name__
    finally:
        await state.shutdown()
    admin = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_servers_list, request_timeout_ms=10000
    )
    missing: list[str] = []
    try:
        async with asyncio.timeout(15):
            await admin.start()
            missing = sorted({t.value for t in KafkaTopic} - set(await admin.list_topics()))
            checks["kafka_topics"] = not missing
    except Exception as exc:
        errors["kafka"] = type(exc).__name__
    finally:
        await admin.close()
    return {
        "book_id": settings.accounting_book_id,
        "ready": all(checks.values()),
        "checks": checks,
        "blocked_by": [name for name, passed in checks.items() if not passed],
        "missing_topics": missing,
        "errors": errors,
    }
