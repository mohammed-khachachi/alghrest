"""Research-only export and atomic, non-destructive merge restoration."""

import json
from collections import Counter
from datetime import datetime

from connectors.advisory.research_journal import ResearchJournal
from core.advisory.research_backup import MAX_BACKUP_BYTES, backup_checksum, read_backup


def export_research(journal: ResearchJournal, now: datetime) -> bytes:
    with journal.store.connect() as db:
        db.execute("BEGIN")
        snapshots: list[dict[str, object]] = []
        size = 0
        for row in db.execute(
            "SELECT id,symbol,saved,payload FROM research_snapshots ORDER BY rowid"
        ):
            if len(row[3].encode()) > 64000:
                raise ValueError("Stored research snapshot exceeds its size bound")
            record = dict(zip(("id", "symbol", "stored_saved", "payload"), row, strict=True))
            size += len(json.dumps(record, ensure_ascii=True).encode())
            if size > MAX_BACKUP_BYTES or len(snapshots) >= 5000:
                raise ValueError("Research backup exceeds its size/count bound")
            snapshots.append(record)
        content: dict[str, object] = {
            "schema_version": "research-backup-v1",
            "created_at": now.isoformat().replace("+00:00", "Z"),
            "watches": [
                r[0] for r in db.execute("SELECT symbol FROM research_watchlist ORDER BY symbol")
            ],
            "snapshots": snapshots,
        }
    value = {**content, "sha256": backup_checksum(content)}
    raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode()
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError("Backup exceeds 32 MiB; existing research is unchanged")
    read_backup(raw, now)  # Never export a silently truncated or corrupt archive.
    return raw


def restore_research(
    journal: ResearchJournal, raw: bytes, now: datetime, *, preview: bool = False
) -> dict[str, int | str]:
    backup = read_backup(raw, now)
    with journal.store.connect() as db:
        db.execute("BEGIN" if preview else "BEGIN IMMEDIATE")
        watches = {row[0] for row in db.execute("SELECT symbol FROM research_watchlist")}
        existing_count = db.execute("SELECT COUNT(*) FROM research_snapshots").fetchone()[0]
        counts = Counter(
            dict(
                db.execute(
                    "SELECT symbol,COUNT(*) FROM research_snapshots GROUP BY symbol"
                ).fetchall()
            )
        )
        pending = []
        for row in backup.snapshots:
            previous = db.execute(
                "SELECT symbol,saved,payload FROM research_snapshots WHERE id=?", (row.id,)
            ).fetchone()
            if previous is not None:
                if previous != (row.symbol, row.stored_saved, row.payload):
                    raise ValueError(
                        "Backup conflicts with existing snapshot identity; nothing restored"
                    )
            else:
                pending.append(row)
        counts.update(row.symbol for row in pending)
        if (
            len(watches | set(backup.watches)) > 50
            or existing_count + len(pending) > 5000
            or any(n > 100 for n in counts.values())
        ):
            raise ValueError("Merged research would exceed journal limits; nothing restored")
        if not preview:
            db.executemany(
                "INSERT OR IGNORE INTO research_watchlist VALUES(?)", [(s,) for s in backup.watches]
            )
            db.executemany(
                "INSERT INTO research_snapshots VALUES(?,?,?,?)",
                [(r.id, r.symbol, r.stored_saved, r.payload) for r in pending],
            )
            db.executemany(
                "INSERT INTO research_restores VALUES(?,?,?)",
                [(r.id, backup.sha256, now.isoformat()) for r in pending],
            )
        return {
            "sha256": backup.sha256,
            "watches_in_file": len(backup.watches),
            "snapshots_in_file": len(backup.snapshots),
            "watches_added": len(set(backup.watches) - watches),
            "snapshots_added": len(pending),
            "snapshots_unchanged": len(backup.snapshots) - len(pending),
        }
