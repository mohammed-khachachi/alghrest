"""
Agent 12 — Trend Follower
Strategy: Donchian channel breakout (20-day) filtered by ADX > 25.
Exit: ATR-based trailing stop (2.5 x ATR) + Donchian channel re-entry break.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import structlog

from agents.base_agent import BaseStrategy
from agents.tier5_execution.position_sizer import PositionSizer
from backtesting.engine import BacktestEngine
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

_DONCHIAN_PERIOD = 20
_ADX_PERIOD = 14
_ADX_THRESHOLD = 25.0
_ATR_PERIOD = 14
_ATR_STOP_MULT = 2.5
_MIN_BARS = 30
_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT"]


class TrendFollower(BaseStrategy):
    AGENT_ID = 12
    strategy_id = "trend_follower_donchian"
    capital_pct = 0.12
    max_positions = 4
    risk_per_trade = 0.008

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="TrendFollower",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._bars: dict[str, deque[OHLCVBar]] = defaultdict(lambda: deque(maxlen=200))
        self._trailing_stops: dict[str, float] = {}
        self._active_sides: dict[str, OrderSide] = {}

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("trend_follower.initialized", symbols=_SYMBOLS)

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PRICES_REALTIME])
        await consumer.initialize()
        async for msg in consumer.stream():
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(5)
                continue
            try:
                if msg.get("message_type") != "ohlcv":
                    continue
                payload = msg.get("payload", msg)
                bar = OHLCVBar.model_validate(payload)
                if bar.timeframe != Timeframe.H4 or bar.symbol not in _SYMBOLS or not bar.is_closed:
                    continue
                self._bars[bar.symbol].append(bar)
                await self._evaluate(bar.symbol)
            except Exception as exc:
                self.record_processing_error("prices.realtime", type(exc).__name__)
                log.warning("trend_follower.bar_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("trend_follower.shutdown", active=list(self._active_sides))

    # ─── Evaluation ───────────────────────────────────────────────────────────

    async def _evaluate(self, symbol: str) -> None:
        bars = list(self._bars[symbol])
        if len(bars) < _MIN_BARS:
            return

        df = self._to_df(bars)
        df = self._compute_indicators(df)
        last = df.iloc[-1]

        adx = float(last.get("ADX_14") or 0.0)
        if np.isnan(adx) or adx < _ADX_THRESHOLD:
            return

        dc_high = last.get(f"DCU_{_DONCHIAN_PERIOD}_{_DONCHIAN_PERIOD}")
        dc_low = last.get(f"DCL_{_DONCHIAN_PERIOD}_{_DONCHIAN_PERIOD}")
        # pandas-ta exposes both DCU_x_x and DCL_x_x; fall back to alt naming
        if dc_high is None:
            dc_high = last.get(f"DCH_{_DONCHIAN_PERIOD}")
        if dc_low is None:
            dc_low = last.get(f"DCL_{_DONCHIAN_PERIOD}")
        if dc_high is None or dc_low is None or np.isnan(dc_high) or np.isnan(dc_low):
            return

        close = float(last["close"])
        atr = float(last.get(f"ATRr_{_ATR_PERIOD}") or last.get("ATR") or close * 0.01)

        # Entry
        if symbol not in self._active_sides:
            if close >= float(dc_high):
                await self._open_position(symbol, OrderSide.BUY, close, atr, adx, df)
            elif close <= float(dc_low):
                await self._open_position(symbol, OrderSide.SELL, close, atr, adx, df)
        else:
            # Exit on trailing stop
            stop = self._trailing_stops.get(symbol)
            side = self._active_sides[symbol]
            if stop is not None:
                if side == OrderSide.BUY and close < stop:
                    await self._close_position(symbol, "trailing_stop")
                    return
                if side == OrderSide.SELL and close > stop:
                    await self._close_position(symbol, "trailing_stop")
                    return
            self._update_trailing_stop(symbol, close, atr)

    async def _open_position(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        atr: float,
        adx: float,
        df: pd.DataFrame,
    ) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        stop_distance = _ATR_STOP_MULT * atr
        if side == OrderSide.BUY:
            stop_price = price - stop_distance
            tp_price = price + 4 * stop_distance
            direction = SignalDirection.BULLISH
        else:
            stop_price = price + stop_distance
            tp_price = price - 4 * stop_distance
            direction = SignalDirection.BEARISH

        sizer = PositionSizer(portfolio_value_usd=portfolio.total_capital)
        daily_vol = float(df["close"].pct_change().std()) * (6**0.5)  # H4 -> approx daily
        sizing = sizer.size(
            symbol=symbol,
            strategy_id=self.strategy_id,
            entry_price=Decimal(str(price)),
            stop_loss=Decimal(str(stop_price)),
            win_rate=0.52,
            avg_win=0.04,
            avg_loss=0.02,
            symbol_daily_vol=daily_vol if not np.isnan(daily_vol) else 0.02,
            current_leverage=float(portfolio.leverage),
            signal_strength=min(1.0, adx / 50.0),
        )

        if sizing.final_size_usd <= Decimal("10"):
            return

        self._trailing_stops[symbol] = stop_price
        self._active_sides[symbol] = side

        proposal = TradeProposal(
            strategy_id=self.strategy_id,
            agent_id=self.AGENT_ID,
            symbol=symbol,
            exchange=Exchange.BINANCE,
            asset_class=AssetClass.CRYPTO,
            side=side,
            order_type=OrderType.MARKET,
            size=sizing.final_size_units,
            size_usd=sizing.final_size_usd,
            limit_price=None,
            stop_loss=Decimal(str(round(stop_price, 2))),
            take_profit=Decimal(str(round(tp_price, 2))),
            confidence_score=min(0.95, adx / 50.0),
            rationale=f"Donchian breakout ADX={adx:.1f} ATR={atr:.2f} {direction.value}",
        )

        await self.publish(
            KafkaTopic.PROPOSALS_BUS,
            payload=proposal.model_dump(mode="json"),
            message_type="TradeProposal",
        )
        log.info(
            "trend_follower.entry",
            symbol=symbol,
            side=side.value,
            price=round(price, 2),
            adx=round(adx, 1),
            size_usd=float(sizing.final_size_usd),
        )

    async def _close_position(self, symbol: str, reason: str) -> None:
        side = self._active_sides.pop(symbol, None)
        self._trailing_stops.pop(symbol, None)
        if reason == "trailing_stop":
            self.record_loss()
        log.info(
            "trend_follower.exit", symbol=symbol, side=side.value if side else None, reason=reason
        )

    def _update_trailing_stop(self, symbol: str, close: float, atr: float) -> None:
        side = self._active_sides.get(symbol)
        if side is None:
            return
        current = self._trailing_stops.get(symbol)
        if current is None:
            return
        if side == OrderSide.BUY:
            new_stop = close - _ATR_STOP_MULT * atr
            self._trailing_stops[symbol] = max(current, new_stop)
        else:
            new_stop = close + _ATR_STOP_MULT * atr
            self._trailing_stops[symbol] = min(current, new_stop)

    # ─── Strategy interface ───────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> TradeProposal | None:
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        stop = self._trailing_stops.get(position.symbol)
        if stop is None:
            return False
        price = float(market_state.prices.get(position.symbol, Decimal("0")))
        if position.side == OrderSide.BUY:
            return price < stop
        return price > stop

    def backtest(self, data: pd.DataFrame, params: dict[str, Any]) -> BacktestResult:
        engine = BacktestEngine(
            strategy_id=self.strategy_id,
            strategy_name="TrendFollower",
            symbol="BTC/USDT",
            timeframe=Timeframe.H4,
        )
        params.get("donchian_period", _DONCHIAN_PERIOD)
        df = self._compute_indicators(data.copy())

        entries = pd.Series(False, index=df.index)
        exits = pd.Series(False, index=df.index)
        dc_high_col = next(
            (c for c in df.columns if c.startswith("DCU_") or c.startswith("DCH_")), None
        )
        dc_low_col = next((c for c in df.columns if c.startswith("DCL_")), None)
        if dc_high_col and dc_low_col and "ADX_14" in df.columns:
            entries = (df["close"] >= df[dc_high_col]) & (df["ADX_14"] >= _ADX_THRESHOLD)
            exits = df["close"] < df[dc_low_col]

        return engine.run(data, entries, exits)

    # ─── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _to_df(bars: list[OHLCVBar]) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "open": float(b.open),
                    "high": float(b.high),
                    "low": float(b.low),
                    "close": float(b.close),
                    "volume": float(b.volume),
                }
                for b in bars
            ],
            index=[b.time for b in bars],
        )

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df.ta.donchian(lower_length=_DONCHIAN_PERIOD, upper_length=_DONCHIAN_PERIOD, append=True)
        df.ta.adx(length=_ADX_PERIOD, append=True)
        df.ta.atr(length=_ATR_PERIOD, append=True)
        return df
