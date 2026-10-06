"""Headline-only source collection with age limits and explicit source outages."""

import asyncio
import calendar
import hashlib
import re
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

import feedparser
import httpx
from pydantic import HttpUrl

from core.advisory.models import News, utcnow

FEEDS: dict[str, tuple[str, Literal["macro", "crypto", "regulation", "equity"]]] = {
    "Federal Reserve": ("https://www.federalreserve.gov/feeds/press_all.xml", "macro"),
    "BLS": ("https://www.bls.gov/feed/bls_latest.rss", "macro"),
    "CNBC Markets": ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "equity"),
    "SEC": ("https://www.sec.gov/news/pressreleases.rss", "regulation"),
    "Cointelegraph": ("https://cointelegraph.com/rss", "crypto"),
}


class FeedCache:
    """One bounded, single-flight cache per service, before instrument filtering.

    Successful feeds live for five minutes; outages retry after 30 seconds.
    No stale success is returned after a failed refresh. Cancelling a request
    releases its lock without caching an incomplete result.
    """

    def __init__(self) -> None:
        self._values: dict[str, tuple[float, list[News], str | None]] = {}
        self._locks = {name: asyncio.Lock() for name in FEEDS}

    async def get(self, client: httpx.AsyncClient, name: str) -> tuple[list[News], str | None]:
        async with self._locks[name]:
            cached = self._values.get(name)
            if cached and time.monotonic() < cached[0]:
                return list(cached[1]), cached[2]
            items, error = await self._fetch(client, name)
            self._values[name] = (time.monotonic() + (30 if error else 300), items, error)
            return list(items), error

    @staticmethod
    async def _fetch(client: httpx.AsyncClient, name: str) -> tuple[list[News], str | None]:
        url, category = FEEDS[name]
        try:
            content = bytearray()
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes(chunk_size=65536):
                    if len(content) + len(chunk) > 1_000_000:
                        raise ValueError("RSS too large")
                    content.extend(chunk)
            feed = await asyncio.to_thread(feedparser.parse, bytes(content))
            if not feed.entries:
                raise ValueError("No parseable headlines")
            items = []
            for entry in feed.entries[:50]:
                stamp = entry.get("published_parsed") or entry.get("updated_parsed")
                if not stamp:
                    continue
                timestamp = datetime.fromtimestamp(calendar.timegm(stamp), UTC)
                if not utcnow() - timedelta(days=7) <= timestamp <= utcnow() + timedelta(minutes=5):
                    continue
                title, link = str(entry.get("title", ""))[:300], str(entry.get("link", ""))
                if not link.startswith("https://") or not title:
                    continue
                items.append(
                    News(
                        id=hashlib.sha256(link.encode()).hexdigest()[:20],
                        title=title,
                        url=HttpUrl(link),
                        source=name,
                        published_at=timestamp,
                        category=category,
                    )
                )
            return items, None
        except (httpx.HTTPError, ValueError, TypeError):
            return [], f"تعذر تحديث مصدر الأخبار: {name}"


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
                and instrument in {"NASDAQ100", "NQ", "MNQ"}
                and not any(term.search(item.title.lower()) for term in terms)
            ):
                continue
            unique[item.id] = item
    return sorted(unique.values(), key=lambda x: x.published_at, reverse=True)[:25], [
        error for _, error in results if error
    ]
