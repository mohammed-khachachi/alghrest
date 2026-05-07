"""
ALGHREST — Agent 07: Social Sentiment Analyst
Streams Twitter/X mentions and Reddit posts for tracked crypto assets.
Applies VADER sentiment + custom Fear & Greed calculation.
Publishes per-asset SentimentSignal to sentiment.scored Kafka topic.
"""
from __future__ import annotations

import asyncio
import re
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any

import structlog
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import KafkaTopic, SentimentScore, SentimentSignal, SignalDirection

logger = structlog.get_logger(__name__)

TRACKED_SYMBOLS = {
    "BTC": ["bitcoin", "btc", "#bitcoin", "$btc", "BTC"],
    "ETH": ["ethereum", "eth", "#ethereum", "$eth", "ETH"],
    "SOL": ["solana", "sol", "#solana", "$sol"],
    "BNB": ["binance", "bnb", "$bnb"],
    "AVAX": ["avalanche", "avax", "$avax"],
    "LINK": ["chainlink", "link", "$link"],
}

CRYPTO_SUBREDDITS = [
    "CryptoCurrency", "Bitcoin", "ethereum", "solana",
    "defi", "CryptoMarkets", "BitcoinMarkets",
]


class SentimentAnalyst(BaseAgent):
    """Agent 07 — Aggregates Twitter/Reddit sentiment per asset."""

    AGENT_ID = 7

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="sentiment_analyst")
        self._vader = SentimentIntensityAnalyzer()
        # Rolling windows of (timestamp, score) tuples per symbol
        self._sentiment_windows: dict[str, deque] = defaultdict(lambda: deque(maxlen=500))
        self._mention_counts: dict[str, int] = defaultdict(int)
        self._reddit = None
        self._twitter_bearer = settings.twitter_bearer_token

    async def initialize(self) -> None:
        # Initialize Reddit PRAW if credentials available
        if settings.reddit_client_id and settings.reddit_client_secret:
            try:
                import asyncpraw
                self._reddit = asyncpraw.Reddit(
                    client_id=settings.reddit_client_id,
                    client_secret=settings.reddit_client_secret,
                    user_agent=settings.reddit_user_agent,
                )
                self.logger.info("Reddit PRAW initialized")
            except ImportError:
                self.logger.warning("asyncpraw not installed — Reddit disabled")
            except Exception as e:
                self.logger.warning("Reddit init failed", error=str(e))

        if self._twitter_bearer:
            self.logger.info("Twitter bearer token configured")
        else:
            self.logger.warning("TWITTER_BEARER_TOKEN not set — Twitter streaming disabled")

        self.logger.info("sentiment analyst ready", tracked_symbols=list(TRACKED_SYMBOLS.keys()))

    async def run(self) -> None:
        """Run Reddit polling + Twitter streaming + periodic aggregation."""
        tasks = [
            asyncio.create_task(self._reddit_polling_loop(), name="reddit_poll"),
            asyncio.create_task(self._twitter_streaming_loop(), name="twitter_stream"),
            asyncio.create_task(self._aggregation_loop(), name="aggregation"),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── REDDIT ────────────────────────────────────────────────────────────────

    async def _reddit_polling_loop(self) -> None:
        """Poll hot posts and new comments from crypto subreddits every 5 min."""
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue
            try:
                if self._reddit:
                    await self._poll_reddit()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.warning("Reddit poll error", error=str(e))
            await asyncio.sleep(300)

    async def _poll_reddit(self) -> None:
        for subreddit_name in CRYPTO_SUBREDDITS[:3]:  # Limit API calls
            try:
                subreddit = await self._reddit.subreddit(subreddit_name)
                async for submission in subreddit.hot(limit=25):
                    text = f"{submission.title} {submission.selftext}"
                    await self._process_text(text, source="reddit", metadata={"subreddit": subreddit_name})
            except Exception as e:
                self.logger.debug("reddit subreddit error", sub=subreddit_name, error=str(e))

    # ── TWITTER ───────────────────────────────────────────────────────────────

    async def _twitter_streaming_loop(self) -> None:
        """Stream Twitter/X filtered stream for tracked crypto keywords."""
        if not self._twitter_bearer:
            self.logger.warning("Twitter disabled — no bearer token")
            return

        import httpx
        query = " OR ".join([kw for kws in TRACKED_SYMBOLS.values() for kw in kws[:2]])
        # Twitter filtered stream is complex — use search API in 15-min windows
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue
            try:
                await self._poll_twitter_recent(query)
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.warning("Twitter poll error", error=str(e))
            await asyncio.sleep(900)  # 15-minute intervals (rate limits)

    async def _poll_twitter_recent(self, query: str) -> None:
        """Search recent tweets (last 15 min)."""
        import httpx
        now = datetime.utcnow()
        start = (now - timedelta(minutes=15)).strftime("%Y-%m-%dT%H:%M:%SZ")

        headers = {"Authorization": f"Bearer {self._twitter_bearer}"}
        params = {
            "query": f"({query}) lang:en -is:retweet",
            "max_results": 100,
            "start_time": start,
            "tweet.fields": "created_at,public_metrics",
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                "https://api.twitter.com/2/tweets/search/recent",
                headers=headers, params=params,
            )
            if r.status_code == 429:
                self.logger.warning("Twitter rate limited — backing off")
                await asyncio.sleep(900)
                return
            r.raise_for_status()
            data = r.json()

        for tweet in data.get("data", []):
            metrics = tweet.get("public_metrics", {})
            engagement = (
                metrics.get("like_count", 0) +
                metrics.get("retweet_count", 0) * 3 +
                metrics.get("reply_count", 0)
            )
            await self._process_text(
                tweet["text"], source="twitter",
                metadata={"engagement": engagement, "tweet_id": tweet["id"]}
            )

    # ── SENTIMENT PROCESSING ──────────────────────────────────────────────────

    async def _process_text(self, text: str, source: str, metadata: dict | None = None) -> None:
        """Apply VADER sentiment and route to appropriate symbol windows."""
        text_lower = text.lower()
        scores = self._vader.polarity_scores(text)
        compound = scores["compound"]   # -1 to +1

        # Route to all matched symbols
        for symbol, keywords in TRACKED_SYMBOLS.items():
            if any(kw.lower() in text_lower for kw in keywords):
                engagement = (metadata or {}).get("engagement", 1)
                # Weight score by engagement (viral = more impact), clamped to [-1, 1]
                weighted_score = compound * (1 + min(engagement, 100) / 100)
                weighted_score = max(-1.0, min(1.0, weighted_score))
                self._sentiment_windows[symbol].append((datetime.utcnow(), weighted_score))
                self._mention_counts[symbol] += 1

    # ── AGGREGATION & PUBLISHING ──────────────────────────────────────────────

    async def _aggregation_loop(self) -> None:
        """Compute and publish aggregate sentiment every 15 minutes."""
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue
            try:
                await self._publish_all_sentiments()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error("aggregation error", error=str(e))
            await asyncio.sleep(900)  # Every 15 minutes

    async def _publish_all_sentiments(self) -> None:
        now = datetime.utcnow()
        cutoff = now - timedelta(hours=1)

        for symbol in TRACKED_SYMBOLS:
            window = self._sentiment_windows[symbol]
            # Keep only last hour
            recent = [(ts, s) for ts, s in window if ts > cutoff]

            if len(recent) < 3:
                continue  # Not enough data

            scores = [s for _, s in recent]
            avg_score = sum(scores) / len(scores)
            volume = self._mention_counts[symbol]

            direction = self._score_to_direction(avg_score)

            score_model = SentimentScore(
                symbol=symbol,
                timestamp=now,
                source="aggregate",
                score=avg_score,
                volume=volume,
                positive_count=sum(1 for s in scores if s > 0.05),
                negative_count=sum(1 for s in scores if s < -0.05),
                neutral_count=sum(1 for s in scores if abs(s) <= 0.05),
            )

            signal = SentimentSignal(
                source_agent_id=self.agent_id,
                symbol=symbol,
                direction=direction,
                confidence=min(abs(avg_score), 1.0),
                source="aggregate",
                sentiment_score=avg_score,
                volume_mentions=volume,
            )

            await self.publish(
                KafkaTopic.SENTIMENT_SCORED,
                payload=signal.model_dump(mode="json"),
                message_type="sentiment_signal",
            )

            self.logger.debug(
                "sentiment published",
                symbol=symbol,
                score=round(avg_score, 3),
                volume=volume,
                direction=direction.value,
            )

            # Reset mention counts for next period
            self._mention_counts[symbol] = 0

    @staticmethod
    def _score_to_direction(score: float) -> SignalDirection:
        if score >= 0.35:
            return SignalDirection.STRONG_BULLISH
        if score >= 0.10:
            return SignalDirection.BULLISH
        if score <= -0.35:
            return SignalDirection.STRONG_BEARISH
        if score <= -0.10:
            return SignalDirection.BEARISH
        return SignalDirection.NEUTRAL

    async def shutdown(self) -> None:
        if self._reddit:
            await self._reddit.close()
        self.logger.info("sentiment analyst shutdown")
