"""Contracts for the isolated, non-executing manual research assistant."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StrictInt,
    model_validator,
)

from core.strategy_signals import (
    ATRManagementParameters,
    ATRTradePlan,
    BreakoutParameters,
    VolumeBreakoutFeatures,
    VolumeBreakoutKernel,
    atr_entry_plan,
    seeded_range_atr,
)


def utc_instant(value: datetime) -> datetime:
    """Compare elapsed instants, never ambiguous local wall times."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return value.astimezone(UTC)


UTCDateTime = Annotated[AwareDatetime, AfterValidator(utc_instant)]

Price = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]
Number = Annotated[Decimal, Field(allow_inf_nan=False)]
Interval = Literal["5m", "15m", "1h", "4h", "1d"]
INTERVAL_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FuturesSpec(Strict):
    """Outright contract metadata; not listing, margin or prop-firm permission."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    version: str = Field(min_length=1, max_length=100)
    reviewed_on: date
    sources: tuple[HttpUrl, ...] = Field(min_length=1)
    venue: Literal["CME", "CBOT", "COMEX", "NYMEX"]
    research_tier: Literal[1, 2] | None
    exposure_group: Literal["us_equity_index", "gold", "copper", "crude_oil", "fx"]
    quote_unit: str = Field(min_length=1, max_length=100)
    month_codes: str = Field(pattern=r"^[FGHJKMNQUVXZ]+$")
    settlement: Literal["cash", "physical"]

    @model_validator(mode="after")
    def unique_months(self) -> Self:
        if len(set(self.month_codes)) != len(self.month_codes):
            raise ValueError("Contract month codes must be distinct")
        return self


class Instrument(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    name: str
    market: Literal["crypto_perpetual", "index", "cme_future"]
    symbol: str
    currency: str = "USD"
    tick_size: Price
    point_value: Price
    source_required: str | None = None
    # Optional only for reading legacy serialized reports. Active CME catalog
    # entries carry this metadata, required for contract identity validation.
    futures_spec: FuturesSpec | None = None

    @property
    def tick_value(self) -> Decimal:
        return self.tick_size * self.point_value

    @model_validator(mode="after")
    def specification_kind(self) -> Self:
        if self.futures_spec is not None and (
            self.market != "cme_future" or self.currency != "USD"
        ):
            raise ValueError("Futures specification requires a USD CME futures instrument")
        return self

    def valid_contract(self, contract: str | None) -> bool:
        return bool(
            self.market == "cme_future"
            and self.futures_spec is not None
            and contract is not None
            and re.fullmatch(
                re.escape(self.symbol)
                + "["
                + self.futures_spec.month_codes
                + r"](?:[0-9]{2}|[0-9]{4})",
                contract,
            )
        )


_catalog = {
    "BTCUSDT-PERP": Instrument(
        id="BTCUSDT-PERP",
        name="Bitcoin / USDT perpetual",
        market="crypto_perpetual",
        symbol="BTCUSDT",
        currency="USDT",
        tick_size=Decimal("0.1"),
        point_value=Decimal(1),
    ),
    "SOLUSDT-PERP": Instrument(
        id="SOLUSDT-PERP",
        name="Solana / USDT perpetual",
        market="crypto_perpetual",
        symbol="SOLUSDT",
        currency="USDT",
        tick_size=Decimal("0.001"),
        point_value=Decimal(1),
    ),
    "GALAUSDT-PERP": Instrument(
        id="GALAUSDT-PERP",
        name="Gala / USDT perpetual",
        market="crypto_perpetual",
        symbol="GALAUSDT",
        currency="USDT",
        tick_size=Decimal("0.00001"),
        point_value=Decimal(1),
    ),
    "NASDAQ100": Instrument(
        id="NASDAQ100",
        name="Nasdaq-100 index (NDX)",
        market="index",
        symbol="NDX",
        tick_size=Decimal("0.01"),
        point_value=Decimal(1),
        source_required="A licensed index feed or explicit OHLCV import",
    ),
}

# Prices are USD per quoted unit. These are outright increments, never spread
# increments. Market membership/size here confers no Earn2Trade eligibility.
_EQUITY = (
    "https://www.cmegroup.com/trading/equity-index/files/cme-micro-e-mini-futures-fact-card.pdf"
)
_FX = "https://www.cmegroup.com/markets/fx/fx-product-guide"
_FX_MONTHS = "https://www.cmegroup.com/rulebook/files/S_5524.pdf"
_GOLD = "https://www.cmegroup.com/rulebook/COMEX/1a/120.pdf"
_GOLD_MONTHS = "https://www.cmegroup.com/trading/metals/files/fact-card-gold-futures-options.pdf"
_COPPER = "https://www.cmegroup.com/rulebook/COMEX/9/914.pdf"
_COPPER_MONTHS = "https://www.cmegroup.com/education/files/micro-copper-futures-factcard.pdf"
_OIL = "https://www.cmegroup.com/rulebook/NYMEX/3/309.pdf"
_OIL_MONTHS = (
    "https://www.cmegroup.com/education/articles-and-reports/micro-wti-crude-oil-futures-faq"
)

for _record in (
    dict(
        id="NQ",
        name="E-mini Nasdaq-100 futures",
        tick_size="0.25",
        point_value="20",
        venue="CME",
        research_tier=None,
        exposure_group="us_equity_index",
        quote_unit="index points",
        month_codes="HMUZ",
        settlement="cash",
        sources=(
            "https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.html",
            _EQUITY,
        ),
    ),
    dict(
        id="MES",
        name="Micro E-mini S&P 500 futures",
        tick_size="0.25",
        point_value="5",
        venue="CME",
        research_tier=1,
        exposure_group="us_equity_index",
        quote_unit="index points",
        month_codes="HMUZ",
        settlement="cash",
        sources=(_EQUITY,),
    ),
    dict(
        id="MYM",
        name="Micro E-mini Dow futures",
        tick_size="1",
        point_value="0.5",
        venue="CBOT",
        research_tier=1,
        exposure_group="us_equity_index",
        quote_unit="index points",
        month_codes="HMUZ",
        settlement="cash",
        sources=(_EQUITY,),
    ),
    dict(
        id="MNQ",
        name="Micro E-mini Nasdaq-100 futures",
        tick_size="0.25",
        point_value="2",
        venue="CME",
        research_tier=1,
        exposure_group="us_equity_index",
        quote_unit="index points",
        month_codes="HMUZ",
        settlement="cash",
        sources=(_EQUITY,),
    ),
    dict(
        id="MGC",
        name="Micro Gold futures",
        tick_size="0.1",
        point_value="10",
        venue="COMEX",
        research_tier=1,
        exposure_group="gold",
        quote_unit="USD per troy ounce",
        month_codes="GJMQVZ",
        settlement="physical",
        sources=(_GOLD, _GOLD_MONTHS),
    ),
    dict(
        id="M2K",
        name="Micro E-mini Russell 2000 futures",
        tick_size="0.1",
        point_value="5",
        venue="CME",
        research_tier=2,
        exposure_group="us_equity_index",
        quote_unit="index points",
        month_codes="HMUZ",
        settlement="cash",
        sources=(_EQUITY,),
    ),
    dict(
        id="MCL",
        name="Micro WTI Crude Oil futures",
        tick_size="0.01",
        point_value="100",
        venue="NYMEX",
        research_tier=2,
        exposure_group="crude_oil",
        quote_unit="USD per barrel",
        month_codes="FGHJKMNQUVXZ",
        settlement="cash",
        sources=(_OIL, _OIL_MONTHS),
    ),
    dict(
        id="M6E",
        name="Micro EUR/USD futures",
        tick_size="0.0001",
        point_value="12500",
        venue="CME",
        research_tier=2,
        exposure_group="fx",
        quote_unit="USD per EUR",
        month_codes="HMUZ",
        settlement="physical",
        sources=(_FX, "https://www.cmegroup.com/markets/fx/g10/e-micro-euro/specs"),
    ),
    dict(
        id="M6B",
        name="Micro GBP/USD futures",
        tick_size="0.0001",
        point_value="6250",
        venue="CME",
        research_tier=2,
        exposure_group="fx",
        quote_unit="USD per GBP",
        month_codes="HMUZ",
        settlement="physical",
        sources=(_FX, _FX_MONTHS),
    ),
    dict(
        id="MHG",
        name="Micro Copper futures",
        tick_size="0.0005",
        point_value="2500",
        venue="COMEX",
        research_tier=2,
        exposure_group="copper",
        quote_unit="USD per pound",
        month_codes="FGHJKMNQUVXZ",
        settlement="cash",
        sources=(_COPPER, _COPPER_MONTHS),
    ),
):
    _spec = FuturesSpec.model_validate(
        {
            key: value
            for key, value in _record.items()
            if key not in {"id", "name", "tick_size", "point_value"}
        }
        | {"version": "cme-outright-2026-10-05", "reviewed_on": date(2026, 10, 5)}
    )
    _instrument = Instrument.model_validate(
        {
            key: value
            for key, value in _record.items()
            if key in {"id", "name", "tick_size", "point_value"}
        }
        | {
            "market": "cme_future",
            "symbol": _record["id"],
            "futures_spec": _spec,
            "source_required": "A licensed dated CME contract feed or explicit OHLCV import",
        }
    )
    _catalog[_instrument.id] = _instrument

# Keep both the registry and operative tick/multiplier metadata immutable.
CATALOG = MappingProxyType(_catalog)


class Candle(Strict):
    open_time: UTCDateTime
    close_time: UTCDateTime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]

    @model_validator(mode="after")
    def valid_range(self) -> Self:
        if (
            self.open_time >= self.close_time
            or self.high < max(self.open, self.close, self.low)
            or self.low > min(self.open, self.close)
        ):
            raise ValueError("Invalid candle time or OHLC range")
        return self


class PriceObservation(Strict):
    symbol: str
    price: Price
    timestamp: UTCDateTime
    source: HttpUrl
    bid: Price | None = None
    ask: Price | None = None

    @model_validator(mode="after")
    def uncrossed(self) -> Self:
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("Crossed quote")
        return self


class MarketDataEvidence(Strict):
    """Reported source facts, never a provider-supplied permission or health verdict."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    provider_id: str = Field(min_length=1, max_length=100)
    provider_state: Literal["active", "degraded", "disconnected", "unknown"]
    heartbeat_at: UTCDateTime | None = None
    sequence_mode: Literal["not_applicable", "required", "unknown"]
    sequences: tuple[StrictInt, ...] | None = None
    quote: PriceObservation | None = None
    reference_quote: PriceObservation | None = None


class MarketDataHealth(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    state: Literal["HEALTHY", "UNHEALTHY", "UNKNOWN"] = "UNKNOWN"
    policy_version: Literal["closed-bar-health-v1"] = "closed-bar-health-v1"
    scope: Literal["closed_bar_research"] = "closed_bar_research"
    assessed_at: UTCDateTime | None = None
    reasons: tuple[str, ...] = ("unassessed",)
    diagnostics: dict[str, str] = Field(default_factory=dict)
    # This assessment cannot authorize entry or replace risk/account/policy gates.
    trade_permitted: Literal[False] = False


class MarketSnapshot(Strict):
    instrument_id: str
    interval: Interval
    source: HttpUrl
    fetched_at: UTCDateTime
    candles: list[Candle] = Field(min_length=1, max_length=500)
    data_mode: Literal["public_exchange", "user_import", "replay"]
    contract: str | None = Field(default=None, max_length=40)
    derivatives: dict[str, Number] = Field(default_factory=dict)
    observations: list[str] = Field(default_factory=list)
    quality: MarketDataEvidence | None = None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.instrument_id not in CATALOG:
            raise ValueError("Unknown instrument")
        instrument = CATALOG[self.instrument_id]
        if instrument.market == "cme_future" and not instrument.valid_contract(self.contract):
            raise ValueError("Use a dated contract with this instrument's root and contract month")
        for i, bar in enumerate(self.candles):
            duration = (bar.close_time - bar.open_time).total_seconds()
            if (
                not INTERVAL_SECONDS[self.interval] - 1
                <= duration
                <= INTERVAL_SECONDS[self.interval]
            ):
                raise ValueError("Candle duration must match the selected interval")
            if i and bar.open_time <= self.candles[i - 1].close_time:
                raise ValueError("Candles must be ordered and non-overlapping")
            if bar.close_time > self.fetched_at:
                raise ValueError("Only completed candles are accepted")
        return self


class News(Strict):
    id: str
    title: str
    url: HttpUrl
    source: str
    published_at: UTCDateTime
    category: Literal["macro", "crypto", "regulation", "equity"]


class EconomicEvent(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    known_at: UTCDateTime
    scheduled_at: UTCDateTime | None
    source: HttpUrl
    affected_markets: tuple[str, ...] = Field(min_length=1, max_length=len(CATALOG))
    impact: Literal["low", "medium", "high", "unknown"]
    status: Literal["scheduled", "cancelled", "unknown"] = "scheduled"

    @model_validator(mode="after")
    def markets(self) -> Self:
        if len(set(self.affected_markets)) != len(self.affected_markets) or any(
            root not in CATALOG for root in self.affected_markets
        ):
            raise ValueError("Event markets must be distinct catalog identities")
        return self


class EconomicCalendar(Strict):
    """A source revision known at observed_at, with explicit coverage claims."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    source: HttpUrl
    observed_at: UTCDateTime
    coverage_start: UTCDateTime
    coverage_end: UTCDateTime
    covered_markets: tuple[str, ...] = Field(min_length=1, max_length=len(CATALOG))
    complete: StrictBool
    provider_state: Literal["active", "degraded", "disconnected", "unknown"]
    events: tuple[EconomicEvent, ...] = Field(default=(), max_length=2000)

    @model_validator(mode="after")
    def coverage(self) -> Self:
        if self.coverage_start >= self.coverage_end:
            raise ValueError("Calendar coverage must have positive duration")
        if len(set(self.covered_markets)) != len(self.covered_markets) or any(
            root not in CATALOG for root in self.covered_markets
        ):
            raise ValueError("Calendar markets must be distinct catalog identities")
        if len({event.id for event in self.events}) != len(self.events):
            raise ValueError("Duplicate economic event identity")
        for event in self.events:
            if event.known_at > self.observed_at:
                raise ValueError("Calendar cannot contain a future-known revision")
            if not set(event.affected_markets) <= set(self.covered_markets):
                raise ValueError("Event markets must be covered by the calendar")
            if event.scheduled_at is not None and not (
                self.coverage_start <= event.scheduled_at <= self.coverage_end
            ):
                raise ValueError("Scheduled event must lie inside declared coverage")
        return self


class EventRiskPolicy(Strict):
    """Internal research-risk configuration, never an Earn2Trade rule."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=100)
    version: str = Field(min_length=1, max_length=100)
    before_seconds: StrictInt = Field(ge=0, le=604800)
    after_seconds: StrictInt = Field(ge=0, le=604800)
    max_calendar_age_seconds: StrictInt = Field(ge=0, le=604800)
    blocked_impacts: tuple[Literal["low", "medium", "high"], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_impacts(self) -> Self:
        if len(set(self.blocked_impacts)) != len(self.blocked_impacts):
            raise ValueError("Event policy impact classes must be distinct")
        return self


class EventRiskAssessment(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    state: Literal["CLEAR", "BLOCKED", "UNKNOWN"] = "UNKNOWN"
    guard_version: Literal["economic-event-guard-v1"] = "economic-event-guard-v1"
    scope: Literal["internal_research_risk"] = "internal_research_risk"
    assessed_at: UTCDateTime | None = None
    reasons: tuple[str, ...] = ("unassessed",)
    blocked_event_ids: tuple[str, ...] = ()
    calendar: EconomicCalendar | None = None
    policy: EventRiskPolicy | None = None
    trade_permitted: Literal[False] = False


class Watchlist(Strict):
    instruments: list[str] = Field(
        default_factory=lambda: [
            "NQ",
            "MNQ",
            "NASDAQ100",
        ],
        max_length=6,
    )
    interests: list[str] = Field(
        default_factory=lambda: ["inflation", "rates", "earnings", "liquidity"], max_length=20
    )

    @model_validator(mode="after")
    def allowed(self) -> Self:
        if len(set(self.instruments)) != len(self.instruments) or any(
            s not in CATALOG for s in self.instruments
        ):
            raise ValueError("Choose distinct instruments from the catalog")
        if any(not s.strip() or len(s) > 80 for s in self.interests):
            raise ValueError("Interests must contain 1 to 80 characters")
        return self


class Scenario(Strict):
    direction: Literal["bullish", "bearish", "range"]
    condition: str
    trigger: Price
    invalidation: Price
    targets: list[Price]
    rationale: str


class StrategyResearchCheck(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str
    generated_at: UTCDateTime
    instrument_id: str
    interval: Interval
    market: MarketSnapshot | None
    strategy_id: Literal["breakout_hunter_volume"] = "breakout_hunter_volume"
    strategy_version: Literal["range-volume-v1"] = "range-volume-v1"
    scope: Literal["experimental_directional_signal"] = "experimental_directional_signal"
    lifecycle: Literal["EXPERIMENT"] = "EXPERIMENT"
    parameters: BreakoutParameters | None
    management_parameters: ATRManagementParameters | None = None
    management: ATRTradePlan | None = None
    data_health: MarketDataHealth
    event_risk: EventRiskAssessment
    features: VolumeBreakoutFeatures | None
    state: Literal["FEATURES_READY", "WAIT", "NO_TRADE"]
    advice: Literal["WAIT", "NO TRADE"]
    reasons: tuple[str, ...]
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def no_permission(self) -> Self:
        if self.advice != ("NO TRADE" if self.state == "NO_TRADE" else "WAIT"):
            raise ValueError("Experimental signal state must match advice")
        if self.state != "NO_TRADE" and (
            self.market is None
            or self.parameters is None
            or self.features is None
            or self.data_health.state != "HEALTHY"
            or self.event_risk.state != "CLEAR"
            or self.reasons
            or self.interval != "1d"
        ):
            raise ValueError("Experimental features require known valid guarded daily bars")
        if self.state == "NO_TRADE" and (
            not self.reasons or self.features is not None or self.management is not None
        ):
            raise ValueError(
                "Blocked experiment needs reasons and cannot expose a directional signal"
            )
        if self.features and (self.state == "FEATURES_READY") != (
            self.features.direction != "WAIT"
        ):
            raise ValueError("Experimental features and state must agree")
        if self.state != "NO_TRADE":
            assert (
                self.market is not None
                and self.parameters is not None
                and self.features is not None
            )
            if (self.market.instrument_id, self.market.interval) != (
                self.instrument_id,
                self.interval,
            ):
                raise ValueError("Experimental market identity must match the request")
            # Local imports avoid schema initialization cycles. Positive copies
            # must reproduce the same existing guards at their original clock.
            from core.advisory.events import assess_event_risk
            from core.advisory.health import assess_market_data

            if self.data_health != assess_market_data(
                self.market, self.instrument_id, self.interval, now=self.generated_at
            ) or self.event_risk != assess_event_risk(
                self.event_risk.calendar,
                self.event_risk.policy,
                self.instrument_id,
                now=self.generated_at,
            ):
                raise ValueError("Experimental guards must reproduce from their source snapshots")
            if self.features != VolumeBreakoutKernel(self.parameters).evaluate(self.market.candles):
                raise ValueError("Experimental features must reproduce from their source window")
            if self.management_parameters is not None and self.features.direction != "WAIT":
                atr = seeded_range_atr(self.market.candles, self.management_parameters)
                if atr is None or self.management != atr_entry_plan(
                    self.features.direction, self.features.close, atr, self.management_parameters
                ):
                    raise ValueError("Experimental management must reproduce from its source bars")
            elif self.management is not None:
                raise ValueError("Management requires declared parameters and directional features")
        return self


class Report(Strict):
    id: str
    instrument: Instrument
    interval: Interval
    generated_at: UTCDateTime
    market: MarketSnapshot | None
    status: Literal["ready", "stale", "insufficient", "unavailable"]
    observations: list[str]
    indicators: dict[str, Number | str]
    scenarios: list[Scenario]
    news: list[News]
    agent_context: list[dict[str, str]] = Field(default_factory=list)
    strategy_research: StrategyResearchCheck | None = None
    probabilities: Literal["not_calibrated"] = "not_calibrated"
    execution_enabled: Literal[False] = False
    data_health: MarketDataHealth = Field(default_factory=MarketDataHealth)
    event_risk: EventRiskAssessment = Field(default_factory=EventRiskAssessment)


class RiskWorksheet(Strict):
    instrument_id: str
    account_value: Price
    risk_percent: Annotated[Decimal, Field(gt=0, le=1, allow_inf_nan=False)] = Decimal("0.5")
    entry: Price
    stop: Price
    fees_per_unit: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)] = Decimal(0)
    slippage_points: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)] = Decimal(0)


def utcnow() -> datetime:
    return datetime.now(UTC)


class PolicyRiskAllowance(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    """Generic policy output; no TCP25 rules or progression ratios here."""

    account_id: str
    account_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    known_at: UTCDateTime
    source_reference: str = Field(min_length=1, max_length=500, pattern=r".*\S.*")
    policy_id: str = Field(min_length=1, max_length=100)
    policy_version: str = Field(min_length=1, max_length=100)
    instrument_id: str
    contract: str
    at_invalidation: Price
    state: Literal["READY", "BLOCKED", "UNKNOWN"]
    reasons: tuple[str, ...]
    daily_loss_remaining_usd: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)] | None
    drawdown_remaining_usd: Annotated[Decimal, Field(ge=0, allow_inf_nan=False)] | None
    maximum_contracts: StrictInt | None = Field(ge=0)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.instrument_id not in CATALOG or CATALOG[self.instrument_id].futures_spec is None:
            raise ValueError("Policy allowance requires a catalog futures market")
        if not CATALOG[self.instrument_id].valid_contract(self.contract):
            raise ValueError("Policy allowance contract must match its market")
        if self.state == "READY" and (
            self.reasons
            or self.daily_loss_remaining_usd is None
            or self.drawdown_remaining_usd is None
            or self.maximum_contracts is None
        ):
            raise ValueError("Ready policy allowance requires complete unblocked limits")
        if self.state != "READY" and not self.reasons:
            raise ValueError("Blocked or unknown policy allowance requires reasons")
        return self
