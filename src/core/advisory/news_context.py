"""Partial published context. Never a market snapshot or an event-clearance signal."""

import re
from datetime import date, datetime, timedelta
from typing import Literal, Self

from pydantic import ConfigDict, Field, HttpUrl, model_validator

from core.advisory.models import EconomicEvent, News, Strict, UTCDateTime, utc_instant


class ContextModel(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceStatus(ContextModel):
    name: str
    url: HttpUrl
    kind: Literal["news", "calendar"]
    attempted_at: UTCDateTime
    fetched_at: UTCDateTime | None = None
    state: Literal["ok", "empty", "stale", "unavailable", "invalid"]
    http_status: int | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    parsed_count: int = Field(default=0, ge=0)
    usable_count: int = Field(default=0, ge=0)
    reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if self.usable_count > self.parsed_count:
            raise ValueError("Usable count exceeds parsed entries")
        if self.fetched_at is not None and self.fetched_at < self.attempted_at:
            raise ValueError("Fetch precedes request")
        if self.state in {"ok", "empty", "stale"} and (
            self.fetched_at is None or self.content_sha256 is None
        ):
            raise ValueError("Successful content needs retrieval identity")
        return self


class ContextHeadline(ContextModel):
    item: News
    relevance: tuple[str, ...] = Field(min_length=1)


class ScheduledContext(ContextModel):
    event: EconomicEvent
    source_name: str
    date_start: date | None
    date_end: date | None
    printed_time: str | None = Field(max_length=120)
    timezone: Literal["America/New_York", "UTC"] | None
    relevance: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def coherent(self) -> Self:
        if (self.date_start is None) != (self.date_end is None):
            raise ValueError("Incomplete date range")
        if self.date_start and self.date_end and self.date_end < self.date_start:
            raise ValueError("Reversed date range")
        if self.event.scheduled_at is not None and self.timezone is None:
            raise ValueError("Exact event time requires a declared source timezone")
        if self.event.impact != "unknown":
            raise ValueError("Official schedule does not assign our impact rating")
        return self


class NewsContext(ContextModel):
    schema_version: Literal["news-events-v1"] = "news-events-v1"
    instrument_id: Literal["MES", "MNQ"]
    assessed_at: UTCDateTime
    headlines: tuple[ContextHeadline, ...]
    events: tuple[ScheduledContext, ...]
    sources: tuple[SourceStatus, ...]
    returned_date_start: date | None
    returned_date_end: date | None
    coverage: Literal["partial"] = "partial"
    event_risk: Literal["UNKNOWN"] = "UNKNOWN"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False


TOPICS = {
    "inflation": r"\b(inflation|cpi|ppi|personal income|outlays|pce)\b",
    "central_bank": r"\b(fed|fomc|federal reserve|interest rates?|monetary)\b",
    "labor": r"\b(employment|payrolls?|jobs?|job openings|labor|unemployment|wages)\b",
    "growth": r"\b(gdp|gross domestic|economic growth|retail sales|international trade)\b",
    "equity_indexes": r"\b(nasdaq|s&p|equities|stock market|stocks|earnings|technology)\b",
}


def relevance(title: str, interests: list[str]) -> tuple[str, ...]:
    reasons = [key for key, pattern in TOPICS.items() if re.search(pattern, title, re.I)]
    if any(
        term.strip() and re.search(r"(?<!\w)" + re.escape(term.strip()) + r"(?!\w)", title, re.I)
        for term in interests[:50]
    ):
        reasons.append("user_interest")
    return tuple(reasons)


def build_context(
    instrument: Literal["MES", "MNQ"],
    news: list[News],
    events: list[ScheduledContext],
    sources: list[SourceStatus],
    interests: list[str],
    *,
    now: datetime,
) -> NewsContext:
    now = utc_instant(now)
    statuses = []
    for original in sources:
        source = SourceStatus.model_validate(original.model_dump())
        stamp = source.fetched_at or source.attempted_at
        if stamp > now:
            source = source.model_copy(
                update={"state": "invalid", "usable_count": 0, "reasons": ("future_source_clock",)}
            )
        elif source.state in {"ok", "empty", "stale"} and (now - stamp).total_seconds() >= 300:
            source = source.model_copy(
                update={"state": "stale", "usable_count": 0, "reasons": ("stale_source",)}
            )
        statuses.append(source)
    active = {s.name for s in statuses if s.state in {"ok", "empty"}}
    unique = {}
    for original_news in news:
        item = News.model_validate(original_news.model_dump())
        reasons = relevance(item.title, interests)
        if (
            item.source in active
            and now - timedelta(days=7) <= item.published_at <= now
            and reasons
        ):
            unique[str(item.url)] = ContextHeadline(item=item, relevance=reasons)
    selected = []
    for original_event in events:
        value = ScheduledContext.model_validate(original_event.model_dump())
        if (
            value.source_name in active
            and value.event.known_at <= now
            and (value.date_end is None or value.date_end >= now.date())
        ):
            selected.append(value)
    selected = sorted(selected, key=lambda e: (e.date_start or date.max, e.event.id))[:100]
    dates = [d for e in selected for d in (e.date_start, e.date_end) if d is not None]
    return NewsContext(
        instrument_id=instrument,
        assessed_at=now,
        headlines=tuple(
            sorted(unique.values(), key=lambda n: n.item.published_at, reverse=True)[:25]
        ),
        events=tuple(selected),
        sources=tuple(statuses),
        returned_date_start=min(dates) if dates else None,
        returned_date_end=max(dates) if dates else None,
    )
