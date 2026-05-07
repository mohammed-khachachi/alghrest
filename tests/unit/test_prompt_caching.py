"""Unit tests for Claude prompt-caching wiring (I9).

We do NOT call the Anthropic API here; we mock the AsyncAnthropic client and
inspect the request the agent built. The contract under test is:

  1. The system parameter is a list of content blocks, not a plain string.
  2. The system block carries `cache_control` with `type=ephemeral`.
  3. The user message carries the dynamic data (NOT the methodology).
  4. Token-usage metrics break down by cache_create / cache_read / regular.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers — fake an Anthropic Messages API response with usage metadata.
# ---------------------------------------------------------------------------


def _fake_response(text: str, *, cache_created: int = 0, cache_read: int = 0,
                   input_tokens: int = 100, output_tokens: int = 50):
    """Build a SimpleNamespace that quacks like an anthropic Message."""
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(
            cache_creation_input_tokens=cache_created,
            cache_read_input_tokens=cache_read,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        ),
    )


# ---------------------------------------------------------------------------
# CIO agent
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cio_passes_cache_control_in_system_prompt():
    """The CIO must use a list-form system prompt with cache_control."""
    from agents.tier1_executive.cio_agent import CIOAgent, _CIO_SYSTEM_PROMPT

    cio = CIOAgent()
    cio._claude = MagicMock()
    cio._claude.messages = MagicMock()
    cio._claude.messages.create = AsyncMock(return_value=_fake_response(
        '{"trend_follower_donchian": 0.10}',
        cache_created=2500, cache_read=0, input_tokens=2700, output_tokens=20,
    ))

    weights = await cio._ask_claude("dynamic context goes here")
    assert weights == {"trend_follower_donchian": 0.1}

    # Inspect the request that the SDK *would* have sent.
    call_kwargs = cio._claude.messages.create.await_args.kwargs
    system = call_kwargs["system"]
    assert isinstance(system, list), "system must be a list of blocks for caching"
    assert len(system) == 1
    block = system[0]
    assert block["type"] == "text"
    assert block["text"] == _CIO_SYSTEM_PROMPT
    assert block["cache_control"]["type"] == "ephemeral"
    # 1-hour TTL is the design choice for the 5-min CIO cycle.
    assert block["cache_control"].get("ttl") == "1h"

    # The user message must NOT contain the long methodology text.
    user_msg = call_kwargs["messages"][0]["content"]
    assert "Strategy taxonomy" not in user_msg
    assert "Risk limits" not in user_msg
    assert "dynamic context" in user_msg


@pytest.mark.unit
def test_cio_system_prompt_meets_caching_minimum_for_opus():
    """Opus prompt cache requires 2048 tokens minimum; English is ~4 chars
    per token, so we want > 8200 chars to be safely above the threshold."""
    from agents.tier1_executive.cio_agent import _CIO_SYSTEM_PROMPT
    assert len(_CIO_SYSTEM_PROMPT) > 8500, (
        f"CIO system prompt is only {len(_CIO_SYSTEM_PROMPT)} chars — "
        "must exceed ~8500 to comfortably meet Opus 2048-token cache minimum"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cio_records_cache_read_when_response_has_cache_hit():
    """On cache HIT, the cache_read metric increments."""
    from agents.tier1_executive.cio_agent import CIOAgent
    from core.utils.metrics import claude_input_tokens

    cio = CIOAgent()
    cio._claude = MagicMock()
    cio._claude.messages = MagicMock()
    cio._claude.messages.create = AsyncMock(return_value=_fake_response(
        '{"trend_follower_donchian": 0.10}',
        cache_created=0, cache_read=2500, input_tokens=200, output_tokens=20,
    ))

    before = claude_input_tokens.labels(
        model="claude-opus-4-7", agent_id="1", kind="cache_read"
    )._value.get()

    await cio._ask_claude("dynamic context")

    after = claude_input_tokens.labels(
        model="claude-opus-4-7", agent_id="1", kind="cache_read"
    )._value.get()

    assert after - before == 2500


# ---------------------------------------------------------------------------
# News analyst
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_analyst_passes_cache_control_in_system_prompt():
    from agents.tier2_intelligence.news_analyst import (
        NewsAnalyst, _NEWS_CLASSIFIER_SYSTEM,
    )

    analyst = NewsAnalyst()
    analyst._claude = MagicMock()
    analyst._claude.messages = MagicMock()
    analyst._claude.messages.create = AsyncMock(return_value=_fake_response(
        '{"direction": "BULLISH", "impact_score": 7.0, '
        '"categories": ["regulation"], "affected_symbols": ["BTC"], '
        '"summary": "ETF approved."}',
        cache_created=1500, cache_read=0, input_tokens=1600, output_tokens=40,
    ))

    result = await analyst._classify_with_claude(
        headline="SEC approves spot Bitcoin ETF",
        summary="The SEC has approved the first US-listed spot BTC ETFs.",
    )
    assert result["direction"] == "BULLISH"
    assert "BTC" in result["affected_symbols"]

    call_kwargs = analyst._claude.messages.create.await_args.kwargs
    system = call_kwargs["system"]
    assert isinstance(system, list)
    block = system[0]
    assert block["text"] == _NEWS_CLASSIFIER_SYSTEM
    assert block["cache_control"]["type"] == "ephemeral"
    # No TTL override → defaults to 5-minute ephemeral, which is what we want
    # for clustered article bursts.
    assert "ttl" not in block["cache_control"]

    user_msg = call_kwargs["messages"][0]["content"]
    assert "SEC approves spot Bitcoin ETF" in user_msg
    # The taxonomy / rubric must NOT leak into the user message.
    assert "Direction taxonomy" not in user_msg
    assert "Impact-score rubric" not in user_msg


@pytest.mark.unit
def test_news_classifier_system_meets_caching_minimum_for_sonnet():
    """Sonnet minimum is ~1024 tokens; we want ~4000+ chars to be safe."""
    from agents.tier2_intelligence.news_analyst import _NEWS_CLASSIFIER_SYSTEM
    assert len(_NEWS_CLASSIFIER_SYSTEM) > 4000, (
        f"News classifier system prompt is only {len(_NEWS_CLASSIFIER_SYSTEM)} "
        "chars — may not meet Sonnet 1024-token minimum for prompt caching"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_records_cache_create_then_read():
    """First call writes cache; second reads it. Both metrics must increment."""
    from agents.tier2_intelligence.news_analyst import NewsAnalyst
    from core.utils.metrics import claude_input_tokens

    analyst = NewsAnalyst()
    analyst._claude = MagicMock()
    analyst._claude.messages = MagicMock()

    # First call: cache miss (write)
    analyst._claude.messages.create = AsyncMock(return_value=_fake_response(
        '{"direction": "NEUTRAL", "impact_score": 5.0, "categories": [], '
        '"affected_symbols": [], "summary": "Test."}',
        cache_created=1500, cache_read=0, input_tokens=1600, output_tokens=40,
    ))

    create_before = claude_input_tokens.labels(
        model="claude-sonnet-4-6", agent_id="6", kind="cache_create"
    )._value.get()
    read_before = claude_input_tokens.labels(
        model="claude-sonnet-4-6", agent_id="6", kind="cache_read"
    )._value.get()

    await analyst._classify_with_claude("Test headline", "Test summary")

    # Second call: cache hit (read)
    analyst._claude.messages.create = AsyncMock(return_value=_fake_response(
        '{"direction": "NEUTRAL", "impact_score": 5.0, "categories": [], '
        '"affected_symbols": [], "summary": "Test 2."}',
        cache_created=0, cache_read=1500, input_tokens=100, output_tokens=40,
    ))
    await analyst._classify_with_claude("Test headline 2", "Test summary 2")

    create_after = claude_input_tokens.labels(
        model="claude-sonnet-4-6", agent_id="6", kind="cache_create"
    )._value.get()
    read_after = claude_input_tokens.labels(
        model="claude-sonnet-4-6", agent_id="6", kind="cache_read"
    )._value.get()

    assert create_after - create_before == 1500
    assert read_after - read_before == 1500
