"""Market-data REST surface used by the dashboard symbol selector + market panel."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from connectors.data_providers import default_router
from connectors.data_providers.base import ANCHOR_DATE, AssetClass
from connectors.data_providers.holdings import get_holdings
from connectors.data_providers.openbb_adapter import (
    OpenBBAdapter,
    OpenBBAdapterError,
    OpenBBDataValidationError,
    OpenBBProviderError,
    OpenBBUnavailableError,
)
from connectors.data_providers.router import QuoteRouter, UnknownSymbolError
from core.config import settings
from core.data.models import Timeframe

router = APIRouter(prefix="/api", tags=["market-data"])
_openbb_adapter = OpenBBAdapter()


def _router() -> QuoteRouter:
    return default_router


def _openbb() -> OpenBBAdapter:
    return _openbb_adapter


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
) -> dict[str, Any]:
    requested = [s.strip() for s in symbols.split(",") if s.strip()]
    quotes = await _router().quote_many(requested)
    return {
        "as_of": ANCHOR_DATE.isoformat(),
        "quotes": [{**asdict(q), "asset_class": q.asset_class.value} for q in quotes],
    }


@router.get("/history")
async def get_history(
    symbol: Annotated[str, Query(description="Single symbol, e.g. BTC")],
    days: Annotated[int, Query(ge=2, le=365)] = 30,
) -> dict[str, Any]:
    try:
        bars = await _router().history(symbol, days)
    except UnknownSymbolError:
        raise HTTPException(status_code=404, detail=f"Unknown symbol: {symbol}") from None
    return {
        "symbol": symbol.upper(),
        "as_of": ANCHOR_DATE.isoformat(),
        "bars": [asdict(b) for b in bars],
    }


@router.get("/holdings")
async def get_holdings_route() -> dict[str, Any]:
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


@router.get("/openbb/providers")
async def get_openbb_providers() -> dict[str, Any]:
    """Return configured OpenBB provider settings and capability matrix."""
    adapter = _openbb()
    return {
        "enabled": settings.openbb_enabled,
        "sdk_available": adapter.is_available,
        "defaults": {
            "equity": adapter.default_provider_for(AssetClass.EQUITY),
            "crypto": adapter.default_provider_for(AssetClass.CRYPTO),
            "forex": adapter.default_provider_for(AssetClass.FOREX),
            "macro": adapter.default_provider_for("macro"),
        },
        "providers": adapter.supported_providers(),
    }


@router.get("/openbb/historical")
async def get_openbb_historical(
    symbol: Annotated[str, Query(description="Ticker symbol, e.g. AAPL, BTC/USDT, EUR/USD")],
    asset_class: Annotated[AssetClass, Query(description="equity | crypto | forex")] = (
        AssetClass.EQUITY
    ),
    timeframe: Annotated[Timeframe, Query(description="1m | 5m | 15m | 30m | 1h | 4h | 1d | 1w")] = (
        Timeframe.D1
    ),
    start_date: Annotated[date | None, Query(description="ISO start date YYYY-MM-DD")] = None,
    end_date: Annotated[date | None, Query(description="ISO end date YYYY-MM-DD")] = None,
    provider: Annotated[str | None, Query(description="Optional OpenBB provider override")] = None,
) -> dict[str, Any]:
    """Fetch normalized historical OHLCV bars via the OpenBB adapter."""
    adapter = _openbb()
    resolved_provider = provider or adapter.default_provider_for(asset_class)
    try:
        bars = await adapter.fetch_historical_ohlcv(
            symbol,
            asset_class=asset_class,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            provider=resolved_provider,
        )
    except OpenBBUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenBBDataValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OpenBBProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except OpenBBAdapterError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {
        "symbol": symbol.strip().upper(),
        "asset_class": asset_class.value,
        "timeframe": timeframe.value,
        "provider": resolved_provider,
        "count": len(bars),
        "bars": [bar.model_dump(mode="json") for bar in bars],
    }
