"""Independent manual research API. Run: python -m api.advisor (loopback :8011)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.routes.advisory_briefings import router as briefings_router
from api.routes.advisory_capabilities import router as capabilities_router
from api.routes.advisory_context import router as context_router
from api.routes.advisory_observations import router as observations_router
from api.routes.openterminal_context import router as openterminal_router
from api.routes.research_brief import router as research_brief_router
from api.routes.research_journal import router as research_journal_router
from api.routes.tcp25_personal import router as tcp25_personal_router
from api.security import AccessTokenMiddleware
from api.services.advisory import AdvisoryService
from connectors.advisory.economic_calendar import CalendarCache
from connectors.advisory.intelligence import consume
from connectors.advisory.storage import AdvisoryStore
from core.advisory.account import assess_account_role
from core.advisory.analysis import risk_worksheet
from core.advisory.evaluation import (
    RULE_SOURCES,
    RULES_REVIEWED,
    EvaluationPlan,
    EvaluationProfile,
    EvaluationSession,
    evaluation_plan,
    evaluation_status,
    session_clock,
)
from core.advisory.imports import CSVImport
from core.advisory.models import CATALOG, Interval, MarketSnapshot, RiskWorksheet, Watchlist, utcnow
from core.advisory.policy import PolicyAssessment, PolicyControls, TCP25Policy, TCP50Policy
from core.advisory.research_backup import MAX_BACKUP_BYTES
from core.advisory.risk import RiskDecision, RiskRequest
from core.advisory.user_policy import UserPolicyAssessment, UserPolicyRequest, assess_user_policy
from core.advisory.user_risk import (
    UserRiskAssessment,
    UserRiskRequest,
    assess_user_risk,
    personal_account_status,
    personal_rules,
)
from core.config import settings
from core.kafka.security import aiokafka_security


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if settings.advisory_kafka_servers:
        aiokafka_security("advisory")  # Reject missing credentials before launching a task.
    store = await asyncio.to_thread(AdvisoryStore, settings.advisory_db_path)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(8),
        limits=httpx.Limits(max_connections=3, max_keepalive_connections=3),
        follow_redirects=True,
        headers={"User-Agent": "ALGHREST-Manual-Research/1.0"},
    ) as client:
        policy_type = {
            "earn2trade_tcp25": TCP25Policy,
            "earn2trade_tcp50": TCP50Policy,
        }.get(settings.operating_profile)
        policy = (
            policy_type(
                PolicyControls(
                    id="legacy-journal-observation-bounds",
                    version="v1",
                    source_reference="Existing journal freshness (1800 seconds) and rule-review (30 days) ceilings; not calibrated production SLOs",
                    max_evidence_age_seconds=1800,
                    max_review_age_days=30,
                )
            )
            if policy_type is not None
            else None
        )
        app.state.service = AdvisoryService(store, client, evaluation_policy=policy)
        app.state.calendars = CalendarCache()
        task = (
            asyncio.create_task(consume(store, settings.advisory_kafka_servers))
            if settings.advisory_kafka_servers
            else None
        )
        try:
            yield
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="ALGHREST Manual Research", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.advisory_allowed_origins,
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type", "X-Advisory-Client", "Authorization"],
)


@app.middleware("http")
async def local_writes(request: Request, call_next: Any) -> Any:
    from fastapi.responses import JSONResponse

    if request.method in {"POST", "PUT"}:
        if request.headers.get("x-advisory-client") != "dashboard":
            return JSONResponse(
                {"detail": "Explicit advisory client header required"}, status_code=403
            )
        path = request.scope["path"]
        root = request.scope.get("root_path", "").rstrip("/")
        if root and path.startswith(root + "/"):
            path = path[len(root) :]
        retired = path.rstrip("/") == "/assistant-api/briefings" or (
            path.startswith("/assistant-api/evaluations/")
            and path.rstrip("/").rsplit("/", 1)[-1] in {"user-policy-check", "personal-plan"}
        )
        if request.method == "POST" and retired:
            detail = (
                "Legacy briefing creation is retired. Historical briefings remain readable; TCP25 briefing creation is not implemented."
                if path.rstrip("/") == "/assistant-api/briefings"
                else "Legacy personal calculation is retired; use the versioned TCP25 personal endpoints."
            )
            return JSONResponse(
                {"detail": detail}, status_code=409, headers={"Cache-Control": "no-store"}
            )
        # Check bytes received, including chunked requests, before JSON parsing.
        body = bytearray()
        limit = (
            MAX_BACKUP_BYTES
            if request.url.path
            in {"/assistant-api/research-backup/preview", "/assistant-api/research-backup/restore"}
            else 500000
        )
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > limit:
                return JSONResponse(
                    {
                        "detail": (
                            "Request exceeds 500 KB"
                            if limit == 500000
                            else "Research backup exceeds 32 MiB"
                        )
                    },
                    status_code=413,
                )
        request._body = bytes(body)
    return await call_next(request)


# Added after the body middleware so unauthorized requests never enter handlers
# or buffer an import body. Host checks still apply to authenticated requests.
app.add_middleware(AccessTokenMiddleware, service="advisory")
app.include_router(observations_router)
app.include_router(context_router)
app.include_router(briefings_router)
app.include_router(tcp25_personal_router)
app.include_router(capabilities_router)
app.include_router(openterminal_router)
app.include_router(research_journal_router)
app.include_router(research_brief_router)


@app.get("/health/live", include_in_schema=False)
async def liveness() -> dict[str, str]:
    return {"status": "ok"}


def service(request: Request) -> AdvisoryService:
    return request.app.state.service  # type: ignore[no-any-return]


@app.get("/assistant-api/health")
async def health() -> dict[str, Any]:
    return {
        "service": "manual-research",
        "execution_enabled": False,
        "storage": "isolated",
        "agent_tap_enabled": bool(settings.advisory_kafka_servers),
        "time": utcnow().isoformat(),
    }


@app.get("/assistant-api/catalog")
async def catalog() -> list[dict[str, Any]]:
    return [v.model_dump(mode="json") for v in CATALOG.values()]


@app.get("/assistant-api/watchlist")
async def watchlist(request: Request) -> Watchlist:
    return await asyncio.to_thread(service(request).store.watchlist)


@app.put("/assistant-api/watchlist")
async def update_watchlist(value: Watchlist, request: Request) -> Watchlist:
    async with service(request).lock:
        await asyncio.to_thread(service(request).store.set_watchlist, value)
        service(request).cache.clear()
    return value


@app.get("/assistant-api/report/{instrument_id}")
async def report(instrument_id: str, request: Request, interval: Interval = "15m") -> Any:
    try:
        return await service(request).report(instrument_id, interval)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(
            504, "Research sources timed out; automated trading is unaffected"
        ) from exc


@app.get("/assistant-api/market-selection")
async def market_selection(request: Request, interval: Interval = "15m") -> Any:
    try:
        return await service(request).selection(interval)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Market comparison timed out; no market selected") from exc


@app.get("/assistant-api/selection-record/{selection_id}")
async def selection_record(selection_id: str, request: Request) -> Any:
    try:
        value = await asyncio.to_thread(service(request).store.selection, selection_id)
    except ValueError as exc:
        raise HTTPException(400, "Stored selection is invalid") from exc
    if value is None:
        raise HTTPException(404, "Selection not found")
    return value


@app.post("/assistant-api/import")
async def import_market(value: MarketSnapshot, request: Request) -> dict[str, str]:
    if value.data_mode != "user_import" or value.fetched_at > utcnow():
        raise HTTPException(
            400, "Imports must be explicitly marked user_import with a nonfuture timestamp"
        )
    await asyncio.to_thread(service(request).store.import_market, value)
    service(request).cache.pop((value.instrument_id, value.interval), None)
    return {"status": "saved", "instrument": value.instrument_id}


@app.post("/assistant-api/import-csv")
async def import_csv(value: CSVImport, request: Request) -> dict[str, str]:
    try:
        return await import_market(value.market(), request)
    except (ValueError, KeyError, OverflowError) as exc:
        raise HTTPException(
            400,
            "Invalid CSV: verify headers, prices, ordered timezone-aware completed candles and contract",
        ) from exc


@app.post("/assistant-api/risk-worksheet")
async def worksheet(value: RiskWorksheet) -> dict[str, str]:
    try:
        return risk_worksheet(value)
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, "Check instrument, entry, stop and contract type") from exc


@app.get("/assistant-api/history")
async def history(request: Request) -> list[dict[str, str]]:
    return await asyncio.to_thread(service(request).store.history)


@app.get("/assistant-api/saved/{report_id}")
async def saved(report_id: str, request: Request) -> dict[str, Any]:
    try:
        result = await asyncio.to_thread(service(request).store.report, report_id)
    except ValueError as exc:
        raise HTTPException(400, "Stored report is invalid") from exc
    if result is None:
        raise HTTPException(404, "Report not found")
    return result


@app.get("/assistant-api/evaluation-rules")
async def rules() -> dict[str, Any]:
    return {
        "reviewed_on": RULES_REVIEWED,
        "sources": RULE_SOURCES,
        "clock": session_clock(utcnow()),
    }


@app.get("/assistant-api/evaluations")
async def evaluations(request: Request) -> list[EvaluationProfile]:
    return await asyncio.to_thread(service(request).store.evaluations)


@app.post("/assistant-api/evaluations")
async def create_evaluation(value: EvaluationProfile, request: Request) -> EvaluationProfile:
    try:
        await asyncio.to_thread(service(request).store.create_evaluation, value)
        return value
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/assistant-api/evaluations/{evaluation_id}")
async def evaluation(evaluation_id: str, request: Request) -> dict[str, Any]:
    try:
        profile, rows = await asyncio.to_thread(service(request).store.evaluation, evaluation_id)
        return evaluation_status(profile, rows)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.put("/assistant-api/evaluations/{evaluation_id}/session")
async def session(evaluation_id: str, value: EvaluationSession, request: Request) -> dict[str, Any]:
    try:
        await asyncio.to_thread(service(request).store.save_session, evaluation_id, value)
        return await evaluation(evaluation_id, request)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/assistant-api/evaluations/{evaluation_id}/plan")
async def plan(evaluation_id: str, value: EvaluationPlan, request: Request) -> dict[str, str]:
    try:
        advisor = service(request)
        profile, rows, account_plan, registry = await asyncio.to_thread(
            advisor.store.risk_context, evaluation_id
        )
        result = evaluation_plan(value, profile, rows)
        if advisor.account_roles_required or account_plan is not None:
            role = assess_account_role(
                account_plan,
                account_id=evaluation_id,
                requested_configuration=None,
                mode=(
                    "replay"
                    if rows and rows[-1].account and rows[-1].account.source == "replay"
                    else "current"
                ),
                now=advisor.clock(),
            )
            # This legacy worksheet lacks strategy/research identity. It cannot
            # stand in for the versioned, role-scoped risk decision pipeline.
            raise ValueError("NO TRADE: " + ", ".join(role.reasons))
        if advisor.strategy_registry_required or registry.records:
            raise ValueError("NO TRADE: Legacy worksheet lacks immutable strategy identity")
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/assistant-api/evaluations/{evaluation_id}/risk-decision")
async def risk_decision(evaluation_id: str, value: RiskRequest, request: Request) -> RiskDecision:
    try:
        return await service(request).risk_decision(evaluation_id, value)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Risk evidence timed out; no trade permitted") from exc


@app.post("/assistant-api/evaluations/{evaluation_id}/user-policy-check")
async def user_policy_check(
    evaluation_id: str, value: UserPolicyRequest, request: Request
) -> UserPolicyAssessment:
    try:
        advisor = service(request)
        profile, rows = await asyncio.to_thread(advisor.store.evaluation, evaluation_id)
        return assess_user_policy(profile, rows, value, now=advisor.clock())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/assistant-api/user-policy-rules")
async def user_rules() -> dict[str, Any]:
    return personal_rules()


@app.get("/assistant-api/evaluations/{evaluation_id}/personal-status")
async def personal_status(evaluation_id: str, request: Request) -> dict[str, Any]:
    try:
        advisor = service(request)
        profile, rows = await asyncio.to_thread(advisor.store.evaluation, evaluation_id)
        return personal_account_status(profile, rows, now=advisor.clock())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/assistant-api/evaluations/{evaluation_id}/personal-plan")
async def personal_plan(
    evaluation_id: str, value: UserRiskRequest, request: Request
) -> UserRiskAssessment:
    try:
        advisor = service(request)
        profile, rows = await asyncio.to_thread(advisor.store.evaluation, evaluation_id)
        return assess_user_risk(profile, rows, value, now=advisor.clock())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/assistant-api/risk-decision/{decision_id}")
async def saved_risk_decision(decision_id: str, request: Request) -> RiskDecision:
    try:
        value = await asyncio.to_thread(service(request).store.risk_decision, decision_id)
    except ValueError as exc:
        raise HTTPException(400, "Stored risk decision is invalid") from exc
    if value is None:
        raise HTTPException(404, "Risk decision not found")
    return value


@app.get("/assistant-api/evaluation-policy")
async def evaluation_policy(request: Request) -> dict[str, Any]:
    policy = service(request).evaluation_policy
    return {
        "configured": policy is not None,
        "rules": policy.rules.model_dump(mode="json") if policy else None,
        "trade_permitted": False,
        "execution_enabled": False,
    }


@app.get("/assistant-api/account-plan")
async def account_plan(request: Request) -> dict[str, Any]:
    try:
        value = await asyncio.to_thread(service(request).store.account_plan)
    except ValueError as exc:
        raise HTTPException(400, "Stored account plan is invalid") from exc
    return {
        "configured": value is not None,
        "required": service(request).account_roles_required,
        "plan": value.model_dump(mode="json") if value else None,
        "revision": value.revision if value else None,
        "trade_permitted": False,
        "execution_enabled": False,
    }


@app.post("/assistant-api/evaluations/{evaluation_id}/policy-check")
async def policy_check(
    evaluation_id: str, value: RiskRequest, request: Request
) -> PolicyAssessment:
    try:
        return await service(request).policy_assessment(evaluation_id, value)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(504, "Policy evidence timed out; no trade permitted") from exc


@app.get("/assistant-api/policy-check/{assessment_id}")
async def saved_policy_check(assessment_id: str, request: Request) -> PolicyAssessment:
    try:
        value = await asyncio.to_thread(service(request).store.policy_assessment, assessment_id)
    except ValueError as exc:
        raise HTTPException(400, "Stored policy assessment is invalid") from exc
    if value is None:
        raise HTTPException(404, "Policy assessment not found")
    return value


if __name__ == "__main__":
    uvicorn.run(
        "api.advisor:app",
        host="127.0.0.1",
        port=8011,
        workers=1,
        limit_concurrency=8,
        timeout_keep_alive=5,
    )
