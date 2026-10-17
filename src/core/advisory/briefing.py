"""Reproducible session brief: reported evidence, never a signal or permission."""

import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Self
from uuid import uuid4

from pydantic import ConfigDict, Field, StrictBool, model_validator

from core.advisory.evaluation import EvaluationProfile, EvaluationSession
from core.advisory.models import Strict, UTCDateTime, utc_instant
from core.advisory.news_context import NewsContext, build_context
from core.advisory.observations import ObservationView, observation_warnings
from core.advisory.user_policy import UserPolicyAssessment, UserPolicyRequest, assess_user_policy
from core.advisory.user_risk import personal_account_status

Identity = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MAX_RECORD_BYTES = 2_000_000
AGENT_TOPICS = {
    "news.tagged": "agent_news",
    "indicators.computed": "agent_technical",
    "macro.regime": "agent_macro",
    "sentiment.scored": "agent_sentiment",
    "volatility.forecast": "agent_volatility",
}
SOURCE_FILES = (
    "src/core/advisory/briefing.py",
    "src/core/advisory/observations.py",
    "src/core/advisory/news_context.py",
    "src/core/advisory/user_risk.py",
    "src/core/advisory/user_policy.py",
    "src/core/advisory/evaluation.py",
    "src/core/advisory/account.py",
    "src/core/advisory/analysis.py",
    "src/core/advisory/models.py",
    "src/connectors/advisory/intelligence.py",
    "src/connectors/advisory/briefing_store.py",
    "src/api/routes/advisory_briefings.py",
    "src/api/routes/advisory_context.py",
    "src/api/services/briefings.py",
)


def source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[3]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


class BriefModel(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BriefingRequest(BriefModel):
    observation_id: Identity
    observation_revision: Digest
    evaluation_id: Identity
    account_revision: Digest


class BriefingInputs(BriefModel):
    assessed_at: UTCDateTime
    observation: ObservationView
    profile: EvaluationProfile
    sessions: tuple[EvaluationSession, ...] = Field(max_length=2000)
    context: NewsContext
    interests: tuple[Annotated[str, Field(max_length=100)], ...] = Field(max_length=50)
    agent_tap_enabled: StrictBool
    agent_records: tuple[dict[str, str], ...] = Field(max_length=20)

    @model_validator(mode="after")
    def bounded_and_causal(self) -> Self:
        if self.context.instrument_id != self.observation.record.packet.instrument_id:
            raise ValueError("Observation/context instrument mismatch")
        if (
            self.context.assessed_at > self.assessed_at
            or self.observation.assessed_at > self.assessed_at
        ):
            raise ValueError("Future evidence assessment")
        view = self.observation
        if (
            view.reviewed_at is not None
            and not view.record.created_at <= view.reviewed_at <= view.assessed_at
        ):
            raise ValueError("Invalid review clock")
        for row in self.agent_records:
            if len(row) > 7 or any(len(k) > 100 or len(v) > 2000 for k, v in row.items()):
                raise ValueError("Oversize intelligence record")
        return self


class Capability(BriefModel):
    name: str
    state: Literal["AVAILABLE", "PARTIAL", "MISSING", "DISABLED"]
    reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...] = ()


class BriefingResult(BriefModel):
    state: Literal["REVIEWABLE", "INCOMPLETE"]
    decision: Literal["WAIT", "NO_TRADE"]
    reasons: tuple[str, ...]
    observation_warnings: tuple[str, ...]
    frame_comparison: Literal["SAME_TIME_SAME_LAST", "SAME_TIME_CONFLICT", "NOT_COMPARABLE"]
    account_status: dict[str, Any]
    cap: UserPolicyAssessment | None
    context: NewsContext
    capabilities: tuple[Capability, ...]
    agent_context: tuple[dict[str, str], ...]
    firm_compliance: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    passing_probability: Literal["UNKNOWN"] = "UNKNOWN"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False


def _project(inputs: BriefingInputs) -> BriefingResult:
    inputs = BriefingInputs.model_validate(inputs.model_dump())
    now = inputs.assessed_at
    view, packet = inputs.observation, inputs.observation.record.packet
    warnings = observation_warnings(packet, now=now)
    issues = set(warnings) | {"research_only", "event_risk_unknown", "strategy_not_integrated"}
    reviewed = (
        view.reviewed_at is not None
        and view.reviewed_at <= now
        and view.record.revision == view.latest_revision
    )
    if not reviewed:
        issues.add("observation_not_current_and_reviewed")
    if packet.contract is None:
        issues.add("dated_contract_missing")
    frames = packet.frames
    comparable = len(frames) > 1 and all(
        f.observed_at == frames[0].observed_at and f.observed_at is not None and f.last is not None
        for f in frames
    )
    comparison: Literal["SAME_TIME_SAME_LAST", "SAME_TIME_CONFLICT", "NOT_COMPARABLE"] = (
        "NOT_COMPARABLE"
    )
    if comparable:
        from decimal import Decimal

        comparison = (
            "SAME_TIME_SAME_LAST"
            if len({Decimal(f.last) for f in frames if f.last is not None}) == 1
            else "SAME_TIME_CONFLICT"
        )
    if comparison == "SAME_TIME_CONFLICT":
        issues.add("same_time_price_conflict")
    context = inputs.context
    replayed = build_context(
        packet.instrument_id,
        [h.item for h in context.headlines],
        list(context.events),
        list(context.sources),
        list(inputs.interests),
        now=context.assessed_at,
    )
    if replayed != context:
        raise ValueError("Captured context does not reproduce")
    context = build_context(
        packet.instrument_id,
        [h.item for h in context.headlines],
        list(context.events),
        list(context.sources),
        list(inputs.interests),
        now=now,
    )
    if any(s.state not in {"ok", "empty"} for s in context.sources) or not context.sources:
        issues.add("partial_or_unavailable_sources")
    status = personal_account_status(inputs.profile, list(inputs.sessions), now=now)
    if not status["personal_terms_match"]:
        issues.add("personal_terms_mismatch")
    if not status["fresh_observation"] or status["account_state"]["health"] != "KNOWN":
        issues.add("account_evidence_incomplete")
    issues.update("recorded_breach:" + str(r) for r in status["breaches"])
    cap = None
    if packet.contract:
        cap = assess_user_policy(
            inputs.profile,
            list(inputs.sessions),
            UserPolicyRequest(
                instrument_id=packet.instrument_id, contract=packet.contract, additional_contracts=1
            ),
            now=now,
        )
        issues.update(cap.reasons)
    selected = []
    for row in inputs.agent_records:
        try:
            when = utc_instant(datetime.fromisoformat(row["timestamp"]))
            affected = json.loads(row.get("affected_symbols", "[]"))
            if not isinstance(affected, list) or not re.fullmatch(r"[a-f0-9]{64}", row["id"]):
                raise ValueError("Invalid reported source identity")
            markets = [row["symbol"], *affected]
            if not all(isinstance(m, str) for m in markets):
                raise ValueError("Malformed market identities")
            summary = json.loads(row["summary"])
            if not isinstance(summary, dict) or not summary:
                raise ValueError("No reported context")
            related = packet.instrument_id in markets or packet.contract in markets
            if (
                inputs.agent_tap_enabled
                and row["topic"] in AGENT_TOPICS
                and related
                and timedelta(0) <= now - when <= timedelta(hours=1)
            ):
                selected.append(dict(row))
        except (KeyError, ValueError, TypeError, RecursionError):
            issues.add("invalid_agent_record")
    caps = [
        Capability(
            name="observations",
            state="AVAILABLE" if reviewed else "MISSING",
            reasons=("user_reported_not_market_qualified",),
            evidence_ids=(view.record.revision,),
        ),
        Capability(
            name="published_context",
            state="PARTIAL",
            reasons=("coverage_partial", "event_risk_unknown"),
        ),
        Capability(
            name="account_and_exposure",
            state=(
                "AVAILABLE"
                if status["fresh_observation"]
                and status["account_state"]["health"] == "KNOWN"
                and status["personal_terms_match"]
                else "MISSING"
            ),
            reasons=("user_reported_account", "new_size_requires_flat_account_and_reviewed_costs"),
            evidence_ids=(status["account_revision"],),
        ),
        Capability(
            name="strategy",
            state="MISSING",
            reasons=("no_qualified_5m_15m_strategy_in_this_brief",),
        ),
    ]
    for topic, name in AGENT_TOPICS.items():
        ids = tuple(r["id"] for r in selected if r["topic"] == topic and "id" in r)
        caps.append(
            Capability(
                name=name,
                state="PARTIAL" if ids else "MISSING" if inputs.agent_tap_enabled else "DISABLED",
                reasons=(
                    ("reported_context_not_verified_signal",)
                    if ids
                    else (
                        ("no_current_related_context",)
                        if inputs.agent_tap_enabled
                        else ("tap_not_connected",)
                    )
                ),
                evidence_ids=ids,
            )
        )
    caps.extend(
        Capability(name=n, state="DISABLED", reasons=("outside_advisory_workflow",))
        for n in ("execution", "defi", "copy_trading")
    )
    severe = (
        comparison == "SAME_TIME_CONFLICT"
        or bool(status["breaches"])
        or cap is not None
        and cap.state == "BLOCKED"
    )
    adequate = (
        reviewed
        and packet.contract is not None
        and all(
            f.last is not None
            and f.observed_at is not None
            and now - f.observed_at < timedelta(minutes=15)
            for f in frames
        )
        and status["fresh_observation"]
        and status["account_state"]["health"] == "KNOWN"
        and status["personal_terms_match"]
        and not severe
    )
    summary = {k: v for k, v in status.items() if k not in {"profile", "sessions"}}
    return BriefingResult(
        state="REVIEWABLE" if adequate else "INCOMPLETE",
        decision="NO_TRADE" if severe else "WAIT",
        reasons=tuple(sorted(issues)),
        observation_warnings=warnings,
        frame_comparison=comparison,
        account_status=summary,
        cap=cap,
        context=context,
        capabilities=tuple(caps),
        agent_context=tuple(selected),
    )


class Briefing(BriefModel):
    schema_version: Literal["evaluation-briefing-v1"] = "evaluation-briefing-v1"
    id: Annotated[str, Field(pattern=r"^[a-f0-9]{32}$")]
    inputs: BriefingInputs
    source_hashes: dict[str, Digest]
    result: BriefingResult

    @model_validator(mode="after")
    def replay(self) -> Self:
        if self.source_hashes != source_hashes():
            raise ValueError("Briefing source hashes differ; preserve old evidence")
        if self.result != _project(self.inputs):
            raise ValueError("Saved briefing does not reproduce exactly")
        return self


def build_briefing(inputs: BriefingInputs) -> Briefing:
    inputs = BriefingInputs.model_validate(inputs.model_dump())
    return Briefing(
        id=uuid4().hex, inputs=inputs, source_hashes=source_hashes(), result=_project(inputs)
    )


def verify_briefing(value: Briefing) -> Briefing:
    return Briefing.model_validate(value.model_dump())


class BriefingView(BriefModel):
    record: Briefing
    reopened_at: UTCDateTime
    current_warnings: tuple[str, ...]
    historical_context: Literal[True] = True
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False
