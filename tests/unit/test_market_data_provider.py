"""Provider/replay contracts use the same deterministic research path."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from hypothesis import given, settings, strategies as st
from pydantic import HttpUrl, ValidationError

from api.services.advisory import AdvisoryService
from connectors.advisory.market import AdvisoryMarketData
from connectors.advisory.replay import ReplayProvider
from connectors.advisory.storage import AdvisoryStore
from core.advisory.analysis import build_report
from core.advisory.data import MarketDataQuery, bounded_snapshot
from core.advisory.models import Candle, MarketDataEvidence, MarketSnapshot, News
from tests.unit.test_advisory import clear_event_context, market

pytestmark = pytest.mark.unit
START = datetime(2026, 1, 1, tzinfo=UTC)


def records(
    count=640, root="MNQ", contract="MNQZ26", source="https://example.com/synthetic-replay"
):
    bars = [
        Candle(
            open_time=START + timedelta(minutes=15 * index),
            close_time=START + timedelta(minutes=15 * (index + 1), milliseconds=-1),
            open=100 + index,
            high=102 + index,
            low=99 + index,
            close=101 + index,
            volume=10,
        )
        for index in range(count)
    ]
    return [
        MarketSnapshot(
            instrument_id=root,
            interval="15m",
            source=source,
            fetched_at=bars[-1].close_time,
            candles=bars[index : index + 500],
            data_mode="user_import",
            contract=contract,
            derivatives={"future_information": Decimal(999)},
            observations=["Future context must not enter replay."],
            quality=MarketDataEvidence(
                provider_id="explicit-synthetic-replay-fixture",
                provider_state="active",
                heartbeat_at=bars[-1].close_time,
                sequence_mode="not_applicable",
            ),
        )
        for index in range(0, count, 500)
    ]


def query(index=100, **changes):
    return MarketDataQuery.model_validate(
        dict(
            instrument_id="MNQ",
            interval="15m",
            contract="MNQZ26",
            as_of=START + timedelta(minutes=15 * (index + 1), milliseconds=-1),
        )
        | changes
    )


def test_report_revalidates_copied_contract_identity():
    value = market().model_copy(update={"contract": "NQZ26"})
    with pytest.raises(ValidationError, match="dated contract"):
        build_report("MNQ", "15m", value, [], [])


def test_report_revalidates_mutated_candle_economics():
    value = market()
    value.candles[-1].high = Decimal("1")
    with pytest.raises(ValidationError, match="Invalid candle"):
        build_report("MNQ", "15m", value, [], [])


@pytest.mark.parametrize(
    "change",
    [
        {"instrument_id": "UNKNOWN"},
        {"contract": "NQZ26"},
        {"contract": "MNQF26"},
        {"max_bars": 0},
        {"max_bars": 501},
        {"max_bars": True},
        {"max_bars": Decimal("1.5")},
        {"as_of": START.replace(tzinfo=None)},
        {"interval": "30m"},
    ],
)
def test_query_rejects_unknown_identity_clock_or_unbounded_size(change):
    with pytest.raises(ValidationError):
        query(**change)
    with pytest.raises(ValidationError):
        query().max_bars = 999


async def test_replay_is_bounded_without_future_context_or_caller_mutation():
    dataset = records()
    provider = ReplayProvider(dataset)
    dataset[0].candles[0].close = Decimal(999999)
    before = await provider.read(query(0))
    assert before and before.candles[0].close == 101
    assert before.derivatives == {} and "Future context" not in str(before.observations)
    assert before.fetched_at == query(0).as_of and before.data_mode == "replay"
    late = await provider.read(query(639))
    assert late and len(late.candles) == 500 and late.candles[0].close == 241
    assert all(bar.close_time <= query(639).as_of for bar in late.candles)
    one = await provider.read(query(639, max_bars=1))
    assert one and len(one.candles) == 1 and one.candles[0].close == 740
    before.candles[0].close = Decimal(11111)
    assert (await provider.read(query(0))).candles[0].close == 101


async def test_missing_and_unfinished_replay_windows_remain_missing():
    provider = ReplayProvider(records(10))
    for q in (
        query(as_of=START),
        query(as_of=START + timedelta(minutes=5)),
        query(instrument_id="MES", contract="MESZ26"),
        query(contract="MNQH26"),
        query(interval="1h"),
    ):
        assert await provider.read(q) is None
    assert await ReplayProvider([]).read(query()) is None


async def test_overlapping_contracts_require_explicit_pin():
    provider = ReplayProvider(records(80) + records(80, contract="MNQH26"))
    with pytest.raises(ValueError, match="pinned contract"):
        await provider.read(query(contract=None))
    assert (await provider.read(query(contract="MNQH26"))).contract == "MNQH26"
    assert (await provider.read(query(contract="MNQZ26"))).contract == "MNQZ26"


@pytest.mark.parametrize("kind", ["duplicate", "out_of_order", "overlap", "source", "mutated"])
def test_replay_rejects_inconsistent_records(kind):
    dataset = records(600)
    if kind == "duplicate":
        dataset = [dataset[0], dataset[0]]
    elif kind == "out_of_order":
        dataset.reverse()
    elif kind == "overlap":
        first = dataset[1].candles[0]
        first.open_time = dataset[0].candles[-1].close_time
        first.close_time = first.open_time + timedelta(minutes=15, milliseconds=-1)
    elif kind == "source":
        dataset[1].source = HttpUrl("https://example.com/other-source")
    else:
        dataset[0].candles[0].high = Decimal(1)
    with pytest.raises(ValueError):
        ReplayProvider(dataset)


def test_provider_boundary_revalidates_identity_cuts_and_model_copies():
    value = records(80)[0]
    q = query(10, max_bars=3)
    result = bounded_snapshot(value, q)
    assert result and [bar.close for bar in result.candles] == [109, 110, 111]
    assert len(value.candles) == 80
    assert bounded_snapshot(value, query(as_of=START)) is None
    assert bounded_snapshot(None, q) is None
    for wrong in (query(instrument_id="NQ", contract="NQZ26"), query(interval="1h")):
        with pytest.raises(ValueError, match="identity/interval"):
            bounded_snapshot(value, wrong)
    with pytest.raises(ValueError, match="different dated contract"):
        bounded_snapshot(value, query(contract="MNQH26"))
    with pytest.raises(ValidationError):
        bounded_snapshot(value, q.model_copy(update={"max_bars": 999}))
    value.candles[0].low = Decimal(99999)
    with pytest.raises(ValidationError):
        bounded_snapshot(value, q)


async def test_current_adapter_reuses_store_and_public_reads_without_fabrication(tmp_path):
    store = AdvisoryStore(str(tmp_path / "current.sqlite3"))
    public = Mock()
    public.snapshot = AsyncMock(return_value=market("BTCUSDT-PERP"))
    provider = AdvisoryMarketData(public, store)
    assert await provider.read(query()) is None
    public.snapshot.assert_not_awaited()
    store.import_market(records(80)[0])
    result = await provider.read(query(79))
    assert result and result.contract == "MNQZ26"
    value = public.snapshot.return_value
    q = MarketDataQuery(
        instrument_id="BTCUSDT-PERP", interval="15m", as_of=value.candles[-1].close_time, max_bars=3
    )
    assert len((await provider.read(q)).candles) == 3
    public.snapshot.assert_awaited_once_with("BTCUSDT-PERP", "BTCUSDT", "15m")
    with pytest.raises(ValidationError):
        await provider.read(q.model_copy(update={"instrument_id": "UNKNOWN"}))


async def test_service_replay_uses_same_math_and_never_fetches_live_context(tmp_path, monkeypatch):
    store = AdvisoryStore(str(tmp_path / "replay.sqlite3"))
    monkeypatch.setattr(store, "watchlist", Mock(side_effect=AssertionError("live watchlist")))
    monkeypatch.setattr(
        store, "intelligence", Mock(side_effect=AssertionError("live intelligence"))
    )
    headlines = AsyncMock(side_effect=AssertionError("live headlines"))
    monkeypatch.setattr("api.services.advisory.headlines", headlines)
    provider = ReplayProvider(records())
    cut = query(100).as_of
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (_ for _ in ()).throw(AssertionError("live HTTP"))
        )
    ) as client:
        service = AdvisoryService(store, client, provider=provider, clock=lambda: cut)
        first = await service.report("MNQ", "15m", contract="MNQZ26")
        snapshot = await provider.read(query(100))
        direct = build_report("MNQ", "15m", snapshot, [], [], now=cut)
        assert first.indicators == direct.indicators and first.scenarios == direct.scenarios
        assert first.generated_at == cut and first.status == direct.status == "ready"
        assert first.agent_context == first.news == [] and first.execution_enabled is False
        assert store.report(first.id)["market"]["data_mode"] == "replay"
        cut = query(200).as_of
        later = await service.report("MNQ", "15m", contract="MNQZ26")
        assert later.indicators["last_close"] == 301
        cut = query(100).as_of
        repeated = await service.report("MNQ", "15m", contract="MNQZ26")
        assert repeated.indicators == first.indicators
        assert repeated.scenarios == first.scenarios and repeated.generated_at == first.generated_at
        assert service.cache == {}
    headlines.assert_not_awaited()


@pytest.mark.parametrize("fault", ["exception", "identity", "mode", "missing"])
async def test_provider_failure_cannot_generate_price_scenarios(tmp_path, monkeypatch, fault):
    store = AdvisoryStore(str(tmp_path / "fault.sqlite3"))
    monkeypatch.setattr("api.services.advisory.headlines", AsyncMock(return_value=([], [])))
    provider = Mock()
    provider.mode = "current"
    value = records(80)[0]
    if fault == "identity":
        value = value.model_copy(update={"instrument_id": "NQ", "contract": "NQZ26"})
    elif fault == "mode":
        value = value.model_copy(update={"data_mode": "replay"})
    elif fault == "missing":
        value = None
    provider.read = AsyncMock(return_value=value)
    if fault == "exception":
        provider.read.side_effect = httpx.ReadTimeout("unavailable")
    async with httpx.AsyncClient() as client:
        service = AdvisoryService(store, client, provider=provider, clock=lambda: query(79).as_of)
        result = await service.report("MNQ", "15m")
    assert result.status == "unavailable" and not result.scenarios
    assert result.market is None and not result.execution_enabled


def test_unknown_provider_mode_and_naive_research_clock_fail_closed(tmp_path):
    provider = Mock()
    provider.mode = "guess"
    store = AdvisoryStore(str(tmp_path / "unknown.sqlite3"))
    with pytest.raises(ValueError, match="provider mode"):
        AdvisoryService(store, Mock(), provider=provider)
    with pytest.raises(ValueError, match="clock"):
        build_report("MNQ", "15m", None, [], [], now=START.replace(tzinfo=None))


async def test_virtual_clock_boundary_excludes_unfinished_bar():
    provider = ReplayProvider(records(80))
    cut = query(59).as_of
    early = await provider.read(query(59, as_of=cut - timedelta(microseconds=1)))
    exact = await provider.read(query(59))
    late = await provider.read(query(59, as_of=cut + timedelta(microseconds=1)))
    assert len(early.candles) == 59
    assert len(exact.candles) == len(late.candles) == 60
    assert build_report("MNQ", "15m", early, [], [], now=cut).status == "insufficient"
    assert build_report("MNQ", "15m", exact, [], [], now=cut).status == "ready"


def test_direct_report_rejects_future_closing_bar_at_clock_boundary():
    value = records(80)[0]
    close = value.candles[-1].close_time
    before = build_report("MNQ", "15m", value, [], [], now=close - timedelta(microseconds=1))
    exact = build_report("MNQ", "15m", value, [], [], now=close)
    after = build_report("MNQ", "15m", value, [], [], now=close + timedelta(microseconds=1))
    assert before.status == "stale" and before.scenarios == []
    assert exact.status == after.status == "ready"


async def test_future_prices_cannot_change_past_replay_features():
    first = records(200)
    changed = records(200)
    for bar in changed[0].candles[100:]:
        bar.open += 100000
        bar.high += 100000
        bar.low += 100000
        bar.close += 100000
    q = query(79)
    before = await ReplayProvider(first).read(q)
    after = await ReplayProvider(changed).read(q)
    assert before == after
    a = build_report("MNQ", "15m", before, [], [], now=q.as_of)
    b = build_report("MNQ", "15m", after, [], [], now=q.as_of)
    assert a.indicators == b.indicators and a.scenarios == b.scenarios


async def test_changed_provider_mode_is_rejected_before_read(tmp_path):
    provider = Mock()
    provider.mode = "current"
    provider.read = AsyncMock()
    service = AdvisoryService(
        AdvisoryStore(str(tmp_path / "mode.sqlite3")),
        Mock(),
        provider=provider,
        clock=lambda: query().as_of,
    )
    provider.mode = "unknown"
    with pytest.raises(ValueError, match="provider mode"):
        await service.report("MNQ", "15m")
    provider.read.assert_not_awaited()


async def test_current_service_filters_future_context_and_preserves_cache_budget(
    tmp_path, monkeypatch
):
    store = AdvisoryStore(str(tmp_path / "current-service.sqlite3"))
    cut = query(79).as_of
    past = News(
        id="past",
        title="Synthetic past news",
        url="https://example.com/past",
        source="fixture",
        published_at=cut,
        category="macro",
    )
    future = past.model_copy(
        update={"id": "future", "published_at": cut + timedelta(microseconds=1)}
    )
    headlines = AsyncMock(return_value=([past, future], []))
    monkeypatch.setattr("api.services.advisory.headlines", headlines)
    for identity, timestamp, symbol in [
        ("allowed", cut, "MNQ"),
        ("future", cut + timedelta(microseconds=1), "MNQ"),
        ("stale", cut - timedelta(seconds=3601), "MNQ"),
        ("other", cut, "MES"),
    ]:
        store.save_intelligence(
            dict(
                id=identity,
                timestamp=timestamp.isoformat(),
                symbol=symbol,
                summary="Synthetic context",
            )
        )
    provider = Mock()
    provider.mode = "current"
    provider.read = AsyncMock(return_value=records(80)[0])
    monotonic = 10.0
    monkeypatch.setattr("api.services.advisory.time.monotonic", lambda: monotonic)
    service = AdvisoryService(store, Mock(), provider=provider, clock=lambda: cut)
    first = await service.report("MNQ", "15m")
    assert [item.id for item in first.news] == ["past"]
    assert [item["id"] for item in first.agent_context] == ["allowed"]
    assert (await service.report("MNQ", "15m")).id == first.id
    provider.read.assert_awaited_once()
    with pytest.raises(ValueError, match="few seconds"):
        await service.report("NQ", "15m")
    with pytest.raises(ValueError, match="Unknown instrument"):
        await service.report("UNKNOWN", "15m")
    monotonic = 74.0
    refreshed = await service.report("MNQ", "15m")
    assert refreshed.id != first.id and provider.read.await_count == 2


@settings(max_examples=100, derandomize=True, database=None)
@given(
    cut_index=st.integers(min_value=0, max_value=199),
    window=st.integers(min_value=1, max_value=500),
)
def test_property_replay_cut_prevents_future_leakage(cut_index, window):
    original, changed = records(200), records(200)
    for bar in changed[0].candles[cut_index + 1 :]:
        for field in ("open", "high", "low", "close"):
            setattr(bar, field, getattr(bar, field) + 1000000)
    q = query(cut_index, max_bars=window)

    async def snapshots():
        return (await ReplayProvider(original).read(q), await ReplayProvider(changed).read(q))

    before, after = asyncio.run(snapshots())
    assert before == after
    assert len(before.candles) == min(cut_index + 1, window)
    assert all(bar.close_time <= q.as_of for bar in before.candles)
    context = clear_event_context(q.as_of)
    a = build_report("MNQ", "15m", before, [], [], now=q.as_of, **context)
    b = build_report("MNQ", "15m", after, [], [], now=q.as_of, **context)
    assert a.status == b.status and a.indicators == b.indicators and a.scenarios == b.scenarios
    if len(before.candles) >= 60:
        assert len(a.scenarios) == len(b.scenarios) == 3
