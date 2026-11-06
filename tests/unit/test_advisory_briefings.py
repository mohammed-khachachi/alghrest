"""Synthetic mechanics only: joined evidence never qualifies a trade."""

import asyncio
import json
import threading
import time
from contextlib import contextmanager
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from api.advisor import app
from api.services.briefings import BriefingWorkflow
from connectors.advisory.briefing_store import (
    BriefingConflictError,
    BriefingSaveGuard,
    BriefingStore,
    guarded_briefing_save,
)
from connectors.advisory.observation_store import ObservationStore
from connectors.advisory.storage import AdvisoryStore
from core.advisory.briefing import (
    Briefing,
    BriefingInputs,
    BriefingRequest,
    build_briefing,
    verify_briefing,
)
from core.advisory.news_context import build_context
from core.advisory.user_risk import personal_account_status
from core.config import settings
from tests.unit.test_advisory_observations import packet
from tests.unit.test_user_policy import NOW, context

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr("core.advisory.evaluation.utcnow", lambda: NOW)


def raw(**changes):
    p = packet()
    for frame in p["frames"]:
        frame.update(
            captured_at=NOW.isoformat(),
            observed_at=NOW.isoformat(),
            last_closed_bar_at=(NOW - timedelta(minutes=5)).isoformat(),
        )
    p.update(changes)
    return json.dumps(p)


def joined(store, **changes):
    p, sessions = context()
    store.create_evaluation(p)
    for row in sessions:
        store.save_session(p.id, row)
    observations = ObservationStore(store)
    observation = observations.save(raw(), observation_id=None, expected_revision=None, now=NOW)
    observation = observations.review(
        observation.record.id, expected_revision=observation.record.revision, now=NOW
    )
    inputs = BriefingInputs.model_validate(
        dict(
            assessed_at=NOW,
            observation=observation,
            profile=p,
            sessions=tuple(sessions),
            context=build_context("MES", [], [], [], [], now=NOW),
            interests=(),
            agent_tap_enabled=False,
            agent_records=(),
        )
        | changes
    )
    request = BriefingRequest(
        observation_id=observation.record.id,
        observation_revision=observation.record.revision,
        evaluation_id=p.id,
        account_revision=personal_account_status(p, sessions, now=NOW)["account_revision"],
    )
    return inputs, request


@pytest.fixture
def store(tmp_path):
    return AdvisoryStore(str(tmp_path / "assistant.sqlite3"))


def test_joined_report_is_reproducible_and_keeps_financial_arithmetic(store):
    inputs, _ = joined(store)
    value = build_briefing(inputs)
    assert (
        verify_briefing(value) == value
        and Briefing.model_validate_json(value.model_dump_json()) == value
    )
    assert value.result.state == "REVIEWABLE" and value.result.decision == "WAIT"
    assert (
        value.result.account_status["balance"] == "50000"
        and value.result.account_status["daily_loss_remaining"] == "1100"
    )
    assert value.result.cap.remaining_micro_contracts == 20
    assert value.result.trade_permitted is value.result.execution_enabled is False
    assert (
        value.result.context.event_risk == "UNKNOWN"
        and value.result.passing_probability == "UNKNOWN"
    )
    assert all(
        c.state == "DISABLED" for c in value.result.capabilities if c.name.startswith("agent_")
    )


@pytest.mark.parametrize(
    "changed",
    [
        {"decision": "BUY"},
        {"trade_permitted": True},
        {"execution_enabled": True},
        {"passing_probability": "95%"},
        {"frame_comparison": "SAME_TIME_CONFLICT"},
    ],
)
def test_forged_or_reconstructed_results_rejected(store, changed):
    inputs, _ = joined(store)
    value = build_briefing(inputs)
    data = value.model_dump()
    data["result"].update(changed)
    with pytest.raises(ValidationError):
        Briefing.model_validate(data)


def test_whole_source_hash_mismatch_is_never_patched(store):
    inputs, _ = joined(store)
    value = build_briefing(inputs)
    data = value.model_dump()
    key = next(iter(data["source_hashes"]))
    data["source_hashes"][key] = "0" * 64
    with pytest.raises(ValueError, match="source hashes differ"):
        Briefing.model_validate(data)
    detached = value.model_copy(update={"source_hashes": {}})
    with pytest.raises(ValueError):
        verify_briefing(detached)


def test_stale_price_and_unreviewed_record_never_become_eligible(store):
    inputs, _ = joined(store)
    older = inputs.model_copy(update={"assessed_at": NOW + timedelta(minutes=15)})
    value = build_briefing(older)
    assert value.result.state == "INCOMPLETE" and "5m:stale_price" in value.result.reasons
    missing = inputs.observation.model_copy(update={"reviewed_at": None})
    value = build_briefing(inputs.model_copy(update={"observation": missing}))
    assert value.result.state == "INCOMPLETE"
    assert value.result.decision == "WAIT"


def test_same_time_conflict_and_different_frame_times_are_distinct(store):
    inputs, _ = joined(store)
    data = json.loads(raw())
    f = dict(data["frames"][0])
    f.update(image_id="second", interval="15m", last="6000.50")
    data["frames"].append(f)
    os = ObservationStore(store)
    v = os.save(json.dumps(data), observation_id=None, expected_revision=None, now=NOW)
    v = os.review(v.record.id, expected_revision=v.record.revision, now=NOW)
    result = build_briefing(inputs.model_copy(update={"observation": v})).result
    assert result.frame_comparison == "SAME_TIME_CONFLICT" and result.decision == "NO_TRADE"
    data["frames"][1]["observed_at"] = (NOW - timedelta(minutes=1)).isoformat()
    v = os.save(
        json.dumps(data), observation_id=v.record.id, expected_revision=v.record.revision, now=NOW
    )
    v = os.review(v.record.id, expected_revision=v.record.revision, now=NOW)
    result = build_briefing(inputs.model_copy(update={"observation": v})).result
    assert result.frame_comparison == "NOT_COMPARABLE" and result.decision == "WAIT"


def test_context_instrument_or_review_clock_forgery_rejected(store):
    inputs, _ = joined(store)
    with pytest.raises(ValueError):
        build_briefing(
            inputs.model_copy(update={"context": build_context("MNQ", [], [], [], [], now=NOW)})
        )
    view = inputs.observation.model_copy(update={"reviewed_at": NOW + timedelta(seconds=1)})
    with pytest.raises(ValueError):
        build_briefing(inputs.model_copy(update={"observation": view}))


@pytest.mark.parametrize(
    "root,stamp,topic,enabled,expected",
    [
        ("MES", NOW, "news.tagged", True, 1),
        ("MNQ", NOW, "news.tagged", True, 0),
        ("MES", NOW - timedelta(hours=2), "news.tagged", True, 0),
        ("MES", NOW + timedelta(seconds=1), "news.tagged", True, 0),
        ("MES", NOW, "orders.pending", True, 0),
        ("MES", NOW, "news.tagged", False, 0),
    ],
)
def test_agent_context_is_related_causal_readonly_and_not_a_signal(
    store, root, stamp, topic, enabled, expected
):
    inputs, _ = joined(store)
    row = {
        "id": "a" * 64,
        "topic": topic,
        "timestamp": stamp.isoformat(),
        "symbol": root,
        "affected_symbols": "[]",
        "summary": '{"ready":true,"direction":"BUY","confidence":100}',
    }
    value = build_briefing(
        inputs.model_copy(update={"agent_tap_enabled": enabled, "agent_records": (row,)})
    )
    assert len(value.result.agent_context) == expected
    assert value.result.decision == "WAIT" and value.result.trade_permitted is False


def test_bad_or_missing_intelligence_cannot_activate_capability(store):
    inputs, _ = joined(store)
    for row in (
        {"summary": "broken"},
        {
            "id": "a" * 64,
            "topic": "news.tagged",
            "timestamp": NOW.isoformat(),
            "symbol": "MES",
            "affected_symbols": "{}",
            "summary": "{}",
        },
    ):
        value = build_briefing(
            inputs.model_copy(update={"agent_tap_enabled": True, "agent_records": (row,)})
        )
        assert not value.result.agent_context and "invalid_agent_record" in value.result.reasons


def test_append_only_history_reopen_and_changed_inputs_warning(store):
    inputs, request = joined(store)
    bs = BriefingStore(store)
    value = build_briefing(inputs)
    saved = bs.save(value, request, now=NOW)
    assert saved.record == value and len(bs.history()) == 1
    fresh = BriefingStore(store)
    assert fresh.read(value.id, now=NOW + timedelta(minutes=6)).record == value
    assert (
        "historical_context_not_current"
        in fresh.read(value.id, now=NOW + timedelta(minutes=6)).current_warnings
    )
    os = ObservationStore(store)
    os.save(
        raw(source_reference="corrected synthetic"),
        observation_id=request.observation_id,
        expected_revision=request.observation_revision,
        now=NOW,
    )
    assert "current_inputs_changed" in bs.read(value.id, now=NOW).current_warnings
    with pytest.raises(BriefingConflictError):
        bs.save(build_briefing(inputs), request, now=NOW)
    assert len(bs.history()) == 1


def test_account_changes_and_request_mismatch_block_commit(store):
    inputs, request = joined(store)
    bs = BriefingStore(store)
    value = build_briefing(inputs)
    with pytest.raises(ValueError):
        bs.save(value, request.model_copy(update={"evaluation_id": "other"}), now=NOW)
    changed = inputs.sessions[0].model_copy(update={"notes": "new saved state"})
    store.save_session(inputs.profile.id, changed)
    with pytest.raises(BriefingConflictError):
        bs.save(value, request, now=NOW)
    assert not bs.history()


def test_saved_record_tampering_and_future_reopen_rejected(store):
    inputs, request = joined(store)
    bs = BriefingStore(store)
    value = build_briefing(inputs)
    bs.save(value, request, now=NOW)
    with pytest.raises(ValueError):
        bs.read(value.id, now=NOW - timedelta(seconds=1))
    with store.connect() as db:
        altered = value.model_dump()
        altered["result"]["account_status"]["balance"] = "999999"
        db.execute(
            "UPDATE evaluation_briefings SET payload=? WHERE id=?",
            (json.dumps(altered, default=str), value.id),
        )
    with pytest.raises(ValueError):
        bs.read(value.id, now=NOW)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("r" * 48))
    monkeypatch.setattr(settings, "advisory_db_path", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(settings, "advisory_kafka_servers", "")
    with TestClient(app, headers={"Authorization": "Bearer " + "r" * 48}) as client:
        monkeypatch.setattr(app.state.service, "clock", lambda: NOW)
        inputs, request = joined(app.state.service.store)

        async def captured(_service, _calendars, _root):
            return inputs.context, []

        monkeypatch.setattr("api.services.briefings.collect_context", captured)
        yield client, inputs, request


def test_api_create_read_history_auth_and_no_price_or_order_path(api_client, monkeypatch):
    client, inputs, request = api_client
    forbidden = AsyncMock(side_effect=AssertionError("price/report path must not run"))
    monkeypatch.setattr(app.state.service, "report", forbidden)
    response = client.post(
        "/assistant-api/briefings",
        json=request.model_dump(),
        headers={"X-Advisory-Client": "dashboard"},
    )
    assert response.status_code == 409, response.text
    saved = BriefingStore(app.state.service.store).save(build_briefing(inputs), request, now=NOW)
    value = saved.model_dump(mode="json")
    identifier = value["record"]["id"]
    assert value["trade_permitted"] is False
    assert (
        client.get("/assistant-api/briefings/" + identifier).status_code == 200
        and len(client.get("/assistant-api/briefings").json()) == 1
    )
    assert not forbidden.called
    assert (
        client.get(
            "/assistant-api/briefings", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/assistant-api/orders", json={}, headers={"X-Advisory-Client": "dashboard"}
        ).status_code
        == 404
    )
    assert client.get("/assistant-api/briefings/missing").status_code == 404
    assert (
        client.post(
            "/assistant-api/briefings",
            json=request.model_dump() | {"confirmed": True},
            headers={"X-Advisory-Client": "dashboard"},
        ).status_code
        == 409
    )
    assert app.state.service.store.evaluation(inputs.profile.id) == (
        inputs.profile,
        list(inputs.sessions),
    )


async def test_api_race_during_source_fetch_leaves_no_briefing(api_client, monkeypatch):
    client, inputs, request = api_client

    async def changed(_service, _calendars, _root):
        store = app.state.service.store
        store.save_session(
            inputs.profile.id,
            inputs.sessions[0].model_copy(update={"notes": "changed while fetching"}),
        )
        return inputs.context, []

    monkeypatch.setattr("api.services.briefings.collect_context", changed)
    from api.routes import advisory_briefings as route

    with pytest.raises(HTTPException) as caught:
        await route.create(request, SimpleNamespace(app=app))
    assert caught.value.status_code == 409 and client.get("/assistant-api/briefings").json() == []


def test_api_unreviewed_or_stale_selected_revision_is_rejected(api_client):
    client, _, request = api_client
    os = ObservationStore(app.state.service.store)
    latest = os.save(
        raw(),
        observation_id=request.observation_id,
        expected_revision=request.observation_revision,
        now=NOW,
    )
    for revision in (request.observation_revision, latest.record.revision):
        r = client.post(
            "/assistant-api/briefings",
            json=request.model_dump() | {"observation_revision": revision},
            headers={"X-Advisory-Client": "dashboard"},
        )
        assert r.status_code == 409
    assert client.get("/assistant-api/briefings").json() == []


def test_review_evidence_change_between_capture_and_commit_is_rejected(store):
    inputs, request = joined(store)
    bs = BriefingStore(store)
    with store.connect() as db:
        db.execute(
            "UPDATE observation_reviews SET reviewed=? WHERE revision=?",
            ((NOW + timedelta(seconds=1)).isoformat(), request.observation_revision),
        )
    with pytest.raises(BriefingConflictError):
        bs.save(build_briefing(inputs), request, now=NOW + timedelta(seconds=2))
    assert not bs.history()


def test_concurrent_append_only_briefs_do_not_overwrite_each_other(store):
    from concurrent.futures import ThreadPoolExecutor

    inputs, request = joined(store)
    bs = BriefingStore(store)

    def save(_):
        return bs.save(build_briefing(inputs), request, now=NOW).record.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(save, range(2)))
    assert len(set(ids)) == 2 and len(bs.history()) == 2


def test_reconstructed_oversize_agent_record_is_rejected(store):
    inputs, _ = joined(store)
    with pytest.raises(ValueError):
        build_briefing(inputs.model_copy(update={"agent_records": ({"summary": "x" * 2001},)}))


async def test_deadline_before_save_prevents_late_report(api_client, monkeypatch):
    from api.routes import advisory_briefings as route

    _, _, request = api_client
    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_save = BriefingStore.save
    errors = []

    def held(self, value, selected, *, now):
        started.set()
        try:
            assert release.wait(2)
            return original_save(self, value, selected, now=now)
        except TimeoutError as exc:
            errors.append(exc)
            raise
        finally:
            finished.set()

    monkeypatch.setattr(BriefingStore, "save", held)
    monkeypatch.setattr("api.services.briefings.WORKFLOW_TIMEOUT_SECONDS", 0.2)
    task = asyncio.create_task(route.create(request, SimpleNamespace(app=app)))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        with pytest.raises(HTTPException) as caught:
            await task
        assert caught.value.status_code == 504
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
    assert BriefingStore(app.state.service.store).history() == []
    assert len(errors) == 1


def test_expired_guard_rolls_back_and_does_not_leak_to_direct_save(store):
    inputs, request = joined(store)
    bs, value = BriefingStore(store), build_briefing(inputs)
    guard = BriefingSaveGuard(time.monotonic() - 1)
    with guarded_briefing_save(guard), pytest.raises(TimeoutError):
        bs.save(value, request, now=NOW)
    assert bs.history() == []
    assert bs.save(value, request, now=NOW).record == value
    assert len(bs.history()) == 1


async def test_cancelled_collection_finishes_without_save(api_client, monkeypatch):
    _, _, request = api_client
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def waiting(*_):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    monkeypatch.setattr("api.services.briefings.collect_context", waiting)
    workflow = BriefingWorkflow(app.state.service, app.state.calendars, agent_tap_enabled=False)
    task = asyncio.create_task(workflow.create(request))
    await asyncio.wait_for(started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and BriefingStore(app.state.service.store).history() == []


@pytest.mark.parametrize("cross_commit", [False, True])
async def test_deadline_on_both_sides_of_commit_decision(api_client, monkeypatch, cross_commit):
    from api.routes import advisory_briefings as route

    _, _, request = api_client
    began, release, finished = threading.Event(), threading.Event(), threading.Event()
    original_begin, original_save = BriefingSaveGuard.begin_commit, BriefingStore.save
    errors = []

    def pause(guard):
        if cross_commit:
            original_begin(guard)
        began.set()
        assert release.wait(2)
        if not cross_commit:
            original_begin(guard)

    def completed(self, *args, **kwargs):
        try:
            return original_save(self, *args, **kwargs)
        except TimeoutError as exc:
            errors.append(exc)
            raise
        finally:
            finished.set()

    monkeypatch.setattr(BriefingSaveGuard, "begin_commit", pause)
    monkeypatch.setattr(BriefingStore, "save", completed)
    monkeypatch.setattr("api.services.briefings.WORKFLOW_TIMEOUT_SECONDS", 0.2)
    task = asyncio.create_task(route.create(request, SimpleNamespace(app=app)))
    try:
        assert await asyncio.to_thread(began.wait, 1)
        with pytest.raises(HTTPException) as caught:
            await task
        assert caught.value.status_code == 504
        assert ("قد يكون" in caught.value.detail) is cross_commit
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 1)
    bs = BriefingStore(app.state.service.store)
    assert len(bs.history()) == int(cross_commit)
    assert len(errors) == int(not cross_commit)
    if cross_commit:
        view = bs.read(bs.history()[0]["id"], now=NOW)
        assert view.record.result.account_status["balance"] == "50000"
        assert view.trade_permitted is view.execution_enabled is False


async def test_cancelled_writer_waiting_for_sqlite_lock_cannot_commit(api_client, monkeypatch):
    _, _, request = api_client
    store = app.state.service.store
    bs = BriefingStore(store)
    entered, finished = threading.Event(), threading.Event()
    original = BriefingStore.save
    errors = []

    def writer(self, *args, **kwargs):
        entered.set()
        try:
            return original(self, *args, **kwargs)
        except TimeoutError as exc:
            errors.append(exc)
            raise
        finally:
            finished.set()

    monkeypatch.setattr(BriefingStore, "save", writer)
    workflow = BriefingWorkflow(app.state.service, app.state.calendars, agent_tap_enabled=False)
    with store.connect() as lock:
        lock.execute("BEGIN IMMEDIATE")
        task = asyncio.create_task(workflow.create(request))
        assert await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert await asyncio.to_thread(finished.wait, 1)
    assert len(errors) == 1 and bs.history() == []


async def test_committed_report_delivery_failure_is_not_reported_as_unsaved(
    api_client, monkeypatch
):
    import sqlite3

    client, _, request = api_client

    def broken_read(*_, **__):
        raise sqlite3.OperationalError("synthetic-private-error")

    monkeypatch.setattr(BriefingStore, "read", broken_read)
    from api.routes import advisory_briefings as route

    with pytest.raises(HTTPException) as caught:
        await route.create(request, SimpleNamespace(app=app))
    assert caught.value.status_code == 503 and "حُفظ التقرير" in caught.value.detail
    assert "synthetic-" not in caught.value.detail
    assert len(client.get("/assistant-api/briefings").json()) == 1


async def test_error_after_commit_decision_remains_indeterminate(api_client, monkeypatch):
    import sqlite3

    client, _, request = api_client
    store = app.state.service.store
    original = store.connect

    @contextmanager
    def fail_commit():
        with original() as db:
            yield db
            if db.total_changes:
                raise sqlite3.OperationalError("synthetic-commit-error")

    monkeypatch.setattr(store, "connect", fail_commit)
    from api.routes import advisory_briefings as route

    with pytest.raises(HTTPException) as caught:
        await route.create(request, SimpleNamespace(app=app))
    assert caught.value.status_code == 503 and "قد يكون" in caught.value.detail
    assert "synthetic-" not in caught.value.detail
    assert client.get("/assistant-api/briefings").json() == []


async def test_cancelled_request_guard_is_not_reused_by_next_request(api_client, monkeypatch):
    from api.services import briefings

    _, _, request = api_client
    original_context = briefings.collect_context
    started = asyncio.Event()

    async def waiting(*_):
        started.set()
        await asyncio.Future()

    monkeypatch.setattr(briefings, "collect_context", waiting)
    workflow = BriefingWorkflow(app.state.service, app.state.calendars, agent_tap_enabled=False)
    first = asyncio.create_task(workflow.create(request))
    await asyncio.wait_for(started.wait(), 1)
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    monkeypatch.setattr(briefings, "collect_context", original_context)
    saved = await workflow.create(request)
    assert saved.trade_permitted is saved.execution_enabled is False
    assert len(await workflow.history()) == 1
    assert (await workflow.read(saved.record.id)).record == saved.record
