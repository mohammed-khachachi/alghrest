"""
Agent 19 — Breakout Hunter
Volume-confirmed range breakouts: price closes outside 20-day range
with volume ≥ 2 x  the 20-day average. ATR trailing stop.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from decimal import Decimal
from typing import Any

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
    Timeframe,
    TradeProposal,
)
from core.strategy_signals import (
    ATRManagementParameters,
    BreakoutParameters,
    VolumeBreakoutKernel,
    atr_entry_plan,
    atr_trailing_step,
    close_crossed_stop,
    seeded_range_atr,
)

log = structlog.get_logger(__name__)

_RANGE_PERIOD = 20
_VOLUME_MULT = 2.0  # Volume must be ≥ 2 x  average
_ATR_PERIOD = 14
_ATR_STOP_MULT = 2.0
_MIN_BARS = 30
_MANAGEMENT = ATRManagementParameters(
    atr_period=_ATR_PERIOD,
    atr_window=200,
    atr_stop_multiplier=Decimal(str(_ATR_STOP_MULT)),
    proposed_target_r=Decimal(3),
)
_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "AVAX/USDT", "MATIC/USDT"]


class BreakoutHunter(BaseStrategy):
    """Agent 19 — Volume-confirmed breakout on daily bars."""

    AGENT_ID = 19
    strategy_id = "breakout_hunter_volume"
    capital_pct = 0.09
    max_positions = 4
    risk_per_trade = 0.008

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="BreakoutHunter",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._bars: dict[str, deque[OHLCVBar]] = defaultdict(lambda: deque(maxlen=200))
        self._trailing_stops: dict[str, float] = {}
        self._positions: dict[str, str] = {}  # symbol → "long" | "short"

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("breakout_hunter.initialized")

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
                bar = OHLCVBar.model_validate(msg.get("payload", msg))
                if bar.timeframe != Timeframe.D1 or not bar.is_closed:
                    continue
                if bar.symbol not in _SYMBOLS:
                    continue
                self._bars[bar.symbol].append(bar)
                await self._evaluate(bar.symbol)
            except Exception as exc:
                log.warning("breakout_hunter.bar_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("breakout_hunter.shutdown", positions=list(self._positions))

    # ── Evaluation ────────────────────────────────────────────────────────────

    async def _evaluate(self, symbol: str) -> None:
        bars = list(self._bars[symbol])
        if len(bars) < _MIN_BARS:
            return

        df = self._to_df(bars)
        df = self._compute_indicators(df)
        last = df.iloc[-1]

        close = float(last["close"])
        try:
            atr = float(last.get(f"ATRr_{_ATR_PERIOD}", float("nan")))
        except (TypeError, ValueError):
            atr = float("nan")
        signal = VolumeBreakoutKernel(
            BreakoutParameters(
                range_period=_RANGE_PERIOD,
                minimum_bars=_MIN_BARS,
                volume_multiplier=Decimal(str(_VOLUME_MULT)),
            )
        ).evaluate(list(df.itertuples()))

        if symbol not in self._positions:
            if not pd.notna(atr) or atr <= 0 or atr == float("inf"):
                log.warning("breakout_hunter.unknown_atr", symbol=symbol)
                return
            if signal is not None and signal.direction == "BUY":
                await self._enter(symbol, OrderSide.BUY, close, atr)
            elif signal is not None and signal.direction == "SELL":
                await self._enter(symbol, OrderSide.SELL, close, atr)
        else:
            side = self._positions[symbol]
            stop = self._trailing_stops.get(symbol)
            try:
                if side not in {"long", "short"} or stop is None:
                    raise ValueError("Missing management position state")
                crossed = close_crossed_stop(
                    "BUY" if side == "long" else "SELL", Decimal(str(close)), Decimal(str(stop))
                )
            except ValueError:
                log.warning("breakout_hunter.invalid_management_state", symbol=symbol)
                return
            if crossed:
                await self._exit(symbol, close, "trailing_stop")
            else:
                self._update_trailing_stop(symbol, close, atr, side)

    async def _enter(self, symbol: str, side: OrderSide, price: float, atr: float) -> None:
        if len(self._positions) >= self.max_positions:
            return
        if side not in {OrderSide.BUY, OrderSide.SELL}:
            log.warning("breakout_hunter.invalid_management_side", symbol=symbol)
            return
        try:
            plan = atr_entry_plan(
                "BUY" if side == OrderSide.BUY else "SELL",
                Decimal(str(price)),
                Decimal(str(atr)),
                _MANAGEMENT,
            )
        except (ValueError, ArithmeticError):
            log.warning("breakout_hunter.invalid_entry_geometry", symbol=symbol)
            return

        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        sleeve = portfolio.total_capital * Decimal(str(self.capital_pct))
        size_usd = min(
            sleeve / Decimal(str(self.max_positions)), portfolio.total_capital * Decimal("0.05")
        )
        size = size_usd / Decimal(str(price))

        if size_usd < Decimal("10"):
            return

        stop_price = float(plan.invalidation)
        target_price = float(plan.proposed_target)

        self._trailing_stops[symbol] = stop_price
        self._positions[symbol] = "long" if side == OrderSide.BUY else "short"

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
            stop_loss=Decimal(str(round(stop_price, 2))),
            take_profit=Decimal(str(round(target_price, 2))),
            confidence_score=0.75,
            rationale=f"Volume breakout {'above high' if side == OrderSide.BUY else 'below low'} ATR={atr:.2f}",
        )
        await self.publish(
            KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "TradeProposal"
        )
        log.info(
            "breakout_hunter.entry", symbol=symbol, side=side.value, price=price, atr=round(atr, 2)
        )

    async def _exit(self, symbol: str, price: float, reason: str) -> None:
        side = self._positions.pop(symbol, "unknown")
        self._trailing_stops.pop(symbol, None)
        if reason == "trailing_stop":
            self.record_loss()
        log.info("breakout_hunter.exit", symbol=symbol, side=side, price=price, reason=reason)

    def _update_trailing_stop(self, symbol: str, close: float, atr: float, side: str) -> None:
        current = self._trailing_stops.get(symbol)
        if current is None:
            return
        try:
            if side not in {"long", "short"}:
                raise ValueError("Unknown position side")
            step = atr_trailing_step(
                "BUY" if side == "long" else "SELL",
                Decimal(str(close)),
                Decimal(str(current)),
                Decimal(str(atr)),
                _MANAGEMENT,
            )
        except (ValueError, ArithmeticError):
            log.warning("breakout_hunter.invalid_management_state", symbol=symbol)
            return
        if step.action == "HOLD":
            self._trailing_stops[symbol] = float(step.next_stop)

    # ── Strategy interface ─────────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> TradeProposal | None:
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        stop = self._trailing_stops.get(position.symbol)
        if stop is None:
            return False
        price = market_state.prices.get(position.symbol)
        if price is None or position.side not in {OrderSide.BUY, OrderSide.SELL}:
            return False
        try:
            return close_crossed_stop(
                "BUY" if position.side == OrderSide.BUY else "SELL", price, Decimal(str(stop))
            )
        except ValueError:
            return False

    def backtest(self, data: pd.DataFrame, params: dict[str, Any]) -> BacktestResult:
        from backtesting.engine import BacktestEngine

        engine = BacktestEngine(
            strategy_id=self.strategy_id,
            strategy_name=self.name,
            symbol=params.get("symbol", "BTC/USDT"),
        )
        period = params.get("range_period", _RANGE_PERIOD)
        vol_mult = params.get("volume_mult", _VOLUME_MULT)
        kernel = VolumeBreakoutKernel(
            BreakoutParameters(
                range_period=period,
                minimum_bars=max(_MIN_BARS, period + 1),
                volume_multiplier=Decimal(str(vol_mult)),
            )
        )
        bars = list(data.itertuples())
        signals = pd.Series(0, index=data.index)
        for i in range(kernel.parameters.minimum_bars - 1, len(bars)):
            signal = kernel.evaluate(bars[i - kernel.parameters.minimum_bars + 1 : i + 1])
            assert signal is not None
            signals.iloc[i] = (
                1 if signal.direction == "BUY" else -1 if signal.direction == "SELL" else 0
            )
        # The close that creates a signal cannot also be its execution price.
        # Existing engine supports next-bar close as a proxy, not futures fills.
        entries = signals.eq(1).shift(1, fill_value=False)
        exits = signals.lt(0).shift(1, fill_value=False)
        return engine.run(data, entries, exits)

    # ── Helpers ───────────────────────────────────────────────────────────────

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
            ]
        )

    @staticmethod
    def _compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        atr = seeded_range_atr(list(df.itertuples()), _MANAGEMENT)
        # Only the current closed-bar value is consumed by this agent.
        df[f"ATRr_{_ATR_PERIOD}"] = float("nan")
        if atr is not None:
            df.iloc[-1, df.columns.get_loc(f"ATRr_{_ATR_PERIOD}")] = float(atr)
        return df
