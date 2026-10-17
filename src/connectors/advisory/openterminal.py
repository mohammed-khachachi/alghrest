"""Bounded read-only public context from the fixed local OpenTerminal API."""

import asyncio
import hashlib
import ipaddress
import json
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import quote as encode_symbol, urlsplit

import httpx

from core.advisory.models import utcnow
from core.advisory.openterminal_context import (
    PROXIES,
    OpenTerminalContext,
    PublicHeadline,
    PublicQuote,
    TerminalInstrument,
    TerminalSource,
    build_terminal_context,
)

BASE_URL = "http://127.0.0.1:4001"
MAX_BODY_BYTES = 256_000
PROVIDERS = frozenset({"nasdaq", "yahoo", "stooq", "tradingview"})


def _number(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float | Decimal | str):
        raise ValueError("Invalid number")
    result = Decimal(str(value))
    if not result.is_finite() or abs(result) > Decimal("1e30"):
        raise ValueError("Invalid number")
    return result


def _stamp(value: Any, now: datetime) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, str):
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        number = _number(value)
        if number is None:
            return None
        stamp = datetime.fromtimestamp(float(number), UTC)
    if stamp.tzinfo is None or stamp.utcoffset() is None or stamp > now:
        raise ValueError("Invalid source clock")
    return stamp.astimezone(UTC)


def _text(value: Any, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValueError("Invalid text")
    result = re.sub(r"<[^>]*>", "", value).strip()
    if not result or len(result) > maximum:
        raise ValueError("Invalid text")
    return result


def parse_quote(value: Any, symbol: str, now: datetime) -> PublicQuote:
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        raise ValueError("Unexpected single-symbol quote response")
    row = value[0]
    if row.get("symbol") != symbol or row.get("currency") != "USD":
        raise ValueError("Proxy identity or currency mismatch")
    if row.get("source") not in PROVIDERS:
        raise ValueError("Unknown public provider")
    return PublicQuote.model_validate(
        {
            "symbol": symbol,
            "name": _text(row["name"], 200) if row.get("name") is not None else None,
            "price": _number(row.get("price")),
            "change_percent": _number(row.get("changePercent")),
            "provider": row["source"],
            "currency": "USD",
            "market_time": _stamp(row.get("time"), now),
        }
    )


def parse_headlines(value: Any, symbol: str, now: datetime) -> tuple[PublicHeadline, ...]:
    if not isinstance(value, list) or len(value) > 500:
        raise ValueError("Unexpected news response")
    items: dict[str, PublicHeadline] = {}
    for row in value:
        if not isinstance(row, dict) or row.get("symbol") not in {None, symbol}:
            continue
        try:
            url = _text(row.get("link"), 2000)
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.hostname.lower() in {"localhost", "testserver"}
                or parsed.hostname.lower().endswith((".local", ".localhost"))
            ):
                continue
            try:
                ipaddress.ip_address(parsed.hostname)
            except ValueError:
                pass
            else:
                continue
            stamp = _stamp(row.get("publishedAt"), now)
            if stamp is not None and now - stamp > timedelta(days=7):
                continue
            item = PublicHeadline.model_validate(
                {
                    "title": _text(row.get("title"), 400),
                    "url": url,
                    "publisher": _text(row.get("publisher"), 150),
                    "published_at": stamp,
                }
            )
            items.setdefault(str(item.url), item)
        except (ValueError, TypeError, OverflowError, ArithmeticError):
            continue
    return tuple(list(items.values())[:8])


async def _read(
    client: httpx.AsyncClient,
    kind: Literal["quotes", "news", "history"],
    symbol: str,
    *,
    quote_metadata: bool = False,
) -> tuple[Any, TerminalSource]:
    digest = None
    state: Literal["unavailable", "invalid"]
    try:
        async with client.stream(
            "GET",
            (
                f"{BASE_URL}/api/history/{encode_symbol(symbol, safe='')}"
                if kind == "history"
                else f"{BASE_URL}/api/{kind}"
            ),
            params=(
                {"range": "6M", "metadata": "1"}
                if kind == "history"
                else (
                    {"symbols": symbol, **({"metadata": "1"} if quote_metadata else {})}
                    if kind == "quotes"
                    else {"symbol": symbol}
                )
            ),
            follow_redirects=False,
        ) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_BODY_BYTES:
                    raise ValueError("Oversized public response")
        digest = hashlib.sha256(body).hexdigest()
        value = json.loads(body, parse_float=Decimal, parse_int=Decimal)
        return value, TerminalSource(
            kind=kind, state="available", received_at=utcnow(), response_sha256=digest
        )
    except (httpx.HTTPError, TimeoutError):
        reason, state = "terminal_unavailable", "unavailable"
    except (ValueError, TypeError, ArithmeticError):
        reason, state = "invalid_public_response", "invalid"
    return None, TerminalSource(
        kind=kind,
        state=state,
        received_at=utcnow(),
        response_sha256=digest,
        reasons=(reason,),
    )


async def collect_terminal_context(
    client: httpx.AsyncClient, instrument: TerminalInstrument
) -> OpenTerminalContext:
    symbol = PROXIES[instrument]
    try:
        async with asyncio.timeout(12):
            (quote_data, quote_source), (news_data, news_source) = await asyncio.gather(
                _read(client, "quotes", symbol), _read(client, "news", symbol)
            )
    except TimeoutError:
        quote_data, news_data = None, None
        quote_source = TerminalSource(
            kind="quotes", state="unavailable", received_at=utcnow(), reasons=("terminal_timeout",)
        )
        news_source = TerminalSource(
            kind="news", state="unavailable", received_at=utcnow(), reasons=("terminal_timeout",)
        )
    now = utcnow()
    quote = None
    headlines: tuple[PublicHeadline, ...] = ()
    for kind, value, source in (
        ("quotes", quote_data, quote_source),
        ("news", news_data, news_source),
    ):
        if source.state != "available":
            continue
        try:
            if kind == "quotes":
                quote = parse_quote(value, symbol, now)
            else:
                headlines = parse_headlines(value, symbol, now)
        except (ValueError, TypeError, OverflowError, ArithmeticError):
            invalid = TerminalSource(
                kind=source.kind,
                state="invalid",
                received_at=source.received_at,
                response_sha256=source.response_sha256,
                reasons=("invalid_public_response",),
            )
            if kind == "quotes":
                quote_source = invalid
            else:
                news_source = invalid
    return build_terminal_context(
        instrument, quote, headlines, (quote_source, news_source), now=now
    )
