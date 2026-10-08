"""Intelligence agent decisions, provider failures, and message contracts."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from agents.tier2_intelligence import (
    geopolitical_watcher as geo,
    macro_economist as macro,
    news_analyst as news,
    sentiment_analyst as sentiment,
)
from agents.tier2_intelligence.market_data_hub import MarketDataHub
from core.config import settings
from core.data.models import MarketRegime

pytestmark = pytest.mark.unit


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://provider.test"))


@pytest.mark.parametrize(
    "values,regime",
    [
        ({}, "NEUTRAL"),
        ({"VIX": {"value": 50}}, "CRISIS"),
        ({"VIX": {"value": 35}}, "RISK_OFF"),
        ({"VIX": {"value": 15}, "YieldSpread10Y2Y": {"value": 1}}, "RISK_ON"),
        (
            {
                "YieldSpread10Y2Y": {"value": -1},
                "FedFundsRate": {"change": 0.5},
                "CPI_YoY": {"value": 6},
                "UnemploymentRate": {"change": 0.5},
            },
            "RISK_OFF",
        ),
        (
            {"VIX": {"value": 15}, "FedFundsRate": {"change": -0.5}, "CPI_YoY": {"value": 2}},
            "RISK_ON",
        ),
    ],
)
async def test_macro_regimes_publish_and_cache_consistent_direction(values, regime):
    agent = macro.MacroEconomist()
    agent._macro_data = values
    agent.state = AsyncMock()
    agent.publish = AsyncMock()
    result = agent._classify_regime()
    assert result == MarketRegime(regime)
    await agent._publish_regime_signal(result)
    payload = agent.publish.await_args.kwargs["payload"]
    assert payload["regime"] == regime
    cached = agent.state.cache_signal.await_args.kwargs["data"]
    assert cached == {"regime": regime, "direction": payload["direction"]}
    await agent.shutdown()


@pytest.mark.parametrize(
    "observations,expected",
    [
        ([], None),
        (
            [{"value": "2", "date": "2026-01-01"}],
            {"value": 2.0, "previous": None, "date": "2026-01-01", "change": None},
        ),
        (
            [{"value": "2", "date": "2026-01-01"}, {"value": "0"}],
            {"value": 2.0, "previous": 0.0, "date": "2026-01-01", "change": 2.0},
        ),
        (
            [{"value": ".", "date": "2026-01-01"}, {"value": "1"}],
            {"value": None, "previous": 1.0, "date": "2026-01-01", "change": None},
        ),
        ([{"value": "invalid", "date": "2026-01-01"}], None),
    ],
)
async def test_fred_parses_missing_and_zero_observations(monkeypatch, observations, expected):
    agent = macro.MacroEconomist()
    assert await agent._fetch_fred_series("VIXCLS") is None
    monkeypatch.setattr(settings, "fred_api_key", "test-only")
    agent._fred_client = AsyncMock()
    agent._fred_client.get.return_value = response({"observations": observations})
    assert await agent._fetch_fred_series("VIXCLS") == expected
    await agent.shutdown()


async def test_macro_refresh_retains_good_series_when_another_fails(monkeypatch):
    agent = macro.MacroEconomist()
    monkeypatch.setattr(
        macro,
        "FRED_SERIES",
        {"VIX": ("VIX", "VIX", "HIGH"), "BAD": ("bad", "", ""), "EMPTY": ("empty", "", "")},
    )
    agent._fetch_fred_series = AsyncMock(side_effect=[{"value": 10}, RuntimeError("offline"), None])
    await agent._refresh_all_indicators()
    assert agent._macro_data == {"VIX": {"value": 10}}


@pytest.mark.parametrize(
    "score,direction",
    [
        (0.4, "STRONG_BULLISH"),
        (0.1, "BULLISH"),
        (-0.4, "STRONG_BEARISH"),
        (-0.1, "BEARISH"),
        (0, "NEUTRAL"),
    ],
)
def test_sentiment_direction_thresholds(score, direction):
    assert sentiment.SentimentAnalyst._score_to_direction(score).value == direction


async def test_sentiment_aggregation_filters_stale_mentions_and_clamps_engagement():
    agent = sentiment.SentimentAnalyst()
    agent.publish = AsyncMock()
    agent._vader = MagicMock()
    agent._vader.polarity_scores.return_value = {"compound": 0.8}
    for _ in range(3):
        await agent._process_text("bitcoin great news", "twitter", {"engagement": 1000})
    agent._sentiment_windows["ETH"].extend([(datetime.utcnow() - timedelta(hours=2), -1)] * 5)
    await agent._publish_all_sentiments()
    payload = agent.publish.await_args.kwargs["payload"]
    assert payload["symbol"] == "BTC" and payload["sentiment_score"] == 1
    assert payload["volume_mentions"] == 3 and agent._mention_counts["BTC"] == 0
    assert agent.publish.await_count == 1
    await agent._poll_reddit()  # unavailable integration is a no-op
    await agent.shutdown()


async def test_twitter_engagement_and_rate_limit(monkeypatch):
    agent = sentiment.SentimentAnalyst()
    agent._process_text = AsyncMock()
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = response(
        {
            "data": [
                {
                    "id": "1",
                    "text": "bitcoin",
                    "public_metrics": {"like_count": 2, "retweet_count": 3, "reply_count": 4},
                }
            ]
        }
    )
    monkeypatch.setattr(httpx, "AsyncClient", MagicMock(return_value=client))
    await agent._poll_twitter_recent("bitcoin")
    assert agent._process_text.await_args.kwargs["metadata"]["engagement"] == 15
    client.get.return_value = response({}, 429)
    sleep = AsyncMock()
    monkeypatch.setattr(sentiment.asyncio, "sleep", sleep)
    await agent._poll_twitter_recent("bitcoin")
    sleep.assert_awaited_once_with(900)
    assert agent._process_text.await_count == 1


@pytest.mark.parametrize(
    "text,region",
    [
        ("washington", "us"),
        ("european", "eu"),
        ("beijing", "china"),
        ("moscow", "russia"),
        ("iran", "middle_east"),
        ("moon", "global"),
    ],
)
def test_geo_region_lookup(text, region):
    assert geo.GeopoliticalWatcher._infer_region(text) == region


@pytest.mark.parametrize(
    "headline,event",
    [
        ("bitcoin war attack invasion nuclear emergency", "conflict"),
        ("bitcoin sanctions embargo crackdown", "sanctions"),
        ("bitcoin election president crypto ban", "sanctions"),
        ("bitcoin sec regulation crackdown", "regulation"),
    ],
)
def test_geopolitical_risk_classification(headline, event):
    agent = geo.GeopoliticalWatcher()
    signal = agent._classify_article(headline, "", datetime.utcnow(), "test")
    assert signal is not None
    assert signal.event_type == event and signal.direction.value == "BEARISH"
    assert signal.metadata["headline"] == headline
    assert agent._classify_article("sports result", "", datetime.utcnow(), "test") is None


async def test_geo_rss_filters_stale_irrelevant_and_duplicate_articles(monkeypatch):
    agent = geo.GeopoliticalWatcher()
    agent.publish = AsyncMock()
    monkeypatch.setattr(geo, "GEOPOLITICAL_RSS_FEEDS", {"source": "test"})
    headline = "bitcoin war attack invasion nuclear emergency"
    entries = [
        SimpleNamespace(id="one", title=headline, summary=""),
        SimpleNamespace(id="one", title=headline, summary=""),
        SimpleNamespace(id="sports", title="sports", summary=""),
        SimpleNamespace(
            id="old", title=headline, summary="", published_parsed=(2000, 1, 1, 0, 0, 0)
        ),
    ]
    monkeypatch.setattr(geo.feedparser, "parse", lambda _: SimpleNamespace(entries=entries))
    await agent._process_all_rss()
    assert agent.publish.await_count == 1
    await agent._fetch_gdelt_events()
    agent._gdelt_client = AsyncMock()
    agent._gdelt_client.get.return_value = response({"articles": []})
    await agent._fetch_gdelt_events()
    agent._gdelt_client.get.side_effect = httpx.ConnectError("offline")
    await agent._fetch_gdelt_events()
    await agent.shutdown()
    agent._gdelt_client.aclose.assert_awaited_once()


async def test_news_feed_dedup_expiry_and_failure_tracking(monkeypatch):
    agent = news.NewsAnalyst()
    agent.state = AsyncMock()
    agent.state.is_already_processed.return_value = False
    monkeypatch.setattr(news, "RSS_FEEDS", {"test": "local", "empty": "empty"})
    entries = [
        SimpleNamespace(link="one", title="bitcoin", summary="ok"),
        SimpleNamespace(link="one", title="duplicate"),
        SimpleNamespace(link=""),
        SimpleNamespace(link="old", title="bitcoin", published_parsed=(2000, 1, 1, 0, 0, 0)),
    ]
    monkeypatch.setattr(
        news.feedparser,
        "parse",
        lambda url: SimpleNamespace(entries=entries if url == "local" else []),
    )
    articles = await agent._fetch_all_feeds()
    assert [a["url"] for a in articles] == ["one"]
    assert agent._feed_failures["empty"] == 1
    assert await agent._fetch_all_feeds() == []
    assert agent._feed_failures["test"] == 0


async def test_news_relevance_validation_and_entity_extraction():
    agent = news.NewsAnalyst()
    agent.publish = AsyncMock()
    agent._classify_with_claude = AsyncMock(
        return_value={
            "direction": "BULLISH",
            "impact_score": 8,
            "affected_symbols": ["BTC"],
            "summary": "test",
        }
    )
    article = dict(
        headline="bitcoin rally", source="test", published_at=datetime.utcnow(), url="https://test"
    )
    await agent._process_article({**article, "headline": ""})
    await agent._process_article({**article, "headline": "football"})
    agent._classify_with_claude.assert_not_awaited()
    await agent._process_article(article)
    payload = agent.publish.await_args.kwargs["payload"]
    assert payload["confidence"] == 0.8 and payload["symbol"] == "BTC"
    agent._classify_with_claude.return_value = {"direction": "INVALID"}
    await agent._process_article(article)
    assert agent._messages_failed == 1
    assert agent._extract_entities("bitcoin", "") == []
    agent._nlp = MagicMock(
        return_value=SimpleNamespace(
            ents=[
                SimpleNamespace(text="Bitcoin", label_="ORG"),
                SimpleNamespace(text="today", label_="DATE"),
            ]
        )
    )
    assert agent._extract_entities("Bitcoin today", "") == ["Bitcoin"]


@pytest.mark.parametrize(
    "candle,expected",
    [
        ([0, 100, 110, 90, 105, 10], True),
        ([0, None, 110, 90, 105, 10], False),
        ([0, 100, 80, 90, 105, 10], False),
        ([], False),
    ],
)
def test_market_data_normalization_rejects_bad_candles(candle, expected):
    result = MarketDataHub._normalize_ohlcv(candle, "binance", "BTC/USDT", "1h")
    assert (result is not None) is expected
    if result:
        assert result.close == 105 and result.timeframe.value == "1h"


def test_orderbook_normalization_caps_depth_and_rejects_malformed():
    book = MarketDataHub._normalize_order_book(
        {"bids": [[99, 1]] * 30, "asks": [[101, 2]] * 30}, "binance", "BTC/USDT"
    )
    assert len(book.bids) == len(book.asks) == 20 and book.mid_price == 100
    assert MarketDataHub._normalize_order_book({}, "binance", "BTC/USDT") is None
