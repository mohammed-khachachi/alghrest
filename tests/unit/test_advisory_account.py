"""Account evidence is required before journal-backed evaluation sizing."""

import pytest

from core.advisory import evaluation as ev
from tests.unit.test_evaluation import NOW, plan, profile, session

pytestmark = pytest.mark.unit


def test_missing_exposure_observation_blocks_sizing(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    with pytest.raises(ValueError, match="account observation"):
        ev.evaluation_plan(plan(), profile(), [session(pnl=-500, low=-500)])


def observation(**changes):
    from core.advisory.account import AccountObservation

    return AccountObservation(
        **(
            dict(
                account_id="example-only",
                source="manual_report",
                source_reference="Human review of evaluation statement, test fixture",
                observed_at=NOW,
                human_confirmed=True,
                costs_included=True,
                currency="USD",
                cash_balance="49500",
                unrealized_pnl="0",
                equity="49500",
                positions=(),
                working_orders=(),
            )
            | changes
        )
    )


def observed_session(pnl=-500, low=-500, **changes):
    from decimal import Decimal

    equity = Decimal(50000) + Decimal(pnl)
    account = observation(cash_balance=equity, equity=equity, **changes)
    return session(pnl=pnl, low=low).model_copy(update={"account": account})


def test_complete_reconciled_state_reaches_existing_risk_limits(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    rows = [observed_session()]
    state = ev.evaluation_status(profile(), rows)
    assert state["account_state"]["health"] == "KNOWN"
    result = ev.evaluation_plan(
        plan(existing_standard_contracts=0, allowed_standard_contracts_at_stop=1), profile(), rows
    )
    assert result["risk_budget"] == "495" and result["size"] == "10"


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"positions": None}, "positions_unknown"),
        ({"working_orders": None}, "working_orders_unknown"),
        ({"human_confirmed": False}, "unconfirmed_account_observation"),
        ({"costs_included": False}, "account_costs_unknown"),
    ],
)
def test_incomplete_or_unconfirmed_evidence_blocks_sizing(monkeypatch, change, reason):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    rows = [observed_session(**change)]
    state = ev.evaluation_status(profile(), rows)["account_state"]
    assert state["health"] == "UNKNOWN" and reason in state["reasons"]
    with pytest.raises(ValueError, match="account observation"):
        ev.evaluation_plan(plan(), profile(), rows)


@pytest.mark.parametrize(
    "changes", [{"account_id": "account-C"}, {"equity": "49501", "cash_balance": "49501"}]
)
def test_cross_account_or_wrong_equity_cannot_enter_durable_journal(monkeypatch, tmp_path, changes):
    from connectors.advisory.storage import AdvisoryStore

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    store = AdvisoryStore(str(tmp_path / "account.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    unsafe = session(pnl=-500, low=-500).model_copy(update={"account": observation(**changes)})
    with pytest.raises(ValueError, match="account identity and equity"):
        store.save_session(p.id, unsafe)
    assert store.evaluation(p.id)[1] == []


def test_nonflat_state_is_persistable_and_cannot_use_flat_sizing(monkeypatch, tmp_path):
    from connectors.advisory.storage import AdvisoryStore
    from core.advisory.account import OpenPosition, WorkingOrder

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    position = OpenPosition(
        position_id="p",
        instrument_id="MES",
        contract="MESZ26",
        side="BUY",
        contracts=1,
        unrealized_pnl="-25",
    )
    order = WorkingOrder(
        order_id="o", instrument_id="MGC", contract="MGCZ26", side="SELL", contracts=1
    )
    account = observation(
        cash_balance="49525", unrealized_pnl="-25", positions=(position,), working_orders=(order,)
    )
    row = session(pnl=-500, low=-500).model_copy(update={"account": account})
    store = AdvisoryStore(str(tmp_path / "nonflat.sqlite3"))
    p = profile()
    store.create_evaluation(p)
    store.save_session(p.id, row)
    saved_profile, rows = AdvisoryStore(str(store.path)).evaluation(p.id)
    assert ev.evaluation_status(saved_profile, rows)["account_state"]["health"] == "KNOWN"
    with pytest.raises(ValueError, match="Open exposure"):
        ev.evaluation_plan(plan(), saved_profile, rows)


def test_request_cannot_override_observed_position_count(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    with pytest.raises(ValueError, match="observed flat"):
        ev.evaluation_plan(plan(existing_standard_contracts=1), profile(), [observed_session()])


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_corrupt_internal_model_copy_cannot_reach_risk(monkeypatch, bad):
    from decimal import Decimal

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    corrupted = observation().model_copy(update={"equity": Decimal(bad)})
    row = session(pnl=-500, low=-500).model_copy(update={"account": corrupted})
    with pytest.raises(ValueError):
        ev.evaluation_plan(plan(), profile(), [row])


def test_explicit_account_clock_and_freshness_boundaries():
    from datetime import timedelta
    from decimal import Decimal

    from core.advisory.account import account_state

    value = observation()
    for seconds, expected in [
        (-0.001, "UNKNOWN"),
        (0, "KNOWN"),
        (1799.999, "KNOWN"),
        (1800, "KNOWN"),
        (1800.001, "UNKNOWN"),
    ]:
        state = account_state(
            value,
            account_id=value.account_id,
            journal_equity=Decimal("49500"),
            now=NOW + timedelta(seconds=seconds),
            max_age_seconds=1800,
        )
        assert state.health == expected
    assert (
        account_state(
            value,
            account_id=value.account_id,
            journal_equity=Decimal("49500"),
            now=NOW.replace(tzinfo=None),
            max_age_seconds=1800,
        ).health
        == "INVALID"
    )


def test_account_snapshot_is_immutable_and_position_pnl_reconciles():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        observation(unrealized_pnl="1", cash_balance="49499")
    value = observation()
    with pytest.raises(ValidationError):
        value.equity = 60000


def test_sizing_never_uses_nominal_capital_over_current_equity(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    with pytest.raises(ValueError, match="journal's current net equity"):
        ev.evaluation_plan(
            plan(account_value=50000, existing_standard_contracts=0),
            profile(),
            [observed_session()],
        )


def test_property_unknown_coverage_cannot_reach_evaluation_sizing():
    from hypothesis import given, settings, strategies as st

    @settings(max_examples=80, derandomize=True, database=None)
    @given(
        pnl=st.decimals(
            min_value=-1000, max_value=1000, places=2, allow_nan=False, allow_infinity=False
        ),
        field=st.sampled_from(["positions", "working_orders", "human_confirmed", "costs_included"]),
    )
    def invariant(pnl, field):
        change = {field: None if field in {"positions", "working_orders"} else False}
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ev, "utcnow", lambda: NOW)
            row = observed_session(pnl=pnl, low=min(0, pnl), **change)
            assert ev.evaluation_status(profile(), [row])["account_state"]["health"] == "UNKNOWN"
            with pytest.raises(ValueError, match="account observation"):
                ev.evaluation_plan(plan(), profile(), [row])

    invariant()


def test_property_verified_state_cannot_exceed_available_risk():
    from decimal import Decimal

    from hypothesis import given, settings, strategies as st

    @settings(max_examples=100, derandomize=True, database=None)
    @given(
        pnl=st.decimals(
            min_value=-1000, max_value=1000, places=2, allow_nan=False, allow_infinity=False
        ),
        risk=st.decimals(
            min_value="0.01", max_value="1", places=2, allow_nan=False, allow_infinity=False
        ),
    )
    def invariant(pnl, risk):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(ev, "utcnow", lambda: NOW)
            equity = Decimal(50000) + pnl
            row = observed_session(pnl=pnl, low=min(0, pnl))
            result = ev.evaluation_plan(
                plan(account_value=equity, risk_percent=risk), profile(), [row]
            )
            loss = Decimal(result["estimated_loss_at_stop"])
            assert 0 <= loss <= equity * risk / 100
            assert loss <= max(0, Decimal(1100) + pnl - 100)
            assert loss <= max(0, equity - Decimal(48000) - 100)
            assert 0 <= Decimal(result["size"]) <= 10

    invariant()


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"account_id": "other"}, "account_identity_mismatch"),
        ({"cash_balance": "49501", "equity": "49501"}, "journal_equity_mismatch"),
    ],
)
def test_account_guard_rejects_identity_or_financial_disagreement(change, reason):
    from decimal import Decimal

    from core.advisory.account import account_state

    state = account_state(
        observation(**change),
        account_id="example-only",
        journal_equity=Decimal(49500),
        now=NOW,
        max_age_seconds=1800,
    )
    assert state.health == "INVALID" and reason in state.reasons


def test_account_guard_rejects_bypassed_model_validation_and_invalid_age_configuration():
    from decimal import Decimal

    from core.advisory.account import account_state

    value = observation().model_copy(update={"positions": None, "equity": Decimal("NaN")})
    result = account_state(
        value,
        account_id="example-only",
        journal_equity=Decimal(49500),
        now=NOW,
        max_age_seconds=1800,
    )
    assert result.health == "INVALID" and result.observation is None
    assert (
        account_state(
            observation(),
            account_id="example-only",
            journal_equity=Decimal(49500),
            now=NOW,
            max_age_seconds=-1,
        ).health
        == "INVALID"
    )


def test_duplicate_position_and_order_identities_are_invalid():
    from pydantic import ValidationError

    from core.advisory.account import OpenPosition, WorkingOrder

    p = OpenPosition(
        position_id="same",
        instrument_id="MNQ",
        contract="MNQZ26",
        side="BUY",
        contracts=1,
        unrealized_pnl=0,
    )
    o = WorkingOrder(
        order_id="same", instrument_id="MGC", contract="MGCZ26", side="BUY", contracts=1
    )
    with pytest.raises(ValidationError, match="Duplicate position"):
        observation(positions=(p, p))
    with pytest.raises(ValidationError, match="Duplicate working-order"):
        observation(working_orders=(o, o))


def test_equity_cannot_disagree_with_cash_and_open_pnl():
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="equity must equal"):
        observation(equity="49501")


def test_session_requires_same_observation_time_and_flat_state_for_finalization(monkeypatch):
    from datetime import timedelta

    from pydantic import ValidationError

    from core.advisory.account import WorkingOrder

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    row = session()
    with pytest.raises(ValidationError, match="same timestamp"):
        ev.EvaluationSession.model_validate(
            row.model_dump()
            | {"account": observation(observed_at=NOW - timedelta(seconds=1)).model_dump()}
        )
    closed = session(23, closed=True)
    order = WorkingOrder(
        order_id="resting", instrument_id="MES", contract="MESZ26", side="BUY", contracts=1
    )
    with pytest.raises(ValidationError, match="finalized session"):
        ev.EvaluationSession.model_validate(
            closed.model_dump()
            | {
                "account": observation(
                    observed_at=closed.as_of,
                    cash_balance=50000,
                    equity=50000,
                    working_orders=(order,),
                ).model_dump()
            }
        )


def test_evaluation_revalidates_policy_and_clock_inputs(monkeypatch):
    from datetime import timedelta
    from decimal import Decimal

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    with pytest.raises(ValueError, match="timezone"):
        ev.evaluation_status(profile(), [], now=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError, match="Drawdown"):
        ev.evaluation_status(profile().model_copy(update={"maximum_drawdown": Decimal(50000)}), [])
    with pytest.raises(ValueError, match="future"):
        ev.evaluation_status(
            profile().model_copy(update={"verified_on": NOW.date() + timedelta(days=1)}), []
        )


def test_foreign_currency_cannot_be_treated_as_usd_equity(monkeypatch):
    from decimal import Decimal

    from core.advisory.account import account_state

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    value = observation(currency="EUR")
    state = account_state(
        value,
        account_id=value.account_id,
        journal_equity=Decimal(49500),
        now=NOW,
        max_age_seconds=1800,
    )
    assert state.health == "INVALID" and "account_currency_mismatch" in state.reasons
    with pytest.raises(ValueError, match="USD"):
        ev.evaluation_plan(plan(), profile(), [observed_session(currency="EUR")])


def test_account_observation_cannot_make_future_journal_rows_current(monkeypatch):
    from datetime import timedelta

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    with pytest.raises(ValueError, match="Future session"):
        ev.evaluation_status(profile(), [observed_session()], now=NOW - timedelta(seconds=1))


def test_known_account_does_not_override_session_closure(monkeypatch):
    from datetime import datetime

    closed_time = datetime(2026, 9, 24, 20, 55, tzinfo=NOW.tzinfo)
    monkeypatch.setattr(ev, "utcnow", lambda: closed_time)
    row = observed_session()
    account = row.account.model_copy(update={"observed_at": closed_time})
    row = row.model_copy(update={"as_of": closed_time, "account": account})
    state = ev.evaluation_status(profile(), [row])
    assert state["account_state"]["health"] == "KNOWN" and state["fresh_observation"]
    with pytest.raises(ValueError, match="permitted evaluation hours"):
        ev.evaluation_plan(plan(), profile(), [row])
