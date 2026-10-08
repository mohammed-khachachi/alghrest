"""Explicit paper-book preparation and read-only recovery status.

python -m scripts.paper prepare opening.json accounts.json [--apply]
python -m scripts.paper status
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import TypeAdapter

from connectors.exchanges.paper import PaperVenue
from core.accounting.funding import Deposit, PaperDeposits
from core.accounting.models import BookState, OpeningBalances
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import Exchange
from core.execution.contracts import AccountScope, native_balances
from core.execution.store import ExecutionStore
from core.orchestrator.state_manager import StateManager


def validate(opening_path: Path, accounts_path: Path) -> tuple[OpeningBalances, list[AccountScope]]:
    if settings.environment != "paper_trading":
        raise ValueError("Select ENVIRONMENT=paper_trading explicitly")
    opening = OpeningBalances.model_validate_json(opening_path.read_text())
    accounts = TypeAdapter(list[AccountScope]).validate_json(accounts_path.read_text())
    if opening.as_of > datetime.now(UTC):
        raise ValueError("Opening cutoff cannot be in the future")
    if not accounts or len({a.exchange for a in accounts}) != len(accounts):
        raise ValueError("Provide one explicit account per exchange")
    supported = {Exchange.BINANCE, Exchange.BYBIT, Exchange.COINBASE, Exchange.KRAKEN}
    if any(a.exchange not in supported for a in accounts):
        raise ValueError("Unsupported execution exchange")
    balances = native_balances(BookState.from_opening(opening))
    if set(balances) - {a.key for a in accounts}:
        raise ValueError("Opening holdings include an unconfigured account")
    if any(v < 0 for cash in balances.values() for v in cash.values()):
        raise ValueError("Spot paper accounts cannot open with borrowed assets")
    return opening, accounts


async def run(args: argparse.Namespace) -> None:
    if args.command == "deposit":
        deposit = Deposit.model_validate_json(args.deposit.read_text())
        if settings.environment != "paper_trading":
            raise ValueError("Select ENVIRONMENT=paper_trading explicitly")
        ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        state = StateManager()
        try:
            await state.initialize()
            receipt = await PaperDeposits(ledger, state).register(deposit, apply=args.apply)
            print(receipt.model_dump_json(indent=2))
            if not args.apply:
                print("Dry run: no balances changed. Append --apply to register this deposit.")
        finally:
            await state.shutdown()
            await ledger.close()
        return
    if args.command in {"provision", "preflight"}:
        from scripts.paper_runtime import preflight, provision

        report = await (provision() if args.command == "provision" else preflight())
        print(json.dumps(report, indent=2))
        if args.command == "preflight" and not report["ready"]:
            raise SystemExit(1)
        return
    if args.command == "prepare":
        opening, accounts = validate(args.opening, args.accounts)
        print(
            f"Validated {settings.accounting_book_id}: {len(accounts)} accounts; cutoff {opening.as_of.isoformat()}"
        )
        print("Use the same account scope for runtime EXECUTION_ACCOUNTS:")
        print(json.dumps([a.model_dump(mode="json") for a in accounts]))
        if not args.apply:
            print("Dry run. Append --apply to install migrations and prepare the paper book.")
            return
    ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
    store = ExecutionStore(ledger)
    try:
        if args.command == "prepare":
            root = Path(__file__).resolve().parents[1]
            for name in (
                "001_accounting.sql",
                "002_execution_recovery.sql",
                "003_funding_performance.sql",
            ):
                await ledger.pool.execute((root / "infra/migrations" / name).read_text())
            await store.claim_writer()  # refuse preparation while an executor owns the book
            saved = await ledger.pool.fetchval(
                "SELECT opening FROM accounting.books WHERE book_id=$1", ledger.book_id
            )
            if saved is None:
                await ledger.open_book(opening)
            elif OpeningBalances.model_validate_json(saved) != opening:
                raise ValueError("Existing opening differs; this command never reseeds a book")
            await store.configure(accounts)
            for account in accounts:
                await PaperVenue(store, account, None, settings.paper_fee_bps).initialize()
            print(
                "Paper book prepared. Trading remains blocked until runtime recovery, accounting and fresh valuation succeed."
            )
            print(
                "Start PortfolioAccountant, ExchangeExecutor and your market-data/price publisher services using the same environment and book."
            )
        else:
            report = await ledger.pool.fetchval(
                "SELECT report FROM execution.books WHERE book_id=$1", ledger.book_id
            )
            print(
                json.dumps(
                    {
                        "book_id": ledger.book_id,
                        "reconciliation": json.loads(report) if report else None,
                        "unresolved_orders": [
                            {
                                "client_order_id": str(row["client_order_id"]),
                                "phase": row["phase"],
                                "error": row["error"],
                            }
                            for row in await store.orders()
                        ],
                        "ledger_revision": (await ledger.load()).revision,
                    },
                    indent=2,
                )
            )
    finally:
        await store.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("opening", type=Path)
    prepare.add_argument("accounts", type=Path)
    prepare.add_argument("--apply", action="store_true")
    deposit = commands.add_parser("deposit", help="Validate an explicit new paper deposit")
    deposit.add_argument("deposit", type=Path)
    deposit.add_argument("--apply", action="store_true")
    commands.add_parser("status")
    commands.add_parser(
        "provision",
        help="Migrate and create topics in the isolated local paper stack; never fund a book",
    )
    commands.add_parser("preflight", help="Check actual activation readiness; exit 1 while blocked")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
