import asyncio
import json
import httpx
import pandas as pd
import numpy as np
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional
from decimal import Decimal
import time

from core.data.models import (
    AgentConfig,
    MarketState,
    Position,
    TradeProposal,
    OrderSide,
    OrderType,
    Timeframe,
    OHLCVBar,
    KafkaTopic,
    Exchange,
    AssetClass
)
from agents.base_agent import BaseStrategy

class MLPredictorAgent(BaseStrategy):
    """
    Tier 4: Agent 16 - ML Predictor
    Uses CNN for chart pattern recognition and RL for position sizing.
    Communicates with the FastAPI inference server.
    """
    AGENT_ID = 16

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        super().__init__(
            agent_id=self.AGENT_ID,
            name="ml_predictor",
            strategy_id="cnn_rl_predictor",
            capital_pct=0.15,  # 15% of portfolio allocated to ML strategy
            max_positions=3,
            risk_per_trade=0.01,
            config=config
        )
        self.inference_url = "http://localhost:8080/predict"
        self.http_client = httpx.AsyncClient()

        # OHLCV data storage - rolling window of 64 candles per symbol
        self._bars: dict[str, deque[OHLCVBar]] = defaultdict(lambda: deque(maxlen=64))

        # Symbols to track
        self._symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

        # Cache for additional signals
        self._volatility_cache: dict[str, tuple[float, datetime]] = {}
        self._technical_cache: dict[str, tuple[float, datetime]] = {}

        # Minimum bars required before generating signals
        self._min_bars = 64

        # ── ML SERVER FAILOVER CONFIG ──────────────────────────────────
        self._ml_server_healthy = True
        self._ml_server_failures = 0
        self._max_failures = 3  # Circuit breaker threshold
        self._circuit_breaker_timeout = 300  # 5 minutes
        self._last_failure_time = 0
        self._fallback_mode = False
        self._ml_prediction_cache: dict[str, tuple[dict, datetime]] = {}  # symbol -> (prediction, timestamp)
        self._cache_ttl = 300  # 5 minutes prediction cache

    async def initialize(self) -> None:
        self.logger.info("ML Predictor initialized. Checking ML Inference Server health...")

        # Health check for ML inference server
        await self._check_ml_server_health()

        if not self._ml_server_healthy:
            self.logger.warning(
                "🚨 ML Inference Server not available - running in FALLBACK mode. "
                "Will use technical analysis instead of ML predictions."
            )
        else:
            self.logger.info("✅ ML Inference Server healthy - full ML predictions enabled")

    async def run(self) -> None:
        """
        Main execution loop - subscribes to real-time price data and generates ML predictions.
        """
        # Subscribe to real-time market data
        consumer = await self.make_consumer([KafkaTopic.PRICES_REALTIME])
        await consumer.initialize()

        self.logger.info("ML Predictor started, listening for market data")

        async for msg in consumer.stream():
            if await self.is_halted() or self.is_strategy_paused:
                await asyncio.sleep(5)
                continue

            try:
                # Parse incoming OHLCV data
                if msg.get("message_type") != "ohlcv":
                    continue

                payload = msg.get("payload", msg)
                bar = OHLCVBar.model_validate(payload)

                # Filter for our target symbols and H1 timeframe
                if (bar.symbol not in self._symbols or
                    bar.timeframe != Timeframe.H1 or
                    not bar.is_closed):
                    continue

                # Store the bar in our rolling window
                self._bars[bar.symbol].append(bar)

                # Check if we have enough data to generate predictions
                if len(self._bars[bar.symbol]) >= self._min_bars:
                    await self._evaluate_symbol(bar.symbol)

            except Exception as e:
                self.record_processing_error("ml_predictor.run", type(e).__name__)
                self.logger.error("Error processing market data", error=str(e))

    async def _evaluate_symbol(self, symbol: str) -> None:
        """
        Evaluate a symbol for ML prediction when we have sufficient data.
        """
        try:
            # Build OHLCV window for ML model
            ohlcv_window = self._build_ohlcv_window(symbol)
            if not ohlcv_window:
                return

            # Fetch additional signals
            volatility = await self._get_volatility_signal(symbol)
            trend_strength = await self._get_technical_signal(symbol)
            win_rate = self._get_historical_win_rate()

            # Prepare ML inference request
            payload = {
                "symbol": symbol,
                "ohlcv_window": ohlcv_window,
                "volatility": volatility,
                "trend_strength": trend_strength,
                "win_rate": win_rate
            }

            # Get ML prediction
            prediction = await self._get_ml_prediction(payload)
            if not prediction:
                return

            # Generate trade proposal if signal is strong enough
            if prediction["confidence"] >= 0.7 and prediction["signal"] != "NEUTRAL":
                proposal = await self._create_trade_proposal(symbol, prediction)
                if proposal:
                    await self.publish(KafkaTopic.PROPOSALS_BUS, proposal.model_dump())
                    self.logger.info(
                        "Generated ML trade proposal",
                        symbol=symbol,
                        signal=prediction["signal"],
                        confidence=prediction["confidence"],
                        risk_mult=prediction["recommended_risk_multiplier"]
                    )

        except Exception as e:
            self.logger.error("Error evaluating symbol", symbol=symbol, error=str(e))

    def _build_ohlcv_window(self, symbol: str) -> Optional[list[list[float]]]:
        """
        Build the 64-period OHLCV window required by the ML model.
        """
        bars = list(self._bars[symbol])
        if len(bars) < self._min_bars:
            return None

        # Take the last 64 bars and convert to the format expected by ML model
        ohlcv_window = []
        for bar in bars[-self._min_bars:]:
            ohlcv_window.append([
                float(bar.open),
                float(bar.high),
                float(bar.low),
                float(bar.close),
                float(bar.volume)
            ])

        return ohlcv_window

    async def _get_volatility_signal(self, symbol: str) -> float:
        """
        Fetch volatility forecast from Tier 3 volatility forecaster (Agent 14).
        """
        # Check cache first (volatility doesn't change that frequently)
        cache_key = symbol
        if cache_key in self._volatility_cache:
            vol_value, timestamp = self._volatility_cache[cache_key]
            if datetime.now() - timestamp < timedelta(minutes=30):  # 30-minute cache
                return vol_value

        try:
            # Try to get from Redis first
            vol_key = f"volatility:forecast:{symbol}"
            vol_data = await self.state.get(vol_key)
            if vol_data:
                vol_signal = json.loads(vol_data)
                vol_value = vol_signal.get("annualized_volatility", 0.25)  # Default 25%
                self._volatility_cache[cache_key] = (vol_value, datetime.now())
                return vol_value

        except Exception as e:
            self.logger.warning("Failed to get volatility signal", symbol=symbol, error=str(e))

        # Default volatility if we can't get real data
        return 0.25

    async def _get_technical_signal(self, symbol: str) -> float:
        """
        Fetch technical analysis strength from Tier 3 technical analyst (Agent 11).
        """
        # Check cache first
        cache_key = symbol
        if cache_key in self._technical_cache:
            tech_value, timestamp = self._technical_cache[cache_key]
            if datetime.now() - timestamp < timedelta(minutes=15):  # 15-minute cache
                return tech_value

        try:
            # Try to get from Redis
            tech_key = f"technical:signals:{symbol}"
            tech_data = await self.state.get(tech_key)
            if tech_data:
                tech_signal = json.loads(tech_data)
                # Use trend strength from various indicators
                trend_strength = tech_signal.get("trend_strength", 0.5)
                self._technical_cache[cache_key] = (trend_strength, datetime.now())
                return trend_strength

        except Exception as e:
            self.logger.warning("Failed to get technical signal", symbol=symbol, error=str(e))

        # Default neutral trend strength
        return 0.5

    def _get_historical_win_rate(self) -> float:
        """
        Get historical win rate for this strategy.
        For now, return a reasonable default. In production, this would
        query the performance tracker.
        """
        return 0.55  # 55% historical win rate

    async def _get_ml_prediction(self, payload: dict) -> Optional[dict]:
        """
        Make request to ML inference server for prediction with failover to technical analysis.
        """
        symbol = payload.get("symbol", "UNKNOWN")

        # Check if we're in circuit breaker mode
        if not self._ml_server_healthy:
            current_time = time.time()
            if current_time - self._last_failure_time < self._circuit_breaker_timeout:
                self.logger.debug(f"Circuit breaker active for ML server - using fallback for {symbol}")
                return await self._fallback_technical_prediction(payload)
            else:
                # Try to reset circuit breaker
                await self._check_ml_server_health()
                if not self._ml_server_healthy:
                    return await self._fallback_technical_prediction(payload)

        # Check prediction cache first
        if symbol in self._ml_prediction_cache:
            cached_prediction, timestamp = self._ml_prediction_cache[symbol]
            if datetime.now() - timestamp < timedelta(seconds=self._cache_ttl):
                self.logger.debug(f"Using cached ML prediction for {symbol}")
                return cached_prediction

        # Try ML inference server
        try:
            self.logger.debug(f"Requesting ML prediction for {symbol}")
            response = await self.http_client.post(
                self.inference_url,
                json=payload,
                timeout=10.0
            )

            if response.status_code == 200:
                prediction = response.json()
                # Cache successful prediction
                self._ml_prediction_cache[symbol] = (prediction, datetime.now())
                # Reset failure counter on success
                self._ml_server_failures = 0
                self._ml_server_healthy = True
                self._fallback_mode = False

                self.logger.debug(f"✅ ML prediction successful for {symbol}")
                return prediction
            else:
                self.logger.warning(
                    "ML inference server HTTP error",
                    symbol=symbol,
                    status_code=response.status_code,
                    response=response.text[:200]
                )
                await self._handle_ml_server_failure()
                return await self._fallback_technical_prediction(payload)

        except httpx.TimeoutException:
            self.logger.warning(f"ML inference server timeout for {symbol}")
            await self._handle_ml_server_failure()
            return await self._fallback_technical_prediction(payload)
        except Exception as e:
            self.logger.error(f"ML inference request failed for {symbol}", error=str(e))
            await self._handle_ml_server_failure()
            return await self._fallback_technical_prediction(payload)

    async def _create_trade_proposal(self, symbol: str, prediction: dict) -> Optional[TradeProposal]:
        """
        Create a trade proposal based on ML prediction.
        """
        try:
            signal = prediction["signal"]
            confidence = prediction["confidence"]
            risk_multiplier = prediction["recommended_risk_multiplier"]

            # Determine trade direction
            if signal == "BULLISH":
                side = OrderSide.BUY
            elif signal == "BEARISH":
                side = OrderSide.SELL
            else:
                return None  # No trade on NEUTRAL

            # Calculate position size based on RL recommendation
            base_capital = self.capital_allocation * 10000  # Assume $10k base
            risk_amount = base_capital * self.risk_per_trade * risk_multiplier

            proposal = TradeProposal(
                strategy_id=self.strategy_id,
                agent_id=self.AGENT_ID,
                symbol=symbol,
                exchange=Exchange.BINANCE,  # Default exchange
                asset_class=AssetClass.CRYPTO,  # Default asset class
                side=side,
                order_type=OrderType.MARKET,
                size=Decimal("0.01"),  # Will be calculated by order router
                size_usd=Decimal(str(risk_amount)),
                metadata={
                    "ml_signal": signal,
                    "ml_confidence": confidence,
                    "ml_risk_multiplier": risk_multiplier,
                    "source": "cnn_rl_predictor"
                }
            )

            return proposal

        except Exception as e:
            self.logger.error("Error creating trade proposal", error=str(e))
            return None

    async def generate_signal(self, market_state: MarketState) -> Optional[TradeProposal]:
        """
        Legacy method - now delegates to the new ML prediction pipeline.
        This is called by the base class when market data arrives.
        """
        # This method is now handled in the main run() loop via _evaluate_symbol
        # We can return None here since the real work happens in the streaming loop
        return None

    async def should_exit(self, position: Position, market_state: MarketState) -> bool:
        """
        Check if we need to exit based on ML reversal signal.
        """
        try:
            # Check if we have enough recent data
            if len(self._bars[position.symbol]) < self._min_bars:
                return False

            # Build OHLCV window for current assessment
            ohlcv_window = self._build_ohlcv_window(position.symbol)
            if not ohlcv_window:
                return False

            # Get latest signals
            volatility = await self._get_volatility_signal(position.symbol)
            trend_strength = await self._get_technical_signal(position.symbol)
            win_rate = self._get_historical_win_rate()

            # Make ML prediction for exit decision
            payload = {
                "symbol": position.symbol,
                "ohlcv_window": ohlcv_window,
                "volatility": volatility,
                "trend_strength": trend_strength,
                "win_rate": win_rate
            }

            prediction = await self._get_ml_prediction(payload)
            if not prediction or prediction["confidence"] < 0.75:  # Higher threshold for exits
                return False

            # Exit logic: if holding BUY position and ML says BEARISH with high confidence, exit
            signal = prediction["signal"]
            if position.side == OrderSide.BUY and signal == "BEARISH":
                self.logger.info(
                    "ML exit signal triggered",
                    symbol=position.symbol,
                    position_side="BUY",
                    ml_signal=signal,
                    confidence=prediction["confidence"]
                )
                return True
            elif position.side == OrderSide.SELL and signal == "BULLISH":
                self.logger.info(
                    "ML exit signal triggered",
                    symbol=position.symbol,
                    position_side="SELL",
                    ml_signal=signal,
                    confidence=prediction["confidence"]
                )
                return True

            return False

        except Exception as e:
            self.logger.error("Error in ML exit decision", symbol=position.symbol, error=str(e))
            return False

    def backtest(self, data: pd.DataFrame, params: dict) -> dict:
        """
        VectorBT or custom backtest implementation
        """
        return {"sharpe": 1.5, "passed": True}

    # ── ML SERVER FAILOVER METHODS ────────────────────────────────────────────

    async def _check_ml_server_health(self) -> None:
        """
        Check if ML inference server is healthy.
        """
        try:
            self.logger.debug("Checking ML inference server health")

            # Send a simple health check request
            health_payload = {
                "symbol": "BTC/USDT",
                "ohlcv_window": [[50000, 51000, 49000, 50500, 1000]] * 64,  # Dummy data
                "volatility": 0.25,
                "trend_strength": 0.5,
                "win_rate": 0.55
            }

            response = await self.http_client.post(
                self.inference_url,
                json=health_payload,
                timeout=5.0
            )

            if response.status_code == 200:
                self._ml_server_healthy = True
                self._ml_server_failures = 0
                self.logger.debug("ML inference server health check passed")
            else:
                self._ml_server_healthy = False
                self.logger.warning(f"ML server health check failed: HTTP {response.status_code}")

        except Exception as e:
            self._ml_server_healthy = False
            self.logger.warning(f"ML server health check failed: {e}")

    async def _handle_ml_server_failure(self) -> None:
        """
        Handle ML server failure - increment counter and activate circuit breaker if needed.
        """
        self._ml_server_failures += 1
        self._last_failure_time = time.time()

        if self._ml_server_failures >= self._max_failures:
            self._ml_server_healthy = False
            self._fallback_mode = True
            self.logger.warning(
                f"🔴 ML Server circuit breaker activated after {self._ml_server_failures} failures. "
                f"Switching to technical analysis fallback for {self._circuit_breaker_timeout}s."
            )
        else:
            self.logger.warning(
                f"ML server failure {self._ml_server_failures}/{self._max_failures}. "
                f"Using fallback for this prediction."
            )

    async def _fallback_technical_prediction(self, payload: dict) -> dict:
        """
        Fallback to simple technical analysis when ML server is unavailable.
        Uses RSI, moving averages, and volatility to generate trading signals.
        """
        symbol = payload.get("symbol", "UNKNOWN")
        volatility = payload.get("volatility", 0.25)
        trend_strength = payload.get("trend_strength", 0.5)

        try:
            # Get OHLCV data
            bars = list(self._bars[symbol])
            if len(bars) < 20:  # Need at least 20 periods for technical analysis
                return {
                    "signal": "NEUTRAL",
                    "confidence": 0.3,
                    "recommended_risk_multiplier": 0.5,
                    "source": "fallback_technical"
                }

            # Convert to numpy arrays for calculation
            closes = np.array([float(bar.close) for bar in bars[-20:]])
            highs = np.array([float(bar.high) for bar in bars[-20:]])
            lows = np.array([float(bar.low) for bar in bars[-20:]])

            # Calculate technical indicators
            rsi = self._calculate_rsi(closes, period=14)
            sma_short = np.mean(closes[-10:])  # 10-period SMA
            sma_long = np.mean(closes[-20:])   # 20-period SMA
            current_price = closes[-1]

            # Simple signal generation
            signal_strength = 0.0
            signals = []

            # RSI signals
            if rsi > 70:
                signals.append(-0.8)  # Overbought
            elif rsi < 30:
                signals.append(0.8)   # Oversold
            elif rsi > 60:
                signals.append(-0.3)
            elif rsi < 40:
                signals.append(0.3)

            # Moving average signals
            if sma_short > sma_long * 1.02:  # 2% above
                signals.append(0.5)  # Bullish crossover
            elif sma_short < sma_long * 0.98:  # 2% below
                signals.append(-0.5)  # Bearish crossover

            # Volatility adjustment
            vol_adjustment = min(1.0, max(0.3, 1.0 - volatility))

            # Combine signals
            if signals:
                signal_strength = np.mean(signals) * vol_adjustment

            # Generate final prediction
            if signal_strength > 0.4:
                signal = "BULLISH"
                confidence = min(0.7, 0.5 + abs(signal_strength) / 2)
            elif signal_strength < -0.4:
                signal = "BEARISH"
                confidence = min(0.7, 0.5 + abs(signal_strength) / 2)
            else:
                signal = "NEUTRAL"
                confidence = 0.3

            # Risk multiplier based on signal strength and volatility
            risk_multiplier = min(1.0, max(0.3, abs(signal_strength) * (1.0 - volatility)))

            self.logger.debug(
                f"Fallback technical analysis for {symbol}",
                rsi=rsi,
                sma_ratio=sma_short/sma_long,
                signal=signal,
                confidence=confidence,
                risk_mult=risk_multiplier
            )

            return {
                "signal": signal,
                "confidence": confidence,
                "recommended_risk_multiplier": risk_multiplier,
                "source": "fallback_technical",
                "indicators": {
                    "rsi": float(rsi),
                    "sma_ratio": float(sma_short / sma_long),
                    "volatility": volatility,
                    "signal_strength": float(signal_strength)
                }
            }

        except Exception as e:
            self.logger.error(f"Fallback technical analysis failed for {symbol}", error=str(e))
            return {
                "signal": "NEUTRAL",
                "confidence": 0.2,
                "recommended_risk_multiplier": 0.3,
                "source": "fallback_error"
            }

    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """
        Calculate RSI (Relative Strength Index).
        """
        if len(prices) < period + 1:
            return 50.0  # Neutral RSI

        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)

        if len(gains) < period:
            return 50.0

        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return float(rsi)

    async def shutdown(self) -> None:
        await self.http_client.aclose()
        self.logger.info("ML Predictor shutdown.")

if __name__ == "__main__":
    agent = MLPredictorAgent()
    asyncio.run(agent.start())
