"""
ALGHREST — Agent 08: Macro Economist
Monitors FRED API (Fed rate, CPI, NFP, yield curve) and economic calendar.
Classifies current macro regime: Risk-On / Risk-Off / Neutral / Crisis.
Publishes MacroSignal to macro.regime Kafka topic.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import KafkaTopic, MacroSignal, MarketRegime, SignalDirection

logger = structlog.get_logger(__name__)

# FRED series IDs → friendly names
FRED_SERIES = {
    "FEDFUNDS": ("FedFundsRate", "Fed Funds Rate", "HIGH"),
    "CPIAUCSL": ("CPI_YoY", "CPI All Items", "HIGH"),
    "UNRATE": ("UnemploymentRate", "Unemployment", "HIGH"),
    "T10Y2Y": ("YieldSpread10Y2Y", "Yield Curve Spread", "HIGH"),
    "DXY": ("DXY", "Dollar Index", "MEDIUM"),
    "T10YIE": ("InflationExp10Y", "10Y Breakeven Inflation", "MEDIUM"),
    "DCOILWTICO": ("WTI_Oil", "WTI Crude Oil", "MEDIUM"),
    "VIXCLS": ("VIX", "VIX Fear Index", "HIGH"),
    "SP500": ("SP500", "S&P 500", "MEDIUM"),
    "GOLDAMGBD228NLBM": ("Gold", "Gold Price", "LOW"),
}


class MacroEconomist(BaseAgent):
    """Agent 08 — Macro regime classification from economic indicators."""

    AGENT_ID = 8
    POLL_INTERVAL = 3600  # Re-check macro data every hour (most is daily/monthly)

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="macro_economist")
        self._fred_client: httpx.AsyncClient | None = None
        self._current_regime = MarketRegime.NEUTRAL
        self._macro_data: dict[str, Any] = {}

    async def initialize(self) -> None:
        if not settings.fred_api_key:
            self.logger.warning("FRED_API_KEY not set — macro data limited")

        self._fred_client = httpx.AsyncClient(
            base_url="https://api.stlouisfed.org/fred",
            timeout=30.0,
            params={"api_key": settings.fred_api_key, "file_type": "json"},
        )
        # Fetch initial macro state
        await self._refresh_all_indicators()
        self.logger.info("macro economist initialized", regime=self._current_regime.value)

    async def run(self) -> None:
        while True:
            if await self.is_halted():
                await asyncio.sleep(60)
                continue
            try:
                await self._refresh_all_indicators()
                regime = self._classify_regime()

                if regime != self._current_regime:
                    self.logger.info(
                        "macro regime changed",
                        old=self._current_regime.value,
                        new=regime.value,
                    )
                    self._current_regime = regime

                await self._publish_regime_signal(regime)

            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error("macro refresh error", error=str(e))

            await asyncio.sleep(self.POLL_INTERVAL)

    async def _refresh_all_indicators(self) -> None:
        """Fetch all FRED series concurrently."""
        tasks = {
            series_id: asyncio.create_task(self._fetch_fred_series(series_id))
            for series_id in FRED_SERIES
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for series_id, result in zip(tasks.keys(), results, strict=False):
            if isinstance(result, Exception):
                self.logger.debug("FRED series unavailable", series=series_id, error=str(result))
                continue
            if result is not None:
                friendly_name = FRED_SERIES[series_id][0]
                self._macro_data[friendly_name] = result

    async def _fetch_fred_series(self, series_id: str) -> dict[str, Any] | None:
        """Fetch latest observation from FRED."""
        if not settings.fred_api_key or not self._fred_client:
            return None
        try:
            r = await self._fred_client.get(
                "/series/observations",
                params={
                    "series_id": series_id,
                    "sort_order": "desc",
                    "limit": 2,  # Latest + previous for change calculation
                    "observation_start": (datetime.utcnow() - timedelta(days=90)).strftime(
                        "%Y-%m-%d"
                    ),
                },
            )
            r.raise_for_status()
            observations = r.json().get("observations", [])
            if not observations:
                return None

            latest = observations[0]
            previous = observations[1] if len(observations) > 1 else None

            value = float(latest["value"]) if latest["value"] != "." else None
            prev_value = float(previous["value"]) if previous and previous["value"] != "." else None

            return {
                "value": value,
                "previous": prev_value,
                "date": latest["date"],
                "change": (
                    (value - prev_value) if value is not None and prev_value is not None else None
                ),
            }
        except Exception:
            return None

    def _classify_regime(self) -> MarketRegime:
        """
        Rule-based regime classification from macro indicators.
        Can be replaced with ML model in future.
        """
        risk_on_signals = 0
        risk_off_signals = 0

        # VIX: < 20 = calm (risk on), > 30 = fear (risk off), > 45 = crisis
        vix = self._macro_data.get("VIX", {})
        if vix and vix.get("value"):
            v = vix["value"]
            if v > 45:
                return MarketRegime.CRISIS
            elif v > 30:
                risk_off_signals += 2
            elif v < 20:
                risk_on_signals += 2

        # Yield curve: inverted (T10Y2Y < 0) = recessionary signal
        yield_curve = self._macro_data.get("YieldSpread10Y2Y", {})
        if yield_curve and yield_curve.get("value") is not None:
            if yield_curve["value"] < -0.5:
                risk_off_signals += 2
            elif yield_curve["value"] > 0.5:
                risk_on_signals += 1

        # Fed Funds: rising rates = risk off for growth assets
        fed_rate = self._macro_data.get("FedFundsRate", {})
        if fed_rate and fed_rate.get("change"):
            if fed_rate["change"] > 0.25:  # Rate hike
                risk_off_signals += 1
            elif fed_rate["change"] < -0.25:  # Rate cut
                risk_on_signals += 1

        # CPI: high inflation = risk off (Fed will hike)
        cpi = self._macro_data.get("CPI_YoY", {})
        if cpi and cpi.get("value"):
            if cpi["value"] > 5.0:
                risk_off_signals += 1
            elif cpi["value"] < 3.0:
                risk_on_signals += 1

        # Unemployment: rising = risk off
        unemp = self._macro_data.get("UnemploymentRate", {})
        if unemp and unemp.get("change") and unemp["change"] > 0.3:
            risk_off_signals += 1

        # Net classification
        net = risk_on_signals - risk_off_signals
        if net >= 3:
            return MarketRegime.RISK_ON
        elif net <= -2:
            return MarketRegime.RISK_OFF
        else:
            return MarketRegime.NEUTRAL

    async def _publish_regime_signal(self, regime: MarketRegime) -> None:
        """Publish current macro regime to Kafka."""
        # Use Fed rate as the primary indicator value
        fed_data = self._macro_data.get("FedFundsRate", {})
        vix_data = self._macro_data.get("VIX", {})

        direction = {
            MarketRegime.RISK_ON: SignalDirection.BULLISH,
            MarketRegime.RISK_OFF: SignalDirection.BEARISH,
            MarketRegime.NEUTRAL: SignalDirection.NEUTRAL,
            MarketRegime.CRISIS: SignalDirection.STRONG_BEARISH,
        }[regime]

        signal = MacroSignal(
            source_agent_id=self.agent_id,
            direction=direction,
            confidence=0.7,  # Rule-based model confidence
            indicator_name="MACRO_REGIME",
            actual_value=vix_data.get("value"),
            regime=regime,
            country="US",
            metadata={
                "vix": vix_data.get("value"),
                "fed_rate": fed_data.get("value"),
                "yield_curve": self._macro_data.get("YieldSpread10Y2Y", {}).get("value"),
                "cpi": self._macro_data.get("CPI_YoY", {}).get("value"),
                "indicators_loaded": list(self._macro_data.keys()),
            },
        )

        await self.publish(
            KafkaTopic.MACRO_REGIME,
            payload=signal.model_dump(mode="json"),
            message_type="macro_regime",
        )

        # Cache in Redis for quick access by other agents
        await self.state.cache_signal(
            symbol="GLOBAL",
            signal_type="macro_regime",
            data={"regime": regime.value, "direction": direction.value},
            ttl=7200,
        )

    async def shutdown(self) -> None:
        if self._fred_client:
            await self._fred_client.aclose()
        self.logger.info("macro economist shutdown")
