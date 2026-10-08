"""Publish high-confidence, approved proposals using their actual prices and stops."""

import asyncio
from decimal import Decimal

from agents.base_agent import BaseAgent
from core.data.models import AgentConfig, KafkaTopic, OrderSide, TradeProposal
from core.orchestrator.message_bus import AlghrestConsumer
from core.telegram.bot import TelegramBroadcaster


class CopyTradingAgent(BaseAgent):
    AGENT_ID = 36

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(agent_id=self.AGENT_ID, tier=7, name="copy_trading_channel", config=config)
        self.broadcaster = TelegramBroadcaster()
        self.consumer: AlghrestConsumer | None = None

    async def initialize(self) -> None:
        self.consumer = self.make_consumer([KafkaTopic.PROPOSALS_APPROVED])
        await self.consumer.initialize()

    async def run(self) -> None:
        if self.consumer is None:
            raise RuntimeError("Copy trading agent must be initialized before running")
        async for message in self.consumer.stream():
            if await self.is_halted():
                continue
            try:
                proposal = TradeProposal.model_validate(message.get("payload", message))
                if proposal.confidence_score < 0.85:
                    continue
                price = proposal.limit_price
                if price is None:
                    quote = await self.state.get_json(f"prices:{proposal.symbol}")
                    if not quote or quote.get("price") is None:
                        continue
                    price = Decimal(str(quote["price"]))
                if not price.is_finite() or price <= 0:
                    continue
                await self.broadcaster.broadcast_signal(
                    symbol=proposal.symbol,
                    direction="LONG" if proposal.side == OrderSide.BUY else "SHORT",
                    price=float(price),
                    strategy=proposal.strategy_id,
                    confidence=proposal.confidence_score,
                    tp=float(proposal.take_profit) if proposal.take_profit is not None else None,
                    sl=float(proposal.stop_loss) if proposal.stop_loss is not None else None,
                )
                self._messages_processed += 1
            except Exception as exc:
                self.record_processing_error(
                    KafkaTopic.PROPOSALS_APPROVED.value, type(exc).__name__
                )
                self.logger.warning("copy trading proposal rejected", error=str(exc))

    async def shutdown(self) -> None:
        try:
            if self.consumer is not None:
                await self.consumer.shutdown()
        finally:
            await self.broadcaster.close()


if __name__ == "__main__":
    asyncio.run(CopyTradingAgent().start())
