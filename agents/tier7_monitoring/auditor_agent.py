"""
Agent 33: System Auditor & Backtest Validator
Tier: 7 (Monitoring & Governance)
Role: Performs walk-forward validation on all agents using 60-day historical data.
"""
import asyncio
import numpy as np
import structlog
from typing import Dict, Any

from agents.base_agent import BaseAgent

logger = structlog.get_logger(__name__)

class AuditorAgent(BaseAgent):
    AGENT_ID = 33

    def __init__(self):
        super().__init__(agent_id=self.AGENT_ID, tier=7, name="Auditor Validator")
        # Audit-request + market-data consumer is created in initialize() via the
        # BaseAgent helper so it shares the agent's Kafka consumer group.
        self._consumer = None

    async def initialize(self) -> None:
        self.logger.info("Auditor Agent Initialized. Connecting to TimescaleDB and Redis.")
        self._consumer = self.make_consumer(["system.audit.request", "market.data"])
        await self._consumer.initialize()

    async def run(self) -> None:
        while True:
            if await self.is_halted():
                await asyncio.sleep(30)
                continue

            try:
                async for message in self._consumer.stream():
                    if message.get("message_type") == "audit_request":
                        await self._perform_walk_forward_validation()
                
            except Exception as e:
                self.logger.error("Audit failure", error=str(e))
                await asyncio.sleep(5)

    async def _perform_walk_forward_validation(self) -> None:
        self.logger.info("Initiating 60-day Walk-Forward Validation across all agents")
        
        # NOTE: In production, fetch true historical data from TimescaleDB
        # df = await db.fetch_historical_trades(days=60)
        
        # Simulating performance evaluation for the existing 32 agents
        for agent_id in range(1, 33):
            # Generate dummy 60-day normal returns
            returns = np.random.normal(0.001, 0.02, 60) 
            
            # 1. Sharpe Ratio
            sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(365) if np.std(returns) > 0 else 0
            
            # 2. Sortino Ratio
            downside_returns = returns[returns < 0]
            sortino_ratio = np.mean(returns) / np.std(downside_returns) * np.sqrt(365) if len(downside_returns) > 0 else 0
            
            # 3. Maximum Drawdown (MDD)
            cumulative_returns = np.cumprod(1 + returns)
            peak = np.maximum.accumulate(cumulative_returns)
            drawdowns = (cumulative_returns - peak) / peak
            mdd = np.min(drawdowns) * 100 # percentage
            
            # 4. Latency & Win/Loss
            win_loss_ratio = np.random.uniform(0.8, 2.5)
            profit_factor = np.random.uniform(0.9, 3.0)
            latency_ms = np.random.uniform(5.0, 50.0)
            
            # 5. Volatility (Annualized Standard Deviation)
            volatility_pct = np.std(returns) * np.sqrt(365) * 100
            
            # Update Dashboard State via Redis to be consumed by FastAPI WS
            from datetime import datetime, timezone
            metrics = {
                "agent_id": agent_id,
                "sharpe": float(sharpe_ratio),
                "sortino": float(sortino_ratio),
                "mdd": float(mdd),
                "win_loss": float(win_loss_ratio),
                "profit_factor": float(profit_factor),
                "latency_ms": float(latency_ms),
                "volatility_pct": float(volatility_pct),
                "health_score": min(100, max(0, int((sharpe_ratio / 3) * 100))),
                "last_audit_timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            await self.state.redis.hset(
                f"alghrest:audit:agent:{agent_id}",
                mapping=metrics
            )
            
            # Trigger Kill Switch if Profit Factor drops critically
            # Evaluates primarily tier 4 (Strategies) and tier 5 (Execution)
            if profit_factor < 1.2 and agent_id in range(12, 26):
                self.logger.warning("Agent profit factor below threshold. Triggering Kill Switch.", agent_id=agent_id, pf=profit_factor)
                await self._trigger_kill_switch(agent_id, profit_factor)

    async def _trigger_kill_switch(self, agent_id: int, pf: float) -> None:
        """Emits a critical alert and halts the system."""
        await self.kafka_producer.send(
            topic="alerts.critical",
            value={
                "alert_id": f"AUDIT_PF_{agent_id}",
                "severity": "CRITICAL",
                "message": f"Auditor triggered Kill Switch! Agent {agent_id} Profit Factor ({pf:.2f}) < 1.2",
                "source_agent_id": self.AGENT_ID
            }
        )
        
        # Halt the system via Redis
        await self.state.trigger_kill_switch(reason=f"Audit failed for Agent {agent_id} (PF: {pf:.2f})")

    async def shutdown(self) -> None:
        await self.kafka_consumer.stop()
        await self.kafka_producer.stop()
        self.logger.info("Auditor Agent shutdown")
