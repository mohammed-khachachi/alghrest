"""Headline-only source collection with age limits and explicit source outages."""

import asyncio
import calendar
import hashlib
import re
import time
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlsplit

import feedparser
import httpx
from pydantic import HttpUrl

from core.advisory.models import News, utcnow
from core.advisory.news_context import SourceStatus

FEEDS: dict[str, tuple[str, Literal["macro", "crypto", "regulation", "equity"]]] = {
    "Federal Reserve": ("https://www.federalreserve.gov/feeds/press_all.xml", "macro"),
    "BLS": ("https://www.bls.gov/feed/bls_latest.rss", "macro"),
    "CNBC Markets": ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "equity"),
    "SEC": ("https://www.sec.gov/news/pressreleases.rss", "regulation"),
    "Cointelegraph": ("https://cointelegraph.com/rss", "crypto"),
}


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def plain_text(value: str) -> str:
    parser = PlainText()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


async def download(client: httpx.AsyncClient, url: str) -> tuple[bytes, int]:
    """Fixed configured origins only; do not follow cross-origin or HTTP redirects."""
    current = url
    for _ in range(4):
        async with client.stream("GET", current, follow_redirects=False) as response:
            if response.is_redirect:
                target = str(response.url.join(response.headers.get("location", "")))
                parts = urlsplit(target)
                if (
                    parts.scheme != "https"
                    or parts.netloc != urlsplit(url).netloc
                    or parts.username
                ):
                    raise ValueError("Unapproved redirect")
                current = target
                continue
            response.raise_for_status()
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                if len(content) + len(chunk) > 1_000_000:
                    raise ValueError("Source exceeds size limit")
                content.extend(chunk)
            return bytes(content), response.status_code
    raise ValueError("Too many redirects")


class FeedCache:
    """Bounded single-flight HTTP cache; retrieval timestamps never refresh on reads."""

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, list[News], SourceStatus]] = {}
        self._locks = {name: asyncio.Lock() for name in FEEDS}

    async def get(self, client: httpx.AsyncClient, name: str) -> tuple[list[News], str | None]:
        items, status = await self.context(client, name)
        error = (
            f"تعذر تحديث مصدر الأخبار: {name}"
            if status.state in {"invalid", "unavailable"}
            else None
        )
        return items, error

    async def context(
        self, client: httpx.AsyncClient, name: str
    ) -> tuple[list[News], SourceStatus]:
        async with self._locks[name]:
            cached = self._values.get(name)
            if cached and time.monotonic() < cached[0]:
                return [News.model_validate(item.model_dump()) for item in cached[1]], cached[2]
            items, status = await self._result(client, name)
            ttl = 300 if status.state in {"ok", "empty"} else 30
            self._values[name] = (time.monotonic() + ttl, items, status)
            return [News.model_validate(item.model_dump()) for item in items], status

    @staticmethod
    async def _fetch(client: httpx.AsyncClient, name: str) -> tuple[list[News], str | None]:
        items, status = await FeedCache._result(client, name)
        return items, (
            f"تعذر تحديث مصدر الأخبار: {name}"
            if status.state in {"invalid", "unavailable"}
            else None
        )

    @staticmethod
    async def _result(client: httpx.AsyncClient, name: str) -> tuple[list[News], SourceStatus]:
        url, category = FEEDS[name]
        attempted = utcnow()
        status_code = None
        content_hash = None
        try:
            async with asyncio.timeout(12):
                content, status_code = await download(client, url)
            content_hash = hashlib.sha256(content).hexdigest()
            fetched = utcnow()
            feed = await asyncio.to_thread(feedparser.parse, content)
            if feed.bozo or feed.version not in {
                "rss",
                "rss20",
                "rss10",
                "rss091n",
                "rss092",
                "atom10",
                "atom03",
            }:
                raise ValueError("Invalid feed")
            items = {}
            for entry in feed.entries[:50]:
                try:
                    stamp = entry.get("published_parsed") or entry.get("updated_parsed")
                    if not stamp:
                        continue
                    timestamp = datetime.fromtimestamp(calendar.timegm(stamp), UTC)
                    if (
                        not fetched - timedelta(days=7)
                        <= timestamp
                        <= fetched + timedelta(minutes=5)
                    ):
                        continue
                    title = plain_text(str(entry.get("title", "")))[:300]
                    link = str(entry.get("link", ""))
                    parts = urlsplit(link)
                    if parts.scheme != "https" or not parts.hostname or parts.username or not title:
                        continue
                    item = News(
                        id=hashlib.sha256(link.encode()).hexdigest()[:20],
                        title=title,
                        url=HttpUrl(link),
                        source=name,
                        published_at=timestamp,
                        category=category,
                    )
                    items[item.id] = item
                except (ValueError, TypeError, OverflowError):
                    continue
            reasons = ("no_current_usable_items",) if feed.entries and not items else ()
            return list(items.values()), SourceStatus(
                name=name,
                url=HttpUrl(url),
                kind="news",
                attempted_at=attempted,
                fetched_at=fetched,
                state="ok" if items else "empty",
                http_status=status_code,
                content_sha256=content_hash,
                parsed_count=len(feed.entries[:50]),
                usable_count=len(items),
                reasons=reasons,
            )
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError) as exc:
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code
            unavailable = isinstance(exc, httpx.HTTPError | TimeoutError)
            return [], SourceStatus(
                name=name,
                url=HttpUrl(url),
                kind="news",
                attempted_at=attempted,
                state="unavailable" if unavailable else "invalid",
                http_status=status_code,
                content_sha256=content_hash,
                reasons=("source_unavailable" if unavailable else "invalid_source_format",),
            )


async def headlines(
    client: httpx.AsyncClient,
    instrument: str,
    interests: list[str],
    cache: FeedCache | None = None,
) -> tuple[list[News], list[str]]:
    feeds = cache if cache is not None else FeedCache()
    results = await asyncio.gather(*(feeds.get(client, name) for name in FEEDS))
    terms = [
        re.compile(r"(?<!\w)" + re.escape(t.lower()) + r"(?!\w)")
        for t in ["fed", "inflation", "rate", "nasdaq", *interests]
    ]
    now = utcnow()
    unique = {}
    for items, _ in results:
        for item in items:
            # Cached headlines must still meet the publication-age contract.
            if not now - timedelta(days=7) <= item.published_at <= now + timedelta(minutes=5):
                continue
            if (
                item.category == "crypto"
                and instrument in {"NASDAQ100", "NQ", "MNQ", "MES"}
                and not any(term.search(item.title.lower()) for term in terms)
            ):
                continue
            unique[item.id] = item
    return sorted(unique.values(), key=lambda x: x.published_at, reverse=True)[:25], [
        error for _, error in results if error
    ]
