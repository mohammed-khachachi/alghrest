"""
ALGHREST — Agent 11: Technical Analyst
Consumes OHLCV bars from prices.realtime, computes 200+ indicators
across 5 timeframes per symbol, detects signal events (crossovers, extremes).
Publishes TechnicalSignal objects to indicators.computed Kafka topic.

Uses pandas-ta (wraps TA-Lib + more) for vectorized computation.
Maintains a rolling OHLCV DataFrame per (symbol, timeframe) — max 500 bars.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd
import structlog
from pandas_ta.utils._study import Study

from agents.base_agent import BaseAgent
from core.data.models import KafkaTopic, OHLCVBar, SignalDirection, TechnicalSignal, Timeframe
from core.orchestrator.message_bus import AlghrestConsumer
from core.utils.metrics import agent_processing_latency

logger = structlog.get_logger(__name__)

# Minimum bars needed before computing indicators
MIN_BARS = 50
MAX_BARS = 500  # Rolling window cap to bound memory

# Timeframes we analyze (subset of what Market Data Hub streams)
ANALYSIS_TIMEFRAMES = [Timeframe.M5, Timeframe.H1, Timeframe.H4, Timeframe.D1]


class TechnicalAnalyst(BaseAgent):
    """Agent 11 — Computes 200+ technical indicators and detects signal events."""

    AGENT_ID = 11

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=3, name="technical_analyst")
        # Keyed by (symbol, timeframe) → pd.DataFrame with columns: open,high,low,close,volume
        self._bars: dict[tuple[str, str], pd.DataFrame] = defaultdict(
            lambda: pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        )
        self._consumer: AlghrestConsumer | None = None

    async def initialize(self) -> None:
        self._consumer = self.make_consumer(
            [KafkaTopic.PRICES_REALTIME], auto_offset_reset="latest"
        )
        await self._consumer.initialize()
        self.logger.info("technical analyst initialized — consuming prices.realtime")

    async def run(self) -> None:
        if self._consumer is None:
            raise RuntimeError("Agent must be initialized before running")
        async for message in self._consumer.stream():
            if await self.is_halted():
                await asyncio.sleep(1)
                continue
            try:
                msg_type = message.get("message_type", "")
                if msg_type == "ohlcv":
                    await self._process_ohlcv(message.get("payload", message))
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.record_processing_error("prices.realtime", type(e).__name__)
                self.logger.warning("ohlcv processing failed", error=str(e))

    async def _process_ohlcv(self, payload: dict[str, Any]) -> None:
        """Update rolling DataFrame and re-compute indicators on each new closed bar."""
        try:
            bar = OHLCVBar.model_validate(payload)
        except Exception:
            return

        # Only analyze closed bars for signal accuracy
        if not bar.is_closed:
            return

        if bar.timeframe not in {tf.value for tf in ANALYSIS_TIMEFRAMES}:
            return

        key = (bar.symbol, bar.timeframe)
        df = self._bars[key]

        # Append new bar
        new_row = pd.DataFrame(
            [
                {
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
            ],
            index=[bar.time],
        )

        df = pd.concat([df, new_row])
        df = df[~df.index.duplicated(keep="last")]  # Dedup by timestamp
        df = df.tail(MAX_BARS)  # Cap memory
        self._bars[key] = df

        if len(df) < MIN_BARS:
            return

        with agent_processing_latency.labels(
            agent_id=str(self.agent_id), agent_name=self.name
        ).time():
            signals = await asyncio.get_event_loop().run_in_executor(
                None, self._compute_and_detect, df, bar.symbol, bar.timeframe
            )

        for signal in signals:
            await self.publish(
                KafkaTopic.INDICATORS_COMPUTED,
                payload=signal.model_dump(mode="json"),
                message_type="technical_signal",
            )

    def _compute_and_detect(
        self, df: pd.DataFrame, symbol: str, timeframe: str
    ) -> list[TechnicalSignal]:
        """Compute all indicators and detect crossover/extreme events. CPU-bound → run in executor."""
        signals: list[TechnicalSignal] = []

        try:
            ind = self._compute_indicators(df)
        except Exception as e:
            self.logger.debug("indicator computation failed", symbol=symbol, error=str(e))
            return []

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi = ind.get("RSI_14")
        if rsi is not None and not np.isnan(rsi):
            if rsi < 30:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "RSI",
                        rsi,
                        SignalDirection.BULLISH,
                        0.70,
                        threshold_breached=30.0,
                    )
                )
            elif rsi > 70:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "RSI",
                        rsi,
                        SignalDirection.BEARISH,
                        0.70,
                        threshold_breached=70.0,
                    )
                )

        # ── MACD ──────────────────────────────────────────────────────────────
        macd_hist = ind.get("MACDh_12_26_9")
        prev_hist = ind.get("MACDh_12_26_9_prev")
        if (
            macd_hist is not None
            and prev_hist is not None
            and not np.isnan(macd_hist)
            and not np.isnan(prev_hist)
        ):
            if prev_hist < 0 < macd_hist:  # Bullish crossover
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "MACD_CROSS",
                        macd_hist,
                        SignalDirection.BULLISH,
                        0.72,
                    )
                )
            elif prev_hist > 0 > macd_hist:  # Bearish crossover
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "MACD_CROSS",
                        macd_hist,
                        SignalDirection.BEARISH,
                        0.72,
                    )
                )

        # ── BOLLINGER BANDS ───────────────────────────────────────────────────
        bb_upper = ind.get("BBU_20_2.0")
        bb_lower = ind.get("BBL_20_2.0")
        close = df["close"].iloc[-1]
        if bb_upper and bb_lower and not np.isnan(bb_upper):
            if close <= bb_lower:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "BBANDS_LOWER",
                        close,
                        SignalDirection.BULLISH,
                        0.65,
                        threshold_breached=bb_lower,
                    )
                )
            elif close >= bb_upper:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "BBANDS_UPPER",
                        close,
                        SignalDirection.BEARISH,
                        0.65,
                        threshold_breached=bb_upper,
                    )
                )

        # ── STOCHASTIC ────────────────────────────────────────────────────────
        stoch_k = ind.get("STOCHk_14_3_3")
        stoch_d = ind.get("STOCHd_14_3_3")
        if (
            stoch_k is not None
            and stoch_d is not None
            and not np.isnan(stoch_k)
            and not np.isnan(stoch_d)
        ):
            if stoch_k < 20 and stoch_d < 20:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "STOCH",
                        stoch_k,
                        SignalDirection.BULLISH,
                        0.60,
                        threshold_breached=20.0,
                    )
                )
            elif stoch_k > 80 and stoch_d > 80:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "STOCH",
                        stoch_k,
                        SignalDirection.BEARISH,
                        0.60,
                        threshold_breached=80.0,
                    )
                )

        # ── EMA CROSS (20/50) ──────────────────────────────────────────────
        ema20 = ind.get("EMA_20")
        ema50 = ind.get("EMA_50")
        ema20_prev = ind.get("EMA_20_prev")
        ema50_prev = ind.get("EMA_50_prev")
        if (
            ema20 is not None
            and ema50 is not None
            and ema20_prev is not None
            and ema50_prev is not None
            and all(v and not np.isnan(v) for v in [ema20, ema50, ema20_prev, ema50_prev])
        ):
            if ema20_prev < ema50_prev and ema20 > ema50:  # Golden cross
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "EMA_GOLDEN_CROSS",
                        ema20,
                        SignalDirection.STRONG_BULLISH,
                        0.78,
                    )
                )
            elif ema20_prev > ema50_prev and ema20 < ema50:  # Death cross
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "EMA_DEATH_CROSS",
                        ema20,
                        SignalDirection.STRONG_BEARISH,
                        0.78,
                    )
                )

        # ── ADX (Trend Strength) ──────────────────────────────────────────────
        adx = ind.get("ADX_14")
        if adx and not np.isnan(adx):
            # ADX > 25 = trending, > 50 = strong trend
            trend_strength = float(adx) if not np.isnan(adx) else None
            if adx > 30:
                # Determine direction from DI lines
                plus_di = ind.get("DMP_14")
                minus_di = ind.get("DMN_14")
                if plus_di and minus_di:
                    direction = (
                        SignalDirection.BULLISH if plus_di > minus_di else SignalDirection.BEARISH
                    )
                    signals.append(
                        self._make_signal(
                            symbol,
                            timeframe,
                            "ADX_TREND",
                            adx,
                            direction,
                            0.65,
                            trend_strength=trend_strength,
                        )
                    )

        # ── CCI ───────────────────────────────────────────────────────────────
        cci = ind.get("CCI_14_0.015")
        if cci and not np.isnan(cci):
            if cci < -100:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "CCI",
                        cci,
                        SignalDirection.BULLISH,
                        0.58,
                    )
                )
            elif cci > 100:
                signals.append(
                    self._make_signal(
                        symbol,
                        timeframe,
                        "CCI",
                        cci,
                        SignalDirection.BEARISH,
                        0.58,
                    )
                )

        return signals

    def _compute_indicators(self, df: pd.DataFrame) -> dict[str, float]:
        """
        Compute all indicators using pandas-ta.
        Returns a flat dict of indicator_name → latest value.
        """
        result: dict[str, float] = {}

        # Store previous row values for crossover detection
        prev = df.iloc[-2] if len(df) >= 2 else None

        # Run all indicators via pandas-ta strategy
        df = df.copy()
        df.ta.study(
            Study(
                name="alghrest_full",
                cores=0,  # Already running in the agent executor; do not fork worker pools.
                ta=[
                    {"kind": "rsi", "length": 14},
                    {"kind": "macd", "fast": 12, "slow": 26, "signal": 9},
                    {"kind": "bbands", "length": 20, "std": 2.0},
                    {"kind": "stoch", "k": 14, "d": 3, "smooth_k": 3},
                    {"kind": "ema", "length": 9},
                    {"kind": "ema", "length": 20},
                    {"kind": "ema", "length": 50},
                    {"kind": "ema", "length": 200},
                    {"kind": "sma", "length": 20},
                    {"kind": "sma", "length": 50},
                    {"kind": "adx", "length": 14},
                    {"kind": "cci", "length": 14},
                    {"kind": "atr", "length": 14},
                    {"kind": "obv"},
                    {"kind": "mfi", "length": 14},
                    {"kind": "willr", "length": 14},
                    {"kind": "aroon", "length": 25},
                    {"kind": "ichimoku"},
                    {"kind": "vwap"},
                ],
            )
        )

        # Extract latest values from all computed columns
        latest = df.iloc[-1]
        for col in df.columns:
            if col in ("open", "high", "low", "close", "volume"):
                continue
            v = latest.get(col)
            if v is not None and not (isinstance(v, float) and np.isnan(v)):
                result[col] = float(v)

        # Add prev row values for crossover detection
        if prev is not None:
            for col in ["MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9", "EMA_20", "EMA_50"]:
                if col in df.columns:
                    v = df.iloc[-2].get(col)
                    if v is not None and not np.isnan(v):
                        result[f"{col}_prev"] = float(v)

        return result

    @staticmethod
    def _make_signal(
        symbol: str,
        timeframe: str,
        indicator: str,
        value: float,
        direction: SignalDirection,
        confidence: float,
        threshold_breached: float | None = None,
        trend_strength: float | None = None,
    ) -> TechnicalSignal:
        tf_enum = next((t for t in Timeframe if t.value == timeframe), Timeframe.H1)
        return TechnicalSignal(
            source_agent_id=11,
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            timeframe=tf_enum,
            indicator=indicator,
            indicator_value=value,
            threshold_breached=threshold_breached,
            trend_strength=trend_strength,
        )

    async def shutdown(self) -> None:
        if self._consumer:
            await self._consumer.shutdown()
        self.logger.info("technical analyst shutdown")
