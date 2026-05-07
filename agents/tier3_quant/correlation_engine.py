"""
ALGHREST — Agent 15: Correlation Engine
Computes rolling correlation matrices (30d/90d/180d) and tests for cointegration.
Identifies pairs suitable for statistical arbitrage (Kalman spread trading).
Publishes CorrelationUpdate to correlation.matrix Kafka topic.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Optional

import numpy as np
import pandas as pd
import structlog
from statsmodels.tsa.stattools import adfuller, coint

from agents.base_agent import BaseAgent
from core.data.models import (
    CorrelationUpdate,
    KafkaTopic,
    OHLCVBar,
    SignalDirection,
    RISK_LIMITS,
)

logger = structlog.get_logger(__name__)

WINDOWS = [30, 90, 180]   # Rolling windows in days
MIN_BARS_FOR_CORR = 30
COINTEGRATION_PVALUE_THRESHOLD = 0.05
HIGH_CORRELATION_THRESHOLD = RISK_LIMITS.max_correlation_allowed  # 0.85

TRACKED_PAIRS = [
    ("BTC/USDT", "ETH/USDT"),
    ("ETH/USDT", "SOL/USDT"),
    ("BTC/USDT", "BNB/USDT"),
    ("ETH/USDT", "AVAX/USDT"),
    ("SOL/USDT", "AVAX/USDT"),
    ("ETH/USDT", "LINK/USDT"),
    ("BTC/USDT", "AVAX/USDT"),
]


class CorrelationEngine(BaseAgent):
    """Agent 15 — Rolling correlations, cointegration tests, and effective N."""

    AGENT_ID = 15
    PUBLISH_INTERVAL = 3600  # Recompute and publish every 1 hour

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=3, name="correlation_engine")
        # Daily closing prices per symbol
        self._daily_prices: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
        self._consumer = None
        self._last_published: Optional[datetime] = None

    async def initialize(self) -> None:
        self._consumer = self.make_consumer(
            [KafkaTopic.PRICES_REALTIME], auto_offset_reset="latest"
        )
        await self._consumer.initialize()
        self.logger.info("correlation engine initialized")

    async def run(self) -> None:
        """
        Consume price data to build price history,
        then publish correlation update every hour.
        """
        tasks = [
            asyncio.create_task(self._price_collection_loop(), name="price_collection"),
            asyncio.create_task(self._publication_loop(), name="correlation_publish"),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _price_collection_loop(self) -> None:
        async for message in self._consumer.stream():
            if await self.is_halted():
                await asyncio.sleep(1)
                continue
            try:
                payload = message.get("payload", message)
                if message.get("message_type") != "ohlcv":
                    continue
                bar = OHLCVBar.model_validate(payload)
                # Use daily bars only for clean correlation computation
                if bar.timeframe != "1d" or not bar.is_closed:
                    continue
                history = self._daily_prices[bar.symbol]
                # Dedup by date
                if history and history[-1][0].date() == bar.time.date():
                    history[-1] = (bar.time, float(bar.close))
                else:
                    history.append((bar.time, float(bar.close)))
                # Cap at 200 days
                self._daily_prices[bar.symbol] = history[-200:]
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.debug("price collection error", error=str(e))

    async def _publication_loop(self) -> None:
        """Publish correlation update every hour."""
        while True:
            if await self.is_halted():
                await asyncio.sleep(60)
                continue

            await asyncio.sleep(self.PUBLISH_INTERVAL)

            try:
                update = await asyncio.get_event_loop().run_in_executor(
                    None, self._compute_all_correlations
                )
                if update:
                    await self.publish(
                        KafkaTopic.CORRELATION_MATRIX,
                        payload=update.model_dump(mode="json"),
                        message_type="correlation_update",
                    )
                    self._last_published = datetime.utcnow()
                    self.logger.info(
                        "correlation update published",
                        symbols=len(update.symbols),
                        cointegrated_pairs=len(update.cointegrated_pairs),
                        high_corr_pairs=len(update.high_correlation_pairs),
                        effective_n=round(update.effective_n, 2),
                    )
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error("correlation computation failed", error=str(e))

    def _compute_all_correlations(self) -> Optional[CorrelationUpdate]:
        """CPU-bound computation: correlations, cointegration, effective N."""
        # Get symbols with at least 30 days of data
        eligible = {
            sym: prices for sym, prices in self._daily_prices.items()
            if len(prices) >= MIN_BARS_FOR_CORR
        }
        if len(eligible) < 2:
            return None

        # Build price DataFrame aligned on dates
        dfs = {}
        for sym, history in eligible.items():
            dfs[sym] = pd.Series(
                [p for _, p in history],
                index=[t for t, _ in history],
                name=sym,
            )
        price_df = pd.DataFrame(dfs).dropna()

        if price_df.shape[1] < 2 or len(price_df) < MIN_BARS_FOR_CORR:
            return None

        # ── Rolling correlations (90d window as default) ──────────────────
        returns_df = np.log(price_df / price_df.shift(1)).dropna()
        corr_90d = returns_df.tail(90).corr()

        # Build nested dict for serialization
        symbols = list(corr_90d.columns)
        corr_matrix = {
            sym1: {
                sym2: float(corr_90d.loc[sym1, sym2])
                for sym2 in symbols
            }
            for sym1 in symbols
        }

        # ── High correlation pairs ─────────────────────────────────────────
        high_corr_pairs = []
        for i, s1 in enumerate(symbols):
            for s2 in symbols[i+1:]:
                corr_val = corr_90d.loc[s1, s2]
                if abs(corr_val) >= HIGH_CORRELATION_THRESHOLD:
                    high_corr_pairs.append((s1, s2, float(corr_val)))

        # ── Cointegration tests ────────────────────────────────────────────
        cointegrated_pairs = []
        for s1, s2 in TRACKED_PAIRS:
            if s1 not in price_df.columns or s2 not in price_df.columns:
                continue
            pair_data = price_df[[s1, s2]].dropna()
            if len(pair_data) < 60:
                continue
            result = self._test_cointegration(pair_data[s1].values, pair_data[s2].values)
            if result:
                cointegrated_pairs.append((s1, s2, result))

        # ── Effective N ────────────────────────────────────────────────────
        try:
            effective_n = self._compute_effective_n(returns_df.tail(90).values)
        except Exception:
            effective_n = float(len(symbols))

        return CorrelationUpdate(
            source_agent_id=self.agent_id,
            window_days=90,
            symbols=symbols,
            correlation_matrix=corr_matrix,
            cointegrated_pairs=cointegrated_pairs,
            high_correlation_pairs=high_corr_pairs,
            effective_n=effective_n,
        )

    @staticmethod
    def _test_cointegration(price_a: np.ndarray, price_b: np.ndarray) -> Optional[float]:
        """
        Engle-Granger cointegration test.
        Returns estimated half-life in days if cointegrated, else None.
        """
        try:
            _, pvalue, _ = coint(price_a, price_b)
            if pvalue > COINTEGRATION_PVALUE_THRESHOLD:
                return None

            # Estimate half-life via OLS spread
            spread = price_a - price_b
            spread_lag = spread[:-1]
            spread_diff = np.diff(spread)
            # Simple OLS: Δspread_t = φ * spread_{t-1} + ε
            phi = np.polyfit(spread_lag, spread_diff, 1)[0]
            if phi >= 0:
                return None  # Not mean-reverting
            half_life = -np.log(2) / phi
            if half_life <= 0 or half_life > 252:
                return None  # Unreasonably long
            return float(half_life)
        except Exception:
            return None

    @staticmethod
    def _compute_effective_n(returns_matrix: np.ndarray) -> float:
        """
        Effective number of independent bets via eigenvalue entropy.
        Low value = concentrated book, High = well diversified.
        """
        if returns_matrix.shape[1] < 2:
            return 1.0
        corr = np.corrcoef(returns_matrix.T)
        eigenvalues = np.linalg.eigvalsh(corr)
        eigenvalues = eigenvalues[eigenvalues > 1e-10]
        normalized = eigenvalues / eigenvalues.sum()
        entropy = -np.sum(normalized * np.log(normalized + 1e-12))
        return float(np.exp(entropy))

    async def shutdown(self) -> None:
        if self._consumer:
            await self._consumer.shutdown()
        self.logger.info("correlation engine shutdown")
