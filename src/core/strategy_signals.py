"""Pure directional rules reused by agents and guarded research, never sizing.

These calculations have no clock, provider, state or order capability. Callers
must first establish closed, valid point-in-time data. No approval is implied.
"""

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation, localcontext
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator


class PriceBar(Protocol):
    @property
    def high(self) -> Decimal | float: ...
    @property
    def low(self) -> Decimal | float: ...
    @property
    def close(self) -> Decimal | float: ...
    @property
    def volume(self) -> Decimal | float: ...


class BreakoutParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    range_period: StrictInt = Field(ge=1)
    minimum_bars: StrictInt = Field(ge=2)
    volume_multiplier: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def history(self) -> Self:
        if self.minimum_bars <= self.range_period:
            raise ValueError("Warmup must include the previous range and current closed bar")
        return self


class VolumeBreakoutFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    direction: Literal["BUY", "SELL", "WAIT"]
    reason: Literal[
        "above_range",
        "below_range",
        "inside_range",
        "volume_not_confirmed",
        "unknown_volume_baseline",
    ]
    close: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    volume: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]
    previous_high: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    previous_low: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    previous_average_volume: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class DirectionalKernel(Protocol):
    @property
    def strategy_id(self) -> str: ...
    @property
    def version(self) -> str: ...
    def evaluate(self, bars: Sequence[PriceBar]) -> VolumeBreakoutFeatures | None: ...


class VolumeBreakoutKernel:
    strategy_id = "breakout_hunter_volume"
    version = "range-volume-v1"

    def __init__(self, parameters: BreakoutParameters) -> None:
        self.parameters = BreakoutParameters.model_validate(parameters.model_dump())

    def evaluate(self, bars: Sequence[PriceBar]) -> VolumeBreakoutFeatures | None:
        parameters = BreakoutParameters.model_validate(self.parameters.model_dump())
        if len(bars) < parameters.minimum_bars:
            return None
        # The current close is compared with all immediately preceding N bars.
        window = bars[-parameters.range_period - 1 :]
        highs, lows, closes, volumes = [], [], [], []
        for bar in window:
            try:
                high, low, close, volume = (
                    Decimal(str(value)) for value in (bar.high, bar.low, bar.close, bar.volume)
                )
            except (InvalidOperation, ValueError, TypeError, AttributeError) as exc:
                raise ValueError("Invalid numeric breakout bar") from exc
            if (
                not all(value.is_finite() for value in (high, low, close, volume))
                or not 0 < low <= close <= high
                or volume < 0
            ):
                raise ValueError(
                    "Breakout bars require finite positive prices and nonnegative volume"
                )
            highs.append(high)
            lows.append(low)
            closes.append(close)
            volumes.append(volume)
        previous_high, previous_low = max(highs[:-1]), min(lows[:-1])
        average_volume = sum(volumes[:-1], Decimal(0)) / parameters.range_period
        close, volume = closes[-1], volumes[-1]
        direction: Literal["BUY", "SELL", "WAIT"] = "WAIT"
        reason: Literal[
            "above_range",
            "below_range",
            "inside_range",
            "volume_not_confirmed",
            "unknown_volume_baseline",
        ]
        if average_volume <= 0:
            reason = "unknown_volume_baseline"
        elif volume < parameters.volume_multiplier * average_volume:
            reason = "volume_not_confirmed"
        elif close > previous_high:
            direction, reason = "BUY", "above_range"
        elif close < previous_low:
            direction, reason = "SELL", "below_range"
        else:
            reason = "inside_range"
        return VolumeBreakoutFeatures(
            direction=direction,
            reason=reason,
            close=close,
            volume=volume,
            previous_high=previous_high,
            previous_low=previous_low,
            previous_average_volume=average_volume,
        )


class ATRManagementParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    atr_period: StrictInt = Field(ge=1, le=499)
    atr_window: StrictInt = Field(ge=2, le=500)
    atr_stop_multiplier: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    proposed_target_r: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    atr_method: Literal["seeded-rma-no-epsilon-v1"] = "seeded-rma-no-epsilon-v1"
    exit_rule: Literal["strict-close-trailing-stop"] = "strict-close-trailing-stop"

    @model_validator(mode="after")
    def history(self) -> Self:
        if self.atr_window <= self.atr_period:
            raise ValueError("ATR window must include seed and a subsequent observation")
        return self


def _decimal_price(value: Decimal | float) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("Invalid numeric management price") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError("Management prices and volatility must be finite and positive")
    return result


def seeded_range_atr(
    bars: Sequence[PriceBar], parameters: ATRManagementParameters
) -> Decimal | None:
    """First range is high-low; seed first N ranges, then RMA without epsilon.

    This pins the inspected pandas-ta non-TA-Lib convention. A rolling caller
    recomputes the seed from the configured bounded history, as the agent did.
    """
    parameters = ATRManagementParameters.model_validate(parameters.model_dump())
    window = bars[-parameters.atr_window :]
    if len(window) <= parameters.atr_period:
        return None
    with localcontext() as context:
        context.prec = 50
        ranges = []
        previous = None
        for bar in window:
            high, low, close = (_decimal_price(value) for value in (bar.high, bar.low, bar.close))
            if not low <= close <= high:
                raise ValueError("Invalid management bar range")
            ranges.append(
                high - low
                if previous is None
                else max(high - low, abs(high - previous), abs(low - previous))
            )
            previous = close
        atr = sum(ranges[: parameters.atr_period], Decimal(0)) / parameters.atr_period
        for value in ranges[parameters.atr_period :]:
            atr = ((parameters.atr_period - 1) * atr + value) / parameters.atr_period
    return atr if atr > 0 else None


def close_crossed_stop(side: Literal["BUY", "SELL"], close: Decimal, stop: Decimal) -> bool:
    if side not in {"BUY", "SELL"}:
        raise ValueError("Unknown management position side")
    close, stop = _decimal_price(close), _decimal_price(stop)
    return close < stop if side == "BUY" else close > stop


def _entry_levels(
    side: Literal["BUY", "SELL"], entry: Decimal, atr: Decimal, parameters: ATRManagementParameters
) -> tuple[Decimal, Decimal, Decimal]:
    if side not in {"BUY", "SELL"}:
        raise ValueError("Unknown management entry side")
    with localcontext() as context:
        context.prec = 80
        distance = atr * parameters.atr_stop_multiplier
        stop = entry - distance if side == "BUY" else entry + distance
        target_distance = parameters.proposed_target_r * distance
        target = entry + target_distance if side == "BUY" else entry - target_distance
        if (
            not (0 < stop < entry < target if side == "BUY" else 0 < target < entry < stop)
            or abs(entry - stop) != distance
            or abs(target - entry) != target_distance
        ):
            raise ValueError(
                "ATR geometry must be positive, directional and numerically representable"
            )
    return distance, stop, target


class ATRTradePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    management_version: Literal["atr-close-trail-v1"] = "atr-close-trail-v1"
    scope: Literal["experimental_unrounded_atr_geometry"] = "experimental_unrounded_atr_geometry"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    parameters: ATRManagementParameters
    side: Literal["BUY", "SELL"]
    entry: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    atr: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    stop_distance: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    invalidation: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    proposed_target: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def geometry(self) -> Self:
        if (self.stop_distance, self.invalidation, self.proposed_target) != _entry_levels(
            self.side, self.entry, self.atr, self.parameters
        ):
            raise ValueError("ATR entry geometry must reproduce from its parameters")
        return self


def atr_entry_plan(
    side: Literal["BUY", "SELL"], entry: Decimal, atr: Decimal, parameters: ATRManagementParameters
) -> ATRTradePlan:
    parameters = ATRManagementParameters.model_validate(parameters.model_dump())
    entry, atr = _decimal_price(entry), _decimal_price(atr)
    distance, stop, target = _entry_levels(side, entry, atr, parameters)
    return ATRTradePlan(
        parameters=parameters,
        side=side,
        entry=entry,
        atr=atr,
        stop_distance=distance,
        invalidation=stop,
        proposed_target=target,
    )


def _trailing_step(
    side: Literal["BUY", "SELL"],
    close: Decimal,
    previous_stop: Decimal,
    atr: Decimal | None,
    parameters: ATRManagementParameters,
) -> tuple[Literal["EXIT", "HOLD", "NO_TRADE"], Decimal, str]:
    if close_crossed_stop(side, close, previous_stop):
        return "EXIT", previous_stop, "close_crossed_existing_stop"
    if atr is None:
        return "NO_TRADE", previous_stop, "unknown_atr"
    with localcontext() as context:
        context.prec = 80
        candidate = (
            close - parameters.atr_stop_multiplier * atr
            if side == "BUY"
            else close + parameters.atr_stop_multiplier * atr
        )
    if not (candidate < close if side == "BUY" else candidate > close):
        return "NO_TRADE", previous_stop, "unrepresentable_trailing_geometry"
    return (
        "HOLD",
        max(previous_stop, candidate) if side == "BUY" else min(previous_stop, candidate),
        "ratchet_only",
    )


class ATRTradeStep(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    management_version: Literal["atr-close-trail-v1"] = "atr-close-trail-v1"
    scope: Literal["experimental_close_trailing_decision"] = "experimental_close_trailing_decision"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    parameters: ATRManagementParameters
    side: Literal["BUY", "SELL"]
    close: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    previous_stop: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    atr: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)] | None
    action: Literal["EXIT", "HOLD", "NO_TRADE"]
    next_stop: Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
    reason: str
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def step(self) -> Self:
        if (self.action, self.next_stop, self.reason) != _trailing_step(
            self.side, self.close, self.previous_stop, self.atr, self.parameters
        ):
            raise ValueError("Trailing decision must reproduce from its captured inputs")
        return self


def atr_trailing_step(
    side: Literal["BUY", "SELL"],
    close: Decimal,
    previous_stop: Decimal,
    atr: Decimal | None,
    parameters: ATRManagementParameters,
) -> ATRTradeStep:
    parameters = ATRManagementParameters.model_validate(parameters.model_dump())
    close, previous_stop = _decimal_price(close), _decimal_price(previous_stop)
    try:
        atr = _decimal_price(atr) if atr is not None else None
    except ValueError:
        atr = None
    action, next_stop, reason = _trailing_step(side, close, previous_stop, atr, parameters)
    return ATRTradeStep(
        parameters=parameters,
        side=side,
        close=close,
        previous_stop=previous_stop,
        atr=atr,
        action=action,
        next_stop=next_stop,
        reason=reason,
    )
