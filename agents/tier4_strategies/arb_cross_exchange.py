"""
Agent 18 — Cross-Exchange Arbitrage
Strategy: Monitor bid/ask spread across Binance/Bybit/Coinbase.
Execute simultaneous buy on cheaper + sell on more expensive when net spread > fees + slippage.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any, Optional

import pandas as pd
import structlog

from agents.base_agent import BaseStrategy
from connectors.exchanges.ccxt_connector import MultiExchangeConnector
from core.data.models import (
    AgentConfig,
    AssetClass,
    BacktestResult,
    Exchange,
    KafkaTopic,
    MarketState,
    OrderSide,
    OrderType,
    Position,
    Timeframe,
    TradeProposal,
)

log = structlog.get_logger(__name__)

_MIN_NET_SPREAD_BPS = 15
_FEE_BPS: dict[Exchange, float] = {
    Exchange.BINANCE: 7.5,
    Exchange.BYBIT: 10.0,
    Exchange.COINBASE: 20.0,
}
_SLIPPAGE_BPS = 5.0
_MAX_ARB_SIZE_USD = Decimal("5000")
_POLL_INTERVAL = 0.5
_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]


class CrossExchangeArb(BaseStrategy):
    AGENT_ID = 18
    strategy_id = "arb_cross_exchange"
    capital_pct = 0.08
    max_positions = 3
    risk_per_trade = 0.003

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="CrossExchangeArb",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        self._connector = MultiExchangeConnector()
        self._active_arbs: set[str] = set()

    # ─── Lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        await self._connector.connect_all([Exchange.BINANCE, Exchange.BYBIT, Exchange.COINBASE])
        log.info("arb_cross_exchange.initialized", exchanges=list(_FEE_BPS.keys()))

    async def run(self) -> None:
        while True:
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(5)
                continue
            for symbol in _SYMBOLS:
                try:
                    await self._scan(symbol)
                except Exception as exc:
                    self.record_processing_error("ticker", type(exc).__name__)
                    log.warning("arb.scan_error", symbol=symbol, error=str(exc))
            await asyncio.sleep(_POLL_INTERVAL)

    async def shutdown(self) -> None:
        await self._connector.close_all()
        log.info("arb_cross_exchange.shutdown")

    # ─── Scan ─────────────────────────────────────────────────────────────────

    async def _scan(self, symbol: str) -> None:
        if symbol in self._active_arbs:
            return

        tickers = await self._connector.fetch_all_tickers(symbol)
        if len(tickers) < 2:
            return

        best_ask: Optional[tuple[Exchange, float]] = None
        best_bid: Optional[tuple[Exchange, float]] = None

        for exchange, ticker in tickers.items():
            if exchange not in _FEE_BPS:
                continue
            ask = ticker.get("ask")
            bid = ticker.get("bid")
            if ask and (best_ask is None or ask < best_ask[1]):
                best_ask = (exchange, float(ask))
            if bid and (best_bid is None or bid > best_bid[1]):
                best_bid = (exchange, float(bid))

        if best_ask is None or best_bid is None or best_ask[0] == best_bid[0]:
            return

        buy_exchange, ask_price = best_ask
        sell_exchange, bid_price = best_bid
        if ask_price <= 0:
            return

        raw_spread_bps = (bid_price - ask_price) / ask_price * 10_000
        total_fee_bps = _FEE_BPS[buy_exchange] + _FEE_BPS[sell_exchange] + _SLIPPAGE_BPS
        net_spread_bps = raw_spread_bps - total_fee_bps

        if net_spread_bps < _MIN_NET_SPREAD_BPS:
            return

        await self._execute_arb(symbol, buy_exchange, ask_price, sell_exchange, bid_price, net_spread_bps)

    async def _execute_arb(
        self,
        symbol: str,
        buy_exchange: Exchange,
        buy_price: float,
        sell_exchange: Exchange,
        sell_price: float,
        net_spread_bps: float,
    ) -> None:
        self._active_arbs.add(symbol)
        try:
            portfolio = await self.state.get_portfolio()
            if portfolio is None:
                return

            arb_capital = portfolio.total_capital * Decimal(str(self.capital_pct))
            size_usd = min(_MAX_ARB_SIZE_USD, arb_capital / Decimal(str(self.max_positions)))
            if size_usd < Decimal("20"):
                return

            qty_buy = size_usd / Decimal(str(buy_price))
            qty_sell = size_usd / Decimal(str(sell_price))

            buy_proposal = TradeProposal(
                strategy_id=f"{self.strategy_id}_buy",
                agent_id=self.AGENT_ID,
                symbol=symbol,
                exchange=buy_exchange,
                asset_class=AssetClass.CRYPTO,
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                size=qty_buy.quantize(Decimal("0.000001")),
                size_usd=size_usd.quantize(Decimal("0.01")),
                limit_price=Decimal(str(round(buy_price, 2))),
                stop_loss=Decimal(str(round(buy_price * 0.995, 2))),
                take_profit=Decimal(str(round(sell_price, 2))),
                urgency="immediate",
                confidence_score=0.85,
                rationale=f"ARB buy@{buy_exchange.value} spread={net_spread_bps:.1f}bps",
            )
            sell_proposal = TradeProposal(
                strategy_id=f"{self.strategy_id}_sell",
                agent_id=self.AGENT_ID,
                symbol=symbol,
                exchange=sell_exchange,
                asset_class=AssetClass.CRYPTO,
                side=OrderSide.SELL,
                order_type=OrderType.LIMIT,
                size=qty_sell.quantize(Decimal("0.000001")),
                size_usd=size_usd.quantize(Decimal("0.01")),
                limit_price=Decimal(str(round(sell_price, 2))),
                stop_loss=Decimal(str(round(sell_price * 1.005, 2))),
                take_profit=Decimal(str(round(buy_price, 2))),
                urgency="immediate",
                confidence_score=0.85,
                rationale=f"ARB sell@{sell_exchange.value} spread={net_spread_bps:.1f}bps",
            )

            await asyncio.gather(
                self.publish(KafkaTopic.PROPOSALS_BUS, buy_proposal.model_dump(mode="json"), "TradeProposal"),
                self.publish(KafkaTopic.PROPOSALS_BUS, sell_proposal.model_dump(mode="json"), "TradeProposal"),
            )
            log.info(
                "arb.opportunity",
                symbol=symbol,
                buy_exchange=buy_exchange.value,
                sell_exchange=sell_exchange.value,
                net_bps=round(net_spread_bps, 2),
                size_usd=float(size_usd),
            )
        finally:
            await asyncio.sleep(2.0)
            self._active_arbs.discard(symbol)

    # ─── Strategy interface ───────────────────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> Optional[TradeProposal]:
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        return False

    def backtest(self, data: pd.DataFrame, params: dict[str, Any]) -> BacktestResult:
        # Cross-exchange arb cannot be backtested on single-exchange OHLCV; return placeholder.
        from core.data.models import BacktestResult as BR
        from datetime import datetime
        return BR(
            strategy_id=self.strategy_id,
            strategy_name="CrossExchangeArb",
            symbol="BTC/USDT",
            timeframe=Timeframe.M1,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow(),
            initial_capital=Decimal("100000"),
            final_capital=Decimal("100000"),
            total_return_pct=0.0,
            annualized_return_pct=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_duration_days=0,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate_pct=0.0,
            profit_factor=0.0,
            avg_return_per_trade_pct=0.0,
            avg_winning_trade_pct=0.0,
            avg_losing_trade_pct=0.0,
            largest_winner_pct=0.0,
            largest_loser_pct=0.0,
            max_consecutive_losses=0,
            avg_holding_hours=0.0,
            trades_per_year=0.0,
            passed_validation=False,
            failure_reasons=["Cross-exchange arb requires multi-exchange tick data"],
        )
