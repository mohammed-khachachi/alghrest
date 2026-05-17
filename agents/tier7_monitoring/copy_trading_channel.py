import asyncio
from typing import Optional

from core.data.models import AgentConfig, KafkaTopic
from agents.base_agent import BaseAgent
from core.telegram.bot import TelegramBroadcaster

class CopyTradingAgent(BaseAgent):
    """
    Tier 7: Agent 36 - Copy Trading Broadcaster
    Listens to 'orders.filled' and 'strategy.signals' from Kafka 
    and broadcasts them to the public/premium Telegram Copy Trading Channel.
    """
    AGENT_ID = 36

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            tier=7,
            name="copy_trading_channel",
            config=config
        )
        self.broadcaster = TelegramBroadcaster()
        
    async def initialize(self) -> None:
        self.logger.info("Copy Trading Agent initialized. Subscribing to trade signals...")
        # Subscribe to strategy signals via Kafka consumer
        self.consumer = self.make_consumer([KafkaTopic.STRATEGY_SIGNALS, KafkaTopic.ORDERS_FILLED])

    async def run(self) -> None:
        try:
            await self.consumer.start()
            
            async for msg in self.consumer:
                if await self.is_halted():
                    await asyncio.sleep(5)
                    continue
                    
                payload = msg.payload
                
                # Check if it's a high-confidence strategy signal
                if msg.topic == KafkaTopic.STRATEGY_SIGNALS:
                    confidence = payload.get("confidence", 0.0)
                    
                    # Only broadcast signals with high confidence (>85%) to followers
                    if confidence >= 0.85:
                        self.logger.info("High confidence signal detected, broadcasting to Telegram...")
                        
                        symbol = payload.get("symbol")
                        direction = payload.get("direction")
                        strategy = payload.get("strategy_id")
                        
                        # In reality, fetch current market price from Redis
                        # For now, we mock the current price
                        current_price = await self.state.get_market_price(symbol) if hasattr(self.state, 'get_market_price') else 50000.0
                        
                        # Calculate mock TP/SL for copy traders
                        tp_offset = 1.05 if direction == "LONG" else 0.95
                        sl_offset = 0.98 if direction == "LONG" else 1.02
                        
                        await self.broadcaster.broadcast_signal(
                            symbol=symbol,
                            direction=direction,
                            price=current_price,
                            strategy=strategy,
                            confidence=confidence,
                            tp=current_price * tp_offset,
                            sl=current_price * sl_offset
                        )
                
                # Acknowledge Kafka message processing
                self._messages_processed += 1
                
        except Exception as e:
            self.logger.error("Error in Copy Trading Agent loop", error=str(e))
        finally:
            await self.consumer.stop()

    async def shutdown(self) -> None:
        await self.broadcaster.close()
        self.logger.info("Copy Trading Agent shutdown.")

if __name__ == "__main__":
    agent = CopyTradingAgent()
    asyncio.run(agent.start())
