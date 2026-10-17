"""Synthetic persistence, concurrency and authenticated capture tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from api.advisor import app
from api.routes import research_journal as route
from connectors.advisory.research_journal import ResearchJournal
from connectors.advisory.storage import AdvisoryStore
from core.advisory.openterminal_context import TerminalSource
from core.advisory.openterminal_research import TerminalResearch
from core.advisory.research_journal import ResearchSnapshot
from core.config import settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)
WRITE = {"X-Advisory-Client": "dashboard"}


def report(symbol="AAPL", now=NOW):
    return TerminalResearch(
        symbol=symbol,
        assessed_at=now,
        sources=tuple(
            TerminalSource(kind=kind, state="unavailable", received_at=now)
            for kind in ("quotes", "history", "news")
        ),
    )


def snapshot(index=1, symbol="AAPL", now=NOW):
    return ResearchSnapshot(id=f"{index:032x}", saved_at=now, report=report(symbol, now))


@pytest.fixture
def journal(tmp_path):
    return ResearchJournal(AdvisoryStore(str(tmp_path / "journal.sqlite3")))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("j" * 48))
    monkeypatch.setattr(settings, "advisory_db_path", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(settings, "advisory_kafka_servers", "")
    monkeypatch.setattr(route, "utcnow", lambda: NOW)
    monkeypatch.setattr(route, "terminal_research", AsyncMock(return_value=report()))
    with TestClient(app, headers={"Authorization": "Bearer " + "j" * 48}) as value:
        yield value


def test_watchlist_is_durable_and_separate_from_futures(journal):
    before = journal.store.watchlist()
    for symbol in ["AAPL", "BTC-USD", "M&M.NS"]:
        journal.watch(symbol, True)
    reopened = ResearchJournal(AdvisoryStore(str(journal.store.path)))
    assert [r.symbol for r in reopened.watchlist()] == ["AAPL", "BTC-USD", "M&M.NS"]
    assert reopened.store.watchlist() == before


def test_unwatch_preserves_original_payload_and_source_clocks(journal):
    journal.watch("AAPL", True)
    saved = journal.save(snapshot())
    journal.watch("AAPL", False)
    assert journal.watchlist() == []
    assert journal.history("AAPL") == [saved]
    assert journal.history("MSFT") == []
    entry = journal.watch("AAPL", True)[0]
    assert entry.snapshots == 1 and entry.latest_saved_at == NOW


def test_retry_is_idempotent_and_cannot_replace_a_saved_report(journal):
    journal.watch("AAPL", True)
    first = journal.save(snapshot())
    later = snapshot(now=NOW + timedelta(seconds=5))
    assert journal.save(later) == first
    assert len(journal.history("AAPL")) == 1
    with pytest.raises(ValueError):
        journal.existing(first.id, "MSFT")


def test_concurrent_retries_have_one_durable_result(journal):
    journal.watch("AAPL", True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(journal.save, [snapshot()] * 3))
    assert results == [results[0]] * 3
    assert len(journal.history("AAPL")) == 1


def test_history_order_and_first_snapshot(journal):
    assert journal.history("AAPL") == []
    journal.watch("AAPL", True)
    a = journal.save(snapshot())
    b = journal.save(snapshot(2, now=NOW + timedelta(seconds=1)))
    assert journal.history("AAPL") == [b, a]
    with pytest.raises(ValueError):
        journal.save(snapshot(3, now=NOW - timedelta(seconds=1)))


def test_watch_limit_is_atomic_and_existing_symbol_remains_idempotent(journal):
    for i in range(50):
        journal.watch(f"SYM{i}", True)
    assert len(journal.watch("SYM0", True)) == 50
    with pytest.raises(ValueError):
        journal.watch("OVER", True)
    assert len(journal.watchlist()) == 50


def test_snapshot_limit_does_not_delete_history(journal):
    journal.watch("AAPL", True)
    for i in range(100):
        journal.save(snapshot(i))
    with pytest.raises(ValueError):
        journal.save(snapshot(101))
    assert len(journal.history("AAPL")) == 100


def test_unwatched_symbols_and_invalid_identity_are_rejected(journal):
    with pytest.raises(ValueError):
        journal.save(snapshot())
    for symbol in ["..", "AAPL,MSFT", "https://bad.test", "aapl"]:
        with pytest.raises(ValueError):
            journal.watch(symbol, True)


@pytest.mark.parametrize("offset", [-1, 90, 100])
def test_save_clock_must_follow_recent_assessment(offset):
    with pytest.raises(ValidationError):
        ResearchSnapshot(id="1" * 32, saved_at=NOW + timedelta(seconds=offset), report=report())


def test_corrupted_saved_identity_is_not_served(journal):
    journal.watch("AAPL", True)
    record = journal.save(snapshot())
    with journal.store.connect() as db:
        db.execute(
            "UPDATE research_snapshots SET payload=? WHERE id=?",
            (snapshot(symbol="MSFT").model_dump_json(), record.id),
        )
    with pytest.raises(ValueError):
        journal.history("AAPL")


def test_api_auth_and_write_header_are_required(client):
    assert (
        client.get(
            "/assistant-api/research-watchlist", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        client.put("/assistant-api/research-watchlist/AAPL", json={"watched": True}).status_code
        == 403
    )
    assert (
        client.post("/assistant-api/research-snapshots/AAPL", json={"id": "a" * 32}).status_code
        == 403
    )


def test_capture_uses_server_data_retry_and_history_api(client):
    path = "/assistant-api/research-snapshots/AAPL"
    assert client.post(path, headers=WRITE, json={"id": "a" * 32}).status_code == 409
    assert route.terminal_research.await_count == 0
    assert (
        client.put(
            "/assistant-api/research-watchlist/AAPL", headers=WRITE, json={"watched": True}
        ).status_code
        == 200
    )
    saved = client.post(path, headers=WRITE, json={"id": "a" * 32})
    assert saved.status_code == 200
    assert saved.json()["report"] == report().model_dump(mode="json")
    assert client.post(path, headers=WRITE, json={"id": "a" * 32}).json() == saved.json()
    assert route.terminal_research.await_count == 1
    history = client.get(path)
    assert history.json() == [saved.json()]
    assert history.headers["cache-control"] == "no-store"
    assert client.get("/assistant-api/research-watchlist").json()[0]["snapshots"] == 1


def test_capture_rejects_client_supplied_reports_and_cross_symbol_ids(client):
    client.put("/assistant-api/research-watchlist/AAPL", headers=WRITE, json={"watched": True})
    path = "/assistant-api/research-snapshots/AAPL"
    assert client.post(path, headers=WRITE, json={"id": "b" * 32, "report": {}}).status_code == 422
    client.post(path, headers=WRITE, json={"id": "b" * 32})
    assert (
        client.post(
            "/assistant-api/research-snapshots/MSFT", headers=WRITE, json={"id": "b" * 32}
        ).status_code
        == 409
    )


def test_capture_refuses_wrong_provider_symbol(client):
    client.put("/assistant-api/research-watchlist/AAPL", headers=WRITE, json={"watched": True})
    route.terminal_research.return_value = report("MSFT")
    response = client.post(
        "/assistant-api/research-snapshots/AAPL", headers=WRITE, json={"id": "d" * 32}
    )
    assert response.status_code == 502
    assert client.get("/assistant-api/research-snapshots/AAPL").json() == []


def test_bounded_overview_history_preserves_full_history(journal):
    journal.watch("AAPL", True)
    for index in range(4):
        journal.save(snapshot(index, now=NOW + timedelta(seconds=index)))
    full = journal.history("AAPL")
    assert journal.history("AAPL", limit=2) == full[:2]
    assert len(journal.history("AAPL")) == 4
    for limit in (0, -1, 101):
        with pytest.raises(ValueError):
            journal.history("AAPL", limit=limit)


def test_overview_history_api_limit_is_validated_and_read_only(client):
    client.put("/assistant-api/research-watchlist/AAPL", headers=WRITE, json={"watched": True})
    path = "/assistant-api/research-snapshots/AAPL"
    for index in range(3):
        assert client.post(path, headers=WRITE, json={"id": f"{index:032x}"}).status_code == 200
    full = client.get(path).json()
    assert client.get(path + "?limit=2").json() == full[:2]
    assert client.get(path).json() == full
    assert route.terminal_research.await_count == 3
    for limit in ("0", "101", "-1", "x"):
        assert client.get(path + "?limit=" + limit).status_code == 422
