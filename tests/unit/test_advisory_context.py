"""Synthetic mechanics only: partial context cannot authorize trading."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from api.advisor import app
from connectors.advisory import economic_calendar as calendars, news as feeds
from core.advisory.news_context import NewsContext, SourceStatus, build_context, relevance
from core.config import settings

pytestmark = pytest.mark.unit
NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)
FOMC = b"""<div class="panel"><h4>2026 FOMC Meetings</h4>
<div class="fomc-meeting"><div class="fomc-meeting__month">October</div><div class="fomc-meeting__date">27-28*</div></div>
<div class="fomc-meeting"><div class="fomc-meeting__month">December/January</div><div class="fomc-meeting__date">31-1</div></div></div>"""
BEA = b"""<table id="release-schedule-table"><thead>Year 2026</thead><tbody>
<tr><td class="release-title">Gross Domestic Product</td><td class="scheduled-date"><span class="release-date">October 30</span><small>8:30 AM</small></td></tr>
<tr><td class="release-title">Personal Income and Outlays</td><td class="scheduled-date">To Be Announced</td></tr></tbody></table>"""


def rss(items=None):
    if items is None:
        items = [("Fed inflation", "https://example.org/a", NOW - timedelta(minutes=30))]
    return (
        '<rss version="2.0"><channel><title>Fixture</title>'
        + "".join(
            f"<item><title><![CDATA[{title}]]></title><link>{url}</link>"
            + (f"<pubDate>{format_datetime(stamp)}</pubDate>" if stamp else "")
            + "</item>"
            for title, url, stamp in items
        )
        + "</channel></rss>"
    ).encode()


def ics(start="DTSTART;TZID=America/New_York:20261030T083000", extra=""):
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nSUMMARY:Employment report\r\n{start}\r\n{extra}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n".encode()


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(feeds, "utcnow", lambda: NOW)
    monkeypatch.setattr(calendars, "utcnow", lambda: NOW)


def source(name="Federal Reserve", **overrides):
    return SourceStatus.model_validate(
        {
            "name": name,
            "url": feeds.FEEDS[name][0],
            "kind": "news",
            "attempted_at": NOW,
            "fetched_at": NOW,
            "state": "ok",
            "content_sha256": "a" * 64,
            "http_status": 200,
            "parsed_count": 1,
            "usable_count": 1,
            **overrides,
        }
    )


async def test_headline_identity_deduplication_html_dates_links_and_compatibility():
    body = rss(
        [
            ("<b>Fed</b> inflation", "https://example.org/a", NOW),
            ("Fed revised", "https://example.org/a", NOW),
            ("Fed unsafe", "javascript:alert(1)", NOW),
            ("Fed credentials", "https://user:password@example.org/b", NOW),
            ("Fed old", "https://example.org/c", NOW - timedelta(days=8)),
            ("Fed future", "https://example.org/d", NOW + timedelta(hours=1)),
            ("Fed missing", "https://example.org/e", None),
            ("<img src=x onerror=alert(1)>Fed rates", "https://example.org/f", NOW),
        ]
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        cache = feeds.FeedCache()
        items, status = await cache.context(client, "Federal Reserve")
        old, error = await cache.get(client, "Federal Reserve")
    assert len(items) == 2 and error is None and old == items
    assert items[-1].title == "Fed rates"
    assert status.parsed_count == 8 and status.usable_count == 2
    items[0].title = "modified caller copy"
    assert old[0].title == "Fed revised"


@pytest.mark.parametrize(
    "body,state",
    [
        (b"<html>Unavailable</html>", "invalid"),
        (b"<rss><channel>", "invalid"),
        (rss([]), "empty"),
        (rss([("Fed old", "https://example.org/a", NOW - timedelta(days=8))]), "empty"),
    ],
)
async def test_invalid_format_and_valid_empty_are_distinct(body, state):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        items, status = await feeds.FeedCache().context(client, "BLS")
    assert items == [] and status.state == state and status.http_status == 200
    assert status.content_sha256 is not None


@pytest.mark.parametrize("root", ["MES", "MNQ"])
async def test_legacy_crypto_filter_and_new_explained_relevance(root):
    def respond(request):
        title = "Unrelated token giveaway" if "cointelegraph" in request.url.host else "Fed policy"
        return httpx.Response(200, content=rss([(title, str(request.url), NOW)]))

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        legacy, errors = await feeds.headlines(client, root, [])
        results = await asyncio.gather(*(feeds.FeedCache().context(client, n) for n in feeds.FEEDS))
    assert not errors and all(n.category != "crypto" for n in legacy)
    context = build_context(
        root, [n for items, _ in results for n in items], [], [s for _, s in results], [], now=NOW
    )
    assert len(context.headlines) == 4
    assert all(h.relevance == ("central_bank",) for h in context.headlines)
    assert relevance("Congress", ["ES"]) == ()
    assert relevance("A+B earnings", ["A+B"]) == ("equity_indexes", "user_interest")


async def test_single_flight_cache_clocks_expiry_failure_recovery(monkeypatch):
    tick = [0.0]
    monkeypatch.setattr(feeds.time, "monotonic", lambda: tick[0])
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) == 2 else 200, content=rss())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        cache = feeds.FeedCache()
        first = await asyncio.gather(*(cache.context(client, "BLS") for _ in range(8)))
        assert len(calls) == 1 and all(v[1].fetched_at == NOW for v in first)
        tick[0] = 299
        assert (await cache.context(client, "BLS"))[1] == first[0][1]
        tick[0] = 300
        items, failed = await cache.context(client, "BLS")
        assert not items and failed.state == "unavailable" and failed.http_status == 503
        tick[0] = 329
        assert (await cache.context(client, "BLS"))[1] == failed
        tick[0] = 330
        assert (await cache.context(client, "BLS"))[1].state == "ok" and len(calls) == 3


async def test_cancelled_fetch_releases_single_flight_lock():
    started, wait = asyncio.Event(), asyncio.Event()

    async def respond(_):
        started.set()
        await wait.wait()
        return httpx.Response(200, content=rss())

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        cache = feeds.FeedCache()
        task = asyncio.create_task(cache.context(client, "BLS"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        wait.set()
        assert (await asyncio.wait_for(cache.context(client, "BLS"), 1))[1].state == "ok"


@pytest.mark.parametrize(
    "location",
    ["http://www.bls.gov/x", "https://evil.example/x", "https://user:pass@www.bls.gov/x"],
)
async def test_redirects_cannot_escape_origin(location):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": location})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        _, status = await feeds.FeedCache().context(client, "BLS")
    assert status.state == "invalid" and len(calls) == 1


async def test_size_and_redirect_loop_bounds():
    for respond in (
        lambda _: httpx.Response(200, content=b"x" * 1_000_001),
        lambda _: httpx.Response(302, headers={"location": "/loop"}),
    ):
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            _, status = await feeds.FeedCache().context(client, "BLS")
            assert status.state == "invalid"


async def test_network_failure_and_same_origin_redirect():
    async def fail(_):
        raise httpx.ConnectError("synthetic")

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        assert (await feeds.FeedCache().context(client, "BLS"))[1].state == "unavailable"

    def redirect(request):
        return (
            httpx.Response(200, content=rss())
            if request.url.path == "/new"
            else httpx.Response(302, headers={"location": "/new"})
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect)) as client:
        assert (await feeds.FeedCache().context(client, "BLS"))[1].state == "ok"


def test_official_date_only_ranges_and_unannounced_times_remain_unknown():
    fomc = calendars.parse_calendar("FOMC", FOMC, now=NOW)
    bea = calendars.parse_calendar("BEA", BEA, now=NOW)
    assert str(fomc[0].date_start) == "2026-10-27" and str(fomc[0].date_end) == "2026-10-28"
    assert str(fomc[1].date_end) == "2027-01-01"
    assert all(e.event.scheduled_at is None and e.timezone is None for e in fomc + bea)
    assert bea[0].printed_time == "8:30 AM" and bea[1].date_start is None
    assert bea[1].event.status == "unknown"


@pytest.mark.parametrize(
    "local,utc",
    [
        ("20260306T083000", "2026-03-06T13:30:00+00:00"),
        ("20260309T083000", "2026-03-09T12:30:00+00:00"),
        ("20261102T083000", "2026-11-02T13:30:00+00:00"),
    ],
)
def test_explicit_eastern_conversion_observes_dst(local, utc):
    value = calendars.parse_calendar(
        "BLS calendar", ics(f"DTSTART;TZID=America/New_York:{local}"), now=NOW
    )[0]
    assert value.event.scheduled_at.isoformat() == utc


@pytest.mark.parametrize(
    "start",
    [
        "DTSTART;TZID=America/New_York:20260308T023000",
        "DTSTART;TZID=America/New_York:20261101T013000",
        "DTSTART:20261030T083000",
        "DTSTART;TZID=Europe/London:20261030T083000",
    ],
)
def test_ambiguous_nonexistent_or_unspecified_zone_is_not_invented(start):
    with pytest.raises(ValueError):
        calendars.parse_calendar("BLS calendar", ics(start), now=NOW)


def test_cancelled_date_only_utc_and_unsupported_recurring_events():
    value = calendars.parse_calendar(
        "BLS calendar", ics("DTSTART;VALUE=DATE:20261030", "STATUS:CANCELLED"), now=NOW
    )[0]
    assert value.event.status == "cancelled" and value.event.scheduled_at is None
    value = calendars.parse_calendar("BLS calendar", ics("DTSTART:20261030T123000Z"), now=NOW)[0]
    assert value.timezone == "UTC" and value.event.scheduled_at.hour == 12
    with pytest.raises(ValueError):
        calendars.parse_calendar("BLS calendar", ics(extra="RRULE:FREQ=MONTHLY"), now=NOW)


@pytest.mark.parametrize(
    "name,body",
    [
        ("FOMC", b"<html>changed</html>"),
        ("BEA", b"<html>changed</html>"),
        ("BLS calendar", b"<html>denied</html>"),
        ("BEA", BEA.replace(b"Year 2026", b"Year unknown")),
        ("FOMC", FOMC.replace(b"27-28*", b"undecided")),
    ],
)
def test_changed_or_bad_schedule_is_rejected(name, body):
    with pytest.raises(ValueError):
        calendars.parse_calendar(name, body, now=NOW)


async def test_calendar_failure_no_stale_fallback_cache_and_source_edit(monkeypatch):
    tick = [0.0]
    monkeypatch.setattr(calendars.time, "monotonic", lambda: tick[0])
    bodies = [FOMC, FOMC.replace(b"27-28*", b"28-29*")]

    def respond(request):
        if "bls" in request.url.host:
            return httpx.Response(403)
        return httpx.Response(200, content=bodies[min(int(tick[0] // 300), 1)])

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        cache = calendars.CalendarCache()
        a, status_a = await cache.get(client, "FOMC")
        assert (await cache.get(client, "FOMC"))[1] == status_a
        tick[0] = 300
        b, status_b = await cache.get(client, "FOMC")
        assert a[0].event.id != b[0].event.id and status_a.content_sha256 != status_b.content_sha256
        missing, status = await cache.get(client, "BLS calendar")
        assert missing == [] and status.state == "unavailable" and status.http_status == 403


async def test_context_rechecks_cache_age_every_request_and_rejects_forged_permissions():
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=rss()))
    ) as client:
        items, status = await feeds.FeedCache().context(client, "Federal Reserve")
    a = build_context("MES", items, [], [status], [], now=NOW)
    b = build_context("MES", items, [], [status], [], now=NOW + timedelta(minutes=5))
    c = build_context("MES", items, [], [status], [], now=NOW - timedelta(seconds=1))
    assert len(a.headlines) == 1 and not b.headlines and not c.headlines
    assert b.sources[0].state == "stale" and c.sources[0].state == "invalid"
    assert b.sources[0].fetched_at == a.sources[0].fetched_at
    for key, val in [
        ("trade_permitted", True),
        ("execution_enabled", True),
        ("event_risk", "CLEAR"),
        ("coverage", "complete"),
    ]:
        forged = a.model_dump()
        forged[key] = val
        with pytest.raises(ValidationError):
            NewsContext.model_validate(forged)


def test_source_clock_and_counts_inconsistent_rejected():
    with pytest.raises(ValueError):
        source(usable_count=2)
    with pytest.raises(ValueError):
        source(fetched_at=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError):
        source(content_sha256=None)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "advisory_access_token", SecretStr("n" * 48))
    monkeypatch.setattr(settings, "advisory_db_path", str(tmp_path / "api.sqlite3"))
    monkeypatch.setattr(settings, "advisory_kafka_servers", "")

    async def news(_, name):
        return [], source(name, state="empty", parsed_count=0, usable_count=0)

    async def events(_, name):
        return [], SourceStatus(
            name=name,
            url=calendars.CALENDARS[name],
            kind="calendar",
            attempted_at=NOW,
            state="unavailable",
            http_status=403,
        )

    with TestClient(app, headers={"Authorization": "Bearer " + "n" * 48}) as client:
        monkeypatch.setattr(app.state.service, "clock", lambda: NOW)
        monkeypatch.setattr(app.state.service.feeds, "context", news)
        monkeypatch.setattr(app.state.calendars, "get", events)
        yield client


def test_authenticated_context_no_price_report_storage_write_or_order_path(api_client, monkeypatch):
    report = AsyncMock(side_effect=AssertionError("price/report must not run"))
    monkeypatch.setattr(app.state.service, "report", report)
    for root in ("MES", "MNQ"):
        response = api_client.get(f"/assistant-api/context/{root}")
        assert response.status_code == 200
        value = NewsContext.model_validate(response.json())
        assert (
            len(value.sources) == 8
            and value.coverage == "partial"
            and value.event_risk == "UNKNOWN"
        )
        assert value.trade_permitted is False and value.execution_enabled is False
        assert value.headlines == () and value.events == ()
    assert not report.called
    assert api_client.get("/assistant-api/context/ES").status_code == 422
    assert (
        api_client.get(
            "/assistant-api/context/MES", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/assistant-api/context/MES", headers={"X-Advisory-Client": "dashboard"}
        ).status_code
        == 405
    )
    assert api_client.get("/assistant-api/history").json() == []


async def test_context_facade_matches_application_collector_and_http(api_client):
    from types import SimpleNamespace

    from api.routes.advisory_context import _collect_context
    from api.services.briefings import collect_context

    captured, interests = await _collect_context(SimpleNamespace(app=app), "MES")
    direct, selected = await collect_context(app.state.service, app.state.calendars, "MES")
    exposed = NewsContext.model_validate(api_client.get("/assistant-api/context/MES").json())
    assert captured == direct == exposed and interests == selected
    assert len(captured.sources) == 8 and captured.event_risk == "UNKNOWN"
    assert captured.trade_permitted is captured.execution_enabled is False


async def test_application_collector_cancellation_releases_all_source_reads(
    api_client, monkeypatch
):
    from api.services.briefings import collect_context

    started, cancelled = [], []
    all_started = asyncio.Event()

    async def waiting(_, name):
        started.append(name)
        if len(started) == len(feeds.FEEDS):
            all_started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.append(name)

    monkeypatch.setattr(app.state.service.feeds, "context", waiting)
    task = asyncio.create_task(collect_context(app.state.service, app.state.calendars, "MES"))
    await asyncio.wait_for(all_started.wait(), 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sorted(started) == sorted(cancelled) == sorted(feeds.FEEDS)
    assert api_client.get("/assistant-api/history").json() == []


async def test_publication_age_is_recomputed_without_refreshing_cache():
    body = rss(
        [
            ("Fed recent", "https://example.org/recent", NOW),
            ("Fed too early", "https://example.org/future", NOW + timedelta(minutes=1)),
            (
                "Fed about to expire",
                "https://example.org/old",
                NOW - timedelta(days=7) + timedelta(seconds=1),
            ),
        ]
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    ) as client:
        items, status = await feeds.FeedCache().context(client, "BLS")
    initial = build_context("MES", items, [], [status], [], now=NOW)
    later = build_context("MES", items, [], [status], [], now=NOW + timedelta(seconds=2))
    assert {h.item.id for h in later.headlines} < {h.item.id for h in initial.headlines}
    assert [h.item.title for h in later.headlines] == ["Fed recent"]
    assert later.sources[0].fetched_at == NOW


async def test_partial_calendar_merges_valid_sources_and_dates_without_clearance():
    def respond(request):
        if "bls" in request.url.host:
            return httpx.Response(403)
        return httpx.Response(200, content=FOMC if "federalreserve" in request.url.host else BEA)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        cache = calendars.CalendarCache()
        results = await asyncio.gather(*(cache.get(client, name) for name in calendars.CALENDARS))
    value = build_context(
        "MNQ", [], [e for items, _ in results for e in items], [s for _, s in results], [], now=NOW
    )
    assert len(value.events) == 4 and str(value.returned_date_start) == "2026-10-27"
    assert str(value.returned_date_end) == "2027-01-01"
    assert value.event_risk == "UNKNOWN" and value.trade_permitted is False
    assert value.events[-1].date_start is None


@pytest.mark.parametrize(
    "body",
    [
        ics(extra="SUMMARY:duplicate"),
        ics().replace(b"END:VEVENT", b""),
        ics().replace(b"SUMMARY:Employment report", b"SUMMARY:"),
    ],
)
def test_incomplete_or_duplicate_calendar_fields_fail_closed(body):
    with pytest.raises(ValueError):
        calendars.parse_calendar("BLS calendar", body, now=NOW)
