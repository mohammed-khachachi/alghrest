"""Synthetic-only plans from the existing kernel. No fills, PnL or account engine."""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, localcontext
from typing import Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from backtesting.mes5m_spec import Closed, Money, ResearchSpec, Safety
from core.advisory.models import Candle, UTCDateTime, utc_instant
from core.strategy_signals import BreakoutParameters, VolumeBreakoutKernel

FIVE = timedelta(minutes=5)
TICK = Decimal("0.25")


class SyntheticWindow(Safety):
    origin: Literal["synthetic", "real_provider_sample"] = "synthetic"
    instrument: Literal["MES"] = "MES"
    contract: Literal["MESH26"] = "MESH26"
    interval: Literal["5m"] = "5m"
    candles: tuple[Candle, ...] = Field(max_length=84)


class ResearchState(Safety):
    shadow_equity: Money = Field(default=Decimal("25000"), gt=0)
    day_net_pnl: Money = Decimal("0")
    shadow_drawdown_floor: Money = Field(default=Decimal("23500"), gt=0, le=25000)
    exposure: Literal[
        "FLAT", "OPEN", "UNKNOWN", "WORKING_ORDERS", "MINI", "MIXED", "UNSUPPORTED"
    ] = "UNKNOWN"
    calendar_status: Literal["VERIFIED_SYNTHETIC", "UNKNOWN"] = "UNKNOWN"
    path_complete: StrictBool = False
    executed_entries: StrictInt = Field(default=0, ge=0)
    consecutive_losses: StrictInt = Field(default=0, ge=0)


class SignalPlan(Safety):
    schema_version: Literal["mes5m-qualification-v1"] = "mes5m-qualification-v1"
    scope: Literal["synthetic_signal_plan_only"] = "synthetic_signal_plan_only"
    origin: Literal["synthetic"] = "synthetic"
    decision: Literal["ABSTAIN", "SYNTHETIC_PLAN"]
    reasons: tuple[str, ...]
    at: UTCDateTime
    side: Literal["BUY", "SELL"] | None = None
    research_quantity: StrictInt = Field(default=0, ge=0, le=1)
    signal_close: Money | None = None
    stop: Money | None = None
    target: Money | None = None
    budget_usd: Money = Decimal("0")
    projected_risk_usd: Money | None = None
    scheduled_entry_at: UTCDateTime | None = None
    time_exit_at: UTCDateTime | None = None
    range_condition: Literal["EXPANDING", "NONEXPANDING"] | None = None
    fill_observed: Closed = False
    performance_observation_valid: Closed = False

    @model_validator(mode="after")
    def geometry_and_time(self) -> Self:
        if self.decision == "ABSTAIN":
            if self.research_quantity or any(
                v is not None
                for v in (
                    self.side,
                    self.signal_close,
                    self.stop,
                    self.target,
                    self.projected_risk_usd,
                    self.scheduled_entry_at,
                    self.time_exit_at,
                    self.range_condition,
                )
            ):
                raise ValueError("Abstention cannot carry an entry plan")
            return self
        if (
            self.research_quantity != 1
            or self.reasons
            or self.side is None
            or self.signal_close is None
            or self.stop is None
            or self.target is None
            or self.projected_risk_usd is None
            or self.range_condition is None
        ):
            raise ValueError("Incomplete synthetic plan")
        sign = 1 if self.side == "BUY" else -1
        distance = sign * (self.signal_close - self.stop)
        expected_entry = self.at + timedelta(seconds=60)
        expected_exit = min(
            expected_entry + timedelta(minutes=60),
            datetime.combine(self.at.date(), time(13, 55), UTC),
        )
        if (
            distance <= 0
            or min(self.signal_close, self.stop, self.target) <= 0
            or any(v % TICK for v in (self.signal_close, self.stop, self.target))
            or self.target != self.signal_close + sign * 2 * distance
            or self.projected_risk_usd != 5 * distance + 19
            or not 0 < self.projected_risk_usd <= self.budget_usd <= 100
            or self.scheduled_entry_at != expected_entry
            or self.time_exit_at != expected_exit
        ):
            raise ValueError("Synthetic plan violates frozen geometry, risk or timing")
        ResearchSpec().authorize_day(self.at.date())
        if (
            self.at.second
            or self.at.microsecond
            or self.at.minute % 5
            or not time(8, 5) <= self.at.time() < time(12, 55)
        ):
            raise ValueError("Synthetic decision outside the frozen window")
        return self


def risk_budget(state: ResearchState) -> Decimal:
    state = ResearchState.model_validate(state.model_dump())
    with localcontext() as context:
        context.prec = 96
        return max(
            Decimal(0),
            min(
                Decimal(100),
                Decimal("0.01") * state.shadow_equity,
                Decimal(200) + state.day_net_pnl,
                Decimal(450) + state.day_net_pnl,
                state.shadow_equity - state.shadow_drawdown_floor - Decimal(100),
            ),
        )


def propose_signal(window: SyntheticWindow, *, at: datetime, state: ResearchState) -> SignalPlan:
    window = SyntheticWindow.model_validate(window.model_dump())
    state = ResearchState.model_validate(state.model_dump())
    if window.origin != "synthetic":
        raise PermissionError("Historical signal generation is not authorized")
    at = utc_instant(at)
    ResearchSpec().authorize_day(at.date())
    bars = window.candles
    segment: list[Candle] = []
    previous = None
    for bar in bars:
        end = bar.open_time + FIVE
        if (
            bar.open_time.date() != at.date()
            or not time(7) <= bar.open_time.time() < time(14)
            or bar.open_time.minute % 5
            or bar.open_time.second
            or bar.open_time.microsecond
            or bar.close_time != end - timedelta(microseconds=1)
            or any(v % TICK for v in (bar.open, bar.high, bar.low, bar.close))
        ):
            raise ValueError("Invalid synthetic session, duration or tick")
        if end > at:
            raise ValueError("Future information is forbidden, including the final microsecond")
        if previous is not None:
            if bar.open_time <= previous:
                raise ValueError("Duplicate or unordered synthetic bars")
            if bar.open_time != previous + FIVE:
                segment = []
        previous = bar.open_time
        segment.append(bar)
    reasons = []
    if at.second or at.microsecond or at.minute % 5 or not time(8, 5) <= at.time() < time(12, 55):
        reasons.append("outside_decision_window")
    if state.calendar_status != "VERIFIED_SYNTHETIC":
        reasons.append("unknown_calendar")
    if state.exposure != "FLAT":
        reasons.append("nonflat_or_unknown_exposure")
    if not state.path_complete:
        reasons.append("incomplete_exposure_path")
    if state.executed_entries >= 2:
        reasons.append("daily_entry_limit")
    if state.consecutive_losses >= 5:
        reasons.append("loss_pause_no_automatic_resume")
    if len(segment) < 13:
        reasons.append("warmup_or_gap_reset")
    if not segment or segment[-1].open_time + FIVE != at:
        reasons.append("missing_latest_completed_bar")
    budget = risk_budget(state)
    if budget <= 0:
        reasons.append("no_risk_budget")
    if reasons:
        return SignalPlan(decision="ABSTAIN", reasons=tuple(reasons), at=at, budget_usd=budget)
    kernel = VolumeBreakoutKernel(
        BreakoutParameters(range_period=12, minimum_bars=13, volume_multiplier=Decimal("1.5"))
    )
    feature = kernel.evaluate(segment)
    assert feature is not None
    if feature.direction == "WAIT":
        return SignalPlan(decision="ABSTAIN", reasons=(feature.reason,), at=at, budget_usd=budget)
    with localcontext() as context:
        context.prec = 96
        current = segment[-1]
        sign = 1 if feature.direction == "BUY" else -1
        stop = current.low - TICK if sign == 1 else current.high + TICK
        distance = sign * (current.close - stop)
        projected = 5 * distance + 19  # $14 severe round-trip costs + $5 gap reserve.
        if stop <= 0 or projected > budget:
            return SignalPlan(
                decision="ABSTAIN",
                reasons=("risk_budget_below_one_contract",),
                at=at,
                budget_usd=budget,
            )
        prior = segment[-13:-1]
        expanding = sum((b.high - b.low for b in prior[-6:]), Decimal(0)) > sum(
            (b.high - b.low for b in prior[:6]), Decimal(0)
        )
        scheduled = at + timedelta(seconds=60)
        return SignalPlan(
            decision="SYNTHETIC_PLAN",
            reasons=(),
            at=at,
            side=feature.direction,
            research_quantity=1,
            signal_close=current.close,
            stop=stop,
            target=current.close + sign * 2 * distance,
            budget_usd=budget,
            projected_risk_usd=projected,
            scheduled_entry_at=scheduled,
            time_exit_at=min(
                scheduled + timedelta(minutes=60), datetime.combine(at.date(), time(13, 55), UTC)
            ),
            range_condition="EXPANDING" if expanding else "NONEXPANDING",
        )


def entry_timing_status(
    plan: SignalPlan,
    *,
    at: datetime,
    previous_minute_available: bool | None,
) -> Literal["NOT_DUE", "SCHEDULED_SYNTHETIC_ONLY", "INCOMPLETE"]:
    plan = SignalPlan.model_validate(plan.model_dump())
    at = utc_instant(at)
    if plan.decision != "SYNTHETIC_PLAN" or plan.scheduled_entry_at is None or at < plan.at:
        raise ValueError("Require a synthetic plan and a non-backdated event")
    if at < plan.scheduled_entry_at:
        return "NOT_DUE"
    if at != plan.scheduled_entry_at or previous_minute_available is not True:
        return "INCOMPLETE"
    return "SCHEDULED_SYNTHETIC_ONLY"


class ExposurePath(Safety):
    status: Literal["UNOBSERVED", "OPEN_REPORTED", "CLOSED_REPORTED", "INCOMPLETE"] = "UNOBSERVED"
    missing_data: StrictBool = False
    last_event_at: UTCDateTime
    reasons: tuple[str, ...] = ()
    performance_observation_valid: Closed = False

    @model_validator(mode="after")
    def unresolved_is_sticky(self) -> Self:
        if self.missing_data != (self.status == "INCOMPLETE"):
            raise ValueError("Missing exposure data must remain INCOMPLETE")
        return self


def record_unavailable(
    path: ExposurePath,
    *,
    at: datetime,
    operation: Literal["entry", "mark", "exit"],
) -> ExposurePath:
    path = ExposurePath.model_validate(path.model_dump())
    at = utc_instant(at)
    if at < path.last_event_at or operation not in {"entry", "mark", "exit"}:
        raise ValueError("Invalid missing-data event")
    return ExposurePath(
        status="INCOMPLETE",
        missing_data=True,
        last_event_at=at,
        reasons=(*path.reasons, f"unavailable_{operation}_no_fill_or_exit_inferred"),
    )
