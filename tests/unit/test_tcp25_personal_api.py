"""Versioned personal API and server-side legacy retirement; no services."""

from unittest.mock import AsyncMock, Mock

import pytest

from api.advisor import app
from core.config import settings
from tests.unit import test_advisory_api
from tests.unit.test_tcp25_personal import NOW, context, identity, plan

client = test_advisory_api.client

pytestmark = pytest.mark.unit
HEADERS = {"X-Advisory-Client": "dashboard"}


@pytest.mark.parametrize(
    "path",
    [
        "/assistant-api/briefings",
        "/assistant-api/briefings/",
        "/assistant-api/briefings?schema_version=2",
    ],
)
def test_legacy_briefing_post_stops_before_workflow(client, monkeypatch, path):
    forbidden = Mock(side_effect=AssertionError("workflow must not be constructed"))
    context = AsyncMock(side_effect=AssertionError("context must not be collected"))
    monkeypatch.setattr("api.routes.advisory_briefings._workflow", forbidden)
    monkeypatch.setattr("api.services.briefings.collect_context", context)
    monkeypatch.setattr("api.services.briefings.build_briefing", forbidden)
    monkeypatch.setattr("core.advisory.briefing.assess_user_policy", forbidden)
    monkeypatch.setattr("connectors.advisory.briefing_store.BriefingStore.save", forbidden)
    monkeypatch.setattr(app.state.service.client, "request", context)
    monkeypatch.setattr(app.state.service.store, "evaluation", forbidden)
    response = client.post(path, content=b"not JSON", headers=HEADERS, follow_redirects=False)
    assert response.status_code == 409
    assert response.headers["cache-control"] == "no-store"
    forbidden.assert_not_called()
    context.assert_not_called()


@pytest.mark.parametrize("profile", ["general", "earn2trade_tcp25", "earn2trade_tcp50"])
@pytest.mark.parametrize(
    "path",
    [
        "/assistant-api/briefings//",
        "/assistant-api/%62riefings",
        "/assistant-api/briefings?confirmed=true",
    ],
)
def test_legacy_creation_has_no_profile_or_path_bypass(client, monkeypatch, profile, path):
    monkeypatch.setattr(settings, "operating_profile", profile)
    assert (
        client.post(
            path,
            json={"schema_version": 2, "evaluation_id": "different"},
            headers=HEADERS,
            follow_redirects=False,
        ).status_code
        == 409
    )


@pytest.mark.parametrize("path", ["/mounted/assistant-api/briefings/", "/assistant-api/briefings"])
def test_mounted_path_creation_cannot_bypass_guard(client, path):
    from fastapi.testclient import TestClient

    with TestClient(app, root_path="/mounted", headers=client.headers) as mounted:
        assert (
            mounted.post(path, headers=HEADERS, json={}, follow_redirects=False).status_code == 409
        )


def test_guard_keeps_auth_header_enforcement_and_never_buffers_body(client, monkeypatch):
    async def forbidden_stream(_self):
        raise AssertionError("Retired request must not buffer a body")
        yield b""  # pragma: no cover

    monkeypatch.setattr("starlette.requests.Request.stream", forbidden_stream)
    for body in [b"", b"{bad JSON", b"x" * 500001]:
        assert (
            client.post("/assistant-api/briefings", headers=HEADERS, content=body).status_code
            == 409
        )
    assert client.post("/assistant-api/briefings", json={}).status_code == 403
    assert (
        client.post(
            "/assistant-api/briefings", headers=HEADERS | {"Authorization": "Bearer wrong"}, json={}
        ).status_code
        == 401
    )


@pytest.fixture
def account(client, monkeypatch):
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: NOW)
    app.state.service.clock = lambda: NOW
    p, rows = context()
    app.state.service.store.create_evaluation(p)
    for row in rows:
        app.state.service.store.save_session(p.id, row)
    return p, rows


def test_tcp25_endpoints_calculate_personal_only_without_writes(client, account):
    p, rows = account
    before = app.state.service.store.evaluation(p.id)
    rules = client.get("/assistant-api/tcp25/personal/rules").json()
    assert rules["schema_version"] == 2 and rules["result"]["daily_loss_limit"] == "550"
    base = f"/assistant-api/tcp25/personal/evaluations/{p.id}"
    status = client.get(base + "/status").json()
    body = identity(p, rows) | dict(instrument_id="MES", contract="MESZ26", additional_contracts=10)
    cap = client.post(base + "/capacity", headers=HEADERS, json=body)
    assert cap.status_code == 200 and cap.json()["result"]["remaining_micro_contracts"] == 10
    response = client.post(
        base + "/plan", headers=HEADERS, json=plan(p, rows).request.model_dump(mode="json")
    )
    assert response.status_code == 200
    assert response.json()["result"]["personal_contracts"] == 2
    assert response.json()["result"]["qualified_contracts"] == 0
    assert status["result"]["firm_eligibility"] == "BLOCKED"
    assert app.state.service.store.evaluation(p.id) == before


def test_tcp25_revision_auth_missing_and_invalid_requests(client, account):
    p, rows = account
    base = f"/assistant-api/tcp25/personal/evaluations/{p.id}/capacity"
    body = identity(p, rows) | dict(instrument_id="MES", contract="MESZ26", additional_contracts=1)
    assert client.post(base, json=body).status_code == 403
    assert (
        client.post(
            base, headers=HEADERS | {"Authorization": "Bearer wrong"}, json=body
        ).status_code
        == 401
    )
    assert (
        client.post(
            base, headers=HEADERS, json=body | {"expected_account_revision": "0" * 64}
        ).status_code
        == 409
    )
    assert client.post(base, headers=HEADERS, json=body | {"schema_version": 1}).status_code == 422
    assert (
        client.post(base, headers=HEADERS, json=body | {"additional_contracts": 11}).status_code
        == 422
    )
    assert client.get("/assistant-api/tcp25/personal/evaluations/missing/status").status_code == 404


@pytest.mark.parametrize("age", [1799, 1800, 1801])
@pytest.mark.parametrize("endpoint", ["capacity", "plan"])
def test_api_never_returns_positive_capacity_with_nonpositive_lifetime(
    client, account, age, endpoint
):
    from datetime import datetime, timedelta

    p, rows = account
    generated = NOW + timedelta(seconds=age)
    app.state.service.clock = lambda: generated
    body = (
        (identity(p, rows) | dict(instrument_id="MES", contract="MESZ26", additional_contracts=1))
        if endpoint == "capacity"
        else plan(p, rows).request.model_dump(mode="json")
    )
    response = client.post(
        f"/assistant-api/tcp25/personal/evaluations/{p.id}/{endpoint}", headers=HEADERS, json=body
    )
    assert response.status_code == 200
    data = response.json()
    positive = data["result"]["state"] in {"WITHIN_CAP", "CALCULATED"}
    assert positive is (age < 1800)
    if positive:
        assert datetime.fromisoformat(data["result"]["expires_at"]) > datetime.fromisoformat(
            data["generated_at"]
        )
    else:
        assert "personal_capacity_expired" in data["result"]["reasons"]
