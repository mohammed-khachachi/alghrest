"""Authenticated observation collection; no trading or market qualification routes."""

import asyncio
import sqlite3
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from connectors.advisory.observation_store import ObservationConflictError, ObservationStore
from core.advisory.models import utcnow
from core.advisory.observations import (
    ObservationReview,
    ObservationView,
    ObservationWrite,
    observation_warnings,
    parse_observation,
)

router = APIRouter(prefix="/assistant-api/observations")


async def _call(request: Request, action: Callable[[ObservationStore], Any]) -> Any:
    def run() -> Any:
        return action(ObservationStore(request.app.state.service.store))

    try:
        return await asyncio.to_thread(run)
    except ObservationConflictError as exc:
        raise HTTPException(409, "تغيرت النسخة؛ افتح النسخة الأحدث قبل الحفظ أو المراجعة.") from exc
    except KeyError as exc:
        raise HTTPException(404, "لم توجد الملاحظة أو النسخة المطلوبة.") from exc
    except sqlite3.Error as exc:
        raise HTTPException(503, "تعذر الوصول إلى سجل الملاحظات؛ احتفظ بنسخة من مدخلاتك.") from exc
    except (ValueError, TypeError) as exc:
        # Never reflect input contents or filesystem/database details.
        raise HTTPException(
            400, "بيانات غير صالحة؛ راجع العقد والأرقام والأوقات وهوية النسخة."
        ) from exc


@router.post("/validate")
async def validate(value: ObservationWrite) -> dict[str, Any]:
    try:
        packet = parse_observation(value.raw_json)
        return {
            "packet": packet.model_dump(mode="json"),
            "warnings": observation_warnings(packet, now=utcnow()),
            "origin": "user_reported",
            "trade_permitted": False,
            "execution_enabled": False,
        }
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            400, "راجع صيغة JSON والعقد والأسعار والأوقات؛ لا تخمّن المجهول."
        ) from exc


@router.get("")
async def history(request: Request, observation_id: str | None = None) -> list[ObservationView]:
    result: list[ObservationView] = await _call(
        request, lambda store: store.history(now=utcnow(), observation_id=observation_id)
    )
    return result


@router.post("")
async def create(value: ObservationWrite, request: Request) -> ObservationView:
    result: ObservationView = await _call(
        request,
        lambda store: store.save(
            value.raw_json,
            observation_id=None,
            expected_revision=value.expected_revision,
            now=utcnow(),
        ),
    )
    return result


@router.get("/{observation_id}")
async def read(
    observation_id: str, request: Request, revision: str | None = None
) -> ObservationView:
    result: ObservationView = await _call(
        request, lambda store: store.read(observation_id, now=utcnow(), revision=revision)
    )
    return result


@router.put("/{observation_id}")
async def edit(observation_id: str, value: ObservationWrite, request: Request) -> ObservationView:
    result: ObservationView = await _call(
        request,
        lambda store: store.save(
            value.raw_json,
            observation_id=observation_id,
            expected_revision=value.expected_revision,
            now=utcnow(),
        ),
    )
    return result


@router.post("/{observation_id}/review")
async def review(
    observation_id: str, value: ObservationReview, request: Request
) -> ObservationView:
    result: ObservationView = await _call(
        request,
        lambda store: store.review(
            observation_id, expected_revision=value.expected_revision, now=utcnow()
        ),
    )
    return result
