"""
ALGHREST — Agent 06: News & Events Analyst
Polls RSS feeds (Reuters, Bloomberg, CoinDesk) + dedicated APIs.
Uses Claude Sonnet for NLP classification and FinBERT for sentiment.
Publishes tagged NewsSignal objects to news.tagged Kafka topic.

Prompt caching:
  Articles are processed in batches; the classification rubric (taxonomy,
  impact rubric, output contract, examples) is identical for every article.
  We move all of that into a cached SYSTEM prompt with `cache_control: 5m`
  TTL, and send only the headline + summary in the user message. With ~5
  articles per burst, the first call writes the cache and the next ~4 read
  it cheaply, cutting per-article cost by ~80-90%.
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import Any, Optional

import feedparser
import httpx
import spacy
import structlog
from anthropic import AsyncAnthropic

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import KafkaTopic, NewsItem, NewsSignal, SignalDirection
from core.utils.metrics import claude_calls, claude_input_tokens, claude_output_tokens

logger = structlog.get_logger(__name__)

RSS_FEEDS = {
    "reuters_markets":    "https://feeds.reuters.com/reuters/businessNews",
    "reuters_crypto":     "https://cointelegraph.com/rss",
    "coindesk":           "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "decrypt":            "https://decrypt.co/feed",
    "theblock":           "https://www.theblock.co/rss.xml",
}

CRYPTO_ENTITIES = {
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "binance", "bnb",
    "cardano", "ada", "avalanche", "avax", "polygon", "matic", "chainlink",
    "link", "uniswap", "uni", "aave", "compound", "defi", "nft", "sec",
    "fed", "federal reserve", "inflation", "cpi", "interest rate",
}


_CLAUDE_MODEL = "claude-sonnet-4-6"

# =============================================================================
# CACHED SYSTEM PROMPT
# Identical for every article in a batch — perfect for prompt caching.
# Anything that changes per call (the headline + summary) MUST stay in the
# user message; anything in here invalidates the cache when modified.
# =============================================================================
_NEWS_CLASSIFIER_SYSTEM = """You are a senior financial-news analyst classifying market-moving headlines for an autonomous crypto-and-equities trading system. Each user message contains exactly one news article (headline + short summary). You return one JSON object describing how that article will move markets.

# Output contract
Respond with EXACTLY one JSON object, no markdown fences, no commentary, no leading text. Schema:

{
  "direction": "STRONG_BULLISH" | "BULLISH" | "NEUTRAL" | "BEARISH" | "STRONG_BEARISH",
  "impact_score": <float in [1.0, 10.0]>,
  "categories": [<one or more of: "macro", "regulation", "technology", "defi", "institutional", "exchange", "security", "geopolitics", "monetary_policy", "earnings">],
  "affected_symbols": [<zero or more of: "BTC", "ETH", "SOL", "BNB", "AVAX", "MATIC", "LINK", "UNI", "AAVE", "ADA", "DOT", "XRP", "SPY", "QQQ", "GLD">],
  "summary": "<2 sentences max, factual, no editorialising>"
}

Use double quotes (strict JSON), no trailing commas, no extra keys, no nested arrays inside categories. If an article touches the entire crypto market without naming individual assets, set affected_symbols to ["BTC", "ETH"]. If an article is purely about traditional finance with no crypto crossover, set affected_symbols to [] and impact_score to ≤ 4.0 unless it is a major macro print.

# Direction taxonomy
The five-step direction reflects how the average affected asset will move over the next 24-72 hours, after the article is fully digested by the market.

- STRONG_BULLISH: high-confidence positive catalyst affecting a major asset or sector. Examples: "Spot Bitcoin ETF approved by SEC", "Federal Reserve cuts rates 50bps", "MicroStrategy buys 10,000 BTC", "Ethereum Pectra upgrade activates on mainnet".
- BULLISH: positive but smaller scale or already partially priced. Examples: "BlackRock files BTC ETF amendment", "Coinbase reports profitable quarter", "El Salvador adds 100 BTC to treasury".
- NEUTRAL: factual / informational without clear directional impact. Examples: "Vitalik publishes blog post on rollup roadmap", "exchange announces UI redesign", "SEC schedules round-table".
- BEARISH: negative event with limited contagion. Examples: "Mt. Gox repayment process delayed", "stablecoin briefly depegs to $0.98", "Coinbase reports weaker volumes".
- STRONG_BEARISH: high-confidence negative catalyst. Examples: "FTX-style exchange insolvency announcement", "SEC sues major exchange for unregistered securities", "Federal Reserve hikes rates 75bps unexpectedly", "China announces fresh crypto crackdown", "Major DeFi protocol exploited for $500M".

When the article describes a *rumour* or *speculation* (not a confirmed event), bias one step toward NEUTRAL.

# Impact-score rubric
A continuous score in [1.0, 10.0]. Anchor against these reference points:

- 10.0: existential catalyst — first US spot BTC ETF approval, Federal Reserve emergency rate move, top-10 exchange insolvency.
- 8-9: major catalyst — top-three CEX listing for a top-twenty asset, scheduled Fed press conference with surprise, congressional crypto bill passes a chamber.
- 6-7: significant — meaningful regulatory development on a single asset, top-twenty exchange hack, large protocol upgrade.
- 4-5: standard — routine earnings, planned protocol updates, sentiment-only news, single whale transactions.
- 2-3: minor — UI changes, conference talks, marketing announcements, opinion pieces.
- 1: noise — duplicate / clickbait / non-financial.

If the article reports a *forecast* or *analyst opinion* without new information, cap impact_score at 4.0. If the article reports a confirmed fact about a SEC enforcement action, central-bank decision, or top-ten asset, never go below 6.0.

# Category definitions
- macro: monetary policy, inflation, growth, employment, central-bank communication.
- regulation: SEC / CFTC / FCA / ESMA / FSA enforcement, rule-making, legislation.
- technology: protocol upgrades, scaling, mainnet launches, security upgrades, hard forks.
- defi: DEX, lending, staking, yield, AMM, governance — both positive (TVL growth) and negative (exploits).
- institutional: ETF, custody, treasury allocations, asset-manager filings, traditional-finance entry.
- exchange: CEX listings, delistings, outages, hacks, token launches, fee changes.
- security: protocol exploits, bridge hacks, oracle manipulation, smart-contract vulnerabilities — anything with on-chain loss-of-funds.
- geopolitics: conflict, sanctions, elections, capital controls — anything that changes risk-on / risk-off appetite at the country level.
- monetary_policy: subset of macro specifically about interest-rate and balance-sheet decisions.
- earnings: corporate earnings reports for crypto-relevant or major equity issuers (Tesla, Microstrategy, Coinbase, Block, …).

A single article can carry multiple categories (e.g., a regulatory ETF approval is both "regulation" and "institutional"). Always include the most specific category first.

# Symbol extraction
Only emit ticker symbols from the supplied affected_symbols list. Do not invent symbols. Synonym mapping you should apply:

- "Bitcoin" / "Bitcoin Cash" / "Satoshi" → BTC (BCH only if explicitly Bitcoin Cash)
- "Ethereum" / "ETH" / "ether" → ETH
- "Solana" / "SOL" → SOL
- "Binance Coin" / "BNB Chain" / "Binance" (when the asset, not the company) → BNB
- "Avalanche" → AVAX
- "Polygon" / "Matic" → MATIC
- "Chainlink" → LINK
- "Uniswap" → UNI
- "Aave" → AAVE
- "Cardano" → ADA
- "Polkadot" → DOT
- "XRP" / "Ripple" (the asset) → XRP
- "S&P 500" / "SPX" → SPY
- "Nasdaq 100" / "NDX" → QQQ
- "Gold" → GLD

If the article is about Coinbase the company (COIN equity), still include BTC and ETH because that is what the trading bot trades. Do not include COIN itself.

# Pitfalls to avoid
- Never wrap output in code fences. Never prefix with "Here is the JSON". Just the JSON.
- Do not include "OTHER" or unmapped categories.
- Do not output null; use [] for empty lists, "NEUTRAL" for unclear direction, 5.0 for unclear impact.
- Headlines that mention a price change but not a cause ("BTC up 3%") get NEUTRAL direction and impact_score ≤ 4.0 — price moves are downstream of news, not news themselves.
- Headlines about future events ("Fed meets next week") classify the *event*, not the announcement: direction NEUTRAL, impact_score 3-5 depending on event importance.
- Headlines that conflate multiple stories must focus on the highest-impact one; use the summary field to acknowledge the others.
"""


class NewsAnalyst(BaseAgent):
    """Agent 06 — Processes news from RSS + APIs, classifies with Claude Sonnet."""

    AGENT_ID = 6

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="news_analyst")
        self._claude: Optional[AsyncAnthropic] = None
        self._nlp: Optional[object] = None
        self._seen_urls: set[str] = set()   # In-memory dedup within session
        self._http: Optional[httpx.AsyncClient] = None

    async def initialize(self) -> None:
        if settings.anthropic_api_key:
            self._claude = AsyncAnthropic(api_key=settings.anthropic_api_key)
            self.logger.info("Claude Sonnet connected for news NLP")
        else:
            self.logger.warning("ANTHROPIC_API_KEY not set — news NLP disabled")

        # Load spaCy for entity recognition (small English model)
        try:
            self._nlp = spacy.load("en_core_web_sm")
            self.logger.info("spaCy NLP model loaded")
        except Exception as e:
            self.logger.warning("spaCy model not available", error=str(e))

        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": "ALGHREST-NewsBot/1.0"},
            follow_redirects=True,
        )
        self.logger.info("news analyst initialized", feeds=len(RSS_FEEDS))

    async def run(self) -> None:
        """Poll all RSS feeds every 5 minutes."""
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue

            try:
                articles = await self._fetch_all_feeds()
                self.logger.debug("articles fetched", count=len(articles))

                # Process in batches of 5 to respect API rate limits
                for i in range(0, len(articles), 5):
                    batch = articles[i:i + 5]
                    await asyncio.gather(*[self._process_article(a) for a in batch])
                    await asyncio.sleep(2)  # Rate limit Claude API

            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error("news polling error", error=str(e))

            await asyncio.sleep(300)  # 5-minute poll interval

    async def _fetch_all_feeds(self) -> list[dict]:
        """Fetch and deduplicate articles from all RSS feeds."""
        articles = []
        for feed_name, feed_url in RSS_FEEDS.items():
            try:
                feed_articles = await asyncio.get_event_loop().run_in_executor(
                    None, lambda url=feed_url: feedparser.parse(url).entries
                )
                for entry in feed_articles[:20]:   # Max 20 per feed
                    url = getattr(entry, "link", "")
                    url_hash = hashlib.md5(url.encode()).hexdigest()

                    # Redis dedup: skip if seen in last 24 hours
                    if url_hash in self._seen_urls:
                        continue
                    if await self.state.is_already_processed(f"news:{url_hash}", ttl_seconds=86400):
                        self._seen_urls.add(url_hash)
                        continue

                    self._seen_urls.add(url_hash)
                    published = getattr(entry, "published_parsed", None)
                    published_dt = datetime(*published[:6]) if published else datetime.utcnow()

                    # Skip articles older than 6 hours
                    if (datetime.utcnow() - published_dt).total_seconds() > 21600:
                        continue

                    articles.append({
                        "url": url,
                        "url_hash": url_hash,
                        "headline": getattr(entry, "title", ""),
                        "summary": getattr(entry, "summary", "")[:1000],
                        "published_at": published_dt,
                        "source": feed_name,
                    })
            except Exception as e:
                self.logger.warning("feed fetch failed", feed=feed_name, error=str(e))

        return articles

    async def _process_article(self, article: dict) -> None:
        """Classify article with Claude, extract entities, publish to Kafka."""
        headline = article["headline"]
        if not headline:
            return

        # Quick relevance filter: skip if no crypto/macro keywords
        text_lower = (headline + " " + article.get("summary", "")).lower()
        if not any(kw in text_lower for kw in CRYPTO_ENTITIES):
            return

        try:
            classification = await self._classify_with_claude(
                headline, article.get("summary", "")
            )
            entities = self._extract_entities(headline, article.get("summary", ""))

            news_item = NewsItem(
                headline=headline,
                summary=classification.get("summary"),
                source=article["source"],
                url=article.get("url"),
                published_at=article["published_at"],
                direction=SignalDirection(classification.get("direction", "NEUTRAL")),
                impact_score=float(classification.get("impact_score", 5.0)),
                categories=classification.get("categories", []),
                entities=entities,
                affected_symbols=classification.get("affected_symbols", []),
            )

            # Publish as NewsSignal
            signal = NewsSignal(
                source_agent_id=self.agent_id,
                symbol=news_item.affected_symbols[0] if news_item.affected_symbols else None,
                direction=news_item.direction,
                confidence=news_item.impact_score / 10.0,
                headline=headline,
                summary=news_item.summary,
                source=news_item.source,
                url=news_item.url,
                impact_score=news_item.impact_score,
                categories=news_item.categories,
                entities=entities,
                affected_symbols=news_item.affected_symbols,
                published_at=news_item.published_at,
            )

            await self.publish(
                KafkaTopic.NEWS_TAGGED,
                payload=signal.model_dump(mode="json"),
                message_type="news_signal",
            )

            self.logger.info(
                "article published",
                headline=headline[:80],
                direction=signal.direction.value,
                impact=signal.impact_score,
                symbols=signal.affected_symbols,
            )

        except Exception as e:
            self.record_processing_error("news.tagged", type(e).__name__)
            self.logger.warning("article processing failed", headline=headline[:60], error=str(e))

    async def _classify_with_claude(self, headline: str, summary: str) -> dict:
        """Use Claude Sonnet to classify news article direction and impact.

        The classification rubric (~1500 tokens) lives in the cached system
        prompt; the user message carries only the headline + summary, so a
        burst of 5 articles writes the cache once and reads it 4 times.
        """
        if not self._claude:
            return {"direction": "NEUTRAL", "impact_score": 5.0, "categories": [], "affected_symbols": []}

        import json

        user_message = (
            f"Headline: {headline}\n"
            f"Summary: {summary[:500] if summary else '(no summary available)'}\n\n"
            f"Return one JSON object as specified."
        )

        try:
            response = await self._claude.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=256,
                system=[
                    {
                        "type": "text",
                        "text": _NEWS_CLASSIFIER_SYSTEM,
                        # 5-min ephemeral is sufficient: bursts are clustered
                        # within seconds of each other.
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )
            self._record_cache_metrics(response)
            claude_calls.labels(
                model=_CLAUDE_MODEL, agent_id=str(self.AGENT_ID), outcome="success"
            ).inc()
        except Exception:
            claude_calls.labels(
                model=_CLAUDE_MODEL, agent_id=str(self.AGENT_ID), outcome="error"
            ).inc()
            raise

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        return json.loads(raw)

    def _record_cache_metrics(self, response: Any) -> None:
        """Token usage broken down by cache_create / cache_read / regular."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        cache_created = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        regular = int(getattr(usage, "input_tokens", 0) or 0) - cache_created
        regular = max(0, regular)
        output = int(getattr(usage, "output_tokens", 0) or 0)

        agent_label = str(self.AGENT_ID)
        if cache_created:
            claude_input_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label, kind="cache_create"
            ).inc(cache_created)
        if cache_read:
            claude_input_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label, kind="cache_read"
            ).inc(cache_read)
        if regular:
            claude_input_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label, kind="regular"
            ).inc(regular)
        if output:
            claude_output_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label
            ).inc(output)

    def _extract_entities(self, headline: str, summary: str) -> list[str]:
        """Extract named entities using spaCy NER."""
        if not self._nlp:
            return []
        doc = self._nlp(f"{headline}. {summary}"[:500])
        entities = [
            ent.text for ent in doc.ents
            if ent.label_ in ("ORG", "PERSON", "GPE", "PRODUCT", "MONEY")
        ]
        return list(set(entities))[:20]

    async def shutdown(self) -> None:
        if self._http:
            await self._http.aclose()
        self.logger.info("news analyst shutdown")
