"""Long observation fails visibly on gaps/boundary changes and preserves provenance."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from pydantic import SecretStr

from core.advisory.openterminal_context import TerminalSource
from core.advisory.openterminal_research import QuoteObservation, ResearchQuote, TerminalResearch
from scripts import monitor_research as monitor

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 16, 14, tzinfo=UTC)


def report():
    return TerminalResearch(
        symbol="BTC",
        assessed_at=NOW,
        sources=tuple(
            TerminalSource(
                kind=k,
                state="available" if k == "quotes" else "unavailable",
                received_at=NOW,
                response_sha256="a" * 64 if k == "quotes" else None,
            )
            for k in ("quotes", "history", "news")
        ),
        quote=ResearchQuote(
            symbol="BTC",
            price=100,
            currency="USD",
            provider="binance",
            market_state="Open",
            observation=QuoteObservation(
                schema_version="quote-observation-v1",
                fetched_at=NOW,
                cache_state="fetched",
                market_state_basis="UNVERIFIED",
            ),
        ),
    )


@pytest.mark.parametrize("seconds", [-1, 300.001, 301, 3600])
def test_invalid_gap_never_passes(seconds):
    with pytest.raises(RuntimeError):
        monitor.sample_gap(NOW, NOW + timedelta(seconds=seconds))


def test_gap_boundaries_and_first_sample():
    assert monitor.sample_gap(None, NOW) == 0
    assert monitor.sample_gap(NOW, NOW + timedelta(seconds=300)) == 300


def test_assumed_crypto_session_does_not_count_as_a_provider_report():
    value = monitor.reading(report(), NOW, 1)
    assert value["current_provider_session"] == "unknown"
    assert value["provider_session_recent"] is False
    assert value["quote_context"]["status"] == "unknown"
    assert value["quote"]["observation"]["fetched_at"] == "2026-10-16T14:00:00Z"
    assert value["sources"]["history"] == "unavailable" and value["freshness_certified"] is False


def test_old_or_future_report_is_rejected():
    for seconds in [-1, 90, 100]:
        with pytest.raises(RuntimeError):
            monitor.reading(report(), NOW + timedelta(seconds=seconds), 1)


async def test_only_assistant_receives_the_credential():
    seen = []

    def respond(request):
        seen.append(request)
        if request.url.port == 8011:
            body = {
                "service": "manual-research",
                "execution_enabled": False,
                "agent_tap_enabled": False,
            }
        else:
            body = {"integration": "alghrest-research", "execution_enabled": False, "ai": False}
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(respond), headers={"Authorization": "do-not-forward"}
    ) as client:
        await monitor.health(client, "synthetic-secret")
    assert len(seen) == 4
    for request in seen:
        assert request.headers["Authorization"] == (
            "Bearer synthetic-secret" if request.url.port == 8011 else ""
        )


@pytest.mark.parametrize("fault", ["execution", "agent", "identity", "ai", "unavailable"])
async def test_service_failures_and_changed_boundaries_abort(fault):
    def respond(request):
        assistant = request.url.port == 8011
        body = {
            "execution_enabled": False,
            "agent_tap_enabled": False,
            "service": "manual-research",
            "ai": False,
            "integration": "alghrest-research",
        }
        if fault == "execution":
            body["execution_enabled"] = True
        if fault == "agent" and assistant:
            body["agent_tap_enabled"] = True
        if fault == "identity" and assistant:
            body["service"] = "different"
        if fault == "ai" and not assistant:
            body["ai"] = True
        return httpx.Response(503 if fault == "unavailable" else 200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(RuntimeError):
            await monitor.health(client, "fixture")


def test_evidence_size_bound_preserves_existing_bytes(tmp_path, monkeypatch):
    file = tmp_path / "events.jsonl"
    monitor.append_json(file, {"first": True})
    before = file.read_bytes()
    monkeypatch.setattr(monitor, "MAX_LOG_BYTES", len(before) + 1)
    with pytest.raises(RuntimeError):
        monitor.append_json(file, {"large": "x" * 100})
    assert file.read_bytes() == before
    with pytest.raises(RuntimeError):
        monitor.append_json(tmp_path / "new.jsonl", {"large": "x" * 100})
    assert not (tmp_path / "new.jsonl").exists()


async def test_source_change_preserves_failure_receipt_without_http_or_restart(
    tmp_path, monkeypatch
):
    values = iter([{"source": "old"}, {"source": "new"}])
    monkeypatch.setattr(monitor, "source_manifest", lambda: next(values))
    monkeypatch.setattr(monitor.settings, "advisory_access_token", SecretStr("fixture"))
    output = tmp_path / "run"
    with pytest.raises(SystemExit):
        await monitor.run(0.001, 1, ["BTC"], output)
    receipt = json.loads((output / "verification.json").read_text())
    assert receipt["status"] == "failed" and receipt["cycles"] == 0
    assert "source changed" in receipt["failure"]
    with pytest.raises(FileExistsError):
        await monitor.run(0.001, 1, ["BTC"], output)
