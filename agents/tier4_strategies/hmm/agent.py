"""
Agent 37 — HMM Regime Strategy
================================
Tier 4 strategy agent that uses the HMM_Trading research subproject
to detect market regimes and emit regime-aware trade proposals.

Lifecycle
---------
  initialize()
    → Load HMM config from HMM_Trading/configs/default.json
    → Download / generate historical OHLCV data
    → Train GaussianHMM and decode initial regime labels

  run()
    → Consume daily (D1) OHLCV bars from PRICES_REALTIME
    → Accumulate a rolling bar window (min _MIN_BARS rows)
    → Every _INFERENCE_INTERVAL seconds, re-infer the current regime
    → Map regime label → signal direction + confidence
    → Emit a TradeProposal to PROPOSALS_BUS

Safety guarantees
-----------------
  ✅  Paper / simulation only by default — no live order execution.
  ✅  No exchange connector calls.
  ✅  No API keys required.
  ✅  Fails gracefully: HMM errors are caught; agent logs a warning and
      waits rather than crashing the system.
  ✅  Kill-switch aware (self.is_halted() checked every loop iteration).

TODO (future hardening):
  - Persist the trained model weights and reload on restart.
  - Add an explicit re-train cadence (weekly) instead of train-on-startup.
  - Register in the central agent registry once one exists.
  - Extend to multi-symbol regime detection.
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog

from agents.base_agent import BaseStrategy
from agents.tier4_strategies.hmm.adapter import (
    HMMAdapter,
    HMMAdapterError,
    regime_to_signal_direction,
)
from core.data.models import (
    AgentConfig,
    AssetClass,
    BacktestResult,
    Exchange,
    KafkaTopic,
    MarketState,
    OHLCVBar,
    OrderSide,
    OrderType,
    Position,
    Timeframe,
    TradeProposal,
)

log = structlog.get_logger(__name__)

# ── Constants ────────────────────────────────────────────────────────────────
_MIN_BARS = 100  # Need at least ~5 months of daily data for warm-up
_MAX_BARS = 1500  # Rolling window cap (≈ 6 years of daily bars)
_INFERENCE_INTERVAL = 3600  # Re-infer regime every 60 minutes (in seconds)
_TRAIN_TIMEOUT_S = 300  # Max seconds allowed for the initial training step
_SYMBOL = "BTC/USDT"  # Primary symbol for regime-driven proposals


class HMMAgent(BaseStrategy):
    """
    Agent 37 — HMM Market Regime Strategy.

    Detects the current market regime using a Hidden Markov Model trained on
    historical daily OHLCV data (via HMM_Trading research subproject).
    Emits a TradeProposal when a non-neutral regime is detected.
    """

    AGENT_ID = 37
    strategy_id = "hmm_regime_detection"
    capital_pct = 0.08  # 8% capital sleeve
    max_positions = 2
    risk_per_trade = 0.008  # 0.8% per trade (below the 1% hard limit)

    def __init__(self, config: AgentConfig | None = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="HMMAgent",
            strategy_id=self.strategy_id,
            capital_pct=self.capital_pct,
            max_positions=self.max_positions,
            risk_per_trade=self.risk_per_trade,
            config=config,
        )
        # Adapter to HMM_Trading (lazy-loads HMM functions on first use)
        self._adapter = HMMAdapter()

        # State (set during initialize)
        self._hmm_model: Any | None = None
        self._regime_labels: dict[int, str] = {}
        self._last_inference_ts: datetime | None = None
        self._last_regime: str | None = None
        self._last_confidence: float = 0.0
        self._last_state_id: int = -1

        # Rolling bar buffer (D1 bars from Kafka)
        self._bars: deque[OHLCVBar] = deque(maxlen=_MAX_BARS)

        # Safety flag: if initial training failed, we skip inference
        self._model_ready: bool = False

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        log.info(
            "hmm_agent.starting",
            agent_id=self.AGENT_ID,
            strategy=self.strategy_id,
            symbol=_SYMBOL,
            note="paper/simulation only — no live orders",
        )
        await self._initial_train()

    async def run(self) -> None:
        """
        Main loop: consume D1 bars, periodically re-infer regime, publish signals.
        """
        consumer = self.make_consumer([KafkaTopic.PRICES_REALTIME])
        log.info("hmm_agent.listening", topic=KafkaTopic.PRICES_REALTIME.value)

        async for msg in consumer.stream():
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(5)
                continue

            try:
                bar = OHLCVBar(**msg)
            except Exception as exc:
                log.debug("hmm_agent.bar_parse_error", error=str(exc))
                self.record_processing_error(KafkaTopic.PRICES_REALTIME.value, type(exc).__name__)
                continue

            # Only accumulate closed daily bars for the target symbol
            if bar.timeframe != Timeframe.D1 or not bar.is_closed:
                continue
            if bar.symbol != _SYMBOL:
                continue

            self._bars.append(bar)

            await self._maybe_infer_and_publish()

    async def shutdown(self) -> None:
        log.info("hmm_agent.shutdown", last_regime=self._last_regime)

    # ── Training ───────────────────────────────────────────────────────────────

    async def _initial_train(self) -> None:
        """
        Train the HMM on historical data at startup.
        Uses asyncio.wait_for to avoid blocking forever on slow yfinance calls.
        """
        log.info("hmm_agent.training_start", config=self._adapter.config.get("ticker"))
        try:
            model, meta = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, self._train_sync),
                timeout=_TRAIN_TIMEOUT_S,
            )
            self._hmm_model = model
            self._regime_labels = meta["labels"]
            self._model_ready = True
            log.info(
                "hmm_agent.training_complete",
                n_states=len(self._regime_labels),
                regime_labels=self._regime_labels,
            )
        except TimeoutError:
            log.warning(
                "hmm_agent.training_timeout",
                timeout_s=_TRAIN_TIMEOUT_S,
                note="Agent will run without a model until re-initialised.",
            )
        except HMMAdapterError as exc:
            log.warning(
                "hmm_agent.training_failed",
                error=str(exc),
                note="Agent will run without a model — no signals will be emitted.",
            )
        except Exception as exc:
            log.warning(
                "hmm_agent.training_unexpected_error",
                error=str(exc),
            )

    def _train_sync(self):
        """Synchronous training helper (runs in executor thread)."""
        df = self._adapter.load_data()
        return self._adapter.train(df)

    # ── Inference & publishing ─────────────────────────────────────────────────

    async def _maybe_infer_and_publish(self) -> None:
        """
        Re-infer the current regime if enough time has elapsed since the last check.
        Publishes a proposal when a non-neutral regime is detected.
        """
        if not self._model_ready:
            return
        if len(self._bars) < _MIN_BARS:
            return

        now = datetime.utcnow()
        if (
            self._last_inference_ts is not None
            and (now - self._last_inference_ts).total_seconds() < _INFERENCE_INTERVAL
        ):
            return

        self._last_inference_ts = now

        try:
            df = self._adapter.ohlcv_bars_to_dataframe(list(self._bars))
            regime_label, confidence, state_id = await asyncio.get_event_loop().run_in_executor(
                None,
                self._detect_regime_sync,
                df,
            )
        except HMMAdapterError as exc:
            log.warning("hmm_agent.inference_failed", error=str(exc))
            return
        except Exception as exc:
            log.warning("hmm_agent.inference_unexpected_error", error=str(exc))
            return

        self._last_regime = regime_label
        self._last_confidence = confidence
        self._last_state_id = state_id

        signal_direction = regime_to_signal_direction(regime_label)
        log.info(
            "hmm_agent.regime_detected",
            regime=regime_label,
            signal=signal_direction,
            confidence=round(confidence, 3),
            state_id=state_id,
        )

        if signal_direction == "NEUTRAL":
            log.info("hmm_agent.no_proposal_neutral_regime", regime=regime_label)
            return

        proposal = self._build_proposal(regime_label, signal_direction, confidence)
        if proposal is not None:
            await self.publish(
                KafkaTopic.PROPOSALS_BUS,
                proposal.model_dump(mode="json"),
                "TradeProposal",
            )
            log.info(
                "hmm_agent.proposal_published",
                symbol=_SYMBOL,
                side=proposal.side.value,
                confidence=round(confidence, 3),
                regime=regime_label,
            )

    def _detect_regime_sync(self, df: pd.DataFrame):
        """Synchronous regime detection helper (runs in executor thread)."""
        return self._adapter.detect_regime(self._hmm_model, df, self._regime_labels)

    # ── Proposal construction ─────────────────────────────────────────────────

    def _build_proposal(
        self,
        regime_label: str,
        signal_direction: str,
        confidence: float,
    ) -> TradeProposal | None:
        """
        Convert an HMM regime signal into an ALGHREST TradeProposal.

        SAFETY: This method NEVER calls any exchange connector or execution class.
        The proposal is sent to PROPOSALS_BUS and must be approved by the
        ProposalApprover (Tier 1) before reaching the execution layer.
        """
        if not self._bars:
            return None

        try:
            last_bar = self._bars[-1]
            current_price = float(last_bar.close)
            if current_price <= 0:
                return None

            side = OrderSide.BUY if signal_direction == "BULLISH" else OrderSide.SELL

            # Conservative sizing: symbolic placeholder — real sizing done by PositionSizer
            size_usd = Decimal("0.00")  # ProposalApprover / position sizer overrides this
            size = Decimal("0.001")  # Symbolic minimum lot

            # Stop/take-profit: use a 5% trailing stop, 10% target (regime-level logic)
            stop_distance = current_price * 0.05
            stop_loss = (
                current_price - stop_distance
                if side == OrderSide.BUY
                else current_price + stop_distance
            )
            take_profit = (
                current_price + 2 * stop_distance
                if side == OrderSide.BUY
                else current_price - 2 * stop_distance
            )

            proposal = TradeProposal(
                strategy_id=self.strategy_id,
                agent_id=self.AGENT_ID,
                symbol=_SYMBOL,
                exchange=Exchange.BINANCE,
                asset_class=AssetClass.CRYPTO,
                side=side,
                order_type=OrderType.MARKET,
                size=size,
                size_usd=size_usd,
                limit_price=None,
                stop_loss=Decimal(str(round(stop_loss, 2))),
                take_profit=Decimal(str(round(take_profit, 2))),
                confidence_score=confidence,
                rationale=(
                    f"HMM regime={regime_label!r} | "
                    f"signal={signal_direction} | "
                    f"state_id={self._last_state_id} | "
                    f"confidence={confidence:.3f}"
                ),
                metadata={
                    "model": "HMM",
                    "source": "HMM_Trading",
                    "regime_label": regime_label,
                    "regime_state_id": self._last_state_id,
                    "signal_direction": signal_direction,
                    "confidence": confidence,
                    "strategy": "regime_detection",
                    "timestamp": datetime.utcnow().isoformat(),
                    "paper_only": True,
                },
            )
            return proposal

        except Exception as exc:
            log.warning("hmm_agent.proposal_build_error", error=str(exc))
            return None

    # ── BaseStrategy abstract interface ───────────────────────────────────────

    async def generate_signal(self, market_state: MarketState) -> TradeProposal | None:
        """
        On-demand signal generation (called by the base class if integrated
        into a polling loop). The HMM agent is reactive (bar-driven) so this
        returns the last known proposal rather than re-running inference.
        """
        if self._last_regime is None or not self._model_ready:
            return None

        signal_direction = regime_to_signal_direction(self._last_regime)
        if signal_direction == "NEUTRAL":
            return None

        return self._build_proposal(self._last_regime, signal_direction, self._last_confidence)

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        """
        Exit a position if the regime flips against the held direction.

        BUY  position + BEARISH regime → exit
        SELL position + BULLISH regime → exit
        """
        if self._last_regime is None:
            return False

        signal_direction = regime_to_signal_direction(self._last_regime)
        if position.side == OrderSide.BUY and signal_direction == "BEARISH":
            log.info(
                "hmm_agent.regime_exit_triggered",
                symbol=position.symbol,
                position_side="BUY",
                new_regime=self._last_regime,
            )
            return True
        if position.side == OrderSide.SELL and signal_direction == "BULLISH":
            log.info(
                "hmm_agent.regime_exit_triggered",
                symbol=position.symbol,
                position_side="SELL",
                new_regime=self._last_regime,
            )
            return True
        return False

    def backtest(self, data: pd.DataFrame, params: dict) -> BacktestResult:
        """
        Backtest stub — runs HMM regime labelling over historical data and
        returns a BacktestResult with summary metrics.

        For a full walk-forward backtest, wire this into
        backtesting/engine.py::BacktestEngine.
        """
        try:
            _, meta = self._adapter.train(data)
            states = meta["states"]
            labels = meta["labels"]

            # Count regime-driven trades (regime change = one trade)
            n_trades = int((pd.Series(states).diff().abs() > 0).sum())

            return BacktestResult(
                strategy_name="HMMAgent",
                strategy_id=self.strategy_id,
                symbol=_SYMBOL,
                timeframe=Timeframe.D1,
                total_trades=n_trades,
                metadata={
                    "n_states": len(labels),
                    "regime_labels": labels,
                    "note": "Stub backtest — integrate with BacktestEngine for full metrics.",
                },
            )
        except HMMAdapterError as exc:
            log.warning("hmm_agent.backtest_failed", error=str(exc))
            return BacktestResult(
                strategy_name="HMMAgent",
                strategy_id=self.strategy_id,
                failure_reasons=[str(exc)],
            )
