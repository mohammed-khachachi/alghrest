"""Source-reported session context, never an inferred exchange calendar or latency SLA."""

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.advisory.openterminal_research import TerminalResearch

QUOTE_DISPLAY_SECONDS = 900
SESSION_DISPLAY_SECONDS = 90
STATES = {
    "REGULAR": "open",
    "OPEN": "open",
    "CLOSED": "closed",
    "PRE": "pre",
    "PRE-MARKET": "pre",
    "PRE MARKET": "pre",
    "POST": "post",
    "AFTER-HOURS": "post",
    "AFTER HOURS": "post",
}
STATE_NAMES = {
    "open": "مفتوحة",
    "closed": "مغلقة",
    "pre": "قبل الافتتاح",
    "post": "بعد الإغلاق",
    "unknown": "غير معلومة",
}


def quote_freshness(report: "TerminalResearch", now: datetime | None = None) -> dict[str, str]:
    at = now or report.assessed_at
    q = report.quote
    if not q:
        return {"status": "unavailable", "session": "unknown", "message": "السعر غير متاح."}
    o = q.observation
    reported = bool(o and o.market_state_basis == "provider")
    session = (
        STATES.get((q.market_state or "").strip().upper(), "unknown") if reported else "unknown"
    )
    current_state = bool(
        o
        and 0 <= (at - o.fetched_at).total_seconds() < SESSION_DISPLAY_SECONDS
        and o.cache_state != "stale"
    )
    if o and o.cache_state == "stale":
        status, message = "stale_cache", "فشل تحديث السعر؛ هذه نسخة سابقة بوقت جلبها الأصلي."
    elif q.market_time is None:
        status, message = "unknown", "وقت السعر غير معلن؛ لا نثبت حداثته من وقت الجلب."
    elif (at - q.market_time).total_seconds() <= QUOTE_DISPLAY_SECONDS:
        status, message = (
            "within_display_window",
            "وقت السعر ضمن حد العرض البالغ 15 دقيقة؛ لا يثبت أنه مباشر.",
        )
    elif session == "closed" and current_state:
        status, message = (
            "closed_reported",
            "وقت السعر قديم والمصدر أعلن إغلاق السوق عند الجلب؛ هذا لا يثبت تأخر المزوّد.",
        )
    elif session == "open" and current_state:
        status, message = (
            "old_while_open_reported",
            "وقت السعر أقدم من 15 دقيقة والمصدر أعلن جلسة مفتوحة عند الجلب؛ يحتاج مراجعة.",
        )
    else:
        status, message = "old_observation", "وقت السعر أقدم من 15 دقيقة؛ سبب العمر غير متحقق."
    state_note = (
        f"الحالة المعلنة عند الجلب: {STATE_NAMES[session]}."
        if reported
        else "حالة جلسة المصدر غير متحققة؛ لا نعتمد افتراض المحوّل بأن السوق مفتوح."
    )
    if reported and not current_state:
        state_note += " إعلان الحالة قديم أو من نسخة تعثر تحديثها؛ لا يصف حالة السوق الآن."
    return {"status": status, "session": session, "message": message, "session_note": state_note}


def freshness_lines(report: "TerminalResearch") -> list[str]:
    context = quote_freshness(report)
    lines = [context["message"]]
    if "session_note" in context:
        lines.append(context["session_note"])
    q = report.quote
    if q and q.observation:
        lines.append(
            f"آخر جلب للسعر في OpenTerminal: {q.observation.fetched_at.isoformat()}؛ حالة النسخة {q.observation.cache_state}."
        )
    a = report.analysis
    if a:
        age = int((report.assessed_at - a.last_time).total_seconds())
        lines.append(
            f"عمر ختم آخر شمعة عند القراءة: {age} ثانية؛ وقت الشمعة قد يمثل بداية الفترة ولا يثبت آخر تحديث لها."
        )
        lines.append(
            "تقويم الجلسات والعطل وموعد اكتمال الشمعة غير معتمدة؛ لا نحكم على تأخر الشموع من عمرها وحده."
        )
    return lines
