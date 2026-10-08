"""Initial account isolation uses synthetic research, never readiness evidence."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest
from hypothesis import given, settings, strategies as st

from connectors.advisory.storage import AdvisoryStore
from core.advisory.account import (
    AccountBinding,
    AccountConfiguration,
    AccountPlan,
    AccountRoleCheck,
    ResearchAssignment,
    assess_account_role,
)
from tests.unit.test_advisory_risk import config, decision, inputs, observation
from tests.unit.test_evaluation import profile as legacy_profile
from tests.unit.test_market_selection import NOW, select

pytestmark = pytest.mark.unit


def configuration(selected=None, **changes):
    selected = select(roots=("MNQ",)) if selected is None else selected
    row = selected.assessments[0]
    edge, fit = row.evidence.edge, row.evidence.fit
    return AccountConfiguration.model_validate(
        dict(
            instrument_id=row.instrument_id,
            strategy_id=edge.strategy_id,
            strategy_version=edge.strategy_version,
            risk_configuration_id=edge.risk_configuration_id,
            risk_configuration_version=config().version,
            evaluation_policy_id=fit.evaluation_policy_id,
            evaluation_policy_version=fit.evaluation_policy_version,
            cost_model_version=edge.cost_model_version,
            edge_id=edge.id,
            edge_version=edge.version,
            fit_id=fit.id,
            fit_version=fit.version,
            dataset_sha256=edge.dataset_sha256,
        )
        | changes
    )


def plan(selected=None, now=NOW, **changes):
    selected = select(roots=("MNQ",)) if selected is None else selected
    assignment = ResearchAssignment(
        configuration=configuration(selected),
        selection_id=selected.id,
        source_reference="SYNTHETIC selected comparison; no real validation claim",
    )
    return AccountPlan.model_validate(
        dict(
            id="synthetic-account-plan",
            version="v1",
            known_at=now,
            source_reference="SYNTHETIC operator assignment",
            origin="synthetic",
            bindings=(
                AccountBinding(slot="B", account_id="B", assignments=(assignment,)),
                AccountBinding(slot="A", account_id="A"),
                AccountBinding(slot="C", account_id="C"),
            ),
        )
        | changes
    )


def role_check(account_id="B", **changes):
    return assess_account_role(
        **(
            dict(
                plan=plan(),
                account_id=account_id,
                requested_configuration=configuration(),
                mode="replay",
                now=NOW,
            )
            | changes
        )
    )


def store_with_plan_sources(tmp_path):
    store = AdvisoryStore(str(tmp_path / "roles.sqlite3"))
    for account_id in ("B", "A", "C"):
        store.create_evaluation(legacy_profile(id=account_id))
    selected = select(roots=("MNQ",))
    store.save_selection(selected)
    return store, plan(selected)


def test_initial_roles_are_explicit_distinct_and_never_trade_permission():
    champion = role_check()
    assert champion.state == "READY" and champion.role == "champion" and champion.slot == "B"
    assert champion.plan_revision == champion.plan.revision
    assert not champion.trade_permitted and not champion.execution_enabled
    assert role_check("A").reasons == ("challenger_shadow_only", "champion_workflow_not_proven")
    assert role_check("C").reasons == ("reserve_account_locked",)
    assert role_check("unknown").reasons == ("account_not_in_plan",)


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "unassigned",
        "configuration",
        "future",
        "current_synthetic",
        "invalid_plan",
        "invalid_request",
    ],
)
def test_role_evidence_failures_never_allow_positive_risk(fault):
    p, request = plan(), configuration()
    mode, now = "replay", NOW
    if fault == "missing":
        p = None
    elif fault == "unassigned":
        p = plan(bindings=tuple(b.model_copy(update={"assignments": ()}) for b in p.bindings))
    elif fault == "configuration":
        request = configuration(risk_configuration_version="other")
    elif fault == "future":
        now = NOW - timedelta(microseconds=1)
    elif fault == "current_synthetic":
        mode = "current"
    elif fault == "invalid_plan":
        p = p.model_copy(update={"reserve_locked": False})
    else:
        request = request.model_copy(update={"instrument_id": "NDX"})
    value = role_check(plan=p, requested_configuration=request, mode=mode, now=now)
    assert value.state != "READY" and value.reasons


@pytest.mark.parametrize(
    "fault",
    [
        "shared_journal",
        "duplicate_slot",
        "reserve_assignment",
        "duplicate_market",
        "unlock",
        "copying",
        "unknown_market",
        "fake_ready",
        "missing_reasons",
        "wrong_revision",
        "wrong_role",
    ],
)
def test_invalid_role_topology_and_forged_positive_results_are_rejected(fault):
    p = plan()
    with pytest.raises(ValueError):
        if fault == "shared_journal":
            plan(bindings=tuple(b.model_copy(update={"account_id": "B"}) for b in p.bindings))
        elif fault == "duplicate_slot":
            plan(bindings=tuple(b.model_copy(update={"slot": "B"}) for b in p.bindings))
        elif fault == "reserve_assignment":
            AccountBinding(slot="C", account_id="C", assignments=p.bindings[0].assignments)
        elif fault == "duplicate_market":
            AccountBinding(slot="B", account_id="B", assignments=p.bindings[0].assignments * 2)
        elif fault == "unlock":
            plan(reserve_locked=False)
        elif fault == "copying":
            plan(trade_copying_enabled=True)
        elif fault == "unknown_market":
            configuration(instrument_id="NDX")
        else:
            changes = (
                {"state": "READY", "reasons": ()}
                if fault == "fake_ready"
                else (
                    {"state": "BLOCKED", "reasons": ()}
                    if fault == "missing_reasons"
                    else (
                        {"plan_revision": "a" * 64}
                        if fault == "wrong_revision"
                        else {"role": "reserve"}
                    )
                )
            )
            AccountRoleCheck.model_validate(
                role_check("C" if fault == "fake_ready" else "B").model_dump() | changes
            )


@pytest.mark.parametrize("slot", ["B", "A", "C"])
def test_final_risk_role_gate_cannot_increase_size_or_borrow_an_account(slot):
    value = decision(
        account_id=slot,
        observation=observation(account_id=slot),
        inputs=inputs(
            history=inputs().history.model_copy(update={"account_id": slot}),
            allowance=inputs().allowance.model_copy(update={"account_id": slot}),
        ),
        account_plan=plan(),
        account_roles_required=True,
    )
    assert value.account_role_check.slot == slot
    if slot == "B":
        assert value.state == "QUALIFIED" and value.allowed_contracts == 6
    else:
        assert value.allowed_contracts == 0 and value.state == "BLOCKED"
    assert not value.trade_permitted and not value.execution_enabled


def test_missing_plan_blocks_role_required_math_without_rewriting_general_math():
    assert decision().allowed_contracts == 6
    value = decision(account_roles_required=True)
    assert value.allowed_contracts == 0 and "missing_account_plan" in value.reasons


@settings(max_examples=80, derandomize=True, database=None)
@given(
    slot=st.sampled_from(("A", "C")),
    equity=st.decimals(
        min_value="1", max_value="100000", places=4, allow_nan=False, allow_infinity=False
    ),
)
def test_property_shadow_and_reserve_never_gain_size_from_another_balance(slot, equity):
    value = decision(
        account_id=slot,
        observation=observation(account_id=slot, cash_balance=equity, equity=equity),
        journal_equity=equity,
        account_plan=plan(),
        account_roles_required=True,
    )
    assert value.state == "BLOCKED" and value.allowed_contracts == 0


def test_store_role_plan_is_atomic_versioned_and_survives_reopen(tmp_path):
    store, value = store_with_plan_sources(tmp_path)
    assert store.account_plan() is None
    revision = store.set_account_plan(value)
    assert store.set_account_plan(value) == revision
    other = AdvisoryStore(str(tmp_path / "roles.sqlite3"))
    assert other.account_plan() == value
    p, rows, captured = other.evaluation_context("B")
    assert p.id == "B" and rows == [] and captured == value
    updated = value.model_copy(update={"version": "v2", "known_at": NOW + timedelta(seconds=1)})
    with pytest.raises(ValueError, match="revision changed"):
        store.set_account_plan(updated)
    assert store.set_account_plan(updated, expected_revision=revision) == updated.revision
    assert other.account_plan() == updated


@pytest.mark.parametrize(
    "fault",
    [
        "missing_journal",
        "missing_comparison",
        "comparison_id",
        "comparison_time",
        "comparison_key_time",
        "ineligible",
        "wrong_configuration",
        "reported_replay",
        "binding_swap",
        "same_version",
        "old_time",
    ],
)
def test_store_cannot_install_or_update_unsupported_assignments(tmp_path, fault):
    store, value = store_with_plan_sources(tmp_path)
    expected = None
    if fault in {"binding_swap", "same_version", "old_time"}:
        expected = store.set_account_plan(value)
        value = value.model_copy(update={"version": "v2", "known_at": NOW + timedelta(seconds=1)})
        if fault == "binding_swap":
            value = value.model_copy(
                update={
                    "bindings": tuple(
                        b.model_copy(
                            update={
                                "account_id": (
                                    "A" if b.slot == "B" else "B" if b.slot == "A" else "C"
                                )
                            }
                        )
                        for b in value.bindings
                    )
                }
            )
        elif fault == "same_version":
            value = value.model_copy(update={"version": "v1"})
        else:
            value = value.model_copy(update={"known_at": NOW})
    elif fault == "reported_replay":
        value = value.model_copy(update={"origin": "reported"})
    elif fault == "wrong_configuration":
        b = value.bindings[0]
        a = b.assignments[0]
        value = value.model_copy(
            update={
                "bindings": (
                    b.model_copy(
                        update={
                            "assignments": (
                                a.model_copy(
                                    update={
                                        "configuration": a.configuration.model_copy(
                                            update={"fit_version": "other"}
                                        )
                                    }
                                ),
                            )
                        }
                    ),
                    *value.bindings[1:],
                )
            }
        )
    else:
        with store.connect() as db:
            if fault == "missing_journal":
                db.execute("DELETE FROM evaluations WHERE id='C'")
            elif fault == "missing_comparison":
                db.execute("DELETE FROM selections")
            else:
                import json

                raw = json.loads(db.execute("SELECT payload FROM selections").fetchone()[0])
                if fault == "comparison_id":
                    raw["id"] = "other"
                elif fault == "comparison_key_time":
                    db.execute("UPDATE selections SET created='wrong-time'")
                elif fault == "comparison_time":
                    value = value.model_copy(update={"known_at": NOW - timedelta(microseconds=1)})
                else:
                    raw["assessments"][0]["eligible"] = False
                    raw["ranked"] = []
                    raw["primary"] = None
                db.execute("UPDATE selections SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError):
        store.set_account_plan(value, expected_revision=expected)


def test_two_plan_initializers_cannot_overwrite_each_other(tmp_path):
    store, value = store_with_plan_sources(tmp_path)
    other = value.model_copy(update={"id": "other-plan"})

    def write(candidate):
        try:
            return store.set_account_plan(candidate)
        except ValueError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, (value, other)))
    assert sum(r is not None for r in results) == 1
    assert store.account_plan().revision in results


def test_corrupted_stored_plan_or_missing_bound_journal_never_falls_back(tmp_path):
    store, value = store_with_plan_sources(tmp_path)
    store.set_account_plan(value)
    with store.connect() as db:
        db.execute("DELETE FROM evaluations WHERE id='C'")
    with pytest.raises(ValueError, match="missing financial journal"):
        store.evaluation_context("B")
    with store.connect() as db:
        db.execute("UPDATE settings SET value='{}' WHERE key='account_plan'")
    with pytest.raises(ValueError):
        store.account_plan()


async def test_service_roles_hold_with_other_financial_gates_ready(tmp_path, monkeypatch):
    from core.advisory import evaluation as ev
    from tests.unit.test_evaluation_policy import NOW as POLICY_NOW, policy_service, session

    monkeypatch.setattr(ev, "utcnow", lambda: POLICY_NOW)
    service, request = policy_service(tmp_path)
    for slot in ("A", "C"):
        row = session()
        row = row.model_copy(
            update={"account": row.account.model_copy(update={"account_id": slot})}
        )
        service.store.save_session(slot, row)
        value = await service.risk_decision(slot, request)
        assert value.evaluation_policy.state == "READY"
        assert value.account_state.health == "KNOWN"
        assert value.state == "BLOCKED" and value.allowed_contracts == 0
        assert value.account_role_check.slot == slot
        assert service.store.risk_decision(value.id) == value
    champion = await service.risk_decision("B", request)
    assert champion.allowed_contracts == 10 and champion.account_role_check.state == "READY"
    assert service.store.risk_decision(champion.id) == champion


async def test_role_change_during_acquisition_uses_final_plan_and_blocks_old_config(
    tmp_path, monkeypatch
):
    from core.advisory import evaluation as ev
    from tests.unit.test_evaluation_policy import NOW as POLICY_NOW, policy_service

    monkeypatch.setattr(ev, "utcnow", lambda: POLICY_NOW)
    service, request = policy_service(tmp_path)
    original = service.risk_inputs_reader
    before = service.store.account_plan()
    after = before.model_copy(
        update={
            "version": "v2",
            "known_at": POLICY_NOW + timedelta(seconds=1),
            "bindings": tuple(b.model_copy(update={"assignments": ()}) for b in before.bindings),
        }
    )

    def reader(*args):
        inputs = original(*args)
        service.store.set_account_plan(after, expected_revision=before.revision)
        return inputs

    service.risk_inputs_reader = reader
    times = iter((POLICY_NOW, POLICY_NOW + timedelta(seconds=1)))
    service.clock = lambda: next(times)
    value = await service.risk_decision("B", request)
    assert value.account_role_check.plan_revision == after.revision
    assert "missing_champion_configuration_assignment" in value.reasons
    assert value.allowed_contracts == 0


def test_positive_risk_role_record_rejects_hidden_assignment_loss(tmp_path):
    value = decision(account_plan=plan(), account_roles_required=True)
    store = AdvisoryStore(str(tmp_path / "risk-record.sqlite3"))
    store.save_risk_decision(value)
    import json

    with store.connect() as db:
        raw = json.loads(db.execute("SELECT payload FROM risk_decisions").fetchone()[0])
        captured = raw["account_role_check"]["plan"]
        captured["bindings"][0]["assignments"] = []
        rewritten = AccountPlan.model_validate(captured)
        raw["account_role_check"]["plan_revision"] = rewritten.revision
        db.execute("UPDATE risk_decisions SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError):
        store.risk_decision(value.id)


def test_positive_record_cannot_silently_remove_its_account_role_scope(tmp_path):
    import json

    value = decision(account_plan=plan(), account_roles_required=True)
    store = AdvisoryStore(str(tmp_path / "role-scope.sqlite3"))
    store.save_risk_decision(value)
    with store.connect() as db:
        raw = json.loads(db.execute("SELECT payload FROM risk_decisions").fetchone()[0])
        raw["account_roles_required"] = False
        raw["account_role_check"] = None
        db.execute("UPDATE risk_decisions SET payload=?", (json.dumps(raw),))
    with pytest.raises(ValueError):
        store.risk_decision(value.id)


def test_reported_historical_labels_are_metadata_not_authenticated_validation(tmp_path):
    from tests.unit.test_market_selection import candidate, edge, snapshots

    # The deliberately test-labelled inputs verify the branch; neither changing
    # origin labels nor READY authenticates licensed data or genuine approval.
    markets = {
        k: v.model_copy(update={"data_mode": "user_import"}) for k, v in snapshots(("MNQ",)).items()
    }
    selected = select(
        roots=("MNQ",),
        markets=markets,
        inputs={"MNQ": candidate(edge=edge(origin="historical"))},
        mode="current",
    )
    assert selected.primary == "MNQ" and not selected.trade_permitted
    store = AdvisoryStore(str(tmp_path / "reported-labels.sqlite3"))
    for slot in ("B", "A", "C"):
        store.create_evaluation(legacy_profile(id=slot))
    store.save_selection(selected)
    value = plan(selected=selected, origin="reported")
    store.set_account_plan(value)
    checked = role_check(plan=value, mode="current")
    assert checked.state == "READY" and not checked.trade_permitted
    assert store.account_plan() == value


@pytest.mark.parametrize(
    "epsilon", [timedelta(microseconds=-1), timedelta(0), timedelta(microseconds=1)]
)
def test_plan_knowledge_clock_boundary_uses_instants(epsilon):
    value = role_check(now=NOW + epsilon)
    assert (value.state == "READY") is (epsilon >= timedelta(0))


@pytest.mark.parametrize(
    "epsilon", [timedelta(microseconds=-1), timedelta(0), timedelta(microseconds=1)]
)
def test_plan_update_known_time_is_strictly_later_at_epsilon(tmp_path, epsilon):
    store, value = store_with_plan_sources(tmp_path)
    revision = store.set_account_plan(value)
    next_value = value.model_copy(update={"version": "v2", "known_at": NOW + epsilon})
    if epsilon <= timedelta(0):
        with pytest.raises(ValueError, match="later known-at"):
            store.set_account_plan(next_value, expected_revision=revision)
        assert store.account_plan() == value
    else:
        store.set_account_plan(next_value, expected_revision=revision)
        assert store.account_plan() == next_value
