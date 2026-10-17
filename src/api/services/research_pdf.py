"""Local PDF rendering with embedded fonts, Arabic shaping and no network access."""

import hashlib
import re
import unicodedata
from io import BytesIO
from pathlib import Path
from threading import Lock
from urllib.parse import urlsplit

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    PageBreak,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from core.advisory.openterminal_context import PublicHeadline
from core.advisory.openterminal_research import TerminalResearch
from core.advisory.research_brief import (
    ResearchBrief,
    comparison_lines,
    indicator_explanations,
    local_time,
    number,
    previous_report,
    quality_label,
    quality_lines,
)
from core.advisory.research_freshness import freshness_lines

FONT = "AlghrestResearchArabic"
FONT_LOCK = Lock()
RENDER_LOCK = Lock()
INK = colors.HexColor("#142033")
MUTED = colors.HexColor("#58657A")
PURPLE = colors.HexColor("#6D43C5")
AMBER = colors.HexColor("#8C5100")


def _font() -> None:
    with FONT_LOCK:
        if FONT not in pdfmetrics.getRegisteredFontNames():
            path = Path(__file__).resolve().parents[1] / "assets/research_pdf/DejaVuSans.ttf"
            pdfmetrics.registerFont(TTFont(FONT, str(path)))


def _shape(text: str) -> str:
    clean = "".join(
        c for c in unicodedata.normalize("NFC", text) if unicodedata.category(c) not in {"Cc", "Cf"}
    )
    return str(get_display(arabic_reshaper.reshape(clean)))


class ArabicText(Flowable):  # type: ignore[misc]  # ReportLab's base class has no type stubs.
    """Wrap logical words before shaping each line; split safely across pages."""

    def __init__(
        self,
        text: str,
        *,
        size: float = 10,
        color: colors.Color = INK,
        link: str | None = None,
        lines: tuple[str, ...] | None = None,
    ) -> None:
        Flowable.__init__(self)
        self.text, self.size, self.color, self.link = text, size, color, link
        self.leading = size * 1.55
        self.lines = lines
        self.spaceAfter = 6

    def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
        if self.lines is None:
            lines, current = [], ""
            for word in self.text.split():
                trial = (current + " " + word).strip()
                if pdfmetrics.stringWidth(_shape(trial), FONT, self.size) <= avail_width:
                    current = trial
                    continue
                if current:
                    lines.append(current)
                current = ""
                for char in word:
                    if (
                        current
                        and pdfmetrics.stringWidth(_shape(current + char), FONT, self.size)
                        > avail_width
                    ):
                        lines.append(current)
                        current = ""
                    current += char
            if current:
                lines.append(current)
            self.lines = tuple(lines or [""])
        self.width, self.height = avail_width, len(self.lines) * self.leading
        return self.width, self.height

    def split(self, avail_width: float, avail_height: float) -> list[Flowable]:
        self.wrap(avail_width, avail_height)
        count = int(avail_height // self.leading)
        if not self.lines or count < 1 or count >= len(self.lines):
            return []
        return [
            ArabicText(self.text, size=self.size, color=self.color, link=self.link, lines=part)
            for part in (self.lines[:count], self.lines[count:])
        ]

    def draw(self) -> None:
        self.canv.setFont(FONT, self.size)
        self.canv.setFillColor(self.color)
        for index, line in enumerate(self.lines or ()):
            y = self.height - (index + 1) * self.leading + self.leading * 0.25
            self.canv.drawRightString(self.width, y, _shape(line))
            if self.link:
                self.canv.linkURL(self.link, (0, y - 2, self.width, y + self.leading), relative=1)


def _headlines(report: TerminalResearch) -> list[PublicHeadline]:
    name = (
        re.split(
            r"\b(?:inc|corp|corporation|common stock|class [a-z]|ltd|plc)\b",
            report.quote.name or "",
            flags=re.I,
        )[0].strip(" .,\t")
        if report.quote
        else ""
    )

    def mentions(h: PublicHeadline) -> bool:
        terms = [report.symbol] + ([name] if len(name) >= 3 else [])
        return any(
            re.search(
                r"(?<!\w)" + re.escape(term) + r"(?!\w)",
                h.title,
                flags=0 if len(term) <= 2 else re.I,
            )
            for term in terms
        )

    return sorted(
        report.headlines,
        key=lambda h: (mentions(h), h.published_at.timestamp() if h.published_at else 0),
        reverse=True,
    )[:3]


def render_research_pdf(brief: ResearchBrief) -> bytes:
    # ReportLab's shared dynamic TTFont cannot serve two documents concurrently.
    with RENDER_LOCK:
        return _render_research_pdf(brief)


def _render_research_pdf(brief: ResearchBrief) -> bytes:
    _font()
    stream = BytesIO()
    digest = hashlib.sha256(brief.model_dump_json().encode()).hexdigest()
    doc = SimpleDocTemplate(
        stream,
        pagesize=A4,
        rightMargin=38,
        leftMargin=38,
        topMargin=50,
        bottomMargin=42,
        title="ALGHREST Daily Research Brief",
        author="ALGHREST",
        subject=f"Saved research snapshot brief | SHA-256 {digest}",
    )
    story: list[Flowable] = []

    def text(
        value: str, *, size: float = 10, color: colors.Color = INK, link: str | None = None
    ) -> None:
        story.append(ArabicText(value, size=size, color=color, link=link))

    def heading(value: str) -> None:
        item = ArabicText(value, size=12, color=PURPLE)
        item.keepWithNext = True
        story.extend([Spacer(1, 8), item])

    text("ALGHREST", size=25, color=PURPLE)
    text("موجز البحث اليومي", size=20)
    text(f"أُنشئ: {local_time(brief.generated_at)} - توقيت المغرب", color=MUTED)
    text(
        "تقرير مؤرخ من أحدث اللقطات المحفوظة. وقت إنشاء التقرير لا يغيّر توقيت بيانات السوق ولا يجعلها مباشرة.",
        color=AMBER,
    )
    text(
        "الفترات محسوبة بعدد الشموع. حداثة السوق واكتمال الأخبار غير معتمدتين. هذا بحث وصفي والقرار بشري.",
        size=9,
        color=MUTED,
    )
    heading("قائمة الرموز المشمولة")
    rows = [
        [
            ArabicText(t, size=9, color=PURPLE)
            for t in ("السجل", "وقت أحدث قراءة محفوظة - المغرب", "الرمز")
        ]
    ]
    for entry in brief.entries:
        latest = entry.snapshots[0] if entry.snapshots else None
        state = (
            "لا توجد لقطة محفوظة"
            if latest is None
            else (
                "بيانات ناقصة"
                if any(s.state != "available" for s in latest.report.sources)
                else "لقطة محفوظة - الحداثة غير معتمدة"
            )
        )
        if latest and latest.report.data_quality:
            state += f" - جودة الشموع {quality_label(latest.report.data_quality)}"
        rows.append(
            [
                ArabicText(state, size=8.5, color=AMBER),
                ArabicText(
                    local_time(latest.report.assessed_at) if latest else "غير متاح", size=8.5
                ),
                ArabicText(entry.symbol, size=10),
            ]
        )
    table = Table(rows, colWidths=[180, 220, 119], repeatRows=1, hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1ECFA")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#E0E4EB")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.append(table)
    text(
        "الرموز بلا لقطة مذكورة في الجدول؛ لم نولّد لها مؤشرات أو عناوين بديلة. احفظ لقطة لتضمين بحثها في التقرير القادم.",
        size=8.5,
        color=MUTED,
    )
    heading("هوية التقرير")
    text("بصمة محتوى اللقطات والتوقيت - SHA-256:", size=8, color=MUTED)
    text(digest, size=8, color=MUTED)

    states = {"available": "متاح", "unavailable": "غير متاح", "invalid": "مرفوض"}
    kinds = {"quotes": "السعر", "history": "الشموع", "news": "الأخبار"}
    for entry in brief.entries:
        if not entry.snapshots:
            continue
        story.append(PageBreak())
        text(entry.symbol, size=22, color=PURPLE)
        snapshot = entry.snapshots[0]
        r, a = snapshot.report, snapshot.report.analysis
        text("لقطة تاريخية محفوظة؛ ليست قراءة مباشرة الآن.", color=AMBER)
        text(
            f"وقت القراءة: {local_time(r.assessed_at)} | وقت الحفظ: {local_time(snapshot.saved_at)} - المغرب",
            size=8.5,
            color=MUTED,
        )
        text(f"معرّف اللقطة: {snapshot.id}", size=8, color=MUTED)
        if snapshot.restored_from_backup:
            text(
                f"لقطة مستعادة من ملف محلي؛ البصمة تثبت اتساق الملف ولا تثبت مصدره: {snapshot.restored_from_backup}",
                size=8,
                color=AMBER,
            )
        if r.quote:
            text(
                f"السعر المعلن {number(r.quote.price)} {r.quote.currency} | المزوّد {r.quote.provider} | وقت السوق {local_time(r.quote.market_time)}. لا نستبدله بالإغلاق التاريخي.",
                size=9,
            )
            if (
                r.quote.market_time
                and (brief.generated_at - r.quote.market_time).total_seconds() > 900
            ):
                minutes = int((brief.generated_at - r.quote.market_time).total_seconds() / 60)
                text(
                    f"عمر وقت السعر {minutes} دقيقة عند إنشاء التقرير. تنبيه عمر يتجاوز 15 دقيقة؛ لا يثبت تأخير المزوّد ولا يتحقق من جلسة التداول.",
                    size=8.5,
                    color=AMBER,
                )
        heading("حداثة البيانات وسياق الجلسة وقت القراءة")
        for line in freshness_lines(r):
            text(line, size=8.5, color=AMBER)
        heading("جودة بيانات الشموع")
        for line in quality_lines(r.data_quality):
            text(line, size=8.5, color=AMBER)
        heading("الاتجاه والزخم والتذبذب")
        for title, explanation in indicator_explanations(a, r.data_quality):
            text(f"{title}: {explanation}", size=9.5)
        heading("ما تغير منذ اللقطة السابقة")
        for line in comparison_lines(r, previous_report(entry)):
            text(line, size=9)
        heading("حالة البيانات وأوقاتها")
        if a:
            interval = a.interval if a.interval != "UNVERIFIED" else "غير معلن"
            provider = a.history_provider if a.history_provider != "UNKNOWN" else "غير معلن"
            text(
                f"مزوّد الشموع: {provider} | الإطار المطلوب: {interval} | عدد الشموع: {a.count}.",
                size=9,
            )
            text(
                f"آخر شمعة: {local_time(a.last_time)} | آخر جلب ناجح في OpenTerminal: {local_time(a.history_fetched_at)} - المغرب.",
                size=9,
            )
            age = max(0, int((brief.generated_at - a.last_time).total_seconds() / 3600))
            text(
                f"عمر آخر شمعة عند إنشاء التقرير: {age} ساعة؛ قد يشمل جلسة مغلقة أو عطلة، ولا يثبت وحده تعطل المصدر.",
                size=8.5,
                color=MUTED,
            )
            cache = {
                "fetched": "جلب ناجح",
                "cached": "نسخة مؤقتة",
                "stale": "تعثر التحديث؛ أُعيدت نسخة سابقة مع توقيتها الأصلي",
                "UNKNOWN": "غير معلنة",
            }[a.history_cache_state]
            text(
                f"حالة نسخة الشموع: {cache}.",
                size=9,
                color=AMBER if a.history_cache_state == "stale" else MUTED,
            )
        for source in r.sources:
            text(
                f"{kinds[source.kind]}: {states[source.state]} | استلام ALGHREST: {local_time(source.received_at)} - المغرب.",
                size=8.5,
                color=AMBER if source.state != "available" else MUTED,
            )
        heading("عناوين تستحق القراءة")
        text(
            "تُعرض ثلاثة عناوين كحد أقصى، مع تقديم ذكر الرمز أو الاسم في العنوان ثم الأحدث. هذه قرينة عنوانية فقط؛ لم نقرأ المقالات ولا نحدد سبب حركة السعر.",
            size=8.5,
            color=MUTED,
        )
        for index, headline in enumerate(_headlines(r), 1):
            url = str(headline.url)
            safe_link = url if urlsplit(url).scheme == "https" and urlsplit(url).hostname else None
            story.append(
                KeepTogether(
                    [
                        ArabicText(
                            f"{index}. {headline.title}", size=9, color=PURPLE, link=safe_link
                        ),
                        ArabicText(
                            f"{headline.publisher} | نشر: {local_time(headline.published_at)} - المغرب | {urlsplit(url).hostname}",
                            size=8,
                            color=MUTED,
                        ),
                    ]
                )
            )
        if not r.headlines:
            text(
                "لا توجد عناوين صالحة في هذه اللقطة؛ هذا لا يعني عدم وجود أخبار.",
                size=9,
                color=AMBER,
            )
        heading("هوية استجابات المصادر")
        text(
            "البصمات التالية تخص استجابات OpenTerminal المحفوظة، وتتيح مطابقة القراءة مع السجل المحلي.",
            size=8,
            color=MUTED,
        )
        for source in r.sources:
            text(f"{source.kind}: {source.response_sha256 or 'غير متاح'}", size=7.5, color=MUTED)

    def page(canvas: Canvas, document: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setFont(FONT, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(38, A4[1] - 25, "ALGHREST | SAVED RESEARCH")
        canvas.drawRightString(A4[0] - 38, 23, _shape("بحث وصفي - قرار بشري"))
        canvas.drawString(38, 23, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    return stream.getvalue()
