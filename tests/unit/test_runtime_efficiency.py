"""Work reduction must preserve source freshness, isolation and display lifecycle."""

import asyncio
from collections import Counter
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from api.websockets.dashboard_ws import DashboardWebSocketManager
from connectors.advisory import news
from scripts.runtime import commands, contains_live_services

pytestmark = pytest.mark.unit


def feed(title, link, stamp=None):
    stamp = format_datetime(stamp or datetime.now(UTC))
    return f"<rss><channel><item><title>{title}</title><link>{link}</link><pubDate>{stamp}</pubDate></item></channel></rss>"


async def test_concurrent_markets_share_downloads_but_keep_independent_filtering():
    calls = Counter()

    async def respond(request):
        calls[request.url.host] += 1
        await asyncio.sleep(0)
        return httpx.Response(200, text=feed("Bitcoin mining", str(request.url) + "/item"))

    cache = news.FeedCache()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        crypto, nasdaq = await asyncio.gather(
            news.headlines(client, "BTCUSDT-PERP", [], cache),
            news.headlines(client, "MNQ", [], cache),
        )
        interested, errors = await news.headlines(client, "MNQ", ["mining"], cache)
    assert sum(calls.values()) == len(news.FEEDS) == 5
    assert len(crypto[0]) == len(interested) == 5
    assert len(nasdaq[0]) == 4 and not errors
    assert all(item.category != "crypto" for item in nasdaq[0])


async def test_feed_ttl_outages_and_recovery_never_relabel_stale_success(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(news.time, "monotonic", lambda: clock[0])
    responses = iter([200, 503, 200])
    calls = []

    def respond(request):
        calls.append(request.url)
        return httpx.Response(next(responses), text=feed("Fed rates", "https://example.com/1"))

    cache = news.FeedCache()
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        assert (await cache.get(client, "Federal Reserve"))[0]
        clock[0] += 299
        assert (await cache.get(client, "Federal Reserve"))[0]
        assert len(calls) == 1
        clock[0] += 1
        assert (await cache.get(client, "Federal Reserve"))[0] == []
        clock[0] += 29
        assert (await cache.get(client, "Federal Reserve"))[1]
        assert len(calls) == 2
        clock[0] += 1
        items, error = await cache.get(client, "Federal Reserve")
        assert items and error is None and len(calls) == 3


async def test_cached_news_still_expires_by_publication_age(monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(news, "utcnow", lambda: now)
    xml = feed("Fed rates", "https://example.com/1", now - timedelta(days=7) + timedelta(seconds=2))
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=xml))
    ) as client:
        cache = news.FeedCache()
        assert (await news.headlines(client, "MNQ", [], cache))[0]
        now += timedelta(seconds=3)
        assert (await news.headlines(client, "MNQ", [], cache))[0] == []


async def test_cancelled_feed_refresh_can_retry_and_oversize_is_not_cached_as_success():
    started = asyncio.Event()

    async def hang(request):
        started.set()
        await asyncio.Event().wait()

    cache = news.FeedCache()
    async with httpx.AsyncClient(transport=httpx.MockTransport(hang)) as client:
        task = asyncio.create_task(cache.get(client, "SEC"))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 1_000_001))
    ) as client:
        items, error = await cache.get(client, "SEC")
        assert items == [] and error


async def test_display_loops_wait_for_viewer_then_resume_and_cancel_cleanly():
    manager = DashboardWebSocketManager()
    names = [
        "_build_portfolio_snapshot",
        "_build_agents_heartbeats",
        "_build_positions_update",
        "_build_kafka_metrics",
        "_build_system_status",
    ]
    for name in names:
        setattr(manager, name, AsyncMock(return_value={}))
    tasks = [
        asyncio.create_task(loop())
        for loop in [
            manager.run_portfolio_loop,
            manager.run_positions_kafka_loop,
            manager.run_system_status_loop,
        ]
    ]
    try:
        await asyncio.sleep(0.02)
        assert all(getattr(manager, n).await_count == 0 for n in names)
        ws = AsyncMock()
        conn = await manager.connect(ws)
        async with asyncio.timeout(1):
            while ws.send_bytes.await_count < 5:
                await asyncio.sleep(0.001)
        assert all(getattr(manager, n).await_count == 1 for n in names)
        manager.disconnect(conn)
        assert not manager._has_clients.is_set()
        # One-second channel wakes, sees no clients, and does no Redis work.
        await asyncio.sleep(1.05)
        assert manager._build_portfolio_snapshot.await_count == 1
        conn = await manager.connect(ws)
        async with asyncio.timeout(1):
            while manager._build_portfolio_snapshot.await_count < 2:
                await asyncio.sleep(0.001)
        manager.disconnect(conn)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    assert all(t.cancelled() for t in tasks)


async def test_broadcast_survives_connections_changing_during_send():
    manager = DashboardWebSocketManager()
    first, second = AsyncMock(), AsyncMock()
    first_id = await manager.connect(first)
    second_id = await manager.connect(second)

    async def disconnect_mid_send(_):
        manager.disconnect(second_id)

    first.send_bytes.side_effect = disconnect_mid_send
    await manager.broadcast("portfolio.snapshot", {})
    manager.disconnect(first_id)
    assert not manager._has_clients.is_set()


def test_runtime_modes_select_only_their_deployment_and_preserve_volumes():
    research = str(commands("research", "start"))
    assert "docker-compose.advisor.yml" in research
    assert "paper_services" not in research and "docker-compose.yml" not in research
    paper = commands("paper", "start")
    assert paper[0][3] == "docker-compose.paper.yml"
    assert paper[-1][-2:] == ["scripts.paper_services", "start"]
    assert all("prepare" not in c and "deposit" not in c for c in paper)
    for mode in ["research", "paper", "full"]:
        assert all("down" not in c and "-v" not in c for c in commands(mode, "stop"))


def test_full_mode_checks_actual_container_environment_not_only_host_settings():
    assert contains_live_services(
        {"services": {"executor": {"environment": {"ENVIRONMENT": "live"}}}}
    )
    assert contains_live_services(
        {"services": {"executor": {"environment": {"environment": "live"}}}}
    )
    assert not contains_live_services(
        {"services": {"executor": {"environment": {"ENVIRONMENT": "paper_trading"}}, "redis": {}}}
    )


def test_runtime_plan_has_no_process_side_effects(monkeypatch, capsys):
    from scripts import runtime

    monkeypatch.setattr(runtime.sys, "argv", ["runtime", "research", "plan"])
    run = AsyncMock()
    monkeypatch.setattr(runtime.subprocess, "run", run)
    assert runtime.main() == 0
    run.assert_not_called()
    assert "docker-compose.advisor.yml" in capsys.readouterr().out


def test_runtime_full_rejects_live_compose_without_printing_secrets(monkeypatch, capsys):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from core.config import settings
    from scripts import runtime

    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(runtime.sys, "argv", ["runtime", "full", "start"])
    run = Mock(
        return_value=SimpleNamespace(
            returncode=0,
            stdout='{"services":{"executor":{"environment":{"ENVIRONMENT":"live","TOKEN":"sensitive"}}}}',
        )
    )
    monkeypatch.setattr(runtime.subprocess, "run", run)
    with pytest.raises(SystemExit) as caught:
        runtime.main()
    assert caught.value.code == 2
    assert run.call_count == 1 and "config" in run.call_args.args[0]
    assert "sensitive" not in str(capsys.readouterr())


def test_paper_start_stops_before_agents_when_provisioning_fails(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from core.config import settings
    from scripts import paper_runtime, runtime

    monkeypatch.setattr(settings, "execution_accounts", [object()])
    monkeypatch.setattr(paper_runtime, "require_local_paper", lambda: None)
    monkeypatch.setattr(runtime.sys, "argv", ["runtime", "paper", "start"])
    run = Mock(side_effect=[SimpleNamespace(returncode=0), SimpleNamespace(returncode=9)])
    monkeypatch.setattr(runtime.subprocess, "run", run)
    assert runtime.main() == 9
    assert run.call_count == 2
    assert run.call_args.args[0][-1] == "provision"
