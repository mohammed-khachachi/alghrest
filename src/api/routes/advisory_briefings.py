"""Authenticated evidence composition. No price, execution or paid model calls."""

import sqlite3

from fastapi import APIRouter, HTTPException, Request

from api.services.briefings import BriefingSaveOutcomeError, BriefingWorkflow
from connectors.advisory.briefing_store import BriefingConflictError
from core.advisory.briefing import BriefingRequest, BriefingView
from core.config import settings

router = APIRouter(prefix="/assistant-api/briefings")


def _workflow(request: Request) -> BriefingWorkflow:
    return BriefingWorkflow(
        request.app.state.service,
        request.app.state.calendars,
        agent_tap_enabled=bool(settings.advisory_kafka_servers),
    )


@router.post("")
async def create(value: BriefingRequest, request: Request) -> BriefingView:
    try:
        return await _workflow(request).create(value)
    except BriefingConflictError as exc:
        raise HTTPException(
            409, "تغيرت النسخة أو الحساب؛ اختر نسخة محفوظة مراجعة وأعد تحميل الحساب."
        ) from exc
    except BriefingSaveOutcomeError as exc:
        detail = (
            "حُفظ التقرير لكن تعذر عرض النتيجة؛ افتح سجل التقارير قبل إعادة المحاولة."
            if exc.state == "COMMITTED"
            else "تعذر تأكيد نتيجة الحفظ؛ قد يكون التقرير محفوظًا. راجع سجل التقارير قبل إعادة المحاولة."
        )
        raise HTTPException(504 if exc.timed_out else 503, detail) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "انتهت المهلة قبل الحفظ؛ لم يُحفظ تقرير.") from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "تعذر الوصول لسجل التقارير.") from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(
            400, "بيانات غير كافية أو غير متسقة؛ راجع النسخة والعقد والحساب."
        ) from exc


@router.get("")
async def history(request: Request) -> list[dict[str, str]]:
    try:
        return await _workflow(request).history()
    except sqlite3.Error as exc:
        raise HTTPException(503, "تعذر الوصول لسجل التقارير.") from exc


@router.get("/{identifier}")
async def read(identifier: str, request: Request) -> BriefingView:
    try:
        return await _workflow(request).read(identifier)
    except KeyError as exc:
        raise HTTPException(404, "التقرير غير موجود.") from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "تعذر الوصول لسجل التقارير.") from exc
    except ValueError as exc:
        raise HTTPException(
            400, "تعذر التحقق من التقرير؛ قد يختلف المصدر أو الكود. احتفظ بالأصل."
        ) from exc
