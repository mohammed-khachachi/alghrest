"""Research-only backups, exact payload preservation, atomic merges and protected API."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from pydantic import SecretStr

from api import advisor
from api.routes import research_journal as route
from connectors.advisory.research_backup import export_research, restore_research
from connectors.advisory.research_journal import ResearchJournal
from connectors.advisory.storage import AdvisoryStore
from core.advisory.openterminal_context import TerminalSource
from core.advisory.openterminal_research import TerminalResearch
from core.advisory.research_backup import backup_checksum, read_backup
from core.advisory.research_journal import ResearchSnapshot
from core.config import settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 16, 12, tzinfo=UTC)


def journal(tmp_path, name="source"):
    return ResearchJournal(AdvisoryStore(str(tmp_path / f"{name}.sqlite3")))


def save(journal, index=1, symbol="AAPL"):
    journal.watch(symbol, True)
    r = TerminalResearch(
        symbol=symbol,
        assessed_at=NOW,
        sources=tuple(
            TerminalSource(kind=k, state="unavailable", received_at=NOW)
            for k in ("quotes", "history", "news")
        ),
    )
    value = ResearchSnapshot(id=f"{index:032x}", saved_at=NOW, report=r)
    journal.save(value)
    return value


def payloads(journal):
    with journal.store.connect() as db:
        return db.execute(
            "SELECT id,symbol,saved,payload FROM research_snapshots ORDER BY id"
        ).fetchall()


def rehash(value):
    value["sha256"] = backup_checksum({k: v for k, v in value.items() if k != "sha256"})
    return json.dumps(value).encode()


def test_backup_excludes_account_tables_and_keeps_unwatched_history(tmp_path):
    source = journal(tmp_path)
    save(source)
    source.watch("AAPL", False)
    with source.store.connect() as db:
        db.execute(
            "INSERT INTO settings VALUES(?,?)", ("private-fixture", "DO_NOT_EXPORT_PRIVATE_FIXTURE")
        )
    raw = export_research(source, NOW)
    assert b"DO_NOT_EXPORT_PRIVATE_FIXTURE" not in raw
    backup = read_backup(raw, NOW)
    assert backup.watches == () and len(backup.snapshots) == 1
    assert backup.snapshots[0].payload == payloads(source)[0][3]


def test_restore_is_exact_idempotent_and_marks_imported_evidence_without_changing_payload(tmp_path):
    source = journal(tmp_path)
    record = save(source)
    raw = export_research(source, NOW)
    target = journal(tmp_path, "restored")
    preview = restore_research(target, raw, NOW, preview=True)
    assert preview["snapshots_added"] == 1 and not payloads(target) and target.watchlist() == []
    result = restore_research(target, raw, NOW)
    assert result == preview and payloads(source) == payloads(target)
    restored = target.history("AAPL")[0]
    assert restored.report == record.report and restored.saved_at == record.saved_at
    assert restored.restored_from_backup == read_backup(raw, NOW).sha256
    assert target.existing(record.id, "AAPL").restored_from_backup == restored.restored_from_backup
    assert (
        target.brief(now=NOW).entries[0].snapshots[0].restored_from_backup
        == restored.restored_from_backup
    )
    repeat = restore_research(target, raw, NOW + timedelta(days=1))
    assert (
        repeat["snapshots_added"] == repeat["watches_added"] == 0
        and repeat["snapshots_unchanged"] == 1
    )
    assert payloads(source) == payloads(target)


def test_conflicting_identity_rolls_back_every_new_record_and_watch(tmp_path):
    source = journal(tmp_path)
    save(source)
    save(source, 2, "MSFT")
    target = journal(tmp_path, "target")
    save(target, 2, "QQQ")
    old = payloads(target)
    old_watches = target.watchlist()
    with pytest.raises(ValueError, match="conflict"):
        restore_research(target, export_research(source, NOW), NOW)
    assert payloads(target) == old and target.watchlist() == old_watches


@pytest.mark.parametrize(
    "defect", ["checksum", "permission", "identity", "clock", "extra", "future"]
)
def test_corrupt_or_inconsistent_backups_are_rejected_before_any_write(tmp_path, defect):
    source = journal(tmp_path)
    save(source)
    value = json.loads(export_research(source, NOW))
    if defect == "checksum":
        value["sha256"] = "0" * 64
    elif defect == "permission":
        r = json.loads(value["snapshots"][0]["payload"])
        r["report"]["execution_enabled"] = True
        value["snapshots"][0]["payload"] = json.dumps(r)
    elif defect == "identity":
        value["snapshots"][0]["symbol"] = "MSFT"
    elif defect == "clock":
        value["snapshots"][0]["stored_saved"] = (NOW + timedelta(seconds=1)).isoformat()
    elif defect == "extra":
        value["unexpected_account_data"] = {"fixture": 1}
    else:
        value["created_at"] = (NOW + timedelta(days=1)).isoformat().replace("+00:00", "Z")
    raw = json.dumps(value).encode() if defect == "checksum" else rehash(value)
    target = journal(tmp_path, "target")
    with pytest.raises(ValueError):
        restore_research(target, raw, NOW)
    assert payloads(target) == [] and target.watchlist() == []


def test_merged_limits_and_oversized_files_fail_without_deleting_existing_research(
    tmp_path, monkeypatch
):
    from core.advisory import research_backup as core

    source = journal(tmp_path)
    save(source)
    raw = export_research(source, NOW)
    target = journal(tmp_path, "target")
    for n in range(50):
        target.watch(f"S{n}", True)
    with pytest.raises(ValueError, match="limits"):
        restore_research(target, raw, NOW)
    assert len(target.watchlist()) == 50 and payloads(target) == []
    monkeypatch.setattr(core, "MAX_BACKUP_BYTES", 10)
    with pytest.raises(ValueError, match="32 MiB"):
        read_backup(raw, NOW)


def test_raw_legacy_json_is_not_normalized_by_backup_restore(tmp_path):
    source = journal(tmp_path)
    save(source)
    with source.store.connect() as db:
        original = json.loads(db.execute("SELECT payload FROM research_snapshots").fetchone()[0])
        original.pop("restored_from_backup")
        original["report"].pop("data_quality")
        raw_original = json.dumps(original, indent=3)
        db.execute("UPDATE research_snapshots SET payload=?", (raw_original,))
    target = journal(tmp_path, "legacy")
    restore_research(target, export_research(source, NOW), NOW)
    assert payloads(target)[0][3] == raw_original
    assert target.history("AAPL")[0].report.data_quality is None


async def test_backup_api_auth_preview_restore_and_body_limits(tmp_path, monkeypatch):
    source = journal(tmp_path)
    save(source)
    raw = export_research(source, NOW)
    target = journal(tmp_path, "api")
    monkeypatch.setattr(route, "utcnow", lambda: NOW)
    monkeypatch.setattr(
        settings, "advisory_access_token", SecretStr("synthetic_backup_" + "x" * 32)
    )
    monkeypatch.setattr(
        advisor.app.state, "service", SimpleNamespace(store=target.store), raising=False
    )
    headers = {
        "Authorization": "Bearer synthetic_backup_" + "x" * 32,
        "X-Advisory-Client": "dashboard",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=advisor.app), base_url="http://testserver"
    ) as client:
        assert (await client.get("/assistant-api/research-backup")).status_code == 401
        assert (
            await client.post("/assistant-api/research-backup/restore", content=raw)
        ).status_code == 401
        no_client = {k: v for k, v in headers.items() if k != "X-Advisory-Client"}
        assert (
            await client.post(
                "/assistant-api/research-backup/restore", content=raw, headers=no_client
            )
        ).status_code == 403
        preview = await client.post(
            "/assistant-api/research-backup/preview", content=raw, headers=headers
        )
        assert (
            preview.status_code == 200
            and preview.json()["snapshots_added"] == 1
            and not payloads(target)
        )
        restored = await client.post(
            "/assistant-api/research-backup/restore", content=raw, headers=headers
        )
        assert restored.status_code == 200 and restored.json()["snapshots_added"] == 1
        download = await client.get("/assistant-api/research-backup", headers=headers)
        assert download.status_code == 200 and download.headers["cache-control"] == "no-store"
        assert len(read_backup(download.content, NOW + timedelta(days=100)).snapshots) == 1
        monkeypatch.setattr(advisor, "MAX_BACKUP_BYTES", 1000)
        assert (
            await client.post(
                "/assistant-api/research-backup/preview", content=b"x" * 1001, headers=headers
            )
        ).status_code == 413
        assert payloads(source) == payloads(target)
