"""Read only the selected OpenTerminal symbol, without catalog/proxy substitution."""

import asyncio
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import TypeAdapter

from connectors.advisory.openterminal import _number, _read, _stamp, _text, parse_headlines
from core.advisory.models import utcnow
from core.advisory.openterminal_context import PublicHeadline, TerminalSource
from core.advisory.openterminal_research import (
    CandleAnalysis,
    HistoryMetadata,
    QuoteObservation,
    ResearchQuote,
    TerminalCandle,
    TerminalResearch,
    TerminalSymbol,
    analyze_candles,
    valid_symbol,
)
from core.advisory.research_quality import assess_candle_quality, unavailable_quality


async def collect_terminal_research(client: httpx.AsyncClient, symbol: str) -> TerminalResearch:
    # Validate before constructing any local URL, including direct adapter callers.
    symbol = valid_symbol(TypeAdapter(TerminalSymbol).validate_python(symbol))
    try:
        async with asyncio.timeout(22):
            results = await asyncio.gather(
                _read(client, "quotes", symbol, quote_metadata=True),
                _read(client, "news", symbol),
                _read(client, "history", symbol),
            )
    except TimeoutError:
        now = utcnow()
        return TerminalResearch(
            symbol=symbol,
            assessed_at=now,
            data_quality=unavailable_quality("history_unavailable"),
            sources=(
                TerminalSource(kind="quotes", state="unavailable", received_at=now),
                TerminalSource(kind="news", state="unavailable", received_at=now),
                TerminalSource(kind="history", state="unavailable", received_at=now),
            ),
        )
    now = utcnow()
    quote = None
    analysis: CandleAnalysis | None = None
    quality = unavailable_quality("history_unavailable")
    headlines: tuple[PublicHeadline, ...] = ()
    sources = []
    for value, source in results:
        if source.kind == "history" and source.state != "available":
            quality = unavailable_quality(
                "invalid_response" if source.state == "invalid" else "history_unavailable"
            )
        if source.state == "available":
            try:
                if source.kind == "quotes":
                    if (
                        not isinstance(value, list)
                        or len(value) != 1
                        or not isinstance(value[0], dict)
                    ):
                        raise ValueError("Unexpected quote response")
                    row = value[0]
                    if row.get("symbol") != symbol:
                        raise ValueError("Selected symbol mismatch")
                    observation = (
                        QuoteObservation.model_validate(row["observation"])
                        if row.get("observation") is not None
                        else None
                    )
                    if observation and observation.fetched_at > source.received_at:
                        raise ValueError("Quote fetch clock exceeds receipt")
                    quote = ResearchQuote.model_validate(
                        {
                            "symbol": symbol,
                            "name": (
                                _text(row["name"], 200) if row.get("name") is not None else None
                            ),
                            "price": _number(row.get("price")),
                            "change_percent": _number(row.get("changePercent")),
                            "currency": row.get("currency"),
                            "provider": row.get("source"),
                            "market_time": _stamp(row.get("time"), now),
                            "market_state": row.get("marketState"),
                            "observation": observation,
                        }
                    )
                elif source.kind == "news":
                    headlines = parse_headlines(value, symbol, now)
                else:
                    quality = unavailable_quality("invalid_metadata")
                    metadata = None
                    if isinstance(value, dict):
                        if set(value) != {"metadata", "candles"}:
                            raise ValueError("Invalid history envelope")
                        metadata = HistoryMetadata.model_validate(value["metadata"])
                        if metadata.symbol != symbol or metadata.fetched_at > source.received_at:
                            raise ValueError("History metadata identity or clock mismatch")
                        value = value["candles"]
                    quality = unavailable_quality("invalid_response")
                    if not isinstance(value, list) or len(value) > 2000:
                        raise ValueError("Unexpected history response")
                    times = []
                    invalid = 0
                    for row in value:
                        try:
                            time = (
                                _stamp(row.get("time"), datetime.max.replace(tzinfo=UTC))
                                if isinstance(row, dict)
                                else None
                            )
                        except (ValueError, TypeError, OverflowError, ArithmeticError):
                            time = None
                        times.append(time)
                        try:
                            parse_candles([row], datetime.max.replace(tzinfo=UTC))
                        except (ValueError, TypeError, OverflowError, ArithmeticError):
                            invalid += 1
                    quality = assess_candle_quality(
                        tuple(times),
                        now,
                        invalid_candles=invalid,
                        provider=metadata.provider if metadata else None,
                        interval=metadata.interval if metadata else None,
                        fetched_at=metadata.fetched_at if metadata else None,
                        cache_state=metadata.cache_state if metadata else None,
                    )
                    if quality.status == "unavailable":
                        raise ValueError("History integrity failed")
                    analysis = analyze_candles(parse_candles(value, now), now, metadata, quality)
            except (ValueError, TypeError, OverflowError, ArithmeticError):
                source = TerminalSource(
                    kind=source.kind,
                    state="invalid",
                    received_at=source.received_at,
                    response_sha256=source.response_sha256,
                    reasons=("invalid_public_response",),
                )
        sources.append(source)
    return TerminalResearch(
        symbol=symbol,
        assessed_at=now,
        quote=quote,
        analysis=analysis,
        data_quality=quality,
        headlines=headlines,
        sources=tuple(sources),
    )


def parse_candles(value: Any, now: datetime) -> tuple[TerminalCandle, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= 2000:
        raise ValueError("Unexpected history response")
    candles = []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("Invalid candle row")
        candles.append(
            TerminalCandle.model_validate(
                {
                    "time": _stamp(row.get("time"), now),
                    **{
                        key: _number(row.get(key))
                        for key in ("open", "high", "low", "close", "volume")
                    },
                }
            )
        )
    return tuple(candles)
