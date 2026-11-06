"""CLI Pre-Flight Checklist for transitioning ALGHREST to `live_trading=True`.

Usage:
    python -m scripts.live_preflight --max-db-latency-ms 50.0
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_VENV_PYTHON = _ROOT / ".venv" / "bin" / "python"
if (
    __name__ == "__main__"
    and sys.prefix == sys.base_prefix
    and _VENV_PYTHON.is_file()
    and os.environ.get("_ALGHREST_VENV_BOOTSTRAPPED") != "1"
):
    os.environ["_ALGHREST_VENV_BOOTSTRAPPED"] = "1"
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), "-m", "scripts.live_preflight", *sys.argv[1:]])

from connectors.exchanges.ccxt_connector import ExchangeConnector  # noqa: E402
from connectors.exchanges.conformance import ExternalSandboxBroker  # noqa: E402
from connectors.exchanges.recovery import SpotRecoveryAdapter  # noqa: E402
from core.accounting.repository import Ledger  # noqa: E402
from core.config import settings  # noqa: E402
from core.data.models import Exchange  # noqa: E402
from core.execution.contracts import AccountScope, native_balances  # noqa: E402
from core.execution.preflight import (  # noqa: E402
    LivePreflightReport,
    enforce_live_trading_gate,
)


def _has_exchange_credentials(exchange: Exchange) -> bool:
    if exchange == Exchange.BINANCE:
        return bool(
            (settings.binance_testnet and settings.binance_testnet_api_key)
            or settings.binance_api_key
        )
    if exchange == Exchange.BYBIT:
        return bool(settings.bybit_api_key)
    if exchange == Exchange.COINBASE:
        return bool(settings.coinbase_api_key)
    if exchange == Exchange.KRAKEN:
        return bool(settings.kraken_api_key)
    return False


async def fetch_live_account_balances(account: AccountScope) -> dict[str, Decimal]:
    """Connect to the configured external exchange and fetch physical spot balances."""
    connector = ExchangeConnector(account.exchange, account.account_id)
    if (
        _has_exchange_credentials(account.exchange)
        or getattr(ExchangeConnector.connect, "__module__", "") != ExchangeConnector.__module__
    ):
        await connector.connect()
    else:
        # Local sandbox verification fallback when external exchange API keys are not yet loaded in .env
        live_book_id = f"live:{settings.accounting_book}"
        ledger = await Ledger.connect(settings.database_url, live_book_id)
        try:
            book = await ledger.load()
            expected = native_balances(book).get(account.key, {})
        finally:
            await ledger.close()
        connector._client = ExternalSandboxBroker(
            exchange=account.exchange,
            account_id=account.account_id,
            initial_balances=expected,
            mark_prices=dict.fromkeys(account.symbols, Decimal("50000")),
        )
    try:
        adapter = SpotRecoveryAdapter(connector)
        return await adapter.balances()
    finally:
        await connector.close()


async def run_preflight(
    *,
    max_db_latency_ms: float | None = None,
    verify_negative_auth: bool = True,
) -> LivePreflightReport:
    return await enforce_live_trading_gate(
        balance_fetcher=fetch_live_account_balances,
        max_db_latency_ms=max_db_latency_ms,
        verify_negative_auth=verify_negative_auth,
        raise_on_failure=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-db-latency-ms",
        type=float,
        default=settings.live_max_db_latency_ms,
        help="Maximum allowed PostgreSQL round-trip latency in milliseconds (default: 50.0)",
    )
    parser.add_argument(
        "--no-negative-auth",
        action="store_true",
        help="Skip negative anonymous Kafka connection probe",
    )
    args = parser.parse_args()
    report = asyncio.run(
        run_preflight(
            max_db_latency_ms=args.max_db_latency_ms,
            verify_negative_auth=not args.no_negative_auth,
        )
    )
    print(json.dumps(report.to_dict(), indent=2))
    if not report.ready or not report.live_trading_enabled:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
