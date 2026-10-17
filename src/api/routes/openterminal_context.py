"""Authenticated read-only bridge; no user token is forwarded to OpenTerminal."""

import httpx
from fastapi import APIRouter, Response

from connectors.advisory.openterminal import collect_terminal_context
from connectors.advisory.openterminal_research import collect_terminal_research
from core.advisory.openterminal_context import OpenTerminalContext, TerminalInstrument
from core.advisory.openterminal_research import TerminalResearch, TerminalSymbol, valid_symbol
from core.advisory.research_diagnostics import DiagnosticResult

router = APIRouter(prefix="/assistant-api")


@router.get("/openterminal-context/{instrument_id}")
async def terminal_context(
    instrument_id: TerminalInstrument, response: Response
) -> OpenTerminalContext:
    response.headers["Cache-Control"] = "no-store"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(6),
        trust_env=False,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=2, max_keepalive_connections=2),
    ) as client:
        return await collect_terminal_context(client, instrument_id)


@router.get("/openterminal-research/{symbol}")
async def terminal_research(symbol: TerminalSymbol, response: Response) -> TerminalResearch:
    from fastapi import HTTPException

    try:
        valid_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(422, "Invalid terminal symbol") from exc
    response.headers["Cache-Control"] = "no-store"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(16),
        trust_env=False,
        follow_redirects=False,
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=3),
    ) as client:
        return await collect_terminal_research(client, symbol)


@router.get("/research-diagnostics/{symbol}")
async def research_diagnostics(symbol: TerminalSymbol, response: Response) -> DiagnosticResult:
    from fastapi import HTTPException

    from connectors.advisory.research_diagnostics import collect_diagnostics

    try:
        valid_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(422, "Invalid terminal symbol") from exc
    response.headers["Cache-Control"] = "no-store"
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(3), trust_env=False, follow_redirects=False
    ) as client:
        return await collect_diagnostics(client, symbol)
