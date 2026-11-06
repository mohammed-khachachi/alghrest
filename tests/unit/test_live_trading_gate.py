"""Unit tests for Step 5: The 'Live Trading' Pre-Flight Gate."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiokafka.errors import SaslAuthenticationFailed
from pydantic import SecretStr

import scripts.live_preflight as live_preflight_cli
from connectors.exchanges.ccxt_connector import ExchangeConnector
from connectors.exchanges.conformance import ExternalSandboxBroker
from core.accounting.models import BookState, CashBalance, LedgerPosition
from core.accounting.repository import Ledger
from core.config import OrderExecutionDisabledError, settings
from core.data.models import Exchange, KafkaTopic
from core.execution.contracts import AccountScope
from core.execution.preflight import (
    KafkaAdminProbe,
    LiveTradingGateError,
    enforce_live_trading_gate,
    verify_account_balances,
    verify_db_latency,
    verify_kafka_acls,
)
from core.resilience import DatabaseCircuitBreaker


class _FakeKafkaAdmin(KafkaAdminProbe):
    """Fake Kafka admin client supporting both authenticated and anonymous probes."""

    def __init__(
        self,
        auth_options: dict[str, Any],
        *,
        topics: set[str] | None = None,
        reject_unauthenticated: bool = True,
    ) -> None:
        self.auth_options = auth_options
        self.topics = topics if topics is not None else {t.value for t in KafkaTopic}
        self.reject_unauthenticated = reject_unauthenticated
        self.started = False
        self.closed = False

    async def start(self) -> None:
        if not self.auth_options and self.reject_unauthenticated:
            raise SaslAuthenticationFailed("Anonymous connections denied by SASL_SSL broker")
        self.started = True

    async def list_topics(self) -> set[str]:
        return set(self.topics)

    async def close(self) -> None:
        self.closed = True


class _FakeTx:
    async def __aenter__(self) -> _FakeTx:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeConn:
    def __init__(self, pool: _FakePool) -> None:
        self._pool = pool

    async def __aenter__(self) -> _FakeConn:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def transaction(self) -> _FakeTx:
        return _FakeTx()

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        if "FROM safety.halts" in query and args:
            identifiers: list[str] = list(args[0])
            return [
                {"book_id": book_id, "active": self._pool.kill_switch_active}
                for book_id in identifiers
            ]
        return []


class _FakePool:
    """Fake asyncpg pool for testing database schema, kill switch, and latency SLAs."""

    def __init__(
        self,
        *,
        schema_ok: bool = True,
        kill_switch_active: bool = False,
    ) -> None:
        self.schema_ok = schema_ok
        self.kill_switch_active = kill_switch_active
        self.closed = False

    def acquire(self) -> _FakeConn:
        return _FakeConn(self)

    async def fetchval(self, query: str, *args: object) -> Any:
        if "to_regclass('accounting.books')" in query:
            return self.schema_ok
        if "SELECT 1" in query:
            return 1
        return None

    async def close(self) -> None:
        self.closed = True


def _make_funded_book() -> BookState:
    cash = CashBalance(
        exchange=Exchange.BINANCE,
        account_id="main",
        currency="USDT",
        amount=Decimal("25000"),
    )
    pos = LedgerPosition(
        exchange=Exchange.BINANCE,
        account_id="main",
        symbol="BTC/USDT",
        quantity=Decimal("1.5"),
        average_cost=Decimal("50000"),
        opened_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return BookState(
        revision=7,
        cash={cash.key: cash},
        positions={pos.key: pos},
    )


def _make_fake_ledger(
    *,
    book: BookState | None = None,
    schema_ok: bool = True,
    kill_switch_active: bool = False,
    circuit_open: bool = False,
) -> Ledger:
    pool = _FakePool(schema_ok=schema_ok, kill_switch_active=kill_switch_active)
    breaker = DatabaseCircuitBreaker(failure_threshold=1, recovery_timeout=60.0)
    if circuit_open:
        breaker.record_failure(RuntimeError("db connection lost"))
    ledger = Ledger(
        pool=pool,  # type: ignore[arg-type]
        book_id="live:primary",
        circuit_breaker=breaker,
    )
    loaded_book = book if book is not None else _make_funded_book()
    ledger.load = AsyncMock(return_value=loaded_book)  # type: ignore[method-assign]
    return ledger


def _deterministic_clock(step_seconds: float) -> Any:
    current = 100.0

    def _clock() -> float:
        nonlocal current
        val = current
        current += step_seconds
        return val

    return _clock


@pytest.fixture(autouse=True)
def _configure_live_gate_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set baseline SASL_SSL + account configuration with live_trading initially disabled."""
    monkeypatch.setattr(settings, "operating_profile", "general")
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(settings, "accounting_book", "primary")
    monkeypatch.setattr(settings, "live_trading", False)
    monkeypatch.setattr(settings, "live_preflight_verified", False)
    monkeypatch.setattr(settings, "enable_defi_agents", False)
    monkeypatch.setattr(settings, "kafka_security_protocol", "SASL_SSL")
    monkeypatch.setattr(settings, "kafka_sasl_mechanism", "SCRAM-SHA-512")
    monkeypatch.setattr(settings, "kafka_sasl_username", "alghrest_tier5_executor")
    monkeypatch.setattr(
        settings,
        "kafka_sasl_password",
        SecretStr("prod-scram-sha512-secret"),
    )
    monkeypatch.setattr(
        settings,
        "execution_accounts",
        [AccountScope(exchange=Exchange.BINANCE, account_id="main", symbols=["BTC/USDT"])],
    )
    monkeypatch.setattr(
        settings,
        "execution_balance_tolerances",
        {"USDT": Decimal("0.01"), "BTC": Decimal("0.000001")},
    )
    monkeypatch.setattr(settings, "live_max_db_latency_ms", 50.0)


@pytest.mark.unit
class TestLiveTradingPreflightGate:
    async def test_preflight_passes_all_checks_and_enables_live_trading(self) -> None:
        assert settings.live_trading is False
        assert settings.is_live is False

        async def _ledger_factory() -> Ledger:
            return _make_fake_ledger()

        async def _balance_fetcher(account: AccountScope) -> dict[str, Decimal]:
            assert account.exchange == Exchange.BINANCE
            assert account.account_id == "main"
            return {"USDT": Decimal("25000"), "BTC": Decimal("1.5")}

        report = await enforce_live_trading_gate(
            balance_fetcher=_balance_fetcher,
            admin_factory=lambda opts: _FakeKafkaAdmin(opts),
            ledger_factory=_ledger_factory,
            clock=_deterministic_clock(0.004),  # 4.0ms per probe (< 50.0ms SLA)
        )

        assert report.ready is True
        assert report.live_trading_enabled is True
        assert report.blocked_by == []
        assert report.checks == {
            "kafka_acls": True,
            "db_latency": True,
            "account_balances": True,
        }
        assert report.db_latency_ms == pytest.approx(4.0, abs=0.01)
        assert settings.live_trading is True
        assert settings.live_preflight_verified is True
        assert settings.environment == "live"
        assert settings.is_live is True

    async def test_plaintext_kafka_blocks_live_trading_activation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "kafka_security_protocol", "PLAINTEXT")
        # Even if env var prematurely set live_trading=True, preflight must revoke it.
        monkeypatch.setattr(settings, "live_trading", True)

        async def _ledger_factory() -> Ledger:
            return _make_fake_ledger()

        async def _balance_fetcher(_account: AccountScope) -> dict[str, Decimal]:
            return {"USDT": Decimal("25000"), "BTC": Decimal("1.5")}

        with pytest.raises(LiveTradingGateError, match="kafka_acls"):
            await enforce_live_trading_gate(
                balance_fetcher=_balance_fetcher,
                admin_factory=lambda opts: _FakeKafkaAdmin(opts),
                ledger_factory=_ledger_factory,
                clock=_deterministic_clock(0.003),
            )

        assert settings.live_trading is False
        assert settings.live_preflight_verified is False
        assert settings.is_live is False

    async def test_kafka_missing_topics_or_unauthenticated_access_blocks_gate(self) -> None:
        incomplete_topics = {t.value for t in KafkaTopic} - {KafkaTopic.ORDERS_EXECUTED.value}
        missing_topic_res = await verify_kafka_acls(
            admin_factory=lambda opts: _FakeKafkaAdmin(opts, topics=incomplete_topics),
        )
        assert missing_topic_res.passed is False
        assert "orders.executed" in (missing_topic_res.error or "")

        unauth_accepted_res = await verify_kafka_acls(
            admin_factory=lambda opts: _FakeKafkaAdmin(opts, reject_unauthenticated=False),
        )
        assert unauth_accepted_res.passed is False
        assert "unauthenticated connection" in (unauth_accepted_res.error or "")

    async def test_excessive_db_latency_blocks_live_trading_activation(self) -> None:
        async def _ledger_factory() -> Ledger:
            return _make_fake_ledger()

        async def _balance_fetcher(_account: AccountScope) -> dict[str, Decimal]:
            return {"USDT": Decimal("25000"), "BTC": Decimal("1.5")}

        with pytest.raises(LiveTradingGateError, match="db_latency"):
            await enforce_live_trading_gate(
                balance_fetcher=_balance_fetcher,
                admin_factory=lambda opts: _FakeKafkaAdmin(opts),
                ledger_factory=_ledger_factory,
                max_db_latency_ms=50.0,
                clock=_deterministic_clock(0.075),  # 75.0ms > 50.0ms threshold
            )

        assert settings.live_trading is False
        assert settings.live_preflight_verified is False

    async def test_open_circuit_breaker_or_active_kill_switch_blocks_db_preflight(self) -> None:
        open_breaker_res = await verify_db_latency(
            ledger_factory=lambda: _async_val(_make_fake_ledger(circuit_open=True)),
            clock=_deterministic_clock(0.002),
        )
        assert open_breaker_res.passed is False
        assert "circuit breaker is not CLOSED" in (open_breaker_res.error or "")

        halted_res = await verify_db_latency(
            ledger_factory=lambda: _async_val(_make_fake_ledger(kill_switch_active=True)),
            clock=_deterministic_clock(0.002),
        )
        assert halted_res.passed is False
        assert "kill switch is active" in (halted_res.error or "")

        missing_schema_res = await verify_db_latency(
            ledger_factory=lambda: _async_val(_make_fake_ledger(schema_ok=False)),
            clock=_deterministic_clock(0.002),
        )
        assert missing_schema_res.passed is False
        assert "tables are missing" in (missing_schema_res.error or "")

    async def test_account_balance_drift_blocks_live_trading_activation(self) -> None:
        async def _ledger_factory() -> Ledger:
            return _make_fake_ledger()

        async def _drifted_balance_fetcher(_account: AccountScope) -> dict[str, Decimal]:
            # Missing 0.25 BTC compared to BookState (1.5 BTC)
            return {"USDT": Decimal("25000"), "BTC": Decimal("1.25")}

        with pytest.raises(LiveTradingGateError, match="account_balances"):
            await enforce_live_trading_gate(
                balance_fetcher=_drifted_balance_fetcher,
                admin_factory=lambda opts: _FakeKafkaAdmin(opts),
                ledger_factory=_ledger_factory,
                clock=_deterministic_clock(0.003),
            )

        assert settings.live_trading is False
        assert settings.live_preflight_verified is False

    async def test_defi_agents_enabled_or_zero_capital_blocks_balance_preflight(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        zero_cash = CashBalance(
            exchange=Exchange.BINANCE,
            account_id="main",
            currency="USDT",
            amount=Decimal(0),
        )
        empty_book = BookState(
            revision=1,
            cash={zero_cash.key: zero_cash},
            positions={},
        )
        zero_cap_res = await verify_account_balances(
            balance_fetcher=lambda _acc: _async_val({"USDT": Decimal(0)}),
            ledger_factory=lambda: _async_val(_make_fake_ledger(book=empty_book)),
        )
        assert zero_cap_res.passed is False
        assert "zero funded balance" in (zero_cap_res.error or "")

        monkeypatch.setattr(settings, "enable_defi_agents", True)
        defi_res = await verify_account_balances(
            balance_fetcher=lambda _acc: _async_val({"USDT": Decimal("25000")}),
            ledger_factory=lambda: _async_val(_make_fake_ledger()),
        )
        assert defi_res.passed is False
        assert "ENABLE_DEFI_AGENTS=false" in (defi_res.error or "")

    async def test_advisory_profile_rejects_live_trading_gate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "operating_profile", "advisory")
        monkeypatch.setattr(settings, "live_trading", True)

        with pytest.raises(OrderExecutionDisabledError):
            await enforce_live_trading_gate(
                balance_fetcher=lambda _acc: _async_val({"USDT": Decimal("25000")}),
                admin_factory=lambda opts: _FakeKafkaAdmin(opts),
                ledger_factory=lambda: _async_val(_make_fake_ledger()),
            )

        assert settings.live_trading is False
        assert settings.live_preflight_verified is False

    async def test_cli_live_preflight_wires_exchange_connector_and_enables_live_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sandbox_broker = ExternalSandboxBroker(
            exchange=Exchange.BINANCE,
            initial_balances={"USDT": Decimal("25000"), "BTC": Decimal("1.5")},
            mark_prices={"BTC/USDT": Decimal("50000")},
        )

        async def _fake_connect(self: ExchangeConnector) -> None:
            self._client = sandbox_broker

        monkeypatch.setattr(ExchangeConnector, "connect", _fake_connect)
        monkeypatch.setattr(
            "core.execution.preflight._default_kafka_admin_factory",
            lambda opts: _FakeKafkaAdmin(opts),
        )
        monkeypatch.setattr(
            "core.execution.preflight._default_ledger_factory",
            lambda: _async_val(_make_fake_ledger()),
        )

        report = await live_preflight_cli.run_preflight(max_db_latency_ms=50.0)
        payload = report.to_dict()

        assert payload["ready"] is True
        assert payload["live_trading_enabled"] is True
        assert payload["book_id"] == "live:primary"
        assert settings.live_trading is True
        assert settings.environment == "live"


async def _async_val(value: Any) -> Any:
    return value
