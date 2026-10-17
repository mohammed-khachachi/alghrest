"""Fixed local read-only endpoint; no credentials or remote error text forwarded."""

from urllib.parse import quote

import httpx
from pydantic import TypeAdapter

from connectors.advisory.openterminal import BASE_URL, MAX_BODY_BYTES
from core.advisory.models import utcnow
from core.advisory.openterminal_research import TerminalSymbol, valid_symbol
from core.advisory.research_diagnostics import DiagnosticResult, ResearchDiagnostics


async def collect_diagnostics(client: httpx.AsyncClient, symbol: str) -> DiagnosticResult:
    symbol = valid_symbol(TypeAdapter(TerminalSymbol).validate_python(symbol))
    try:
        async with client.stream(
            "GET", f"{BASE_URL}/api/research-diagnostics/{quote(symbol, safe='')}"
        ) as response:
            response.raise_for_status()
            raw = bytearray()
            async for chunk in response.aiter_bytes():
                raw.extend(chunk)
                if len(raw) > MAX_BODY_BYTES:
                    raise ValueError("Diagnostic response too large")
        data = ResearchDiagnostics.model_validate_json(raw)
        return DiagnosticResult(
            symbol=symbol, checked_at=utcnow(), state="available", diagnostics=data
        )
    except httpx.HTTPError:
        return DiagnosticResult(symbol=symbol, checked_at=utcnow(), state="unavailable")
    except (ValueError, TypeError, OverflowError):
        return DiagnosticResult(symbol=symbol, checked_at=utcnow(), state="invalid")
