"""Explicit operator commands: python -m scripts.accounting --help."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from core.accounting.engine import apply_fill, fingerprint
from core.accounting.models import BookState, OpeningBalances
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import Fill


async def run(args: argparse.Namespace) -> None:
    book_id = settings.accounting_book_id
    if args.command == "open":
        opening = OpeningBalances.model_validate_json(args.file.read_text())
        print(
            f"Validated opening for {book_id}: {len(opening.cash)} cash balances, "
            f"{len(opening.positions)} positions; cutoff {opening.as_of.isoformat()}"
        )
        if not args.apply:
            print("Dry run. Use --apply to create this book once.")
            return
    elif args.command == "import-fills":
        fills = [Fill.model_validate(item) for item in json.loads(args.file.read_text())]
        # Validate contracts/economics before writing. Database conflicts can
        # still stop a partially committed import; a retry is idempotent.
        for fill in fills:
            fingerprint(fill)
            apply_fill(BookState(), fill)
        if not args.apply:
            print(f"Validated {len(fills)} fills for {book_id}. Use --apply to import.")
            return
    ledger = await Ledger.connect(settings.database_url, book_id)
    try:
        if args.command == "open":
            await ledger.open_book(opening)
            print(f"Created {book_id}; no existing book can be reseeded.")
        elif args.command == "import-fills":
            count = 0
            for fill in fills:
                count += await ledger.record(fill)
            print(f"Recorded {count} new fills; {len(fills) - count} duplicates.")
        else:
            print((await ledger.load()).model_dump_json(indent=2))
    finally:
        await ledger.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("open", "import-fills"):
        command = commands.add_parser(name)
        command.add_argument("file", type=Path)
        command.add_argument("--apply", action="store_true")
    commands.add_parser("show")
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
