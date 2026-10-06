"""Synthetic account tables test the port; they are not official progression bands."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from core.advisory import evaluation as ev
from core.advisory.account import AccountObservation
from core.advisory.policy import (
    EODPolicy,
    EvaluationEvidence,
    PolicyAssessment,
    PolicyControls,
    ProgressionBand,
    ProgressionSchedule,
    TCP25Policy,
    TradingCalendar,
    TradingWindow,
    tcp25_rules,
)
from core.advisory.risk import RiskInputs, RiskRequest

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 6, 15, tzinfo=UTC)
REVISION = "c" * 64


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)


def controls(**changes):
    return PolicyControls.model_validate(
        dict(
            id="synthetic-controls",
            version="v1",
            source_reference="SYNTHETIC explicit source ages",
            max_evidence_age_seconds=10,
            max_review_age_days=30,
        )
        | changes
    )


def profile(**changes):
    return ev.EvaluationProfile.model_validate(
        dict(
            id="B",
            program="trader_career_path",
            starting_balance=25000,
            profit_target=1750,
            daily_loss_limit=550,
            maximum_drawdown=1500,
            minimum_trading_days=0,
            verified_on=NOW.date(),
            source="https://example.com/synthetic-account",
        )
        | changes
    )


def session(pnl=0, low=0, **changes):
    equity = Decimal(25000) + Decimal(pnl)
    account = AccountObservation(
        account_id="B",
        source="replay",
        source_reference="SYNTHETIC statement",
        observed_at=NOW,
        human_confirmed=True,
        costs_included=True,
        currency="USD",
        cash_balance=equity,
        unrealized_pnl=Decimal(0),
        equity=equity,
        positions=(),
        working_orders=(),
    )
    return ev.EvaluationSession.model_validate(
        dict(
            session_date=NOW.date(),
            as_of=NOW,
            net_pnl=pnl,
            lowest_pnl=low,
            closed=False,
            traded=bool(pnl or low),
            account=account,
        )
        | changes
    )


def progression(**changes):
    rules = tcp25_rules()
    return ProgressionSchedule.model_validate(
        dict(
            id="synthetic-bands",
            version="fixture-v1",
            policy_id=rules.id,
            policy_version=rules.version,
            known_at=NOW,
            source_reference="SYNTHETIC bands; NOT official account thresholds",
            confirmed=True,
            bands=[
                dict(minimum_equity=23500, maximum_standard_contracts=1),
                dict(minimum_equity=25500, maximum_standard_contracts=2),
                dict(minimum_equity=26500, maximum_standard_contracts=3),
            ],
        )
        | changes
    )


def calendar(root="MNQ", **changes):
    return TradingCalendar.model_validate(
        dict(
            id="synthetic-calendar",
            version="fixture-v1",
            known_at=NOW,
            source_reference="SYNTHETIC exchange windows",
            confirmed=True,
            complete=True,
            coverage_start=NOW - timedelta(days=1),
            coverage_end=NOW + timedelta(days=1),
            covered_markets=(root,),
            windows=(
                TradingWindow(
                    instrument_id=root,
                    start=NOW - timedelta(hours=1),
                    end=NOW + timedelta(hours=10),
                    flat_by=NOW + timedelta(hours=9),
                ),
            ),
        )
        | changes
    )


def evidence(root="MNQ", **changes):
    return EvaluationEvidence.model_validate(
        dict(
            id="synthetic-policy-inputs",
            version="fixture-v1",
            account_id="B",
            account_revision=REVISION,
            instrument_id=root,
            contract=root + "Z26",
            known_at=NOW,
            source_reference="SYNTHETIC policy inputs",
            origin="synthetic",
            confirmed=True,
            observed_minimum_balance=23500,
            thresholds_in_sync=True,
            margin_contracts_available=30,
            progression=progression(),
            calendar=calendar(root),
        )
        | changes
    )


def assess(**changes):
    args = (
        dict(
            profile=profile(),
            sessions=[session()],
            account_revision=REVISION,
            evidence=evidence(),
            now=NOW,
        )
        | changes
    )
    return TCP25Policy(controls()).assess(**args)


def allowance(value=None, root="MNQ", loss=Decimal(10), **changes):
    return TCP25Policy(controls()).allowance(
        assess(evidence=evidence(root)) if value is None else value,
        instrument_id=root,
        contract=root + "Z26",
        invalidation=Decimal(178),
        loss_per_contract=loss,
        **changes,
    )


def test_official_review_snapshot_is_versioned_and_has_no_day_minimum():
    rules = tcp25_rules()
    assert (
        rules.starting_balance,
        rules.profit_target,
        rules.daily_loss_limit,
        rules.maximum_drawdown,
    ) == (25000, 1750, 550, 1500)
    assert rules.minimum_trading_days == 0 and rules.consistency_percent == 30
    assert (
        rules.maximum_standard_contracts == 3
        and len(rules.micro_markets) == 9
        and rules.micros_per_standard == 10
    )
    assert rules.version == "tcp25-eod-public-2026-10-06" and len(rules.sources) == 7


def test_a_ready_reported_snapshot_uses_shared_journal_arithmetic():
    value = assess()
    assert value.state == "READY" and value.outcome == "CONTINUE"
    assert (
        value.balance == 25000
        and value.minimum_balance == 23500
        and value.daily_loss_remaining == 550
    )
    assert value.flat_by == datetime(2026, 10, 6, 20, 50, tzinfo=UTC)
    result = allowance(value)
    assert result.state == "READY" and result.maximum_contracts == 10
    assert result.policy_id == value.rules.id and result.account_revision == REVISION
    assert not value.trade_permitted and not value.execution_enabled


@pytest.mark.parametrize("epsilon", [Decimal("-.0001"), Decimal(0), Decimal(".0001")])
def test_stop_touching_daily_limit_cannot_fit_one_contract(epsilon):
    value = assess(evidence=evidence(margin_contracts_available=1))
    result = allowance(value, loss=Decimal(550) + epsilon)
    assert result.maximum_contracts == (1 if epsilon < 0 else 0)


def test_corrupted_ready_policy_cannot_issue_allowance():
    value = assess().model_copy(update={"daily_loss_remaining": Decimal(10000)})
    with pytest.raises(ValueError, match="reproduce"):
        allowance(value)


def test_another_policy_assessment_cannot_issue_this_policy_allowance():
    implementation = EODPolicy(tcp25_rules().model_copy(update={"id": "other"}), controls())
    result = implementation.allowance(
        assess(),
        instrument_id="MNQ",
        contract="MNQZ26",
        invalidation=Decimal(178),
        loss_per_contract=Decimal(10),
    )
    assert result.state == "BLOCKED" and result.maximum_contracts is None


@pytest.mark.parametrize("missing", ["all", "progression", "calendar", "margin", "floor", "sync"])
def test_unverified_capacity_or_calendar_is_unknown_and_never_fabricated(missing):
    changes = (
        {"progression": None}
        if missing == "progression"
        else (
            {"calendar": None}
            if missing == "calendar"
            else (
                {"margin_contracts_available": None}
                if missing == "margin"
                else (
                    {"observed_minimum_balance": None}
                    if missing == "floor"
                    else {"thresholds_in_sync": None}
                )
            )
        )
    )
    value = assess(evidence=None if missing == "all" else evidence(**changes))
    assert value.state == "UNKNOWN" and allowance(value).maximum_contracts is None
    assert value.reasons and not value.trade_permitted


@pytest.mark.parametrize("epsilon", [Decimal("-.000001"), Decimal(0), Decimal(".000001")])
def test_daily_loss_boundary_survives_a_profitable_current_balance(epsilon):
    value = assess(sessions=[session(pnl=100, low=Decimal(-550) + epsilon)])
    assert (value.outcome == "FAILED") is (epsilon <= 0)
    assert (value.state == "READY") is (epsilon > 0)


def test_consistency_is_not_a_hard_fail_or_a_fake_day_count_rule():
    value = assess(sessions=[session(pnl=1750)])
    assert value.state == "READY" and not value.consistency_met and value.outcome == "CONTINUE"
    assert not value.recorded_targets_met


@pytest.mark.parametrize(
    "root", ["MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG", "NQ"]
)
def test_micro_equivalence_is_policy_data_for_all_research_markets(root):
    a = allowance(root=root)
    assert a.state == "READY" and a.maximum_contracts == (1 if root == "NQ" else 10)


@pytest.mark.parametrize(
    "equity,expected",
    [
        (Decimal("25600") - Decimal(".000001"), 19),
        (Decimal(25600), 20),
        (Decimal("25600") + Decimal(".000001"), 20),
    ],
)
def test_progression_uses_equity_at_fixed_invalidation_including_costs(equity, expected):
    value = assess(sessions=[session(equity - 25000)])
    assert allowance(value, loss=Decimal(5)).maximum_contracts == expected


@pytest.mark.parametrize(
    "fault",
    [
        "account",
        "revision",
        "profile",
        "confirmed",
        "bands-confirmed",
        "bands-version",
        "bands-cap",
        "bands-coverage",
        "calendar-confirmed",
        "calendar-coverage",
        "calendar-closed",
        "floor-disagrees",
        "synthetic-current",
    ],
)
def test_bad_reported_facts_fail_closed(fault):
    e = evidence()
    p = profile()
    rows = [session()]
    if fault == "account":
        e = evidence(account_id="A")
    elif fault == "revision":
        e = evidence(account_revision="a" * 64)
    elif fault == "profile":
        p = profile(minimum_trading_days=10)
    elif fault == "confirmed":
        e = evidence(confirmed=False)
    elif fault == "bands-confirmed":
        e = evidence(progression=progression(confirmed=False))
    elif fault == "bands-version":
        e = evidence(progression=progression(policy_version="other"))
    elif fault == "bands-cap":
        e = evidence(
            progression=progression(
                bands=(ProgressionBand(minimum_equity=23000, maximum_standard_contracts=4),)
            )
        )
    elif fault == "bands-coverage":
        e = evidence(
            progression=progression(
                bands=(ProgressionBand(minimum_equity=25000, maximum_standard_contracts=1),)
            )
        )
    elif fault == "calendar-confirmed":
        e = evidence(calendar=calendar(complete=False))
    elif fault == "calendar-coverage":
        e = evidence(calendar=calendar(coverage_start=NOW + timedelta(seconds=1), windows=()))
    elif fault == "calendar-closed":
        e = evidence(calendar=calendar(windows=()))
    elif fault == "floor-disagrees":
        e = evidence(observed_minimum_balance=23501)
    else:
        rows = [session(account=session().account.model_copy(update={"source": "manual_report"}))]
    value = assess(profile=p, sessions=rows, evidence=e)
    assert value.state != "READY" and allowance(value).maximum_contracts is None


@pytest.mark.parametrize(
    "epsilon", [timedelta(microseconds=-1), timedelta(0), timedelta(microseconds=1)]
)
def test_evidence_age_epsilon_and_firm_flat_deadline(epsilon, monkeypatch):
    value = assess(now=NOW + timedelta(seconds=10) + epsilon)
    assert (value.state == "READY") is (epsilon <= timedelta(0))
    close = datetime(2026, 10, 6, 20, 50, tzinfo=UTC)
    monkeypatch.setattr(ev, "utcnow", lambda: close)
    # Refresh reported evidence for the later cut; source windows can never extend
    # the firm's required deadline even if they claim a longer exchange window.
    e = evidence(
        known_at=close, calendar=calendar(known_at=close), progression=progression(known_at=close)
    )
    row = session(as_of=close, account=session().account.model_copy(update={"observed_at": close}))
    blocked = assess(sessions=[row], evidence=e, now=close)
    assert blocked.state == "BLOCKED"


@settings(max_examples=100, derandomize=True, database=None)
@given(
    equity=st.decimals(
        min_value="25000", max_value="27000", places=4, allow_nan=False, allow_infinity=False
    ),
    cost=st.decimals(
        min_value=".01", max_value="100", places=4, allow_nan=False, allow_infinity=False
    ),
    margin=st.integers(min_value=0, max_value=30),
)
def test_property_stop_capacity_matches_independent_piecewise_oracle(equity, cost, margin):
    value = assess(
        sessions=[session(equity - 25000)], evidence=evidence(margin_contracts_available=margin)
    )
    actual = allowance(value, loss=cost).maximum_contracts
    feasible = []
    for q in range(1, min(30, margin) + 1):
        after = equity - cost * q
        standard = 3 if after >= 26500 else 2 if after >= 25500 else 1 if after >= 23500 else 0
        if (
            q <= standard * 10
            and cost * q < value.daily_loss_remaining
            and after > value.minimum_balance
        ):
            feasible.append(q)
    assert actual == max(feasible, default=0)


def test_another_eod_policy_reuses_the_port_and_arithmetic():
    rules = tcp25_rules().model_copy(
        update={
            "id": "alternate-eod",
            "version": "research-v1",
            "starting_balance": Decimal(50000),
            "profit_target": Decimal(3000),
            "daily_loss_limit": Decimal(1100),
            "maximum_drawdown": Decimal(2000),
        }
    )
    implementation = EODPolicy(rules, controls())
    p = profile(
        starting_balance=50000, profit_target=3000, daily_loss_limit=1100, maximum_drawdown=2000
    )
    row = session(
        account=session().account.model_copy(
            update={"cash_balance": Decimal(50000), "equity": Decimal(50000)}
        )
    )
    e = evidence(
        observed_minimum_balance=48000,
        progression=progression(
            policy_id=rules.id,
            policy_version=rules.version,
            bands=(ProgressionBand(minimum_equity=48000, maximum_standard_contracts=2),),
        ),
    )
    value = implementation.assess(p, [row], account_revision=REVISION, evidence=e, now=NOW)
    result = implementation.allowance(
        value,
        instrument_id="MNQ",
        contract="MNQZ26",
        invalidation=Decimal(178),
        loss_per_contract=Decimal(10),
    )
    assert (
        value.state == "READY"
        and result.maximum_contracts == 20
        and result.policy_id == "alternate-eod"
    )


def policy_service(tmp_path, *, missing=False, halt_age=0):
    from unittest.mock import Mock

    from api.services.advisory import AdvisoryService
    from connectors.advisory.storage import AdvisoryStore
    from core.advisory.selection import select_markets
    from tests.unit import (
        test_advisory_risk as risk_fixture,
        test_market_selection as select_fixture,
    )

    # Translate the existing synthetic replay cohort as one unit. No prices,
    # measured edge or fitted statistics are computed or claimed here.
    offset = NOW - select_fixture.NOW

    def shifted(value):
        def walk(item):
            if isinstance(item, dict):
                return {key: walk(child) for key, child in item.items()}
            if isinstance(item, list):
                return [walk(child) for child in item]
            if isinstance(item, str) and "T" in item:
                try:
                    stamp = datetime.fromisoformat(item.replace("Z", "+00:00"))
                    if stamp.tzinfo is not None:
                        return (stamp + offset).isoformat()
                except ValueError:
                    pass
            return item

        return type(value).model_validate(walk(value.model_dump(mode="json")))

    rules = tcp25_rules()
    selected_policy = select_fixture.policy(
        roots=("MNQ",), evaluation_policy_id=rules.id, evaluation_policy_version=rules.version
    )
    candidate = select_fixture.candidate(
        fit=select_fixture.fit(
            evaluation_policy_id=rules.id, evaluation_policy_version=rules.version
        )
    )
    selected = select_markets(
        {root: shifted(value) for root, value in select_fixture.snapshots(("MNQ",)).items()},
        {"MNQ": shifted(candidate)},
        {root: shifted(value) for root, value in select_fixture.context(("MNQ",)).items()},
        interval="15m",
        now=NOW,
        mode="replay",
        policy=selected_policy,
        event_policy=select_fixture.clear_event_context(NOW)["event_policy"],
    )
    assert selected.primary == "MNQ"
    store = AdvisoryStore(str(tmp_path / "policy.sqlite3"))
    store.create_evaluation(profile())
    store.save_session("B", session())
    store.save_selection(selected)

    from tests.unit.test_account_profiles import plan

    store.create_evaluation(profile(id="A"))
    store.create_evaluation(profile(id="C"))
    store.set_account_plan(plan(selected=selected, now=NOW))

    def inputs_reader(account_id, revision, setup, cut):
        # Deliberately generous reader allowance must be replaced by policy.
        return RiskInputs(
            id="synthetic-inputs",
            version="v1",
            known_at=cut,
            source_reference="SYNTHETIC risk inputs",
            halted=False,
            halted_at=cut - timedelta(seconds=halt_age),
            configuration=risk_fixture.config(),
            history=risk_fixture.history(
                known_at=cut,
                account_id=account_id,
                account_revision=revision,
                peak_equity_usd=25000,
            ),
            allowance=risk_fixture.allowance(
                known_at=cut,
                account_revision=revision,
                maximum_contracts=1000,
                daily_loss_remaining_usd=10000,
                drawdown_remaining_usd=10000,
                at_invalidation=setup.invalidation,
            ),
        )

    def evidence_reader(account_id, revision, setup, cut):
        return evidence(
            account_id=account_id,
            account_revision=revision,
            progression=None if missing else progression(),
        )

    service = AdvisoryService(
        store,
        Mock(),
        clock=lambda: NOW,
        risk_inputs_reader=inputs_reader,
        evaluation_policy=TCP25Policy(controls()),
        policy_evidence_reader=evidence_reader,
        strategy_registry_required=False,  # Isolated policy arithmetic, not approved advice.
    )
    return service, RiskRequest(selection_id=selected.id, setup=shifted(risk_fixture.setup()))


async def test_service_policy_replaces_reader_allowance_and_record_replays(tmp_path):
    from connectors.advisory.storage import AdvisoryStore

    service, request = policy_service(tmp_path)
    value = await service.risk_decision("B", request)
    assert value.state == "QUALIFIED" and value.allowed_contracts == 10
    assert value.evaluation_policy.state == "READY"
    assert value.risk_inputs.allowance.policy_id == tcp25_rules().id
    assert value.risk_inputs.allowance.maximum_contracts == 10
    assert not value.trade_permitted and not value.execution_enabled
    assert AdvisoryStore(str(tmp_path / "policy.sqlite3")).risk_decision(value.id) == value
    assessment = await service.policy_assessment("B", request)
    assert service.store.policy_assessment(assessment.id) == assessment


@pytest.mark.parametrize("fault", ["missing", "stale_halt", "journal_race", "reader_error"])
async def test_service_missing_or_changed_evidence_never_qualifies(tmp_path, fault):
    service, request = policy_service(
        tmp_path, missing=fault == "missing", halt_age=11 if fault == "stale_halt" else 0
    )
    if fault == "journal_race":
        original = service.policy_evidence_reader

        def reader(*args):
            value = original(*args)
            service.store.save_session("B", session(1))
            return value

        service.policy_evidence_reader = reader
    elif fault == "reader_error":
        service.policy_evidence_reader = lambda *args: (_ for _ in ()).throw(OSError("offline"))
    value = await service.risk_decision("B", request)
    assert value.state != "QUALIFIED" and value.allowed_contracts == 0
    if fault == "stale_halt":
        assert "stale_or_future_halt_state" in value.reasons
    elif fault == "journal_race":
        assert "policy_evidence_account_mismatch" in value.evaluation_policy.reasons


async def test_policy_only_source_race_uses_final_journal_and_missing_policy_errors(tmp_path):
    service, request = policy_service(tmp_path)
    service.risk_inputs_reader = None
    original = service.policy_evidence_reader

    def reader(*args):
        value = original(*args)
        service.store.save_session("B", session(1))
        return value

    service.policy_evidence_reader = reader
    value = await service.risk_decision("B", request)
    assert value.evaluation_policy.balance == 25001
    assert "policy_evidence_account_mismatch" in value.evaluation_policy.reasons
    assessment = await service.policy_assessment("B", request)
    assert assessment.balance == 25001
    service.evaluation_policy = None
    with pytest.raises(ValueError, match="No evaluation policy"):
        await service.policy_assessment("B", request)


@pytest.mark.parametrize("fault", ["payload", "id", "time", "account"])
def test_policy_storage_rejects_corrupted_positive_record(tmp_path, fault):
    import json

    from connectors.advisory.storage import AdvisoryStore

    store = AdvisoryStore(str(tmp_path / "corrupt.sqlite3"))
    value = assess()
    store.save_policy_assessment(value)
    with store.connect() as db:
        if fault == "payload":
            payload = value.model_dump(mode="json") | {"minimum_balance": "20000"}
            db.execute("UPDATE policy_assessments SET payload=?", (json.dumps(payload),))
        elif fault == "id":
            payload = value.model_dump(mode="json") | {"id": "other"}
            db.execute("UPDATE policy_assessments SET payload=?", (json.dumps(payload),))
        else:
            column = "created" if fault == "time" else "account"
            db.execute(f"UPDATE policy_assessments SET {column}=?", ("other",))
    with pytest.raises(ValueError):
        store.policy_assessment(value.id)


def test_policy_storage_is_immutable_bounded_and_handles_missing(tmp_path):
    from connectors.advisory.storage import AdvisoryStore

    store = AdvisoryStore(str(tmp_path / "bounded.sqlite3"))
    value = assess()
    store.save_policy_assessment(value)
    with pytest.raises(Exception, match="UNIQUE"):
        store.save_policy_assessment(value)
    assert store.policy_assessment("missing") is None
    for i in range(101):
        store.save_policy_assessment(value.model_copy(update={"id": f"record-{i:03d}"}))
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM policy_assessments").fetchone()[0] == 100


@pytest.mark.parametrize(
    "fault",
    [
        "drawdown",
        "duplicate",
        "micro_subset",
        "nonfuture",
        "bands_order",
        "window_market",
        "window_order",
        "calendar_order",
        "calendar_market",
        "calendar_overlap",
        "calendar_outside",
        "contract",
        "child_future",
        "ready_missing",
        "blocked_missing",
    ],
)
def test_ambiguous_policy_scope_and_time_records_are_rejected(fault):
    rules = tcp25_rules()
    with pytest.raises(ValueError):
        if fault == "drawdown":
            type(rules).model_validate(rules.model_dump() | {"maximum_drawdown": 25000})
        elif fault == "duplicate":
            type(rules).model_validate(
                rules.model_dump() | {"eligible_markets": ("MNQ", "MNQ"), "micro_markets": ("MNQ",)}
            )
        elif fault == "micro_subset":
            type(rules).model_validate(rules.model_dump() | {"micro_markets": ("OTHER",)})
        elif fault == "nonfuture":
            type(rules).model_validate(
                rules.model_dump() | {"eligible_markets": ("NDX",), "micro_markets": ()}
            )
        elif fault == "bands_order":
            progression(
                bands=(
                    ProgressionBand(minimum_equity=25000, maximum_standard_contracts=2),
                    ProgressionBand(minimum_equity=24000, maximum_standard_contracts=1),
                )
            )
        elif fault == "window_market":
            TradingWindow(
                instrument_id="NDX",
                start=NOW,
                end=NOW + timedelta(hours=1),
                flat_by=NOW + timedelta(minutes=50),
            )
        elif fault == "window_order":
            TradingWindow(instrument_id="MNQ", start=NOW, end=NOW, flat_by=NOW)
        elif fault == "calendar_order":
            calendar(coverage_end=NOW - timedelta(days=1))
        elif fault == "calendar_market":
            calendar(covered_markets=("OTHER",), windows=())
        elif fault == "calendar_overlap":
            calendar(windows=calendar().windows * 2)
        elif fault == "calendar_outside":
            calendar(coverage_start=NOW)
        elif fault == "contract":
            evidence(contract="MESZ26")
        elif fault == "child_future":
            evidence(calendar=calendar(known_at=NOW + timedelta(microseconds=1)))
        elif fault == "ready_missing":
            PolicyAssessment.model_validate(assess().model_dump() | {"evidence": None})
        else:
            PolicyAssessment.model_validate(
                assess().model_dump() | {"state": "BLOCKED", "reasons": ()}
            )


@pytest.mark.parametrize(
    "fault",
    [
        "old_rules",
        "unknown_account",
        "open_account",
        "corrupt_source",
        "ineligible",
        "old_progression",
        "old_calendar",
    ],
)
def test_policy_source_failures_keep_capacity_unknown(fault):
    implementation = TCP25Policy(controls())
    rows, source = [session()], evidence()
    if fault == "old_rules":
        implementation = EODPolicy(
            tcp25_rules().model_copy(update={"known_at": NOW - timedelta(days=31)}), controls()
        )
    elif fault == "unknown_account":
        rows = [session(account=None)]
    elif fault == "open_account":
        from core.advisory.account import OpenPosition

        account = session().account.model_copy(
            update={
                "positions": (
                    OpenPosition(
                        position_id="synthetic-open",
                        instrument_id="MGC",
                        contract="MGCZ26",
                        side="BUY",
                        contracts=1,
                        unrealized_pnl=Decimal(0),
                    ),
                )
            }
        )
        rows = [session(account=account)]
    elif fault == "corrupt_source":
        source = evidence().model_copy(update={"confirmed": "yes"})
    elif fault == "ineligible":
        implementation = EODPolicy(
            tcp25_rules().model_copy(
                update={"eligible_markets": ("MGC",), "micro_markets": ("MGC",)}
            ),
            controls(),
        )
    elif fault == "old_progression":
        source = evidence(progression=progression(known_at=NOW - timedelta(seconds=11)))
    else:
        source = evidence(calendar=calendar(known_at=NOW - timedelta(seconds=11)))
    value = implementation.assess(
        profile(), rows, account_revision=REVISION, evidence=source, now=NOW
    )
    result = implementation.allowance(
        value,
        instrument_id="MNQ",
        contract="MNQZ26",
        invalidation=Decimal(178),
        loss_per_contract=Decimal(10),
    )
    assert value.state != "READY" and result.maximum_contracts is None


@pytest.mark.parametrize(
    "cost", [None, Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("Infinity")]
)
def test_policy_missing_or_invalid_cost_never_fabricates_capacity(cost):
    result = allowance(loss=cost)
    assert result.state == "UNKNOWN" and result.maximum_contracts is None


def test_allowance_for_different_dated_market_is_blocked():
    result = TCP25Policy(controls()).allowance(
        assess(),
        instrument_id="MGC",
        contract="MGCZ26",
        invalidation=Decimal(178),
        loss_per_contract=Decimal(10),
    )
    assert result.state == "BLOCKED" and "policy_allowance_market_mismatch" in result.reasons


def test_halt_future_and_mismatched_policy_revision_cannot_qualify():
    from tests.unit.test_advisory_risk import decision, inputs

    with pytest.raises(ValueError, match="future-known halt"):
        inputs(halted_at=inputs().known_at + timedelta(microseconds=1))
    value = decision(evaluation_policy=assess())
    assert "evaluation_policy_account_mismatch" in value.reasons and value.allowed_contracts == 0


@pytest.mark.parametrize("epsilon", [Decimal("-.0001"), Decimal(0), Decimal(".0001")])
def test_stop_touching_drawdown_floor_cannot_fit_one_contract(epsilon):
    # Relax only the synthetic daily rule to isolate the independent floor.
    rules = tcp25_rules().model_copy(update={"daily_loss_limit": Decimal(5000)})
    implementation = EODPolicy(rules, controls())
    value = implementation.assess(
        profile(daily_loss_limit=5000),
        [session()],
        account_revision=REVISION,
        evidence=evidence(margin_contracts_available=1),
        now=NOW,
    )
    result = implementation.allowance(
        value,
        instrument_id="MNQ",
        contract="MNQZ26",
        invalidation=Decimal(178),
        loss_per_contract=Decimal(1500) + epsilon,
    )
    assert result.maximum_contracts == (1 if epsilon < 0 else 0)


@pytest.mark.parametrize(
    "fault", ["no_config", "wrong_stop", "corrupt_policy", "corrupt_configuration"]
)
async def test_service_incomplete_math_or_corrupt_policy_cannot_save_positive(tmp_path, fault):
    service, request = policy_service(tmp_path)
    if fault == "no_config":
        original = service.risk_inputs_reader
        service.risk_inputs_reader = lambda *args: original(*args).model_copy(
            update={"configuration": None}
        )
    elif fault == "wrong_stop":
        request = request.model_copy(
            update={"setup": request.setup.model_copy(update={"invalidation": request.setup.entry})}
        )
    elif fault == "corrupt_configuration":
        original = service.risk_inputs_reader
        service.risk_inputs_reader = lambda *args: original(*args).model_copy(
            update={"configuration": "invalid"}
        )
    else:
        original = service.evaluation_policy.assess
        service.evaluation_policy.assess = lambda *args, **kwargs: original(
            *args, **kwargs
        ).model_copy(update={"daily_loss_remaining": Decimal(100000)})
    if fault == "corrupt_policy":
        with pytest.raises(ValueError, match="reproduce"):
            await service.risk_decision("B", request)
        with service.store.connect() as db:
            assert db.execute("SELECT COUNT(*) FROM risk_decisions").fetchone()[0] == 0
    else:
        value = await service.risk_decision("B", request)
        assert value.allowed_contracts == 0 and value.state != "QUALIFIED"
