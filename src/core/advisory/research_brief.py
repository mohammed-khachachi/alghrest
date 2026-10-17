"""A dated public-research brief from immutable saved snapshots."""

from datetime import datetime
from decimal import Decimal
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import ConfigDict, Field, field_validator, model_validator

from core.advisory.models import Strict, UTCDateTime
from core.advisory.openterminal_research import (
    CandleAnalysis,
    TerminalResearch,
    TerminalSymbol,
    valid_symbol,
)
from core.advisory.research_journal import ResearchSnapshot
from core.advisory.research_quality import CandleQuality, QualityReason

QUALITY_REASONS: dict[QualityReason, str] = {
    "history_unavailable": "تعذر الحصول على الشموع من OpenTerminal.",
    "invalid_response": "استجابة الشموع غير صالحة أو تتجاوز الحد المسموح.",
    "invalid_metadata": "هوية المصدر أو توقيت الجلب أو الإطار المعلن غير متسق.",
    "no_candles": "أعاد المصدر سلسلة بلا شموع.",
    "invalid_candles": "توجد شموع ناقصة أو قيم سعر وحجم غير صالحة.",
    "invalid_timestamps": "توجد أوقات شموع مفقودة أو غير صالحة.",
    "duplicate_timestamps": "توجد أوقات شموع مكررة؛ لم نحذفها أو ندمجها.",
    "out_of_order_timestamps": "توجد شموع بترتيب زمني معكوس؛ لم نعد ترتيب المصدر.",
    "future_timestamps": "توجد شموع مؤرخة بعد وقت قراءة البيانات.",
    "inconsistent_fetch_time": "وقت شمعة يتجاوز وقت الجلب، أو وقت الجلب في المستقبل.",
    "missing_intervals": "توجد فترات مفقودة في إطار مستمر معلن.",
    "irregular_intervals": "الفواصل لا تطابق شبكة الإطار المستمر المعلن.",
    "stale_cache": "فشل تحديث المصدر؛ حُجبت الاستنتاجات لهذه النسخة السابقة.",
    "provider_unverified": "مزوّد الشموع غير معلن؛ الحسابات وصفية ومحدودة.",
    "interval_unverified": "الإطار غير معلن؛ لم نستنتجه من المسافة بين الشموع.",
    "session_calendar_unverified": "تقويم الجلسات والعطل غير متحقق؛ الفواصل الطويلة لا تثبت فقد شموع.",
    "calendar_interval_unverified": "الإطار تقويمي؛ لم نحوله إلى عدد ثابت من الثواني.",
    "insufficient_samples": "عدد الشموع غير كافٍ: الاتجاه 50، والزخم والتذبذب 15.",
}


def quality_label(quality: CandleQuality | None) -> str:
    return (
        {"usable": "قابلة للاستخدام", "limited": "محدودة", "unavailable": "غير متاحة"}[
            quality.status
        ]
        if quality
        else "محدودة - لم تُفحص جودة هذه اللقطة"
    )


def quality_lines(quality: CandleQuality | None) -> list[str]:
    if quality is None:
        return [quality_label(None), "لقطة سابقة بلا فحص جودة؛ لم نعد تقييمها أو نغير بياناتها."]
    lines = [f"جودة الشموع: {quality_label(quality)}. حداثة السوق واكتمال التغطية غير معتمدتين."]
    for key, label in (
        ("received_candles", "الشموع المستلمة"),
        ("invalid_candles", "شموع غير صالحة"),
        ("invalid_timestamps", "أوقات غير صالحة"),
        ("duplicate_timestamps", "أوقات مكررة"),
        ("out_of_order_pairs", "أزواج معكوسة"),
        ("future_timestamps", "أوقات مستقبلية"),
        ("gap_count", "فواصل أطول من الإطار"),
        ("missing_intervals", "فترات مفقودة في الإطار المستمر"),
        ("irregular_intervals", "فواصل غير منتظمة في الإطار المستمر"),
        ("largest_gap_seconds", "أكبر فاصل بالثواني"),
    ):
        value = getattr(quality, key)
        lines.append(f"{label}: {value if value is not None else 'غير معلوم'}.")
    lines.extend(QUALITY_REASONS[r] for r in quality.reasons)
    return lines


class BriefEntry(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    symbol: TerminalSymbol
    snapshots: tuple[ResearchSnapshot, ...] = Field(max_length=2)

    _symbol = field_validator("symbol")(valid_symbol)

    @model_validator(mode="after")
    def identity(self) -> Self:
        if any(s.report.symbol != self.symbol for s in self.snapshots):
            raise ValueError("Brief symbol mismatch")
        if len({s.id for s in self.snapshots}) != len(self.snapshots):
            raise ValueError("Duplicate snapshot")
        if len(self.snapshots) == 2 and self.snapshots[0].saved_at < self.snapshots[1].saved_at:
            raise ValueError("Snapshot order mismatch")
        return self


class ResearchBrief(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    generated_at: UTCDateTime
    entries: tuple[BriefEntry, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def clocks(self) -> Self:
        if len({e.symbol for e in self.entries}) != len(self.entries):
            raise ValueError("Duplicate watch symbol")
        if any(s.saved_at > self.generated_at for e in self.entries for s in e.snapshots):
            raise ValueError("Future saved snapshot")
        return self


def local_time(value: datetime | None) -> str:
    return (
        value.astimezone(ZoneInfo("Africa/Casablanca")).strftime("%Y-%m-%d %H:%M:%S")
        if value
        else "غير معلن"
    )


def number(value: Decimal | None) -> str:
    return "غير متاح" if value is None else format(value, ".6g")


def indicator_explanations(
    a: CandleAnalysis | None, quality: CandleQuality | None = None
) -> list[tuple[str, str]]:
    def qualified(rows: list[tuple[str, str]]) -> list[tuple[str, str]]:
        if quality is None:
            return rows
        checks = (quality.trend, quality.momentum, quality.volatility)
        return [
            (
                title,
                (
                    explanation
                    if check.allowed
                    else "حُجب هذا الاستنتاج بسبب جودة البيانات. "
                    + " ".join(QUALITY_REASONS[r] for r in check.reasons)
                ),
            )
            for (title, explanation), check in zip(rows, checks, strict=True)
        ]

    if a is None:
        return qualified(
            [
                (title, "لا تتوفر شموع صالحة؛ لا نستنتج هذه القراءة من السعر وحده.")
                for title in ("الاتجاه", "الزخم", "التذبذب")
            ]
        )
    if a.sma20 is None or a.sma50 is None:
        trend = f"المتاح {a.count} شمعة؛ نحتاج 50 شمعة لمقارنة المتوسطين."
    else:
        direction = (
            "يميل للصعود"
            if a.last_close > a.sma20 > a.sma50
            else "يميل للهبوط" if a.last_close < a.sma20 < a.sma50 else "مختلط"
        )
        distance = (a.last_close / a.sma20 - 1) * 100
        trend = f"ترتيب الإغلاق والمتوسطين {direction}. الإغلاق {number(a.last_close)}، متوسط 20 شمعة {number(a.sma20)}، ومتوسط 50 شمعة {number(a.sma50)}. المسافة عن متوسط 20: {number(distance)}%."
    if a.rsi14_simple is None:
        momentum = "RSI غير متاح؛ نحتاج 15 شمعة لقياس آخر 14 تغيرًا في الإغلاق."
    else:
        balance = (
            "الارتفاعات أكبر من الانخفاضات"
            if a.rsi14_simple > 50
            else (
                "الانخفاضات أكبر من الارتفاعات"
                if a.rsi14_simple < 50
                else "الارتفاعات والانخفاضات متوازنة، أو الإغلاق ثابت"
            )
        )
        momentum = f"RSI 14 = {number(a.rsi14_simple)} من 100، بمتوسط بسيط. {balance} في هذه العينة. نقطة المقارنة 50؛ هذه ليست توقعات انعكاس."
    volatility = "ATR غير متاح؛ نحتاج 15 شمعة لقياس الحركة في آخر 14 شمعة."
    if a.atr14_simple is not None:
        volatility = f"متوسط النطاق الحقيقي ATR 14 = {number(a.atr14_simple)} بوحدة سعر الشموع، أي {number(a.atr14_simple / a.last_close * 100)}% من الإغلاق. يشمل نطاق الشمعة والفجوة عن الإغلاق السابق، ولا يحدد اتجاه الحركة أو تصنيف التذبذب دون مقارنة تاريخية."
    return qualified([("الاتجاه", trend), ("الزخم", momentum), ("التذبذب", volatility)])


def previous_report(entry: BriefEntry) -> TerminalResearch | None:
    if (
        len(entry.snapshots) == 2
        and entry.snapshots[1].report.assessed_at < entry.snapshots[0].report.assessed_at
    ):
        return entry.snapshots[1].report
    return None


def comparison_lines(current: TerminalResearch, previous: TerminalResearch | None) -> list[str]:
    if previous is None:
        return ["لا توجد لقطة سابقة أقدم لهذه القراءة؛ لا توجد مقارنة معتمدة."]
    a, b = current.analysis, previous.analysis
    comparable = bool(
        a
        and b
        and a.history_provider != "UNKNOWN"
        and a.history_provider == b.history_provider
        and a.interval != "UNVERIFIED"
        and a.interval == b.interval
    )
    lines = [
        f"وقت القراءة السابقة: {local_time(previous.assessed_at)}. الأرقام التالية: السابقة ثم الحالية."
    ]
    lines.append(
        f"جودة الشموع: {quality_label(previous.data_quality)} ثم {quality_label(current.data_quality)}."
    )
    trends = {
        "above_averages": "ترتيب صاعد",
        "below_averages": "ترتيب هابط",
        "mixed": "مختلط",
        "insufficient": "غير كافٍ",
    }
    lines.append(
        f"الاتجاه: {trends[b.trend] if b else 'غير متاح'} ثم {trends[a.trend] if a else 'غير متاح'}."
    )
    if not comparable:
        lines.append(
            "قابلية المقارنة غير مؤكدة: الشموع ناقصة أو المزوّد/الإطار مختلف أو غير معلن. لا نعتبر اختلاف القيم دليلًا على حركة السوق."
        )
    labels = {
        "last_close": "الإغلاق",
        "sma20": "متوسط 20",
        "sma50": "متوسط 50",
        "rsi14_simple": "RSI 14",
        "atr14_simple": "ATR 14",
    }
    for key, label in labels.items():
        before, after = getattr(b, key, None), getattr(a, key, None)
        delta = (
            f"؛ الفرق {number(after - before)}"
            if comparable and before is not None and after is not None
            else ""
        )
        changed = "تغيرت القراءة" if before != after else "دون تغير"
        lines.append(f"{label}: {number(before)} ثم {number(after)}{delta} - {changed}.")
    states = {"available": "متاح", "unavailable": "غير متاح", "invalid": "مرفوض"}
    kinds = {"quotes": "السعر", "history": "الشموع", "news": "الأخبار"}
    for source in current.sources:
        prior = next(s for s in previous.sources if s.kind == source.kind)
        if prior.state != source.state:
            lines.append(
                f"تغير توفر {kinds[source.kind]}: {states[prior.state]} ثم {states[source.state]}."
            )
    news_ok = all(
        next(s for s in r.sources if s.kind == "news").state == "available"
        for r in (current, previous)
    )
    if news_ok:
        old = {str(h.url): h for h in previous.headlines}
        new = {str(h.url): h for h in current.headlines}
        edited = sum(old[url] != new[url] for url in old.keys() & new.keys())
        lines.append(
            f"العناوين المُعادة: ظهرت {len(new.keys() - old.keys())}، تغيرت بيانات {edited}، وغابت عن النتائج {len(old.keys() - new.keys())}. ظهور العنوان لا يعني نشر حدث جديد، وغيابه لا يعني حذف المقال."
        )
    else:
        lines.append("الأخبار ناقصة في إحدى القراءتين؛ لا نستنتج أن عناوين ظهرت أو اختفت.")
    return lines
