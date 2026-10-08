"""Isolated API writes, reports and bounded input do not need the trading stack."""

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api.advisor import app
from core.config import settings
from tests.unit.test_advisory import market
from tests.unit.test_evaluation import profile

pytestmark = pytest.mark.unit
HEADERS = {"X-Advisory-Client": "dashboard"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "operating_profile", "earn2trade_tcp25")
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("b" * 48))
    monkeypatch.setattr(settings, "advisory_db_path", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(settings, "advisory_kafka_servers", "")
    monkeypatch.setattr("api.services.advisory.headlines", AsyncMock(return_value=([], [])))
    with TestClient(app, headers={"Authorization": "Bearer " + "b" * 48}) as value:
        yield value


def test_api_offline_nasdaq_is_explicit_and_cannot_trade(client):
    assert client.get("/assistant-api/health").json()["execution_enabled"] is False
    catalog = {item["id"]: item for item in client.get("/assistant-api/catalog").json()}
    assert {"MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG"} <= catalog.keys()
    assert catalog["M6B"]["point_value"] == "6250"
    assert catalog["MGC"]["futures_spec"]["settlement"] == "physical"
    r = client.get("/assistant-api/report/MNQ").json()
    assert r["status"] == "unavailable" and r["scenarios"] == []
    assert client.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404
    assert client.get("/assistant-api/report/UNKNOWN").status_code == 400
    assert client.get("/assistant-api/report/NQ?interval=2m").status_code == 422
    assert client.get("/assistant-api/saved/missing").status_code == 404


@pytest.mark.parametrize(
    "selected,policy_id",
    [
        ("general", None),
        ("earn2trade_tcp25", "earn2trade-tcp25-eod"),
        ("earn2trade_tcp50", "earn2trade-tcp50-eod"),
    ],
)
def test_api_profile_selects_policy_without_creating_accounts(
    tmp_path, monkeypatch, selected, policy_id
):
    monkeypatch.setattr(settings, "operating_profile", selected)
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("b" * 48))
    monkeypatch.setattr(settings, "advisory_db_path", str(tmp_path / "selected.sqlite3"))
    monkeypatch.setattr(settings, "advisory_kafka_servers", "")
    with TestClient(app, headers={"Authorization": "Bearer " + "b" * 48}) as current:
        description = current.get("/assistant-api/evaluation-policy").json()
        assert description["configured"] is (policy_id is not None)
        assert (description["rules"]["id"] if description["rules"] else None) == policy_id
        assert description["trade_permitted"] is description["execution_enabled"] is False
        assert current.get("/assistant-api/evaluations").json() == []
        assert (
            app.state.service.account_roles_required
            and app.state.service.strategy_registry_required
        )
        assert app.state.service.policy_evidence_reader is None
        assert current.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404
        if selected != "earn2trade_tcp50":
            return
        from tests.unit.test_advisory_risk import setup
        from tests.unit.test_evaluation_policy import tcp50_inputs

        p, row, _, now = tcp50_inputs(monkeypatch)
        assert description["rules"]["profit_target"] == "3000"
        assert description["rules"]["starting_balance"] == "50000"
        app.state.service.clock = lambda: now
        app.state.service.store.create_evaluation(p)
        app.state.service.store.save_session(p.id, row)
        payload = {"setup": setup(known_at=now).model_dump(mode="json")}
        result = current.post(
            "/assistant-api/evaluations/B/policy-check", json=payload, headers=HEADERS
        )
        assert result.status_code == 200
        value = result.json()
        assert value["state"] == "UNKNOWN" and "missing_policy_evidence" in value["reasons"]
        assert "unverified_tcp50_progression_limits" in value["reasons"]
        assert current.get("/assistant-api/policy-check/" + value["id"]).json() == value
        decision = current.post(
            "/assistant-api/evaluations/B/risk-decision", json=payload, headers=HEADERS
        ).json()
        assert decision["allowed_contracts"] == 0 and decision["advice"] == "NO TRADE"
        assert decision["trade_permitted"] is decision["execution_enabled"] is False


def test_api_valid_import_analysis_cache_history_and_independent_watchlist(client):
    data = market().model_dump(mode="json")
    assert client.post("/assistant-api/import", json=data, headers=HEADERS).status_code == 200
    report = client.get("/assistant-api/report/MNQ").json()
    assert report["status"] == "ready"
    assert report["data_health"]["state"] == "HEALTHY"
    assert report["data_health"]["trade_permitted"] is False
    assert report["event_risk"]["state"] == "UNKNOWN"
    assert report["event_risk"]["trade_permitted"] is False
    assert report["scenarios"] == []
    assert client.get("/assistant-api/report/MNQ").json()["id"] == report["id"]
    assert client.get("/assistant-api/history").json()[0]["id"] == report["id"]
    assert client.get(f"/assistant-api/saved/{report['id']}").json() == report
    assert client.get("/assistant-api/report/NQ").status_code == 400
    assert (
        client.put(
            "/assistant-api/watchlist",
            json={"instruments": ["MNQ"], "interests": ["rates"]},
            headers=HEADERS,
        ).status_code
        == 200
    )
    assert client.get("/assistant-api/watchlist").json()["instruments"] == ["MNQ"]
    assert (
        client.post(
            "/assistant-api/import", json=data | {"data_mode": "public_exchange"}, headers=HEADERS
        ).status_code
        == 400
    )


@pytest.mark.parametrize("fault", ["missing", "degraded", "sequence", "gap"])
def test_api_persists_blocked_health_and_cannot_override_it(client, fault):
    value = market()
    if fault == "missing":
        value.quality = None
    elif fault == "gap":
        value.candles.pop(30)
    elif fault == "degraded":
        value.quality = value.quality.model_copy(update={"provider_state": "degraded"})
    else:
        value.quality = value.quality.model_copy(update={"sequence_mode": "required"})
    data = value.model_dump(mode="json")
    assert client.post("/assistant-api/import", json=data, headers=HEADERS).status_code == 200
    report = client.get("/assistant-api/report/MNQ").json()
    assert report["data_health"]["state"] != "HEALTHY"
    assert report["scenarios"] == [] and report["indicators"] == {}
    assert report["data_health"]["trade_permitted"] is False
    assert client.get(f"/assistant-api/saved/{report['id']}").json() == report
    data["data_health"] = {"state": "HEALTHY"}
    assert client.post("/assistant-api/import", json=data, headers=HEADERS).status_code == 422
    assert client.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404


@pytest.mark.parametrize("root,contract", [("MGC", "MGCV26"), ("MCL", "MCLX26"), ("MHG", "MHGX26")])
def test_api_monthly_contract_import_persists_without_execution(client, root, contract):
    data = market().model_dump(mode="json") | {"instrument_id": root, "contract": contract}
    assert client.post("/assistant-api/import", json=data, headers=HEADERS).status_code == 200
    report = client.get(f"/assistant-api/report/{root}").json()
    assert report["market"]["contract"] == contract
    assert report["instrument"]["futures_spec"]["version"] == "cme-outright-2026-10-05"
    assert report["execution_enabled"] is False
    assert client.get(f"/assistant-api/saved/{report['id']}").json() == report
    assert client.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404
    assert (
        client.post(
            "/assistant-api/import", json=data | {"contract": "MNQZ26"}, headers=HEADERS
        ).status_code
        == 422
    )


def test_api_rejects_cross_origin_writes_and_actual_oversize_body(client):
    assert client.put("/assistant-api/watchlist", json={}).status_code == 403
    assert (
        client.post(
            "/assistant-api/import",
            content=b"x" * 500001,
            headers=HEADERS | {"Content-Length": "1"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/assistant-api/import", content=iter([b"x" * 260000, b"x" * 260000]), headers=HEADERS
        ).status_code
        == 413
    )
    assert (
        client.get("/assistant-api/health", headers={"Host": "attacker.example"}).status_code == 400
    )
    response = client.options(
        "/assistant-api/watchlist",
        headers={"Origin": "https://attacker.example", "Access-Control-Request-Method": "PUT"},
    )
    assert "access-control-allow-origin" not in response.headers


def test_api_evaluation_persists_and_never_invents_a_profile(client):
    assert client.get("/assistant-api/evaluations").json() == []
    p = profile().model_dump(mode="json")
    assert client.post("/assistant-api/evaluations", json=p, headers=HEADERS).status_code == 200
    state = client.get(f"/assistant-api/evaluations/{p['id']}").json()
    assert state["sessions"] == [] and not state["recorded_targets_met"]
    assert client.get("/assistant-api/evaluation-rules").json()["reviewed_on"] == "2026-09-28"
    assert client.get("/assistant-api/evaluations/missing").status_code == 400


def test_advisory_imports_cannot_reach_execution_or_main_state():
    root = Path(__file__).resolve().parents[2] / "src"
    paths = [
        root / "api/advisor.py",
        root / "api/services/advisory.py",
        *list((root / "core/advisory").glob("*.py")),
        *list((root / "connectors/advisory").glob("*.py")),
    ]
    prohibited = (
        "agents",
        "core.execution",
        "core.accounting",
        "core.orchestrator",
        "connectors.exchanges",
        "api.main",
        "redis",
        "asyncpg",
    )
    for path in paths:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            )
            assert not any(
                name == p or name.startswith(p + ".") for name in names for p in prohibited
            ), path
        assert "AIOKafkaProducer" not in path.read_text()


def test_csv_malformed_numbers_and_truncated_rows_are_client_errors(client):
    value = dict(
        instrument_id="MNQ", interval="15m", contract="MNQZ26", source="https://example.com/chart"
    )
    for csv in (
        "time,open,high,low,close,volume\n2026-09-01T10:00:00Z,oops,2,1,1,1",
        "open,high,low,close,volume,time\n1,2",
    ):
        response = client.post(
            "/assistant-api/import-csv", json=value | {"csv": csv}, headers=HEADERS
        )
        assert response.status_code == 400


def test_api_requires_persisted_complete_account_state_before_evaluation_plan(client, monkeypatch):
    from core.advisory import evaluation as ev
    from tests.unit.test_advisory_account import observed_session
    from tests.unit.test_evaluation import NOW, plan, session

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    p = profile()
    assert (
        client.post(
            "/assistant-api/evaluations", json=p.model_dump(mode="json"), headers=HEADERS
        ).status_code
        == 200
    )
    url = f"/assistant-api/evaluations/{p.id}"
    row = session(pnl=-500, low=-500)
    saved = client.put(url + "/session", json=row.model_dump(mode="json"), headers=HEADERS)
    assert saved.status_code == 200 and saved.json()["account_state"]["health"] == "UNKNOWN"
    request = plan().model_dump(mode="json")
    blocked = client.post(url + "/plan", json=request, headers=HEADERS)
    assert blocked.status_code == 400 and "account observation" in blocked.json()["detail"]
    saved = client.put(
        url + "/session", json=observed_session().model_dump(mode="json"), headers=HEADERS
    )
    assert saved.status_code == 200 and saved.json()["account_state"]["health"] == "KNOWN"
    result = client.post(url + "/plan", json=request, headers=HEADERS)
    assert result.status_code == 400 and "NO TRADE" in result.json()["detail"]
    # Isolated research arithmetic requires both scopes off and no bound plan.
    app.state.service.account_roles_required = False
    app.state.service.strategy_registry_required = False
    result = client.post(url + "/plan", json=request, headers=HEADERS)
    assert result.status_code == 200 and result.json()["size"] == "10"
    # A request-side override cannot substitute another account's nominal capital.
    request["account_value"] = "50000"
    assert client.post(url + "/plan", json=request, headers=HEADERS).status_code == 400
    assert client.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404


def test_selection_default_is_fail_closed_read_only_and_durable(client):
    response = client.get("/assistant-api/market-selection")
    assert response.status_code == 200
    value = response.json()
    assert value["primary"] is None and value["backup"] is None and value["ranked"] == []
    assert (
        value["trade_permitted"]
        is value["execution_enabled"]
        is value["simultaneous_use_permitted"]
        is False
    )
    assert {row["instrument_id"] for row in value["assessments"]} == {"MES", "MYM", "MNQ", "MGC"}
    assert all("missing_research_evidence" in row["reasons"] for row in value["assessments"])
    assert client.get("/assistant-api/selection-record/" + value["id"]).json() == value
    assert client.get("/assistant-api/selection-record/missing").status_code == 404
    assert client.get("/assistant-api/market-selection?interval=2m").status_code == 422
    assert (
        client.post(
            "/assistant-api/market-selection", headers=HEADERS, json={"primary": "MNQ"}
        ).status_code
        == 405
    )
    assert client.post("/assistant-api/orders", headers=HEADERS, json={}).status_code == 404


def test_selection_api_returns_faults_without_nomination(client, monkeypatch):
    for fault, code in [(ValueError("missing policy"), 400), (TimeoutError(), 504)]:
        monkeypatch.setattr(app.state.service, "selection", AsyncMock(side_effect=fault))
        assert client.get("/assistant-api/market-selection").status_code == code
    monkeypatch.setattr(
        app.state.service.store,
        "selection",
        lambda _: (_ for _ in ()).throw(ValueError("bad persisted identity")),
    )
    assert client.get("/assistant-api/selection-record/corrupt").status_code == 400


def test_api_risk_decision_requires_server_state_and_disallows_budget_overrides(client):
    from tests.unit.test_advisory_risk import setup

    value = profile()
    assert (
        client.post(
            "/assistant-api/evaluations", json=value.model_dump(mode="json"), headers=HEADERS
        ).status_code
        == 200
    )
    payload = {"setup": setup().model_dump(mode="json")}
    response = client.post(
        f"/assistant-api/evaluations/{value.id}/risk-decision", json=payload, headers=HEADERS
    )
    assert response.status_code == 200
    decision = response.json()
    assert decision["advice"] == "NO TRADE" and decision["allowed_contracts"] == 0
    assert (
        decision["risk_qualified"]
        is decision["trade_permitted"]
        is decision["execution_enabled"]
        is False
    )
    assert client.get("/assistant-api/risk-decision/" + decision["id"]).json() == decision
    assert client.get("/assistant-api/risk-decision/missing").status_code == 404
    assert (
        client.post(
            "/assistant-api/evaluations/missing/risk-decision", json=payload, headers=HEADERS
        ).status_code
        == 400
    )
    for key in ("account_value", "risk_percent", "contracts", "policy_allowance"):
        assert (
            client.post(
                f"/assistant-api/evaluations/{value.id}/risk-decision",
                json=payload | {key: 100000},
                headers=HEADERS,
            ).status_code
            == 422
        )
    assert client.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404


def test_api_synthetic_qualified_risk_is_wait_and_can_be_reproduced(client, tmp_path):
    from tests.unit.test_advisory_risk import make_service

    service, request, _ = make_service(tmp_path)
    app.state.service = service
    response = client.post(
        "/assistant-api/evaluations/B/risk-decision",
        json=request.model_dump(mode="json"),
        headers=HEADERS,
    )
    assert response.status_code == 200
    value = response.json()
    assert (
        value["state"] == "QUALIFIED"
        and value["allowed_contracts"] == 6
        and value["advice"] == "WAIT"
    )
    assert value["trade_permitted"] is value["execution_enabled"] is False
    assert client.get("/assistant-api/risk-decision/" + value["id"]).json() == value


def test_api_risk_source_timeouts_and_stored_corruption_are_fail_closed(client, monkeypatch):
    from tests.unit.test_advisory_risk import setup

    monkeypatch.setattr(app.state.service, "risk_decision", AsyncMock(side_effect=TimeoutError()))
    assert (
        client.post(
            "/assistant-api/evaluations/B/risk-decision",
            json={"setup": setup().model_dump(mode="json")},
            headers=HEADERS,
        ).status_code
        == 504
    )
    monkeypatch.setattr(
        app.state.service.store,
        "risk_decision",
        lambda _: (_ for _ in ()).throw(ValueError("synthetic corrupted key")),
    )
    assert client.get("/assistant-api/risk-decision/invalid").status_code == 400


def test_api_policy_default_is_versioned_and_missing_evidence_is_unknown(client, monkeypatch):
    from core.advisory import evaluation as ev
    from tests.unit.test_advisory_risk import setup
    from tests.unit.test_evaluation_policy import NOW, profile, session

    description = client.get("/assistant-api/evaluation-policy").json()
    assert description["configured"] and description["rules"]["minimum_trading_days"] == 0
    assert description["trade_permitted"] is description["execution_enabled"] is False
    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    app.state.service.clock = lambda: NOW
    app.state.service.store.create_evaluation(profile())
    app.state.service.store.save_session("B", session())
    payload = {"setup": setup(known_at=NOW).model_dump(mode="json")}
    response = client.post(
        "/assistant-api/evaluations/B/policy-check", json=payload, headers=HEADERS
    )
    assert response.status_code == 200
    value = response.json()
    assert value["state"] == "UNKNOWN" and "missing_policy_evidence" in value["reasons"]
    assert value["trade_permitted"] is value["execution_enabled"] is False
    assert client.get("/assistant-api/policy-check/" + value["id"]).json() == value
    assert client.get("/assistant-api/policy-check/missing").status_code == 404
    assert client.post("/assistant-api/evaluations/B/policy-check", json=payload).status_code == 403
    assert (
        client.post(
            "/assistant-api/evaluations/missing/policy-check", json=payload, headers=HEADERS
        ).status_code
        == 400
    )
    for key in ("risk_percent", "contracts", "policy_allowance", "margin"):
        assert (
            client.post(
                "/assistant-api/evaluations/B/policy-check",
                json=payload | {key: 10000},
                headers=HEADERS,
            ).status_code
            == 422
        )
    app.state.service.evaluation_policy = None
    assert client.get("/assistant-api/evaluation-policy").json()["configured"] is False
    assert (
        client.post(
            "/assistant-api/evaluations/B/policy-check", json=payload, headers=HEADERS
        ).status_code
        == 400
    )
    assert client.post("/assistant-api/orders", json={}, headers=HEADERS).status_code == 404


def test_api_policy_timeout_and_corruption_are_explicit(client, monkeypatch):
    from tests.unit.test_advisory_risk import setup

    monkeypatch.setattr(
        app.state.service, "policy_assessment", AsyncMock(side_effect=TimeoutError())
    )
    assert (
        client.post(
            "/assistant-api/evaluations/B/policy-check",
            json={"setup": setup().model_dump(mode="json")},
            headers=HEADERS,
        ).status_code
        == 504
    )
    monkeypatch.setattr(
        app.state.service.store,
        "policy_assessment",
        lambda _: (_ for _ in ()).throw(ValueError("corrupt")),
    )
    assert client.get("/assistant-api/policy-check/invalid").status_code == 400


def test_api_account_plan_is_required_read_only_and_does_not_infer_roles(client, monkeypatch):
    value = client.get("/assistant-api/account-plan").json()
    assert value["required"] and not value["configured"]
    assert value["plan"] is value["revision"] is None
    assert value["trade_permitted"] is value["execution_enabled"] is False
    for path in ("account-plan", "accounts/C/unlock", "accounts/A/promote", "copy-trades"):
        assert client.post("/assistant-api/" + path, json={}, headers=HEADERS).status_code in (
            404,
            405,
        )
    monkeypatch.setattr(
        app.state.service.store,
        "account_plan",
        lambda: (_ for _ in ()).throw(ValueError("corrupt")),
    )
    assert client.get("/assistant-api/account-plan").status_code == 400


def test_api_account_role_snapshot_and_forbidden_assignment_inputs(client, tmp_path, monkeypatch):
    from core.advisory import evaluation as ev
    from tests.unit.test_evaluation_policy import NOW, policy_service

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    service, request = policy_service(tmp_path)
    app.state.service = service
    response = client.get("/assistant-api/account-plan").json()
    assert response["configured"] and response["required"]
    assert response["revision"] == service.store.account_plan().revision
    assert response["plan"]["reserve_locked"] and response["plan"]["challenger_shadow_only"]
    body = request.model_dump(mode="json")
    for key in ("account_plan", "account_roles_required", "role", "champion_workflow_proven"):
        assert (
            client.post(
                "/assistant-api/evaluations/B/risk-decision",
                json=body | {key: False},
                headers=HEADERS,
            ).status_code
            == 422
        )
    value = client.post(
        "/assistant-api/evaluations/B/risk-decision", json=body, headers=HEADERS
    ).json()
    assert value["account_role_check"]["state"] == "READY"
    assert value["account_role_check"]["plan_revision"] == response["revision"]
    assert value["trade_permitted"] is value["execution_enabled"] is False


@pytest.mark.parametrize("slot", ["A", "C", "B"])
def test_legacy_account_planner_cannot_bypass_roles(client, tmp_path, monkeypatch, slot):
    from core.advisory import evaluation as ev
    from tests.unit.test_evaluation import plan as legacy_plan
    from tests.unit.test_evaluation_policy import NOW, policy_service, session

    monkeypatch.setattr(ev, "utcnow", lambda: NOW)
    service, _ = policy_service(tmp_path)
    app.state.service = service
    if slot != "B":
        row = session()
        service.store.save_session(
            slot,
            row.model_copy(update={"account": row.account.model_copy(update={"account_id": slot})}),
        )
    body = legacy_plan(account_value=25000).model_dump(mode="json")
    response = client.post(f"/assistant-api/evaluations/{slot}/plan", json=body, headers=HEADERS)
    assert response.status_code == 400
    assert "NO TRADE" in response.json()["detail"]


def test_saved_report_corruption_is_explicit_and_never_approval(client, monkeypatch):
    monkeypatch.setattr(
        app.state.service.store,
        "report",
        lambda _: (_ for _ in ()).throw(ValueError("SYNTHETIC report corruption")),
    )
    assert client.get("/assistant-api/saved/corrupt").status_code == 400


def test_client_cannot_supply_registry_approval_or_disable_its_gate(client, tmp_path):
    from tests.unit.test_advisory_risk import make_service

    service, request, _ = make_service(tmp_path, strategy_registry_required=True)
    app.state.service = service
    body = request.model_dump(mode="json")
    for field, value in [
        ("strategy_registry_required", False),
        ("strategy_registry", {}),
        ("strategy_approval_check", {"state": "APPROVED"}),
    ]:
        response = client.post(
            "/assistant-api/evaluations/B/risk-decision",
            json=body | {field: value},
            headers=HEADERS,
        )
        assert response.status_code == 422
    response = client.post("/assistant-api/evaluations/B/risk-decision", json=body, headers=HEADERS)
    assert response.status_code == 200
    result = response.json()
    assert result["strategy_registry_required"] and result["allowed_contracts"] == 0
    assert (
        result["advice"] == "NO TRADE"
        and not result["trade_permitted"]
        and not result["execution_enabled"]
    )
    assert (
        client.post(
            "/assistant-api/strategy-registry/approve", json={}, headers=HEADERS
        ).status_code
        == 404
    )


def test_legacy_planner_cannot_bypass_strategy_registry_with_roles_disabled(
    client, tmp_path, monkeypatch
):
    from tests.unit.test_evaluation import plan as legacy_plan
    from tests.unit.test_evaluation_policy import NOW, policy_service

    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: NOW)
    service, _ = policy_service(tmp_path)
    service.account_roles_required = False
    service.strategy_registry_required = True
    app.state.service = service
    with service.store.connect() as db:
        db.execute("DELETE FROM settings WHERE key='account_plan'")
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: NOW)
    body = legacy_plan(account_value=25000).model_dump(mode="json")
    response = client.post("/assistant-api/evaluations/B/plan", json=body, headers=HEADERS)
    assert response.status_code == 400
    assert "strategy" in response.json()["detail"] and "NO TRADE" in response.json()["detail"]
    # A standalone worksheet remains arithmetic only when both scopes are off
    # and no durable strategy definition/account assignment exists.
    service.strategy_registry_required = False
    assert (
        client.post("/assistant-api/evaluations/B/plan", json=body, headers=HEADERS).status_code
        == 200
    )
    from tests.unit.test_strategy_registry import definition

    service.store.register_strategy(
        definition(),
        expected_revision=service.store.strategy_registry().revision,
        reason="Research experiment",
    )
    assert (
        client.post("/assistant-api/evaluations/B/plan", json=body, headers=HEADERS).status_code
        == 400
    )
