"""
Agent 34 — Macro Rotator
Risk-on / risk-off regime detection from macro signals.
Rotates between high-beta (BTC/ETH) and defensive (stables/gold) based on regime.
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Optional

import structlog

from agents.base_agent import BaseStrategy
from core.data.models import (
    AgentConfig,
    AssetClass,
    BacktestResult,
    Exchange,
    KafkaTopic,
    MacroSignal,
    MarketRegime,
    MarketState,
    OrderSide,
    OrderType,
    Position,
    SentimentSignal,
    TradeProposal,
    VolatilitySignal,
    VolatilityRegime,
)

import pandas as pd

log = structlog.get_logger(__name__)

# Asset baskets
_RISK_ON_ASSETS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
_RISK_OFF_ASSETS: list[str] = []    # Cash / USDC — no long positions in risk-off

_REBALANCE_INTERVAL = 3600 * 4    # 4 hours


class MacroRotator(BaseStrategy):
    """
    Agent 18 — Macro regime rotator.
    Listens to macro and volatility signals from Tier 2/3 and allocates accordingly.
    In RISK_ON: holds BTC/ETH/SOL longs.
    In RISK_OFF / CRISIS: closes all positions and holds cash.
    """

    AGENT_ID = 34
    strategy_id = "macro_rotator_regime"
    capital_pct = 0.10
    max_positions = 3
    risk_per_trade = 0.01

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="MacroRotator",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._current_regime = MarketRegime.NEUTRAL
        self._vol_regime = VolatilityRegime.NORMAL
        self._active_positions: set[str] = set()
        self._last_rebalance: float = 0.0
        self._regime_votes: list[MarketRegime] = []   # Recent regime signals

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("macro_rotator.initialized")

    async def run(self) -> None:
        consumer = self.make_consumer(
            [KafkaTopic.MACRO_REGIME, KafkaTopic.VOLATILITY_FORECAST, KafkaTopic.SENTIMENT_SCORED]
        )
        rebalance_task = asyncio.create_task(self._rebalance_loop())
        try:
            async for msg in consumer.stream():
                if await self.is_halted() or self.is_strategy_paused:
                    await asyncio.sleep(5)
                    continue
                try:
                    await self._ingest_signal(msg)
                except Exception as exc:
                    log.warning("macro_rotator.ingest_error", error=str(exc))
        finally:
            rebalance_task.cancel()

    async def shutdown(self) -> None:
        log.info("macro_rotator.shutdown", regime=self._current_regime.value)

    # ── Signal Ingestion ──────────────────────────────────────────────────────

    async def _ingest_signal(self, msg: dict) -> None:
        topic = msg.get("topic", "")

        if topic == KafkaTopic.MACRO_REGIME.value:
            regime_raw = msg.get("regime", "")
            try:
                regime = MarketRegime(regime_raw)
                self._regime_votes.append(regime)
                self._regime_votes = self._regime_votes[-10:]   # rolling window
                self._current_regime = self._majority_regime()
                log.debug("macro_rotator.regime_vote", regime=regime.value, consensus=self._current_regime.value)
            except ValueError:
                pass

        elif topic == KafkaTopic.VOLATILITY_FORECAST.value:
            vol_raw = msg.get("regime", "")
            try:
                self._vol_regime = VolatilityRegime(vol_raw)
            except ValueError:
                pass

        elif topic == KafkaTopic.SENTIMENT_SCORED.value:
            score = msg.get("sentiment_score", msg.get("score", 0.0))
            if score > 0.5:
                self._regime_votes.append(MarketRegime.RISK_ON)
            elif score < -0.5:
                self._regime_votes.append(MarketRegime.RISK_OFF)
            self._regime_votes = self._regime_votes[-10:]
            self._current_regime = self._majority_regime()

    def _majority_regime(self) -> MarketRegime:
        if not self._regime_votes:
            return MarketRegime.NEUTRAL
        counts: dict[MarketRegime, int] = {}
        for v in self._regime_votes:
            counts[v] = counts.get(v, 0) + 1
        return max(counts, key=lambda k: counts[k])

    # ── Rebalance Loop ────────────────────────────────────────────────────────

    async def _rebalance_loop(self) -> None:
        while True:
            await asyncio.sleep(_REBALANCE_INTERVAL)
            if await self.is_halted():
                continue
            try:
                await self._rebalance()
            except Exception as exc:
                log.error("macro_rotator.rebalance_error", error=str(exc))

    async def _rebalance(self) -> None:
        regime = self._current_regime
        vol = self._vol_regime

        # In crisis/high vol → close all and hold cash
        if regime in (MarketRegime.RISK_OFF, MarketRegime.CRISIS) or vol == VolatilityRegime.CRISIS:
            for sym in list(self._active_positions):
                await self._close(sym, "risk_off_regime")
            log.info("macro_rotator.risk_off", regime=regime.value, vol_regime=vol.value)
            return

        if regime == MarketRegime.RISK_ON:
            target_assets = _RISK_ON_ASSETS
        else:
            # NEUTRAL: lighter allocation to BTC/ETH only
            target_assets = _RISK_ON_ASSETS[:2]

        # Scale down in volatile regimes
        size_scalar = 0.6 if vol == VolatilityRegime.VOLATILE else 1.0

        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        sleeve = portfolio.total_capital * Decimal(str(self.capital_pct)) * Decimal(str(size_scalar))
        per_asset = sleeve / Decimal(str(len(target_assets)))

        # Close positions not in target
        for sym in list(self._active_positions - set(target_assets)):
            await self._close(sym, "regime_rotation")

        # Open missing positions
        for sym in target_assets:
            if sym not in self._active_positions:
                await self._open(sym, per_asset, portfolio)

        log.info(
            "macro_rotator.rebalanced",
            regime=regime.value,
            targets=target_assets,
            scalar=size_scalar,
        )

    async def _open(self, symbol: str, size_usd: Decimal, portfolio: object) -> None:
        price = portfolio.positions and next(
            (float(p.current_price) for p in portfolio.positions if p.symbol == symbol), None
        )
        if price is None:
            prices = await self.state.redis.get(f"prices:{symbol}")
            if prices:
                import json
                price = float(json.loads(prices).get("last", 0))
        if not price or price <= 0:
            return

        size = size_usd / Decimal(str(price))
        if size_usd < Decimal("10"):
            return

        stop_pct = 0.10
        stop_loss = Decimal(str(price * (1 - stop_pct)))
        take_profit = Decimal(str(price * (1 + stop_pct * 3)))

        proposal = TradeProposal(
            strategy_id=self.strategy_id,
            agent_id=self.AGENT_ID,
            symbol=symbol,
            exchange=Exchange.BINANCE,
            asset_class=AssetClass.CRYPTO,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            size=size.quantize(Decimal("0.000001")),
            size_usd=size_usd.quantize(Decimal("0.01")),
            limit_price=None,
            stop_loss=stop_loss,
            take_profit=take_profit,
            confidence_score=0.70,
            rationale=f"Macro regime={self._current_regime.value} risk-on allocation",
        )
        await self.publish(KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "TradeProposal")
        self._active_positions.add(symbol)
        log.info("macro_rotator.open", symbol=symbol, size_usd=float(size_usd), regime=self._current_regime.value)

    async def _close(self, symbol: str, reason: str) -> None:
        self._active_positions.discard(symbol)
        log.info("macro_rotator.close", symbol=symbol, reason=reason)

    # ── Strategy interface ─────────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> Optional[TradeProposal]:
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        return self._current_regime in (MarketRegime.RISK_OFF, MarketRegime.CRISIS)

    def backtest(self, data: pd.DataFrame, params: dict) -> BacktestResult:
        from backtesting.engine import BacktestEngine
        engine = BacktestEngine()
        signals = pd.Series(1, index=data.index)   # always long as approximation
        return engine.run(data, signals, self.strategy_id)
