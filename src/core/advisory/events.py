"""Pure economic-event guard; no AI, order, provider or prop-firm dependency."""

from datetime import datetime, timedelta

from core.advisory.models import (
    CATALOG,
    EconomicCalendar,
    EventRiskAssessment,
    EventRiskPolicy,
    utc_instant,
)


def assess_event_risk(
    calendar: EconomicCalendar | None,
    policy: EventRiskPolicy | None,
    instrument_id: str,
    *,
    now: datetime,
) -> EventRiskAssessment:
    """Require complete point-in-time coverage before interpreting no event as clear."""
    now = utc_instant(now)
    failures: list[str] = []
    unknown: list[str] = []
    blocked: list[str] = []
    if instrument_id not in CATALOG:
        failures.append("unknown_event_market")
    if policy is None:
        unknown.append("missing_event_policy")
    else:
        try:
            policy = EventRiskPolicy.model_validate(policy.model_dump())
        except (ValueError, TypeError, AttributeError):
            policy = None
            failures.append("invalid_event_policy")
    if calendar is None:
        unknown.append("missing_economic_calendar")
    else:
        try:
            calendar = EconomicCalendar.model_validate(calendar.model_dump())
        except (ValueError, TypeError, AttributeError):
            calendar = None
            failures.append("invalid_economic_calendar")
    if calendar is not None:
        if calendar.provider_state in {"degraded", "disconnected"}:
            failures.append("calendar_provider_" + calendar.provider_state)
        elif calendar.provider_state == "unknown":
            unknown.append("unknown_calendar_provider")
        if not calendar.complete:
            unknown.append("incomplete_calendar")
        if instrument_id not in calendar.covered_markets:
            unknown.append("uncovered_event_market")
        age = (now - calendar.observed_at).total_seconds()
        if age < 0:
            failures.append("future_calendar_observation")
        if policy is not None:
            if age > policy.max_calendar_age_seconds:
                unknown.append("stale_calendar")
            # Events that can affect this cut lie in [now - after, now + before].
            try:
                start = now - timedelta(seconds=policy.after_seconds)
                end = now + timedelta(seconds=policy.before_seconds)
            except OverflowError:
                failures.append("invalid_event_clock_window")
                start = end = now
            if calendar.coverage_start > start or calendar.coverage_end < end:
                unknown.append("incomplete_event_window")
            for event in calendar.events:
                if instrument_id not in event.affected_markets or event.status == "cancelled":
                    continue
                if event.scheduled_at is None:
                    unknown.append("unknown_event_time:" + event.id)
                    continue
                if not start <= event.scheduled_at <= end:
                    continue
                if event.status == "unknown" or event.impact == "unknown":
                    unknown.append("unknown_event_classification:" + event.id)
                elif event.impact in policy.blocked_impacts:
                    failures.append("event_blackout:" + event.id)
                    blocked.append(event.id)
    return EventRiskAssessment(
        state="BLOCKED" if failures else "UNKNOWN" if unknown else "CLEAR",
        assessed_at=now,
        reasons=tuple(sorted(set(failures + unknown))),
        blocked_event_ids=tuple(sorted(blocked)),
        calendar=calendar,
        policy=policy,
    )
