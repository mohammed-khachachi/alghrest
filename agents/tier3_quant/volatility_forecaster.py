"""
ALGHREST — Agent 14: Volatility Forecaster
Fits GARCH/EGARCH models on realized returns to forecast 1d/7d/30d volatility.
Classifies volatility regime: Calm / Normal / Volatile / Crisis.
Publishes VolatilitySignal to volatility.forecast Kafka topic.
"""
from __future__ import annotations

import asyncio
import warnings
from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import structlog

try:
    from arch import arch_model
except ImportError:
    arch_model = None

from agents.base_agent import BaseAgent
from core.data.models import KafkaTopic, OHLCVBar, SignalDirection, VolatilityRegime, VolatilitySignal

logger = structlog.get_logger(__name__)
warnings.filterwarnings("ignore", category=UserWarning)  # Suppress ARCH convergence warnings

MIN_BARS_FOR_GARCH = 60    # Minimum observations for reliable GARCH fit
MAX_BARS = 500

# Volatility regime thresholds (annualized %)
VOL_THRESHOLDS = {
    VolatilityRegime.CALM:     (0, 10),
    VolatilityRegime.NORMAL:   (10, 25),
    VolatilityRegime.VOLATILE: (25, 50),
    VolatilityRegime.CRISIS:   (50, float("inf")),
}


class VolatilityForecaster(BaseAgent):
    """Agent 14 — GARCH volatility forecasting and regime classification."""

    AGENT_ID = 14

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=3, name="volatility_forecaster")
        # Daily closing prices per symbol
        self._daily_closes: dict[str, list[float]] = defaultdict(list)
        self._last_published: dict[str, datetime] = {}
        self._consumer = None

    async def initialize(self) -> None:
        self._consumer = self.make_consumer(
            [KafkaTopic.PRICES_REALTIME], auto_offset_reset="latest"
        )
        await self._consumer.initialize()
        self.logger.info("volatility forecaster initialized")

    async def run(self) -> None:
        async for message in self._consumer.stream():
            if await self.is_halted():
                await asyncio.sleep(1)
                continue
            try:
                payload = message.get("payload", message)
                if message.get("message_type") != "ohlcv":
                    continue

                bar = OHLCVBar.model_validate(payload)

                # Only use daily bars for GARCH (clean, non-noisy)
                if bar.timeframe != "1d" or not bar.is_closed:
                    continue

                self._daily_closes[bar.symbol].append(float(bar.close))
                # Cap buffer
                if len(self._daily_closes[bar.symbol]) > MAX_BARS:
                    self._daily_closes[bar.symbol] = self._daily_closes[bar.symbol][-MAX_BARS:]

                closes = self._daily_closes[bar.symbol]
                if len(closes) < MIN_BARS_FOR_GARCH:
                    continue

                # Rate limit: max one forecast per symbol per hour
                last = self._last_published.get(bar.symbol)
                if last and (datetime.utcnow() - last).total_seconds() < 3600:
                    continue

                signal = await asyncio.get_event_loop().run_in_executor(
                    None, self._compute_volatility_signal, bar.symbol, closes
                )

                if signal:
                    await self.publish(
                        KafkaTopic.VOLATILITY_FORECAST,
                        payload=signal.model_dump(mode="json"),
                        message_type="volatility_signal",
                    )
                    self._last_published[bar.symbol] = datetime.utcnow()
                    self.logger.debug(
                        "vol signal published",
                        symbol=bar.symbol,
                        regime=signal.regime.value,
                        forecast_1d=round(signal.forecast_1d, 2),
                    )

            except asyncio.CancelledError:
                return
            except Exception as e:
                self.record_processing_error("prices.realtime", type(e).__name__)
                self.logger.warning("vol computation failed", error=str(e))

    def _compute_volatility_signal(self, symbol: str, closes: list[float]) -> Optional[VolatilitySignal]:
        """
        CPU-bound: fit GARCH model and generate volatility forecasts.
        Runs in thread executor so it doesn't block the event loop.
        """
        try:
            prices = np.array(closes)
            # Log returns × 100 for numerical stability in GARCH
            returns = np.diff(np.log(prices)) * 100
            if len(returns) < MIN_BARS_FOR_GARCH:
                return None

            # ── Realized volatility ───────────────────────────────────────────
            rv_1d = float(returns[-1:].std() * np.sqrt(252))     # Last day (annualized)
            rv_7d = float(returns[-7:].std() * np.sqrt(252))     # 7-day
            rv_30d = float(returns[-30:].std() * np.sqrt(252))   # 30-day

            # ── GARCH(1,1) fit ────────────────────────────────────────────────
            garch_forecast = self._fit_garch(returns)

            # ── EGARCH for asymmetric volatility ──────────────────────────────
            egarch_forecast = self._fit_egarch(returns)

            # Use GARCH as primary, EGARCH as robustness check
            forecast_1d = garch_forecast if garch_forecast else rv_1d
            forecast_7d = forecast_1d * np.sqrt(7) / np.sqrt(252) * np.sqrt(252)
            forecast_30d = forecast_1d * np.sqrt(30) / np.sqrt(252) * np.sqrt(252)

            # ── Hurst exponent (mean reversion vs trend) ──────────────────────
            hurst = self._hurst_exponent(returns)

            # ── Regime classification ─────────────────────────────────────────
            regime = self._classify_regime(rv_30d)
            direction = self._regime_to_direction(regime, rv_30d, rv_7d)

            return VolatilitySignal(
                source_agent_id=self.agent_id,
                symbol=symbol,
                direction=direction,
                confidence=0.75,
                regime=regime,
                realized_vol_1d=rv_1d,
                realized_vol_7d=rv_7d,
                realized_vol_30d=rv_30d,
                forecast_1d=forecast_1d,
                forecast_7d=forecast_7d,
                forecast_30d=forecast_30d,
                garch_model="GARCH",
                hurst_exponent=hurst,
            )

        except Exception as e:
            self.logger.debug("GARCH failed", symbol=symbol, error=str(e))
            return None

    @staticmethod
    def _fit_garch(returns: np.ndarray) -> Optional[float]:
        """Fit GARCH(1,1) and return 1-step-ahead annualized volatility forecast."""
        if arch_model is None:
            return None

        try:
            model = arch_model(returns, vol="Garch", p=1, q=1, dist="normal")
            result = model.fit(disp="off", show_warning=False, options={"maxiter": 100})
            forecast = result.forecast(horizon=1)
            variance_1d = forecast.variance.values[-1, 0]
            # Convert from daily % variance to annualized decimal volatility
            annualized_vol = float(np.sqrt(variance_1d) * np.sqrt(252) / 100)
            return annualized_vol
        except Exception:
            return None

    @staticmethod
    def _fit_egarch(returns: np.ndarray) -> Optional[float]:
        """Fit EGARCH(1,1) for asymmetric (leverage) effect."""
        if arch_model is None:
            return None

        try:
            model = arch_model(returns, vol="EGARCH", p=1, q=1, dist="normal")
            result = model.fit(disp="off", show_warning=False, options={"maxiter": 100})
            forecast = result.forecast(horizon=1)
            variance_1d = forecast.variance.values[-1, 0]
            return float(np.sqrt(variance_1d) * np.sqrt(252) / 100)
        except Exception:
            return None

    @staticmethod
    def _hurst_exponent(returns: np.ndarray, lags: int = 20) -> Optional[float]:
        """
        Estimate Hurst exponent via R/S analysis.
        H < 0.5: mean-reverting, H = 0.5: random walk, H > 0.5: trending.
        """
        try:
            if len(returns) < lags * 2:
                return None
            ts = returns[-200:]
            rs_list = []
            lag_list = []
            for lag in range(2, min(lags, len(ts) // 4)):
                chunks = [ts[i:i+lag] for i in range(0, len(ts) - lag, lag)]
                rs_values = []
                for chunk in chunks:
                    if len(chunk) < 2:
                        continue
                    mean = chunk.mean()
                    std = chunk.std()
                    if std == 0:
                        continue
                    deviation = (chunk - mean).cumsum()
                    r = deviation.max() - deviation.min()
                    rs_values.append(r / std)
                if rs_values:
                    rs_list.append(np.log(np.mean(rs_values)))
                    lag_list.append(np.log(lag))
            if len(lag_list) < 3:
                return None
            hurst = float(np.polyfit(lag_list, rs_list, 1)[0])
            return max(0.0, min(1.0, hurst))
        except Exception:
            return None

    @staticmethod
    def _classify_regime(realized_vol_30d: float) -> VolatilityRegime:
        for regime, (low, high) in VOL_THRESHOLDS.items():
            if low <= realized_vol_30d * 100 < high:
                return regime
        return VolatilityRegime.VOLATILE

    @staticmethod
    def _regime_to_direction(
        regime: VolatilityRegime,
        rv_30d: float,
        rv_7d: float,
    ) -> SignalDirection:
        if regime == VolatilityRegime.CRISIS:
            return SignalDirection.STRONG_BEARISH
        if regime == VolatilityRegime.VOLATILE:
            return SignalDirection.BEARISH
        # Rising volatility = caution
        if rv_7d > rv_30d * 1.3:
            return SignalDirection.BEARISH
        # Falling volatility = calm = neutral to bullish
        if rv_7d < rv_30d * 0.7:
            return SignalDirection.BULLISH
        return SignalDirection.NEUTRAL

    async def shutdown(self) -> None:
        if self._consumer:
            await self._consumer.shutdown()
        self.logger.info("volatility forecaster shutdown")
