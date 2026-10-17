"""Per-symbol diagnostics are bounded, authenticated, identity-checked observations."""

from datetime import UTC, datetime

import httpx
import pytest

from connectors.advisory.research_diagnostics import collect_diagnostics

pytestmark = pytest.mark.unit
STAMP = datetime.now(UTC).isoformat()


def payload():
    return {
        "schema_version": "research-diagnostics-v1",
        "symbol": "^VIX",
        "assessed_at": STAMP,
        "started_at": STAMP,
        "scope": "process_memory",
        "observations": [
            {
                "symbol": "^VIX",
                "feed": "history",
                "provider": "yahoo",
                "state": "available",
                "last_attempt": STAMP,
                "last_success": STAMP,
                "last_failure": None,
                "failure": None,
                "http_status": None,
                "clock": None,
            }
        ],
    }


@pytest.mark.asyncio
async def test_fixed_local_endpoint_without_forwarded_credentials():
    def handle(request):
        assert request.url.host == "127.0.0.1"
        assert request.url.port == 4001
        assert request.url.path == "/api/research-diagnostics/^VIX"
        assert "authorization" not in request.headers
        return httpx.Response(200, json=payload())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await collect_diagnostics(client, "^VIX")
    assert result.state == "available"
    assert result.diagnostics.observations[0].provider == "yahoo"


@pytest.mark.parametrize(
    "change", ["symbol", "future", "duplicate", "raw_error", "clock", "missing_success"]
)
@pytest.mark.asyncio
async def test_invalid_diagnostics_never_pass_to_ui(change):
    data = payload()
    row = data["observations"][0]
    if change == "symbol":
        data["symbol"] = "AAPL"
    elif change == "future":
        data["assessed_at"] = "2099-01-01T00:00:00Z"
    elif change == "duplicate":
        data["observations"].append(dict(row))
    elif change == "raw_error":
        row["failure"] = "token=SECRET"
    elif change == "clock":
        row["clock"] = {"basis": "ticker_window_close", "value": STAMP}
    else:
        row["last_success"] = None
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))
    ) as client:
        result = await collect_diagnostics(client, "^VIX")
    assert result.state == "invalid"
    assert result.diagnostics is None
    assert "SECRET" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_failed_or_large_response_is_explicit_and_sanitized():
    for response in [
        httpx.Response(502, text="token=SECRET"),
        httpx.Response(200, content=b"x" * 256001),
    ]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _, response=response: response)
        ) as client:
            result = await collect_diagnostics(client, "^VIX")
        assert result.state in {"unavailable", "invalid"}
        assert result.diagnostics is None
        assert "SECRET" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_diagnostic_route_auth_no_store_and_symbol_validation(monkeypatch):
    from pydantic import SecretStr

    from api.advisor import app
    from connectors.advisory import research_diagnostics as adapter
    from core.advisory.research_diagnostics import DiagnosticResult
    from core.config import settings

    calls = []

    async def fake(_client, symbol):
        calls.append(symbol)
        return DiagnosticResult(symbol=symbol, checked_at=datetime.now(UTC), state="unavailable")

    monkeypatch.setattr(
        settings, "advisory_access_token", SecretStr("synthetic_diagnostic_test_" + "x" * 32)
    )
    monkeypatch.setattr(adapter, "collect_diagnostics", fake)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/assistant-api/research-diagnostics/BTC")).status_code == 401
        headers = {"Authorization": "Bearer " + settings.advisory_access_token.get_secret_value()}
        response = await client.get("/assistant-api/research-diagnostics/BTC", headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["state"] == "unavailable"
        assert (
            await client.get("/assistant-api/research-diagnostics/..", headers=headers)
        ).status_code != 200
    assert calls == ["BTC"]
