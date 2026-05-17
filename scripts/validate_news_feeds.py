#!/usr/bin/env python3
"""
ALGHREST — News Feed Validation Script
Tests all RSS feeds defined in News Analyst to identify working vs broken feeds.
"""

import asyncio
import time
from datetime import datetime
from typing import Dict, List, Tuple

import feedparser
import httpx


# Copy RSS_FEEDS from news_analyst.py
RSS_FEEDS = {
    # Crypto-native sources (reliable)
    "coindesk":           "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph":      "https://cointelegraph.com/rss",
    "decrypt":            "https://decrypt.co/feed",
    "theblock":           "https://www.theblock.co/rss.xml",
    "blockworks":         "https://blockworks.co/feed",

    # Traditional finance with crypto coverage
    "yahoo_crypto":       "https://finance.yahoo.com/rss/topstories",
    "marketwatch":        "https://feeds.marketwatch.com/marketwatch/topstories/",
    "cnbc_crypto":        "https://www.cnbc.com/id/100727362/device/rss/rss.html",

    # Central bank and regulation
    "fed_news":           "https://www.federalreserve.gov/feeds/press_all.xml",

    # Alternative to Reuters (working business news)
    "ap_business":        "https://feeds.apnews.com/rss/apf-businessnews.xml",
    "bbc_business":       "http://feeds.bbci.co.uk/news/business/rss.xml",
}


async def test_feed(feed_name: str, feed_url: str) -> Dict:
    """Test a single RSS feed and return results."""
    result = {
        "feed_name": feed_name,
        "url": feed_url,
        "status": "UNKNOWN",
        "response_time_ms": None,
        "article_count": 0,
        "latest_article_age_hours": None,
        "error": None,
        "has_crypto_content": False
    }

    try:
        start_time = time.time()

        # Test with HTTP client first
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(feed_url)
            response.raise_for_status()

        # Parse RSS feed
        feed_data = await asyncio.get_event_loop().run_in_executor(
            None, lambda: feedparser.parse(feed_url)
        )

        response_time = (time.time() - start_time) * 1000
        result["response_time_ms"] = int(response_time)

        # Check if parsing was successful
        if hasattr(feed_data, 'entries') and len(feed_data.entries) > 0:
            result["status"] = "WORKING"
            result["article_count"] = len(feed_data.entries[:20])  # Max 20 like in agent

            # Check latest article age
            latest_entry = feed_data.entries[0]
            if hasattr(latest_entry, 'published_parsed') and latest_entry.published_parsed:
                latest_time = datetime(*latest_entry.published_parsed[:6])
                age_hours = (datetime.utcnow() - latest_time).total_seconds() / 3600
                result["latest_article_age_hours"] = round(age_hours, 1)

            # Check for crypto-related content in first few articles
            crypto_keywords = {
                "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain",
                "solana", "binance", "coinbase", "defi", "nft", "sec crypto"
            }

            for entry in feed_data.entries[:5]:
                title = getattr(entry, 'title', '').lower()
                summary = getattr(entry, 'summary', '').lower()
                text = title + " " + summary

                if any(keyword in text for keyword in crypto_keywords):
                    result["has_crypto_content"] = True
                    break

        elif hasattr(feed_data, 'bozo') and feed_data.bozo:
            result["status"] = "PARSE_ERROR"
            result["error"] = str(getattr(feed_data, 'bozo_exception', 'Unknown parsing error'))
        else:
            result["status"] = "EMPTY_FEED"
            result["error"] = "Feed parsed successfully but contains no entries"

    except httpx.TimeoutException:
        result["status"] = "TIMEOUT"
        result["error"] = "Request timed out after 15 seconds"
    except httpx.HTTPStatusError as e:
        result["status"] = "HTTP_ERROR"
        result["error"] = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = str(e)

    return result


async def validate_all_feeds() -> List[Dict]:
    """Test all RSS feeds concurrently."""
    print("🔍 ALGHREST News Feed Validation")
    print("=" * 50)
    print(f"Testing {len(RSS_FEEDS)} RSS feeds...")
    print()

    # Test all feeds concurrently
    tasks = [test_feed(name, url) for name, url in RSS_FEEDS.items()]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Handle any exceptions in results
    validated_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            feed_name = list(RSS_FEEDS.keys())[i]
            validated_results.append({
                "feed_name": feed_name,
                "url": RSS_FEEDS[feed_name],
                "status": "EXCEPTION",
                "error": str(result),
                "response_time_ms": None,
                "article_count": 0,
                "latest_article_age_hours": None,
                "has_crypto_content": False
            })
        else:
            validated_results.append(result)

    return validated_results


def print_results(results: List[Dict]) -> None:
    """Print validation results in a formatted table."""

    # Sort by status (working first)
    status_order = {"WORKING": 0, "EMPTY_FEED": 1, "PARSE_ERROR": 2,
                   "HTTP_ERROR": 3, "TIMEOUT": 4, "ERROR": 5, "EXCEPTION": 6}
    results.sort(key=lambda x: status_order.get(x["status"], 999))

    # Calculate stats
    working = [r for r in results if r["status"] == "WORKING"]
    broken = [r for r in results if r["status"] != "WORKING"]
    crypto_feeds = [r for r in working if r["has_crypto_content"]]

    print("\n📊 VALIDATION SUMMARY")
    print("=" * 50)
    print(f"✅ Working feeds: {len(working)}/{len(results)}")
    print(f"❌ Broken feeds: {len(broken)}/{len(results)}")
    print(f"🪙 Feeds with crypto content: {len(crypto_feeds)}/{len(working)}")
    print()

    # Detailed results table
    print("📋 DETAILED RESULTS")
    print("=" * 120)
    print(f"{'Feed Name':<20} {'Status':<12} {'Articles':<8} {'Age (h)':<8} {'Time (ms)':<9} {'Crypto':<6} {'Error'}")
    print("-" * 120)

    for result in results:
        feed_name = result["feed_name"][:19]
        status = result["status"]
        articles = result["article_count"]
        age = f"{result['latest_article_age_hours']:.1f}" if result["latest_article_age_hours"] else "N/A"
        response_time = f"{result['response_time_ms']}" if result["response_time_ms"] else "N/A"
        crypto = "Yes" if result["has_crypto_content"] else "No"
        error = result["error"][:40] + "..." if result["error"] and len(result["error"]) > 40 else result.get("error", "")

        # Color coding
        if status == "WORKING":
            status_icon = "✅"
        elif status in ["TIMEOUT", "HTTP_ERROR"]:
            status_icon = "🔴"
        else:
            status_icon = "⚠️"

        print(f"{feed_name:<20} {status_icon} {status:<10} {articles:<8} {age:<8} {response_time:<9} {crypto:<6} {error}")

    # Recommendations
    print("\n💡 RECOMMENDATIONS")
    print("=" * 50)

    if len(working) >= 7:
        print("✅ Feed health is good - sufficient working sources")
    elif len(working) >= 4:
        print("⚠️ Feed health is moderate - consider adding backup sources")
    else:
        print("🔴 Feed health is poor - need to find more reliable sources")

    if len(crypto_feeds) < 3:
        print("⚠️ Limited crypto-specific content - consider adding more crypto-native feeds")

    # List problematic feeds
    if broken:
        print("\n🔧 FEEDS TO FIX OR REPLACE:")
        for result in broken:
            print(f"  - {result['feed_name']}: {result['status']} - {result.get('error', 'Unknown error')}")

    # Suggest good alternatives
    print("\n📰 SUGGESTED ADDITIONAL FEEDS:")
    suggestions = [
        "Bitcoin Magazine RSS: https://bitcoinmagazine.com/.rss/full/",
        "CryptoSlate: https://cryptoslate.com/feed/",
        "Unchained Crypto: https://unchainedcrypto.com/feed/",
        "Forbes Crypto: https://www.forbes.com/crypto-blockchain/feed/",
        "Wall Street Journal Markets: https://feeds.wsj.com/wsj/xml/rss/3_7014.xml"
    ]

    for suggestion in suggestions:
        print(f"  - {suggestion}")


async def main():
    """Main validation function."""
    try:
        results = await validate_all_feeds()
        print_results(results)

        # Return exit code based on results
        working_feeds = len([r for r in results if r["status"] == "WORKING"])
        if working_feeds >= 7:
            return 0  # Good
        elif working_feeds >= 4:
            return 1  # Warning
        else:
            return 2  # Critical

    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return 3


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)