"""Read-only personal calculations against captured advisory-local journal inputs."""

import asyncio
import sqlite3
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from core.advisory.tcp25_personal import (
    CapacityRequest,
    PersonalEvidence,
    PlanRequest,
    RevisionConflictError,
    assess,
)

router = APIRouter(prefix="/assistant-api/tcp25/personal")


async def _calculate(
    request: Request,
    identifier: str,
    algorithm: Literal[
        "tcp25-personal-status-v1", "tcp25-personal-micro-cap-v1", "tcp25-personal-plan-v1"
    ],
    value: CapacityRequest | PlanRequest | None = None,
) -> PersonalEvidence:
    service = request.app.state.service
    try:
        if not any(p.id == identifier for p in await asyncio.to_thread(service.store.evaluations)):
            raise HTTPException(404, "Account not found")
        profile, rows = await asyncio.to_thread(service.store.evaluation, identifier)
        return assess(algorithm, now=service.clock(), profile=profile, sessions=rows, request=value)
    except RevisionConflictError as exc:
        raise HTTPException(409, "Policy/account revision changed; reload") from exc
    except (ValueError, sqlite3.Error, OSError) as exc:
        raise HTTPException(503, "Personal account evidence unavailable") from exc


@router.get("/rules")
async def rules(request: Request) -> PersonalEvidence:
    return assess("tcp25-personal-rules-v1", now=request.app.state.service.clock())


@router.get("/evaluations/{identifier}/status")
async def status(identifier: str, request: Request) -> PersonalEvidence:
    return await _calculate(request, identifier, "tcp25-personal-status-v1")


@router.post("/evaluations/{identifier}/capacity")
async def capacity(identifier: str, value: CapacityRequest, request: Request) -> PersonalEvidence:
    return await _calculate(request, identifier, "tcp25-personal-micro-cap-v1", value)


@router.post("/evaluations/{identifier}/plan")
async def plan(identifier: str, value: PlanRequest, request: Request) -> PersonalEvidence:
    return await _calculate(request, identifier, "tcp25-personal-plan-v1", value)
