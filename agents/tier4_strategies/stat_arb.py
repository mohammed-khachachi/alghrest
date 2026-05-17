"""
Agent 21 — Statistical Arbitrage (Pairs Trading)
Cointegrated pairs identified via ADF test.
Entry on Z-score ±2, exit at Z-score 0. Stop at ±3.5σ.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from typing import Optional

import numpy as np
import pandas as pd
import structlog
from statsmodels.tsa.stattools import adfuller

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

_ADF_PVALUE = 0.05       # Cointegration significance
_ZSCORE_ENTRY = 2.0
_ZSCORE_EXIT = 0.3
_ZSCORE_STOP = 3.5
_MIN_BARS = 120
_RESCAN_HOURS = 24       # Re-scan pairs every 24 h
_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT", "LINK/USDT"]
_PAIRS = [
    ("BTC/USDT", "ETH/USDT"),
    ("ETH/USDT", "SOL/USDT"),
    ("BNB/USDT", "ETH/USDT"),
    ("AVAX/USDT", "SOL/USDT"),
    ("LINK/USDT", "ETH/USDT"),
]


def _cointegration_hedge_ratio(y: np.ndarray, x: np.ndarray) -> Optional[float]:
    """OLS hedge ratio and ADF test on residuals. Returns ratio if cointegrated."""
    if len(y) < _MIN_BARS or len(x) < _MIN_BARS:
        return None
    n = min(len(y), len(x))
    y, x = y[-n:], x[-n:]
    hedge = np.cov(y, x)[0, 1] / np.var(x)
    spread = y - hedge * x
    try:
        adf_stat, p_value, *_ = adfuller(spread, maxlag=1, autolag=None)
        if p_value < _ADF_PVALUE:
            return float(hedge)
    except Exception:
        pass
    return None


class StatArb(BaseStrategy):
    """Agent 15 — Pairs trading with ADF cointegration test."""

    AGENT_ID = 21
    strategy_id = "stat_arb_pairs"
    capital_pct = 0.08
    max_positions = 4
    risk_per_trade = 0.006

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="StatArb",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._bars: dict[str, deque[OHLCVBar]] = defaultdict(lambda: deque(maxlen=300))
        self._hedge_ratios: dict[tuple[str, str], float] = {}
        self._active_pairs: dict[tuple[str, str], float] = {}  # pair → entry z-score
        self._last_scan: Optional[datetime] = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("stat_arb.initialized", pairs=len(_PAIRS))

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PRICES_REALTIME])
        async for msg in consumer.stream():
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(5)
                continue
            try:
                bar = OHLCVBar(**msg)
                if bar.timeframe != Timeframe.H1 or not bar.is_closed:
                    continue
                if bar.symbol not in _SYMBOLS:
                    continue
                self._bars[bar.symbol].append(bar)
                await self._scan_pairs()
            except Exception as exc:
                log.warning("stat_arb.bar_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("stat_arb.shutdown", active_pairs=len(self._active_pairs))

    # ── Pair Scan ──────────────────────────────────────────────────────────────

    async def _scan_pairs(self) -> None:
        # Re-fit hedge ratios once per day
        now = datetime.utcnow()
        if self._last_scan is None or (now - self._last_scan).total_seconds() > _RESCAN_HOURS * 3600:
            await self._fit_pairs()
            self._last_scan = now

        for pair, hedge in self._hedge_ratios.items():
            sym_y, sym_x = pair
            bars_y = list(self._bars[sym_y])
            bars_x = list(self._bars[sym_x])
            if len(bars_y) < 30 or len(bars_x) < 30:
                continue
            await self._evaluate_pair(pair, hedge, bars_y, bars_x)

    async def _fit_pairs(self) -> None:
        new_ratios: dict[tuple[str, str], float] = {}
        for sym_y, sym_x in _PAIRS:
            bars_y = list(self._bars[sym_y])
            bars_x = list(self._bars[sym_x])
            if len(bars_y) < _MIN_BARS or len(bars_x) < _MIN_BARS:
                continue
            n = min(len(bars_y), len(bars_x))
            y = np.array([float(b.close) for b in bars_y[-n:]])
            x = np.array([float(b.close) for b in bars_x[-n:]])
            hedge = _cointegration_hedge_ratio(y, x)
            if hedge is not None:
                new_ratios[(sym_y, sym_x)] = hedge
                log.debug("stat_arb.pair_fitted", pair=f"{sym_y}/{sym_x}", hedge=round(hedge, 6))
            else:
                log.debug("stat_arb.pair_not_cointegrated", pair=f"{sym_y}/{sym_x}")
        self._hedge_ratios = new_ratios
        log.info("stat_arb.pairs_fitted", count=len(new_ratios))

    async def _evaluate_pair(
        self,
        pair: tuple[str, str],
        hedge: float,
        bars_y: list[OHLCVBar],
        bars_x: list[OHLCVBar],
    ) -> None:
        n = min(len(bars_y), len(bars_x), 60)
        y = np.array([float(b.close) for b in bars_y[-n:]])
        x = np.array([float(b.close) for b in bars_x[-n:]])
        spread = y - hedge * x
        mean = spread.mean()
        std = spread.std()
        if std < 1e-10:
            return
        z = (spread[-1] - mean) / std

        in_trade = pair in self._active_pairs

        if not in_trade:
            if z <= -_ZSCORE_ENTRY:
                await self._enter_pair(pair, "long_spread", z, bars_y[-1], bars_x[-1], hedge, std)
            elif z >= _ZSCORE_ENTRY:
                await self._enter_pair(pair, "short_spread", z, bars_y[-1], bars_x[-1], hedge, std)
        else:
            entry_z = self._active_pairs[pair]
            if abs(z) <= _ZSCORE_EXIT:
                await self._exit_pair(pair, "reversion", z)
            elif abs(z) >= _ZSCORE_STOP:
                await self._exit_pair(pair, "stop_loss", z)
                self.record_loss()

    async def _enter_pair(
        self,
        pair: tuple[str, str],
        direction: str,
        z: float,
        bar_y: OHLCVBar,
        bar_x: OHLCVBar,
        hedge: float,
        spread_std: float,
    ) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        sleeve = portfolio.total_capital * Decimal(str(self.capital_pct))
        size_usd = min(sleeve / Decimal(str(self.max_positions)), portfolio.total_capital * Decimal("0.04"))
        if size_usd < Decimal("20"):
            return

        sym_y, sym_x = pair
        price_y = float(bar_y.close)
        price_x = float(bar_x.close)

        # Long spread: buy Y, sell X
        side_y = OrderSide.BUY if direction == "long_spread" else OrderSide.SELL
        side_x = OrderSide.SELL if direction == "long_spread" else OrderSide.BUY

        qty_y = size_usd / Decimal(str(price_y))
        qty_x = qty_y * Decimal(str(abs(hedge)))
        size_usd_x = qty_x * Decimal(str(price_x))

        sig_dir = SignalDirection.BULLISH if direction == "long_spread" else SignalDirection.BEARISH

        for sym, side, qty, sz_usd, price in [
            (sym_y, side_y, qty_y, size_usd, price_y),
            (sym_x, side_x, qty_x, size_usd_x, price_x),
        ]:
            stop_usd = spread_std * _ZSCORE_STOP
            proposal = TradeProposal(
                strategy_id=self.strategy_id,
                agent_id=self.AGENT_ID,
                symbol=sym,
                exchange=Exchange.BINANCE,
                asset_class=AssetClass.CRYPTO,
                side=side,
                order_type=OrderType.LIMIT,
                size=qty.quantize(Decimal("0.000001")),
                size_usd=sz_usd.quantize(Decimal("0.01")),
                limit_price=Decimal(str(round(price, 2))),
                stop_loss=None,
                take_profit=None,
                confidence_score=min(0.85, abs(z) / _ZSCORE_STOP),
                rationale=f"StatArb {sym_y}/{sym_x} z={z:.2f} direction={direction}",
            )
            await self.publish(KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "TradeProposal")

        self._active_pairs[pair] = z
        log.info("stat_arb.entry", pair=f"{sym_y}/{sym_x}", z=round(z, 3), direction=direction)

    async def _exit_pair(self, pair: tuple[str, str], reason: str, z: float) -> None:
        self._active_pairs.pop(pair, None)
        if reason == "reversion":
            self.record_win()
        log.info("stat_arb.exit", pair=str(pair), reason=reason, z=round(z, 3))

    # ── Strategy interface ─────────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> Optional[TradeProposal]:
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        return False

    def backtest(self, data: pd.DataFrame, params: dict) -> BacktestResult:
        from backtesting.engine import BacktestEngine
        engine = BacktestEngine()
        signals = pd.Series(0, index=data.index)
        return engine.run(data, signals, self.strategy_id)
