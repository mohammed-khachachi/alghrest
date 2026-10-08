"""Independent reference examples for evaluation boundaries and durable loss history."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from connectors.advisory.storage import AdvisoryStore
from core.advisory import evaluation as ev

pytestmark = pytest.mark.unit
NOW = datetime(2026, 9, 24, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)


def profile(**changes):
    return ev.EvaluationProfile(
        **(
            dict(
                id="example-only",
                program="gauntlet_mini",
                starting_balance=50000,
                profit_target=3000,
                daily_loss_limit=1100,
                maximum_drawdown=2000,
                minimum_trading_days=0,
                source="https://www.earn2trade.com/gauntlet-mini",
                verified_on=date(2026, 9, 24),
            )
            | changes
        )
    )


def session(day=24, pnl=0, low=0, closed=False):
    return ev.EvaluationSession(
        session_date=date(2026, 9, day),
        as_of=datetime(2026, 9, day, 21 if closed else 15, tzinfo=UTC),
        net_pnl=pnl,
        lowest_pnl=low,
        closed=closed,
        traded=True,
    )


def test_eod_floor_rises_only_after_finalizing_and_stops_at_starting_balance():
    p = profile()
    row = session(21, 1500, closed=True)
    first = ev.evaluation_status(p, [row])
    assert first["minimum_balance"] == "49500"
    second = ev.evaluation_status(p, [row, session(22, -500, -500, closed=True)])
    assert second["minimum_balance"] == "49500"
    current = ev.evaluation_status(p, [row, session(24, 500)])
    assert current["minimum_balance"] == "49500"  # Open profit does not trail EOD floor.
    final = ev.evaluation_status(p, [row, session(22, 1000, closed=True)])
    assert final["minimum_balance"] == "50000"


def test_intraday_breach_survives_profitable_close_and_exact_daily_boundary():
    s = ev.evaluation_status(profile(), [session(21, 50, -1100, closed=True), session(24, 200)])
    assert s["breaches"] == ["daily_loss:2026-09-21"]
    assert not s["recorded_targets_met"]
    s = ev.evaluation_status(profile(daily_loss_limit=3000), [session(24, 100, -2000)])
    assert s["breaches"] == ["drawdown_boundary:2026-09-24"]


def test_consistency_strictly_less_than_thirty_percent_includes_losing_days():
    rows = [
        session(20, 900, closed=True),
        session(21, 800, closed=True),
        session(22, 700, closed=True),
        session(23, 600, closed=True),
    ]
    result = ev.evaluation_status(profile(), rows)
    assert not result["consistency_met"] and result["consistency_total_required"] == "3000.01"
    assert ev.evaluation_status(profile(), [*rows, session(24, Decimal("0.01"))])["consistency_met"]
    assert not ev.evaluation_status(profile(), [*rows, session(24, -500, -500)])["consistency_met"]


def test_session_day_uses_chicago_dst_and_regular_closures():
    assert ev.session_clock(datetime(2026, 9, 24, 22, tzinfo=UTC))["session_date"] == "2026-09-25"
    assert ev.session_clock(datetime(2026, 1, 5, 23, tzinfo=UTC))["session_date"] == "2026-01-06"
    for now in (
        datetime(2026, 9, 24, 20, 50, tzinfo=UTC),
        datetime(2026, 9, 26, 12, tzinfo=UTC),
        datetime(2026, 9, 27, 21, tzinfo=UTC),
    ):
        assert ev.session_clock(now)["regular_hours_closed"]
    assert not ev.session_clock(datetime(2026, 9, 27, 22, tzinfo=UTC))["regular_hours_closed"]


def test_journal_is_atomic_immutable_after_close_and_loss_cannot_be_erased(tmp_path):
    store = AdvisoryStore(str(tmp_path / "evaluation.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    store.create_evaluation(p)
    assert len(store.evaluations()) == 1
    with pytest.raises(ValueError, match="immutable"):
        store.create_evaluation(profile(daily_loss_limit=2000))
    row = session(21, -100, -200)
    store.save_session(p.id, row)
    with pytest.raises(ValueError, match="erase"):
        store.save_session(p.id, session(21, 100, -100))
    with pytest.raises(ValueError, match="finalized"):
        store.save_session(p.id, session(22, 100))
    store.save_session(p.id, session(21, 200, -200, closed=True))
    with pytest.raises(ValueError, match="finalized"):
        store.save_session(p.id, session(21, 300, -200, closed=True))
    reopened = AdvisoryStore(str(tmp_path / "evaluation.sqlite3"))
    saved, rows = reopened.evaluation(p.id)
    assert saved == p and rows[0].lowest_pnl == -200 and rows[0].net_pnl == 200


def plan(**changes):
    return ev.EvaluationPlan(
        **(
            dict(
                instrument_id="MNQ",
                account_value=49500,
                risk_percent=1,
                entry=20000,
                stop=19990,
                fees_per_unit=2,
                slippage_points=1,
                allowed_standard_contracts_at_stop=1,
                existing_standard_contracts=0,
                safety_buffer=100,
                schedule_checked=True,
            )
            | changes
        )
    )


def account_session(pnl, low):
    from core.advisory.account import AccountObservation

    row = session(24, pnl, low)
    equity = Decimal(50000) + Decimal(pnl)
    evidence = AccountObservation(
        account_id="example-only",
        source="manual_report",
        source_reference="Test statement",
        observed_at=row.as_of,
        human_confirmed=True,
        costs_included=True,
        currency="USD",
        cash_balance=equity,
        unrealized_pnl=0,
        equity=equity,
        positions=(),
        working_orders=(),
    )
    return row.model_copy(update={"account": evidence})


def test_sizing_uses_daily_budget_drawdown_contracts_and_micro_multiplier():
    rows = [account_session(-500, -500)]
    result = ev.evaluation_plan(plan(), profile(), rows)
    assert result["risk_budget"] == "495"
    assert result["size"] == "10"  # 1 standard equivalent of observed flat-account headroom.
    tighter = ev.evaluation_plan(
        plan(account_value=49000), profile(), [account_session(-1000, -1000)]
    )
    assert tighter["risk_budget"] == "0" and tighter["size"] == "0"
    assert ev.evaluation_plan(plan(instrument_id="NQ"), profile(), rows)["size"] == "1"


def test_planning_blocks_unknown_stale_breached_or_inconsistent_state():
    rows = [account_session(-500, -500)]
    for value, p, entries in (
        (plan(), profile(verified_on=date(2026, 8, 1)), rows),
        (plan(), profile(), []),
        (plan(), profile(), [session(21, -500, -1200, closed=True), session(24, 0)]),
        (plan(account_value=50000), profile(), rows),
        (plan(entry="20000.1"), profile(), rows),
        (plan(instrument_id="BTCUSDT-PERP"), profile(), rows),
    ):
        with pytest.raises(ValueError):
            ev.evaluation_plan(value, p, entries)
    old = rows[0].model_copy(update={"as_of": NOW - timedelta(minutes=31), "account": None})
    with pytest.raises(ValueError, match="fresh"):
        ev.evaluation_plan(plan(), profile(), [old])


@pytest.mark.parametrize(
    "update",
    [
        {"lowest_pnl": 1},
        {"as_of": NOW + timedelta(seconds=1)},
        {"session_date": date(2026, 9, 25)},
        {"closed": True},
        {"net_pnl": -1, "lowest_pnl": 0},
        {"traded": False, "net_pnl": 1},
    ],
)
def test_invalid_session_evidence_is_rejected(update):
    with pytest.raises(ValidationError):
        ev.EvaluationSession.model_validate(session().model_dump() | update)


def test_rules_can_be_reverified_without_resetting_journal(tmp_path):
    store = AdvisoryStore(str(tmp_path / "review.sqlite3"))
    p = profile(verified_on=date(2026, 9, 1))
    store.create_evaluation(p)
    store.save_session(p.id, session(21, 100, -200, closed=True))
    store.create_evaluation(profile())
    reviewed, rows = store.evaluation(p.id)
    assert reviewed.verified_on == date(2026, 9, 24) and rows[0].lowest_pnl == -200
    with pytest.raises(ValueError, match="immutable"):
        store.create_evaluation(p)


@pytest.mark.parametrize("operation", ["read", "append", "refresh"])
def test_profile_database_identity_mismatch_is_unavailable(tmp_path, operation):
    store = AdvisoryStore(str(tmp_path / "identity.sqlite3"))
    original = profile()
    store.create_evaluation(original)
    with store.connect() as db:
        db.execute(
            "UPDATE evaluations SET payload=? WHERE id=?",
            (profile(id="another-account").model_dump_json(), original.id),
        )
    with pytest.raises(ValueError, match="state|identity"):
        if operation == "read":
            store.evaluation(original.id)
        elif operation == "append":
            store.save_session(original.id, session())
        else:
            store.create_evaluation(original)


def test_corrupt_profile_cannot_appear_as_available_in_account_list(tmp_path):
    store = AdvisoryStore(str(tmp_path / "list.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    with store.connect() as db:
        db.execute("UPDATE evaluations SET payload=?", (profile(id="wrong").model_dump_json(),))
    with pytest.raises(ValueError, match="state|identity"):
        store.evaluations()


@pytest.mark.parametrize("operation", ["read", "append"])
def test_session_database_day_mismatch_is_unavailable(tmp_path, operation):
    store = AdvisoryStore(str(tmp_path / "day.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    store.save_session(p.id, session(21, closed=True))
    with store.connect() as db:
        db.execute("UPDATE sessions SET day='2026-09-20'")
    with pytest.raises(ValueError, match="state|identity"):
        if operation == "read":
            store.evaluation(p.id)
        else:
            store.save_session(p.id, session())


def test_persisted_unfinalized_history_blocks_reads_and_does_not_get_repaired(tmp_path):
    store = AdvisoryStore(str(tmp_path / "ordering.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    store.save_session(p.id, session(21))
    with store.connect() as db:
        db.execute(
            "INSERT INTO sessions VALUES(?,?,?)", (p.id, "2026-09-24", session().model_dump_json())
        )
    with pytest.raises(ValueError, match="state|finalized"):
        store.evaluation(p.id)
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2


@pytest.mark.parametrize("bad_value", ["NaN", "Infinity", "-1"])
def test_unvalidated_profile_copy_is_rejected_before_persistence(tmp_path, bad_value):
    store = AdvisoryStore(str(tmp_path / "unvalidated-profile.sqlite3"))
    unsafe = profile().model_copy(update={"daily_loss_limit": Decimal(bad_value)})
    with pytest.raises(ValueError):
        store.create_evaluation(unsafe)
    assert store.evaluations() == []


def test_unvalidated_session_copy_cannot_erase_losses_in_storage(tmp_path):
    store = AdvisoryStore(str(tmp_path / "unvalidated-session.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    store.save_session(p.id, session(low=-100))
    unsafe = session().model_copy(update={"net_pnl": Decimal("NaN"), "lowest_pnl": Decimal(-200)})
    with pytest.raises(ValueError):
        store.save_session(p.id, unsafe)
    _, saved = store.evaluation(p.id)
    assert len(saved) == 1 and saved[0].lowest_pnl == -100 and saved[0].net_pnl == 0


def test_concurrent_journal_writers_preserve_worst_loss_and_isolate_accounts(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = str(tmp_path / "concurrent.sqlite3")
    first, second = AdvisoryStore(path), AdvisoryStore(path)
    p = profile(id="account-B")
    reserve = profile(id="account-C")
    first.create_evaluation(p)
    first.create_evaluation(reserve)
    first.save_session(p.id, session(low=-100))
    barrier = Barrier(2)

    def update(store, low):
        value = session(low=low)
        barrier.wait(timeout=5)
        try:
            store.save_session(p.id, value)
            return "saved"
        except ValueError as exc:
            assert "erase" in str(exc)
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(update, first, -200), executor.submit(update, second, -300)]
        results = [future.result(timeout=10) for future in futures]
    assert "saved" in results
    _, saved = first.evaluation(p.id)
    assert saved[0].lowest_pnl == -300
    assert first.evaluation(reserve.id)[1] == []


@pytest.mark.parametrize("table", ["evaluations", "sessions"])
def test_malformed_persisted_payload_blocks_financial_state(tmp_path, table):
    store = AdvisoryStore(str(tmp_path / "malformed.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    store.save_session(p.id, session())
    with store.connect() as db:
        db.execute(f"UPDATE {table} SET payload='{{broken'")
    with pytest.raises(ValueError, match="state is invalid"):
        store.evaluation(p.id)
    with pytest.raises(ValueError, match="state is invalid"):
        store.save_session(p.id, session(low=-100))


def test_profile_and_sessions_read_from_one_snapshot_during_concurrent_commit(
    tmp_path, monkeypatch
):
    from contextlib import contextmanager

    store = AdvisoryStore(str(tmp_path / "snapshot.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    original_connect = store.connect
    committed = False

    class ProfileCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def fetchone(self):
            nonlocal committed
            value = self.cursor.fetchone()
            # Inject an external atomic commit precisely between the two reads.
            if not committed:
                with original_connect() as writer:
                    writer.execute("BEGIN IMMEDIATE")
                    writer.execute(
                        "UPDATE evaluations SET payload=? WHERE id=?",
                        (profile(starting_balance=60000).model_dump_json(), p.id),
                    )
                    writer.execute(
                        "INSERT INTO sessions VALUES(?,?,?)",
                        (p.id, "2026-09-24", session(pnl=100).model_dump_json()),
                    )
                committed = True
            return value

    class ReadConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, *args):
            cursor = self.db.execute(sql, *args)
            return (
                ProfileCursor(cursor)
                if sql.startswith("SELECT payload FROM evaluations")
                else cursor
            )

    @contextmanager
    def interleaved_read():
        with original_connect() as db:
            yield ReadConnection(db)

    monkeypatch.setattr(store, "connect", interleaved_read)
    saved_profile, saved_sessions = store.evaluation(p.id)
    assert committed
    assert saved_profile.starting_balance == 50000 and saved_sessions == []
    # A subsequent transaction observes the complete new state.
    new_profile, new_sessions = store.evaluation(p.id)
    assert new_profile.starting_balance == 60000 and new_sessions[0].net_pnl == 100
