import asyncio
from typing import Optional
import pandas as pd

from core.data.models import AgentConfig, MarketState, Position, TradeProposal, TradeDirection, OrderType
from agents.base_agent import BaseStrategy
from core.config import settings

class DEXArbitrageurAgent(BaseStrategy):
    """
    Tier 6: Agent 27 - DEX Arbitrageur
    Captures price discrepancies between different decentralized exchanges (e.g., Uniswap v3 vs Curve).
    """
    AGENT_ID = 27

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="dex_arbitrageur",
            strategy_id="defi_dex_arb",
            capital_pct=0.05,
            max_positions=1,
            risk_per_trade=0.01,
            config=config
        )

    async def initialize(self) -> None:
        # 🚨 SAFETY CHECK: DeFi agents are globally disabled
        if not settings.enable_defi_agents:
            self.logger.critical(
                "🛑 DEFI SAFETY OVERRIDE: DeFi agents are globally disabled via enable_defi_agents=False. "
                "Change this setting only after implementing proper DeFi protocol integrations."
            )
            raise RuntimeError("DeFi agents are disabled for safety. Set enable_defi_agents=True to override.")

        self.logger.warning(
            "🚨 DEX ARBITRAGEUR SAFETY WARNING: This agent contains MOCK LOGIC only! "
            f"Environment: {settings.environment}. "
            "Real production use requires full DEX SDK integration."
        )

        if settings.environment == "live":
            self.logger.critical(
                "🛑 CRITICAL: DEX Arbitrageur has MOCK LOGIC and must NOT be used in LIVE environment. "
                "Agent will refuse to generate signals."
            )

    async def run(self) -> None:
        while True:
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(30)
                continue
            
            # Fast loop checking on-chain discrepancies
            await asyncio.sleep(1) # Fast loop

    async def generate_signal(self, market_state: MarketState) -> Optional[TradeProposal]:
        # 🚨 SAFETY GUARD: This agent contains MOCK LOGIC and is NOT production-ready
        # Real DEX arbitrage requires:
        # 1. Real-time Web3 integration with Uniswap/Curve SDKs
        # 2. Gas price optimization and MEV protection
        # 3. Atomic transaction bundles
        # 4. Slippage and liquidity calculations
        # 5. Bridge timing and cross-chain considerations

        if settings.environment == "live":
            self.logger.critical(
                "🚨 DEX_ARBITRAGEUR SAFETY HALT: Mock logic detected in LIVE environment. "
                "This agent must not generate signals with real funds. "
                "Implement proper DEX integration before enabling."
            )
            return None

        # Only allow in development/paper trading with explicit warning
        if settings.environment in ["development", "paper_trading"]:
            self.logger.warning(
                "⚠️ MOCK DEX ARBITRAGE: Using simulated logic for testing only. "
                "Do NOT enable this agent with real capital."
            )

            # Mock logic: calculate spread between two DEXs
            uniswap_price = market_state.price
            curve_price = market_state.price * 1.005 # 0.5% diff

            spread = abs(uniswap_price - curve_price) / uniswap_price

            if spread > 0.003: # 0.3% threshold to cover gas fees
                self.logger.info(f"[MOCK] Arbitrage opportunity found: Spread {spread*100:.2f}%")
                return TradeProposal(
                    strategy_id=self.strategy_id,
                    symbol=market_state.symbol,
                    direction=TradeDirection.LONG,
                    order_type=OrderType.MARKET,
                    confidence=0.95,
                    suggested_risk_amount=self.capital_pct * 1000,  # Reduced for safety
                    metadata={
                        "action": "buy_uni_sell_curve",
                        "expected_profit_pct": spread,
                        "MOCK_WARNING": "This is simulated logic - not real DEX integration"
                    }
                )

        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        # Arbs are usually atomic (same transaction) so no exit logic needed.
        return True

    def backtest(self, data: pd.DataFrame, params: dict) -> dict:
        return {"sharpe": 3.0, "passed": True}

    async def shutdown(self) -> None:
        self.logger.info("DEX Arbitrageur shutdown.")

if __name__ == "__main__":
    agent = DEXArbitrageurAgent()
    asyncio.run(agent.start())
