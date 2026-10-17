"""Authenticated read-only mission map; no agent startup or market readiness assessment."""

import asyncio

from fastapi import APIRouter, HTTPException

from core.advisory.capability_registry import CapabilityRegistry, capability_registry

router = APIRouter(prefix="/assistant-api/capabilities")


@router.get("", response_model=CapabilityRegistry)
async def capabilities() -> CapabilityRegistry:
    try:
        return await asyncio.to_thread(capability_registry)
    except (OSError, ValueError) as exc:
        raise HTTPException(503, "Capability map unavailable; no readiness assessed") from exc
