"""Agent 38: public production prices for configured simulated spot accounts."""

import asyncio
from datetime import UTC, datetime

import httpx

from agents.base_agent import BaseAgent
from connectors.advisory.market import PublicMarkets
from core.config import settings


class PaperMarketFeed(BaseAgent):
    AGENT_ID = 38

    def __init__(self) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=2, name="paper_market_feed")
        self.client: httpx.AsyncClient | None = None

    async def initialize(self) -> None:
        if (
            settings.environment != "paper_trading"
            or not settings.execution_accounts
            or any(a.exchange.value != "binance" for a in settings.execution_accounts)
        ):
            raise ValueError("Paper public feed requires explicit Binance paper accounts")
        self.client = httpx.AsyncClient(
            timeout=8, limits=httpx.Limits(max_connections=2, max_keepalive_connections=2)
        )

    async def refresh(self) -> None:
        assert self.client is not None
        markets = PublicMarkets(self.client)
        pairs = sorted({symbol for a in settings.execution_accounts for symbol in a.symbols})
        for symbol in [*pairs, "USDT/USD"]:
            try:
                observation = await (
                    markets.tether_usd() if symbol == "USDT/USD" else markets.spot(symbol)
                )
                age = (datetime.now(UTC) - observation.timestamp).total_seconds()
                if not 0 <= age <= settings.accounting_mark_max_age_seconds:
                    raise ValueError("Source mark stale/future")
                await self.state.set_accounting_mark(
                    "binance",
                    symbol,
                    str(observation.price),
                    observation.timestamp.isoformat(),
                    int(observation.timestamp.timestamp() * 1000),
                )
                await self.state.set_json(
                    f"accounting:mark-source:binance:{symbol}",
                    observation.model_dump(mode="json"),
                    ttl=120,
                )
                # Cross-venue USDT/USD is an explicit reporting conversion, never
                # an executable Binance market or an assumed USD peg.
                if symbol != "USDT/USD":
                    await self.state.set_json(
                        f"prices:{symbol}",
                        {
                            "last": float(observation.price),
                            "exchange": "binance",
                            "ts": observation.timestamp.isoformat(),
                            "source": str(observation.source),
                        },
                        ttl=60,
                    )
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                self.logger.warning(
                    "paper_mark_unavailable", symbol=symbol, error_type=type(exc).__name__
                )

    async def run(self) -> None:
        while True:
            # Valuation and risk monitoring require prices even while halted.
            await self.refresh()
            await asyncio.sleep(15)

    async def shutdown(self) -> None:
        if self.client:
            await self.client.aclose()
