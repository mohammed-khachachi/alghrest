"""Production Readiness Protocol: The 'Live Trading' Pre-Flight Gate.

Verifies Kafka SASL_SSL + worker ACL enforcement, PostgreSQL/TimescaleDB
schema & round-trip latency SLAs, and external broker account balance
reconciliation against the internal BookState before allowing
`live_trading=True` / `ENVIRONMENT=live` to take effect.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.errors import KafkaConnectionError, SaslAuthenticationFailed

from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import KafkaTopic
from core.execution.contracts import AccountScope, balance_differences, native_balances
from core.kafka.security import (
    KAFKA_ROLE_ACLS,
    SUPPORTED_SASL_MECHANISMS,
    aiokafka_security,
    authorize_topic_operation,
)
from core.resilience import CircuitState
from core.risk.halt import RiskHaltStore


class LiveTradingGateError(RuntimeError):
    """Raised when pre-flight checks fail and block `live_trading=True` activation."""


class KafkaAdminProbe(Protocol):
    """Protocol for Kafka admin client inspection during pre-flight."""

    async def start(self) -> None: ...
    async def list_topics(self) -> list[str] | set[str]: ...
    async def close(self) -> None: ...


BalanceFetcher = Callable[[AccountScope], Awaitable[dict[str, Decimal]]]
LedgerFactory = Callable[[], Awaitable[Ledger]]
KafkaAdminFactory = Callable[[dict[str, Any]], KafkaAdminProbe]


@dataclass(frozen=True)
class PreflightCheckResult:
    """Result of an individual pre-flight verification domain."""

    passed: bool
    details: dict[str, Any]
    error: str | None = None


@dataclass(frozen=True)
class LivePreflightReport:
    """Comprehensive pre-flight readiness report for live trading activation."""

    ready: bool
    live_trading_enabled: bool
    book_id: str
    checked_at: str
    db_latency_ms: float
    checks: dict[str, bool]
    blocked_by: list[str]
    details: dict[str, Any]
    errors: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "live_trading_enabled": self.live_trading_enabled,
            "book_id": self.book_id,
            "checked_at": self.checked_at,
            "db_latency_ms": round(self.db_latency_ms, 3),
            "checks": dict(self.checks),
            "blocked_by": list(self.blocked_by),
            "details": dict(self.details),
            "errors": dict(self.errors),
        }


def _default_kafka_admin_factory(auth_options: dict[str, Any]) -> KafkaAdminProbe:
    client: Any = AIOKafkaAdminClient(
        bootstrap_servers=settings.kafka_servers_list,
        request_timeout_ms=5000,
        **auth_options,
    )
    return client  # type: ignore[no-any-return]


async def _default_ledger_factory() -> Ledger:
    live_book_id = f"live:{settings.accounting_book}"
    return await Ledger.connect(settings.database_url, live_book_id)


def _verify_static_acl_matrix() -> tuple[bool, list[str]]:
    """Verify the in-memory worker role ACL policy enforces strict least privilege."""
    violations: list[str] = []
    required_roles = {
        "tier1_executive",
        "tier2_intelligence",
        "tier3_quant",
        "tier4_strategy",
        "tier5_router",
        "tier5_executor",
        "tier7_monitoring",
        "advisory_reader",
    }
    missing_roles = sorted(required_roles - set(KAFKA_ROLE_ACLS))
    if missing_roles:
        violations.append(f"Missing worker ACL roles: {missing_roles}")

    if not authorize_topic_operation("tier4_strategy", KafkaTopic.PROPOSALS_BUS.value, "Write"):
        violations.append("tier4_strategy must be allowed Write on proposals.bus")
    for forbidden_topic in (
        KafkaTopic.PROPOSALS_APPROVED.value,
        KafkaTopic.ORDERS_PENDING.value,
        KafkaTopic.ORDERS_APPROVED.value,
        KafkaTopic.ORDERS_EXECUTED.value,
        KafkaTopic.FILLS_CONFIRMED.value,
    ):
        if authorize_topic_operation("tier4_strategy", forbidden_topic, "Write"):
            violations.append(f"tier4_strategy must be denied Write on {forbidden_topic}")

    for exec_topic in (KafkaTopic.ORDERS_EXECUTED.value, KafkaTopic.FILLS_CONFIRMED.value):
        if not authorize_topic_operation("tier5_executor", exec_topic, "Write"):
            violations.append(f"tier5_executor must be allowed Write on {exec_topic}")
    if authorize_topic_operation("tier5_executor", KafkaTopic.ORDERS_PENDING.value, "Write"):
        violations.append("tier5_executor must be denied Write on orders.pending")

    for topic in KafkaTopic:
        if authorize_topic_operation("advisory_reader", topic.value, "Write"):
            violations.append(f"advisory_reader must be denied Write on {topic.value}")

    return len(violations) == 0, violations


async def verify_kafka_acls(
    *,
    admin_factory: KafkaAdminFactory | None = None,
    verify_negative_auth: bool = True,
) -> PreflightCheckResult:
    """Verify SASL_SSL transport, SCRAM/PLAIN credentials, ACL matrix, and all 18 Kafka topics."""
    resolved_admin_factory = admin_factory or _default_kafka_admin_factory
    previous_env = settings.environment
    try:
        # Force live validation rules on aiokafka_security() (requires SASL_SSL + non-empty credentials)
        settings.environment = "live"
        auth_options = aiokafka_security("trading")
    except Exception as exc:
        return PreflightCheckResult(
            passed=False,
            details={"protocol": settings.kafka_security_protocol},
            error=f"Kafka security validation failed: {exc}",
        )
    finally:
        settings.environment = previous_env

    mechanism = str(auth_options.get("sasl_mechanism", ""))
    if mechanism not in SUPPORTED_SASL_MECHANISMS:
        return PreflightCheckResult(
            passed=False,
            details={"sasl_mechanism": mechanism},
            error=f"Unsupported SASL mechanism: {mechanism}",
        )

    acl_ok, acl_violations = _verify_static_acl_matrix()
    if not acl_ok:
        return PreflightCheckResult(
            passed=False,
            details={"acl_violations": acl_violations},
            error="Worker ACL matrix failed least-privilege verification",
        )

    admin = resolved_admin_factory(auth_options)
    try:
        await admin.start()
        existing_topics = set(await admin.list_topics())
    except Exception as exc:
        return PreflightCheckResult(
            passed=False,
            details={"bootstrap_servers": settings.kafka_servers_list},
            error=f"Authenticated Kafka admin connection failed: {type(exc).__name__}: {exc}",
        )
    finally:
        await admin.close()

    required_topics = {t.value for t in KafkaTopic}
    missing_topics = sorted(required_topics - existing_topics)
    if missing_topics:
        return PreflightCheckResult(
            passed=False,
            details={"missing_topics": missing_topics},
            error=f"Missing required Kafka topics: {missing_topics}",
        )

    if verify_negative_auth:
        unauth_admin = resolved_admin_factory({})
        try:
            await unauth_admin.start()
        except (KafkaConnectionError, SaslAuthenticationFailed, TimeoutError, PermissionError):
            pass
        else:
            return PreflightCheckResult(
                passed=False,
                details={"negative_auth": "unauthenticated client accepted"},
                error="Kafka broker accepted an unauthenticated connection",
            )
        finally:
            await unauth_admin.close()

    return PreflightCheckResult(
        passed=True,
        details={
            "security_protocol": auth_options["security_protocol"],
            "sasl_mechanism": mechanism,
            "topics_verified": len(required_topics),
            "roles_verified": len(KAFKA_ROLE_ACLS),
            "negative_auth_rejected": verify_negative_auth,
        },
    )


async def verify_db_latency(
    *,
    ledger_factory: LedgerFactory | None = None,
    max_latency_ms: float | None = None,
    probes: int = 3,
    clock: Callable[[], float] = time.perf_counter,
) -> PreflightCheckResult:
    """Verify PostgreSQL/TimescaleDB schema, kill-switch state, and round-trip latency SLA."""
    resolved_ledger_factory = ledger_factory or _default_ledger_factory
    threshold_ms = max_latency_ms if max_latency_ms is not None else settings.live_max_db_latency_ms
    if threshold_ms <= 0 or probes < 1:
        raise ValueError("max_latency_ms must be > 0 and probes >= 1")

    try:
        ledger = await resolved_ledger_factory()
    except Exception as exc:
        return PreflightCheckResult(
            passed=False,
            details={"max_allowed_ms": threshold_ms},
            error=f"Database connection failed: {type(exc).__name__}: {exc}",
        )

    try:
        if ledger.circuit_breaker.state != CircuitState.CLOSED:
            return PreflightCheckResult(
                passed=False,
                details={"circuit_state": ledger.circuit_breaker.state.value},
                error="Database circuit breaker is not CLOSED",
            )

        schema_ok = await ledger.pool.fetchval(
            """SELECT to_regclass('accounting.books') IS NOT NULL
                  AND to_regclass('execution.books') IS NOT NULL
                  AND to_regclass('accounting.performance') IS NOT NULL
                  AND to_regclass('execution.authorizations') IS NOT NULL
                  AND to_regclass('safety.halts') IS NOT NULL
                  AND to_regclass('safety.halt_events') IS NOT NULL"""
        )
        if not schema_ok:
            return PreflightCheckResult(
                passed=False,
                details={"schema_ready": False},
                error="Required accounting/execution/risk database tables are missing",
            )

        halt_store = RiskHaltStore(ledger.pool, ledger.book_id)
        if await halt_store.is_active():
            return PreflightCheckResult(
                passed=False,
                details={"kill_switch_active": True},
                error="Authoritative book or global kill switch is active",
            )

        samples_ms: list[float] = []
        for _ in range(probes):
            start = clock()
            await ledger.pool.fetchval("SELECT 1")
            elapsed_ms = (clock() - start) * 1000.0
            samples_ms.append(elapsed_ms)

        max_observed_ms = max(samples_ms)
        avg_observed_ms = sum(samples_ms) / len(samples_ms)
        if max_observed_ms > threshold_ms:
            return PreflightCheckResult(
                passed=False,
                details={
                    "max_latency_ms": round(max_observed_ms, 3),
                    "avg_latency_ms": round(avg_observed_ms, 3),
                    "threshold_ms": threshold_ms,
                },
                error=(
                    f"Database latency {max_observed_ms:.2f}ms exceeds live threshold "
                    f"{threshold_ms:.2f}ms"
                ),
            )

        return PreflightCheckResult(
            passed=True,
            details={
                "max_latency_ms": round(max_observed_ms, 3),
                "avg_latency_ms": round(avg_observed_ms, 3),
                "threshold_ms": threshold_ms,
                "circuit_state": ledger.circuit_breaker.state.value,
                "kill_switch_active": False,
            },
        )
    except Exception as exc:
        return PreflightCheckResult(
            passed=False,
            details={"threshold_ms": threshold_ms},
            error=f"Database pre-flight probe failed: {type(exc).__name__}: {exc}",
        )
    finally:
        await ledger.close()


async def verify_account_balances(
    *,
    balance_fetcher: BalanceFetcher,
    ledger_factory: LedgerFactory | None = None,
) -> PreflightCheckResult:
    """Verify external exchange balances match internal BookState with zero unpermitted drift."""
    resolved_ledger_factory = ledger_factory or _default_ledger_factory
    if settings.enable_defi_agents:
        return PreflightCheckResult(
            passed=False,
            details={"enable_defi_agents": True},
            error="DeFi skeleton agents must remain disabled (ENABLE_DEFI_AGENTS=false) in live mode",
        )
    if not settings.execution_accounts:
        return PreflightCheckResult(
            passed=False,
            details={"execution_accounts": 0},
            error="No execution_accounts configured for live trading",
        )

    try:
        ledger = await resolved_ledger_factory()
    except Exception as exc:
        return PreflightCheckResult(
            passed=False,
            details={},
            error=f"Failed to connect ledger for balance reconciliation: {type(exc).__name__}: {exc}",
        )

    try:
        book = await ledger.load()
        expected_by_account = native_balances(book)
        reconciled_accounts: dict[str, dict[str, str]] = {}
        total_positive_assets = Decimal(0)

        for account in settings.execution_accounts:
            actual = await balance_fetcher(account)
            if any(not amount.is_finite() or amount < 0 for amount in actual.values()):
                return PreflightCheckResult(
                    passed=False,
                    details={"account": account.key},
                    error=f"Account {account.key} reported negative or non-finite spot balance",
                )
            expected = expected_by_account.get(account.key, {})
            diffs = balance_differences(
                expected,
                actual,
                settings.execution_balance_tolerances,
            )
            if diffs:
                return PreflightCheckResult(
                    passed=False,
                    details={"account": account.key, "differences": diffs},
                    error=f"Account {account.key} balances diverge from internal BookState: {diffs}",
                )
            total_positive_assets += sum((v for v in actual.values() if v > 0), Decimal(0))
            reconciled_accounts[account.key] = {k: str(v) for k, v in sorted(actual.items())}

        if total_positive_assets <= 0:
            return PreflightCheckResult(
                passed=False,
                details={"total_positive_assets": "0"},
                error="Live accounts have zero funded balance",
            )

        return PreflightCheckResult(
            passed=True,
            details={
                "book_revision": book.revision,
                "accounts_verified": len(settings.execution_accounts),
                "balances": reconciled_accounts,
            },
        )
    except Exception as exc:
        return PreflightCheckResult(
            passed=False,
            details={},
            error=f"Account balance verification failed: {type(exc).__name__}: {exc}",
        )
    finally:
        await ledger.close()


async def enforce_live_trading_gate(
    *,
    balance_fetcher: BalanceFetcher,
    admin_factory: KafkaAdminFactory | None = None,
    ledger_factory: LedgerFactory | None = None,
    max_db_latency_ms: float | None = None,
    verify_negative_auth: bool = True,
    clock: Callable[[], float] = time.perf_counter,
    raise_on_failure: bool = True,
) -> LivePreflightReport:
    """Execute the full live-trading pre-flight checklist and gate `settings.live_trading`."""
    # Fail closed immediately: live_trading remains disabled until every check passes.
    settings.live_trading = False
    settings.live_preflight_verified = False
    settings.require_order_execution()

    kafka_res = await verify_kafka_acls(
        admin_factory=admin_factory,
        verify_negative_auth=verify_negative_auth,
    )
    db_res = await verify_db_latency(
        ledger_factory=ledger_factory,
        max_latency_ms=max_db_latency_ms,
        clock=clock,
    )
    balance_res = await verify_account_balances(
        balance_fetcher=balance_fetcher,
        ledger_factory=ledger_factory,
    )

    checks = {
        "kafka_acls": kafka_res.passed,
        "db_latency": db_res.passed,
        "account_balances": balance_res.passed,
    }
    errors: dict[str, str] = {}
    for name, res in (
        ("kafka_acls", kafka_res),
        ("db_latency", db_res),
        ("account_balances", balance_res),
    ):
        if res.error:
            errors[name] = res.error

    blocked_by = [name for name, passed in checks.items() if not passed]
    ready = len(blocked_by) == 0

    if ready:
        settings.environment = "live"
        settings.live_trading = True
        settings.live_preflight_verified = True
    else:
        if settings.environment == "live":
            settings.environment = "paper_trading"
        settings.live_trading = False
        settings.live_preflight_verified = False

    db_latency_val = float(db_res.details.get("max_latency_ms", 0.0))
    report = LivePreflightReport(
        ready=ready,
        live_trading_enabled=settings.live_trading and settings.live_preflight_verified,
        book_id=f"live:{settings.accounting_book}",
        checked_at=datetime.now(UTC).isoformat(),
        db_latency_ms=db_latency_val,
        checks=checks,
        blocked_by=blocked_by,
        details={
            "kafka_acls": kafka_res.details,
            "db_latency": db_res.details,
            "account_balances": balance_res.details,
        },
        errors=errors,
    )

    if not ready and raise_on_failure:
        raise LiveTradingGateError(
            f"Live trading activation blocked by failed pre-flight checks: {blocked_by} ({errors})"
        )
    return report
