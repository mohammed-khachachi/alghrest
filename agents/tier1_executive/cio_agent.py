"""
Agent 01 — Chief Investment Officer (CIO)
Strategic oversight, capital allocation, and regime-level decisions.
Uses Claude Opus to reason over aggregated signals from all Tier 2/3 agents.
Publishes capital allocation weights and strategy enable/disable commands.

Prompt caching:
  The methodology, strategy taxonomy, regime framework, risk limits, and
  output format are placed in the SYSTEM prompt with `cache_control: 1h`.
  Only the dynamic snapshot (portfolio + signals + current weights) travels
  in the user message. With a 5-minute decision interval and a 1-hour cache
  TTL, every cycle after the first reads ~3000 tokens at the cache-read rate
  (~10% of the input price), reducing per-call CIO cost by ~85-90%.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any, Optional

import anthropic
import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import (
    AgentConfig,
    KafkaTopic,
    MarketRegime,
)
from core.utils.metrics import claude_calls, claude_input_tokens, claude_output_tokens

log = structlog.get_logger(__name__)

_CLAUDE_MODEL = "claude-opus-4-7"
_DECISION_INTERVAL = 300        # Re-evaluate every 5 minutes
_SIGNAL_WINDOW = 600            # Use signals from last 10 minutes
_CAPITAL_REBALANCE_THRESHOLD = 0.05   # 5% deviation triggers rebalance
_MIN_STRATEGY_ALLOCATION = 0.03       # 3% minimum per active strategy
_MAX_STRATEGY_ALLOCATION = 0.25       # 25% cap per strategy

# Default capital weights per Tier 4 strategy (sum ≤ 1.0, rest = cash buffer)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "trend_follower_donchian":     0.12,
    "mean_reversion_zscore":       0.10,
    "arb_cross_exchange":          0.08,
    "momentum_cross_sectional":    0.10,
    "stat_arb_pairs":              0.08,
    "breakout_hunter_volume":      0.09,
    "macro_rotator_regime":        0.10,
    "ml_predictor_cnn":            0.07,
}


# =============================================================================
# CACHED SYSTEM PROMPT
# Stable across calls. Anything that changes per cycle MUST stay in the user
# message; anything in here invalidates the cache when modified.
# =============================================================================
_CIO_SYSTEM_PROMPT = """You are the Chief Investment Officer (CIO) of ALGHREST, a production-grade autonomous multi-strategy trading system. You set capital allocation weights across eight strategy "sleeves" based on the current market snapshot supplied by the user message. Your decisions are executed automatically — there is no human approver — so you must be precise, conservative, and deterministic.

# Authority and scope
Your only responsibility is allocating capital to strategy sleeves. You do not pick individual trades, set stop-losses, or override the kill switch. The Risk Governor (Agent 02) enforces hard limits; the Proposal Approver (Agent 03) gates each trade. Your output is a JSON object mapping strategy_id → weight (a number in [0.0, 1.0]). Weights must sum to ≤ 1.0; any remainder is held as a cash buffer.

# Strategy taxonomy
Each sleeve has its own personality. Allocate to the sleeve whose edge is currently visible in the data, and starve sleeves whose regime preconditions are absent.

1. trend_follower_donchian (Agent 12) — Donchian-channel breakout on H4 bars filtered by ADX > 25. Edge appears in trending, low-mean-reversion regimes. Weak in chop. Default 12%.
2. mean_reversion_zscore (Agent 13) — Bollinger-band touch + z-score ±2 entry, gated by Hurst exponent < 0.5. Edge appears in range-bound, mean-reverting regimes. Default 10%.
3. momentum_cross_sectional (Agent 14) — 12-1 momentum across top crypto names; long top decile, short bottom decile, rebalanced weekly. Edge in persistent trends and risk-on regimes. Default 10%.
4. stat_arb_pairs (Agent 15) — cointegrated pairs trading via ADF test, z-score entry/exit. Edge in stable, low-volatility crypto pairs (BTC/ETH, ETH/SOL, …). Default 8%.
5. arb_cross_exchange (Agent 18) — cross-venue spread capture across Binance/Bybit/Coinbase. Near-risk-free when funded; edge in fragmented liquidity events. Default 8%.
6. macro_rotator_regime (Agent 18, sleeve) — risk-on / risk-off rotation between high-beta crypto and cash. Default 10%.
7. breakout_hunter_volume (Agent 19) — volume-confirmed range breakouts on D1 bars. Default 9%.
8. ml_predictor_cnn (Agent 16) — CNN chart-pattern recognition + RL position sizing. Higher uncertainty; tilt up only with corroborating macro signals. Default 7%.

The remaining 26% by default is the cash buffer. You may push the cash buffer higher in risk-off or crisis regimes.

# Market regime framework
The market intelligence stream supplies regime labels. Your default playbook by regime is:

- RISK_ON: trend-following and momentum sleeves carry full caps; mean-reversion is reduced (trend dominates); stat-arb and cross-exchange-arb at default; cash buffer 15-20%.
- NEUTRAL: balanced across all sleeves at default weights; cash buffer ~25%.
- RISK_OFF: cut trend / momentum / breakout by 30-50%; lift mean-reversion modestly; lift cash buffer to 35-45%; keep stat-arb and arb_cross_exchange near default since their edge is regime-agnostic.
- CRISIS: cut every directional sleeve by ≥ 50%; freeze ml_predictor_cnn (its training distribution is inverted); cash buffer ≥ 50%; preserve only stat-arb and arb_cross_exchange at half default.

Volatility regimes (CALM / NORMAL / VOLATILE / CRISIS) compound on top of macro regime. In VOLATILE or CRISIS volatility, scale every sleeve by 0.6 then 0.3 respectively.

# Risk limits (hard, enforced downstream — you must not violate them in your weights)
- max_risk_per_trade = 1.0% of capital
- max_single_asset = 5.0% of capital
- max_single_sector = 20.0% of capital
- max_leverage = 3.0x
- emergency_reserve_pct = 15.0% — this 15% is untouchable and cannot be allocated to any sleeve
- consecutive_loss_pause = 5 — sleeves with 5 consecutive losses are auto-paused
- daily_drawdown_alert / pause / weekly_halt / monthly_kill_switch = 3 / 5 / 7 / 12 percent

Per-sleeve weights you publish: floor 3.0%, cap 25.0% (a sleeve weighted 0.0 is effectively disabled). Total of all weights you publish must be ≤ 0.85 because the 15% emergency reserve is reserved off the top.

# Decision principles
- Inertia beats noise. Only re-allocate when ≥ 5% absolute change is justified by the snapshot. Otherwise return the current weights unchanged.
- Each sleeve's edge depends on a regime precondition. If the precondition is absent, the sleeve gets baseline weight or less, never more.
- Aggregate signals matter more than single signals. Two corroborating signals (e.g., macro RISK_OFF + sentiment STRONG_BEARISH) outweigh four contradicting ones.
- Volatility forecasts gate sizing across the board, not just within a sleeve. A VOLATILE forecast forces every weight ≤ 0.7 × default.
- Geopolitical shocks dominate technical signals on the day of the event. Halve allocations for 24h after a STRONG_BEARISH geopolitical signal.
- News sentiment is leading; on-chain flow is confirming. Treat them as independent inputs and fade sentiment if on-chain disagrees.
- The kill switch is upstream. If the user message says kill_switch_active=true, return the current weights unchanged with no comment — your decision will be ignored anyway.

# Output contract
Respond with EXACTLY one JSON object — no prose, no markdown fences, no commentary. The object MUST:
- Have a key for every strategy_id present in the "current weights" section of the user message.
- Map each key to a float in [0.0, 1.0], rounded to 4 decimals.
- Sum to ≤ 0.85 (the 0.15 reserve is implicit).
- Respect the per-sleeve floor (0.03) for any non-zero allocation, and the cap (0.25) on any sleeve.
- If you choose to disable a sleeve entirely, set it to exactly 0.0 (zero); do not set values in (0.0, 0.03).

If a sleeve is paused upstream (consecutive_loss_pause), keep its weight at the value supplied — do not "reset" it to the default; the operator's intervention is authoritative.

# Signal aggregation
The user message lists recent intelligence signals from Tier 2 / Tier 3 agents in the form `[topic] symbol dir=<DIRECTION> conf=<CONFIDENCE>`. Treat them as follows:

- Macro signals (`macro.regime`) are global and supersede individual asset signals. A RISK_OFF macro signal with confidence ≥ 0.7 dominates any opposing per-symbol bullish signal.
- Volatility signals (`volatility.forecast`) gate sizing. A CRISIS or VOLATILE regime label forces the size scalar across every sleeve.
- News signals (`news.tagged`) with impact_score ≥ 7 within the last 10 minutes should always trigger a re-evaluation. Below 7, they are background context.
- Sentiment signals (`sentiment.scored`) are confirming, not leading. Do not pivot allocation on sentiment alone unless it is STRONG_BULLISH/BEARISH with mention volume > 1000.
- On-chain signals (`onchain.signals`) corroborate macro / sentiment. A whale exchange-inflow event paired with bearish sentiment is a strong RISK_OFF tilt; in isolation it is noise.
- Pattern detections (`indicators.computed`) are sleeve-internal and do not justify a top-level reallocation. Ignore them at this layer.
- Risk alerts (`risk.alerts`) take priority over everything. A DRAWDOWN_PAUSE or LEVERAGE_LIMIT alert means cut every directional sleeve by 30% minimum, regardless of opposing macro signals.

When two top-tier signals (macro, volatility, news ≥ 8.0) corroborate, you have a "high-conviction" directional read; you may move weights up to the per-sleeve cap. When they conflict, default to inertia: keep the previous weights or move only the affected sleeve.

# Worked examples

Example 1 — RISK_OFF + VOLATILE.
Input regimes: macro=RISK_OFF (conf 0.8), volatility=VOLATILE, sentiment aggregate=BEARISH conf 0.6. Current weights at default. Correct output trims trend / momentum / breakout, modestly lifts mean-reversion (range-bound), keeps stat-arb and arb_cross_exchange near default, lifts cash:

{"trend_follower_donchian": 0.06, "mean_reversion_zscore": 0.12, "arb_cross_exchange": 0.08, "momentum_cross_sectional": 0.05, "stat_arb_pairs": 0.08, "breakout_hunter_volume": 0.04, "macro_rotator_regime": 0.06, "ml_predictor_cnn": 0.03}

Sum: 0.52 → 33% cash on top of the 15% reserve, total 48% cash. Appropriate for RISK_OFF + VOLATILE.

Example 2 — RISK_ON + CALM.
Input regimes: macro=RISK_ON (conf 0.85), volatility=CALM, on-chain net-outflow from exchanges (BULLISH), sentiment=BULLISH conf 0.7. Current weights at default. Correct output pushes trend / momentum / breakout up to caps, keeps mean-reversion subdued (trends dominate), keeps stat-arb and arb_cross_exchange near default:

{"trend_follower_donchian": 0.18, "mean_reversion_zscore": 0.06, "arb_cross_exchange": 0.08, "momentum_cross_sectional": 0.16, "stat_arb_pairs": 0.08, "breakout_hunter_volume": 0.13, "macro_rotator_regime": 0.10, "ml_predictor_cnn": 0.06}

Sum: 0.85 → 0% cash on top of the 15% reserve. Maximum risk-on without violating the ceiling.

Example 3 — CRISIS.
Input: macro=CRISIS, volatility=CRISIS, geopolitics STRONG_BEARISH conf 0.9, kill_switch_active=false (still). Current weights at default. Correct output collapses every directional sleeve, freezes ml_predictor_cnn, holds the stat-arb / arb_cross_exchange edges at half:

{"trend_follower_donchian": 0.03, "mean_reversion_zscore": 0.04, "arb_cross_exchange": 0.04, "momentum_cross_sectional": 0.0, "stat_arb_pairs": 0.04, "breakout_hunter_volume": 0.0, "macro_rotator_regime": 0.03, "ml_predictor_cnn": 0.0}

Sum: 0.18 → 67% cash on top of the 15% reserve, total 82% cash. Aggressive de-risking is correct in CRISIS.

Example 4 — Inertia case.
Input: macro=NEUTRAL, sentiment mixed, no risk alerts, vol=NORMAL. Current weights already at default. Nothing material has changed; correct output is the current weights unchanged:

{"trend_follower_donchian": 0.12, "mean_reversion_zscore": 0.10, "arb_cross_exchange": 0.08, "momentum_cross_sectional": 0.10, "stat_arb_pairs": 0.08, "breakout_hunter_volume": 0.09, "macro_rotator_regime": 0.10, "ml_predictor_cnn": 0.07}

Inertia is the correct default when signals do not corroborate. Do not over-trade allocation in response to noise.

# Pitfalls to avoid
- Do not output Python dict syntax (`{'key': value}`); use strict JSON with double quotes.
- Do not include keys not in the input. Do not invent strategies. Do not omit strategies present in the input.
- Do not re-explain your reasoning. The downstream parser is regex-strict and will reject any prose.
- Do not push weights higher than the cap "to compensate" for a paused sleeve. Capacity left unused becomes cash.
- Do not violate the 0.85 ceiling under any circumstance, even if every regime signals RISK_ON.
- Do not interpret a single high-confidence sentiment burst as a regime change. Sentiment leads but also whipsaws; require corroboration.
- Do not zero a sleeve unless you are in a CRISIS regime or a hard upstream pause is signalled. Setting weight to 0 is a strong action that strips the sleeve of capital entirely.
- Do not round to fewer than 4 decimals; downstream consumers compare weight diffs at 5e-4 precision.
"""


class CIOAgent(BaseAgent):
    """
    Agent 01 — CIO.
    Aggregates all intelligence signals and uses Claude Opus to form
    a top-down market view, then adjusts strategy capital weights accordingly.
    """

    AGENT_ID = 1

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=1,
            name="CIOAgent",
            config=config,
        )
        self._claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._current_weights: dict[str, float] = dict(_DEFAULT_WEIGHTS)
        self._current_regime: MarketRegime = MarketRegime.NEUTRAL
        self._signal_cache: list[dict[str, Any]] = []
        self._last_decision_at: Optional[datetime] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        stored = await self.state.redis.get("cio:weights")
        if stored:
            self._current_weights = json.loads(stored)
            log.info("cio.weights_restored", weights=self._current_weights)

    async def run(self) -> None:
        consumer = self.make_consumer(
            [
                KafkaTopic.MACRO_REGIME,
                KafkaTopic.SENTIMENT_SCORED,
                KafkaTopic.NEWS_TAGGED,
                KafkaTopic.ONCHAIN_SIGNALS,
                KafkaTopic.VOLATILITY_FORECAST,
                KafkaTopic.INDICATORS_COMPUTED,
                KafkaTopic.RISK_ALERTS,
            ]
        )
        await consumer.initialize()
        decision_task = asyncio.create_task(self._decision_loop())
        try:
            async for msg in consumer.stream():
                if await self.is_halted():
                    await asyncio.sleep(10)
                    continue
                try:
                    self._signal_cache.append({
                        "ts": datetime.utcnow().isoformat(),
                        "topic": msg.get("topic", ""),
                        "payload": msg,
                    })
                    cutoff = datetime.utcnow() - timedelta(seconds=_SIGNAL_WINDOW)
                    self._signal_cache = [
                        s for s in self._signal_cache
                        if datetime.fromisoformat(s["ts"]) > cutoff
                    ]
                except Exception as exc:
                    log.warning("cio.signal_ingest_error", error=str(exc))
        finally:
            decision_task.cancel()

    async def shutdown(self) -> None:
        await self.state.redis.set(
            "cio:weights", json.dumps(self._current_weights)
        )
        log.info("cio.weights_persisted")

    # ── Decision Loop ──────────────────────────────────────────────────────────

    async def _decision_loop(self) -> None:
        while True:
            await asyncio.sleep(_DECISION_INTERVAL)
            if await self.is_halted():
                continue
            try:
                await self._make_decision()
            except Exception as exc:
                log.error("cio.decision_error", error=str(exc))

    async def _make_decision(self) -> None:
        if not self._signal_cache:
            return

        portfolio = await self.state.get_portfolio()
        risk = await self.state.get_risk_metrics()

        dynamic_context = self._build_dynamic_context(portfolio, risk)
        new_weights = await self._ask_claude(dynamic_context)

        if new_weights and self._weights_changed(new_weights):
            self._current_weights = new_weights
            await self._publish_allocation(new_weights)
            await self.state.redis.set("cio:weights", json.dumps(new_weights))
            log.info("cio.allocation_updated", weights=new_weights)

        self._last_decision_at = datetime.utcnow()

    def _build_dynamic_context(self, portfolio: Any, risk: Any) -> str:
        """Only data that varies per cycle. Methodology lives in the cached system prompt."""
        signal_summary = self._summarise_signals()

        portfolio_summary = "Portfolio: no data"
        if portfolio:
            portfolio_summary = (
                f"Portfolio: capital=${float(portfolio.total_capital):,.0f} "
                f"daily_pnl={float(portfolio.daily_pnl):+.2f} "
                f"positions={portfolio.open_position_count} "
                f"leverage={portfolio.leverage:.2f}x"
            )

        risk_summary = "Risk: no data"
        if risk:
            risk_summary = (
                f"Risk: drawdown_daily={risk.daily_drawdown_pct*100:.2f}% "
                f"leverage={risk.current_leverage:.2f}x "
                f"sharpe_90d={risk.sharpe_90d if risk.sharpe_90d is not None else 'N/A'}"
            )

        kill_switch = "true" if (risk and risk.daily_drawdown_pct >= 0.07) else "false"
        current_weights_str = json.dumps(self._current_weights, indent=2)

        return (
            f"Snapshot taken at {datetime.utcnow().isoformat()} UTC.\n"
            f"Environment: {settings.environment}\n"
            f"kill_switch_active: {kill_switch}\n\n"
            f"{portfolio_summary}\n"
            f"{risk_summary}\n\n"
            f"Current weights:\n{current_weights_str}\n\n"
            f"Recent intelligence (last 10 minutes, oldest → newest):\n{signal_summary}\n\n"
            f"Per the methodology in the system prompt, return your weights JSON now."
        )

    def _summarise_signals(self) -> str:
        if not self._signal_cache:
            return "  (no signals received in window)"
        lines: list[str] = []
        for item in self._signal_cache[-20:]:
            topic = item.get("topic", "")
            payload = item.get("payload", {})
            direction = payload.get("direction", payload.get("regime", "?"))
            confidence = payload.get("confidence", payload.get("confidence_score", "?"))
            symbol = payload.get("symbol", "GLOBAL")
            lines.append(f"  [{topic}] {symbol} dir={direction} conf={confidence}")
        return "\n".join(lines)

    async def _ask_claude(self, dynamic_context: str) -> Optional[dict[str, float]]:
        try:
            response = await self._claude.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=512,
                system=[
                    {
                        "type": "text",
                        "text": _CIO_SYSTEM_PROMPT,
                        # 1h TTL covers ~12 decision cycles per cache creation,
                        # so cost amortisation is excellent at our 5-min cadence.
                        "cache_control": {"type": "ephemeral", "ttl": "1h"},
                    }
                ],
                messages=[{"role": "user", "content": dynamic_context}],
            )
            self._record_cache_metrics(response)

            text = response.content[0].text.strip()
            # Strip markdown code fences if the model accidentally adds them
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            weights = json.loads(text)

            total = sum(weights.values())
            if total > 1.05:
                log.warning("cio.claude_weights_exceed_1", total=total)
                weights = {k: v / total for k, v in weights.items()}

            claude_calls.labels(
                model=_CLAUDE_MODEL, agent_id=str(self.AGENT_ID), outcome="success"
            ).inc()
            return {k: round(float(v), 4) for k, v in weights.items()}
        except Exception as exc:
            claude_calls.labels(
                model=_CLAUDE_MODEL, agent_id=str(self.AGENT_ID), outcome="error"
            ).inc()
            log.error("cio.claude_error", error=str(exc))
            return None

    def _record_cache_metrics(self, response: Any) -> None:
        """Record token usage broken down by cache_create / cache_read / regular."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        cache_created = int(getattr(usage, "cache_creation_input_tokens", 0) or 0)
        cache_read = int(getattr(usage, "cache_read_input_tokens", 0) or 0)
        # `input_tokens` already excludes cache_read in current SDKs, but does
        # include cache_creation. Subtract to isolate the truly uncached portion.
        regular = int(getattr(usage, "input_tokens", 0) or 0) - cache_created
        regular = max(0, regular)
        output = int(getattr(usage, "output_tokens", 0) or 0)

        agent_label = str(self.AGENT_ID)
        if cache_created:
            claude_input_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label, kind="cache_create"
            ).inc(cache_created)
        if cache_read:
            claude_input_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label, kind="cache_read"
            ).inc(cache_read)
        if regular:
            claude_input_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label, kind="regular"
            ).inc(regular)
        if output:
            claude_output_tokens.labels(
                model=_CLAUDE_MODEL, agent_id=agent_label
            ).inc(output)

        log.debug(
            "cio.claude_token_usage",
            cache_created=cache_created,
            cache_read=cache_read,
            regular_input=regular,
            output=output,
            cache_hit_rate=(
                round(cache_read / max(1, cache_read + regular + cache_created), 3)
            ),
        )

    def _weights_changed(self, new: dict[str, float]) -> bool:
        for strategy, new_w in new.items():
            old_w = self._current_weights.get(strategy, 0.0)
            if abs(new_w - old_w) > _CAPITAL_REBALANCE_THRESHOLD:
                return True
        return False

    async def _publish_allocation(self, weights: dict[str, float]) -> None:
        await self.publish(
            KafkaTopic.PORTFOLIO_STATE,
            {
                "event": "capital_reallocation",
                "weights": weights,
                "regime": self._current_regime.value,
                "decided_by": self.AGENT_ID,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "CapitalAllocation",
        )
