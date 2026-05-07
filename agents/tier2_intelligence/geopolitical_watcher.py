"""
ALGHREST — Agent 10: Geopolitical Watcher
Monitors geopolitical risk via GDELT, Reuters Politics RSS, and PredictIt.
Computes a risk index and classifies impact on crypto/financial markets.
Publishes GeopoliticalSignal to onchain.signals Kafka topic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import feedparser
import httpx
import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import GeopoliticalSignal, KafkaTopic, SignalDirection

logger = structlog.get_logger(__name__)

GEOPOLITICAL_RSS_FEEDS = {
    "reuters_politics": "https://feeds.reuters.com/Reuters/PoliticsNews",
    "reuters_world":    "https://feeds.reuters.com/Reuters/worldNews",
    "bbc_world":        "https://feeds.bbci.co.uk/news/world/rss.xml",
}

HIGH_RISK_KEYWORDS = [
    "sanctions", "war", "conflict", "ban", "regulate", "regulation",
    "arrest", "seized", "hack", "exploit", "breach", "central bank",
    "emergency", "crisis", "default", "debt ceiling", "recession",
    "nuclear", "invasion", "blockade", "tariff", "trade war",
]

CRYPTO_REGULATION_KEYWORDS = [
    "bitcoin", "crypto", "cryptocurrency", "blockchain", "defi", "nft",
    "stablecoin", "sec", "cftc", "fca", "miFID", "mica", "cbdc",
    "digital asset", "exchange", "binance", "coinbase",
]

CRYPTO_BULLISH_KEYWORDS = [
    "etf approved", "legal tender", "institutional adoption", "reserve",
    "spot etf", "custody", "regulated", "framework", "clarity",
]

CRYPTO_BEARISH_KEYWORDS = [
    "ban", "banned", "illegal", "prohibited", "crackdown", "shut down",
    "delisted", "money laundering", "enforcement", "penalty", "fine",
]


class GeopoliticalWatcher(BaseAgent):
    """Agent 10 — Monitors geopolitical events and regulatory developments."""

    AGENT_ID = 10

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="geopolitical_watcher")
        self._risk_index: float = 30.0  # 0-100, starts at baseline
        self._seen_articles: set[str] = set()
        self._gdelt_client: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        self._gdelt_client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "ALGHREST-GeoBot/1.0"},
            follow_redirects=True,
        )
        self.logger.info("geopolitical watcher initialized")

    async def run(self) -> None:
        tasks = [
            asyncio.create_task(self._rss_polling_loop(), name="geo_rss"),
            asyncio.create_task(self._gdelt_polling_loop(), name="gdelt"),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── RSS FEEDS ─────────────────────────────────────────────────────────────

    async def _rss_polling_loop(self) -> None:
        while True:
            if await self.is_halted():
                await asyncio.sleep(60)
                continue
            try:
                await self._process_all_rss()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error("RSS polling error", error=str(e))
            await asyncio.sleep(1800)  # 30 minutes

    async def _process_all_rss(self) -> None:
        for feed_name, feed_url in GEOPOLITICAL_RSS_FEEDS.items():
            try:
                entries = await asyncio.get_event_loop().run_in_executor(
                    None, lambda u=feed_url: feedparser.parse(u).entries
                )
                for entry in entries[:30]:
                    article_id = getattr(entry, "id", getattr(entry, "link", ""))
                    if article_id in self._seen_articles:
                        continue
                    self._seen_articles.add(article_id)

                    # Trim seen set to prevent memory growth
                    if len(self._seen_articles) > 5000:
                        self._seen_articles = set(list(self._seen_articles)[-2500:])

                    headline = getattr(entry, "title", "")
                    summary = getattr(entry, "summary", "")
                    text = f"{headline} {summary}".lower()

                    # Filter for market-relevant content
                    is_high_risk = any(kw in text for kw in HIGH_RISK_KEYWORDS)
                    is_crypto_relevant = any(kw in text for kw in CRYPTO_REGULATION_KEYWORDS)

                    if not (is_high_risk or is_crypto_relevant):
                        continue

                    published = getattr(entry, "published_parsed", None)
                    pub_dt = datetime(*published[:6]) if published else datetime.utcnow()

                    if (datetime.utcnow() - pub_dt).total_seconds() > 86400:
                        continue

                    signal = self._classify_article(headline, summary, pub_dt, feed_name)
                    if signal:
                        await self.publish(
                            KafkaTopic.ONCHAIN_SIGNALS,
                            payload=signal.model_dump(mode="json"),
                            message_type="geopolitical_signal",
                        )
                        self.logger.info(
                            "geo signal published",
                            headline=headline[:80],
                            direction=signal.direction.value,
                            risk_index=signal.risk_index,
                        )

            except Exception as e:
                self.logger.warning("RSS feed error", feed=feed_name, error=str(e))

    def _classify_article(
        self, headline: str, summary: str, published_at: datetime, source: str
    ) -> Optional[GeopoliticalSignal]:
        text_lower = f"{headline} {summary}".lower()

        # Determine event type
        if any(kw in text_lower for kw in ["war", "invasion", "attack", "nuclear"]):
            event_type = "conflict"
        elif any(kw in text_lower for kw in ["sanction", "ban", "embargo"]):
            event_type = "sanctions"
        elif any(kw in text_lower for kw in ["election", "vote", "president"]):
            event_type = "election"
        elif any(kw in text_lower for kw in ["regulation", "ban", "law", "sec", "cftc"]):
            event_type = "regulation"
        elif any(kw in text_lower for kw in ["tariff", "trade war"]):
            event_type = "tariff"
        else:
            event_type = "general"

        # Determine direction for crypto
        bullish_score = sum(1 for kw in CRYPTO_BULLISH_KEYWORDS if kw in text_lower)
        bearish_score = sum(1 for kw in CRYPTO_BEARISH_KEYWORDS if kw in text_lower)
        risk_score = sum(1 for kw in HIGH_RISK_KEYWORDS if kw in text_lower)

        # Update rolling risk index
        if risk_score > 3:
            self._risk_index = min(100, self._risk_index + risk_score * 5)
        else:
            self._risk_index = max(10, self._risk_index - 1)  # Slowly decay

        if bullish_score > bearish_score:
            direction = SignalDirection.BULLISH
        elif bearish_score > bullish_score:
            direction = SignalDirection.BEARISH
        elif risk_score > 2:
            direction = SignalDirection.BEARISH  # High geopolitical risk = risk-off
        else:
            return None  # Not market-relevant enough

        # Determine affected assets
        affected = []
        if any(kw in text_lower for kw in ["bitcoin", "btc"]):
            affected.append("BTC")
        if any(kw in text_lower for kw in ["ethereum", "eth"]):
            affected.append("ETH")
        if any(kw in text_lower for kw in ["crypto", "cryptocurrency"]):
            affected.extend(["BTC", "ETH", "SOL"])

        return GeopoliticalSignal(
            source_agent_id=self.agent_id,
            direction=direction,
            confidence=min(0.4 + risk_score * 0.1, 0.85),
            region=self._infer_region(text_lower),
            event_type=event_type,
            risk_index=self._risk_index,
            affected_assets=list(set(affected)),
            data_source=source,
            metadata={"headline": headline[:200]},
        )

    @staticmethod
    def _infer_region(text: str) -> str:
        regions = {
            "us": ["united states", "washington", "congress", "federal reserve"],
            "eu": ["european", "ecb", "eurozone", "brussels"],
            "china": ["china", "chinese", "beijing", "pboc"],
            "russia": ["russia", "russian", "moscow", "kremlin"],
            "middle_east": ["israel", "iran", "saudi", "opec"],
        }
        for region, keywords in regions.items():
            if any(kw in text for kw in keywords):
                return region
        return "global"

    # ── GDELT ─────────────────────────────────────────────────────────────────

    async def _gdelt_polling_loop(self) -> None:
        """Poll GDELT 2.0 API for geopolitical event data."""
        while True:
            if await self.is_halted():
                await asyncio.sleep(60)
                continue
            try:
                await self._fetch_gdelt_events()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.debug("GDELT fetch error", error=str(e))
            await asyncio.sleep(3600)  # Hourly

    async def _fetch_gdelt_events(self) -> None:
        """Fetch recent high-impact GDELT events."""
        if not self._gdelt_client:
            return
        try:
            r = await self._gdelt_client.get(
                "https://api.gdeltproject.org/api/v2/doc/doc",
                params={
                    "query": "crypto OR bitcoin OR federal+reserve OR sanctions",
                    "mode": "artlist",
                    "maxrecords": 10,
                    "format": "json",
                    "timespan": "1h",
                },
            )
            r.raise_for_status()
            # GDELT responses are JSON with 'articles' array
            data = r.json()
            articles = data.get("articles", [])
            self.logger.debug("GDELT events fetched", count=len(articles))
        except Exception as e:
            self.logger.debug("GDELT unavailable", error=str(e))

    async def shutdown(self) -> None:
        if self._gdelt_client:
            await self._gdelt_client.aclose()
        self.logger.info("geopolitical watcher shutdown")
