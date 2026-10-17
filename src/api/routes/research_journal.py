"""Authenticated local watchlist and server-collected research snapshots."""

import asyncio
import sqlite3
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query, Request, Response

from api.routes.openterminal_context import terminal_research
from connectors.advisory.research_backup import export_research, restore_research
from connectors.advisory.research_journal import ResearchJournal
from core.advisory.models import utcnow
from core.advisory.openterminal_research import TerminalSymbol, valid_symbol
from core.advisory.research_journal import (
    CaptureRequest,
    ResearchSnapshot,
    ResearchWatch,
    ResearchWatchEntry,
)

router = APIRouter(prefix="/assistant-api")
T = TypeVar("T")


@router.get("/research-backup")
async def backup_download(request: Request) -> Response:
    now = utcnow()
    try:
        raw = await asyncio.to_thread(
            export_research, ResearchJournal(request.app.state.service.store), now
        )
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(
            409, "تعذر إنشاء نسخة بحث سليمة ضمن حد 32 ميغابايت؛ السجل الأصلي محفوظ."
        ) from exc
    return Response(
        raw,
        media_type="application/json",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="ALGHREST-research-backup-{now.date()}.json"',
        },
    )


async def restore_backup(request: Request, *, preview: bool) -> dict[str, int | str]:
    raw = await request.body()
    try:
        return await asyncio.to_thread(
            restore_research,
            ResearchJournal(request.app.state.service.store),
            raw,
            utcnow(),
            preview=preview,
        )
    except (ValueError, sqlite3.Error) as exc:
        raise HTTPException(
            409,
            "لم تُستعد أي بيانات: الملف غير صالح، أو توجد هوية لقطة متعارضة، أو سيُتجاوز حد السجل. لا يُحذف أو يُستبدل السجل الحالي.",
        ) from exc


@router.post("/research-backup/preview")
async def backup_preview(request: Request) -> dict[str, int | str]:
    return await restore_backup(request, preview=True)


@router.post("/research-backup/restore")
async def backup_restore(request: Request) -> dict[str, int | str]:
    return await restore_backup(request, preview=False)


async def call(request: Request, action: Callable[[ResearchJournal], T]) -> T:
    def run() -> T:
        return action(ResearchJournal(request.app.state.service.store))

    try:
        return await asyncio.to_thread(run)
    except sqlite3.Error as exc:
        raise HTTPException(503, "تعذر الوصول إلى سجل البحث؛ لم يتم تأكيد الحفظ.") from exc
    except ValueError as exc:
        raise HTTPException(
            409,
            "تعذر حفظ التغيير. أضف الرمز للمتابعة وتحقق من حدود السجل: 50 رمزًا و100 لقطة لكل رمز و5000 إجمالًا. اللقطات السابقة محفوظة.",
        ) from exc


@router.get("/research-watchlist")
async def watchlist(request: Request, response: Response) -> list[ResearchWatchEntry]:
    response.headers["Cache-Control"] = "no-store"
    return await call(request, lambda journal: journal.watchlist())


@router.put("/research-watchlist/{symbol}")
async def watch(
    symbol: TerminalSymbol, value: ResearchWatch, request: Request
) -> list[ResearchWatchEntry]:
    return await call(request, lambda journal: journal.watch(symbol, value.watched))


@router.get("/research-snapshots/{symbol}")
async def history(
    symbol: TerminalSymbol,
    request: Request,
    response: Response,
    limit: int = Query(default=100, ge=1, le=100),
) -> list[ResearchSnapshot]:
    response.headers["Cache-Control"] = "no-store"
    return await call(request, lambda journal: journal.history(symbol, limit=limit))


@router.post("/research-snapshots/{symbol}")
async def capture(
    symbol: TerminalSymbol, value: CaptureRequest, request: Request, response: Response
) -> ResearchSnapshot:
    response.headers["Cache-Control"] = "no-store"
    try:
        valid_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(422, "Invalid terminal symbol") from exc
    previous = await call(request, lambda journal: journal.existing(value.id, symbol))
    if previous:
        return previous  # Safe retry after a lost HTTP response; no new provider fetch.
    watches = await call(request, lambda journal: journal.watchlist())
    if symbol not in {entry.symbol for entry in watches}:
        raise HTTPException(409, "أضف الرمز إلى قائمة المتابعة قبل حفظ لقطة.")
    report = await terminal_research(symbol, response)
    if report.symbol != symbol:
        raise HTTPException(502, "رمز القراءة لا يطابق الرمز المطلوب؛ لم تُحفظ اللقطة.")
    record = ResearchSnapshot(id=value.id, saved_at=utcnow(), report=report)
    return await call(request, lambda journal: journal.save(record))
