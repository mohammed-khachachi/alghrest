"""Append-only briefs in the isolated assistant store; commit-time input checks."""

import sqlite3
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Literal

from connectors.advisory.storage import AdvisoryStore
from core.advisory.briefing import (
    MAX_RECORD_BYTES,
    Briefing,
    BriefingRequest,
    BriefingView,
    verify_briefing,
)
from core.advisory.models import utc_instant
from core.advisory.observations import ObservationRevision, observation_warnings
from core.advisory.user_risk import personal_account_status


class BriefingConflictError(ValueError):
    pass


SaveState = Literal["PREPARED", "CANCELLED", "COMMITTING", "COMMITTED", "UNKNOWN"]


class BriefingSaveGuard:
    """Request-local commit handshake; never evidence or a verification cache."""

    def __init__(self, deadline: float) -> None:
        self.deadline = deadline
        self._state: SaveState = "PREPARED"
        self._lock = threading.Lock()

    def cancel(self) -> SaveState:
        with self._lock:
            if self._state == "PREPARED":
                self._state = "CANCELLED"
            return self._state

    def begin_commit(self) -> None:
        with self._lock:
            if self._state == "PREPARED" and time.monotonic() < self.deadline:
                self._state = "COMMITTING"
                return
            if self._state == "PREPARED":
                self._state = "CANCELLED"
            raise TimeoutError("Save cancelled before commit")

    def committed(self) -> None:
        with self._lock:
            self._state = "COMMITTED"

    def failed(self) -> None:
        with self._lock:
            # An error while committing cannot prove that no durable row exists.
            if self._state == "COMMITTING":
                self._state = "UNKNOWN"
            elif self._state == "PREPARED":
                self._state = "CANCELLED"


_save_guard: ContextVar[BriefingSaveGuard | None] = ContextVar("briefing_save_guard", default=None)


@contextmanager
def guarded_briefing_save(guard: BriefingSaveGuard) -> Iterator[None]:
    """Propagated by to_thread; scoped to one write without changing save's signature."""
    token = _save_guard.set(guard)
    try:
        yield
    finally:
        _save_guard.reset(token)


class BriefingStore:
    def __init__(self, store: AdvisoryStore) -> None:
        self.store = store
        with store.connect() as db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS evaluation_briefings (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)"
            )

    def check(
        self, request: BriefingRequest, *, now: datetime, db: sqlite3.Connection | None = None
    ) -> None:
        if db is None:
            with self.store.connect() as connection:
                connection.execute("BEGIN")
                self.check(request, now=now, db=connection)
            return
        head = db.execute(
            "SELECT revision FROM observation_heads WHERE id=?", (request.observation_id,)
        ).fetchone()
        review = db.execute(
            "SELECT reviewed FROM observation_reviews WHERE revision=?",
            (request.observation_revision,),
        ).fetchone()
        if head is None or head[0] != request.observation_revision or review is None:
            raise BriefingConflictError("Observation must be the current reviewed revision")
        when = utc_instant(datetime.fromisoformat(review[0]))
        if when > utc_instant(now):
            raise ValueError("Future observation review")
        profile, sessions = self.store._evaluation(db, request.evaluation_id)
        if (
            personal_account_status(profile, sessions, now=now)["account_revision"]
            != request.account_revision
        ):
            raise BriefingConflictError("Account changed; reopen the current journal")

    def save(self, value: Briefing, request: BriefingRequest, *, now: datetime) -> BriefingView:
        value = verify_briefing(value)
        i = value.inputs
        status = personal_account_status(i.profile, list(i.sessions), now=i.assessed_at)
        if (
            i.observation.record.id != request.observation_id
            or i.observation.record.revision != request.observation_revision
            or i.profile.id != request.evaluation_id
            or status["account_revision"] != request.account_revision
        ):
            raise ValueError("Briefing/request evidence mismatch")
        payload = value.model_dump_json()
        if len(payload.encode()) > MAX_RECORD_BYTES:
            raise ValueError("Briefing exceeds size limit")
        guard = _save_guard.get()
        try:
            with self.store.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                self.check(request, now=now, db=db)
                captured = db.execute(
                    "SELECT payload FROM observation_revisions WHERE id=? AND revision=?",
                    (request.observation_id, request.observation_revision),
                ).fetchone()
                reviewed = db.execute(
                    "SELECT reviewed FROM observation_reviews WHERE revision=?",
                    (request.observation_revision,),
                ).fetchone()
                if (
                    captured is None
                    or reviewed is None
                    or ObservationRevision.model_validate_json(captured[0]) != i.observation.record
                    or utc_instant(datetime.fromisoformat(reviewed[0])) != i.observation.reviewed_at
                ):
                    raise BriefingConflictError("Observation or review changed before commit")
                db.execute(
                    "INSERT INTO evaluation_briefings VALUES (?,?,?)",
                    (value.id, i.assessed_at.isoformat(), payload),
                )
                if guard is not None:
                    guard.begin_commit()
            if guard is not None:
                guard.committed()
        except BaseException:
            if guard is not None:
                guard.failed()
            raise
        return self.read(value.id, now=now)

    def read(self, identifier: str, *, now: datetime) -> BriefingView:
        now = utc_instant(now)
        with self.store.connect() as db:
            db.execute("BEGIN")
            row = db.execute(
                "SELECT payload FROM evaluation_briefings WHERE id=?", (identifier,)
            ).fetchone()
            if row is None:
                raise KeyError("Briefing not found")
            if len(row[0].encode()) > MAX_RECORD_BYTES:
                raise ValueError("Oversize briefing")
            value = Briefing.model_validate_json(row[0])
            if value.id != identifier or value.inputs.assessed_at > now:
                raise ValueError("Saved briefing identity/clock mismatch")
            warnings = set(observation_warnings(value.inputs.observation.record.packet, now=now))
            if (now - value.inputs.assessed_at).total_seconds() >= 300:
                warnings.add("historical_context_not_current")
            request = BriefingRequest(
                observation_id=value.inputs.observation.record.id,
                observation_revision=value.inputs.observation.record.revision,
                evaluation_id=value.inputs.profile.id,
                account_revision=value.result.account_status["account_revision"],
            )
            try:
                self.check(request, now=now, db=db)
            except BriefingConflictError:
                warnings.add("current_inputs_changed")
            return BriefingView(
                record=value, reopened_at=now, current_warnings=tuple(sorted(warnings))
            )

    def history(self) -> list[dict[str, str]]:
        with self.store.connect() as db:
            rows = db.execute(
                "SELECT id,created FROM evaluation_briefings ORDER BY rowid DESC LIMIT 30"
            ).fetchall()
        return [{"id": row[0], "created": row[1]} for row in rows]
