"""Experimental per-contract futures outcomes from the shared guarded rules.

This is a closed-bar/next-open research model, not a broker-stop, allocation,
TCP25 or execution simulator. A proposed target never triggers an exit. Archive
claims are reported provenance; hashes do not authenticate licensing or approval.
"""

import hashlib
import json
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal, localcontext
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, StrictInt, model_validator

from backtesting.path_risk import LongestRunDistribution, LossStreakConfig, recorded_loss_run_tables
from connectors.advisory.replay import ReplayProvider
from core.advisory.analysis import breakout_research_check
from core.advisory.data import MarketDataQuery
from core.advisory.models import (
    CATALOG,
    Candle,
    EconomicCalendar,
    EventRiskPolicy,
    Instrument,
    MarketDataHealth,
    MarketSnapshot,
    Number,
    Price,
    UTCDateTime,
)
from core.advisory.selection import Evidence, LosingStreakEstimate, Nonnegative, Probability
from core.advisory.strategies import Digest, Identity, Reference, StrategyDefinition
from core.strategy_signals import (
    ATRTradePlan,
    ATRTradeStep,
    VolumeBreakoutFeatures,
    atr_trailing_step,
    seeded_range_atr,
)

Side = Literal["BUY", "SELL"]


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def futures_dataset_digest(records: tuple[MarketSnapshot, ...]) -> str:
    """Canonical ordered snapshot JSON, including quality; not a raw CSV digest."""
    return _sha(
        [MarketSnapshot.model_validate(r.model_dump()).model_dump(mode="json") for r in records]
    )


def strategy_source_digest() -> str:
    return hashlib.sha256(
        (Path(__file__).resolve().parents[1] / "core/strategy_signals.py").read_bytes()
    ).hexdigest()


class FuturesFillModel(Evidence):
    id: Identity
    version: Identity
    source_reference: Reference
    commission_per_side_usd: Nonnegative
    adverse_ticks_per_side: StrictInt = Field(ge=0, le=10000)
    method: Literal["close-decision-next-open-v1"] = "close-decision-next-open-v1"
    stop_rounding: Literal["outward-to-tick"] = "outward-to-tick"
    target_exit: Literal[False] = False


class FuturesResearchInput(Evidence):
    definition: StrategyDefinition
    instrument: Instrument
    records: tuple[MarketSnapshot, ...] = Field(min_length=1, max_length=100)
    calendars: tuple[EconomicCalendar, ...] = Field(default=(), max_length=10000)
    event_policy: EventRiskPolicy | None = None
    fills: FuturesFillModel

    @model_validator(mode="after")
    def joined(self) -> Self:
        definition = self.definition
        if definition.research is None or definition.management is None:
            raise ValueError("Futures research requires a declared split plan and management")
        if (
            self.instrument != CATALOG.get(self.instrument.id)
            or self.instrument.futures_spec is None
            or self.instrument.id not in definition.supported_markets
        ):
            raise ValueError("Research requires the exact supported catalog futures specification")
        keys = {(r.instrument_id, r.interval, r.contract) for r in self.records}
        if len(keys) != 1 or next(iter(keys))[:2] != (self.instrument.id, definition.interval):
            raise ValueError("Research requires one pinned dated daily contract stream")
        if sum(len(r.candles) for r in self.records) > 10000:
            raise ValueError("Research archive exceeds 10000 bars")
        if definition.research.dataset_sha256 != futures_dataset_digest(self.records):
            raise ValueError("Research dataset digest does not match captured snapshots")
        if definition.code_sha256 != strategy_source_digest():
            raise ValueError("Strategy source digest does not match the shared rule module")
        # Reuse archive ordering/duplicate/source/sequence/calendar validation.
        ReplayProvider(self.records, calendars=self.calendars)
        times = [b.close_time for r in self.records for b in r.candles]
        if any(
            not any(p.start <= t <= p.end for t in times) for p in definition.research.partitions
        ):
            raise ValueError("Every declared partition requires recorded observations")
        return self

    @property
    def revision(self) -> str:
        return _sha(self.model_dump(mode="json"))


class FuturesEntry(Evidence):
    side: Side
    signal_at: UTCDateTime
    entry_at: UTCDateTime
    entry_open: Price
    entry_fill: Price
    raw_invalidation: Price
    initial_stop: Price
    initial_risk_usd: Price


class FuturesTrade(Evidence):
    entry: FuturesEntry
    exit_signal_at: UTCDateTime
    exit_at: UTCDateTime
    exit_open: Price
    exit_fill: Price
    exit_stop: Price
    gross_usd: Number
    commission_usd: Nonnegative
    net_usd: Number
    net_r: Number


class CensoredFuturesPosition(Evidence):
    entry: FuturesEntry
    censored_at: UTCDateTime
    last_stop: Price
    reason: Identity


class FuturesEventCheck(Evidence):
    """Guard result summary; full calendar/policy captured once in run inputs."""

    state: Literal["CLEAR", "BLOCKED", "UNKNOWN"]
    guard_version: Literal["economic-event-guard-v1"]
    scope: Literal["internal_research_risk"]
    assessed_at: UTCDateTime | None
    reasons: tuple[str, ...]
    blocked_event_ids: tuple[str, ...]
    trade_permitted: Literal[False] = False


class FuturesDecision(Evidence):
    at: UTCDateTime
    snapshot_sha256: Digest
    calendar_sha256: Digest | None
    data_health: MarketDataHealth
    event_risk: FuturesEventCheck
    features: VolumeBreakoutFeatures | None
    geometry: ATRTradePlan | None
    step: ATRTradeStep | None
    action: Literal["WAIT", "ENTRY_PENDING", "HOLD", "EXIT_PENDING", "BLOCKED", "CENSORED"]


class FuturesFillObservation(Evidence):
    signal_at: UTCDateTime
    observed_at: UTCDateTime
    kind: Literal["ENTRY", "EXIT"]
    state: Literal["FILLED", "SKIPPED", "CENSORED"]
    reason: Identity


class FuturesPartitionRun(Evidence):
    role: Literal["TRAIN", "VALIDATION", "OOS"]
    decisions: tuple[FuturesDecision, ...]
    fills: tuple[FuturesFillObservation, ...]
    trades: tuple[FuturesTrade, ...]
    censored: tuple[CensoredFuturesPosition, ...]
    state: Literal["COMPLETE", "INCOMPLETE"]


class FuturesResearchRun(Evidence):
    format_version: Literal["futures-outcomes-v1"] = "futures-outcomes-v1"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    scope: Literal["per_contract_closed_bar_research"] = "per_contract_closed_bar_research"
    inputs: FuturesResearchInput
    input_sha256: Digest
    runner_sha256: Digest
    shared_source_sha256: dict[str, Digest]
    partitions: tuple[FuturesPartitionRun, FuturesPartitionRun, FuturesPartitionRun]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def identity(self) -> Self:
        if self.input_sha256 != self.inputs.revision:
            raise ValueError("Captured futures input digest mismatch")
        if tuple(p.role for p in self.partitions) != ("TRAIN", "VALIDATION", "OOS"):
            raise ValueError("Futures results require the declared partition order")
        return self


def _stop(raw: Decimal, side: Side, tick: Decimal) -> Decimal:
    return (raw / tick).to_integral_value(
        rounding=ROUND_FLOOR if side == "BUY" else ROUND_CEILING
    ) * tick


def _fill(open_price: Decimal, side: Side, inputs: FuturesResearchInput, *, entry: bool) -> Decimal:
    sign = 1 if (side == "BUY") == entry else -1
    return open_price + sign * inputs.fills.adverse_ticks_per_side * inputs.instrument.tick_size


async def run_futures_research(inputs: FuturesResearchInput) -> FuturesResearchRun:
    """Detached inputs; each partition starts flat, with prior prices for warmup.

    Fills use only the following recorded open, before its close is inspected.
    Gaps over one second lack session authority and are never forward-filled.
    Unknown in-position data censors the path; it never fabricates a realized PnL.
    """
    inputs = FuturesResearchInput.model_validate(inputs.model_dump(warnings=False))
    with localcontext() as context:
        context.prec = 80
        return await _run(inputs)


async def _run(inputs: FuturesResearchInput) -> FuturesResearchRun:
    provider = ReplayProvider(inputs.records, calendars=inputs.calendars)
    definition = inputs.definition
    assert definition.research is not None and definition.management is not None
    management = definition.management
    instrument = inputs.instrument
    bars = [b for r in inputs.records for b in r.candles]
    contract = inputs.records[0].contract
    partitions = []
    for partition in definition.research.partitions:
        decisions: list[FuturesDecision] = []
        fills: list[FuturesFillObservation] = []
        trades: list[FuturesTrade] = []
        censored: list[CensoredFuturesPosition] = []
        position: FuturesEntry | None = None
        stop: Decimal | None = None
        pending: ATRTradePlan | datetime | None = None
        prior: Candle | None = None
        incomplete = False
        selected = [
            bar
            for bar in bars
            if partition.start <= bar.open_time and bar.close_time <= partition.end
        ]
        if not selected:
            raise ValueError("Partition requires at least one fully contained bar")
        for bar in selected:
            if pending is not None:
                assert prior is not None
                kind: Literal["ENTRY", "EXIT"] = (
                    "ENTRY" if isinstance(pending, ATRTradePlan) else "EXIT"
                )
                gap = (bar.open_time - prior.close_time).total_seconds()
                reason = "unverified_next_open_gap" if not 0 < gap <= 1 else "next_open"
                if isinstance(pending, ATRTradePlan):
                    entry_fill = _fill(bar.open, pending.side, inputs, entry=True)
                    rounded = _stop(pending.invalidation, pending.side, instrument.tick_size)
                    if reason == "next_open" and (
                        rounded <= 0
                        or entry_fill <= 0
                        or not (rounded < bar.open if pending.side == "BUY" else rounded > bar.open)
                        or not (
                            rounded < entry_fill if pending.side == "BUY" else rounded > entry_fill
                        )
                    ):
                        reason = "invalid_entry_after_gap_or_tick_rounding"
                    if reason == "next_open":
                        unit_risk = (
                            abs(entry_fill - rounded) * instrument.point_value
                            + inputs.fills.adverse_ticks_per_side * instrument.tick_value
                            + 2 * inputs.fills.commission_per_side_usd
                        )
                        position = FuturesEntry(
                            side=pending.side,
                            signal_at=prior.close_time,
                            entry_at=bar.open_time,
                            entry_open=bar.open,
                            entry_fill=entry_fill,
                            raw_invalidation=pending.invalidation,
                            initial_stop=rounded,
                            initial_risk_usd=unit_risk,
                        )
                        stop = rounded
                    fills.append(
                        FuturesFillObservation(
                            signal_at=prior.close_time,
                            observed_at=bar.open_time,
                            kind=kind,
                            state="FILLED" if reason == "next_open" else "SKIPPED",
                            reason=reason,
                        )
                    )
                else:
                    assert position is not None and stop is not None
                    exit_fill = _fill(bar.open, position.side, inputs, entry=False)
                    if reason == "next_open" and exit_fill <= 0:
                        reason = "invalid_exit_fill"
                    if reason == "next_open":
                        gross = (
                            (exit_fill - position.entry_fill)
                            * (1 if position.side == "BUY" else -1)
                            * instrument.point_value
                        )
                        commission = 2 * inputs.fills.commission_per_side_usd
                        trades.append(
                            FuturesTrade(
                                entry=position,
                                exit_signal_at=pending,
                                exit_at=bar.open_time,
                                exit_open=bar.open,
                                exit_fill=exit_fill,
                                exit_stop=stop,
                                gross_usd=gross,
                                commission_usd=commission,
                                net_usd=gross - commission,
                                net_r=(gross - commission) / position.initial_risk_usd,
                            )
                        )
                    else:
                        censored.append(
                            CensoredFuturesPosition(
                                entry=position,
                                censored_at=bar.open_time,
                                last_stop=stop,
                                reason=reason,
                            )
                        )
                    fills.append(
                        FuturesFillObservation(
                            signal_at=pending,
                            observed_at=bar.open_time,
                            kind=kind,
                            state="FILLED" if reason == "next_open" else "CENSORED",
                            reason=reason,
                        )
                    )
                    position, stop = None, None
                incomplete |= reason != "next_open"
                pending = None
            snapshot = await provider.read(
                MarketDataQuery(
                    instrument_id=instrument.id,
                    interval=definition.interval,
                    contract=contract,
                    as_of=bar.close_time,
                    max_bars=max(management.atr_window, definition.parameters.minimum_bars),
                )
            )
            calendar = provider.calendar(instrument.id, bar.close_time)
            check = breakout_research_check(
                instrument.id,
                definition.interval,
                snapshot,
                parameters=definition.parameters,
                now=bar.close_time,
                calendar=calendar,
                event_policy=inputs.event_policy,
                management_parameters=management,
            )
            step = None
            action: Literal[
                "WAIT", "ENTRY_PENDING", "HOLD", "EXIT_PENDING", "BLOCKED", "CENSORED"
            ] = "WAIT"
            if check.data_health.state != "HEALTHY":
                incomplete = True
                action = "BLOCKED"
                if position is not None:
                    assert stop is not None
                    censored.append(
                        CensoredFuturesPosition(
                            entry=position,
                            censored_at=bar.close_time,
                            last_stop=stop,
                            reason="unknown_or_unhealthy_position_data",
                        )
                    )
                    position, stop = None, None
                    action = "CENSORED"
            elif position is not None:
                assert snapshot is not None and stop is not None
                # Event restrictions block entries, never suppress a known exit.
                step = atr_trailing_step(
                    position.side,
                    bar.close,
                    stop,
                    seeded_range_atr(snapshot.candles, management),
                    management,
                )
                if step.action == "EXIT":
                    pending = bar.close_time
                    action = "EXIT_PENDING"
                elif step.action == "HOLD":
                    stop = _stop(step.next_stop, position.side, instrument.tick_size)
                    action = "HOLD"
                else:
                    censored.append(
                        CensoredFuturesPosition(
                            entry=position,
                            censored_at=bar.close_time,
                            last_stop=stop,
                            reason="unknown_management_geometry",
                        )
                    )
                    position, stop = None, None
                    action = "CENSORED"
                    incomplete = True
            elif check.management is not None:
                pending = check.management
                action = "ENTRY_PENDING"
            elif check.state == "NO_TRADE":
                action = "BLOCKED"
            incomplete |= check.event_risk.state != "CLEAR"
            decisions.append(
                FuturesDecision(
                    at=bar.close_time,
                    snapshot_sha256=_sha(snapshot.model_dump(mode="json") if snapshot else None),
                    calendar_sha256=_sha(calendar.model_dump(mode="json")) if calendar else None,
                    data_health=check.data_health,
                    event_risk=FuturesEventCheck.model_validate(
                        check.event_risk.model_dump(exclude={"calendar", "policy"})
                    ),
                    features=check.features,
                    geometry=check.management,
                    step=step,
                    action=action,
                )
            )
            prior = bar
        assert prior is not None
        if position is not None:
            assert stop is not None
            censored.append(
                CensoredFuturesPosition(
                    entry=position,
                    censored_at=prior.close_time,
                    last_stop=stop,
                    reason="partition_end_open_position",
                )
            )
        if pending is not None:
            fills.append(
                FuturesFillObservation(
                    signal_at=prior.close_time,
                    observed_at=prior.close_time,
                    kind="ENTRY" if isinstance(pending, ATRTradePlan) else "EXIT",
                    state="SKIPPED" if isinstance(pending, ATRTradePlan) else "CENSORED",
                    reason="partition_end_without_next_open",
                )
            )
        partitions.append(
            FuturesPartitionRun(
                role=partition.role,
                decisions=tuple(decisions),
                fills=tuple(fills),
                trades=tuple(trades),
                censored=tuple(censored),
                state="INCOMPLETE" if incomplete or censored or pending else "COMPLETE",
            )
        )
    return FuturesResearchRun(
        inputs=inputs,
        input_sha256=inputs.revision,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        shared_source_sha256={
            name: hashlib.sha256(
                (Path(__file__).resolve().parents[1] / name).read_bytes()
            ).hexdigest()
            for name in (
                "core/strategy_signals.py",
                "core/advisory/analysis.py",
                "core/advisory/models.py",
                "core/advisory/health.py",
                "core/advisory/events.py",
                "core/advisory/data.py",
                "core/advisory/strategies.py",
                "core/advisory/selection.py",
                "connectors/advisory/replay.py",
                "backtesting/path_risk.py",
            )
        },
        partitions=(partitions[0], partitions[1], partitions[2]),
    )


async def verify_futures_run(value: FuturesResearchRun) -> FuturesResearchRun:
    """Revalidate AND replay every recorded outcome before using saved evidence.

    Constructor validation alone is not full path verification. Changed code,
    catalog, inputs, decisions, costs, fills, censored paths or PnL are rejected.
    """
    value = FuturesResearchRun.model_validate(value.model_dump(warnings=False))
    replayed = await run_futures_research(value.inputs)
    if value.model_dump(mode="json") != replayed.model_dump(mode="json"):
        raise ValueError("Futures research replay mismatch")
    return replayed


class DrawdownRecovery(Evidence):
    """Closed-trade additive R path; no intratrade or allocated NAV assumption."""

    peak_trade: StrictInt = Field(ge=0)
    trough_trade: StrictInt = Field(ge=1)
    recovery_trade: StrictInt | None = Field(default=None, ge=1)
    observed_until_trade: StrictInt = Field(ge=1)
    peak_at: UTCDateTime
    trough_at: UTCDateTime
    observed_until_at: UTCDateTime
    depth_r: Nonnegative
    underwater_trades: StrictInt = Field(ge=1)
    elapsed_calendar_days: Nonnegative


class NetFuturesMetrics(Evidence):
    observations: StrictInt = Field(ge=1)
    winners: StrictInt = Field(ge=0)
    losers: StrictInt = Field(ge=0)
    flat: StrictInt = Field(ge=0)
    win_rate: Probability
    average_winner_r: Number | None
    average_loser_r: Number | None
    expectancy_r: Number
    median_r: Number
    sample_variance_r_squared: Nonnegative | None
    sample_standard_deviation_r: Nonnegative | None
    adjusted_sample_skew: Number | None
    minimum_r: Number
    maximum_r: Number
    quantile05_r: Number
    empirical_es95_loss_r: Nonnegative
    profit_factor_r: Nonnegative | None
    profit_factor_usd: Nonnegative | None
    profit_factor_state: Literal["FINITE", "UNDEFINED_NO_LOSSES", "UNDEFINED_ALL_FLAT"]
    total_net_usd: Number
    total_commission_usd: Nonnegative
    total_adverse_slippage_usd: Nonnegative
    max_closed_trade_drawdown_r: Nonnegative
    max_closed_trade_drawdown_usd: Nonnegative
    unrecovered_drawdown_r: Nonnegative
    max_underwater_trades: StrictInt = Field(ge=0)
    longest_nonpositive_run: StrictInt = Field(ge=0)
    recoveries: tuple[DrawdownRecovery, ...]


class FuturesLossRuns(Evidence):
    algorithm_version: Literal["recorded-loss-runs-v1"] = "recorded-loss-runs-v1"
    loss_definition: Literal["net_futures_outcome_lte_zero"] = "net_futures_outcome_lte_zero"
    bootstrap_method: Literal["non_circular_contiguous_blocks"] = "non_circular_contiguous_blocks"
    state: Literal["CALCULATED", "UNKNOWN"]
    reasons: tuple[str, ...]
    empirical_loss_fraction: Probability | None
    iid_baseline: tuple[LosingStreakEstimate, ...]
    bootstrap: tuple[LosingStreakEstimate, ...]
    longest_runs: tuple[LongestRunDistribution, ...]


class FuturesPartitionEdge(Evidence):
    role: Literal["TRAIN", "VALIDATION", "OOS"]
    state: Literal["CALCULATED", "UNKNOWN"]
    reasons: tuple[str, ...]
    metrics: NetFuturesMetrics | None
    loss_runs: FuturesLossRuns


# Internal unit-neutral drawdown observations: peak, trough, recovery, end, depth.
DrawdownRow = tuple[int, int, int | None, int, Decimal]


def _drawdown_path(values: tuple[Decimal, ...]) -> tuple[Decimal, Decimal, tuple[DrawdownRow, ...]]:
    peak = cumulative = maximum = Decimal(0)
    peak_index = trough_index = 0
    trough = Decimal(0)
    underwater = False
    rows: list[DrawdownRow] = []
    for index, value in enumerate(values, 1):
        cumulative += value
        maximum = max(maximum, peak - cumulative)
        if cumulative < peak:
            if not underwater:
                trough, trough_index = cumulative, index
                underwater = True
            elif cumulative < trough:
                trough, trough_index = cumulative, index
        else:
            if underwater:
                rows.append((peak_index, trough_index, index, index, peak - trough))
                underwater = False
            peak, peak_index = cumulative, index
    if underwater:
        rows.append((peak_index, trough_index, None, len(values), peak - trough))
    return maximum, peak - cumulative, tuple(rows)


def _net_metrics(
    trades: tuple[FuturesTrade, ...], *, start: datetime, point_value: Decimal
) -> NetFuturesMetrics:
    outcomes = tuple(t.net_r for t in trades)
    n = len(outcomes)
    winners = tuple(v for v in outcomes if v > 0)
    losers = tuple(v for v in outcomes if v < 0)
    ordered = sorted(outcomes)
    mean = sum(outcomes, Decimal(0)) / n
    m2 = sum(((v - mean) ** 2 for v in outcomes), Decimal(0))
    variance = m2 / (n - 1) if n > 1 else None
    standard_deviation = variance.sqrt() if variance is not None else None
    skew = None
    if n >= 3 and m2 > 0:
        population_variance = m2 / n
        m3 = sum(((v - mean) ** 3 for v in outcomes), Decimal(0)) / n
        skew = (Decimal(n * (n - 1)).sqrt() / (n - 2)) * m3 / population_variance.sqrt() ** 3
    median = ordered[n // 2] if n % 2 else (ordered[n // 2 - 1] + ordered[n // 2]) / 2
    tail_mass = Decimal(n) * Decimal("0.05")
    rank = int(tail_mass.to_integral_value(rounding=ROUND_CEILING))
    remaining, tail_sum = tail_mass, Decimal(0)
    for value in ordered[:rank]:
        weight = min(Decimal(1), remaining)
        tail_sum += value * weight
        remaining -= weight
    gross_loss_r = -sum(losers, Decimal(0))
    loss_usd = -sum((t.net_usd for t in trades if t.net_usd < 0), Decimal(0))
    gain_usd = sum((t.net_usd for t in trades if t.net_usd > 0), Decimal(0))
    drawdown, unrecovered, rows = _drawdown_path(outcomes)
    recoveries = []
    for peak, trough, recovery, end, depth in rows:
        peak_at = start if peak == 0 else trades[peak - 1].exit_at
        end_at = trades[end - 1].exit_at
        elapsed = end_at - peak_at
        days = (
            Decimal(elapsed.days)
            + Decimal(elapsed.seconds) / 86400
            + Decimal(elapsed.microseconds) / 86400000000
        )
        recoveries.append(
            DrawdownRecovery(
                peak_trade=peak,
                trough_trade=trough,
                recovery_trade=recovery,
                observed_until_trade=end,
                peak_at=peak_at,
                trough_at=trades[trough - 1].exit_at,
                observed_until_at=end_at,
                depth_r=depth,
                underwater_trades=end - peak,
                elapsed_calendar_days=days,
            )
        )
    trailing = longest = 0
    for value in outcomes:
        trailing = trailing + 1 if value <= 0 else 0
        longest = max(longest, trailing)
    return NetFuturesMetrics(
        observations=n,
        winners=len(winners),
        losers=len(losers),
        flat=n - len(winners) - len(losers),
        win_rate=Decimal(len(winners)) / n,
        average_winner_r=sum(winners, Decimal(0)) / len(winners) if winners else None,
        average_loser_r=sum(losers, Decimal(0)) / len(losers) if losers else None,
        expectancy_r=mean,
        median_r=median,
        sample_variance_r_squared=variance,
        sample_standard_deviation_r=standard_deviation,
        adjusted_sample_skew=skew,
        minimum_r=ordered[0],
        maximum_r=ordered[-1],
        quantile05_r=ordered[rank - 1],
        empirical_es95_loss_r=max(Decimal(0), -tail_sum / tail_mass),
        profit_factor_r=sum(winners, Decimal(0)) / gross_loss_r if gross_loss_r else None,
        profit_factor_usd=gain_usd / loss_usd if loss_usd else None,
        profit_factor_state=(
            "FINITE" if losers else "UNDEFINED_NO_LOSSES" if winners else "UNDEFINED_ALL_FLAT"
        ),
        total_net_usd=sum((t.net_usd for t in trades), Decimal(0)),
        total_commission_usd=sum((t.commission_usd for t in trades), Decimal(0)),
        total_adverse_slippage_usd=sum(
            (
                (abs(t.entry.entry_fill - t.entry.entry_open) + abs(t.exit_fill - t.exit_open))
                * point_value
                for t in trades
            ),
            Decimal(0),
        ),
        max_closed_trade_drawdown_r=drawdown,
        max_closed_trade_drawdown_usd=_drawdown_path(tuple(t.net_usd for t in trades))[0],
        unrecovered_drawdown_r=unrecovered,
        max_underwater_trades=max((r.underwater_trades for r in recoveries), default=0),
        longest_nonpositive_run=longest,
        recoveries=tuple(recoveries),
    )


def _edge_partitions(
    source: FuturesResearchRun, configuration: LossStreakConfig
) -> tuple[FuturesPartitionEdge, FuturesPartitionEdge, FuturesPartitionEdge]:
    research = source.inputs.definition.research
    assert research is not None
    partitions = []
    with localcontext() as context:
        context.prec = 80
        for result, partition in zip(source.partitions, research.partitions, strict=True):
            reason = (
                "incomplete_futures_partition"
                if result.state != "COMPLETE"
                else "missing_closed_futures_outcomes" if not result.trades else None
            )
            metrics = None
            if reason is None:
                metrics = _net_metrics(
                    result.trades,
                    start=partition.start,
                    point_value=source.inputs.instrument.point_value,
                )
            path_reason = reason or (
                "block_exceeds_recorded_futures_outcomes"
                if configuration.block_length > len(result.trades)
                else None
            )
            if path_reason is not None:
                path = FuturesLossRuns(
                    state="UNKNOWN",
                    reasons=(path_reason,),
                    empirical_loss_fraction=None,
                    iid_baseline=(),
                    bootstrap=(),
                    longest_runs=(),
                )
            else:
                fraction, iid, bootstrap, longest = recorded_loss_run_tables(
                    tuple(t.net_r for t in result.trades), configuration=configuration
                )
                path = FuturesLossRuns(
                    state="CALCULATED",
                    reasons=(),
                    empirical_loss_fraction=fraction,
                    iid_baseline=iid,
                    bootstrap=bootstrap,
                    longest_runs=longest,
                )
            partitions.append(
                FuturesPartitionEdge(
                    role=result.role,
                    state="UNKNOWN" if reason else "CALCULATED",
                    reasons=(reason,) if reason else (),
                    metrics=metrics,
                    loss_runs=path,
                )
            )
    return partitions[0], partitions[1], partitions[2]


class FuturesEdgeStudy(Evidence):
    algorithm_version: Literal["futures-net-outcome-statistics-v1"] = (
        "futures-net-outcome-statistics-v1"
    )
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    validation_state: Literal["UNVALIDATED"] = "UNVALIDATED"
    scope: Literal["descriptive_net_contract_outcomes"] = "descriptive_net_contract_outcomes"
    source: FuturesResearchRun
    source_sha256: Digest
    configuration: LossStreakConfig
    partitions: tuple[FuturesPartitionEdge, FuturesPartitionEdge, FuturesPartitionEdge]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def reproduce_statistics(self) -> Self:
        if self.source_sha256 != _sha(self.source.model_dump(mode="json")):
            raise ValueError("Futures edge source digest mismatch")
        if self.partitions != _edge_partitions(self.source, self.configuration):
            raise ValueError("Futures edge statistics must reproduce captured net outcomes")
        return self


async def futures_edge_analysis(
    source: FuturesResearchRun, *, configuration: LossStreakConfig
) -> FuturesEdgeStudy:
    """Replay verified outcomes first; computed statistics confer no approval.

    Each split remains separate. Incomplete paths have no cherry-picked metrics.
    Loss-run probabilities are conditional research estimates, not TCP25 fit,
    confidence bounds on positive expectancy or proof of an untuned holdout.
    """
    configuration = LossStreakConfig.model_validate(configuration.model_dump(warnings=False))
    source = await verify_futures_run(source)
    return FuturesEdgeStudy(
        source=source,
        source_sha256=_sha(source.model_dump(mode="json")),
        configuration=configuration,
        partitions=_edge_partitions(source, configuration),
    )


async def verify_futures_edge_study(value: FuturesEdgeStudy) -> FuturesEdgeStudy:
    """Saved statistics require both source-path replay and summary validation."""
    value = FuturesEdgeStudy.model_validate(value.model_dump(warnings=False))
    return await futures_edge_analysis(value.source, configuration=value.configuration)
