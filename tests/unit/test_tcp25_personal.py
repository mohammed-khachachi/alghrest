"""Hand-calculated personal examples; no firm entitlement or market edge."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from core.advisory.account import AccountObservation, OpenPosition, WorkingOrder
from core.advisory.evaluation import EvaluationProfile, EvaluationSession
from core.advisory.tcp25_personal import (
    POLICY_ID,
    CapacityRequest,
    PersonalEvidence,
    PlanRequest,
    RevisionConflictError,
    assess,
    policy_revision,
    verify_current,
)

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 8, 10, tzinfo=UTC)


def position(root="MES", count=1, side="BUY", identifier="p"):
    return OpenPosition(
        position_id=identifier,
        instrument_id=root,
        contract=root + "Z26",
        side=side,
        contracts=count,
        unrealized_pnl=0,
    )


def context(pnl=0, low=None, positions=(), orders=()):
    profile = EvaluationProfile(
        id="tcp25-synthetic",
        program="trader_career_path",
        starting_balance=25000,
        profit_target=1750,
        daily_loss_limit=550,
        maximum_drawdown=1500,
        minimum_trading_days=0,
        source="https://www.earn2trade.com/trader-career-path",
        verified_on=NOW.date(),
    )
    equity = Decimal(25000) + Decimal(pnl)
    account = AccountObservation(
        account_id=profile.id,
        source="replay",
        source_reference="SYNTHETIC MECHANICS ONLY",
        observed_at=NOW,
        human_confirmed=True,
        costs_included=True,
        currency="USD",
        cash_balance=equity,
        unrealized_pnl=0,
        equity=equity,
        positions=positions,
        working_orders=orders,
    )
    session = EvaluationSession(
        session_date=NOW.date(),
        as_of=NOW,
        net_pnl=pnl,
        lowest_pnl=min(Decimal(0), Decimal(pnl)) if low is None else low,
        closed=False,
        traded=True,
        account=account,
    )
    return profile, [session]


def identity(profile, rows):
    value = assess("tcp25-personal-status-v1", now=NOW, profile=profile, sessions=rows)
    return dict(
        schema_version=2,
        policy_id=POLICY_ID,
        expected_policy_revision=policy_revision(),
        expected_account_revision=value.result["account_revision"],
    )


def capacity(profile, rows, count=1, **changes):
    request = CapacityRequest(
        **(
            identity(profile, rows)
            | dict(instrument_id="MES", contract="MESZ26", additional_contracts=count)
            | changes
        )
    )
    return assess(
        "tcp25-personal-micro-cap-v1", now=NOW, profile=profile, sessions=rows, request=request
    )


def plan(profile, rows, **changes):
    request = PlanRequest(
        **(
            identity(profile, rows)
            | dict(
                instrument_id="MES",
                contract="MESZ26",
                entry="5000",
                stop="4990",
                risk_percent="0.5",
                fees_per_unit="2",
                slippage_points="0.25",
                safety_buffer="10",
                cost_source="synthetic",
                cost_reference="SYNTHETIC MECHANICS ONLY",
                costs_reviewed=True,
            )
            | changes
        )
    )
    return assess(
        "tcp25-personal-plan-v1", now=NOW, profile=profile, sessions=rows, request=request
    )


def test_flat_tcp25_worked_example_and_exact_reopen():
    p, rows = context()
    value = plan(p, rows)
    assert (
        value.result["risk_budget"],
        value.result["loss_per_unit"],
        value.result["personal_contracts"],
        Decimal(value.result["estimated_loss_at_stop"]),
    ) == ("125.0", "53.25", 2, Decimal("106.50"))
    assert (
        value.result["firm_eligibility"] == "BLOCKED" and value.result["qualified_contracts"] == 0
    )
    assert value.result["trade_permitted"] is value.result["execution_enabled"] is False
    assert PersonalEvidence.model_validate_json(value.model_dump_json()) == value
    verify_current(value, now=NOW + timedelta(seconds=1), profile=p, sessions=rows)


@pytest.mark.parametrize(
    "gross,addition,state,remaining",
    [
        (0, 10, "WITHIN_CAP", 10),
        (9, 1, "WITHIN_CAP", 1),
        (9, 2, "BLOCKED", 0),
        (10, 1, "BLOCKED", 0),
        (11, 1, "BLOCKED", 0),
    ],
)
def test_gross_cap_boundary(gross, addition, state, remaining):
    p, rows = context(positions=(position(count=gross),) if gross else ())
    result = capacity(p, rows, addition).result
    assert (result["state"], result["remaining_micro_contracts"]) == (state, remaining)


def test_roots_directions_and_dated_lots_do_not_net():
    p, rows = context(positions=(position(count=4), position("MNQ", 5, "SELL", "q")))
    assert capacity(p, rows).result["remaining_micro_contracts"] == 1
    assert plan(p, rows).result["personal_contracts"] == 0


@pytest.mark.parametrize("root", ["NQ", "ES", "BTCUSDT-PERP", "MYM"])
def test_any_mini_or_unsupported_exposure_blocks_micro_branch(root):
    p, rows = context(positions=(position(root), position("MES", 1, "BUY", "q")))
    assert capacity(p, rows).result["state"] == "BLOCKED"
    assert plan(p, rows).result["personal_contracts"] == 0


@pytest.mark.parametrize("field", ["positions", "orders"])
def test_unknown_coverage_has_no_positive_capacity(field):
    p, rows = context(**{field: None})
    assert capacity(p, rows).result["remaining_micro_contracts"] is None
    assert plan(p, rows).result["personal_contracts"] == 0


def test_working_order_never_receives_protective_exemption():
    p, rows = context(
        orders=(
            WorkingOrder(
                order_id="o", instrument_id="MES", contract="MESZ26", side="SELL", contracts=1
            ),
        )
    )
    assert capacity(p, rows).result["state"] == "UNKNOWN"
    assert plan(p, rows).result["personal_contracts"] == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("starting_balance", 50000),
        ("profit_target", 3000),
        ("daily_loss_limit", 1100),
        ("maximum_drawdown", 2000),
        ("minimum_trading_days", 4),
        ("program", "gauntlet_mini"),
    ],
)
def test_legacy_terms_are_not_converted(field, value):
    p, rows = context()
    p = EvaluationProfile.model_validate(p.model_dump() | {field: value})
    if field == "starting_balance":
        account = rows[0].account.model_copy(
            update={"cash_balance": Decimal(value), "equity": Decimal(value)}
        )
        rows = [
            EvaluationSession.model_validate(
                rows[0].model_dump() | {"account": account.model_dump()}
            )
        ]
    assert plan(p, rows).result["state"] == "BLOCKED"


@pytest.mark.parametrize("pnl", ["-549.99", "-550", "-550.01"])
def test_daily_remaining_and_buffer_use_tcp25_amounts(pnl):
    p, rows = context(pnl=pnl)
    value = plan(p, rows)
    assert value.result["personal_contracts"] == 0
    assert Decimal(value.result["daily_loss_remaining"]) == max(
        Decimal(0), Decimal(550) + Decimal(pnl)
    )


def test_ten_contract_ceiling_and_no_stop_movement():
    p, rows = context()
    value = plan(p, rows, stop="4999.75", fees_per_unit="0", slippage_points="0")
    assert value.result["personal_contracts"] == 10
    assert value.request.stop == Decimal("4999.75")


@pytest.mark.parametrize("field", ["expected_policy_revision", "expected_account_revision"])
def test_stale_revision_cannot_calculate(field):
    p, rows = context()
    with pytest.raises(RevisionConflictError):
        capacity(p, rows, **{field: "0" * 64})


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 1),
        ("policy_id", "user-micro-cap-v1"),
        ("additional_contracts", True),
        ("additional_contracts", 11),
        ("instrument_id", "NQ"),
    ],
)
def test_schema_or_request_downgrade_is_rejected(field, value):
    p, rows = context()
    with pytest.raises(ValidationError):
        capacity(p, rows, **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [
        ("personal_contracts", 11),
        ("qualified_contracts", 1),
        ("firm_eligibility", "READY"),
        ("trade_permitted", True),
        ("risk_budget", "10000"),
    ],
)
def test_forged_saved_result_cannot_replay(field, value):
    p, rows = context()
    data = plan(p, rows).model_dump(mode="json")
    data["result"][field] = value
    with pytest.raises(ValidationError):
        PersonalEvidence.model_validate(data)


def test_expiry_source_identity_and_changed_account_are_rechecked():
    p, rows = context()
    value = plan(p, rows)
    with pytest.raises(RevisionConflictError):
        verify_current(value, now=NOW + timedelta(seconds=1800), profile=p, sessions=rows)
    p2, rows2 = context(pnl=1)
    with pytest.raises(RevisionConflictError):
        verify_current(value, now=NOW, profile=p2, sessions=rows2)
    data = value.model_dump(mode="json")
    data["source_hashes"][next(iter(data["source_hashes"]))] = "0" * 64
    with pytest.raises(ValidationError):
        PersonalEvidence.model_validate(data)


@pytest.mark.parametrize("algorithm", ["tcp25-personal-micro-cap-v1", "tcp25-personal-plan-v1"])
@pytest.mark.parametrize(
    "age_microseconds,valid",
    [
        (1799000000, True),
        (1799999999, True),
        (1800000000, False),
        (1800000001, False),
        (1801000000, False),
    ],
)
@pytest.mark.parametrize("offset_hours", [-12, 0, 5.5, 14])
def test_capacity_expiry_is_exclusive_with_microseconds_and_offset(
    algorithm, age_microseconds, valid, offset_hours
):
    from datetime import timezone

    p, rows = context()
    observed = NOW.replace(microsecond=123456)
    local = observed.astimezone(timezone(timedelta(hours=offset_hours)))
    account = rows[0].account.model_copy(update={"observed_at": local})
    rows = [rows[0].model_copy(update={"as_of": local, "account": account})]
    generated = observed + timedelta(microseconds=age_microseconds)
    status = assess("tcp25-personal-status-v1", now=generated, profile=p, sessions=rows)
    request_type = CapacityRequest if "micro-cap" in algorithm else PlanRequest
    raw = (
        capacity(p, context()[1]).request
        if request_type is CapacityRequest
        else plan(p, context()[1]).request
    ).model_dump()
    raw["expected_account_revision"] = status.result["account_revision"]
    value = assess(
        algorithm,
        now=generated.astimezone(timezone(timedelta(hours=offset_hours))),
        profile=p,
        sessions=rows,
        request=request_type.model_validate(raw),
    )
    positive = value.result["state"] in {"WITHIN_CAP", "CALCULATED"}
    assert positive is valid
    expires = datetime.fromisoformat(value.result["expires_at"])
    assert expires == observed + timedelta(seconds=1800)
    assert not positive or expires > value.generated_at
    if not valid:
        assert "personal_capacity_expired" in value.result["reasons"]
        if request_type is CapacityRequest:
            assert value.result["remaining_micro_contracts"] is None
        else:
            assert value.result["personal_contracts"] == 0
    assert value.result["firm_eligibility"] == "BLOCKED"
    assert value.result["qualified_contracts"] == 0
    assert value.result["passing_probability"] == "UNKNOWN"
    assert not value.result["trade_permitted"] and not value.result["execution_enabled"]


@pytest.mark.parametrize("date", ["2026-03-09", "2026-11-02"])
@pytest.mark.parametrize("microseconds_before_close", [1, 0, -1])
def test_capacity_window_expiry_around_chicago_dst(date, microseconds_before_close, monkeypatch):
    p, rows = context()
    observed = datetime.fromisoformat(date + "T13:59:59+00:00")
    p = p.model_copy(update={"verified_on": observed.date()})
    account = rows[0].account.model_copy(update={"observed_at": observed})
    rows = [
        rows[0].model_copy(
            update={"session_date": observed.date(), "as_of": observed, "account": account}
        )
    ]
    close = observed.replace(hour=14, minute=0, second=0)
    generated = close - timedelta(microseconds=microseconds_before_close)
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: generated)
    status = assess("tcp25-personal-status-v1", now=generated, profile=p, sessions=rows)
    request = CapacityRequest(
        schema_version=2,
        policy_id=POLICY_ID,
        expected_policy_revision=policy_revision(),
        expected_account_revision=status.result["account_revision"],
        instrument_id="MES",
        contract="MESZ26",
        additional_contracts=1,
    )
    value = assess(
        "tcp25-personal-micro-cap-v1", now=generated, profile=p, sessions=rows, request=request
    )
    assert datetime.fromisoformat(value.result["expires_at"]) == close
    assert (value.result["state"] == "WITHIN_CAP") is (microseconds_before_close > 0)
    if microseconds_before_close <= 0:
        assert value.result["remaining_micro_contracts"] == 0
