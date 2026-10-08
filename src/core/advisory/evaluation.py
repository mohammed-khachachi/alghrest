"""Manual Earn2Trade evaluation journal. No broker access or pass certification.

Only the EOD evaluation model is supported. Funded/live trailing models differ.
All PnL inputs are net of fees and include intraday open-equity minima.
"""

from datetime import date, datetime, time, timedelta
from decimal import ROUND_FLOOR, Decimal, localcontext
from typing import Annotated, Any, Literal, Protocol, Self
from zoneinfo import ZoneInfo

from pydantic import ConfigDict, Field, HttpUrl, model_validator

from core.advisory.account import AccountObservation, account_state
from core.advisory.analysis import risk_worksheet
from core.advisory.models import (
    CATALOG,
    Number,
    Price,
    RiskWorksheet,
    Strict,
    UTCDateTime,
    utc_instant,
    utcnow,
)

RULES_REVIEWED = date(2026, 9, 28)
RULE_SOURCES = {
    "daily_loss": "https://help.earn2trade.com/en/articles/3395926-how-is-my-daily-loss-calculated",
    "eod_drawdown": "https://help.earn2trade.com/en/articles/5372687-how-does-end-of-day-drawdown-work",
    "consistency": "https://help.earn2trade.com/en/articles/3849975-what-is-the-maintain-consistency-rule",
    "hours": "https://help.earn2trade.com/en/articles/3224526-are-there-any-restrictions-on-when-i-can-trade-in-my-evaluation-account",
    "ladder": "https://help.earn2trade.com/en/articles/3292351-what-is-the-progression-ladder-in-the-gauntlet-mini",
    "gauntlet_mini": "https://www.earn2trade.com/gauntlet-mini",
    "trader_career_path": "https://www.earn2trade.com/trader-career-path",
}
CHICAGO = ZoneInfo("America/Chicago")
Nonnegative = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class EODTerms(Protocol):
    @property
    def starting_balance(self) -> Decimal: ...
    @property
    def profit_target(self) -> Decimal: ...
    @property
    def daily_loss_limit(self) -> Decimal: ...
    @property
    def maximum_drawdown(self) -> Decimal: ...
    @property
    def consistency_percent(self) -> int: ...
    @property
    def minimum_trading_days(self) -> int: ...


class EODFinancialState(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    balance: Number
    peak: Number
    floor: Number
    best_day: Nonnegative = Decimal(0)
    trading_days: int = Field(default=0, ge=0)


class EODProjection(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    financial: EODFinancialState
    daily_loss_breached: bool
    drawdown_breached: bool
    consistency_met: bool
    targets_met: bool


def initial_eod_state(terms: EODTerms) -> EODFinancialState:
    with localcontext() as context:
        context.prec = 80
        return EODFinancialState(
            balance=terms.starting_balance,
            peak=terms.starting_balance,
            floor=terms.starting_balance - terms.maximum_drawdown,
        )


def project_eod_session(
    terms: EODTerms,
    prior: EODFinancialState,
    *,
    net_pnl: Decimal,
    lowest_pnl: Decimal,
    traded: bool,
    closed: bool,
) -> EODProjection:
    """Project one session from its prior closed balance, without clocks/accounts.

    Repeated intraday snapshots use the same prior state; only finalization
    commits its peak/floor/best day. This is arithmetic, never permission.
    """
    prior = EODFinancialState.model_validate(prior.model_dump())
    if (
        not isinstance(net_pnl, Decimal)
        or not isinstance(lowest_pnl, Decimal)
        or not net_pnl.is_finite()
        or not lowest_pnl.is_finite()
        or lowest_pnl > min(Decimal(0), net_pnl)
        or not traded
        and (net_pnl != 0 or lowest_pnl != 0)
    ):
        raise ValueError("EOD projection requires complete finite net session minima")
    with localcontext() as context:
        context.prec = 80
        balance = prior.balance + net_pnl
        peak = max(prior.peak, balance) if closed else prior.peak
        floor = (
            min(terms.starting_balance, peak - terms.maximum_drawdown) if closed else prior.floor
        )
        best = max(prior.best_day, net_pnl)
        days = prior.trading_days + int(traded)
        total = balance - terms.starting_balance
        consistent = total > 0 and best * 100 < total * terms.consistency_percent
        daily = lowest_pnl <= -terms.daily_loss_limit
        draw = prior.balance + lowest_pnl <= prior.floor
        return EODProjection(
            financial=EODFinancialState(
                balance=balance, peak=peak, floor=floor, best_day=best, trading_days=days
            ),
            daily_loss_breached=daily,
            drawdown_breached=draw,
            consistency_met=consistent,
            targets_met=closed
            and not (daily or draw)
            and consistent
            and total >= terms.profit_target
            and days >= terms.minimum_trading_days,
        )


class EvaluationProfile(Strict):
    id: str = Field(min_length=1, max_length=60, pattern=r"^[a-zA-Z0-9_-]+$")
    program: Literal["gauntlet_mini", "trader_career_path"]
    phase: Literal["evaluation_eod"] = "evaluation_eod"
    starting_balance: Price
    profit_target: Price
    daily_loss_limit: Price
    maximum_drawdown: Price
    minimum_trading_days: int = Field(ge=0, le=365)
    consistency_percent: Literal[30] = 30
    source: HttpUrl
    verified_on: date

    @model_validator(mode="after")
    def limits(self) -> Self:
        if self.maximum_drawdown >= self.starting_balance:
            raise ValueError("Drawdown must be smaller than starting balance")
        if self.verified_on > utcnow().date():
            raise ValueError("Rules verification cannot be in the future")
        return self


class EvaluationSession(Strict):
    session_date: date
    as_of: UTCDateTime
    net_pnl: Number
    lowest_pnl: Number
    closed: bool
    traded: bool
    notes: str = Field(default="", max_length=2000)
    account: AccountObservation | None = None

    @model_validator(mode="after")
    def complete_observation(self) -> Self:
        local = self.as_of.astimezone(CHICAGO)
        session = local.date() + timedelta(days=int(local.time() >= time(17)))
        if self.session_date != session or self.as_of > utcnow():
            raise ValueError("Use the Chicago trading session date and a nonfuture observation")
        if self.lowest_pnl > min(Decimal(0), self.net_pnl):
            raise ValueError("Lowest intraday PnL must include zero and current net PnL")
        if not self.traded and (self.net_pnl != 0 or self.lowest_pnl != 0):
            raise ValueError("A non-trading session cannot contain trading PnL")
        if self.closed and local.time() < time(16):
            raise ValueError("Finalize only after 16:00 Chicago; all positions/orders must be flat")
        if self.account is not None:
            if self.account.observed_at != self.as_of:
                raise ValueError("Account observation and session must share the same timestamp")
            if self.closed and (self.account.positions or self.account.working_orders):
                raise ValueError("A finalized session cannot contain positions or working orders")
        return self


def session_clock(now: datetime) -> dict[str, Any]:
    local = now.astimezone(CHICAGO)
    weekday = local.weekday()
    closed = (
        time(15, 50) <= local.time() < time(17)
        or weekday == 5
        or (weekday == 4 and local.time() >= time(15, 50))
        or (weekday == 6 and local.time() < time(17))
    )
    return {
        "chicago_time": local.isoformat(),
        "session_date": (local.date() + timedelta(days=int(local.time() >= time(17)))).isoformat(),
        "required_flat_by": datetime.combine(
            local.date() + timedelta(days=int(local.time() >= time(17))), time(15, 50), CHICAGO
        ).isoformat(),
        "regular_hours_closed": closed,
        "note": "إغلاق جميع المراكز والأوامر قبل 15:50 شيكاغو. العطلات والإغلاق المبكر تتطلب مراجعة تقويم CME.",
    }


def evaluation_status(
    profile: EvaluationProfile, sessions: list[EvaluationSession], now: datetime | None = None
) -> dict[str, Any]:
    now = now or utcnow()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Evaluation clock must include a timezone")
    now = utc_instant(now)
    # Internal copies/assignment can bypass Pydantic's constructor validation.
    profile = EvaluationProfile.model_validate(profile.model_dump())
    sessions = [EvaluationSession.model_validate(row.model_dump()) for row in sessions]
    financial = initial_eod_state(profile)
    balance, floor = financial.balance, financial.floor
    breaches: list[str] = []
    days = 0
    best_day = Decimal(0)
    current: EvaluationSession | None = None
    previous_date = None
    daily_remaining = profile.daily_loss_limit
    for row in sessions:
        if (previous_date and row.session_date <= previous_date) or (
            current and not current.closed
        ):
            raise ValueError("Sessions must be distinct, ordered, and prior sessions finalized")
        if row.as_of > now:
            raise ValueError("Future session observation")
        previous_date = row.session_date
        projection = project_eod_session(
            profile,
            financial,
            net_pnl=row.net_pnl,
            lowest_pnl=row.lowest_pnl,
            traded=row.traded,
            closed=row.closed,
        )
        if projection.daily_loss_breached:
            breaches.append(f"daily_loss:{row.session_date}")
        if projection.drawdown_breached:
            breaches.append(f"drawdown_boundary:{row.session_date}")
        financial = projection.financial
        balance, floor = financial.balance, financial.floor
        if row.account is not None and (
            row.account.account_id != profile.id
            or row.account.equity != balance
            or row.account.currency != "USD"
        ):
            raise ValueError(
                "Account observation must match journal account identity and equity in USD"
            )
        daily_remaining = profile.daily_loss_limit + row.net_pnl
        days = financial.trading_days
        best_day = financial.best_day
        current = row
    with localcontext() as context:
        context.prec = 80
        total = balance - profile.starting_balance
        consistent = total > 0 and best_day * 100 < total * profile.consistency_percent
    # Strictly below 30%: equality is not enough. Round UP to the next cent.
    consistency_total = (
        (best_day / Decimal("0.3") * 100).to_integral_value(rounding=ROUND_FLOOR) / 100
        + Decimal("0.01")
        if best_day > 0
        else Decimal(0)
    )
    clock = session_clock(now)
    fresh = bool(
        current
        and not current.closed
        and current.session_date.isoformat() == clock["session_date"]
        and 0 <= (now - current.as_of).total_seconds() <= 1800
    )
    rules_current = 0 <= (now.date() - profile.verified_on).days <= 30
    account = account_state(
        current.account if current else None,
        account_id=profile.id,
        journal_equity=balance,
        now=now,
        max_age_seconds=1800,
    )
    return {
        "profile": profile.model_dump(mode="json"),
        "balance": str(balance),
        "total_pnl": str(total),
        "minimum_balance": str(floor),
        "drawdown_remaining": str(max(Decimal(0), balance - floor)),
        "daily_loss_remaining": str(max(Decimal(0), daily_remaining)),
        "best_day": str(best_day),
        "trading_days": days,
        "profit_remaining": str(max(Decimal(0), profile.profit_target - total)),
        "consistency_met": consistent,
        "consistency_total_required": str(consistency_total),
        "breaches": breaches,
        "fresh_observation": fresh,
        "rules_current": rules_current,
        "account_state": account.model_dump(mode="json"),
        "recorded_targets_met": bool(sessions)
        and all(s.closed for s in sessions)
        and not breaches
        and consistent
        and total >= profile.profit_target
        and days >= profile.minimum_trading_days,
        "clock": clock,
        "sessions": [s.model_dump(mode="json") for s in sessions],
        "note": "سجل يدوي وفق المدخلات؛ لا يؤكد اجتياز التقييم ولا يراقب منصة الوسيط. أدخل كل جلسة وأدنى ربح/خسارة شاملاً المراكز المفتوحة والعمولات. راجع لوحة الشركة.",
    }


class EvaluationPlan(RiskWorksheet):
    allowed_standard_contracts_at_stop: Price
    existing_standard_contracts: Nonnegative
    safety_buffer: Price
    schedule_checked: Literal[True]


def evaluation_risk_blocks(status: dict[str, Any]) -> tuple[str, ...]:
    """Existing manual EOD journal restrictions; never trade permission."""
    reasons = ["breach:" + str(reason) for reason in status["breaches"]]
    if not status["fresh_observation"]:
        reasons.append("stale_or_missing_session")
    if not status["rules_current"]:
        reasons.append("rules_review_not_current")
    if status["clock"]["regular_hours_closed"]:
        reasons.append("outside_regular_evaluation_hours")
    return tuple(reasons)


def evaluation_plan(
    value: EvaluationPlan, profile: EvaluationProfile, sessions: list[EvaluationSession]
) -> dict[str, str]:
    value = EvaluationPlan.model_validate(value.model_dump())
    status = evaluation_status(profile, sessions)
    blocks = evaluation_risk_blocks(status)
    if value.instrument_id not in {"NQ", "MNQ"}:
        raise ValueError("Evaluation planning supports NQ/MNQ only")
    if any(reason != "outside_regular_evaluation_hours" for reason in blocks):
        raise ValueError("Need current verified rules and a fresh unbreached session observation")
    if "outside_regular_evaluation_hours" in blocks:
        raise ValueError("Outside regular permitted evaluation hours")
    account = status["account_state"]
    if account["health"] != "KNOWN":
        raise ValueError("Need a complete reconciled current account observation before sizing")
    observation = account["observation"]
    if observation["positions"] or observation["working_orders"]:
        raise ValueError("Open exposure sizing requires validated contract-aware exposure limits")
    if value.existing_standard_contracts != 0:
        raise ValueError("Existing contract count must match the observed flat account")
    if value.account_value != Decimal(status["balance"]):
        raise ValueError("Account value must match the journal's current net equity")
    instrument = CATALOG[value.instrument_id]
    if value.entry % instrument.tick_size or value.stop % instrument.tick_size:
        raise ValueError("NQ/MNQ prices must align with the 0.25 tick")
    result = risk_worksheet(value)
    budget = max(
        Decimal(0),
        min(
            Decimal(result["risk_budget"]),
            Decimal(status["daily_loss_remaining"]) - value.safety_buffer,
            Decimal(status["drawdown_remaining"]) - value.safety_buffer,
        ),
    )
    equivalents = max(
        Decimal(0), value.allowed_standard_contracts_at_stop - value.existing_standard_contracts
    )
    cap = equivalents * (10 if value.instrument_id == "MNQ" else 1)
    size = min(budget / Decimal(result["loss_per_unit"]), cap).to_integral_value(
        rounding=ROUND_FLOOR
    )
    result.update(
        risk_budget=str(budget),
        size=str(size),
        estimated_loss_at_stop=str(size * Decimal(result["loss_per_unit"])),
    )
    result["note"] = (
        "حجم مقيد بهامش الخسارة وسقف العقود المُدخل عند الوقف؛ يشمل مراكزك الأخرى. أعد الحساب بعد تغير الأسعار أو سلم العقود. الفجوات قد تتجاوز الوقف."
    )
    return result
