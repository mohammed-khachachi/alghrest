"""Authenticated, offline PDF export of the saved public research watchlist."""

import asyncio
import sqlite3
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request, Response

from connectors.advisory.research_journal import ResearchJournal
from core.advisory.models import utcnow

router = APIRouter(prefix="/assistant-api")


@router.get("/research-brief.pdf")
async def research_brief_pdf(request: Request) -> Response:
    def create() -> tuple[bytes, str]:
        from api.services.research_pdf import render_research_pdf

        journal = ResearchJournal(request.app.state.service.store)
        if not journal.watchlist():
            raise ValueError("Empty watchlist")
        brief = journal.brief(now=utcnow())
        day = brief.generated_at.astimezone(ZoneInfo("Africa/Casablanca")).date().isoformat()
        return render_research_pdf(brief), day

    try:
        content, day = await asyncio.to_thread(create)
    except (ImportError, OSError, sqlite3.Error) as exc:
        raise HTTPException(
            503, "تعذر إنشاء PDF محليًا. تحقق من تثبيت متطلبات المشروع وسجل البحث ثم أعد المحاولة."
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            409, "أضف رمزًا للمتابعة وتحقق من سلامة اللقطات المحفوظة قبل إنشاء التقرير."
        ) from exc
    return Response(
        content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="ALGHREST-research-{day}.pdf"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
