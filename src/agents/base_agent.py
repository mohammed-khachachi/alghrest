"""
ALGHREST — Base Agent Classes
All 32 agents inherit from BaseAgent. Tier 4 strategy agents also inherit BaseStrategy.

Lifecycle:
  initialize() → run() [loop] → shutdown()

Every agent gets:
  - Structured logging with agent context
  - Kafka producer + consumer
  - Redis state access
  - Prometheus metrics
  - Heartbeat reporting
  - Kill switch awareness
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any

import psutil
import structlog

from core.config import settings
from core.data.models import (
    AgentConfig,
    AgentHealth,
    AgentMessage,
    AgentStatus,
    BacktestResult,
    KafkaTopic,
    MarketState,
    Position,
    TradeProposal,
)
from core.orchestrator.message_bus import AlghrestConsumer, AlghrestProducer
from core.orchestrator.state_manager import state_manager
from core.utils.logging import configure_logging
from core.utils.metrics import (
    agent_memory_mb,
    agent_messages_failed,
    agent_messages_processed,
    agent_status as agent_status_metric,
    start_metrics_server,
)

if TYPE_CHECKING:
    import pandas as pd


class BaseAgent(ABC):
    """
    Abstract base for all 32 ALGHREST agents.
    Subclasses implement initialize(), run(), and shutdown().
    """

    def __init__(
        self, agent_id: int, tier: int, name: str, config: AgentConfig | None = None
    ) -> None:
        self.agent_id = agent_id
        self.tier = tier
        self.name = name
        self.config = config or AgentConfig(agent_id=agent_id, agent_name=name, tier=tier)
        self.status = AgentStatus.INITIALIZING
        self.start_time = datetime.utcnow()
        self._messages_processed = 0
        self._messages_failed = 0

        self.logger = structlog.get_logger(name).bind(agent_id=agent_id, tier=tier, agent=name)
        self.producer = AlghrestProducer()
        self.state = state_manager

    # ── ABSTRACT INTERFACE ────────────────────────────────────────────────────

    @abstractmethod
    async def initialize(self) -> None:
        """Setup connections, load models, validate config. Called once at startup."""

    @abstractmethod
    async def run(self) -> None:
        """Main agent loop — runs indefinitely until shutdown signal."""

    @abstractmethod
    async def shutdown(self) -> None:
        """Graceful shutdown: flush queues, close connections, persist state."""

    # ── LIFECYCLE ORCHESTRATION ───────────────────────────────────────────────

    async def start(self) -> None:
        """
        Full agent lifecycle: initialize → run → shutdown.
        Call this to start the agent as a long-running task.
        """
        settings.require_order_execution()
        configure_logging(settings.log_level, settings.environment)
        metrics_port = settings.metrics_base_port + self.agent_id
        start_metrics_server(metrics_port, host=settings.metrics_bind_host)

        self.logger.info("agent starting", metrics_port=metrics_port)

        tasks: list[asyncio.Task[None]] = []
        try:
            await self.state.initialize()
            await self.producer.initialize()
            await self.initialize()

            self.status = AgentStatus.RUNNING
            await self.state.set_agent_status(self.agent_id, AgentStatus.RUNNING)
            agent_status_metric.labels(
                agent_id=str(self.agent_id),
                agent_name=self.name,
                tier=str(self.tier),
            ).set(1)

            self.logger.info("agent running")

            tasks = [
                asyncio.create_task(self.run(), name=f"{self.name}.run"),
                asyncio.create_task(self._heartbeat_loop(), name=f"{self.name}.heartbeat"),
            ]
            await asyncio.gather(*tasks)

        except asyncio.CancelledError:
            self.logger.info("agent cancelled")
        except Exception as e:
            self.status = AgentStatus.ERROR
            self.logger.exception("agent crashed", error=str(e))
            raise
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await self._graceful_shutdown()

    async def _graceful_shutdown(self) -> None:
        self.status = AgentStatus.SHUTDOWN
        agent_status_metric.labels(
            agent_id=str(self.agent_id),
            agent_name=self.name,
            tier=str(self.tier),
        ).set(0)
        for cleanup in (self.shutdown, self.producer.shutdown, self.state.shutdown):
            try:
                await cleanup()
            except Exception as exc:
                self.logger.error("error during shutdown", error=str(exc))
        self.logger.info("agent shutdown complete")

    async def _heartbeat_loop(self) -> None:
        """Publish health status to Redis every 30 seconds."""
        while self.status == AgentStatus.RUNNING:
            try:
                health = await self.health_check()
                await self.state.set_agent_health(health, ttl_seconds=90)

                # Update Prometheus memory metric
                try:
                    proc = psutil.Process()
                    mem_mb = proc.memory_info().rss / 1_048_576
                    agent_memory_mb.labels(agent_id=str(self.agent_id), agent_name=self.name).set(
                        mem_mb
                    )
                except Exception:
                    pass

            except Exception as e:
                self.logger.warning("heartbeat failed", error=str(e))

            await asyncio.sleep(30)

    # ── MESSAGING ─────────────────────────────────────────────────────────────

    async def publish(
        self, topic: KafkaTopic, payload: dict[str, Any], message_type: str = ""
    ) -> None:
        """Publish an AgentMessage to a Kafka topic."""
        settings.require_order_execution()
        if topic in {
            KafkaTopic.PROPOSALS_BUS,
            KafkaTopic.PROPOSALS_APPROVED,
            KafkaTopic.ORDERS_PENDING,
            KafkaTopic.ORDERS_EXECUTED,
            KafkaTopic.FILLS_CONFIRMED,
            KafkaTopic.PORTFOLIO_STATE,
            KafkaTopic.RISK_ALERTS,
        } and not (topic == KafkaTopic.RISK_ALERTS and payload.get("halt_scope") == "global"):
            if payload.get("accounting_book_id") not in (None, settings.accounting_book_id):
                raise ValueError("Cannot publish another book's execution/risk state")
            payload = {**payload, "accounting_book_id": settings.accounting_book_id}
        msg = AgentMessage(
            source_agent_id=self.agent_id,
            topic=topic,
            message_type=message_type or topic.value,
            payload=payload,
        )
        await self.producer.send(topic, msg)
        self._messages_processed += 1
        agent_messages_processed.labels(
            agent_id=str(self.agent_id),
            agent_name=self.name,
            topic=topic.value,
        ).inc()

    def make_consumer(
        self,
        topics: list[KafkaTopic],
        auto_offset_reset: str = "latest",
    ) -> AlghrestConsumer:
        """Create a topic consumer scoped to this agent's group."""
        return AlghrestConsumer(
            agent_name=f"{self.name}.{settings.accounting_book_id}",
            topics=topics,
            auto_offset_reset=auto_offset_reset,
        )

    def record_processing_error(self, topic: str, error_type: str) -> None:
        self._messages_failed += 1
        agent_messages_failed.labels(
            agent_id=str(self.agent_id),
            agent_name=self.name,
            topic=topic,
            error_type=error_type,
        ).inc()

    # ── KILL SWITCH GUARD ─────────────────────────────────────────────────────

    async def is_halted(self) -> bool:
        """Returns True if the system-wide kill switch is active."""
        return await self.state.is_kill_switch_active()

    # ── HEALTH ───────────────────────────────────────────────────────────────

    async def health_check(self) -> AgentHealth:
        uptime = int((datetime.utcnow() - self.start_time).total_seconds())
        return AgentHealth(
            agent_id=self.agent_id,
            agent_name=self.name,
            tier=self.tier,
            status=self.status,
            start_time=self.start_time,
            last_heartbeat=datetime.utcnow(),
            uptime_seconds=uptime,
            messages_processed=self._messages_processed,
            messages_failed=self._messages_failed,
        )


# =============================================================================
# BASE STRATEGY — Tier 4 agents
# =============================================================================


class BaseStrategy(BaseAgent, ABC):
    """
    Abstract base for all 8 Tier 4 strategy agents.
    Each strategy runs in an isolated capital sleeve.
    """

    def __init__(
        self,
        agent_id: int,
        name: str,
        strategy_id: str,
        capital_pct: float,
        max_positions: int = 5,
        risk_per_trade: float = 0.01,
        config: AgentConfig | None = None,
    ) -> None:
        super().__init__(agent_id=agent_id, tier=4, name=name, config=config)
        self.strategy_id = strategy_id
        self.capital_pct = capital_pct  # Fraction of total capital for this sleeve
        self.max_positions = max_positions
        self.risk_per_trade = min(risk_per_trade, 0.01)  # Never more than 1%
        self._consecutive_losses = 0
        self._strategy_paused = False

    # ── ABSTRACT STRATEGY INTERFACE ───────────────────────────────────────────

    @abstractmethod
    async def generate_signal(self, market_state: MarketState) -> TradeProposal | None:
        """
        Core strategy logic. Returns a TradeProposal or None.
        Called by the run() loop every time MarketState is updated.
        """

    @abstractmethod
    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        """Return True if an open position should be closed based on current market state."""

    @abstractmethod
    def backtest(self, data: pd.DataFrame, params: dict[str, Any]) -> BacktestResult:
        """
        Run strategy on historical data.
        Must pass STRATEGY_VALIDATION thresholds before going live.
        """

    # ── CONSECUTIVE LOSS TRACKING ─────────────────────────────────────────────

    def record_loss(self) -> None:
        self._consecutive_losses += 1
        if self._consecutive_losses >= 5:  # RISK_LIMITS.consecutive_loss_pause
            self._strategy_paused = True
            self.logger.error(
                "strategy paused: 5 consecutive losses",
                consecutive_losses=self._consecutive_losses,
            )

    def record_win(self) -> None:
        self._consecutive_losses = 0

    def resume(self) -> None:
        self._strategy_paused = False
        self._consecutive_losses = 0
        self.logger.info("strategy resumed")

    @property
    def is_strategy_paused(self) -> bool:
        return self._strategy_paused
