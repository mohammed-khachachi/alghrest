"""Research composition and bounded single-flight refresh, separate from trading."""

import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

import httpx

from connectors.advisory.market import AdvisoryMarketData, PublicMarkets
from connectors.advisory.news import FeedCache, headlines
from connectors.advisory.storage import AdvisoryStore
from core.advisory.analysis import build_report, risk_worksheet
from core.advisory.data import MarketDataProvider, MarketDataQuery, bounded_snapshot
from core.advisory.evaluation import (
    EvaluationProfile,
    EvaluationSession,
    evaluation_risk_blocks,
    evaluation_status,
)
from core.advisory.events import assess_event_risk
from core.advisory.health import assess_market_data
from core.advisory.models import (
    CATALOG,
    EconomicCalendar,
    EventRiskPolicy,
    Interval,
    News,
    Report,
    RiskWorksheet,
    utcnow,
)
from core.advisory.policy import EvaluationEvidence, EvaluationPolicy, PolicyAssessment
from core.advisory.risk import RiskDecision, RiskInputs, RiskRequest, StructuralSetup, assess_risk
from core.advisory.selection import (
    CandidateEvidence,
    MarketSelection,
    MarketSelectionPolicy,
    select_markets,
)


def relevant(context: dict[str, str], symbol: str) -> bool:
    symbols = ([context["symbol"]] if context["symbol"] else []) + json.loads(
        context.get("affected_symbols", "[]")
    )
    allowed = {"NQ", "MNQ", "NDX", "NASDAQ100"} if symbol in {"NQ", "MNQ", "NDX"} else {symbol}
    return not symbols or any(s.replace("/", "").split(":")[0] in allowed for s in symbols)


def journal_revision(profile: EvaluationProfile, rows: list[EvaluationSession]) -> str:
    encoded = json.dumps(
        [profile.model_dump(mode="json"), [row.model_dump(mode="json") for row in rows]],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


class AdvisoryService:
    def __init__(
        self,
        store: AdvisoryStore,
        client: httpx.AsyncClient,
        *,
        provider: MarketDataProvider | None = None,
        clock: Callable[[], datetime] = utcnow,
        calendar_reader: Callable[[str, datetime], EconomicCalendar | None] | None = None,
        event_policy: EventRiskPolicy | None = None,
        selection_policy: MarketSelectionPolicy | None = None,
        research_reader: Callable[[str, datetime], CandidateEvidence | None] | None = None,
        risk_inputs_reader: (
            Callable[[str, str, StructuralSetup, datetime], RiskInputs | None] | None
        ) = None,
        evaluation_policy: EvaluationPolicy | None = None,
        policy_evidence_reader: (
            Callable[[str, str, StructuralSetup, datetime], EvaluationEvidence | None] | None
        ) = None,
        account_roles_required: bool = True,
        strategy_registry_required: bool = True,
    ) -> None:
        self.store, self.client = store, client
        self.markets = PublicMarkets(client)
        self.provider: MarketDataProvider = (
            provider if provider is not None else AdvisoryMarketData(self.markets, store)
        )
        if self.provider.mode not in {"current", "replay"}:
            raise ValueError("Unknown market-data provider mode")
        self.clock = clock
        # Server-owned policy and reported calendar evidence, never AI text.
        self.calendar_reader = calendar_reader
        self.research_reader = research_reader
        self.risk_inputs_reader = risk_inputs_reader
        self.evaluation_policy = evaluation_policy
        self.policy_evidence_reader = policy_evidence_reader
        self.account_roles_required = account_roles_required
        self.strategy_registry_required = strategy_registry_required
        self.selection_policy = (
            MarketSelectionPolicy.model_validate(selection_policy.model_dump())
            if selection_policy is not None
            else None
        )
        self.event_policy = (
            EventRiskPolicy.model_validate(event_policy.model_dump())
            if event_policy is not None
            else None
        )
        self.lock = asyncio.Lock()
        self.cache: dict[tuple[str, str], tuple[float, Report]] = {}
        self.feeds = FeedCache()
        self.last_refresh = 0.0

    async def risk_decision(self, account_id: str, request: RiskRequest) -> RiskDecision:
        """Read one durable account; caller supplies structure, never a budget."""
        request = RiskRequest.model_validate(request.model_dump())
        async with asyncio.timeout(25):
            async with self.lock:
                profile, rows, account_plan, strategy_registry = await asyncio.to_thread(
                    self.store.risk_context, account_id
                )

                account_revision = journal_revision(profile, rows)
                selection = (
                    await asyncio.to_thread(self.store.selection, request.selection_id)
                    if request.selection_id
                    else None
                )
                cut = self.clock()
                policy_evidence = self.read_policy_evidence(
                    account_id, account_revision, request.setup, cut
                )
                inputs = None
                if self.risk_inputs_reader is not None:
                    try:
                        inputs = self.risk_inputs_reader(
                            account_id, account_revision, request.setup, cut
                        )
                    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
                        inputs = None
                if self.risk_inputs_reader is not None or self.policy_evidence_reader is not None:
                    # A source reader may overlap a journal update. Assess the
                    # final durable snapshot; old allowances/history then fail
                    # the exact account revision join rather than mixing state.
                    profile, rows, account_plan, strategy_registry = await asyncio.to_thread(
                        self.store.risk_context, account_id
                    )
                    account_revision = journal_revision(profile, rows)
                assessed_at = self.clock()
                status = evaluation_status(profile, rows, now=assessed_at)
                policy_assessment = None
                if self.evaluation_policy is not None:
                    policy_assessment = self.evaluation_policy.assess(
                        profile,
                        rows,
                        account_revision=account_revision,
                        evidence=policy_evidence,
                        now=assessed_at,
                    )
                    if isinstance(inputs, RiskInputs):
                        try:
                            inputs = RiskInputs.model_validate(inputs.model_dump(warnings=False))
                        except (ValueError, TypeError, AttributeError):
                            inputs = None
                    if isinstance(inputs, RiskInputs):
                        loss = None
                        if inputs.configuration is not None:
                            try:
                                loss = Decimal(
                                    risk_worksheet(
                                        RiskWorksheet(
                                            instrument_id=request.setup.instrument_id,
                                            account_value=Decimal(status["balance"]),
                                            risk_percent=inputs.configuration.risk_percent,
                                            entry=request.setup.entry,
                                            stop=request.setup.invalidation,
                                            fees_per_unit=inputs.configuration.round_trip_fees_per_contract_usd,
                                            slippage_points=inputs.configuration.slippage_ticks
                                            * CATALOG[request.setup.instrument_id].tick_size,
                                        )
                                    )["loss_per_unit"]
                                )
                            except (ValueError, ArithmeticError):
                                loss = None
                        allowance = self.evaluation_policy.allowance(
                            policy_assessment,
                            instrument_id=request.setup.instrument_id,
                            contract=request.setup.contract,
                            invalidation=request.setup.invalidation,
                            loss_per_contract=loss,
                        )
                        inputs = inputs.model_copy(
                            update={
                                "allowance": allowance,
                                "halted_at": inputs.halted_at or inputs.known_at,
                                "known_at": max(inputs.known_at, allowance.known_at),
                            }
                        )
                result = assess_risk(
                    request.setup,
                    selection,
                    rows[-1].account if rows else None,
                    account_id=account_id,
                    journal_equity=Decimal(status["balance"]),
                    journal_revision=account_revision,
                    journal_blocks=evaluation_risk_blocks(status),
                    inputs=inputs,
                    now=assessed_at,
                    evaluation_policy=policy_assessment,
                    account_plan=account_plan,
                    account_roles_required=self.account_roles_required,
                    strategy_registry=(
                        strategy_registry
                        if self.strategy_registry_required or strategy_registry.records
                        else None
                    ),
                    strategy_registry_required=self.strategy_registry_required,
                )
                await asyncio.to_thread(self.store.save_risk_decision, result)
                return result

    def read_policy_evidence(
        self, account_id: str, revision: str, setup: StructuralSetup, cut: datetime
    ) -> EvaluationEvidence | None:
        if self.policy_evidence_reader is None:
            return None
        try:
            return self.policy_evidence_reader(account_id, revision, setup, cut)
        except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
            return None

    async def policy_assessment(self, account_id: str, request: RiskRequest) -> PolicyAssessment:
        request = RiskRequest.model_validate(request.model_dump())
        if self.evaluation_policy is None:
            raise ValueError("No evaluation policy configured")
        async with asyncio.timeout(25):
            async with self.lock:
                profile, rows = await asyncio.to_thread(self.store.evaluation, account_id)
                evidence = self.read_policy_evidence(
                    account_id, journal_revision(profile, rows), request.setup, self.clock()
                )
                profile, rows = await asyncio.to_thread(self.store.evaluation, account_id)
                result = self.evaluation_policy.assess(
                    profile,
                    rows,
                    account_revision=journal_revision(profile, rows),
                    evidence=evidence,
                    now=self.clock(),
                )
                await asyncio.to_thread(self.store.save_policy_assessment, result)
                return result

    async def selection(self, interval: Interval = "15m") -> MarketSelection:
        """One serial guarded comparison; no report fanout or synthetic fallback."""
        async with asyncio.timeout(25):
            async with self.lock:
                if self.provider.mode not in {"current", "replay"}:
                    raise ValueError("Unknown market-data provider mode")
                replay = self.provider.mode == "replay"
                if not replay and time.monotonic() - self.last_refresh < 3:
                    raise ValueError("Wait a few seconds before comparing markets")
                self.last_refresh = time.monotonic()
                cut = self.clock()
                universe = (
                    self.selection_policy.universe
                    if self.selection_policy
                    else tuple(
                        root
                        for root, item in CATALOG.items()
                        if item.futures_spec and item.futures_spec.research_tier == 1
                    )
                )
                snapshots = {}
                evidence = {}
                calendars = {}
                for root in universe:
                    query = MarketDataQuery(instrument_id=root, interval=interval, as_of=cut)
                    try:
                        snapshots[root] = bounded_snapshot(await self.provider.read(query), query)
                    except (httpx.HTTPError, ValueError, TypeError, KeyError, AttributeError):
                        snapshots[root] = None
                    try:
                        evidence[root] = (
                            self.research_reader(root, query.as_of)
                            if self.research_reader
                            else None
                        )
                    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
                        evidence[root] = None
                    try:
                        calendars[root] = (
                            self.calendar_reader(root, query.as_of)
                            if self.calendar_reader
                            else None
                        )
                    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
                        calendars[root] = None
                result = select_markets(
                    snapshots,
                    evidence,
                    calendars,
                    interval=interval,
                    now=cut if replay else self.clock(),
                    mode="replay" if replay else "current",
                    policy=self.selection_policy,
                    event_policy=self.event_policy,
                )
                await asyncio.to_thread(self.store.save_selection, result)
                return result

    async def report(
        self, instrument_id: str, interval: Interval, *, contract: str | None = None
    ) -> Report:
        if instrument_id not in CATALOG:
            raise ValueError("Unknown instrument")
        key = (instrument_id, interval)
        async with asyncio.timeout(25):
            async with self.lock:
                query = MarketDataQuery(
                    instrument_id=instrument_id,
                    interval=interval,
                    contract=contract,
                    as_of=self.clock(),
                )
                if self.provider.mode not in {"current", "replay"}:
                    raise ValueError("Unknown market-data provider mode")
                replay = self.provider.mode == "replay"
                calendar = None
                calendar_observations: list[str] = []
                if self.calendar_reader is not None:
                    try:
                        calendar = self.calendar_reader(instrument_id, query.as_of)
                    except (httpx.HTTPError, OSError, ValueError, TypeError, KeyError):
                        calendar_observations.append(
                            "Economic calendar unavailable; event risk remains unknown."
                        )
                cache_allowed = not replay and contract is None
                cached = self.cache.get(key)
                if cache_allowed and cached and time.monotonic() - cached[0] < 60:
                    # Calendar acquisition may cross a blackout/freshness boundary.
                    assessment_at = (
                        self.clock() if self.calendar_reader is not None else query.as_of
                    )
                    health = assess_market_data(
                        cached[1].market, instrument_id, interval, now=assessment_at
                    )
                    event_risk = assess_event_risk(
                        calendar, self.event_policy, instrument_id, now=assessment_at
                    )
                    if (
                        health.state == "HEALTHY"
                        and event_risk.state == cached[1].event_risk.state
                        and event_risk.reasons == cached[1].event_risk.reasons
                        and event_risk.calendar == cached[1].event_risk.calendar
                        and event_risk.policy == cached[1].event_risk.policy
                    ):
                        return Report.model_validate(cached[1].model_dump())
                    # Reassess cached evidence before rate limiting. It cannot
                    # remain ready across a freshness/heartbeat boundary.
                    result = build_report(
                        instrument_id,
                        interval,
                        cached[1].market,
                        [],
                        calendar_observations,
                        now=assessment_at,
                        calendar=calendar,
                        event_policy=self.event_policy,
                    )
                    await asyncio.to_thread(self.store.save_report, result)
                    self.cache[key] = (cached[0], Report.model_validate(result.model_dump()))
                    return result
                # Bounded per-process refresh budget; no parallel report fanout.
                if not replay and time.monotonic() - self.last_refresh < 3:
                    raise ValueError("Wait a few seconds before refreshing another market")
                self.last_refresh = time.monotonic()
                instrument = CATALOG[instrument_id]
                observations: list[str] = list(calendar_observations)
                market = None
                try:
                    market = bounded_snapshot(await self.provider.read(query), query)
                    if market is not None and (market.data_mode == "replay") != replay:
                        raise ValueError("Provider mode and snapshot provenance disagree")
                except (httpx.HTTPError, ValueError, KeyError, TypeError):
                    market = None
                    observations.append(
                        "مصدر الأسعار غير متاح أو غير صالح؛ لا توجد أسعار بديلة مصطنعة."
                    )
                news: list[News] = []
                context = []
                if not replay:
                    watchlist = await asyncio.to_thread(self.store.watchlist)
                    news, errors = await headlines(
                        self.client, instrument_id, watchlist.interests, self.feeds
                    )
                    observations.extend(errors)
                    context = await asyncio.to_thread(self.store.intelligence)
                decision_at = query.as_of if replay else self.clock()
                news = [item for item in news if item.published_at <= decision_at]
                result = build_report(
                    instrument_id,
                    interval,
                    market,
                    news,
                    observations,
                    now=decision_at,
                    calendar=calendar,
                    event_policy=self.event_policy,
                )
                result.agent_context = [
                    c
                    for c in context
                    if 0
                    <= (decision_at - datetime.fromisoformat(c["timestamp"])).total_seconds()
                    <= 3600
                    and relevant(c, instrument.symbol)
                ]
                await asyncio.to_thread(self.store.save_report, result)
                if cache_allowed:
                    self.cache[key] = (time.monotonic(), Report.model_validate(result.model_dump()))
                return result
