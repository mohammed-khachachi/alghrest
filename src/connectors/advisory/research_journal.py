"""Atomic, append-only public research history in the advisory database."""

import sqlite3
from datetime import datetime

from pydantic import TypeAdapter

from connectors.advisory.storage import AdvisoryStore
from core.advisory.openterminal_research import TerminalSymbol, valid_symbol
from core.advisory.research_brief import BriefEntry, ResearchBrief
from core.advisory.research_journal import ResearchSnapshot, ResearchWatchEntry


class ResearchJournal:
    def __init__(self, store: AdvisoryStore) -> None:
        self.store = store
        with store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_watchlist (symbol TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS research_snapshots (
                    id TEXT PRIMARY KEY, symbol TEXT NOT NULL,
                    saved TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS research_snapshots_symbol
                    ON research_snapshots(symbol, saved);
                CREATE TABLE IF NOT EXISTS research_restores (
                    snapshot_id TEXT PRIMARY KEY, backup_sha256 TEXT NOT NULL, restored_at TEXT NOT NULL);
                """
            )

    @staticmethod
    def restored(record: ResearchSnapshot, db: sqlite3.Connection) -> ResearchSnapshot:
        row = db.execute(
            "SELECT backup_sha256 FROM research_restores WHERE snapshot_id=?", (record.id,)
        ).fetchone()
        checksum = row[0] if row else None
        return (
            ResearchSnapshot.model_validate(
                {**record.model_dump(), "restored_from_backup": checksum}
            )
            if checksum
            else record
        )

    @staticmethod
    def symbol(value: str) -> str:
        return valid_symbol(TypeAdapter(TerminalSymbol).validate_python(value))

    def watchlist(self) -> list[ResearchWatchEntry]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT w.symbol, COUNT(s.id), MAX(s.saved) FROM research_watchlist w "
                "LEFT JOIN research_snapshots s ON s.symbol=w.symbol "
                "GROUP BY w.symbol ORDER BY w.symbol"
            ).fetchall()
        return [
            ResearchWatchEntry(symbol=row[0], snapshots=row[1], latest_saved_at=row[2])
            for row in rows
        ]

    def watch(self, symbol: str, watched: bool) -> list[ResearchWatchEntry]:
        symbol = self.symbol(symbol)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if watched:
                exists = db.execute(
                    "SELECT 1 FROM research_watchlist WHERE symbol=?", (symbol,)
                ).fetchone()
                if (
                    not exists
                    and db.execute("SELECT COUNT(*) FROM research_watchlist").fetchone()[0] >= 50
                ):
                    raise ValueError("Watchlist limit reached")
                db.execute("INSERT OR IGNORE INTO research_watchlist VALUES (?)", (symbol,))
            else:
                # Removing a watch never deletes its archived research.
                db.execute("DELETE FROM research_watchlist WHERE symbol=?", (symbol,))
        return self.watchlist()

    def existing(self, identity: str, symbol: str) -> ResearchSnapshot | None:
        with self.store.connect() as db:
            row = db.execute(
                "SELECT symbol,payload FROM research_snapshots WHERE id=?", (identity,)
            ).fetchone()
            if row is not None:
                record = self.restored(ResearchSnapshot.model_validate_json(row[1]), db)
        if row is None:
            return None
        if row[0] != symbol or record.report.symbol != symbol or record.id != identity:
            raise ValueError("Snapshot identity mismatch")
        return record

    def history(self, symbol: str, limit: int = 100) -> list[ResearchSnapshot]:
        symbol = self.symbol(symbol)
        if not 1 <= limit <= 100:
            raise ValueError("Invalid history limit")
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id,payload FROM research_snapshots WHERE symbol=? "
                "ORDER BY saved DESC, rowid DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
            records = []
            for identity, payload in rows:
                record = self.restored(ResearchSnapshot.model_validate_json(payload), db)
                if record.id != identity or record.report.symbol != symbol:
                    raise ValueError("Stored snapshot identity mismatch")
                records.append(record)
        return records

    def save(self, record: ResearchSnapshot) -> ResearchSnapshot:
        payload = record.model_dump_json()
        if len(payload.encode()) > 64000:
            raise ValueError("Snapshot too large")
        symbol = self.symbol(record.report.symbol)
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT payload FROM research_snapshots WHERE id=?", (record.id,)
            ).fetchone()
            if existing:
                previous = ResearchSnapshot.model_validate_json(existing[0])
                if previous.report.symbol != symbol:
                    raise ValueError("Snapshot identity mismatch")
                return previous
            if not db.execute(
                "SELECT 1 FROM research_watchlist WHERE symbol=?", (symbol,)
            ).fetchone():
                raise ValueError("Watch the symbol before saving")
            total = db.execute("SELECT COUNT(*) FROM research_snapshots").fetchone()[0]
            count, latest = db.execute(
                "SELECT COUNT(*),MAX(saved) FROM research_snapshots WHERE symbol=?", (symbol,)
            ).fetchone()
            if total >= 5000 or count >= 100:
                raise ValueError("Snapshot limit reached; existing history is preserved")
            if latest and record.saved_at < datetime.fromisoformat(latest):
                raise ValueError("Snapshot clock moved backwards")
            db.execute(
                "INSERT INTO research_snapshots VALUES (?,?,?,?)",
                (record.id, symbol, record.saved_at.isoformat(), payload),
            )
        return record

    def brief(self, *, now: datetime) -> ResearchBrief:
        """Read watch membership and reports within one SQLite read transaction."""
        entries = []
        with self.store.connect() as db:
            db.execute("BEGIN")
            symbols = db.execute("SELECT symbol FROM research_watchlist ORDER BY symbol").fetchall()
            for (symbol,) in symbols:
                rows = db.execute(
                    "SELECT id,payload FROM research_snapshots WHERE symbol=? "
                    "ORDER BY saved DESC,rowid DESC LIMIT 2",
                    (symbol,),
                ).fetchall()
                records = []
                for identity, payload in rows:
                    record = self.restored(ResearchSnapshot.model_validate_json(payload), db)
                    if record.id != identity:
                        raise ValueError("Saved snapshot identity mismatch")
                    records.append(record)
                entries.append(BriefEntry(symbol=symbol, snapshots=tuple(records)))
        return ResearchBrief(generated_at=now, entries=tuple(entries))
