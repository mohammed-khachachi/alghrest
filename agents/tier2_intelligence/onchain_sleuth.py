"""
ALGHREST — Agent 09: On-Chain Sleuth
Monitors whale movements, exchange flows, and on-chain health metrics.
Sources: Glassnode API, Nansen, Etherscan, Dune Analytics.
Publishes OnChainSignal + WhaleAlert to onchain.signals Kafka topic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Optional

import httpx
import structlog

from agents.base_agent import BaseAgent
from core.config import settings
from core.data.models import Chain, KafkaTopic, OnChainSignal, SignalDirection, WhaleAlert

logger = structlog.get_logger(__name__)

GLASSNODE_BASE = "https://api.glassnode.com/v1/metrics"

# Glassnode metrics to poll (metric_path, friendly_name, asset)
GLASSNODE_METRICS = [
    ("transactions/transfers_volume_exchanges_net", "ExchangeNetFlow",   "BTC"),
    ("transactions/transfers_volume_exchanges_net", "ExchangeNetFlow",   "ETH"),
    ("indicators/sopr",                             "SOPR",              "BTC"),
    ("indicators/nvt",                              "NVT",               "BTC"),
    ("market/price_usd_ohlc",                       "Price",             "BTC"),
    ("addresses/active_count",                       "ActiveAddresses",   "BTC"),
    ("mining/hash_rate_mean",                        "HashRate",          "BTC"),
    ("supply/current",                               "CirculatingSupply", "ETH"),
]

# Whale threshold: transactions above this USD value trigger alerts
WHALE_THRESHOLD_USD = 1_000_000


class OnChainSleuth(BaseAgent):
    """Agent 09 — Tracks whale movements and on-chain health metrics."""

    AGENT_ID = 9

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="onchain_sleuth")
        self._glassnode_client: Optional[httpx.AsyncClient] = None
        self._etherscan_client: Optional[httpx.AsyncClient] = None
        self._previous_values: dict[str, float] = {}

    async def initialize(self) -> None:
        if settings.glassnode_api_key:
            self._glassnode_client = httpx.AsyncClient(
                base_url=GLASSNODE_BASE,
                timeout=30.0,
                params={"api_key": settings.glassnode_api_key},
            )
            self.logger.info("Glassnode client initialized")
        else:
            self.logger.warning("GLASSNODE_API_KEY not set — on-chain metrics limited")

        if settings.ethereum_rpc_url:
            self._etherscan_client = httpx.AsyncClient(
                base_url="https://api.etherscan.io/api",
                timeout=20.0,
            )
            self.logger.info("Etherscan client initialized")

        self.logger.info("on-chain sleuth ready")

    async def run(self) -> None:
        """Poll on-chain metrics every 15 minutes, whale alerts every 5 minutes."""
        tasks = [
            asyncio.create_task(self._metrics_polling_loop(), name="glassnode_poll"),
            asyncio.create_task(self._whale_alert_loop(), name="whale_alerts"),
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    # ── GLASSNODE METRICS ─────────────────────────────────────────────────────

    async def _metrics_polling_loop(self) -> None:
        while True:
            if await self.is_halted():
                await asyncio.sleep(60)
                continue
            try:
                await self._poll_glassnode_metrics()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.error("Glassnode polling error", error=str(e))
            await asyncio.sleep(900)  # 15 minutes

    async def _poll_glassnode_metrics(self) -> None:
        if not self._glassnode_client:
            return

        for metric_path, metric_name, asset in GLASSNODE_METRICS:
            try:
                r = await self._glassnode_client.get(
                    f"/{metric_path}",
                    params={
                        "a": asset,
                        "i": "24h",           # Daily resolution
                        "limit": 2,
                        "format": "JSON",
                    },
                )
                r.raise_for_status()
                data = r.json()

                if not data or len(data) == 0:
                    continue

                latest = data[-1]
                current_value = None

                # Handle different response structures
                if isinstance(latest.get("v"), (int, float)):
                    current_value = float(latest["v"])
                elif isinstance(latest.get("o"), dict):
                    current_value = float(latest["o"].get("c", 0))

                if current_value is None:
                    continue

                prev_key = f"{asset}:{metric_name}"
                prev_value = self._previous_values.get(prev_key)
                change_pct = None
                if prev_value and prev_value != 0:
                    change_pct = (current_value - prev_value) / abs(prev_value) * 100
                self._previous_values[prev_key] = current_value

                # Determine signal direction from metric semantics
                direction = self._classify_metric(metric_name, current_value, change_pct)

                signal = OnChainSignal(
                    source_agent_id=self.agent_id,
                    symbol=asset,
                    direction=direction,
                    confidence=0.65,
                    metric=metric_name,
                    value=current_value,
                    previous_value=prev_value,
                    change_24h_pct=change_pct,
                    chain=Chain.ETHEREUM if asset == "ETH" else Chain.ETHEREUM,
                    data_source="glassnode",
                )

                await self.publish(
                    KafkaTopic.ONCHAIN_SIGNALS,
                    payload=signal.model_dump(mode="json"),
                    message_type="onchain_signal",
                )

                self.logger.debug(
                    "on-chain metric published",
                    metric=metric_name,
                    asset=asset,
                    value=round(current_value, 4),
                    change_pct=round(change_pct, 2) if change_pct else None,
                )

                await asyncio.sleep(0.5)  # Respect Glassnode rate limits

            except Exception as e:
                self.logger.debug("Glassnode metric failed", metric=metric_path, error=str(e))

    @staticmethod
    def _classify_metric(metric_name: str, value: float, change_pct: Optional[float]) -> SignalDirection:
        """Rule-based directional classification per metric type."""
        if metric_name == "ExchangeNetFlow":
            # Negative flow (outflow from exchanges) = bullish (users hodling)
            if value < -10_000_000:
                return SignalDirection.BULLISH
            elif value > 10_000_000:
                return SignalDirection.BEARISH
            return SignalDirection.NEUTRAL

        if metric_name == "SOPR":
            # SOPR > 1 = profitable sells, < 1 = loss sellers (capitulation = buy signal)
            if value < 0.98:
                return SignalDirection.BULLISH  # Capitulation = dip buy
            elif value > 1.05:
                return SignalDirection.BEARISH  # Profit taking
            return SignalDirection.NEUTRAL

        if metric_name == "NVT":
            # NVT > 90 = overvalued, < 30 = undervalued
            if value < 30:
                return SignalDirection.STRONG_BULLISH
            elif value > 90:
                return SignalDirection.BEARISH
            return SignalDirection.NEUTRAL

        if metric_name == "ActiveAddresses" and change_pct:
            # Rising active addresses = bullish adoption
            if change_pct > 15:
                return SignalDirection.BULLISH
            elif change_pct < -15:
                return SignalDirection.BEARISH

        return SignalDirection.NEUTRAL

    # ── WHALE ALERTS ──────────────────────────────────────────────────────────

    async def _whale_alert_loop(self) -> None:
        """Check for large blockchain transactions every 5 minutes."""
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue
            try:
                await self._check_whale_transactions()
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.logger.debug("whale alert check error", error=str(e))
            await asyncio.sleep(300)  # 5 minutes

    async def _check_whale_transactions(self) -> None:
        """
        Uses Whale Alert API (free tier) to find large crypto transfers.
        Falls back to Etherscan large transfer monitoring.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # Whale Alert public API (limited)
                r = await client.get(
                    "https://api.whale-alert.io/v1/transactions",
                    params={
                        "api_key": "free",  # Replace with real key
                        "min_value": WHALE_THRESHOLD_USD,
                        "limit": 10,
                    },
                )
                if r.status_code != 200:
                    return
                data = r.json()

        except Exception:
            return  # Whale Alert unavailable — not critical

        for tx in data.get("transactions", []):
            amount_usd = tx.get("amount_usd", 0)
            if amount_usd < WHALE_THRESHOLD_USD:
                continue

            from_label = tx.get("from", {}).get("owner", "Unknown")
            to_label = tx.get("to", {}).get("owner", "Unknown")

            alert = WhaleAlert(
                chain=Chain.ETHEREUM,
                asset=tx.get("symbol", "BTC").upper(),
                amount=Decimal(str(tx.get("amount", 0))),
                amount_usd=Decimal(str(amount_usd)),
                from_address=tx.get("from", {}).get("address", ""),
                to_address=tx.get("to", {}).get("address", ""),
                from_label=from_label,
                to_label=to_label,
                tx_hash=tx.get("hash", ""),
                block_number=tx.get("transaction_count", 0),
                timestamp=datetime.utcfromtimestamp(tx.get("timestamp", 0)),
                is_exchange_inflow="exchange" in to_label.lower(),
                is_exchange_outflow="exchange" in from_label.lower(),
            )

            # Determine directional bias
            if alert.is_exchange_inflow:
                direction = SignalDirection.BEARISH  # Moving to exchange = potential sell
            elif alert.is_exchange_outflow:
                direction = SignalDirection.BULLISH   # Withdrawing from exchange = hodling
            else:
                direction = SignalDirection.NEUTRAL

            signal = OnChainSignal(
                source_agent_id=self.agent_id,
                symbol=alert.asset,
                direction=direction,
                confidence=0.7,
                metric="whale_transfer",
                value=float(alert.amount_usd),
                whale_threshold_usd=Decimal(str(WHALE_THRESHOLD_USD)),
                chain=alert.chain,
                addresses_involved=[alert.from_address[:20], alert.to_address[:20]],
                data_source="whale_alert",
                metadata={
                    "from_label": from_label,
                    "to_label": to_label,
                    "amount_usd": float(amount_usd),
                    "tx_hash": alert.tx_hash[:20],
                },
            )

            await self.publish(
                KafkaTopic.ONCHAIN_SIGNALS,
                payload=signal.model_dump(mode="json"),
                message_type="whale_alert",
            )

            self.logger.info(
                "whale alert published",
                asset=alert.asset,
                amount_usd=f"${amount_usd:,.0f}",
                from_label=from_label,
                to_label=to_label,
                direction=direction.value,
            )

    async def shutdown(self) -> None:
        if self._glassnode_client:
            await self._glassnode_client.aclose()
        if self._etherscan_client:
            await self._etherscan_client.aclose()
        self.logger.info("on-chain sleuth shutdown")
