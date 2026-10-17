"""Append-only user observations in the existing isolated advisory database."""

from datetime import datetime
from uuid import uuid4

from connectors.advisory.storage import AdvisoryStore
from core.advisory.models import utc_instant
from core.advisory.observations import (
    ObservationRevision,
    ObservationView,
    make_revision,
    observation_warnings,
)


class ObservationConflictError(ValueError):
    """The caller must reread the current revision before editing/reviewing."""


class ObservationStore:
    def __init__(self, store: AdvisoryStore) -> None:
        self.store = store
        with store.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS observation_revisions (
                    id TEXT NOT NULL, revision TEXT PRIMARY KEY,
                    parent TEXT, created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observation_heads (
                    id TEXT PRIMARY KEY, revision TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS observation_reviews (
                    revision TEXT PRIMARY KEY, reviewed TEXT NOT NULL);
                """
            )

    def save(
        self,
        raw: str,
        *,
        observation_id: str | None,
        expected_revision: str | None,
        now: datetime,
    ) -> ObservationView:
        if (observation_id is None) != (expected_revision is None):
            raise ValueError("New records have no parent; edits require the current revision")
        record = make_revision(
            raw,
            observation_id=observation_id or uuid4().hex,
            parent_revision=expected_revision,
            now=now,
        )
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            head = db.execute(
                "SELECT revision FROM observation_heads WHERE id=?", (record.id,)
            ).fetchone()
            if (head[0] if head else None) != expected_revision:
                raise ObservationConflictError("Observation changed; reopen the latest version")
            if expected_revision:
                previous = db.execute(
                    "SELECT payload FROM observation_revisions WHERE revision=?",
                    (expected_revision,),
                ).fetchone()
                if previous is None:
                    raise ValueError("Missing previous observation")
                parent = ObservationRevision.model_validate_json(previous[0])
                if parent.id != record.id or record.created_at < parent.created_at:
                    raise ValueError("Invalid observation parent or clock")
            db.execute(
                "INSERT INTO observation_revisions VALUES (?,?,?,?,?)",
                (
                    record.id,
                    record.revision,
                    expected_revision,
                    record.created_at.isoformat(),
                    record.model_dump_json(),
                ),
            )
            db.execute(
                "INSERT INTO observation_heads VALUES (?,?) "
                "ON CONFLICT(id) DO UPDATE SET revision=excluded.revision",
                (record.id, record.revision),
            )
        return self.read(record.id, revision=record.revision, now=now)

    def read(
        self, observation_id: str, *, now: datetime, revision: str | None = None
    ) -> ObservationView:
        now = utc_instant(now)
        with self.store.connect() as db:
            db.execute("BEGIN")
            head = db.execute(
                "SELECT revision FROM observation_heads WHERE id=?", (observation_id,)
            ).fetchone()
            if head is None:
                raise KeyError("Observation not found")
            selected = revision or str(head[0])
            row = db.execute(
                "SELECT payload FROM observation_revisions WHERE id=? AND revision=?",
                (observation_id, selected),
            ).fetchone()
            review = db.execute(
                "SELECT reviewed FROM observation_reviews WHERE revision=?", (selected,)
            ).fetchone()
        if row is None:
            raise KeyError("Observation revision not found")
        record = ObservationRevision.model_validate_json(row[0])
        if record.id != observation_id or record.revision != selected or record.created_at > now:
            raise ValueError("Saved observation identity or time mismatch")
        reviewed = datetime.fromisoformat(review[0]) if review else None
        if reviewed is not None and not record.created_at <= utc_instant(reviewed) <= now:
            raise ValueError("Invalid review timestamp")
        return ObservationView(
            record=record,
            latest_revision=head[0],
            reviewed_at=reviewed,
            assessed_at=now,
            warnings=observation_warnings(record.packet, now=now),
        )

    def review(
        self, observation_id: str, *, expected_revision: str, now: datetime
    ) -> ObservationView:
        value = self.read(observation_id, now=now)
        if value.latest_revision != expected_revision:
            raise ObservationConflictError("Observation changed; review the current version")
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            head = db.execute(
                "SELECT revision FROM observation_heads WHERE id=?", (observation_id,)
            ).fetchone()
            if head is None or head[0] != expected_revision:
                raise ObservationConflictError("Observation changed during review")
            db.execute(
                "INSERT OR IGNORE INTO observation_reviews VALUES (?,?)",
                (expected_revision, utc_instant(now).isoformat()),
            )
        return self.read(observation_id, now=now)

    def history(self, *, now: datetime, observation_id: str | None = None) -> list[ObservationView]:
        with self.store.connect() as db:
            rows = (
                db.execute(
                    "SELECT id, revision FROM observation_revisions WHERE id=? "
                    "ORDER BY rowid DESC LIMIT 100",
                    (observation_id,),
                ).fetchall()
                if observation_id
                else db.execute(
                    "SELECT id, revision FROM observation_heads ORDER BY rowid DESC LIMIT 100"
                ).fetchall()
            )
        return [self.read(row[0], revision=row[1], now=now) for row in rows]
