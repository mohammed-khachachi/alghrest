"""
Agent 20 — Order Router
Smart order routing: selects the best exchange per symbol based on
spread, liquidity, fees, and latency. Converts TradeProposals → Orders.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import uuid4

import structlog

from agents.base_agent import BaseAgent
from connectors.exchanges.ccxt_connector import MultiExchangeConnector
from core.data.models import (
    AgentConfig,
    Exchange,
    KafkaTopic,
    Order,
    OrderStatus,
    OrderType,
    TradeProposal,
    TradeProposalStatus,
)

log = structlog.get_logger(__name__)

# Taker fee in basis points per exchange
_TAKER_FEES: dict[Exchange, float] = {
    Exchange.BINANCE:  7.5,
    Exchange.BYBIT:   10.0,
    Exchange.COINBASE: 20.0,
    Exchange.OKX:      8.0,
    Exchange.KRAKEN:  16.0,
}

_LARGE_ORDER_USD = Decimal("5000")   # Above this, use TWAP instead of MARKET
_PROPOSAL_TTL_SECONDS = 60            # Proposals older than 60s are stale


class OrderRouter(BaseAgent):
    """
    Agent 20 — Order Router.
    Consumes approved proposals from risk.assessments, selects the best
    exchange, and publishes Orders to orders.pending.
    """

    AGENT_ID = 20

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=5,
            name="OrderRouter",
            config=config,
        )
        self._connector = MultiExchangeConnector()
        self._routing_cache: dict[str, tuple[Exchange, datetime]] = {}  # symbol → (exchange, cached_at)
        self._cache_ttl = timedelta(seconds=30)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        await self._connector.connect_all(list(_TAKER_FEES.keys()))
        log.info("order_router.initialized", exchanges=list(_TAKER_FEES.keys()))

    async def run(self) -> None:
        consumer = self.make_consumer([KafkaTopic.PROPOSALS_APPROVED])
        await consumer.initialize()
        async for msg in consumer.stream():
            if await self.is_halted():
                continue
            try:
                payload = msg.get("payload", msg)
                await self._route(payload)
            except Exception as exc:
                log.error("order_router.route_error", error=str(exc))
                self.record_processing_error(KafkaTopic.PROPOSALS_APPROVED.value, type(exc).__name__)

    async def shutdown(self) -> None:
        await self._connector.close_all()
        log.info("order_router.shutdown")

    # ── Routing Logic ──────────────────────────────────────────────────────────

    async def _route(self, msg: dict) -> None:
        proposal = TradeProposal(**msg)

        if proposal.status != TradeProposalStatus.APPROVED:
            return

        # Stale check
        age = (datetime.utcnow() - proposal.created_at).total_seconds()
        if age > _PROPOSAL_TTL_SECONDS:
            log.warning("order_router.stale_proposal", proposal_id=str(proposal.proposal_id), age_s=round(age))
            return

        exchange = await self._select_exchange(proposal.symbol, proposal.size_usd)
        order_type = self._select_order_type(proposal)

        order = Order(
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            exchange=exchange,
            side=proposal.side,
            order_type=order_type,
            size=proposal.size,
            price=proposal.limit_price if order_type == OrderType.LIMIT else None,
            stop_price=proposal.stop_loss,
            time_in_force="GTC",
            status=OrderStatus.PENDING,
            strategy_id=proposal.strategy_id,
            agent_id=proposal.agent_id,
            algo_params=self._build_algo_params(proposal, order_type),
        )

        await self.publish(
            KafkaTopic.ORDERS_PENDING,
            order.model_dump(mode="json"),
            "Order",
        )
        log.info(
            "order_router.routed",
            symbol=proposal.symbol,
            exchange=exchange.value,
            order_type=order_type.value,
            size_usd=float(proposal.size_usd),
        )

    async def _select_exchange(self, symbol: str, size_usd: Decimal) -> Exchange:
        # Cache hit
        cached = self._routing_cache.get(symbol)
        if cached and (datetime.utcnow() - cached[1]) < self._cache_ttl:
            return cached[0]

        best_exchange = Exchange.BINANCE   # Default fallback
        best_score = float("inf")

        try:
            tickers = await self._connector.fetch_all_tickers(symbol)
            for exchange, ticker in tickers.items():
                if exchange not in _TAKER_FEES:
                    continue
                bid = ticker.get("bid", 0.0)
                ask = ticker.get("ask", 0.0)
                if bid <= 0 or ask <= 0:
                    continue
                spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
                fee_bps = _TAKER_FEES[exchange]
                total_cost = spread_bps + fee_bps
                if total_cost < best_score:
                    best_score = total_cost
                    best_exchange = exchange
        except Exception as exc:
            log.warning("order_router.ticker_fetch_failed", error=str(exc))

        self._routing_cache[symbol] = (best_exchange, datetime.utcnow())
        return best_exchange

    @staticmethod
    def _select_order_type(proposal: TradeProposal) -> OrderType:
        if proposal.order_type in (OrderType.TWAP, OrderType.VWAP):
            return proposal.order_type
        if proposal.size_usd >= _LARGE_ORDER_USD:
            return OrderType.TWAP
        if proposal.urgency == "immediate":
            return OrderType.MARKET
        if proposal.limit_price:
            return OrderType.LIMIT
        return OrderType.MARKET

    @staticmethod
    def _build_algo_params(proposal: TradeProposal, order_type: OrderType) -> dict:
        if order_type == OrderType.TWAP:
            return {
                "duration_minutes": 30,
                "num_slices": 6,
                "slice_interval_seconds": 300,
                "max_participation_rate": 0.10,
            }
        if order_type == OrderType.VWAP:
            return {
                "duration_minutes": 60,
                "max_participation_rate": 0.15,
            }
        return {}
