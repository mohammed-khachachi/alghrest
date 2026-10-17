"""Read-only published context; isolated from prices and permission calculations."""

from typing import Literal

from fastapi import APIRouter, Request

from api.services.briefings import collect_context
from core.advisory.news_context import NewsContext

router = APIRouter(prefix="/assistant-api/context")


async def _collect_context(
    request: Request, instrument_id: Literal["MES", "MNQ"]
) -> tuple[NewsContext, list[str]]:
    return await collect_context(
        request.app.state.service, request.app.state.calendars, instrument_id
    )


@router.get("/{instrument_id}")
async def context(instrument_id: Literal["MES", "MNQ"], request: Request) -> NewsContext:
    value, _ = await _collect_context(request, instrument_id)
    return value
