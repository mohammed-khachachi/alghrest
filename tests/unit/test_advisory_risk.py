"""Independent arithmetic and adversarial joins for synthetic structural risk checks."""

from datetime import timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from core.advisory.account import AccountObservation, OpenPosition, WorkingOrder
from core.advisory.models import CATALOG, EconomicEvent
from core.advisory.policy import EODPolicy, tcp25_rules
from core.advisory.risk import (
    PolicyRiskAllowance,
    RiskConfiguration,
    RiskDecision,
    RiskInputs,
    RiskRequest,
    StrategyRiskHistory,
    StructuralSetup,
    assess_risk,
)
from tests.unit.test_evaluation_policy import (
    TradingWindow,
    calendar,
    controls,
    evidence,
    profile,
    progression,
    session,
)
from tests.unit.test_market_selection import NOW, policy as selection_policy, select

pytestmark = pytest.mark.unit
REVISION = "b" * 64


def setup(root="MNQ", **changes):
    tick = CATALOG[root].tick_size
    return StructuralSetup.model_validate(
        dict(
            id="synthetic-setup",
            version="v1",
            known_at=NOW,
            instrument_id=root,
            contract=root + "Z26",
            side="BUY",
            entry=Decimal(180) + tick,
            invalidation=Decimal(180) - tick * 8,
            structure="SYNTHETIC structural low; no live signal",
            source_kind="manual",
            source_reference="SYNTHETIC replay",
            strategy_id="synthetic-strategy",
            strategy_version="fixture-v1",
        )
        | changes
    )


def config(**changes):
    return RiskConfiguration.model_validate(
        dict(
            id="synthetic-risk-v1",
            version="v1",
            source_reference="SYNTHETIC explicit risk parameters",
            risk_percent=".5",
            safety_buffer_usd=10,
            round_trip_fees_per_contract_usd=2,
            slippage_ticks=2,
            cost_model_version="synthetic-costs-v1",
            max_entry_deviation_ticks=2,
            max_account_age_seconds=10,
            max_setup_age_seconds=10,
            max_selection_age_seconds=10,
            max_risk_evidence_age_seconds=10,
            max_consecutive_losses=5,
            max_drawdown_fraction=".25",
        )
        | changes
    )


def observation(**changes):
    return AccountObservation.model_validate(
        dict(
            account_id="B",
            source="replay",
            source_reference="SYNTHETIC net account observation",
            observed_at=NOW,
            human_confirmed=True,
            costs_included=True,
            currency="USD",
            cash_balance=10000,
            unrealized_pnl=0,
            equity=10000,
            positions=(),
            working_orders=(),
        )
        | changes
    )


def history(**changes):
    return StrategyRiskHistory.model_validate(
        dict(
            account_id="B",
            account_revision=REVISION,
            known_at=NOW,
            source_reference="SYNTHETIC loss sequence and peak",
            strategy_id="synthetic-strategy",
            strategy_version="fixture-v1",
            consecutive_losses=0,
            peak_equity_usd=10000,
        )
        | changes
    )


def allowance(root="MNQ", **changes):
    s = setup(root)
    return PolicyRiskAllowance.model_validate(
        dict(
            account_id="B",
            account_revision=REVISION,
            known_at=NOW,
            source_reference="SYNTHETIC policy output, not TCP25 rules",
            policy_id="synthetic-evaluation",
            policy_version="fixture-v1",
            instrument_id=root,
            contract=s.contract,
            at_invalidation=s.invalidation,
            state="READY",
            reasons=(),
            daily_loss_remaining_usd=100,
            drawdown_remaining_usd=200,
            maximum_contracts=10,
        )
        | changes
    )


def inputs(root="MNQ", **changes):
    return RiskInputs.model_validate(
        dict(
            id="synthetic-risk-inputs",
            version="v1",
            known_at=NOW,
            source_reference="SYNTHETIC reader revision",
            halted=False,
            configuration=config(),
            history=history(),
            allowance=allowance(root),
        )
        | changes
    )


def policy_context(root="MNQ", equity=Decimal(10000), revision=REVISION, **terms):
    """Explicit non-TCP50 synthetic context for existing arithmetic fixtures."""
    rules = tcp25_rules().model_copy(
        update=dict(
            id="synthetic-evaluation",
            version="fixture-v1",
            known_at=NOW,
            program="gauntlet_mini",
            starting_balance=equity,
            profit_target=Decimal(500),
            daily_loss_limit=Decimal(100),
            maximum_drawdown=Decimal(200),
        )
        | terms
    )
    p = profile(
        program=rules.program,
        starting_balance=rules.starting_balance,
        profit_target=rules.profit_target,
        daily_loss_limit=rules.daily_loss_limit,
        maximum_drawdown=rules.maximum_drawdown,
        minimum_trading_days=rules.minimum_trading_days,
        verified_on=NOW.date(),
    )
    row = session(
        session_date=NOW.date(),
        as_of=NOW,
        account=observation(cash_balance=equity, equity=equity),
    )
    captured = evidence(
        root,
        account_revision=revision,
        known_at=NOW,
        observed_minimum_balance=equity - rules.maximum_drawdown,
        progression=progression(
            policy_id=rules.id,
            policy_version=rules.version,
            known_at=NOW,
            bands=(
                dict(minimum_equity=equity - rules.maximum_drawdown, maximum_standard_contracts=1),
            ),
        ),
        calendar=calendar(
            root,
            known_at=NOW,
            coverage_start=NOW - timedelta(days=1),
            coverage_end=NOW + timedelta(days=1),
            windows=(
                TradingWindow(
                    instrument_id=root,
                    start=NOW - timedelta(hours=1),
                    end=NOW + timedelta(hours=2),
                    flat_by=NOW + timedelta(hours=1),
                ),
            ),
        ),
    )
    engine = EODPolicy(rules, controls())
    return engine, p, row, captured


def decision(root="MNQ", **changes):
    equity = changes.get("journal_equity", Decimal(10000))
    engine, p, row, captured = policy_context(
        root, equity if equity.is_finite() and equity > 200 else Decimal(10000)
    )
    args = (
        dict(
            setup=setup(root),
            selection=select(
                roots=(root,),
                rules=selection_policy(
                    (root,),
                    market_limits=tuple(
                        row.model_copy(update={"max_atr_ticks": Decimal(1000000)})
                        for row in selection_policy((root,)).market_limits
                    ),
                ),
            ),
            observation=observation(),
            account_id="B",
            journal_equity=Decimal(10000),
            journal_revision=REVISION,
            journal_blocks=(),
            inputs=inputs(root),
            now=NOW,
            evaluation_policy=engine.assess(
                p, [row], account_revision=REVISION, evidence=captured, now=NOW
            ),
            strategy_registry_required=False,  # Isolated arithmetic, never approved advice.
        )
        | changes
    )
    return assess_risk(**args)


@pytest.mark.parametrize("root", ["MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG"])
def test_one_structural_sizer_uses_catalog_and_all_limits(root):
    value = decision(root)
    s = setup(root)
    c = config()
    instrument = CATALOG[root]
    loss = (
        abs(s.entry - s.invalidation) * instrument.point_value
        + c.slippage_ticks * instrument.tick_size * instrument.point_value
        + c.round_trip_fees_per_contract_usd
    )
    expected = min(int(Decimal(50) // loss), 10)
    assert value.state == "QUALIFIED" and value.allowed_contracts == expected > 0
    assert value.loss_per_contract_usd == loss and value.risk_budget_usd == 50
    assert value.estimated_loss_at_stop_usd == expected * loss <= 50
    assert (
        value.advice == "WAIT"
        and value.risk_qualified
        and not value.trade_permitted
        and not value.execution_enabled
    )
    assert (
        value.setup.invalidation == s.invalidation
        and value.stop_distance == 9 * instrument.tick_size
    )


def test_short_structure_uses_bid_and_never_moves_the_invalidation():
    s = setup(side="SELL", entry="179.75", invalidation="182")
    v = decision(setup=s, inputs=inputs(allowance=allowance(at_invalidation=s.invalidation)))
    assert v.state == "QUALIFIED" and v.allowed_contracts == 6 and v.setup == s


def test_an_allowance_without_account_policy_semantics_cannot_qualify():
    value = decision(evaluation_policy=None)
    assert value.state == "UNKNOWN" and value.allowed_contracts == 0
    assert "missing_evaluation_policy_assessment" in value.reasons


@pytest.mark.parametrize("renamed", [False, True])
def test_direct_risk_cannot_use_confirmed_hypothetical_tcp50_progression(renamed):
    engine, p, row, captured = policy_context(
        equity=Decimal(50000),
        program="trader_career_path",
        profit_target=Decimal(3000),
        daily_loss_limit=Decimal(1100),
        maximum_drawdown=Decimal(2000),
        id="renamed" if renamed else "synthetic-evaluation",
    )
    policy = engine.assess(p, [row], account_revision=REVISION, evidence=captured, now=NOW)
    selected = select(
        roots=("MNQ",),
        rules=selection_policy(
            ("MNQ",),
            evaluation_policy_id=engine.rules.id,
        ),
    )
    result = decision(
        selection=selected,
        observation=row.account,
        journal_equity=Decimal(50000),
        evaluation_policy=policy,
        inputs=inputs(
            history=history(peak_equity_usd=50000),
            allowance=allowance(policy_id=engine.rules.id),
        ),
    )
    assert result.state in {"UNKNOWN", "BLOCKED"} and result.allowed_contracts == 0
    assert "evaluation_policy_unknown" in result.reasons
    forged = policy.model_copy(update={"state": "READY", "reasons": ()})
    with pytest.raises(ValueError, match="TCP50 progression"):
        decision(evaluation_policy=forged)
    assert not result.execution_enabled and not result.trade_permitted


@pytest.mark.parametrize("fault", ["missing", "tcp50", "renamed_tcp50", "false_flag"])
def test_serialized_and_saved_positive_risk_cannot_bypass_policy_gate(tmp_path, fault):
    from connectors.advisory.storage import AdvisoryStore
    from core.advisory.risk import verify_qualified_record

    positive = decision()
    changed = positive.model_copy(update={"evaluation_policy": None})
    if fault in {"tcp50", "renamed_tcp50"}:
        engine, p, row, captured = policy_context(
            equity=Decimal(50000),
            program="trader_career_path",
            profit_target=Decimal(3000),
            daily_loss_limit=Decimal(1100),
            maximum_drawdown=Decimal(2000),
            id="renamed" if fault.startswith("renamed") else "synthetic-evaluation",
        )
        policy = engine.assess(p, [row], account_revision=REVISION, evidence=captured, now=NOW)
        changed = positive.model_copy(
            update={
                "evaluation_policy": policy.model_copy(update={"state": "READY", "reasons": ()})
            }
        )
    elif fault == "false_flag":
        changed = positive.model_copy(update={"risk_qualified": False})
    with pytest.raises(ValueError):
        RiskDecision.model_validate_json(changed.model_dump_json())
    with pytest.raises(ValueError, match="does not reproduce"):
        verify_qualified_record(changed)
    store = AdvisoryStore(str(tmp_path / "gate.sqlite3"))
    with pytest.raises(ValueError):
        store.save_risk_decision(changed)
    store.save_risk_decision(positive)
    with store.connect() as db:
        db.execute(
            "UPDATE risk_decisions SET payload=? WHERE id=?",
            (changed.model_dump_json(), positive.id),
        )
    with pytest.raises(ValueError):
        store.risk_decision(positive.id)


@pytest.mark.parametrize("fault", ["balance", "revision", "policy", "clock"])
def test_detached_ready_policy_must_join_the_positive_risk_record(fault):
    value = decision()
    if fault == "balance":
        engine, p, row, captured = policy_context(equity=Decimal(11000))
    elif fault == "revision":
        engine, p, row, captured = policy_context(revision="a" * 64)
    elif fault == "policy":
        engine, p, row, captured = policy_context(id="different-policy")
    else:
        engine, p, row, captured = policy_context()
    policy = engine.assess(
        p, [row], account_revision=captured.account_revision, evidence=captured, now=NOW
    )
    if fault == "clock":
        policy = engine.assess(
            p, [row], account_revision=REVISION, evidence=captured, now=NOW + timedelta(seconds=1)
        )
    with pytest.raises(ValueError):
        RiskDecision.model_validate(
            value.model_copy(update={"evaluation_policy": policy}).model_dump()
        )


def test_tcp25_risk_keeps_the_same_structural_costs_and_budgets():
    engine, p, row, captured = policy_context(
        equity=Decimal(25000),
        program="trader_career_path",
        profit_target=Decimal(1750),
        daily_loss_limit=Decimal(550),
        maximum_drawdown=Decimal(1500),
    )
    assessed = engine.assess(p, [row], account_revision=REVISION, evidence=captured, now=NOW)
    allowed = engine.allowance(
        assessed,
        instrument_id="MNQ",
        contract="MNQZ26",
        invalidation=setup().invalidation,
        loss_per_contract=Decimal("7.5"),
    )
    result = decision(
        observation=row.account,
        journal_equity=Decimal(25000),
        evaluation_policy=assessed,
        inputs=inputs(history=history(peak_equity_usd=25000), allowance=allowed),
    )
    assert result.state == "QUALIFIED" and result.allowed_contracts == 10
    assert result.loss_per_contract_usd == Decimal("7.5")
    assert result.percentage_budget_usd == result.risk_budget_usd == 125
    assert result.estimated_loss_at_stop_usd == Decimal(75)


@pytest.mark.parametrize(
    "part",
    [
        "all",
        "configuration",
        "history",
        "allowance",
        "halt",
        "account",
        "selection",
        "positions",
        "orders",
    ],
)
def test_missing_evidence_never_becomes_flat_zero_risk_or_positive_size(part):
    changes = {}
    if part == "all":
        changes["inputs"] = None
    elif part in {"configuration", "history", "allowance"}:
        changes["inputs"] = inputs(**{part: None})
    elif part == "halt":
        changes["inputs"] = inputs(halted=None)
    elif part == "account":
        changes["observation"] = None
    elif part == "selection":
        changes["selection"] = None
    else:
        changes["observation"] = observation(
            **{"positions" if part == "positions" else "working_orders": None}
        )
    value = decision(**changes)
    assert value.state == "UNKNOWN" and value.allowed_contracts == 0 and value.advice == "NO TRADE"
    assert value.risk_budget_usd is None and value.loss_per_contract_usd is None


@pytest.mark.parametrize(
    "fault",
    [
        "halt",
        "history-account",
        "history-revision",
        "history-strategy",
        "peak",
        "losses",
        "allowance-account",
        "allowance-revision",
        "allowance-root",
        "allowance-stop",
        "policy",
        "policy-unknown",
        "policy-blocked",
        "risk-percent",
        "costs",
        "slippage",
        "entry",
        "stop",
        "tick",
        "contract",
        "strategy",
        "unknown-root",
    ],
)
def test_identity_and_source_faults_block_risk(fault):
    s = setup()
    i = inputs()
    obs = observation()
    if fault == "halt":
        i = inputs(halted=True)
    elif fault.startswith("history-"):
        field = {
            "account": "account_id",
            "revision": "account_revision",
            "strategy": "strategy_version",
        }[fault.split("-")[1]]
        i = inputs(history=history(**{field: "a" * 64 if field == "account_revision" else "A"}))
    elif fault == "peak":
        i = inputs(history=history(peak_equity_usd=9999))
    elif fault == "losses":
        i = inputs(history=history(consecutive_losses=5))
    elif fault.startswith("allowance-"):
        field = {
            "account": "account_id",
            "revision": "account_revision",
            "root": "instrument_id",
            "stop": "at_invalidation",
        }[fault.split("-")[1]]
        a = (
            allowance("MES")
            if field == "instrument_id"
            else allowance(
                **{
                    field: (
                        179
                        if field == "at_invalidation"
                        else "a" * 64 if field == "account_revision" else "A"
                    )
                }
            )
        )
        i = inputs(allowance=a)
    elif fault == "policy":
        i = inputs(allowance=allowance(policy_version="other"))
    elif fault.startswith("policy-"):
        i = inputs(
            allowance=allowance(state=fault.split("-")[1].upper(), reasons=("synthetic-fault",))
        )
    elif fault == "risk-percent":
        i = inputs(configuration=config(risk_percent="1"))
    elif fault == "costs":
        i = inputs(configuration=config(cost_model_version="other"))
    elif fault == "slippage":
        i = inputs(configuration=config(slippage_ticks=1))
    elif fault == "entry":
        s = setup(entry=182)
    elif fault == "stop":
        s = setup(invalidation=181)
    elif fault == "tick":
        s = setup(invalidation="178.01")
    elif fault == "contract":
        s = setup(contract="MNQH27")
    elif fault == "strategy":
        s = setup(strategy_version="other")
    else:
        obs = observation(
            working_orders=(
                WorkingOrder(
                    order_id="unknown",
                    instrument_id="MISSING",
                    contract="MISSING",
                    side="BUY",
                    contracts=1,
                ),
            )
        )
    result = decision(setup=s, inputs=i, observation=obs)
    assert (
        result.state in {"BLOCKED", "UNKNOWN"} and result.allowed_contracts == 0 and result.reasons
    )


@pytest.mark.parametrize("kind", ["position", "order"])
@pytest.mark.parametrize("side", ["BUY", "SELL"])
def test_correlated_index_exposure_is_not_netted_or_ignored(kind, side):
    if kind == "position":
        exposure = OpenPosition(
            position_id="p",
            instrument_id="MES",
            contract="MESZ26",
            side=side,
            contracts=1,
            unrealized_pnl=0,
        )
        obs = observation(positions=(exposure,))
    else:
        exposure = WorkingOrder(
            order_id="o", instrument_id="MYM", contract="MYMZ26", side=side, contracts=1
        )
        obs = observation(working_orders=(exposure,))
    result = decision(observation=obs)
    assert result.state == "BLOCKED" and result.allowed_contracts == 0
    assert result.correlated_exposure_ids == (kind + ":" + ("p" if kind == "position" else "o"),)


def test_other_market_exposure_and_corrupt_contract_never_count_as_independence():
    holding = OpenPosition(
        position_id="gold",
        instrument_id="MGC",
        contract="MGCZ26",
        side="BUY",
        contracts=1,
        unrealized_pnl=0,
    )
    value = decision(observation=observation(positions=(holding,)))
    assert value.state == "UNKNOWN" and value.reasons == ("unquantified_open_exposure",)
    holding = holding.model_copy(update={"contract": "MGCX26"})
    assert (
        "unknown_open_exposure" in decision(observation=observation(positions=(holding,))).reasons
    )


@pytest.mark.parametrize("limit", ["daily_loss_remaining_usd", "drawdown_remaining_usd"])
@pytest.mark.parametrize("epsilon", [Decimal("-.000001"), Decimal(0), Decimal(".000001")])
def test_one_contract_budget_boundary_does_not_shrink_the_stop(limit, epsilon):
    # MNQ loss: 2.25*2 + 2 ticks*.25*2 + $2 fees = $7.50.
    result = decision(inputs=inputs(allowance=allowance(**{limit: Decimal("17.5") + epsilon})))
    assert result.allowed_contracts == (0 if epsilon < 0 else 1)
    assert result.setup.invalidation == 178 and result.stop_distance == Decimal("2.25")
    assert result.risk_budget_usd == Decimal("7.5") + epsilon


@pytest.mark.parametrize("count", [0, 1, 4, 5, 6])
def test_five_consecutive_losses_are_a_hard_pause(count):
    result = decision(inputs=inputs(history=history(consecutive_losses=count)))
    assert (result.state == "QUALIFIED") is (count < 5)


@pytest.mark.parametrize("epsilon", [Decimal("-.000001"), Decimal(0), Decimal(".000001")])
def test_twenty_five_percent_drawdown_boundary_uses_account_peak(epsilon):
    equity = Decimal(7500) + epsilon
    obs = observation(cash_balance=equity, equity=equity)
    result = decision(observation=obs, journal_equity=equity)
    assert (result.state == "QUALIFIED") is (epsilon > 0)
    if epsilon <= 0:
        assert "portfolio_drawdown_limit" in result.reasons


@pytest.mark.parametrize("quantity", [0, 1, 2, 10])
def test_policy_contract_cap_cannot_be_exceeded(quantity):
    value = decision(inputs=inputs(allowance=allowance(maximum_contracts=quantity)))
    assert value.allowed_contracts == min(quantity, 6)
    assert value.risk_qualified is (quantity > 0)


@pytest.mark.parametrize(
    "field", ["risk_percent", "max_drawdown_fraction", "max_consecutive_losses"]
)
def test_risk_configuration_cannot_weaken_the_hard_rails(field):
    with pytest.raises(ValueError):
        config(
            **{
                field: {
                    "risk_percent": "1.000001",
                    "max_drawdown_fraction": ".250001",
                    "max_consecutive_losses": 6,
                }[field]
            }
        )


def test_ai_proposal_cannot_add_budget_quantity_or_move_source_configuration():
    s = setup(source_kind="ai_proposal")
    for field in ("risk_percent", "risk_budget", "contracts", "account_value"):
        with pytest.raises(ValueError):
            StructuralSetup.model_validate(s.model_dump() | {field: 100000})
        with pytest.raises(ValueError):
            RiskRequest.model_validate({"setup": s.model_dump(), field: 100000})
    proposed = decision(setup=s)
    human = decision()
    assert proposed.allowed_contracts == human.allowed_contracts == 6
    bad = inputs().model_copy(
        update={"configuration": config().model_copy(update={"risk_percent": Decimal(100)})}
    )
    assert decision(inputs=bad).allowed_contracts == 0


def test_saved_data_health_and_event_labels_are_recomputed_not_trusted():
    selected = select(roots=("MNQ",))
    market = selected.assessments[0].market
    market.quality = market.quality.model_copy(update={"provider_state": "degraded"})
    result = decision(selection=selected)
    assert result.state == "BLOCKED" and result.allowed_contracts == 0
    selected = select(roots=("MNQ",))
    row = selected.assessments[0]
    event = EconomicEvent(
        id="event",
        name="Synthetic event",
        known_at=NOW,
        scheduled_at=NOW,
        source="https://example.com/event",
        affected_markets=("MNQ",),
        impact="high",
    )
    calendar = row.event_risk.calendar.model_copy(update={"events": (event,)})
    row = row.model_copy(
        update={"event_risk": row.event_risk.model_copy(update={"calendar": calendar})}
    )
    selected = selected.model_copy(update={"assessments": (row,)})
    assert decision(selection=selected).allowed_contracts == 0


def test_selection_and_source_age_epsilon_boundaries():
    for epsilon in (timedelta(microseconds=-1), timedelta(0), timedelta(microseconds=1)):
        value = decision(now=NOW + timedelta(seconds=10) + epsilon)
        assert (value.state == "QUALIFIED") is (epsilon <= timedelta(0))
    value = decision(now=NOW - timedelta(microseconds=1))
    assert value.allowed_contracts == 0 and "stale_or_future_setup" in value.reasons


@settings(max_examples=100, derandomize=True, database=None)
@given(
    root=st.sampled_from(["MES", "MYM", "MNQ", "MGC"]),
    ticks=st.integers(min_value=1, max_value=170),
    daily=st.decimals(
        min_value="10", max_value="200", places=4, allow_nan=False, allow_infinity=False
    ),
    cap=st.integers(min_value=0, max_value=100),
)
def test_property_structural_risk_never_exceeds_money_caps_or_changes_invalidation(
    root, ticks, daily, cap
):
    s = setup(root)
    s = s.model_copy(update={"invalidation": s.entry - CATALOG[root].tick_size * ticks})
    i = inputs(
        root,
        allowance=allowance(
            root,
            at_invalidation=s.invalidation,
            daily_loss_remaining_usd=daily,
            maximum_contracts=cap,
        ),
    )
    v = decision(root, setup=s, inputs=i)
    assert v.setup.invalidation == s.invalidation
    loss = CATALOG[root].point_value * CATALOG[root].tick_size * (ticks + 2) + 2
    expected = min(int(max(Decimal(0), min(Decimal(50), daily - 10)) // loss), cap)
    assert v.allowed_contracts == expected
    assert v.risk_qualified is (expected > 0)
    if expected:
        assert v.estimated_loss_at_stop_usd == loss * expected <= v.risk_budget_usd <= Decimal(50)
    else:
        assert v.advice == "NO TRADE"


@pytest.mark.parametrize(
    "changes",
    [
        {"loss_per_contract_usd": Decimal(".01")},
        {"risk_budget_usd": Decimal(49)},
        {"selection": None},
    ],
)
def test_stored_qualified_decision_rejects_changed_calculation_or_missing_guard(changes):
    v = decision()
    with pytest.raises(ValueError):
        RiskDecision.model_validate(v.model_copy(update=changes).model_dump())


def make_service(tmp_path, **changes):
    from unittest.mock import Mock

    from api.services.advisory import AdvisoryService
    from connectors.advisory.storage import AdvisoryStore
    from core.advisory.evaluation import EvaluationProfile, EvaluationSession

    store = AdvisoryStore(str(tmp_path / "risk.sqlite3"))
    profile = EvaluationProfile(
        id="B",
        program="trader_career_path",
        starting_balance=10000,
        profit_target=500,
        daily_loss_limit=100,
        maximum_drawdown=1000,
        minimum_trading_days=10,
        source="https://example.com/synthetic-profile",
        verified_on=NOW.date(),
    )
    store.create_evaluation(profile)
    row = EvaluationSession(
        session_date=NOW.date(),
        as_of=NOW,
        net_pnl=0,
        lowest_pnl=0,
        closed=False,
        traded=False,
        account=observation(),
    )
    store.save_session("B", row)
    selected = select(roots=("MNQ",))
    store.save_selection(selected)

    def reader(account_id, revision, s, cut):
        return inputs(
            history=history(account_id=account_id, account_revision=revision),
            allowance=allowance(
                account_id=account_id, account_revision=revision, at_invalidation=s.invalidation
            ),
        )

    service = AdvisoryService(
        store,
        Mock(),
        clock=lambda: NOW,
        risk_inputs_reader=reader,
        evaluation_policy=policy_context(
            program="trader_career_path",
            maximum_drawdown=Decimal(1000),
            minimum_trading_days=10,
        )[0],
        policy_evidence_reader=lambda account_id, revision, s, cut: policy_context(
            s.instrument_id,
            revision=revision,
            program="trader_career_path",
            maximum_drawdown=Decimal(1000),
            minimum_trading_days=10,
        )[3],
        account_roles_required=changes.pop("account_roles_required", False),
        strategy_registry_required=changes.pop("strategy_registry_required", False),
        **changes,
    )
    return service, RiskRequest(selection_id=selected.id, setup=setup()), row


async def test_service_reads_durable_account_saves_complete_risk_and_replays(tmp_path):
    service, request, _ = make_service(tmp_path)
    first = await service.risk_decision("B", request)
    assert first.state == "QUALIFIED" and first.allowed_contracts == 6 and service.cache == {}
    from connectors.advisory.storage import AdvisoryStore

    reopened = AdvisoryStore(str(tmp_path / "risk.sqlite3"))
    assert reopened.risk_decision(first.id) == first and reopened.risk_decision("missing") is None
    repeated = await service.risk_decision("B", request)
    left = first.model_dump(exclude={"id"})
    right = repeated.model_dump(exclude={"id"})
    left["selection"].pop("id")
    right["selection"].pop("id")
    for fields in (left, right):
        policy_id = fields["evaluation_policy"].pop("id")
        fields["risk_inputs"]["allowance"]["source_reference"] = fields["risk_inputs"]["allowance"][
            "source_reference"
        ].replace(policy_id, "assessment-id")
    assert left == right
    # One account's observation/allowance cannot authorize another account.
    with pytest.raises(ValueError, match="not found"):
        await service.risk_decision("A", request)


async def test_source_acquisition_journal_update_cannot_use_old_allowances(tmp_path):
    service, request, row = make_service(tmp_path)
    old_reader = service.risk_inputs_reader

    def reader(account_id, revision, s, cut):
        result = old_reader(account_id, revision, s, cut)
        updated = row.model_copy(
            update={
                "net_pnl": Decimal(1),
                "traded": True,
                "account": observation(cash_balance=10001, equity=10001),
            }
        )
        service.store.save_session("B", updated)
        return result

    service.risk_inputs_reader = reader
    value = await service.risk_decision("B", request)
    assert (
        value.state == "BLOCKED"
        and value.journal_equity_usd == 10001
        and value.allowed_contracts == 0
    )
    assert {"strategy_history_identity_mismatch", "evaluation_policy_blocked"} <= set(value.reasons)
    assert "policy_evidence_account_mismatch" in value.evaluation_policy.reasons


async def test_a_policy_reader_cannot_clear_a_durable_historical_breach(tmp_path):
    service, request, row = make_service(tmp_path)
    service.store.save_session(
        "B", row.model_copy(update={"lowest_pnl": Decimal(-100), "traded": True})
    )
    value = await service.risk_decision("B", request)
    assert value.state == "BLOCKED" and value.allowed_contracts == 0
    assert any("journal_constraint:breach:daily_loss:" in reason for reason in value.reasons)
    assert value.risk_inputs.allowance.state == "BLOCKED"


@pytest.mark.parametrize("fault", [None, "exception", "bad-copy"])
async def test_missing_failed_and_invalid_server_inputs_never_qualify(tmp_path, fault):
    service, request, _ = make_service(tmp_path)
    if fault is None:
        service.risk_inputs_reader = None
    elif fault == "exception":
        service.risk_inputs_reader = lambda *args: (_ for _ in ()).throw(
            OSError("synthetic unavailable")
        )
    else:
        service.risk_inputs_reader = lambda *args: inputs().model_copy(update={"halted": "false"})
    value = await service.risk_decision("B", request)
    assert value.state != "QUALIFIED" and value.allowed_contracts == 0 and not value.trade_permitted


async def test_acquisition_latency_rechecks_quote_account_setup_and_policy(tmp_path):
    service, request, _ = make_service(tmp_path)
    clock = iter([NOW, NOW + timedelta(seconds=11)])
    service.clock = lambda: next(clock)
    value = await service.risk_decision("B", request)
    assert value.state == "BLOCKED" and value.allowed_contracts == 0
    assert (
        "stale_or_future_policy_evidence" in value.evaluation_policy.reasons
        and "stale_or_future_setup" in value.reasons
    )


def test_risk_record_retention_and_corrupt_identity_are_bounded(tmp_path):
    from connectors.advisory.storage import AdvisoryStore

    store = AdvisoryStore(str(tmp_path / "records.sqlite3"))
    value = decision()
    for n in range(102):
        store.save_risk_decision(value.model_copy(update={"id": f"{n:03}"}))
    assert store.risk_decision("000") is None and store.risk_decision("001") is None
    assert store.risk_decision("101").allowed_contracts == 6
    with store.connect() as db:
        db.execute("UPDATE risk_decisions SET account='A' WHERE id='101'")
    with pytest.raises(ValueError, match="identity/time/account"):
        store.risk_decision("101")
    with store.connect() as db:
        db.execute("UPDATE risk_decisions SET payload='{}' WHERE id='100'")
    with pytest.raises(ValueError):
        store.risk_decision("100")


@pytest.mark.parametrize(
    "factory,changes",
    [
        (setup, {"instrument_id": "NDX"}),
        (setup, {"contract": "MESZ26"}),
        (allowance, {"contract": "MESZ26"}),
        (allowance, {"maximum_contracts": None}),
        (allowance, {"daily_loss_remaining_usd": None}),
        (allowance, {"state": "UNKNOWN", "reasons": ()}),
        (inputs, {"history": history(known_at=NOW + timedelta(microseconds=1))}),
    ],
)
def test_invalid_structural_and_reported_policy_contracts_are_rejected(factory, changes):
    with pytest.raises(ValueError):
        factory(**changes)


@pytest.mark.parametrize("equity", [Decimal("NaN"), Decimal("Infinity")])
def test_nonfinite_journal_state_cannot_enter_risk_math(equity):
    with pytest.raises(ValueError, match="finite"):
        decision(journal_equity=equity)


def test_nonpositive_and_mismatched_account_equity_block_math():
    for equity in (Decimal(0), Decimal(-1), Decimal(9999)):
        v = decision(journal_equity=equity)
        assert v.state == "BLOCKED" and v.allowed_contracts == 0
    invalid = observation().model_copy(update={"equity": Decimal(9999)})
    assert decision(observation=invalid).state == "BLOCKED"


def test_corrupt_selection_conflicting_event_policies_and_future_record_are_blocked():
    v = select(roots=("MNQ",)).model_copy(update={"primary": "MGC"})
    assert "invalid_market_selection" in decision(selection=v).reasons
    v = select(roots=("MNQ", "MGC"))
    rows = list(v.assessments)
    changed = rows[1].event_risk.policy.model_copy(update={"version": "different"})
    rows[1] = rows[1].model_copy(
        update={"event_risk": rows[1].event_risk.model_copy(update={"policy": changed})}
    )
    assert decision(selection=v.model_copy(update={"assessments": tuple(rows)})).state == "BLOCKED"
    v = select(roots=("MNQ",)).model_copy(update={"generated_at": NOW + timedelta(microseconds=1)})
    assert "stale_or_future_selection" in decision(selection=v).reasons


def test_missing_book_side_is_not_assumed_zero_entry_deviation():
    from tests.unit.test_market_selection import candidate

    c = candidate()
    quote = c.measurement.quote.model_copy(update={"ask": None, "bid": None})
    c = candidate(measurement=c.measurement.model_copy(update={"quote": quote}))
    v = select(roots=("MNQ",), inputs={"MNQ": c})
    result = decision(selection=v)
    assert result.allowed_contracts == 0 and "missing_entry_quote" in result.reasons


@pytest.mark.parametrize(
    "changes",
    [
        {"advice": "NO TRADE"},
        {"risk_qualified": False},
        {"allowed_contracts": 0},
        {"estimated_loss_at_stop_usd": Decimal(46)},
    ],
)
def test_corrupt_qualified_record_cannot_invent_a_different_verdict(changes):
    with pytest.raises(ValueError):
        RiskDecision.model_validate(decision().model_copy(update=changes).model_dump())
    unqualified = decision(inputs=None).model_copy(update={"allowed_contracts": 1})
    with pytest.raises(ValueError):
        RiskDecision.model_validate(unqualified.model_dump())


def test_positive_record_replays_loss_and_market_guards_before_it_is_saved_or_read(tmp_path):
    from connectors.advisory.storage import AdvisoryStore

    store = AdvisoryStore(str(tmp_path / "guarded.sqlite3"))
    v = decision()
    changed = v.model_copy(update={"risk_inputs": inputs(history=history(consecutive_losses=5))})
    with pytest.raises(ValueError, match="does not reproduce"):
        store.save_risk_decision(changed)
    store.save_risk_decision(v)
    payload = v.model_dump(mode="json")
    payload["risk_inputs"]["history"]["consecutive_losses"] = 5
    import json

    with store.connect() as db:
        db.execute("UPDATE risk_decisions SET payload=? WHERE id=?", (json.dumps(payload), v.id))
    with pytest.raises(ValueError, match="does not reproduce"):
        store.risk_decision(v.id)
    blocked = decision(inputs=None)
    store.save_risk_decision(blocked)
    assert store.risk_decision(blocked.id) == blocked


@pytest.mark.parametrize(
    "changes",
    [
        {"schedule_checked": False},
        {"allowed_standard_contracts_at_stop": Decimal(-1)},
        {"safety_buffer": Decimal(-1)},
    ],
)
def test_legacy_planning_revalidates_rule_fields_on_internal_copies(monkeypatch, changes):
    from core.advisory import evaluation as ev
    from tests.unit.test_evaluation import NOW as EVALUATION_NOW, account_session, plan, profile

    monkeypatch.setattr(ev, "utcnow", lambda: EVALUATION_NOW)
    with pytest.raises(ValueError):
        ev.evaluation_plan(
            plan().model_copy(update=changes), profile(), [account_session(-500, -500)]
        )


def test_replay_verifier_rejects_lost_source_and_internal_copied_guard():
    from core.advisory.risk import verify_qualified_record

    for field in ("selection", "selection_source"):
        with pytest.raises(ValueError, match="does not reproduce"):
            verify_qualified_record(decision().model_copy(update={field: None}))


def test_replay_market_evidence_cannot_size_a_current_account_observation():
    v = decision(observation=observation(source="manual_report"))
    assert v.state == "BLOCKED" and v.allowed_contracts == 0
    assert "replay_current_account_mismatch" in v.reasons
