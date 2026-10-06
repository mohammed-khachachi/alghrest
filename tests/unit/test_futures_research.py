"""Independent synthetic fill/path oracles, not genuine trading edge evidence."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext

import pytest
from hypothesis import given, settings, strategies as st

from backtesting.futures import (
    FuturesFillModel,
    FuturesResearchInput,
    FuturesResearchRun,
    futures_dataset_digest,
    run_futures_research,
    strategy_source_digest,
    verify_futures_run,
)
from core.advisory.analysis import breakout_research_check
from core.advisory.models import CATALOG, Candle, EconomicCalendar, EventRiskPolicy, MarketSnapshot
from core.advisory.strategies import ResearchPartition, StrategyDefinition, StrategyResearchPlan
from core.strategy_signals import ATRManagementParameters, BreakoutParameters

pytestmark = pytest.mark.unit
ROOTS = ("MES", "MYM", "MNQ", "MGC", "M2K", "MCL", "M6E", "M6B", "MHG")
START = datetime(2026, 1, 1, tzinfo=UTC)


def request(root="MES", side="BUY", commission=Decimal(1), ticks=1):
    tick = CATALOG[root].tick_size
    levels = [400, 400, 416, 424, 396, 392, 400, 400]
    if side == "SELL":
        levels = [800 - price for price in levels]
    bars = []
    for i, level in enumerate(levels * 3):
        bars.append(
            Candle(
                open_time=START + timedelta(days=i),
                close_time=START + timedelta(days=i + 1, milliseconds=-1),
                open=level * tick,
                high=(level + 2) * tick,
                low=(level - 2) * tick,
                close=level * tick,
                volume=30 if i % 8 == 2 else 10,
            )
        )
    record = MarketSnapshot(
        instrument_id=root,
        interval="1d",
        contract=root + "Z26",
        source="https://example.com/SYNTHETIC-futures",
        fetched_at=bars[-1].close_time,
        data_mode="user_import",
        candles=bars,
        quality=dict(
            provider_id="SYNTHETIC",
            provider_state="active",
            heartbeat_at=bars[-1].close_time,
            sequence_mode="required",
            sequences=tuple(range(len(bars))),
        ),
    )
    calendars = tuple(
        EconomicCalendar(
            id="SYNTHETIC-calendar",
            version=str(i),
            source="https://example.com/SYNTHETIC-calendar",
            observed_at=b.close_time,
            coverage_start=b.open_time,
            coverage_end=b.close_time + timedelta(days=1),
            covered_markets=(root,),
            complete=True,
            provider_state="active",
        )
        for i, b in enumerate(bars)
    )
    partitions = tuple(
        ResearchPartition(
            role=role,
            start=bars[i * 8].open_time,
            end=bars[(i + 1) * 8 - 1].close_time,
        )
        for i, role in enumerate(("TRAIN", "VALIDATION", "OOS"))
    )
    definition = StrategyDefinition(
        id="breakout_hunter_volume",
        version="SYNTHETIC-outcomes-v1",
        registered_at=START,
        source_reference="SYNTHETIC-test-definition",
        origin="synthetic",
        code_version="range-volume-v1",
        code_sha256=strategy_source_digest(),
        parameters=BreakoutParameters(range_period=2, minimum_bars=3, volume_multiplier=2),
        management=ATRManagementParameters(
            atr_period=1, atr_window=3, atr_stop_multiplier=1, proposed_target_r=3
        ),
        interval="1d",
        supported_markets=(root,),
        research=StrategyResearchPlan(
            dataset_id="SYNTHETIC",
            dataset_sha256=futures_dataset_digest((record,)),
            source_reference="https://example.com/SYNTHETIC-futures",
            research_start=START,
            research_end=bars[-1].close_time,
            partitions=partitions,
        ),
    )
    return FuturesResearchInput(
        definition=definition,
        instrument=CATALOG[root],
        records=(record,),
        calendars=calendars,
        event_policy=EventRiskPolicy(
            id="SYNTHETIC-risk",
            version="v1",
            before_seconds=0,
            after_seconds=0,
            max_calendar_age_seconds=1,
            blocked_impacts=("high",),
        ),
        fills=FuturesFillModel(
            id="SYNTHETIC-costs",
            version="v1",
            source_reference="fixture",
            commission_per_side_usd=commission,
            adverse_ticks_per_side=ticks,
        ),
    )


def changed(value, **changes):
    payload = value.model_dump()
    payload.update(changes)
    if "records" in changes:
        records = tuple(MarketSnapshot.model_validate(r) for r in payload["records"])
        payload["definition"]["research"]["dataset_sha256"] = futures_dataset_digest(records)
    return FuturesResearchInput.model_validate(payload)


@pytest.mark.parametrize("root", ROOTS)
@pytest.mark.parametrize("side", ["BUY", "SELL"])
async def test_hand_derived_fills_net_dollars_r_and_partition_resets(root, side):
    value = request(root, side)
    result = await run_futures_research(value)
    tick_value = CATALOG[root].tick_value
    for partition in result.partitions:
        assert partition.state == "COMPLETE"
        assert len(partition.trades) == 1
        assert not partition.censored
        trade = partition.trades[0]
        # 32 adverse price ticks + 2 slippage ticks; commission $2.
        assert trade.gross_usd == -34 * tick_value
        assert trade.net_usd == -34 * tick_value - 2
        # Entry gap widens 18-tick signal risk to 26 + 1 entry + 1 exit tick.
        assert trade.entry.initial_risk_usd == 28 * tick_value + 2
        with localcontext() as context:
            context.prec = 80
            assert trade.net_r == (-34 * tick_value - 2) / (28 * tick_value + 2)
        assert trade.net_r < -1  # Close exits cannot cap gap/overshoot loss at 1R.
        assert trade.entry.entry_at > trade.entry.signal_at
        assert trade.exit_at > trade.exit_signal_at
        assert not trade.entry.initial_stop % CATALOG[root].tick_size
    assert (
        await verify_futures_run(FuturesResearchRun.model_validate_json(result.model_dump_json()))
        == result
    )
    assert not result.trade_permitted and not result.execution_enabled


async def test_repeated_runs_are_byte_reproducible_and_guarded_rule_matches():
    value = request()
    a, b = await run_futures_research(value), await run_futures_research(value)
    assert a.model_dump_json() == b.model_dump_json()
    decision = a.partitions[0].decisions[2]
    snapshot = value.records[0].model_copy(
        update={
            "candles": value.records[0].candles[:3],
            "fetched_at": decision.at,
            "quality": value.records[0].quality.model_copy(
                update={"heartbeat_at": decision.at, "sequences": (0, 1, 2)}
            ),
        }
    )
    check = breakout_research_check(
        "MES",
        "1d",
        snapshot,
        parameters=value.definition.parameters,
        now=decision.at,
        calendar=value.calendars[2],
        event_policy=value.event_policy,
        management_parameters=value.definition.management,
    )
    assert decision.features == check.features
    assert decision.geometry == check.management
    # Ledger references each calendar revision by digest without repeating its body.
    encoded = json.loads(a.model_dump_json())
    assert "calendar" not in encoded["partitions"][0]["decisions"][2]["event_risk"]
    assert "policy" not in encoded["partitions"][0]["decisions"][2]["event_risk"]
    assert encoded["inputs"]["calendars"][2]["version"] == "2"


@pytest.mark.parametrize(
    "change",
    ["dataset", "code", "spec", "market", "split", "management", "sequence", "duplicate", "source"],
)
def test_captured_input_joins_and_archive_corruption_rejected(change):
    value = request()
    payload = value.model_dump()
    if change == "dataset":
        payload["definition"]["research"]["dataset_sha256"] = "0" * 64
    elif change == "code":
        payload["definition"]["code_sha256"] = "0" * 64
    elif change == "spec":
        payload["instrument"]["point_value"] = "1000"
    elif change == "market":
        payload["definition"]["supported_markets"] = ("MNQ",)
    elif change == "split":
        payload["definition"]["research"]["partitions"][0]["end"] = START + timedelta(days=10)
    elif change == "management":
        payload["definition"]["management"] = None
    elif change == "sequence":
        payload["records"][0]["quality"]["sequences"] = (1,)
    elif change == "duplicate":
        payload["records"] = (payload["records"][0],) * 2
    elif change == "source":
        second = dict(payload["records"][0])
        second["source"] = "https://example.com/other"
        payload["records"] = (payload["records"][0], second)
    with pytest.raises(ValueError):
        if change in {"sequence", "duplicate", "source"}:
            changed(value, records=payload["records"])
        else:
            FuturesResearchInput.model_validate(payload)


@pytest.mark.parametrize("change", ["net", "fill", "decision", "runner", "censor", "state"])
async def test_saved_run_requires_full_replay_and_rejects_computed_path_tampering(change):
    result = await run_futures_research(request())
    payload = json.loads(result.model_dump_json())
    part = payload["partitions"][2]
    if change == "net":
        part["trades"][0]["net_usd"] = "10000"
    elif change == "fill":
        part["trades"][0]["entry"]["entry_fill"] = "110"
    elif change == "decision":
        part["decisions"][2]["action"] = "WAIT"
    elif change == "runner":
        payload["runner_sha256"] = "0" * 64
    elif change == "censor":
        part["censored"] = [
            dict(
                entry=part["trades"][0]["entry"],
                censored_at=part["decisions"][-1]["at"],
                last_stop="100",
                reason="invented",
            )
        ]
    elif change == "state":
        part["state"] = "INCOMPLETE"
    with pytest.raises(ValueError, match="replay mismatch"):
        await verify_futures_run(FuturesResearchRun.model_validate(payload))


@pytest.mark.parametrize(
    "problem",
    [
        "quality",
        "calendar",
        "event_policy",
        "sequence",
        "off_tick",
        "provider",
        "heartbeat",
        "future_calendar",
    ],
)
async def test_unknown_corrupt_guard_facts_never_generate_an_entry(problem):
    value = request()
    records = [value.records[0].model_dump()]
    if problem == "calendar":
        value = changed(value, calendars=())
    elif problem == "event_policy":
        value = changed(value, event_policy=None)
    elif problem == "future_calendar":
        rows = [c.model_dump() for c in value.calendars]
        for c in rows:
            c["observed_at"] += timedelta(days=100)
        value = changed(value, calendars=rows)
    else:
        if problem == "quality":
            records[0]["quality"] = None
        elif problem == "sequence":
            records[0]["quality"]["sequences"] = tuple(i * 2 for i in range(24))
        elif problem == "off_tick":
            for bar in records[0]["candles"]:
                bar["high"] += Decimal("0.001")
        elif problem == "provider":
            records[0]["quality"]["provider_state"] = "disconnected"
        elif problem == "heartbeat":
            records[0]["quality"]["heartbeat_at"] = None
        value = changed(value, records=records)
    run = await run_futures_research(value)
    assert all(not p.trades and not p.censored and p.state == "INCOMPLETE" for p in run.partitions)
    assert all(d.action == "BLOCKED" for p in run.partitions for d in p.decisions)


async def test_train_and_validation_do_not_change_when_final_holdout_changes():
    value = request()
    a = await run_futures_research(value)
    records = [value.records[0].model_dump()]
    for bar in records[0]["candles"][16:]:
        for name in ("open", "high", "low", "close"):
            bar[name] += Decimal(100)
    b = await run_futures_research(changed(value, records=records))
    assert a.partitions[:2] == b.partitions[:2]
    assert a.partitions[2] != b.partitions[2]


async def test_open_position_is_censored_and_never_force_closed_or_crosses_split():
    value = request()
    records = [value.records[0].model_dump()]
    for i, bar in enumerate(records[0]["candles"]):
        if i % 8 >= 3:
            for name in ("open", "high", "low", "close"):
                bar[name] = Decimal(106) + (
                    {"high": Decimal(".5"), "low": Decimal("-.5")}.get(name, 0)
                )
    run = await run_futures_research(changed(value, records=records))
    for p in run.partitions:
        assert not p.trades
        assert len(p.censored) == 1 and p.state == "INCOMPLETE"
        assert p.censored[0].reason == "partition_end_open_position"


async def test_stop_not_moved_to_make_next_open_gap_fit():
    value = request()
    records = [value.records[0].model_dump()]
    for i in (3, 11, 19):
        records[0]["candles"][i]["open"] = Decimal(98)
        records[0]["candles"][i]["low"] = Decimal(98)
    run = await run_futures_research(changed(value, records=records))
    assert all(not p.trades and not p.censored for p in run.partitions)
    assert all(
        p.fills[0].state == "SKIPPED"
        and p.fills[0].reason == "invalid_entry_after_gap_or_tick_rounding"
        for p in run.partitions
    )


async def test_adverse_entry_slippage_cannot_rescue_an_already_invalid_raw_open():
    value = request(ticks=10)
    records = [value.records[0].model_dump()]
    for i in (3, 11, 19):
        records[0]["candles"][i]["open"] = Decimal(98)
        records[0]["candles"][i]["low"] = Decimal(98)
    run = await run_futures_research(changed(value, records=records))
    assert all(not p.trades and p.fills[0].state == "SKIPPED" for p in run.partitions)


async def test_caller_mutation_and_numeric_context_do_not_change_captured_results():
    value = request()
    a = await run_futures_research(value)
    with localcontext() as context:
        context.prec = 6
        b = await run_futures_research(value)
    assert a == b
    value.records[0].candles[0].volume = 999
    assert a.inputs.records[0].candles[0].volume == 10
    with pytest.raises(ValueError, match="dataset digest"):
        await run_futures_research(value)


@pytest.mark.parametrize("field", ["input_sha256", "partitions", "shared_source_sha256"])
async def test_envelope_identity_and_dependency_hashes_are_checked(field):
    run = await run_futures_research(request())
    payload = run.model_dump()
    if field == "input_sha256":
        payload[field] = "0" * 64
    elif field == "partitions":
        payload[field] = tuple(reversed(payload[field]))
    else:
        payload[field]["core/advisory/health.py"] = "0" * 64
    with pytest.raises(ValueError):
        await verify_futures_run(FuturesResearchRun.model_validate(payload))


@pytest.mark.parametrize(
    "problem", ["warmup", "identity", "capacity", "empty_partition", "partial_bar"]
)
async def test_bounded_inputs_and_fully_contained_partitions(problem):
    value = request()
    payload = value.model_dump()
    if problem == "warmup":
        payload["definition"]["parameters"]["minimum_bars"] = 501
        payload["definition"]["management"]["atr_window"] = 500
    elif problem == "identity":
        payload["records"][0]["instrument_id"] = "MNQ"
        payload["records"][0]["contract"] = "MNQZ26"
    elif problem == "capacity":
        payload["records"] = (payload["records"][0],) * 100
        # 24*100 is within the bar cap; use valid 500-bar records to exceed it.
        bars = payload["records"][0]["candles"]
        many = [
            dict(
                bars[0],
                open_time=START + timedelta(days=i),
                close_time=START + timedelta(days=i + 1, milliseconds=-1),
            )
            for i in range(500)
        ]
        row = dict(payload["records"][0], candles=many, fetched_at=many[-1]["close_time"])
        payload["records"] = (row,) * 21
    elif problem == "empty_partition":
        payload["records"][0]["candles"] = payload["records"][0]["candles"][:8]
        payload["records"][0]["quality"]["sequences"] = tuple(range(8))
    else:
        p = payload["definition"]["research"]["partitions"][0]
        p["start"] = value.records[0].candles[0].open_time + timedelta(hours=1)
        p["end"] = value.records[0].candles[0].close_time
    with pytest.raises(ValueError):
        if problem == "partial_bar":
            await run_futures_research(FuturesResearchInput.model_validate(payload))
        else:
            changed(value, **payload)


def chunks(value, changes):
    """Per-bar archive rows let faults be observed only at the affected cut."""
    rows = []
    for i, bar in enumerate(value.records[0].candles):
        row = value.records[0].model_dump()
        row["candles"] = [bar.model_dump()]
        row["fetched_at"] = bar.close_time
        row["quality"]["heartbeat_at"] = bar.close_time
        row["quality"]["sequences"] = (i,)
        rows.append(row)
    changes(rows)
    return changed(value, records=rows)


async def test_archive_chunking_retains_identical_outcomes_and_dependency():
    value = request()
    a = await run_futures_research(value)
    b = await run_futures_research(chunks(value, lambda rows: None))
    assert a.partitions == b.partitions
    assert a.input_sha256 != b.input_sha256  # Declared normalization includes chunk structure.


async def test_disconnection_during_position_censors_instead_of_inventing_pnl():
    value = request()

    def fault(rows):
        rows[3]["quality"]["provider_state"] = "disconnected"

    run = await run_futures_research(chunks(value, fault))
    first = run.partitions[0]
    assert first.state == "INCOMPLETE" and not first.trades
    assert first.censored[0].reason == "unknown_or_unhealthy_position_data"
    assert first.decisions[3].action == "CENSORED"
    assert all(p.state == "COMPLETE" for p in run.partitions[1:])


@pytest.mark.parametrize("kind", ["ENTRY", "EXIT"])
async def test_missing_session_authority_skips_or_censors_pending_open(kind):
    value = request()
    records = [value.records[0].model_dump()]
    index = 3 if kind == "ENTRY" else 5
    # A 2-second gap is outside explicit contiguous 1-second tolerance.
    records[0]["candles"][index]["open_time"] += timedelta(seconds=2)
    records[0]["candles"][index]["close_time"] += timedelta(seconds=2)
    records[0]["candles"][index + 1]["open_time"] += timedelta(seconds=3)
    records[0]["candles"][index + 1]["close_time"] += timedelta(seconds=3)
    # Keep the remaining stream ordered.
    for bar in records[0]["candles"][index + 2 :]:
        bar["open_time"] += timedelta(seconds=3)
        bar["close_time"] += timedelta(seconds=3)
    records[0]["fetched_at"] += timedelta(seconds=3)
    run = await run_futures_research(changed(value, records=records))
    first = run.partitions[0]
    assert not first.trades and first.state == "INCOMPLETE"
    fill = next(f for f in first.fills if f.kind == kind)
    assert fill.reason == "unverified_next_open_gap"
    assert fill.state == ("SKIPPED" if kind == "ENTRY" else "CENSORED")


async def test_nonpositive_exit_fill_censors_recorded_position():
    value = request(ticks=400)
    run = await run_futures_research(value)
    assert all(not p.trades and p.censored[0].reason == "invalid_exit_fill" for p in run.partitions)


async def test_unknown_atr_fault_censors_position_without_fabricating_a_loss(monkeypatch):
    import backtesting.futures as futures

    monkeypatch.setattr(futures, "seeded_range_atr", lambda bars, parameters: None)
    run = await run_futures_research(request())
    assert all(
        not p.trades and p.censored[0].reason == "unknown_management_geometry"
        for p in run.partitions
    )


@pytest.mark.parametrize("kind", ["ENTRY", "EXIT"])
async def test_partition_last_signal_never_consumes_following_partition_open(kind):
    value = request()
    payload = value.model_dump()
    p = payload["definition"]["research"]["partitions"][0]
    index = 2 if kind == "ENTRY" else 4
    p["end"] = value.records[0].candles[index].close_time
    run = await run_futures_research(FuturesResearchInput.model_validate(payload))
    first = run.partitions[0]
    assert first.state == "INCOMPLETE" and not first.trades
    assert first.fills[-1].kind == kind
    assert first.fills[-1].reason == "partition_end_without_next_open"
    assert len(first.censored) == (0 if kind == "ENTRY" else 1)


async def test_event_blackout_blocks_new_entry_but_does_not_hide_a_known_exit():
    value = request()
    rows = [c.model_dump() for c in value.calendars]
    for i in (4, 12, 20):
        c = rows[i]
        c["events"] = (
            dict(
                id="SYNTHETIC-macro",
                name="SYNTHETIC",
                known_at=c["observed_at"],
                scheduled_at=c["observed_at"],
                source="https://example.com/SYNTHETIC",
                affected_markets=("MES",),
                impact="high",
                status="scheduled",
            ),
        )
    run = await run_futures_research(changed(value, calendars=rows))
    for part in run.partitions:
        assert part.state == "INCOMPLETE" and len(part.trades) == 1
        assert part.decisions[4].event_risk.state == "BLOCKED"
        assert part.decisions[4].action == "EXIT_PENDING"


async def test_proposed_target_and_intrabar_stop_touches_do_not_invent_exits():
    value = request()
    records = [value.records[0].model_dump()]
    for i in (3, 11, 19):
        records[0]["candles"][i]["high"] = Decimal(150)
        records[0]["candles"][i]["low"] = Decimal(50)
    run = await run_futures_research(changed(value, records=records))
    for part in run.partitions:
        assert part.decisions[3].action == "HOLD"
        assert part.decisions[3].step.next_stop == part.trades[0].entry.initial_stop
        assert part.trades[0].exit_signal_at == part.decisions[4].at


@pytest.mark.parametrize("side", ["BUY", "SELL"])
async def test_outward_tick_rounding_keeps_structural_invalidation_and_ratchets(side):
    value = request(side=side)
    payload = value.model_dump()
    payload["definition"]["management"]["atr_stop_multiplier"] = Decimal("1.1")
    result = await run_futures_research(FuturesResearchInput.model_validate(payload))
    for p in result.partitions:
        t = p.trades[0]
        assert t.entry.raw_invalidation == (
            Decimal("99.05") if side == "BUY" else Decimal("100.95")
        )
        assert t.entry.initial_stop == (99 if side == "BUY" else 101)
        assert abs(t.entry.entry_fill - t.entry.initial_stop) >= abs(
            t.entry.entry_fill - t.entry.raw_invalidation
        )
        stops = [
            t.entry.initial_stop,
            *[d.step.next_stop for d in p.decisions if d.step and d.step.action == "HOLD"],
        ]
        assert stops == sorted(stops, reverse=side == "SELL")


async def test_profitable_close_exit_has_independently_calculated_net_result():
    value = request()
    records = [value.records[0].model_dump()]
    levels = [400, 400, 416, 424, 480, 440, 448, 440]
    for i, b in enumerate(records[0]["candles"]):
        level = Decimal(levels[i % 8]) * Decimal(".25")
        b.update(open=level, close=level, high=level + Decimal(".5"), low=level - Decimal(".5"))
        if i % 8 == 5:
            # Close 104 crosses the prior 105.5 ratchet; next open recovers to 112.
            b.update(close=Decimal(104), low=Decimal("103.5"))
    run = await run_futures_research(changed(value, records=records))
    for p in run.partitions:
        t = p.trades[0]
        # Entry 106.25, close-based exit at next open 112 minus .25 =111.75.
        assert t.entry.entry_fill == Decimal("106.25")
        assert t.exit_fill == Decimal("111.75")
        assert t.gross_usd == Decimal("27.5")
        assert t.net_usd == Decimal("25.5")
        assert t.net_r > 0


@given(fees=st.integers(min_value=0, max_value=100), ticks=st.integers(min_value=0, max_value=20))
@settings(max_examples=35, deadline=None)
async def test_costs_reduce_net_outcome_and_long_short_symmetry(fees, ticks):
    buy = await run_futures_research(request(commission=Decimal(fees), ticks=ticks))
    sell = await run_futures_research(request(side="SELL", commission=Decimal(fees), ticks=ticks))
    for b, s in zip(buy.partitions, sell.partitions, strict=True):
        assert (
            b.trades[0].net_usd
            == s.trades[0].net_usd
            == (-32 - 2 * ticks) * Decimal("1.25") - 2 * fees
        )
        assert b.trades[0].entry.initial_risk_usd == s.trades[0].entry.initial_risk_usd
        assert b.trades[0].net_r == s.trades[0].net_r
