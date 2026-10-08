"""Typed prompt-cache extension for the pinned Anthropic SDK request schema."""

from typing import Literal, NotRequired, TypedDict

from anthropic.types import TextBlockParam


class CacheControl(TypedDict):
    type: Literal["ephemeral"]
    ttl: NotRequired[Literal["1h", "5m"]]


class CachedTextBlock(TextBlockParam):
    cache_control: CacheControl


def cached_system(text: str, ttl: Literal["1h", "5m"] | None = None) -> CachedTextBlock:
    control: CacheControl = {"type": "ephemeral"}
    if ttl is not None:
        control["ttl"] = ttl
    return {"type": "text", "text": text, "cache_control": control}
