"""Deterministic, auditable conditional scenarios; no order or portfolio effects."""

from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from itertools import pairwise
from typing import Literal
from uuid import uuid4

from core.advisory.events import assess_event_risk
from core.advisory.health import assess_market_data
from core.advisory.models import (
    CATALOG,
    Candle,
    EconomicCalendar,
    EventRiskPolicy,
    Interval,
    MarketSnapshot,
    News,
    Report,
    RiskWorksheet,
    Scenario,
    StrategyResearchCheck,
    utc_instant,
    utcnow,
)
from core.strategy_signals import (
    ATRManagementParameters,
    BreakoutParameters,
    VolumeBreakoutKernel,
    atr_entry_plan,
    seeded_range_atr,
)


def breakout_research_check(
    instrument_id: str,
    interval: Interval,
    market: MarketSnapshot | None,
    *,
    parameters: BreakoutParameters,
    now: datetime,
    calendar: EconomicCalendar | None = None,
    event_policy: EventRiskPolicy | None = None,
    management_parameters: ATRManagementParameters | None = None,
) -> StrategyResearchCheck:
    """Same numeric rule, with the shared production guards before feature access."""
    now = utc_instant(now)
    failures = []
    validated_parameters: BreakoutParameters | None = None
    validated_management = None
    if management_parameters is not None:
        try:
            validated_management = ATRManagementParameters.model_validate(
                management_parameters.model_dump(warnings=False)
            )
        except (ValueError, TypeError, AttributeError):
            failures.append("invalid_management_parameters")
    if market is not None:
        try:
            market = MarketSnapshot.model_validate(market.model_dump(warnings=False))
        except (ValueError, TypeError, AttributeError):
            market = None
            failures.append("invalid_strategy_market")
    health = assess_market_data(market, instrument_id, interval, now=now)
    event = assess_event_risk(calendar, event_policy, instrument_id, now=now)
    if health.state != "HEALTHY":
        failures.extend(health.reasons)
    if event.state != "CLEAR":
        failures.extend(event.reasons)
    if interval != "1d":
        failures.append("strategy_interval_not_supported")
    try:
        kernel = VolumeBreakoutKernel(parameters)
        validated_parameters = kernel.parameters
    except (ValueError, TypeError, AttributeError):
        failures.append("invalid_strategy_parameters")
    features = None
    management = None
    if not failures:
        assert market is not None
        try:
            features = kernel.evaluate(market.candles)
        except (ValueError, TypeError, AttributeError):
            failures.append("invalid_strategy_price_window")
        if features is None:
            failures.append("insufficient_strategy_warmup")
        elif features.reason == "unknown_volume_baseline":
            failures.append("unknown_volume_baseline")
            features = None
        if (
            features is not None
            and features.direction != "WAIT"
            and validated_management is not None
        ):
            try:
                atr = seeded_range_atr(market.candles, validated_management)
                if atr is None:
                    raise ValueError("Unknown strategy ATR")
                management = atr_entry_plan(
                    features.direction, features.close, atr, validated_management
                )
            except (ValueError, TypeError, AttributeError, ArithmeticError):
                failures.append("unknown_or_invalid_management_geometry")
                features = None
    state: Literal["FEATURES_READY", "WAIT", "NO_TRADE"] = (
        "NO_TRADE"
        if failures
        else "FEATURES_READY" if features and features.direction != "WAIT" else "WAIT"
    )
    return StrategyResearchCheck(
        id=str(uuid4()),
        generated_at=now,
        instrument_id=instrument_id,
        interval=interval,
        market=market,
        parameters=validated_parameters,
        management_parameters=validated_management,
        management=management,
        data_health=health,
        event_risk=event,
        features=features,
        state=state,
        advice="NO TRADE" if failures else "WAIT",
        reasons=tuple(sorted(set(failures))),
    )


def ema(values: list[Decimal], length: int) -> Decimal:
    result = values[0]
    weight = Decimal(2) / Decimal(length + 1)
    for value in values[1:]:
        result = weight * value + (1 - weight) * result
    return result


def average_true_range(bars: list[Candle], length: int = 14) -> Decimal | None:
    """Shared simple ATR convention; insufficient observations stay unknown."""
    if length < 1:
        raise ValueError("ATR length must be positive")
    if len(bars) <= length:
        return None
    ranges = [
        max(b.high - b.low, abs(b.high - a.close), abs(b.low - a.close)) for a, b in pairwise(bars)
    ]
    return sum(ranges[-length:], Decimal(0)) / length


def build_report(
    instrument_id: str,
    interval: Interval,
    market: MarketSnapshot | None,
    news: list[News],
    observations: list[str],
    *,
    now: datetime | None = None,
    calendar: EconomicCalendar | None = None,
    event_policy: EventRiskPolicy | None = None,
) -> Report:
    instrument = CATALOG[instrument_id]
    now = now or utcnow()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Research clock must include a timezone")
    now = utc_instant(now)
    if market is not None:
        market = MarketSnapshot.model_validate(market.model_dump())
    result = Report(
        id=str(uuid4()),
        instrument=instrument,
        interval=interval,
        generated_at=now,
        market=market,
        status="unavailable",
        observations=list(observations),
        indicators={},
        scenarios=[],
        news=news,
        data_health=assess_market_data(market, instrument_id, interval, now=now),
        event_risk=assess_event_risk(calendar, event_policy, instrument_id, now=now),
        strategy_research=breakout_research_check(
            instrument_id,
            interval,
            market,
            now=now,
            parameters=BreakoutParameters(
                range_period=20, minimum_bars=30, volume_multiplier=Decimal(2)
            ),
            management_parameters=ATRManagementParameters(
                atr_period=14,
                atr_window=200,
                atr_stop_multiplier=Decimal(2),
                proposed_target_r=Decimal(3),
            ),
            calendar=calendar,
            event_policy=event_policy,
        ),
    )
    if market is None:
        result.observations.append("لا توجد شموع موثقة لهذه الأداة؛ أضف مصدرًا أو استورد بياناتك.")
        return result
    if market.instrument_id != instrument_id or market.interval != interval:
        raise ValueError("Market identity/interval mismatch")
    result.observations.extend(market.observations)
    bars = market.candles
    if result.data_health.state != "HEALTHY":
        reasons = result.data_health.reasons
        if any(reason.startswith(("stale_", "future_")) for reason in reasons):
            result.status = "stale"
        elif any(
            reason in {"unverified_session_gap", "missing_or_irregular_bars"} for reason in reasons
        ):
            result.status = "insufficient"
        result.observations.append(
            "NO TRADE · جودة البيانات غير مؤكدة أو غير سليمة؛ التحليل الرقمي محجوب: "
            + ", ".join(reasons)
        )
        return result
    if len(bars) < 60:
        result.status = "insufficient"
        result.observations.append("يلزم 60 شمعة مكتملة على الأقل لحساب السياق والمستويات.")
        return result
    closes = [b.close for b in bars]
    last = closes[-1]
    atr = average_true_range(bars)
    assert atr is not None  # The 60-bar feature guard precedes calculation.
    differences = [b - a for a, b in zip(closes[-15:-1], closes[-14:], strict=True)]
    gains = sum((max(d, Decimal(0)) for d in differences), Decimal(0)) / 14
    losses = sum((max(-d, Decimal(0)) for d in differences), Decimal(0)) / 14
    rsi = (
        Decimal(100)
        if losses == 0 and gains
        else Decimal(50) if losses == gains == 0 else 100 - 100 / (1 + gains / losses)
    )
    support = min(b.low for b in bars[-21:-1])
    resistance = max(b.high for b in bars[-21:-1])
    fast, slow = ema(closes, 20), ema(closes, 50)
    volume = sum(b.volume for b in bars[-96:])
    result.indicators = {
        "last_close": last,
        "ema20": fast,
        "ema50": slow,
        "atr14": atr,
        "rsi14_simple": rsi,
        "support20": support,
        "resistance20": resistance,
        "bias": "bullish" if last > fast > slow else "bearish" if last < fast < slow else "mixed",
    }
    if volume:
        result.indicators["rolling_vwap96"] = (
            sum((b.high + b.low + b.close) / 3 * b.volume for b in bars[-96:]) / volume
        )
    else:
        result.observations.append("الحجم غير متاح؛ لم يُحسب متوسط السعر المرجح بالحجم.")
    if atr <= 0 or resistance <= support:
        result.status = "insufficient"
        result.observations.append("لا يوجد نطاق سعري كافٍ لبناء سيناريو قابل للتقييم.")
        return result
    tick = instrument.tick_size

    def rounded(p: Decimal) -> Decimal:
        return (p / tick).to_integral_value(rounding=ROUND_FLOOR) * tick

    up = rounded(resistance + max(atr * Decimal("0.1"), tick))
    down = max(tick, rounded(support - max(atr * Decimal("0.1"), tick)))
    risk = max(rounded(atr), tick)
    midpoint = rounded((support + resistance) / 2)
    if down - 2 * risk <= 0 or up - risk <= 0:
        result.status = "insufficient"
        result.observations.append("المستويات المحسوبة لا تسمح بأهداف موجبة معقولة.")
        return result
    if result.event_risk.state != "CLEAR":
        result.status = "ready"
        result.observations.append(
            "NO TRADE · حارس الأحداث سياسة مخاطرة داخلية، منفصلة عن قواعد شركة التمويل: "
            + ", ".join(result.event_risk.reasons)
        )
        return result
    result.scenarios = [
        Scenario(
            direction="bullish",
            condition="إغلاق شمعة فوق المقاومة ثم ثباتها عند إعادة الاختبار؛ راقب الخبر والسيولة قبل القرار.",
            trigger=up,
            invalidation=up - risk,
            targets=[up + risk, up + 2 * risk],
            rationale="اختراق نطاق آخر 20 شمعة؛ مسافة الإلغاء والأهداف مشتقة من ATR وليست توقعًا مضمونًا.",
        ),
        Scenario(
            direction="bearish",
            condition="إغلاق شمعة تحت الدعم ثم فشل استعادته؛ تحقق من السبريد والأخبار قبل القرار.",
            trigger=down,
            invalidation=down + risk,
            targets=[down - risk, down - 2 * risk],
            rationale="كسر نطاق آخر 20 شمعة؛ الأهداف تمثل مضاعفات المسافة إلى الإلغاء.",
        ),
        Scenario(
            direction="range",
            condition="بقاء السعر بين الدعم والمقاومة مع رفض واضح عند الحواف؛ يُلغى السيناريو بكسر النطاق.",
            trigger=midpoint,
            invalidation=down,
            targets=[rounded(support), rounded(resistance)],
            rationale="مراقبة نطاق جانبي؛ لا تعني هذه المستويات أمر شراء أو بيع.",
        ),
    ]
    result.status = "ready"
    result.observations.append(
        "سيناريوهات شرطية غير معايرة الاحتمال. ATR وRSI هنا حسابات بسيطة موضحة في الدليل."
    )
    if market.data_mode == "user_import":
        result.observations.append(
            "بيانات مستوردة من المستخدم؛ لا يُفترض أنها تغذية لحظية أو معتمدة من المزود."
        )
    return result


def risk_worksheet(request: RiskWorksheet) -> dict[str, str]:
    # Internal assignment/model_copy can bypass constructor validation.
    request = RiskWorksheet.model_validate(
        request.model_dump(include=set(RiskWorksheet.model_fields))
    )
    instrument = CATALOG[request.instrument_id]
    if instrument.market == "index":
        raise ValueError("An index is not a tradeable contract; select your actual instrument")
    if instrument.market == "cme_future" and (
        request.entry % instrument.tick_size or request.stop % instrument.tick_size
    ):
        raise ValueError(
            f"{instrument.id} entry and stop must align with tick {instrument.tick_size}"
        )
    distance = abs(request.entry - request.stop)
    if distance == 0:
        raise ValueError("Entry and stop must differ")
    budget = request.account_value * request.risk_percent / 100
    loss_per_unit = (
        distance + request.slippage_points
    ) * instrument.point_value + request.fees_per_unit
    size = budget / loss_per_unit
    if instrument.market == "cme_future":
        size = size.to_integral_value(rounding=ROUND_FLOOR)
    else:
        size = size.quantize(Decimal("0.000001"), rounding=ROUND_FLOOR)
    return {
        "risk_budget": str(budget),
        "loss_per_unit": str(loss_per_unit),
        "size": str(size),
        "estimated_loss_at_stop": str(size * loss_per_unit),
        "currency": instrument.currency,
        "note": "حساب تخطيطي بعملة الأداة؛ لا يشمل متطلبات الهامش أو التصفية أو الفجوات. تحقق من مواصفات وسيطك.",
    }
