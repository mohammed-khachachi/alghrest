"""Synthetic personal-rule arithmetic, never trading-edge evidence."""

from decimal import Decimal

import pytest

from core.advisory.user_risk import UserRiskRequest, assess_user_risk, personal_account_status
from tests.unit.test_user_policy import NOW, context

pytestmark = pytest.mark.unit


def test_confirmed_flat_mes_uses_costs_and_exact_risk_budget(monkeypatch):
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: NOW)
    profile, rows = context()
    status = personal_account_status(profile, rows, now=NOW)
    request = UserRiskRequest(
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
        expected_account_revision=status["account_revision"],
    )
    result = assess_user_risk(profile, rows, request, now=NOW)
    assert result.state == "CALCULATED"
    assert (
        result.risk_budget,
        result.loss_per_unit,
        result.contracts,
        result.estimated_loss_at_stop,
    ) == (Decimal("250"), Decimal("53.25"), 4, Decimal("213"))
    assert result.trade_permitted is result.execution_enabled is False


def make_request(profile, rows, **changes):
    return UserRiskRequest.model_validate(
        dict(
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
            expected_account_revision=personal_account_status(profile, rows, now=NOW)[
                "account_revision"
            ],
        )
        | changes
    )


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: NOW)


def test_negative_net_profit_uses_daily_capacity_without_double_deducting_costs():
    p, rows = context(pnl=Decimal("-1000"))
    result = assess_user_risk(p, rows, make_request(p, rows, stop="4999"), now=NOW)
    assert result.state == "CALCULATED"
    assert (
        result.journal_equity_usd,
        result.daily_loss_remaining,
        result.risk_budget,
        result.loss_per_unit,
        result.contracts,
        result.estimated_loss_at_stop,
    ) == (Decimal("49000"), Decimal("100"), Decimal("90"), Decimal("8.25"), 10, Decimal("82.5"))


@pytest.mark.parametrize(
    "changes",
    [
        dict(instrument_id="MNQ", contract="MNQZ26", stop="5001"),
        dict(stop="4999.75", fees_per_unit="0", slippage_points="0"),
    ],
)
def test_short_mnq_and_explicit_zero_cost_micro_cap(changes):
    p, rows = context()
    result = assess_user_risk(p, rows, make_request(p, rows, **changes), now=NOW)
    assert result.state == "CALCULATED" and result.contracts == 20
    assert result.trade_permitted is False


@pytest.mark.parametrize(
    "changes",
    [
        dict(costs_reviewed=False),
        dict(cost_reference=" "),
        dict(risk_percent="1.01"),
        dict(entry="5000.01"),
        dict(stop="5000"),
        dict(instrument_id="ES", contract="ESZ26"),
        dict(contract="MNQZ26"),
        dict(fees_per_unit="NaN"),
        dict(slippage_points="-1"),
        dict(safety_buffer="0"),
    ],
)
def test_invalid_or_incomplete_request_is_rejected(changes):
    p, rows = context()
    with pytest.raises(ValueError):
        make_request(p, rows, **changes)


def test_missing_costs_are_not_default_zero():
    p, rows = context()
    for key in (
        "fees_per_unit",
        "slippage_points",
        "cost_source",
        "cost_reference",
        "costs_reviewed",
        "expected_account_revision",
    ):
        payload = make_request(p, rows).model_dump()
        del payload[key]
        with pytest.raises(ValueError):
            UserRiskRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["entry", "stop"])
def test_oversized_price_is_a_controlled_validation_error(field):
    p, rows = context()
    with pytest.raises(ValueError, match="price.*too large"):
        make_request(p, rows, **{field: "1000000000000000000000000000000"})


@pytest.mark.parametrize(
    "changes, state, reason",
    [
        (dict(positions=None), "UNKNOWN", "positions_unknown"),
        (dict(human_confirmed=False), "UNKNOWN", "unconfirmed_account_observation"),
        (dict(costs_included=False), "UNKNOWN", "account_costs_unknown"),
        (dict(pnl=Decimal("-1100")), "BLOCKED", "recorded_breach:daily_loss:2026-10-08"),
        (dict(pnl=Decimal("-2000")), "BLOCKED", "recorded_breach:drawdown_boundary:2026-10-08"),
    ],
)
def test_incomplete_and_breached_evidence_never_sizes(changes, state, reason):
    p, rows = context(**changes)
    result = assess_user_risk(p, rows, make_request(p, rows), now=NOW)
    assert result.state == state and reason in result.reasons and result.contracts == 0


def test_open_exposure_cap_still_available_but_stop_risk_is_unknown():
    from core.advisory.user_policy import assess_user_policy
    from tests.unit.test_user_policy import order, position, request

    p, rows = context(positions=(position(quantity=10),), orders=(order(quantity=9),))
    assert assess_user_policy(p, rows, request(), now=NOW).remaining_micro_contracts == 1
    result = assess_user_risk(p, rows, make_request(p, rows), now=NOW)
    assert result.state == "UNKNOWN" and result.contracts == 0
    assert "open_exposure_stop_risk_unknown" in result.reasons


def test_unmatched_profile_cannot_be_silently_migrated():
    p, rows = context()
    p = p.model_copy(update={"profit_target": Decimal("1750")})
    result = assess_user_risk(p, rows, make_request(p, rows), now=NOW)
    assert result.state == "BLOCKED" and result.contracts == 0
    assert "journal_personal_terms_mismatch" in result.reasons


def test_strict_consistency_and_closed_ratchet_ignore_legacy_minimum_days():
    from datetime import timedelta

    from core.advisory.evaluation import EvaluationSession

    p, _ = context()
    p = p.model_copy(update={"minimum_trading_days": 30})
    rows = []
    for i, pnl in enumerate(("900", "700", "700", "700")):
        stamp = (NOW - timedelta(days=4 - i)).replace(hour=21)
        rows.append(
            EvaluationSession(
                session_date=stamp.date(),
                as_of=stamp,
                net_pnl=pnl,
                lowest_pnl=0,
                closed=True,
                traded=True,
            )
        )
    equality = personal_account_status(p, rows, now=NOW)
    assert equality["total_pnl"] == "3000" and equality["minimum_balance"] == "50000"
    assert equality["consistency_met"] is equality["recorded_targets_met"] is False
    rows[-1] = rows[-1].model_copy(update={"net_pnl": Decimal("700.01")})
    complete = personal_account_status(p, rows, now=NOW)
    assert complete["recorded_targets_met"] is True and complete["trading_days"] == 4
    p, opened = context(pnl=Decimal("900"))
    assert personal_account_status(p, opened, now=NOW)["minimum_balance"] == "48000"


def test_recorded_loss_breach_retained_after_recovery_and_next_session():
    from datetime import timedelta

    from core.advisory.evaluation import EvaluationSession

    p, rows = context(pnl=Decimal("400"))
    stamp = (NOW - timedelta(days=1)).replace(hour=21)
    old = EvaluationSession(
        session_date=stamp.date(),
        as_of=stamp,
        net_pnl=0,
        lowest_pnl=-1100,
        closed=True,
        traded=True,
    )
    result = assess_user_risk(p, [old, *rows], make_request(p, [old, *rows]), now=NOW)
    assert result.state == "BLOCKED" and result.contracts == 0
    assert "recorded_breach:daily_loss:2026-10-07" in result.reasons


def test_expiry_revision_and_hash_verification_replays_serialized_evidence():
    from datetime import timedelta

    from core.advisory.user_risk import UserRiskAssessment, verify_user_risk_assessment

    p, rows = context()
    value = assess_user_risk(p, rows, make_request(p, rows), now=NOW)
    restored = UserRiskAssessment.model_validate_json(value.model_dump_json())
    for _ in range(2):
        verify_user_risk_assessment(restored, now=NOW, current_profile=p, current_sessions=rows)
    for changed in (
        {"contracts": 20},
        {"risk_budget": Decimal("251")},
        {"source_hashes": {}},
        {"execution_enabled": True},
        {"reasons": ("invented",)},
    ):
        forged = value.model_copy(update=changed)
        with pytest.raises(ValueError):
            UserRiskAssessment.model_validate_json(forged.model_dump_json())
        with pytest.raises(ValueError):
            verify_user_risk_assessment(forged, now=NOW, current_profile=p, current_sessions=rows)
    for instant in (NOW - timedelta(seconds=1), NOW + timedelta(seconds=1800)):
        with pytest.raises(ValueError):
            verify_user_risk_assessment(
                value, now=instant, current_profile=p, current_sessions=rows
            )
    changed = rows[0].model_copy(update={"notes": "changed"})
    with pytest.raises(ValueError, match="revision"):
        verify_user_risk_assessment(value, now=NOW, current_profile=p, current_sessions=[changed])
    assert assess_user_risk(p, [changed], make_request(p, rows), now=NOW).state == "BLOCKED"


def test_whole_file_mismatch_rejected_after_source_change(monkeypatch):
    from pathlib import Path

    from core.advisory.user_risk import UserRiskAssessment

    p, rows = context()
    value = assess_user_risk(p, rows, make_request(p, rows), now=NOW)
    read = Path.read_bytes
    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda path: read(path) + b"changed" if path.name == "analysis.py" else read(path),
    )
    with pytest.raises(ValueError, match="hashes"):
        UserRiskAssessment.model_validate_json(value.model_dump_json())


@pytest.mark.parametrize(
    "hour,state", [(6, "BLOCKED"), (7, "CALCULATED"), (13, "CALCULATED"), (14, "BLOCKED")]
)
def test_personal_entry_clock_not_external_weekend_gate(monkeypatch, hour, state):
    instant = NOW.replace(day=11, hour=hour)  # Sunday is allowed by personal clock only.
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: instant)
    p, rows = context(as_of=instant)
    request = make_request(
        p,
        [],
        expected_account_revision=personal_account_status(p, rows, now=instant)["account_revision"],
    )
    result = assess_user_risk(p, rows, request, now=instant)
    assert result.state == state
    assert result.contracts == 0 if state == "BLOCKED" else result.contracts > 0


def test_missing_and_stale_sessions_never_size_and_future_rejected():
    from datetime import timedelta

    p, rows = context()
    request = make_request(p, rows)
    assert assess_user_risk(p, [], request, now=NOW).contracts == 0
    assert assess_user_risk(p, rows, request, now=NOW + timedelta(seconds=1801)).state == "UNKNOWN"
    with pytest.raises(ValueError):
        assess_user_risk(p, rows, request, now=NOW - timedelta(seconds=1))
