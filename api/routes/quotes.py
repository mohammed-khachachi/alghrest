"""Market-data REST surface used by the dashboard symbol selector + market panel."""
from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from api.auth import require_api_key
from connectors.data_providers import default_router
from connectors.data_providers.base import ANCHOR_DATE
from connectors.data_providers.holdings import get_holdings
from connectors.data_providers.router import QuoteRouter, UnknownSymbolError

router = APIRouter(prefix="/api", tags=["market-data"])


def _router() -> QuoteRouter:
    return default_router


@router.get("/symbols")
async def list_symbols() -> dict[str, list[dict[str, str]]]:
    return {
        "symbols": [
            {"symbol": e.symbol, "name": e.name, "asset_class": e.asset_class.value}
            for e in _router().catalog
        ]
    }


@router.get("/quotes")
async def get_quotes(
    symbols: Annotated[str, Query(description="Comma-separated symbols, e.g. BTC,EUR/USD,AAPL")],
) -> dict:
    requested = [s.strip() for s in symbols.split(",") if s.strip()]
    quotes = await _router().quote_many(requested)
    return {
        "as_of": ANCHOR_DATE.isoformat(),
        "quotes": [
            {**asdict(q), "asset_class": q.asset_class.value}
            for q in quotes
        ],
    }


@router.get("/history")
async def get_history(
    symbol: Annotated[str, Query(description="Single symbol, e.g. BTC")],
    days: Annotated[int, Query(ge=2, le=365)] = 30,
) -> dict:
    try:
        bars = await _router().history(symbol, days)
    except UnknownSymbolError:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}")
    return {
        "symbol": symbol.upper(),
        "as_of": ANCHOR_DATE.isoformat(),
        "bars": [asdict(b) for b in bars],
    }


@router.get("/holdings", dependencies=[Depends(require_api_key)])
async def get_holdings_route() -> dict:
    """Static mock holdings. P&L is computed client-side by joining with /api/quotes."""
    holdings = await get_holdings(_router())
    return {
        "as_of": ANCHOR_DATE.isoformat(),
        "holdings": [
            {
                "symbol": h.symbol,
                "broker": h.broker,
                "asset_class": h.asset_class.value,
                "side": h.side,
                "volume": h.volume,
                "entry_price": h.entry_price,
                "opened_at": h.opened_at,
            }
            for h in holdings
        ],
    }
