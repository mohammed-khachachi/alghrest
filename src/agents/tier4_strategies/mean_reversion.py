"""
Agent 13 — Mean Reversion
Strategy: Bollinger Band touch + Z-score ±2 entry, gated by Hurst exponent < 0.5.
Exit: Z-score crosses zero (mean reversion complete) or stop at ±3sigma.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import structlog
from numpy.typing import NDArray

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
    Timeframe,
    TradeProposal,
)

log = structlog.get_logger(__name__)

_BB_PERIOD = 20
_BB_STD = 2.0
_ZSCORE_ENTRY = 2.0
_ZSCORE_EXIT = 0.3
_ZSCORE_STOP = 3.0
_MIN_BARS = 60
_HURST_MAX = 0.5
_HURST_WINDOW = 100
_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "MATIC/USDT", "AVAX/USDT"]


def _hurst_exponent(ts: NDArray[np.float64]) -> float:
    """Simplified R/S Hurst exponent on log returns."""
    if len(ts) < 20:
        return 0.5
    log_rets = np.diff(np.log(ts + 1e-10))
    lags = range(2, min(len(log_rets) // 2, 30))
    rs_vals: list[tuple[int, float]] = []
    for lag in lags:
        chunks = [log_rets[i : i + lag] for i in range(0, len(log_rets) - lag, lag)]
        rs_chunk: list[float] = []
        for chunk in chunks:
            if len(chunk) < 2:
                continue
            mean = chunk.mean()
            dev = np.cumsum(chunk - mean)
            r = dev.max() - dev.min()
            s = chunk.std()
            if s > 0:
                rs_chunk.append(r / s)
        if rs_chunk:
            rs_vals.append((lag, float(np.mean(rs_chunk))))
    if len(rs_vals) < 2:
        return 0.5
    log_lags = np.log([v[0] for v in rs_vals])
    log_rs = np.log([v[1] for v in rs_vals])
    poly = np.polyfit(log_lags, log_rs, 1)
    return float(max(0.0, min(1.0, poly[0])))


class MeanReversion(BaseStrategy):
    AGENT_ID = 13
    strategy_id = "mean_reversion_zscore"
    capital_pct = 0.10
    max_positions = 5
    risk_per_trade = 0.007

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="MeanReversion",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._bars: dict[str, deque[OHLCVBar]] = defaultdict(lambda: deque(maxlen=300))
        self._position_z: dict[str, float] = {}
        self._position_side: dict[str, OrderSide] = {}

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info("mean_reversion.initialized", symbols=_SYMBOLS)

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
                if bar.timeframe != Timeframe.H1 or bar.symbol not in _SYMBOLS or not bar.is_closed:
                    continue
                self._bars[bar.symbol].append(bar)
                await self._evaluate(bar.symbol)
            except Exception as exc:
                self.record_processing_error("prices.realtime", type(exc).__name__)
                log.warning("mean_reversion.bar_error", error=str(exc))

    async def shutdown(self) -> None:
        log.info("mean_reversion.shutdown", positions=list(self._position_z))

    # ─── Evaluation ───────────────────────────────────────────────────────────

    async def _evaluate(self, symbol: str) -> None:
        bars = list(self._bars[symbol])
        if len(bars) < _MIN_BARS:
            return

        df = self._to_df(bars)
        df = self._compute_indicators(df)
        last = df.iloc[-1]
        close = float(last["close"])

        bb_upper = last.get(f"BBU_{_BB_PERIOD}_{_BB_STD}")
        bb_lower = last.get(f"BBL_{_BB_PERIOD}_{_BB_STD}")
        bb_mid = last.get(f"BBM_{_BB_PERIOD}_{_BB_STD}")
        if bb_upper is None or bb_lower is None or bb_mid is None:
            return
        if any(np.isnan(float(v)) for v in (bb_upper, bb_lower, bb_mid)):
            return

        band_width = float(bb_upper) - float(bb_lower)
        if band_width <= 0:
            return

        z_score = (close - float(bb_mid)) / (band_width / (2 * _BB_STD))

        # Hurst gating — only trade mean-reverting series
        closes = df["close"].values[-_HURST_WINDOW:]
        hurst = _hurst_exponent(closes)
        if hurst >= _HURST_MAX:
            return

        in_position = symbol in self._position_z

        if not in_position:
            side: OrderSide | None = None
            if z_score <= -_ZSCORE_ENTRY:
                side = OrderSide.BUY
            elif z_score >= _ZSCORE_ENTRY:
                side = OrderSide.SELL
            if side is not None:
                await self._open_position(
                    symbol, side, close, z_score, hurst, float(bb_mid), band_width
                )
        else:
            entry_z = self._position_z[symbol]
            if entry_z < 0 and z_score >= -_ZSCORE_EXIT or entry_z > 0 and z_score <= _ZSCORE_EXIT:
                await self._close_position(symbol, "reversion_complete")
            elif abs(z_score) >= _ZSCORE_STOP:
                await self._close_position(symbol, "zscore_stop")

    async def _open_position(
        self,
        symbol: str,
        side: OrderSide,
        price: float,
        z_score: float,
        hurst: float,
        mean: float,
        band_width: float,
    ) -> None:
        portfolio = await self.state.get_portfolio()
        if portfolio is None:
            return

        stop_z3_offset = (band_width / (2 * _BB_STD)) * _ZSCORE_STOP
        stop_loss = mean - stop_z3_offset if side == OrderSide.BUY else mean + stop_z3_offset

        confidence = min(0.9, abs(z_score) / _ZSCORE_STOP)
        sizer = PositionSizer(portfolio_value_usd=portfolio.total_capital)
        bars_for_vol = list(self._bars[symbol])
        daily_vol = float(self._to_df(bars_for_vol)["close"].pct_change().std()) * (24**0.5)

        sizing = sizer.size(
            symbol=symbol,
            strategy_id=self.strategy_id,
            entry_price=Decimal(str(price)),
            stop_loss=Decimal(str(stop_loss)),
            win_rate=0.58,
            avg_win=0.015,
            avg_loss=0.01,
            symbol_daily_vol=daily_vol if not np.isnan(daily_vol) else 0.02,
            current_leverage=float(portfolio.leverage),
            signal_strength=confidence,
        )

        if sizing.final_size_usd <= Decimal("10"):
            return

        self._position_z[symbol] = z_score
        self._position_side[symbol] = side

        proposal = TradeProposal(
            strategy_id=self.strategy_id,
            agent_id=self.AGENT_ID,
            symbol=symbol,
            exchange=Exchange.BINANCE,
            asset_class=AssetClass.CRYPTO,
            side=side,
            order_type=OrderType.LIMIT,
            size=sizing.final_size_units,
            size_usd=sizing.final_size_usd,
            limit_price=Decimal(str(round(price, 2))),
            stop_loss=Decimal(str(round(stop_loss, 2))),
            take_profit=Decimal(str(round(mean, 2))),
            confidence_score=confidence,
            rationale=f"Z={z_score:.2f} Hurst={hurst:.3f} BB_touch",
        )

        await self.publish(
            KafkaTopic.PROPOSALS_BUS,
            payload=proposal.model_dump(mode="json"),
            message_type="TradeProposal",
        )
        log.info(
            "mean_reversion.entry",
            symbol=symbol,
            side=side.value,
            z=round(z_score, 3),
            hurst=round(hurst, 3),
            size_usd=float(sizing.final_size_usd),
        )

    async def _close_position(self, symbol: str, reason: str) -> None:
        self._position_z.pop(symbol, None)
        self._position_side.pop(symbol, None)
        if reason == "zscore_stop":
            self.record_loss()
        elif reason == "reversion_complete":
            self.record_win()
        log.info("mean_reversion.exit", symbol=symbol, reason=reason)

    # ─── Strategy interface ───────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> TradeProposal | None:
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        bars = list(self._bars.get(position.symbol, []))
        if len(bars) < _MIN_BARS:
            return False
        df = self._compute_indicators(self._to_df(bars))
        last = df.iloc[-1]
        bb_mid = float(last.get(f"BBM_{_BB_PERIOD}_{_BB_STD}", float(last["close"])))
        bb_upper = float(last.get(f"BBU_{_BB_PERIOD}_{_BB_STD}", float(last["close"]) * 1.02))
        bb_lower = float(last.get(f"BBL_{_BB_PERIOD}_{_BB_STD}", float(last["close"]) * 0.98))
        band_width = bb_upper - bb_lower
        if band_width <= 0:
            return False
        z = (float(last["close"]) - bb_mid) / (band_width / (2 * _BB_STD))
        return abs(z) <= _ZSCORE_EXIT

    def backtest(self, data: pd.DataFrame, params: dict[str, Any]) -> BacktestResult:
        engine = BacktestEngine(
            strategy_id=self.strategy_id,
            strategy_name="MeanReversion",
            symbol="BTC/USDT",
            timeframe=Timeframe.H1,
        )
        df = self._compute_indicators(data.copy())

        bb_mid_col = f"BBM_{_BB_PERIOD}_{_BB_STD}"
        bb_upper_col = f"BBU_{_BB_PERIOD}_{_BB_STD}"
        bb_lower_col = f"BBL_{_BB_PERIOD}_{_BB_STD}"

        if bb_mid_col not in df.columns:
            entries = pd.Series(False, index=df.index)
            exits = pd.Series(False, index=df.index)
            return engine.run(data, entries, exits)

        band_w = df[bb_upper_col] - df[bb_lower_col]
        z = (df["close"] - df[bb_mid_col]) / (band_w / (2 * _BB_STD))
        entries = z <= -_ZSCORE_ENTRY
        exits = z.abs() <= _ZSCORE_EXIT
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
        df.ta.bbands(length=_BB_PERIOD, std=_BB_STD, append=True)
        return df
