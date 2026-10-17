"""Source-verified mission map; never agent runtime or strategy qualification evidence."""

import hashlib
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from core.advisory.briefing import AGENT_TOPICS
from core.advisory.models import Strict, UTCDateTime, utcnow

_ROOT = Path(__file__).resolve().parents[3]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class CapabilityDefinition(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    id: str
    source_file: str
    advisory_role: str
    required_inputs: tuple[str, ...] = Field(min_length=1, max_length=10)
    planned_output: str
    acceptance_criteria: tuple[str, ...] = Field(min_length=2, max_length=10)
    adaptation: Literal["PLANNED", "CONTEXT_ONLY", "SUPPORT_ONLY", "EXCLUDED"]
    context_topic: str | None = None
    exclusion_reason: str | None = None
    qualified_signal: Literal[False] = False

    @model_validator(mode="after")
    def exclusions(self) -> Self:
        if (self.adaptation == "EXCLUDED") != bool(self.exclusion_reason):
            raise ValueError("Excluded capabilities require an explicit reason")
        if (self.adaptation == "CONTEXT_ONLY") != (self.context_topic is not None):
            raise ValueError("Context-only capabilities require their existing read-only topic")
        if self.context_topic is not None and self.context_topic not in AGENT_TOPICS:
            raise ValueError("Unsupported advisory context topic")
        return self


# Roles are a migration plan, not a claim that these agents ran or were adapted.
_DEFINITION_DATA = (
    {
        "id": "base_agent",
        "source_file": "src/agents/base_agent.py",
        "advisory_role": "Shared lifecycle support; never report analysis by itself",
        "required_inputs": ("Bounded lifecycle and task ownership", "Advisory-only permissions"),
        "planned_output": "Reusable scheduling and cancellation mechanics",
        "acceptance_criteria": (
            "No execution-capable imports in extracted advisory helpers",
            "Bounded cancellation and cleanup tested",
        ),
        "adaptation": "SUPPORT_ONLY",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "cio_agent",
        "source_file": "src/agents/tier1_executive/cio_agent.py",
        "advisory_role": "Explain the evidence-led report and disagreements",
        "required_inputs": ("Verified deterministic results", "Attributed news and analysis"),
        "planned_output": "Human-readable synthesis with cited gaps",
        "acceptance_criteria": (
            "No invented prices or confidence",
            "Cannot override deterministic denial",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "risk_governor",
        "source_file": "src/agents/tier1_executive/risk_governor.py",
        "advisory_role": "Review account and scenario risk",
        "required_inputs": (
            "Fresh account/exposure revisions",
            "Personal and separately verified firm policy",
        ),
        "planned_output": "Risk constraints and reasons to abstain",
        "acceptance_criteria": (
            "Same deterministic financial calculations",
            "No halt/cancel/order side effects",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "proposal_approver",
        "source_file": "src/agents/tier1_executive/proposal_approver.py",
        "advisory_role": "Qualify an advisory scenario for human review",
        "required_inputs": ("Data and strategy qualification", "Deterministic risk verdict"),
        "planned_output": "Review verdict with explicit exclusions",
        "acceptance_criteria": (
            "Missing evidence cannot qualify a scenario",
            "No approval published onto execution topics",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "market_data_hub",
        "source_file": "src/agents/tier2_intelligence/market_data_hub.py",
        "advisory_role": "Qualify actual-contract market snapshots",
        "required_inputs": (
            "Permitted source and contract metadata",
            "Source and availability clocks",
        ),
        "planned_output": "Completed bars and explicit quality gaps",
        "acceptance_criteria": (
            "No fabricated OHLCV or quotes",
            "Gaps, corrections and incomplete bars tested",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "paper_market_feed",
        "source_file": "src/agents/tier2_intelligence/paper_market_feed.py",
        "advisory_role": "Supply labelled mechanical test inputs only",
        "required_inputs": ("Captured synthetic tape", "Explicit test configuration"),
        "planned_output": "Synthetic fixtures excluded from market qualification",
        "acceptance_criteria": (
            "Synthetic labels survive replay",
            "No trading-edge or passing claim",
        ),
        "adaptation": "SUPPORT_ONLY",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "price_publisher",
        "source_file": "src/agents/tier2_intelligence/price_publisher.py",
        "advisory_role": "Distribute a captured source snapshot",
        "required_inputs": ("Qualified snapshot", "Original source timestamp"),
        "planned_output": "Consistent prices across report readers",
        "acceptance_criteria": (
            "Fetching context never renews price time",
            "No parallel per-panel price truth",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "news_analyst",
        "source_file": "src/agents/tier2_intelligence/news_analyst.py",
        "advisory_role": "Attribute relevant headlines and their uncertainty",
        "required_inputs": ("Licensed/public news sources", "Published and known-at clocks"),
        "planned_output": "Related news context with coverage gaps",
        "acceptance_criteria": (
            "Deduplication and causal clocks verified",
            "Reported context cannot become a qualified signal",
        ),
        "adaptation": "CONTEXT_ONLY",
        "context_topic": "news.tagged",
        "exclusion_reason": None,
    },
    {
        "id": "sentiment_analyst",
        "source_file": "src/agents/tier2_intelligence/sentiment_analyst.py",
        "advisory_role": "Provide attributed sentiment context",
        "required_inputs": ("Relevant bounded observations", "Source and availability time"),
        "planned_output": "Sentiment context with limitations",
        "acceptance_criteria": (
            "Stale/unrelated context rejected",
            "No success probability inferred from sentiment",
        ),
        "adaptation": "CONTEXT_ONLY",
        "context_topic": "sentiment.scored",
        "exclusion_reason": None,
    },
    {
        "id": "macro_economist",
        "source_file": "src/agents/tier2_intelligence/macro_economist.py",
        "advisory_role": "Explain macro context and scheduled-event risk",
        "required_inputs": (
            "Official calendars and releases",
            "Known-at clocks and contract relationships",
        ),
        "planned_output": "Macro regime and coverage/unknown-event warnings",
        "acceptance_criteria": (
            "Unavailable coverage is not absence of risk",
            "No directional certainty from an event label",
        ),
        "adaptation": "CONTEXT_ONLY",
        "context_topic": "macro.regime",
        "exclusion_reason": None,
    },
    {
        "id": "geopolitical_watcher",
        "source_file": "src/agents/tier2_intelligence/geopolitical_watcher.py",
        "advisory_role": "Explain relevant geopolitical event risk",
        "required_inputs": ("Attributed events", "Explicit MES/MNQ relevance"),
        "planned_output": "Event-risk context with uncertainty",
        "acceptance_criteria": (
            "Causal publication/availability checked",
            "No price target derived from headlines alone",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "onchain_sleuth",
        "source_file": "src/agents/tier2_intelligence/onchain_sleuth.py",
        "advisory_role": "No default role for MES/MNQ on-chain analysis",
        "required_inputs": ("A separately justified cross-market hypothesis",),
        "planned_output": "No advisory output in the current MES/MNQ plan",
        "acceptance_criteria": (
            "Remain disabled in this workflow",
            "No crypto data substituted for futures evidence",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "On-chain signals do not establish MES/MNQ market evidence; no approved "
        "hypothesis.",
    },
    {
        "id": "technical_analyst",
        "source_file": "src/agents/tier3_quant/technical_analyst.py",
        "advisory_role": "Calculate reproducible multi-timeframe features",
        "required_inputs": (
            "Sufficient completed same-contract OHLCV bars",
            "Indicator definitions and warmup",
        ),
        "planned_output": "Trend, levels and technical disagreements",
        "acceptance_criteria": (
            "No indicator calculated from a last-price screenshot alone",
            "Public replay and minimum-history tests",
        ),
        "adaptation": "CONTEXT_ONLY",
        "context_topic": "indicators.computed",
        "exclusion_reason": None,
    },
    {
        "id": "volatility_forecaster",
        "source_file": "src/agents/tier3_quant/volatility_forecaster.py",
        "advisory_role": "Estimate volatility with model limitations",
        "required_inputs": ("Sufficient qualified return history", "Pinned model/configuration"),
        "planned_output": "Volatility estimate with uncertainty",
        "acceptance_criteria": (
            "Chronological validation and calibration",
            "Report model failure and insufficient history",
        ),
        "adaptation": "CONTEXT_ONLY",
        "context_topic": "volatility.forecast",
        "exclusion_reason": None,
    },
    {
        "id": "correlation_engine",
        "source_file": "src/agents/tier3_quant/correlation_engine.py",
        "advisory_role": "Assess joint exposure and correlated scenarios",
        "required_inputs": ("Aligned actual-contract series", "Clock and missingness rules"),
        "planned_output": "Exposure relationships with sample limits",
        "acceptance_criteria": (
            "No correlation from unmatched snapshots",
            "Out-of-sample stability and missingness tested",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "trend_follower",
        "source_file": "src/agents/tier4_strategies/trend_follower.py",
        "advisory_role": "Trend-continuation scenarios",
        "required_inputs": (
            "Completed bars and trend warmup",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "mean_reversion",
        "source_file": "src/agents/tier4_strategies/mean_reversion.py",
        "advisory_role": "Mean-reversion scenarios",
        "required_inputs": (
            "Completed bars and range/regime evidence",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "momentum",
        "source_file": "src/agents/tier4_strategies/momentum.py",
        "advisory_role": "Momentum scenarios",
        "required_inputs": (
            "Completed bars and momentum/volume history",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "stat_arb",
        "source_file": "src/agents/tier4_strategies/stat_arb.py",
        "advisory_role": "Relative-value scenarios only if justified for the selected instruments",
        "required_inputs": (
            "Aligned series and stable relationship evidence",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "breakout_hunter",
        "source_file": "src/agents/tier4_strategies/breakout_hunter.py",
        "advisory_role": "Range-breakout scenarios using the existing deterministic kernel",
        "required_inputs": (
            "Completed range/volume history and contract identity",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "macro_rotator",
        "source_file": "src/agents/tier4_strategies/macro_rotator.py",
        "advisory_role": "Macro-conditioned futures scenarios only where instrument mapping is justified",
        "required_inputs": (
            "Causal macro evidence and qualified futures history",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "ml_predictor",
        "source_file": "src/agents/tier4_strategies/ml_predictor.py",
        "advisory_role": "Model-based scenarios only after futures-specific qualification",
        "required_inputs": (
            "Qualified futures training/validation data and pinned model identity",
            "Costs, parameters and untouched chronological validation",
        ),
        "planned_output": "Conditional entry, invalidation, stop/target and abstention",
        "acceptance_criteria": (
            "Preserve numerical behavior while extracting reusable analysis",
            "Qualify 5m/15m separately; existing daily/crypto results do not " "transfer",
            "No order/proposal publishing from the advisory interface",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "arb_cross_exchange",
        "source_file": "src/agents/tier4_strategies/arb_cross_exchange.py",
        "advisory_role": "No default cross-exchange execution role for MES/MNQ",
        "required_inputs": ("A separately approved futures basis hypothesis",),
        "planned_output": "No advisory output in the current plan",
        "acceptance_criteria": (
            "No spot prices substituted for futures",
            "No execution path enabled",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "Crypto cross-exchange execution does not fit the current actual-contract "
        "MES/MNQ report.",
    },
    {
        "id": "order_router",
        "source_file": "src/agents/tier5_execution/order_router.py",
        "advisory_role": "Review execution-style assumptions without routing an order",
        "required_inputs": (
            "Manual venue/instrument assumptions",
            "Extracted computation without broker dependencies",
        ),
        "planned_output": "Advisory execution-assumption explanation",
        "acceptance_criteria": (
            "No create/modify/cancel/liquidate calls reachable",
            "Financial arithmetic and existing risk caps preserved",
            "Insufficient costs/account/stop evidence blocks a positive size",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "slippage_minimizer",
        "source_file": "src/agents/tier5_execution/slippage_minimizer.py",
        "advisory_role": "Study plausible execution friction without splitting orders",
        "required_inputs": (
            "Qualified bid/ask or conservative declared fill model",
            "Extracted computation without broker dependencies",
        ),
        "planned_output": "Slippage sensitivity and model limitations",
        "acceptance_criteria": (
            "No create/modify/cancel/liquidate calls reachable",
            "Financial arithmetic and existing risk caps preserved",
            "Insufficient costs/account/stop evidence blocks a positive size",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "hedge_manager",
        "source_file": "src/agents/tier5_execution/hedge_manager.py",
        "advisory_role": "Explain correlated exposure without creating hedges",
        "required_inputs": (
            "Account positions and justified relationships",
            "Extracted computation without broker dependencies",
        ),
        "planned_output": "Exposure alternatives for human review",
        "acceptance_criteria": (
            "No create/modify/cancel/liquidate calls reachable",
            "Financial arithmetic and existing risk caps preserved",
            "Insufficient costs/account/stop evidence blocks a positive size",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "fee_optimizer",
        "source_file": "src/agents/tier5_execution/fee_optimizer.py",
        "advisory_role": "Compare declared costs without modifying orders",
        "required_inputs": (
            "Verified fee schedule and execution assumptions",
            "Extracted computation without broker dependencies",
        ),
        "planned_output": "Fee comparison and missing-cost warnings",
        "acceptance_criteria": (
            "No create/modify/cancel/liquidate calls reachable",
            "Financial arithmetic and existing risk caps preserved",
            "Insufficient costs/account/stop evidence blocks a positive size",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "liquidation_guard",
        "source_file": "src/agents/tier5_execution/liquidation_guard.py",
        "advisory_role": "Warn about account breach proximity without liquidation",
        "required_inputs": (
            "Fresh equity, exposure and validated limits",
            "Extracted computation without broker dependencies",
        ),
        "planned_output": "Distance to limits and reasons to abstain",
        "acceptance_criteria": (
            "No create/modify/cancel/liquidate calls reachable",
            "Financial arithmetic and existing risk caps preserved",
            "Insufficient costs/account/stop evidence blocks a positive size",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "position_sizer",
        "source_file": "src/agents/tier5_execution/position_sizer.py",
        "advisory_role": "Provide deterministic advisory sizing",
        "required_inputs": (
            "Entry/stop, tick value, costs and current account/exposure",
            "Extracted computation without broker dependencies",
        ),
        "planned_output": "Risk-bounded size for human consideration",
        "acceptance_criteria": (
            "No create/modify/cancel/liquidate calls reachable",
            "Financial arithmetic and existing risk caps preserved",
            "Insufficient costs/account/stop evidence blocks a positive size",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "exchange_executor",
        "source_file": "src/agents/tier5_execution/exchange_executor.py",
        "advisory_role": "Broker execution is excluded from the report workflow",
        "required_inputs": ("Human execution outside ALGHREST",),
        "planned_output": "No advisory execution output",
        "acceptance_criteria": (
            "No broker adapter imports or mutations",
            "Execution remains disabled",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "The human executes externally; no order/cancel/liquidation path is part of "
        "this product.",
    },
    {
        "id": "yield_farmer",
        "source_file": "src/agents/tier6_defi/yield_farmer.py",
        "advisory_role": "DeFi capability excluded from the MES/MNQ report",
        "required_inputs": ("A different separately authorized product scope",),
        "planned_output": "No advisory output",
        "acceptance_criteria": (
            "Skeleton/mock implementations remain disabled",
            "No funds, bridge, smart-contract or swap calls",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "DeFi skeletons are unrelated to the current futures advisory mission and "
        "remain disabled.",
    },
    {
        "id": "dex_arbitrageur",
        "source_file": "src/agents/tier6_defi/dex_arbitrageur.py",
        "advisory_role": "DeFi capability excluded from the MES/MNQ report",
        "required_inputs": ("A different separately authorized product scope",),
        "planned_output": "No advisory output",
        "acceptance_criteria": (
            "Skeleton/mock implementations remain disabled",
            "No funds, bridge, smart-contract or swap calls",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "DeFi skeletons are unrelated to the current futures advisory mission and "
        "remain disabled.",
    },
    {
        "id": "mev_hunter",
        "source_file": "src/agents/tier6_defi/mev_hunter.py",
        "advisory_role": "DeFi capability excluded from the MES/MNQ report",
        "required_inputs": ("A different separately authorized product scope",),
        "planned_output": "No advisory output",
        "acceptance_criteria": (
            "Skeleton/mock implementations remain disabled",
            "No funds, bridge, smart-contract or swap calls",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "DeFi skeletons are unrelated to the current futures advisory mission and "
        "remain disabled.",
    },
    {
        "id": "bridge_strategist",
        "source_file": "src/agents/tier6_defi/bridge_strategist.py",
        "advisory_role": "DeFi capability excluded from the MES/MNQ report",
        "required_inputs": ("A different separately authorized product scope",),
        "planned_output": "No advisory output",
        "acceptance_criteria": (
            "Skeleton/mock implementations remain disabled",
            "No funds, bridge, smart-contract or swap calls",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "DeFi skeletons are unrelated to the current futures advisory mission and "
        "remain disabled.",
    },
    {
        "id": "portfolio_tracker",
        "source_file": "src/agents/tier7_monitoring/portfolio_tracker.py",
        "advisory_role": "Summarize the manually reported evaluation account",
        "required_inputs": (
            "Current positions and account revisions",
            "Advisory-local evidence only",
        ),
        "planned_output": "Account exposure and performance context",
        "acceptance_criteria": (
            "No connection to trading-state writers",
            "Missing/stale/inconsistent evidence stays visible",
            "No readiness or performance percentage from engineering test counts",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "portfolio_accountant",
        "source_file": "src/agents/tier7_monitoring/portfolio_accountant.py",
        "advisory_role": "Reconcile advisory accounting observations",
        "required_inputs": (
            "Captured account facts, fills and costs",
            "Advisory-local evidence only",
        ),
        "planned_output": "Reconciled totals and unresolved differences",
        "acceptance_criteria": (
            "No connection to trading-state writers",
            "Missing/stale/inconsistent evidence stays visible",
            "No readiness or performance percentage from engineering test counts",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "alert_manager",
        "source_file": "src/agents/tier7_monitoring/alert_manager.py",
        "advisory_role": "Prepare actionable warnings for review",
        "required_inputs": (
            "Qualified report reasons and user preferences",
            "Advisory-local evidence only",
        ),
        "planned_output": "Local warnings; external sending needs separate authorization",
        "acceptance_criteria": (
            "No connection to trading-state writers",
            "Missing/stale/inconsistent evidence stays visible",
            "No readiness or performance percentage from engineering test counts",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "compliance_agent",
        "source_file": "src/agents/tier7_monitoring/compliance_agent.py",
        "advisory_role": "Check configured restrictions and trace reasons",
        "required_inputs": (
            "Personal rules and separately verified firm policies",
            "Advisory-local evidence only",
        ),
        "planned_output": "Compliance status and unverifiable rules",
        "acceptance_criteria": (
            "No connection to trading-state writers",
            "Missing/stale/inconsistent evidence stays visible",
            "No readiness or performance percentage from engineering test counts",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "auditor_agent",
        "source_file": "src/agents/tier7_monitoring/auditor_agent.py",
        "advisory_role": "Trace report provenance and verification",
        "required_inputs": (
            "Captured inputs, revisions and code identities",
            "Advisory-local evidence only",
        ),
        "planned_output": "Reproducible audit record",
        "acceptance_criteria": (
            "No connection to trading-state writers",
            "Missing/stale/inconsistent evidence stays visible",
            "No readiness or performance percentage from engineering test counts",
        ),
        "adaptation": "PLANNED",
        "context_topic": None,
        "exclusion_reason": None,
    },
    {
        "id": "copy_trading_channel",
        "source_file": "src/agents/tier7_monitoring/copy_trading_channel.py",
        "advisory_role": "Trade copying excluded from the report workflow",
        "required_inputs": ("Human review of a report",),
        "planned_output": "No copying or external publishing",
        "acceptance_criteria": (
            "No broker or Telegram publication reachable",
            "Report delivery requires separately authorized channels",
        ),
        "adaptation": "EXCLUDED",
        "context_topic": None,
        "exclusion_reason": "Advisory reports do not copy or execute trades.",
    },
)
DEFINITIONS = tuple(CapabilityDefinition.model_validate(row) for row in _DEFINITION_DATA)
_IMPLEMENTATION_FILES = (
    "src/core/advisory/capability_registry.py",
    "src/core/advisory/models.py",
    "src/core/advisory/briefing.py",
    "src/api/routes/advisory_capabilities.py",
    "src/api/advisor.py",
    "src/api/security.py",
    "src/connectors/advisory/intelligence.py",
)


def _source_hashes() -> dict[str, str]:
    declared = {item.source_file for item in DEFINITIONS}
    actual = {
        str(path.relative_to(_ROOT))
        for path in (_ROOT / "src/agents").rglob("*.py")
        if path.name != "__init__.py"
    }
    if declared != actual or len({item.id for item in DEFINITIONS}) != len(DEFINITIONS):
        raise ValueError("Agent inventory differs from the declared mission map")
    if {item.context_topic for item in DEFINITIONS if item.context_topic} != set(AGENT_TOPICS):
        raise ValueError("Advisory context map differs from its existing interface")
    hashes = {}
    for name in sorted(declared | set(_IMPLEMENTATION_FILES)):
        path = _ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(_ROOT.resolve()):
            raise ValueError("Capability source must remain inside the project")
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


class CapabilityRegistry(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal["advisory-capability-registry-v1"] = "advisory-capability-registry-v1"
    mission: Literal["MES/MNQ evidence-led reports for human trading decisions"] = (
        "MES/MNQ evidence-led reports for human trading decisions"
    )
    generated_at: UTCDateTime
    definitions: tuple[CapabilityDefinition, ...]
    source_hashes: dict[str, Digest]
    identity_kind: Literal["CODE_AND_STATIC_CATALOG_ONLY"] = "CODE_AND_STATIC_CATALOG_ONLY"
    runtime_status: Literal["NOT_OBSERVED"] = "NOT_OBSERVED"
    market_qualification: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    all_agents_integrated: Literal[False] = False
    passing_probability: Literal["UNKNOWN"] = "UNKNOWN"
    trade_permitted: Literal[False] = False
    execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def verify(self) -> Self:
        if self.generated_at > utcnow():
            raise ValueError("Future registry generation clock")
        if self.definitions != DEFINITIONS:
            raise ValueError("Capability definitions differ from the approved mission map")
        if self.source_hashes != _source_hashes():
            raise ValueError("Capability source hashes differ; preserve earlier evidence")
        return self


def capability_registry() -> CapabilityRegistry:
    """Read current source identities each request, without importing or starting agents."""
    return CapabilityRegistry(
        generated_at=utcnow(), definitions=DEFINITIONS, source_hashes=_source_hashes()
    )


def verify_capability_registry(value: CapabilityRegistry) -> CapabilityRegistry:
    return CapabilityRegistry.model_validate(value.model_dump())
