"""Bounded official schedules for display only; coverage is always partial."""

import asyncio
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import httpx
from pydantic import HttpUrl

from connectors.advisory.news import download
from core.advisory.models import EconomicEvent, utcnow
from core.advisory.news_context import ScheduledContext, SourceStatus, relevance

CALENDARS = {
    "FOMC": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
    "BEA": "https://www.bea.gov/news/schedule",
    "BLS calendar": "https://www.bls.gov/schedule/news_release/bls.ics",
}
MONTHS = {
    name: i
    for i, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        1,
    )
}
MONTHS.update({name[:3]: number for name, number in list(MONTHS.items())})


@dataclass
class Node:
    tag: str
    attrs: dict[str, str] = field(default_factory=dict)
    children: list["Node"] = field(default_factory=list)
    text: str = ""

    def content(self) -> str:
        return " ".join((self.text + " " + " ".join(c.content() for c in self.children)).split())

    def find(self, *, tag: str = "", cls: str = "", identity: str = "") -> list["Node"]:
        own = (
            (not tag or self.tag == tag)
            and (not cls or cls in self.attrs.get("class", "").split())
            and (not identity or self.attrs.get("id") == identity)
        )
        return ([self] if own else []) + [
            n for child in self.children for n in child.find(tag=tag, cls=cls, identity=identity)
        ]


class ScheduleHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if len(self.stack) > 80:
            raise ValueError("HTML nesting limit")
        node = Node(tag, {k: v or "" for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                return

    def handle_data(self, data: str) -> None:
        if self.stack[-1].tag not in {"script", "style"}:
            self.stack[-1].text += " " + data


def _one(nodes: list[Node]) -> Node:
    if len(nodes) != 1:
        raise ValueError("Schedule layout changed")
    return nodes[0]


def _entry(
    name: str,
    title: str,
    start: date | None,
    end: date | None,
    printed: str | None,
    now: datetime,
    *,
    scheduled: datetime | None = None,
    zone: str | None = None,
    cancelled: bool = False,
) -> ScheduledContext:
    identity = hashlib.sha256(f"{name}|{title}|{start}|{end}|{printed}".encode()).hexdigest()[:32]
    return ScheduledContext.model_validate(
        {
            "event": EconomicEvent(
                id=identity,
                name=title[:200],
                known_at=now,
                scheduled_at=scheduled,
                source=HttpUrl(CALENDARS[name]),
                affected_markets=("MES", "MNQ"),
                impact="unknown",
                status="cancelled" if cancelled else "scheduled" if start else "unknown",
            ),
            "source_name": name,
            "date_start": start,
            "date_end": end,
            "printed_time": printed,
            "timezone": zone,
            "relevance": relevance(title, []) or ("official_schedule_other",),
        }
    )


def _eastern(naive: datetime) -> datetime:
    zone = ZoneInfo("America/New_York")
    aware = naive.replace(tzinfo=zone)
    if (
        aware.utcoffset() != naive.replace(tzinfo=zone, fold=1).utcoffset()
        or aware.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != naive
    ):
        raise ValueError("Ambiguous or nonexistent local time")
    return aware.astimezone(UTC)


def _ics(body: str, now: datetime) -> list[ScheduledContext]:
    if not body.startswith("BEGIN:VCALENDAR") or "END:VCALENDAR" not in body:
        raise ValueError("Not an iCalendar")
    text = re.sub(r"\r?\n[ \t]", "", body)
    result = []
    blocks = re.findall(r"BEGIN:VEVENT\r?\n(.*?)END:VEVENT", text, re.S)
    if text.count("BEGIN:VEVENT") != len(blocks):
        raise ValueError("Truncated event")
    for block in blocks:
        fields: dict[str, tuple[str, str]] = {}
        for line in block.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            base = key.split(";", 1)[0]
            if base in {"SUMMARY", "DTSTART", "STATUS", "RRULE", "RECURRENCE-ID"}:
                if base in fields:
                    raise ValueError("Duplicate iCalendar field")
                fields[base] = (key, value)
        if "RRULE" in fields or "RECURRENCE-ID" in fields:
            raise ValueError("Unsupported recurring schedule")
        title = fields.get("SUMMARY", ("", ""))[1].replace(r"\,", ",").replace(r"\n", " ")
        if not title or "DTSTART" not in fields:
            raise ValueError("Incomplete calendar event")
        key, value = fields["DTSTART"]
        scheduled = None
        zone = None
        if key == "DTSTART;VALUE=DATE":
            day = datetime.strptime(value, "%Y%m%d").date()
        elif key == "DTSTART;TZID=America/New_York":
            naive = datetime.strptime(value, "%Y%m%dT%H%M%S")
            day, scheduled, zone = naive.date(), _eastern(naive), "America/New_York"
        elif key == "DTSTART" and value.endswith("Z"):
            scheduled = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            day, zone = scheduled.date(), "UTC"
        else:
            raise ValueError("Unspecified or unsupported event timezone")
        result.append(
            _entry(
                "BLS calendar",
                title,
                day,
                day,
                value,
                now,
                scheduled=scheduled,
                zone=zone,
                cancelled=fields.get("STATUS", ("", ""))[1] == "CANCELLED",
            )
        )
    return result


def parse_calendar(name: str, body: bytes, *, now: datetime) -> list[ScheduledContext]:
    text = body.decode("utf-8-sig")
    if name == "BLS calendar":
        result = _ics(text, now)
    else:
        parser = ScheduleHTML()
        parser.feed(text)
        root = parser.root
        result = []
        if name == "FOMC":
            recognized = False
            for panel in root.find(cls="panel"):
                heads = panel.find(tag="h4")
                match = (
                    re.fullmatch(r"(\d{4}) FOMC Meetings", heads[0].content())
                    if len(heads) == 1
                    else None
                )
                if not match or not now.year <= int(match[1]) <= now.year + 1:
                    continue
                recognized = True
                year = int(match[1])
                meetings = panel.find(cls="fomc-meeting")
                if not meetings:
                    raise ValueError("Missing meeting rows")
                for meeting in meetings:
                    month = _one(meeting.find(cls="fomc-meeting__month")).content()
                    printed = _one(meeting.find(cls="fomc-meeting__date")).content().rstrip("*")
                    if not re.fullmatch(r"\d{1,2}(-\d{1,2})?", printed):
                        raise ValueError("Unknown FOMC date format")
                    months, days = month.split("/"), printed.split("-")
                    first, last = MONTHS[months[0]], MONTHS[months[-1]]
                    start = date(year, first, int(days[0]))
                    end = date(year + int(last < first), last, int(days[-1]))
                    result.append(_entry(name, "FOMC meeting", start, end, None, now))
            if not recognized:
                raise ValueError("No current FOMC schedule")
        elif name == "BEA":
            table = _one(root.find(tag="table", identity="release-schedule-table"))
            match = re.search(r"Year (\d{4})", _one(table.find(tag="thead")).content())
            if match is None:
                raise ValueError("Missing schedule year")
            year = int(match[1])
            rows = _one(table.find(tag="tbody")).find(tag="tr")
            for row in rows:
                title = _one(row.find(cls="release-title")).content()
                when = _one(row.find(cls="scheduled-date"))
                if "To Be Announced" in when.content():
                    result.append(_entry(name, title, None, None, when.content()[:120], now))
                    continue
                day = datetime.strptime(
                    f"{_one(when.find(cls='release-date')).content()} {year}", "%B %d %Y"
                ).date()
                printed = _one(when.find(tag="small")).content()
                # The inspected page gives a wall time without an explicit timezone.
                # Keep it literal; never infer an Eastern/UTC timestamp.
                result.append(_entry(name, title, day, day, printed, now))
            if not rows:
                raise ValueError("Missing BEA schedule rows")
        else:
            raise ValueError("Unknown calendar")
    if len(result) > 1000 or len({r.event.id for r in result}) != len(result):
        raise ValueError("Oversize or duplicate schedule")
    return result


class CalendarCache:
    def __init__(self) -> None:
        self._locks = {name: asyncio.Lock() for name in CALENDARS}
        self._values: dict[str, tuple[float, list[ScheduledContext], SourceStatus]] = {}

    async def get(
        self, client: httpx.AsyncClient, name: str
    ) -> tuple[list[ScheduledContext], SourceStatus]:
        async with self._locks[name]:
            cached = self._values.get(name)
            if cached and time.monotonic() < cached[0]:
                return list(cached[1]), cached[2]
            url, attempted = CALENDARS[name], utcnow()
            code, sha = None, None
            try:
                async with asyncio.timeout(12):
                    content, code = await download(client, url)
                fetched = utcnow()
                sha = hashlib.sha256(content).hexdigest()
                events = await asyncio.to_thread(parse_calendar, name, content, now=fetched)
                status = SourceStatus(
                    name=name,
                    url=HttpUrl(url),
                    kind="calendar",
                    attempted_at=attempted,
                    fetched_at=fetched,
                    state="ok" if events else "empty",
                    http_status=code,
                    content_sha256=sha,
                    parsed_count=len(events),
                    usable_count=len(events),
                    reasons=("partial_schedule",),
                )
            except (httpx.HTTPError, TimeoutError, ValueError, TypeError, KeyError) as exc:
                if isinstance(exc, httpx.HTTPStatusError):
                    code = exc.response.status_code
                unavailable = isinstance(exc, httpx.HTTPError | TimeoutError)
                events = []
                status = SourceStatus(
                    name=name,
                    url=HttpUrl(url),
                    kind="calendar",
                    attempted_at=attempted,
                    state="unavailable" if unavailable else "invalid",
                    http_status=code,
                    content_sha256=sha,
                    reasons=(
                        "source_unavailable" if unavailable else "invalid_schedule_format",
                        "partial_schedule",
                    ),
                )
            self._values[name] = (
                time.monotonic() + (300 if status.fetched_at else 30),
                events,
                status,
            )
            return list(events), status
