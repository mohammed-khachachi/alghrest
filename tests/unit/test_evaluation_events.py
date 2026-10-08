"""Synthetic event tapes and independent financial boundary/replay oracles."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

import pytest
from hypothesis import given, strategies as st
from pydantic import ValidationError

from backtesting.evaluation import (
    EvaluationEvent,
    EvaluationSimulation,
    EvaluationTape,
    MarginCapacity,
    simulate_evaluation,
    verify_evaluation_simulation,
)
from core.advisory.evaluation import CHICAGO, initial_eod_state, project_eod_session, session_clock
from core.advisory.models import CATALOG
from core.advisory.policy import (
    ProgressionBand,
    ProgressionSchedule,
    TradingCalendar,
    TradingWindow,
    tcp25_rules,
)

pytestmark = pytest.mark.unit
D = Decimal
ROOTS = tcp25_rules().eligible_markets


def at(day=6, hour=12, minute=0):
    return datetime(2026, 10, day, hour, minute, tzinfo=CHICAGO).astimezone(UTC)


def event(kind, *, day=6, hour=12, minute=0, **values):
    return EvaluationEvent(
        **(dict(id=f"{day}-{hour}-{minute}-{kind}", at=at(day, hour, minute), kind=kind) | values)
    )


def opening(**values):
    return event(
        "OPEN",
        **(
            dict(
                position_id="p",
                instrument_id="MES",
                contract="MESZ26",
                side="BUY",
                quantity=1,
                price=D(100),
                commission_usd=D(1),
            )
            | values
        ),
    )


def tape(events=None, **changes):
    rules = changes.pop("rules", tcp25_rules())
    known = at(hour=10)
    progression = ProgressionSchedule(
        id="synthetic-ladder",
        version="example-1",
        policy_id=rules.id,
        policy_version=rules.version,
        known_at=known,
        source_reference="Synthetic bands; NOT official TCP25 account bands",
        confirmed=True,
        bands=tuple(
            ProgressionBand(minimum_equity=D(x), maximum_standard_contracts=n)
            for x, n in [(23500, 1), (25500, 2), (26500, 3)]
        ),
    )
    calendar = TradingCalendar(
        id="synthetic-calendar",
        version="example-1",
        known_at=known,
        source_reference="Synthetic regular sessions; NOT authenticated exchange schedule",
        confirmed=True,
        complete=True,
        coverage_start=at(hour=8),
        coverage_end=at(day=10, hour=17),
        covered_markets=ROOTS,
        windows=tuple(
            TradingWindow(
                instrument_id=root,
                start=at(day=day, hour=8),
                end=at(day=day, hour=16),
                flat_by=at(day=day, hour=15, minute=50),
            )
            for day in range(6, 10)
            for root in ROOTS
        ),
    )
    return EvaluationTape(
        **(
            dict(
                id="synthetic-events",
                version="1",
                origin="synthetic",
                source_reference="Hand-calculated fixture, no account/data entitlement attestation",
                rules=rules,
                policy_confirmed=True,
                fills_complete=True,
                intraday_extrema_complete=True,
                progression=progression,
                calendar=calendar,
                margin=tuple(
                    MarginCapacity(
                        id=root,
                        instrument_id=root,
                        known_at=known,
                        confirmed=True,
                        maximum_total_contracts=30,
                        source_reference="Synthetic capacity",
                    )
                    for root in ROOTS
                ),
                events=tuple(
                    events
                    or [
                        event(
                            "FLOOR_SYNC",
                            hour=11,
                            minimum_balance=rules.starting_balance - rules.maximum_drawdown,
                            confirmed=True,
                        ),
                        opening(),
                    ]
                ),
            )
            | changes
        )
    )


def complete_tape():
    events = [event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=True)]
    for day in range(6, 10):
        events.extend(
            [
                opening(day=day, position_id=f"p{day}"),
                event(
                    "CLOSE",
                    day=day,
                    hour=14,
                    position_id=f"p{day}",
                    price=D(190),
                    commission_usd=D(1),
                ),
                event("SESSION_END", day=day, hour=16),
                event(
                    "FLOOR_SYNC",
                    day=day,
                    hour=16,
                    minute=10,
                    minimum_balance=min(D(25000), D(23500) + (day - 5) * 448),
                    confirmed=True,
                ),
            ]
        )
    return tape(events)


def test_four_days_hand_calculated_pass_and_replay():
    result = simulate_evaluation(complete_tape())
    assert result.outcome == "PASS"
    assert result.steps[-1].cash_balance == D(26792)
    assert result.steps[-1].financial.floor == D(25000)
    assert result.steps[-1].financial.trading_days == 4
    assert result.steps[-1].session_net_pnl == 448
    assert result.steps[-1].financial.best_day == 448
    assert all(
        s.session_lowest_pnl == -1 for s in result.steps if s.event_id.endswith("SESSION_END")
    )
    assert (
        not result.rule_exact_verified
        and not result.trade_permitted
        and not result.execution_enabled
    )
    assert verify_evaluation_simulation(result) == result
    assert EvaluationSimulation.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    "offset,expected", [(D("-1e-20"), "CONTINUE"), (D(0), "FAIL"), (D("1e-20"), "FAIL")]
)
def test_daily_commission_boundary(offset, expected):
    fee = D(550) + offset
    result = simulate_evaluation(
        tape(
            [
                event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=True),
                opening(commission_usd=fee),
                event("CLOSE", hour=14, position_id="p", price=D(300), commission_usd=D(0)),
            ]
        )
    )
    assert result.steps[1].outcome == expected
    if expected == "FAIL":
        assert len(result.steps) == 2 and result.outcome == "FAIL"
        assert "daily_loss_boundary" in result.steps[-1].breaches


@pytest.mark.parametrize("offset,failed", [(D("-1e-20"), False), (D(0), True), (D("1e-20"), True)])
def test_drawdown_touch_with_daily_rule_separately_widened(offset, failed):
    rules = tcp25_rules().model_copy(
        update={"daily_loss_limit": D(2000), "version": "synthetic-wide-daily"}
    )
    result = simulate_evaluation(
        tape(
            [
                event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=True),
                opening(commission_usd=D(1500) + offset),
            ],
            rules=rules,
        )
    )
    assert ("drawdown_boundary" in result.steps[-1].breaches) == failed


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_catalog_pnl_both_directions(root, side):
    spec = CATALOG[root]
    with localcontext() as context:
        context.prec = 80
        price = D(100) * spec.tick_size
        close = price + (spec.tick_size if side == "BUY" else -spec.tick_size)
        expected = spec.tick_size * spec.point_value - D(2)
    result = simulate_evaluation(
        tape(
            [
                event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=True),
                opening(instrument_id=root, contract=f"{root}Z26", side=side, price=price),
                event("CLOSE", hour=14, position_id="p", price=close, commission_usd=D(1)),
            ]
        )
    )
    assert result.steps[-1].cash_balance == D(25000) + expected
    assert result.steps[-1].unrealized_pnl == 0
    assert result.steps[1].standard_equivalents == (D(1) if root == "NQ" else D(".1"))


@pytest.mark.parametrize("closing", [False, True])
def test_realtime_ladder_downgrade_cannot_be_hidden_by_full_close(closing):
    rules = tcp25_rules().model_copy(
        update={
            "starting_balance": D(26000),
            "daily_loss_limit": D(2000),
            "version": "synthetic-capital",
        }
    )
    values = {"commission_usd": D(0)} if closing else {}
    result = simulate_evaluation(
        tape(
            [
                event("FLOOR_SYNC", hour=11, minimum_balance=D(24500), confirmed=True),
                opening(quantity=20, commission_usd=D(0)),
                event(
                    "CLOSE" if closing else "MARK",
                    hour=14,
                    position_id="p",
                    price=D("94.75"),
                    **values,
                ),
            ],
            rules=rules,
        )
    )
    assert result.outcome == "FAIL"
    assert result.steps[-1].breaches == ("progression_ladder_size",)
    assert result.steps[-1].equity == D(25475)


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("policy_confirmed", False, "unconfirmed_evaluation_policy"),
        ("fills_complete", False, "incomplete_fill_history"),
        ("intraday_extrema_complete", False, "unverified_intraday_extrema"),
        ("progression", None, "unknown_progression_schedule"),
        ("calendar", None, "unknown_trading_calendar"),
        ("margin", (), "unknown_margin_capacity"),
    ],
)
def test_missing_evidence_censors_every_pass(field, value, reason):
    source = complete_tape().model_copy(update={field: value})
    result = simulate_evaluation(source)
    assert result.outcome == "CENSORED" and reason in result.steps[-1].unknowns
    assert not result.trade_permitted


def test_incomplete_fills_censor_even_observed_loss():
    result = simulate_evaluation(tape([opening(commission_usd=D(551))], fills_complete=False))
    assert result.outcome == "CENSORED" and "daily_loss_boundary" in result.steps[-1].breaches


@pytest.mark.parametrize(
    "case", ["late", "unconfirmed", "incomplete", "outside", "uncovered", "closed"]
)
def test_calendar_evidence_distinguishes_unknown_from_closed(case):
    source = tape()
    changes = {
        "late": {"known_at": at(hour=14)},
        "unconfirmed": {"confirmed": False},
        "incomplete": {"complete": False},
        "outside": {"coverage_end": at(hour=10), "windows": ()},
        "uncovered": {
            "covered_markets": ("NQ",),
            "windows": tuple(w for w in source.calendar.windows if w.instrument_id == "NQ"),
        },
        "closed": {"windows": ()},
    }[case]
    result = simulate_evaluation(
        source.model_copy(update={"calendar": source.calendar.model_copy(update=changes)})
    )
    assert result.outcome == ("FAIL" if case == "closed" else "CENSORED")
    if case != "closed":
        assert not result.steps[-1].breaches


@pytest.mark.parametrize("case", ["late", "unconfirmed", "policy", "floor", "ceiling"])
def test_unknown_ladder_is_not_invented(case):
    source = tape()
    changes = {
        "late": {"known_at": at(hour=14)},
        "unconfirmed": {"confirmed": False},
        "policy": {"policy_version": "other"},
        "floor": {
            "bands": (ProgressionBand(minimum_equity=D(24000), maximum_standard_contracts=1),)
        },
        "ceiling": {
            "bands": (ProgressionBand(minimum_equity=D(23500), maximum_standard_contracts=4),)
        },
    }[case]
    result = simulate_evaluation(
        source.model_copy(update={"progression": source.progression.model_copy(update=changes)})
    )
    assert result.outcome == "CENSORED"
    assert "unknown_progression_schedule" in result.steps[-1].unknowns


@pytest.mark.parametrize("case", ["zero", "unconfirmed", "late"])
def test_margin_censors_conflict_or_unknown(case):
    source = tape()
    changes = {
        "zero": {"maximum_total_contracts": 0},
        "unconfirmed": {"confirmed": False},
        "late": {"known_at": at(hour=14)},
    }[case]
    result = simulate_evaluation(
        source.model_copy(
            update={"margin": tuple(m.model_copy(update=changes) for m in source.margin)}
        )
    )
    assert result.outcome == "CENSORED" and not result.steps[-1].breaches


def test_no_intraday_trailing_then_eod_raises_floor():
    rules = tcp25_rules().model_copy(
        update={"daily_loss_limit": D(5000), "version": "synthetic-wide"}
    )
    events = [
        event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=True),
        opening(commission_usd=D(0)),
        event("MARK", hour=13, position_id="p", price=D(500)),
        event("MARK", hour=14, position_id="p", price=D(20)),
        event("CLOSE", hour=15, position_id="p", price=D(200), commission_usd=D(0)),
        event("SESSION_END", hour=16),
        event("FLOOR_SYNC", hour=16, minute=10, minimum_balance=D(24000), confirmed=True),
    ]
    result = simulate_evaluation(tape(events, rules=rules))
    assert result.outcome == "CONTINUE"
    assert result.steps[2].equity == 27000 and result.steps[2].financial.floor == 23500
    assert result.steps[3].equity == 24600 and result.steps[3].financial.floor == 23500
    assert result.steps[-1].financial.floor == 24000
    assert result.steps[-1].financial.trading_days == 1


@pytest.mark.parametrize(
    "delta,failed",
    [(timedelta(microseconds=-1), False), (timedelta(0), True), (timedelta(microseconds=1), True)],
)
def test_flat_deadline_boundary(delta, failed):
    mark = event("MARK", hour=15, minute=50, position_id="p", price=D(100)).model_copy(
        update={"at": at(hour=15, minute=50) + delta}
    )
    result = simulate_evaluation(tape([*tape().events, mark]))
    assert (result.outcome == "FAIL") == failed
    assert ("outside_regular_evaluation_hours" in result.steps[-1].breaches) == failed


def test_working_order_match_clear_and_deadline():
    order = event(
        "WORKING_ORDER",
        hour=11,
        minute=10,
        order_id="o",
        instrument_id="MES",
        contract="MESZ26",
        side="BUY",
        quantity=1,
    )
    events = [
        tape().events[0],
        order,
        opening(order_id="o"),
        event("CLOSE", hour=14, position_id="p", price=D(100), commission_usd=D(1)),
        event("SESSION_END", hour=16),
    ]
    assert simulate_evaluation(tape(events)).steps[2].working_order_ids == ()
    cleared = event("CLEAR_ORDER", hour=12, order_id="o")
    assert simulate_evaluation(tape([events[0], order, cleared])).steps[-1].working_order_ids == ()
    late = event("CLEAR_ORDER", hour=15, minute=50, order_id="o")
    assert simulate_evaluation(tape([events[0], order, late])).outcome == "FAIL"


def test_new_session_requires_settlement_and_floor_sync():
    result = simulate_evaluation(
        tape([*tape().events, event("MARK", day=7, position_id="p", price=D(100))])
    )
    assert len(result.steps) == 2 and result.outcome == "CENSORED"
    assert "missing_session_finalization" in result.steps[-1].unknowns
    result = simulate_evaluation(tape([opening()]))
    assert "floor_not_synchronized_before_entry" in result.steps[-1].unknowns
    result = simulate_evaluation(
        tape([event("FLOOR_SYNC", hour=11, minimum_balance=D(23501), confirmed=True), opening()])
    )
    assert "floor_synchronization_mismatch" in result.steps[-1].unknowns


@pytest.mark.parametrize(
    "change", ["step", "hash", "code", "shared", "outcome", "permission", "verified"]
)
def test_saved_tape_replay_rejects_corruption(change):
    result = simulate_evaluation(complete_tape())
    data = result.model_dump()
    if change == "step":
        data["steps"][1]["cash_balance"] += 1
    elif change in {"hash", "code"}:
        data["tape_sha256" if change == "hash" else "implementation_sha256"] = "0" * 64
    elif change == "shared":
        data["shared_source_sha256"] = {}
    elif change == "outcome":
        data["outcome"] = "CONTINUE"
    else:
        data["trade_permitted" if change == "permission" else "rule_exact_verified"] = True
    with pytest.raises(ValidationError):
        EvaluationSimulation.model_validate(data)


@given(st.integers(-1499, 5000), st.integers(0, 1000), st.booleans())
def test_shared_projection_independent_money_oracle(net, extra_loss, closed):
    rules = tcp25_rules()
    prior = initial_eod_state(rules)
    low = min(0, net) - extra_loss
    value = project_eod_session(
        rules, prior, net_pnl=D(net), lowest_pnl=D(low), traded=True, closed=closed
    )
    assert value.financial.balance == 25000 + net
    assert value.financial.floor == (
        min(25000, max(25000, 25000 + net) - 1500) if closed else 23500
    )
    assert value.daily_loss_breached == (low <= -550)
    assert value.drawdown_breached == (25000 + low <= 23500)
    assert value.consistency_met == (net > 0 and max(0, net) * 100 < net * 30)


@pytest.mark.parametrize(
    "offset,consistent", [(D("-1e-20"), False), (D(0), False), (D("1e-20"), True)]
)
def test_consistency_strict_boundary(offset, consistent):
    rules = tcp25_rules()
    prior = initial_eod_state(rules).model_copy(
        update={
            "balance": D(26700),
            "peak": D(26700),
            "floor": D(25000),
            "best_day": D(600),
            "trading_days": 3,
        }
    )
    result = project_eod_session(
        rules, prior, net_pnl=D(300) + offset, lowest_pnl=D(0), traded=True, closed=True
    )
    assert result.consistency_met == consistent
    assert result.targets_met == consistent


def test_numeric_context_and_dst():
    source = complete_tape()
    normal = simulate_evaluation(source)
    with localcontext() as context:
        context.prec = 7
        assert simulate_evaluation(source) == normal
        assert initial_eod_state(source.rules).floor == D(23500)
    assert session_clock(datetime(2026, 11, 2, 22, tzinfo=UTC))["session_date"] == "2026-11-02"
    assert session_clock(datetime(2026, 11, 2, 23, tzinfo=UTC))["session_date"] == "2026-11-03"


@pytest.mark.parametrize(
    "case",
    [
        "missing-position",
        "missing-order",
        "reuse-position",
        "reuse-order",
        "mismatch",
        "off-tick",
        "double-end",
        "early-end",
    ],
)
def test_malformed_observations_rejected(case):
    order = event(
        "WORKING_ORDER",
        hour=11,
        minute=10,
        order_id="o",
        instrument_id="MES",
        contract="MESZ26",
        side="BUY",
        quantity=1,
    )
    base = [tape().events[0], opening()]
    events = {
        "missing-position": [event("MARK", position_id="missing", price=D(100))],
        "missing-order": [event("CLEAR_ORDER", order_id="missing")],
        "reuse-position": [*base, opening(hour=13)],
        "reuse-order": [
            base[0],
            order,
            order.model_copy(update={"id": "other", "at": at(hour=13)}),
        ],
        "mismatch": [base[0], order, opening(order_id="o", quantity=2)],
        "off-tick": [opening(price=D("100.01"))],
        "double-end": [event("SESSION_END", hour=16), event("SESSION_END", hour=16, minute=1)],
        "early-end": [event("SESSION_END", hour=15)],
    }[case]
    with pytest.raises(ValueError):
        simulate_evaluation(tape(events))


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", True),
        ("commission_usd", D(-1)),
        ("contract", "MES"),
        ("contract", "FAKEZ26"),
        ("at", datetime(2026, 10, 6)),
        ("order_id", " "),
    ],
)
def test_strict_observation_shape(field, value):
    with pytest.raises(ValidationError):
        opening(**{field: value})


def test_extra_fields_duplicate_and_reversed_tape_rejected():
    with pytest.raises(ValidationError):
        event("SESSION_END", hour=16, price=D(100))
    source = tape()
    for events in [(source.events[0], source.events[0]), tuple(reversed(source.events))]:
        with pytest.raises(ValidationError):
            tape(events)
    with pytest.raises(ValidationError):
        tape(margin=(source.margin[0], source.margin[0]))


def test_aggregate_micro_plus_standard_exposure_and_hard_ceiling():
    # Different roots still share the same aggregate ladder, with no netting.
    source = tape()
    progression = source.progression.model_copy(
        update={"bands": (ProgressionBand(minimum_equity=D(23500), maximum_standard_contracts=3),)}
    )
    events = [
        source.events[0],
        opening(quantity=10, commission_usd=D(0)),
        opening(
            hour=13,
            position_id="q",
            instrument_id="NQ",
            contract="NQZ26",
            quantity=2,
            side="SELL",
            commission_usd=D(0),
        ),
    ]
    result = simulate_evaluation(tape(events, progression=progression))
    assert result.outcome == "CONTINUE" and result.steps[-1].standard_equivalents == 3
    events.append(
        opening(
            hour=14, position_id="r", instrument_id="MYM", contract="MYMZ26", commission_usd=D(0)
        )
    )
    result = simulate_evaluation(tape(events, progression=progression))
    assert result.outcome == "FAIL"
    assert "maximum_position_size" in result.steps[-1].breaches
    assert "progression_ladder_size" in result.steps[-1].breaches


def test_eod_floor_then_next_day_loss_and_daily_reset():
    rules = tcp25_rules().model_copy(
        update={"daily_loss_limit": D(5000), "version": "synthetic-wide"}
    )
    events = [
        event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=True),
        opening(commission_usd=D(0)),
        event("CLOSE", hour=14, position_id="p", price=D(200), commission_usd=D(0)),
        event("SESSION_END", hour=16),
        event("FLOOR_SYNC", hour=16, minute=10, minimum_balance=D(24000), confirmed=True),
        opening(day=7, position_id="q", commission_usd=D(0)),
        event("MARK", day=7, hour=14, position_id="q", price=D(0.25)),
    ]
    # -498.75 on day two; settled floor remains 24000, no cumulative daily loss.
    result = simulate_evaluation(tape(events, rules=rules))
    assert result.steps[-1].session_net_pnl == D("-498.75")
    assert result.steps[-1].financial.floor == 24000
    assert result.steps[-1].financial.trading_days == 2
    events[-1] = event("MARK", day=7, hour=14, position_id="q", price=D(100))
    events.append(
        event("CLOSE", day=7, hour=15, position_id="q", price=D(100), commission_usd=D(1500))
    )
    result = simulate_evaluation(tape(events, rules=rules))
    assert result.outcome == "FAIL" and "drawdown_boundary" in result.steps[-1].breaches


def test_session_end_requires_flat_and_eligible_root():
    result = simulate_evaluation(tape([*tape().events, event("SESSION_END", hour=16)]))
    assert result.outcome == "FAIL" and "nonflat_session_finalization" in result.steps[-1].breaches
    rules = tcp25_rules().model_copy(
        update={"eligible_markets": ("NQ",), "micro_markets": (), "version": "synthetic-NQ-only"}
    )
    result = simulate_evaluation(tape(rules=rules))
    assert "ineligible_market" in result.steps[-1].breaches


def test_future_policy_and_no_trade_session_and_sync_failure():
    source = tape()
    rules = source.rules.model_copy(update={"known_at": at(hour=14)})
    assert "unknown_policy_at_event" in simulate_evaluation(tape(rules=rules)).steps[-1].unknowns
    result = simulate_evaluation(tape([source.events[0], event("SESSION_END", hour=16)]))
    assert result.steps[-1].financial.trading_days == 0
    assert result.steps[-1].financial.balance == 25000
    result = simulate_evaluation(
        tape([event("FLOOR_SYNC", hour=11, minimum_balance=D(23500), confirmed=False), opening()])
    )
    assert result.outcome == "CENSORED"


def test_calendar_root_exposure_does_not_false_fail_new_root():
    source = tape()
    # MES is exposed, NQ has a legitimate later opening. At 13 CT both can trade.
    calendar = source.calendar.model_copy(
        update={
            "windows": tuple(
                (
                    w.model_copy(update={"start": at(hour=13)})
                    if w.instrument_id == "NQ" and w.start == at(hour=8)
                    else w
                )
                for w in source.calendar.windows
            )
        }
    )
    events = [
        source.events[0],
        opening(commission_usd=D(0)),
        opening(
            hour=13,
            position_id="q",
            instrument_id="NQ",
            contract="NQZ26",
            quantity=1,
            commission_usd=D(0),
        ),
    ]
    progression = source.progression.model_copy(
        update={"bands": (ProgressionBand(minimum_equity=D(23500), maximum_standard_contracts=3),)}
    )
    result = simulate_evaluation(tape(events, calendar=calendar, progression=progression))
    assert result.outcome == "CONTINUE"


@pytest.mark.parametrize(
    "net,low,traded",
    [
        (float("inf"), D(0), True),
        (D("NaN"), D(0), True),
        (D(0), D("NaN"), True),
        (D(0), 0.0, True),
        (D(-1), D(0), True),
        (D(1), D(0), False),
        (D(0), D(-1), False),
    ],
)
def test_pure_arithmetic_rejects_incomplete_extrema(net, low, traded):
    rules = tcp25_rules()
    with pytest.raises(ValueError):
        project_eod_session(
            rules,
            initial_eod_state(rules),
            net_pnl=net,
            lowest_pnl=low,
            traded=traded,
            closed=False,
        )


def test_unknown_catalog_event_and_margin_and_missing_open_order():
    with pytest.raises(ValidationError):
        opening(instrument_id="FAKE", contract="FAKEZ26")
    with pytest.raises(ValidationError):
        MarginCapacity(
            id="x",
            instrument_id="FAKE",
            known_at=at(),
            confirmed=True,
            maximum_total_contracts=1,
            source_reference="synthetic",
        )
    with pytest.raises(ValueError, match="working order"):
        simulate_evaluation(tape([tape().events[0], opening(order_id="missing")]))


def test_consistency_can_delay_profit_target_without_failure():
    events = [
        tape().events[0],
        opening(commission_usd=D(0)),
        event("CLOSE", hour=14, position_id="p", price=D(500), commission_usd=D(0)),
        event("SESSION_END", hour=16),
        event("FLOOR_SYNC", hour=16, minute=10, minimum_balance=D(25000), confirmed=True),
    ]
    result = simulate_evaluation(tape(events))
    assert result.outcome == "CONTINUE" and result.steps[-1].cash_balance == 27000
    assert not result.steps[-1].consistency_met and not result.steps[-1].targets_met
