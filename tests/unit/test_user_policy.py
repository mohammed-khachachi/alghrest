"""Personal Micro ceiling mechanics; no firm entitlement or trading-edge evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from api.services.advisory import journal_revision
from core.advisory import evaluation as ev
from core.advisory.account import AccountObservation, OpenPosition, WorkingOrder
from core.advisory.models import PolicyRiskAllowance
from core.advisory.policy import PolicyAssessment
from core.advisory.risk import RiskDecision, RiskInputs
from core.advisory.user_policy import (
    UserPolicyAssessment,
    UserPolicyRequest,
    assess_user_policy,
    verify_user_policy_assessment,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 8, 10, tzinfo=UTC)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)


def position(root="MES", quantity=1, **changes):
    return OpenPosition.model_validate(
        dict(
            position_id="position-1",
            instrument_id=root,
            contract=root + "Z26",
            side="BUY",
            contracts=quantity,
            unrealized_pnl=0,
        )
        | changes
    )


def order(root="MNQ", quantity=1, **changes):
    return WorkingOrder.model_validate(
        dict(
            order_id="order-1",
            instrument_id=root,
            contract=root + "Z26",
            side="BUY",
            contracts=quantity,
        )
        | changes
    )


def request(**changes):
    return UserPolicyRequest.model_validate(
        dict(instrument_id="MES", contract="MESZ26", additional_contracts=1) | changes
    )


def context(*, positions=(), orders=(), pnl=Decimal(0), as_of=NOW, **observation_changes):
    profile = ev.EvaluationProfile(
        id="user-example",
        program="trader_career_path",
        starting_balance=50000,
        profit_target=3000,
        daily_loss_limit=1100,
        maximum_drawdown=2000,
        minimum_trading_days=0,
        source="https://example.com/synthetic-journal",
        verified_on=NOW.date(),
    )
    unrealized = sum((p.unrealized_pnl for p in positions), Decimal(0)) if positions else Decimal(0)
    account = AccountObservation.model_validate(
        dict(
            account_id=profile.id,
            source="replay",
            source_reference="SYNTHETIC MECHANICS ONLY",
            observed_at=as_of,
            human_confirmed=True,
            costs_included=True,
            currency="USD",
            cash_balance=Decimal(50000) + pnl - unrealized,
            unrealized_pnl=unrealized,
            equity=Decimal(50000) + pnl,
            positions=positions,
            working_orders=orders,
        )
        | observation_changes
    )
    row = ev.EvaluationSession(
        session_date=as_of.date(),
        as_of=as_of,
        net_pnl=pnl,
        lowest_pnl=min(Decimal(0), pnl),
        closed=False,
        traded=bool(positions or orders or pnl),
        account=account,
    )
    return profile, [row]


def check(*, now=NOW, addition=1, **changes):
    profile, rows = context(**changes)
    return assess_user_policy(profile, rows, request(additional_contracts=addition), now=now)


@pytest.mark.parametrize(
    "quantity,addition,state,remaining",
    [
        (0, 20, "WITHIN_CAP", 20),
        (19, 1, "WITHIN_CAP", 1),
        (19, 2, "BLOCKED", 0),
        (20, 1, "BLOCKED", 0),
        (21, 1, "BLOCKED", 0),
    ],
)
def test_fixed_shared_cap_and_requested_additions(quantity, addition, state, remaining):
    value = check(positions=(position(quantity=quantity),) if quantity else (), addition=addition)
    assert (value.state, value.gross_micro_contracts, value.remaining_micro_contracts) == (
        state,
        quantity,
        remaining,
    )
    assert value.trade_permitted is value.execution_enabled is False
    assert value.firm_compliance == "NOT_ASSESSED" and value.passing_probability == "UNKNOWN"


def test_gross_mixed_roots_directions_expiries_and_working_orders_share_one_cap():
    positions = (
        position(quantity=10),
        position("MNQ", 5, position_id="position-2", side="SELL", contract="MNQH27"),
    )
    value = check(positions=positions, orders=(order(quantity=4),))
    assert value.state == "WITHIN_CAP" and value.gross_micro_contracts == 19
    assert value.remaining_micro_contracts == 1
    assert check(positions=positions, orders=(order(quantity=5),)).state == "BLOCKED"


@pytest.mark.parametrize("root", ["NQ", "ES", "MYM", "UNKNOWN"])
@pytest.mark.parametrize("kind", ["position", "order"])
def test_unsupported_exposure_is_never_ignored(root, kind):
    value = check(
        **({"positions": (position(root),)} if kind == "position" else {"orders": (order(root),)})
    )
    assert value.state == "BLOCKED" and value.remaining_micro_contracts == 0
    assert value.gross_micro_contracts is None
    assert "unsupported_user_policy_exposure" in value.reasons


def test_malformed_dated_contract_in_exposure_is_blocked():
    assert check(positions=(position(contract="MNQZ26"),)).state == "BLOCKED"


@pytest.mark.parametrize(
    "changes",
    [
        {"instrument_id": "NQ", "contract": "NQZ26"},
        {"instrument_id": "ES", "contract": "ESZ26"},
        {"contract": "MES"},
        {"contract": "MNQZ26"},
        {"additional_contracts": 0},
        {"additional_contracts": -1},
        {"additional_contracts": True},
        {"additional_contracts": 1.5},
        {"maximum_micro_contracts": 100},
    ],
)
def test_invalid_request_cannot_change_or_bypass_personal_ceiling(changes):
    with pytest.raises(ValidationError):
        request(**changes)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"positions": None}, "positions_unknown"),
        ({"orders": None}, "working_orders_unknown"),
        ({"costs_included": False}, "account_costs_unknown"),
        ({"human_confirmed": False}, "unconfirmed_account_observation"),
    ],
)
def test_incomplete_account_evidence_has_no_personal_capacity(changes, reason):
    value = check(**changes)
    assert value.state == "UNKNOWN" and value.remaining_micro_contracts is None
    assert reason in value.reasons


def test_missing_session_and_missing_account_cannot_supply_capacity():
    p, rows = context()
    for records in ([], [rows[0].model_copy(update={"account": None})]):
        value = assess_user_policy(p, records, request(), now=NOW)
        assert value.state == "UNKNOWN" and value.remaining_micro_contracts is None


@pytest.mark.parametrize("seconds,state", [(1800, "WITHIN_CAP"), (1801, "UNKNOWN")])
def test_account_and_session_freshness_boundary(seconds, state):
    value = check(now=NOW + timedelta(seconds=seconds))
    assert value.state == state
    if state == "UNKNOWN":
        assert value.remaining_micro_contracts is None


@pytest.mark.parametrize(
    "time_text,state",
    [
        ("06:59:59.999999", "BLOCKED"),
        ("07:00:00", "WITHIN_CAP"),
        ("13:59:59.999999", "WITHIN_CAP"),
        ("14:00:00", "BLOCKED"),
    ],
)
def test_fixed_utc_entry_window_boundaries(monkeypatch, time_text, state):
    instant = datetime.fromisoformat("2026-10-08T" + time_text + "+00:00")
    monkeypatch.setattr(ev, "utcnow", lambda: instant)
    p, rows = context(as_of=instant)
    value = assess_user_policy(p, rows, request(), now=instant)
    assert value.state == state
    if state == "BLOCKED":
        assert value.remaining_micro_contracts == 0


def test_net_fees_and_unrealized_pnl_are_not_deducted_twice():
    value = check(positions=(position(unrealized_pnl=Decimal("40")),), pnl=Decimal("-12.50"))
    assert value.journal_equity_usd == Decimal("49987.50")
    assert value.account_state.observation.cash_balance == Decimal("49947.50")
    assert value.state == "WITHIN_CAP"  # Fixed user cap; no invented negative-profit band.


def test_revision_matches_existing_journal_and_old_request_is_blocked():
    p, rows = context()
    value = assess_user_policy(p, rows, request(), now=NOW)
    assert value.account_revision == journal_revision(p, rows)
    changed = assess_user_policy(p, rows, request(expected_account_revision="a" * 64), now=NOW)
    assert changed.state == "BLOCKED" and changed.remaining_micro_contracts == 0


def test_personal_ceiling_does_not_depend_on_firm_rule_review_or_profit_bands():
    p, rows = context()
    p = p.model_copy(update={"verified_on": NOW.date() - timedelta(days=90)})
    assert assess_user_policy(p, rows, request(), now=NOW).state == "WITHIN_CAP"


def test_clock_compares_utc_instant_and_rejects_naive_time():
    from datetime import timezone

    p, rows = context()
    local = NOW.astimezone(timezone(timedelta(hours=6)))
    assert assess_user_policy(p, rows, request(), now=local).state == "WITHIN_CAP"
    with pytest.raises(ValueError, match="timezone"):
        assess_user_policy(p, rows, request(), now=NOW.replace(tzinfo=None))


def test_bypassed_nested_validation_and_future_profile_cannot_produce_capacity():
    p, rows = context()
    forged_request = request().model_copy(update={"additional_contracts": -1})
    with pytest.raises(ValueError):
        assess_user_policy(p, rows, forged_request, now=NOW)
    forged_account = rows[0].account.model_copy(update={"equity": Decimal(50001)})
    with pytest.raises(ValueError):
        assess_user_policy(
            p, [rows[0].model_copy(update={"account": forged_account})], request(), now=NOW
        )


@pytest.mark.parametrize("fault", ["future", "identity", "equity", "closed"])
def test_inconsistent_or_closed_journal_never_qualifies(monkeypatch, fault):
    p, rows = context()
    row = rows[0]
    if fault == "closed":
        stamp = NOW.replace(day=7, hour=21)
        rows = [
            row.model_copy(
                update={
                    "session_date": stamp.date(),
                    "as_of": stamp,
                    "closed": True,
                    "account": row.account.model_copy(update={"observed_at": stamp}),
                }
            )
        ]
        assert assess_user_policy(p, rows, request(), now=NOW).state == "UNKNOWN"
        return
    if fault == "future":
        stamp = NOW + timedelta(seconds=1)
        changes = {"observed_at": stamp}
        row = row.model_copy(update={"as_of": stamp})
    elif fault == "identity":
        changes = {"account_id": "other"}
    else:
        changes = {"equity": Decimal(50001), "cash_balance": Decimal(50001)}
    rows = [row.model_copy(update={"account": row.account.model_copy(update=changes)})]
    with pytest.raises(ValueError):
        assess_user_policy(p, rows, request(), now=NOW)


@pytest.mark.parametrize(
    "changes",
    [
        {"gross_micro_contracts": 0},
        {"remaining_micro_contracts": 20},
        {"account_revision": "b" * 64},
        {"journal_equity_usd": Decimal(50001)},
        {"state": "BLOCKED"},
        {"reasons": ("invented",)},
        {"maximum_micro_contracts": 21},
        {"execution_enabled": True},
        {"trade_permitted": True},
        {"firm_compliance": "VERIFIED"},
    ],
)
def test_reconstruction_and_public_verifier_reject_tampering(changes):
    value = check(positions=(position(),))
    forged = value.model_copy(update=changes)
    with pytest.raises(ValueError):
        UserPolicyAssessment.model_validate_json(forged.model_dump_json())
    with pytest.raises(ValueError):
        verify_user_policy_assessment(forged)


def test_personal_result_cannot_be_a_firm_assessment_or_positive_risk_allowance():
    value = check()
    restored = UserPolicyAssessment.model_validate_json(value.model_dump_json())
    assert restored == value
    verify_user_policy_assessment(restored)
    for model in (PolicyAssessment, PolicyRiskAllowance, RiskDecision):
        with pytest.raises(ValidationError):
            model.model_validate(value.model_dump())
    with pytest.raises(ValidationError):
        RiskInputs.model_validate(
            dict(
                id="user",
                version="v1",
                known_at=NOW,
                source_reference="SYNTHETIC",
                halted=False,
                configuration=None,
                history=None,
                allowance=value.model_dump(),
            )
        )
