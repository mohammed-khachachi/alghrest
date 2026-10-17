"""Local research-only backup/restore; never replaces an existing output or journal."""

import argparse
import json
import os
from pathlib import Path

from connectors.advisory.research_backup import export_research, restore_research
from connectors.advisory.research_journal import ResearchJournal
from connectors.advisory.storage import AdvisoryStore
from core.advisory.models import utcnow
from core.advisory.research_backup import read_backup


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("export", "restore"))
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply a non-destructive restore; otherwise preview only",
    )
    args = parser.parse_args()
    if args.operation == "export" and not args.database.is_file():
        parser.error("Source journal does not exist")
    journal = ResearchJournal(AdvisoryStore(str(args.database)))
    now = utcnow()
    if args.operation == "export":
        raw = export_research(journal, now)
        with os.fdopen(
            os.open(args.file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
        ) as output:
            output.write(raw)
        backup = read_backup(raw, now)
        print(
            json.dumps(
                {
                    "status": "exported",
                    "snapshots": len(backup.snapshots),
                    "watches": len(backup.watches),
                    "sha256": backup.sha256,
                }
            )
        )
    else:
        result = restore_research(journal, args.file.read_bytes(), now, preview=not args.apply)
        print(json.dumps({"status": "restored" if args.apply else "preview", **result}))


if __name__ == "__main__":
    main()
