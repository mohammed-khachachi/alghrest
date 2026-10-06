"""Bounded, separate SQLite storage; never opens the execution/accounting database."""

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.advisory.account import AccountConfiguration, AccountPlan
from core.advisory.evaluation import EvaluationProfile, EvaluationSession, evaluation_status
from core.advisory.models import MarketSnapshot, Report, Watchlist
from core.advisory.policy import PolicyAssessment, verify_policy_assessment
from core.advisory.risk import RiskDecision, verify_qualified_record
from core.advisory.selection import MarketSelection
from core.advisory.strategies import (
    StrategyDefinition,
    StrategyLifecycleEvent,
    StrategyRecord,
    StrategyRegistry,
)


class AdvisoryStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS imports (instrument TEXT NOT NULL,interval TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(instrument,interval));
            CREATE TABLE IF NOT EXISTS reports (id TEXT PRIMARY KEY,created TEXT NOT NULL,instrument TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intelligence (id TEXT PRIMARY KEY,created TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS evaluations (id TEXT PRIMARY KEY,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions (evaluation TEXT NOT NULL,day TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(evaluation,day));
            CREATE TABLE IF NOT EXISTS selections (id TEXT PRIMARY KEY,created TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS risk_decisions (id TEXT PRIMARY KEY,created TEXT NOT NULL,account TEXT NOT NULL,payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS policy_assessments (id TEXT PRIMARY KEY,created TEXT NOT NULL,account TEXT NOT NULL,payload TEXT NOT NULL);
            """
            )

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    def watchlist(self) -> Watchlist:
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='watchlist'").fetchone()
        return Watchlist.model_validate_json(row[0]) if row else Watchlist()

    def set_watchlist(self, value: Watchlist) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO settings(key,value) VALUES('watchlist',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (value.model_dump_json(),),
            )

    def _account_plan(self, db: sqlite3.Connection) -> AccountPlan | None:
        row = db.execute("SELECT value FROM settings WHERE key='account_plan'").fetchone()
        if row is None:
            return None
        value = AccountPlan.model_validate_json(row[0])
        for binding in value.bindings:
            profile = db.execute(
                "SELECT payload FROM evaluations WHERE id=?", (binding.account_id,)
            ).fetchone()
            if profile is None:
                raise ValueError("Account plan references a missing financial journal")
            self._profile(binding.account_id, profile[0])
        return value

    def account_plan(self) -> AccountPlan | None:
        with self.connect() as db:
            db.execute("BEGIN")
            return self._account_plan(db)

    def set_account_plan(self, value: AccountPlan, *, expected_revision: str | None = None) -> str:
        """Server-owned configuration; no public assignment, promotion or unlock API."""
        value = AccountPlan.model_validate(value.model_dump(warnings=False))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._account_plan(db)
            if previous == value:
                return value.revision
            if (previous.revision if previous else None) != expected_revision:
                raise ValueError("Account plan revision changed; reread before updating")
            if previous is not None:
                before = {(b.slot, b.account_id) for b in previous.bindings}
                after = {(b.slot, b.account_id) for b in value.bindings}
                if value.id != previous.id or value.origin != previous.origin or before != after:
                    raise ValueError("Account role bindings are immutable")
                if value.version == previous.version or value.known_at <= previous.known_at:
                    raise ValueError("Plan updates need a new version and later known-at time")
            for binding in value.bindings:
                row = db.execute(
                    "SELECT payload FROM evaluations WHERE id=?", (binding.account_id,)
                ).fetchone()
                if row is None:
                    raise ValueError("Account plan references a missing financial journal")
                self._profile(binding.account_id, row[0])
                for assignment in binding.assignments:
                    selected = self._selection(db, assignment.selection_id)
                    if selected is None:
                        raise ValueError("Account assignment requires a saved research comparison")
                    if selected.generated_at > value.known_at:
                        raise ValueError("Assignment comparison identity or known-at mismatch")
                    market = next(
                        (
                            r
                            for r in selected.assessments
                            if r.instrument_id == assignment.configuration.instrument_id
                        ),
                        None,
                    )
                    if (
                        market is None
                        or not market.eligible
                        or market.evidence is None
                        or market.evidence.edge is None
                        or market.evidence.fit is None
                    ):
                        raise ValueError(
                            "Assignment needs a qualified reported research configuration"
                        )
                    edge, fit = market.evidence.edge, market.evidence.fit
                    expected = AccountConfiguration(
                        instrument_id=market.instrument_id,
                        strategy_id=edge.strategy_id,
                        strategy_version=edge.strategy_version,
                        risk_configuration_id=edge.risk_configuration_id,
                        risk_configuration_version=assignment.configuration.risk_configuration_version,
                        evaluation_policy_id=fit.evaluation_policy_id,
                        evaluation_policy_version=fit.evaluation_policy_version,
                        cost_model_version=edge.cost_model_version,
                        edge_id=edge.id,
                        edge_version=edge.version,
                        fit_id=fit.id,
                        fit_version=fit.version,
                        dataset_sha256=edge.dataset_sha256,
                    )
                    if assignment.configuration != expected:
                        raise ValueError(
                            "Assigned configuration does not match its research revision"
                        )
                    if value.origin == "reported" and (
                        selected.mode != "current" or edge.origin != "historical"
                    ):
                        raise ValueError(
                            "Reported account plans cannot use synthetic/replay research"
                        )
            db.execute(
                "INSERT INTO settings(key,value) VALUES('account_plan',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (value.model_dump_json(),),
            )
            return value.revision

    def evaluation_context(
        self, account_id: str
    ) -> tuple[EvaluationProfile, list[EvaluationSession], AccountPlan | None]:
        with self.connect() as db:
            db.execute("BEGIN")
            profile, rows = self._evaluation(db, account_id)
            return profile, rows, self._account_plan(db)

    @staticmethod
    def _strategy_registry(db: sqlite3.Connection) -> StrategyRegistry:
        row = db.execute("SELECT value FROM settings WHERE key='strategy_registry'").fetchone()
        if row is None:
            return StrategyRegistry()
        envelope = json.loads(row[0])
        if not isinstance(envelope, dict) or set(envelope) != {"revision", "registry"}:
            raise ValueError("Stored strategy registry envelope is invalid")
        value = StrategyRegistry.model_validate(envelope["registry"])
        if value.revision != envelope["revision"]:
            raise ValueError("Stored strategy registry revision does not match its content")
        return value

    def strategy_registry(self) -> StrategyRegistry:
        with self.connect() as db:
            return self._strategy_registry(db)

    @staticmethod
    def _save_strategy_registry(db: sqlite3.Connection, value: StrategyRegistry) -> None:
        db.execute(
            "INSERT INTO settings(key,value) VALUES('strategy_registry',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (json.dumps({"revision": value.revision, "registry": value.model_dump(mode="json")}),),
        )

    def register_strategy(
        self, definition: StrategyDefinition, *, expected_revision: str, reason: str
    ) -> StrategyRecord:
        """Server-owned experiment admission; no public promotion/approval API."""
        definition = StrategyDefinition.model_validate(definition.model_dump(warnings=False))
        event = StrategyLifecycleEvent(
            status="EXPERIMENT",
            known_at=definition.registered_at,
            source_reference=definition.source_reference,
            reason=reason,
        )
        value = StrategyRecord(definition=definition, events=(event,))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._strategy_registry(db)
            if previous.revision != expected_revision:
                raise ValueError("Strategy registry revision changed; reread before updating")
            existing = next(
                (
                    r
                    for r in previous.records
                    if (r.definition.id, r.definition.version)
                    == (definition.id, definition.version)
                ),
                None,
            )
            if existing is not None:
                if existing != value:
                    raise ValueError("Strategy definition/version and lifecycle are immutable")
                return existing
            records = sorted(
                (*previous.records, value), key=lambda r: (r.definition.id, r.definition.version)
            )
            updated = StrategyRegistry(records=tuple(records))
            self._save_strategy_registry(db, updated)
            return value

    def retire_strategy(
        self,
        strategy_id: str,
        strategy_version: str,
        *,
        expected_revision: str,
        event: StrategyLifecycleEvent,
    ) -> StrategyRecord:
        event = StrategyLifecycleEvent.model_validate(event.model_dump(warnings=False))
        if event.status != "RETIRED":
            raise ValueError("Only retirement is supported; promotion needs verified evidence")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = self._strategy_registry(db)
            if previous.revision != expected_revision:
                raise ValueError("Strategy registry revision changed; reread before updating")
            existing = next(
                (
                    r
                    for r in previous.records
                    if (r.definition.id, r.definition.version) == (strategy_id, strategy_version)
                ),
                None,
            )
            if existing is None:
                raise ValueError("Strategy definition not found")
            updated_record = StrategyRecord(
                definition=existing.definition, events=(*existing.events, event)
            )
            updated = StrategyRegistry(
                records=tuple(updated_record if r == existing else r for r in previous.records)
            )
            self._save_strategy_registry(db, updated)
            return updated_record

    def risk_context(
        self, account_id: str
    ) -> tuple[EvaluationProfile, list[EvaluationSession], AccountPlan | None, StrategyRegistry]:
        with self.connect() as db:
            db.execute("BEGIN")
            profile, rows = self._evaluation(db, account_id)
            return profile, rows, self._account_plan(db), self._strategy_registry(db)

    def import_market(self, value: MarketSnapshot) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT INTO imports VALUES(?,?,?) ON CONFLICT(instrument,interval) DO UPDATE SET payload=excluded.payload",
                (value.instrument_id, value.interval, value.model_dump_json()),
            )

    def market(self, instrument: str, interval: str) -> MarketSnapshot | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT payload FROM imports WHERE instrument=? AND interval=?",
                (instrument, interval),
            ).fetchone()
        return MarketSnapshot.model_validate_json(row[0]) if row else None

    def save_report(self, value: Report) -> None:
        value = Report.model_validate(value.model_dump())
        with self.connect() as db:
            db.execute(
                "INSERT INTO reports VALUES(?,?,?,?)",
                (
                    value.id,
                    value.generated_at.isoformat(),
                    value.instrument.id,
                    value.model_dump_json(),
                ),
            )
            db.execute(
                "DELETE FROM reports WHERE id NOT IN (SELECT id FROM reports ORDER BY created DESC LIMIT 100)"
            )

    def report(self, report_id: str) -> dict[str, Any] | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT created,instrument,payload FROM reports WHERE id=?", (report_id,)
            ).fetchone()
        if row is None:
            return None
        value = Report.model_validate_json(row[2])
        if (value.id, value.generated_at.isoformat(), value.instrument.id) != (
            report_id,
            row[0],
            row[1],
        ):
            raise ValueError("Stored report identity/time/market does not match its key")
        return value.model_dump(mode="json")

    def save_selection(self, value: MarketSelection) -> None:
        value = MarketSelection.model_validate(value.model_dump())
        with self.connect() as db:
            db.execute(
                "INSERT INTO selections VALUES(?,?,?)",
                (
                    value.id,
                    value.generated_at.isoformat(),
                    value.model_dump_json(),
                ),
            )
            db.execute(
                "DELETE FROM selections WHERE id NOT IN (SELECT id FROM selections ORDER BY created DESC,id DESC LIMIT 100)"
            )

    def selection(self, selection_id: str) -> MarketSelection | None:
        with self.connect() as db:
            return self._selection(db, selection_id)

    @staticmethod
    def _selection(db: sqlite3.Connection, selection_id: str) -> MarketSelection | None:
        row = db.execute(
            "SELECT created,payload FROM selections WHERE id=?", (selection_id,)
        ).fetchone()
        if row is None:
            return None
        value = MarketSelection.model_validate_json(row[1])
        if value.id != selection_id or value.generated_at.isoformat() != row[0]:
            raise ValueError("Stored selection identity/time does not match its key")
        return value

    def save_risk_decision(self, value: RiskDecision) -> None:
        value = RiskDecision.model_validate(value.model_dump())
        verify_qualified_record(value)
        with self.connect() as db:
            db.execute(
                "INSERT INTO risk_decisions VALUES(?,?,?,?)",
                (
                    value.id,
                    value.generated_at.isoformat(),
                    value.account_id,
                    value.model_dump_json(),
                ),
            )
            db.execute(
                "DELETE FROM risk_decisions WHERE id NOT IN (SELECT id FROM risk_decisions ORDER BY created DESC,id DESC LIMIT 100)"
            )

    def risk_decision(self, decision_id: str) -> RiskDecision | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT created,account,payload FROM risk_decisions WHERE id=?", (decision_id,)
            ).fetchone()
        if row is None:
            return None
        value = RiskDecision.model_validate_json(row[2])
        if (value.id, value.generated_at.isoformat(), value.account_id) != (
            decision_id,
            row[0],
            row[1],
        ):
            raise ValueError("Stored risk decision identity/time/account does not match its key")
        verify_qualified_record(value)
        return value

    def save_policy_assessment(self, value: PolicyAssessment) -> None:
        value = PolicyAssessment.model_validate(value.model_dump())
        verify_policy_assessment(value)
        with self.connect() as db:
            db.execute(
                "INSERT INTO policy_assessments VALUES(?,?,?,?)",
                (
                    value.id,
                    value.generated_at.isoformat(),
                    value.profile.id,
                    value.model_dump_json(),
                ),
            )
            db.execute(
                "DELETE FROM policy_assessments WHERE id NOT IN (SELECT id FROM policy_assessments ORDER BY created DESC,id DESC LIMIT 100)"
            )

    def policy_assessment(self, assessment_id: str) -> PolicyAssessment | None:
        with self.connect() as db:
            row = db.execute(
                "SELECT created,account,payload FROM policy_assessments WHERE id=?",
                (assessment_id,),
            ).fetchone()
        if row is None:
            return None
        value = PolicyAssessment.model_validate_json(row[2])
        if (value.id, value.generated_at.isoformat(), value.profile.id) != (
            assessment_id,
            row[0],
            row[1],
        ):
            raise ValueError(
                "Stored policy assessment identity/time/account does not match its key"
            )
        verify_policy_assessment(value)
        return value

    def history(self) -> list[dict[str, str]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,created,instrument FROM reports ORDER BY created DESC LIMIT 30"
            ).fetchall()
        return [dict(zip(("id", "created", "instrument"), r, strict=True)) for r in rows]

    def save_intelligence(self, value: dict[str, str]) -> None:
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO intelligence VALUES(?,?,?)",
                (value["id"], value["timestamp"], json.dumps(value)),
            )
            db.execute(
                "DELETE FROM intelligence WHERE id NOT IN (SELECT id FROM intelligence ORDER BY created DESC LIMIT 100)"
            )

    def intelligence(self) -> list[dict[str, str]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload FROM intelligence ORDER BY created DESC LIMIT 20"
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def evaluations(self) -> list[EvaluationProfile]:
        with self.connect() as db:
            rows = db.execute("SELECT id,payload FROM evaluations ORDER BY id").fetchall()
        return [self._profile(row[0], row[1]) for row in rows]

    @staticmethod
    def _profile(evaluation_id: str, payload: str) -> EvaluationProfile:
        try:
            value = EvaluationProfile.model_validate_json(payload)
        except ValueError as exc:
            raise ValueError("Stored evaluation state is invalid") from exc
        if value.id != evaluation_id:
            raise ValueError("Stored evaluation identity does not match its account key")
        return value

    def _evaluation(
        self, db: sqlite3.Connection, evaluation_id: str
    ) -> tuple[EvaluationProfile, list[EvaluationSession]]:
        profile = db.execute(
            "SELECT payload FROM evaluations WHERE id=?", (evaluation_id,)
        ).fetchone()
        if not profile:
            raise ValueError("Evaluation not found")
        value = self._profile(evaluation_id, profile[0])
        rows = db.execute(
            "SELECT day,payload FROM sessions WHERE evaluation=? ORDER BY day", (evaluation_id,)
        ).fetchall()
        sessions = []
        for day, payload in rows:
            try:
                session = EvaluationSession.model_validate_json(payload)
            except ValueError as exc:
                raise ValueError("Stored evaluation session state is invalid") from exc
            if session.session_date.isoformat() != day:
                raise ValueError("Stored session identity does not match its journal day")
            sessions.append(session)
        # Validate the whole timeline before exposing financial state. Invalid
        # records are neither silently dropped nor automatically repaired.
        evaluation_status(value, sessions)
        return value, sessions

    def create_evaluation(self, value: EvaluationProfile) -> None:
        # model_copy and assignment can bypass input validation inside Python.
        value = EvaluationProfile.model_validate(value.model_dump())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM evaluations WHERE id=?", (value.id,)).fetchone()
            if row:
                previous = self._profile(value.id, row[0])
                if (
                    previous.model_dump(exclude={"verified_on"})
                    != value.model_dump(exclude={"verified_on"})
                    or value.verified_on < previous.verified_on
                ):
                    raise ValueError(
                        "Profile is immutable; use a new evaluation ID for different rules"
                    )
                db.execute(
                    "UPDATE evaluations SET payload=? WHERE id=?",
                    (value.model_dump_json(), value.id),
                )
                return
            if db.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0] >= 20:
                raise ValueError("At most 20 local evaluations")
            db.execute("INSERT INTO evaluations VALUES(?,?)", (value.id, value.model_dump_json()))

    def evaluation(self, evaluation_id: str) -> tuple[EvaluationProfile, list[EvaluationSession]]:
        with self.connect() as db:
            # SQLite does not start a read transaction for SELECT implicitly.
            # Profile and sessions must belong to one durable snapshot.
            db.execute("BEGIN")
            return self._evaluation(db, evaluation_id)

    def save_session(self, evaluation_id: str, value: EvaluationSession) -> None:
        value = EvaluationSession.model_validate(value.model_dump())
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            profile, rows = self._evaluation(db, evaluation_id)
            if rows and value.session_date == rows[-1].session_date:
                previous = rows[-1]
                if previous == value:
                    return
                if (
                    previous.closed
                    or value.as_of < previous.as_of
                    or value.lowest_pnl > previous.lowest_pnl
                    or (previous.traded and not value.traded)
                ):
                    raise ValueError("Cannot rewrite finalized history or erase an intraday loss")
                rows[-1] = value
            else:
                if len(rows) >= 2000:
                    raise ValueError("Evaluation journal limit reached")
                rows.append(value)
            evaluation_status(profile, rows)
            db.execute(
                "INSERT INTO sessions VALUES(?,?,?) ON CONFLICT(evaluation,day) DO UPDATE SET payload=excluded.payload",
                (evaluation_id, value.session_date.isoformat(), value.model_dump_json()),
            )
