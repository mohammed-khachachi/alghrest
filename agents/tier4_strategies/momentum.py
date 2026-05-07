"""
Agent 14 — Momentum Strategy
Cross-sectional momentum: rank assets by 12-1 momentum (12-month return minus last month).
Go long top-decile, short bottom-decile. Rebalance weekly.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd
import structlog

from agents.base_agent import BaseStrategy
from core.data.models import (
    AgentConfig,
    AssetClass,
    BacktestResult,
    Exchange,
    KafkaTopic,
    MarketState,
    OHLCVBar,
    OrderSide,
    OrderType,
    Position,
    SignalDirection,
    Timeframe,
    TradeProposal,
)

log = structlog.get_logger(__name__)

_MOMENTUM_LOOKBACK = 252      # ~12 months of daily bars
_SKIP_LAST = 21               # Skip last 21 days (1-month reversal)
_MIN_BARS = _MOMENTUM_LOOKBACK + _SKIP_LAST + 10
_REBALANCE_HOURS = 168        # Weekly (7 × 24)
_LONG_TOP_N = 3               # Long top-3 by momentum rank
_SHORT_TOP_N = 3              # Short bottom-3
_SYMBOLS = [
    "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT",
    "ADA/USDT", "AVAX/USDT", "MATIC/USDT", "DOT/USDT", "LINK/USDT",
]


def _momentum_score(closes: np.ndarray) -> float:
    """12-1 momentum: cumulative return from -253 to -22 days."""
    if len(closes) < _MIN_BARS:
        return 0.0
    start = closes[-_MOMENTUM_LOOKBACK - _SKIP_LAST]
    end = closes[-_SKIP_LAST]
    if start <= 0:
        return 0.0
    return float(end / start - 1.0)


class MomentumStrategy(BaseStrategy):
    """Agent 14 — Cross-sectional momentum across top crypto assets."""

    AGENT_ID = 14
    strategy_id = "momentum_cross_sectional"
    capital_pct = 0.10
    max_positions = 6
    risk_per_trade = 0.008

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="MomentumStrategy",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._bars: dict[str, deque[OHLCVBar]] = defaultdict(
            lambda: deque(maxlen=400)
        )
        self._last_rebalance: Optional[datetime] = None
        self._active_longs: set[str] = set()
        self._active_shorts: set[str] = set()

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("momentum.initialized", symbols=_SYMBOLS)

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PRICES_REALTIME])
        async for msg in consumer.stream():
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(5)
                continue
            try:
                bar = OHLCVBar(**msg)
                if bar.timeframe != Timeframe.D1 or not bar.is_closed:
                    continue
                if bar.symbol not in _SYMBOLS:
                    continue
                self._bars[bar.symbol].append(bar)
                await self._maybe_rebalance()
            except Exception as exc:
                log.warning("momentum.bar_error", error=str(exc))
                self.record_processing_error("prices.realtime", type(exc).__name__)

    async def shutdown(self) -> None:
        log.info("momentum.shutdown")

    # ── Rebalance ──────────────────────────────────────────────────────────────

    async def _maybe_rebalance(self) -> None:
        now = datetime.utcnow()
        if self._last_rebalance and (now - self._last_rebalance).total_seconds() < _REBALANCE_HOURS * 3600:
            return

        scores: dict[str, float] = {}
        for sym in _SYMBOLS:
            bars = list(self._bars[sym])
            if len(bars) < _MIN_BARS:
                continue
            closes = np.array([float(b.close) for b in bars])
            scores[sym] = _momentum_score(closes)

        if len(scores) < _LONG_TOP_N + _SHORT_TOP_N:
            return

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        long_targets = {sym for sym, _ in ranked[:_LONG_TOP_N]}
        short_targets = {sym for sym, _ in ranked[-_SHORT_TOP_N:]}

        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        # Exit positions no longer in target set
        for sym in list(self._active_longs - long_targets):
            await self._exit_position(sym, "rebalance_exit_long")
        for sym in list(self._active_shorts - short_targets):
            await self._exit_position(sym, "rebalance_exit_short")

        # Enter new longs
        for sym in long_targets - self._active_longs:
            bars_list = list(self._bars[sym])
            price = float(bars_list[-1].close)
            score = scores[sym]
            await self._enter(sym, OrderSide.BUY, price, score, portfolio.total_capital)

        # Enter new shorts
        for sym in short_targets - self._active_shorts:
            bars_list = list(self._bars[sym])
            price = float(bars_list[-1].close)
            score = scores[sym]
            await self._enter(sym, OrderSide.SELL, price, abs(score), portfolio.total_capital)

        self._last_rebalance = now
        log.info(
            "momentum.rebalanced",
            longs=list(long_targets),
            shorts=list(short_targets),
            top_score=round(ranked[0][1], 4) if ranked else 0,
        )

    async def _enter(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        score: float,
        total_capital: Decimal,
    ) -> None:
        sleeve_capital = total_capital * Decimal(str(self.capital_pct))
        per_position = sleeve_capital / Decimal(str(self.max_positions))
        size_usd = min(per_position, total_capital * Decimal("0.05"))
        size = size_usd / Decimal(str(price))

        if size_usd < Decimal("10"):
            return

        direction = SignalDirection.BULLISH if side == OrderSide.BUY else SignalDirection.BEARISH
        stop_distance = price * 0.08   # 8% stop
        stop_loss = price - stop_distance if side == OrderSide.BUY else price + stop_distance
        take_profit = price + 2 * stop_distance if side == OrderSide.BUY else price - 2 * stop_distance

        proposal = TradeProposal(
            strategy_id=self.strategy_id,
            agent_id=self.AGENT_ID,
            symbol=symbol,
            exchange=Exchange.BINANCE,
            asset_class=AssetClass.CRYPTO,
            side=side,
            order_type=OrderType.MARKET,
            size=size.quantize(Decimal("0.000001")),
            size_usd=size_usd.quantize(Decimal("0.01")),
            limit_price=None,
            stop_loss=Decimal(str(round(stop_loss, 2))),
            take_profit=Decimal(str(round(take_profit, 2))),
            confidence_score=min(0.9, abs(score) * 2),
            rationale=f"12-1 momentum score={score:.4f} side={side.value}",
        )
        await self.publish(KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "TradeProposal")

        if side == OrderSide.BUY:
            self._active_longs.add(symbol)
        else:
            self._active_shorts.add(symbol)

        log.info("momentum.entry", symbol=symbol, side=side.value, score=round(score, 4))

    async def _exit_position(self, symbol: str, reason: str) -> None:
        self._active_longs.discard(symbol)
        self._active_shorts.discard(symbol)
        log.info("momentum.exit", symbol=symbol, reason=reason)

    # ── Strategy interface ─────────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> Optional[TradeProposal]:
        return None  # reactive rebalance

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        return False  # exits managed by rebalance cycle

    def backtest(self, data: pd.DataFrame, params: dict) -> BacktestResult:
        from backtesting.engine import BacktestEngine
        engine = BacktestEngine()
        period = params.get("lookback", _MOMENTUM_LOOKBACK)
        skip = params.get("skip_last", _SKIP_LAST)
        closes = data["close"].values
        signals = pd.Series(0, index=data.index)
        for i in range(period + skip, len(closes)):
            score = (closes[i - skip] / closes[i - period - skip]) - 1.0
            signals.iloc[i] = 1 if score > 0 else -1
        return engine.run(data, signals, self.strategy_id)
