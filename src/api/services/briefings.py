"""One owner for captured context, briefing order and request-local save coordination."""

import asyncio
import time
from typing import Literal

from api.services.advisory import AdvisoryService
from connectors.advisory.briefing_store import (
    BriefingSaveGuard,
    BriefingStore,
    SaveState,
    guarded_briefing_save,
)
from connectors.advisory.economic_calendar import CALENDARS, CalendarCache
from connectors.advisory.news import FEEDS
from connectors.advisory.observation_store import ObservationStore
from core.advisory.briefing import BriefingInputs, BriefingRequest, BriefingView, build_briefing
from core.advisory.news_context import NewsContext, build_context

WORKFLOW_TIMEOUT_SECONDS = 30.0


class BriefingSaveOutcomeError(Exception):
    def __init__(self, state: SaveState, *, timed_out: bool) -> None:
        super().__init__("Save outcome must be reconciled from history")
        self.state = state
        self.timed_out = timed_out


async def collect_context(
    service: AdvisoryService, calendars: CalendarCache, instrument_id: Literal["MES", "MNQ"]
) -> tuple[NewsContext, list[str]]:
    """Reuse the existing caches and retain their actual source timestamps."""
    news_results, calendar_results = await asyncio.gather(
        asyncio.gather(*(service.feeds.context(service.client, name) for name in FEEDS)),
        asyncio.gather(*(calendars.get(service.client, name) for name in CALENDARS)),
    )
    watchlist = await asyncio.to_thread(service.store.watchlist)
    return (
        build_context(
            instrument_id,
            [item for items, _ in news_results for item in items],
            [event for events, _ in calendar_results for event in events],
            [status for _, status in (*news_results, *calendar_results)],
            watchlist.interests,
            now=service.clock(),
        ),
        watchlist.interests,
    )


def _consume_save_result(task: asyncio.Task[BriefingView]) -> None:
    if not task.cancelled():
        # A timed-out caller may leave a bounded worker finishing its transaction.
        # Consume its exception without logging private captured inputs.
        task.exception()


class BriefingWorkflow:
    def __init__(
        self, service: AdvisoryService, calendars: CalendarCache, *, agent_tap_enabled: bool
    ) -> None:
        self.service = service
        self.calendars = calendars
        self.agent_tap_enabled = agent_tap_enabled

    async def create(self, value: BriefingRequest) -> BriefingView:
        value = BriefingRequest.model_validate(value.model_dump())
        service = self.service
        guard = BriefingSaveGuard(time.monotonic() + WORKFLOW_TIMEOUT_SECONDS)
        try:
            async with asyncio.timeout(WORKFLOW_TIMEOUT_SECONDS):
                store = await asyncio.to_thread(BriefingStore, service.store)
                await asyncio.to_thread(store.check, value, now=service.clock())
                observations = await asyncio.to_thread(ObservationStore, service.store)
                observation = await asyncio.to_thread(
                    observations.read,
                    value.observation_id,
                    revision=value.observation_revision,
                    now=service.clock(),
                )
                profile, sessions = await asyncio.to_thread(
                    service.store.evaluation, value.evaluation_id
                )
                context, interests = await collect_context(
                    service, self.calendars, observation.record.packet.instrument_id
                )
                agents = await asyncio.to_thread(service.store.intelligence)
                now = service.clock()
                await asyncio.to_thread(store.check, value, now=now)
                result = await asyncio.to_thread(
                    build_briefing,
                    BriefingInputs(
                        assessed_at=now,
                        observation=observation,
                        profile=profile,
                        sessions=tuple(sessions),
                        context=context,
                        interests=tuple(interests),
                        agent_records=tuple(agents),
                        agent_tap_enabled=self.agent_tap_enabled,
                    ),
                )
                with guarded_briefing_save(guard):
                    save = asyncio.create_task(
                        asyncio.to_thread(store.save, result, value, now=service.clock())
                    )
                save.add_done_callback(_consume_save_result)
                return await asyncio.shield(save)
        except asyncio.CancelledError:
            guard.cancel()
            raise
        except Exception as exc:
            state = guard.cancel()
            if state in {"COMMITTING", "COMMITTED", "UNKNOWN"}:
                raise BriefingSaveOutcomeError(
                    state, timed_out=isinstance(exc, TimeoutError)
                ) from exc
            raise

    async def history(self) -> list[dict[str, str]]:
        store = await asyncio.to_thread(BriefingStore, self.service.store)
        return await asyncio.to_thread(store.history)

    async def read(self, identifier: str) -> BriefingView:
        store = await asyncio.to_thread(BriefingStore, self.service.store)
        return await asyncio.to_thread(store.read, identifier, now=self.service.clock())
