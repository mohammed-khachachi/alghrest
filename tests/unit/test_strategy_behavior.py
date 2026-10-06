"""Strategy sizing, exits, data contracts, and fail-closed skeleton behavior."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pandas as pd
import pytest

from agents.tier4_strategies import (
    breakout_hunter as breakout,
    macro_rotator as macro,
    mean_reversion as mean,
    momentum,
    stat_arb as arb,
    trend_follower as trend,
)
from agents.tier6_defi.bridge_strategist import BridgeStrategistAgent
from agents.tier6_defi.dex_arbitrageur import DEXArbitrageurAgent
from agents.tier6_defi.mev_hunter import MEVHunterAgent
from agents.tier6_defi.yield_farmer import YieldFarmerAgent
from core.config import settings
from core.data.models import (
    KafkaTopic,
    MarketRegime,
    MarketState,
    OrderSide,
    Timeframe,
    TradeProposal,
)
from tests.factories import FiniteConsumer, bar, portfolio, position

pytestmark = pytest.mark.unit
SYMBOL = "BTC/USDT"


def wire(agent):
    agent.state = AsyncMock()
    agent.state.is_kill_switch_active.return_value = False
    agent.state.get_portfolio.return_value = portfolio()
    agent.publish = AsyncMock()
    return agent


def candle_window(count=300):
    now = datetime.utcnow()
    return [
        bar(time=now + timedelta(days=i), close=100 + i * 0.01, timeframe=Timeframe.D1)
        for i in range(count)
    ]


@pytest.mark.parametrize(
    "factory,evaluate,timeframe",
    [
        (momentum.MomentumStrategy, "_maybe_rebalance", Timeframe.D1),
        (breakout.BreakoutHunter, "_evaluate", Timeframe.D1),
        (arb.StatArb, "_scan_pairs", Timeframe.H1),
        (mean.MeanReversion, "_evaluate", Timeframe.H1),
    ],
)
async def test_real_price_envelopes_initialize_consumer_and_filter(
    factory, evaluate, timeframe, monkeypatch
):
    agent = wire(factory())
    setattr(agent, evaluate, AsyncMock())
    consumer = FiniteConsumer(
        [
            {"message_type": "other"},
            {"message_type": "ohlcv", "payload": {}},
            *[
                {"message_type": "ohlcv", "payload": b.model_dump(mode="json")}
                for b in [
                    bar(timeframe=timeframe),
                    bar(is_closed=False),
                    bar(symbol="UNKNOWN"),
                    bar(timeframe=Timeframe.M1),
                ]
            ],
        ]
    )
    monkeypatch.setattr(agent, "make_consumer", lambda *a, **kw: consumer)
    await agent.initialize()
    await agent.run()
    consumer.initialize.assert_awaited_once()
    getattr(agent, evaluate).assert_awaited_once()
    assert len(agent._bars[SYMBOL]) == 1
    await agent.shutdown()


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
async def test_momentum_position_sizing_and_exit(side):
    agent = wire(momentum.MomentumStrategy())
    await agent._enter(SYMBOL, side, 100, 0.25, Decimal(10000))
    proposal = TradeProposal.model_validate(agent.publish.await_args.args[1])
    assert proposal.side == side and proposal.size_usd <= 500
    assert (
        (proposal.stop_loss < 100 < proposal.take_profit)
        if side == OrderSide.BUY
        else (proposal.take_profit < 100 < proposal.stop_loss)
    )
    active = agent._active_longs if side == OrderSide.BUY else agent._active_shorts
    assert SYMBOL in active
    await agent._exit_position(SYMBOL, "rebalance")
    assert SYMBOL not in active
    agent.publish.reset_mock()
    await agent._enter(SYMBOL, side, 100, 0.25, Decimal(1))
    agent.publish.assert_not_awaited()


async def test_momentum_rebalance_ranks_assets_and_rate_limits(monkeypatch):
    agent = wire(momentum.MomentumStrategy())
    await agent._maybe_rebalance()
    agent.publish.assert_not_awaited()
    for index, symbol in enumerate(momentum._SYMBOLS):
        candles = candle_window(momentum._MIN_BARS)
        for i, candle in enumerate(candles):
            candles[i] = candle.model_copy(update={"close": Decimal(str(100 + i * (index + 1)))})
        agent._bars[symbol].extend(candles)
    agent._active_longs = {"OLD"}
    agent._active_shorts = {"OLD_SHORT"}
    await agent._maybe_rebalance()
    assert len(agent._active_longs) == momentum._LONG_TOP_N
    assert len(agent._active_shorts) == momentum._SHORT_TOP_N
    assert not agent._active_longs & agent._active_shorts
    count = agent.publish.await_count
    await agent._maybe_rebalance()
    assert agent.publish.await_count == count
    assert momentum._momentum_score(np.ones(3)) == 0
    assert momentum._momentum_score(np.zeros(300)) == 0


@pytest.mark.parametrize("factory", [trend.TrendFollower, breakout.BreakoutHunter])
@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
async def test_trailing_stops_tighten_without_loosening_and_signal_exit(factory, side):
    agent = wire(factory())
    if isinstance(agent, trend.TrendFollower):
        frame = pd.DataFrame({"close": [99, 100, 101, 100]})
        await agent._open_position(SYMBOL, side, 100, 2, 40, frame)

        def update(price):
            agent._update_trailing_stop(SYMBOL, price, 2)

    else:
        await agent._enter(SYMBOL, side, 100, 2)

        def update(price):
            agent._update_trailing_stop(
                SYMBOL, price, 2, "long" if side == OrderSide.BUY else "short"
            )

    call = agent.publish.await_args
    proposal = TradeProposal.model_validate(call.kwargs["payload"] if call.kwargs else call.args[1])
    assert proposal.side == side and proposal.size_usd > 10
    initial = agent._trailing_stops[SYMBOL]
    update(110 if side == OrderSide.BUY else 90)
    tight = agent._trailing_stops[SYMBOL]
    assert tight > initial if side == OrderSide.BUY else tight < initial
    update(100)
    assert agent._trailing_stops[SYMBOL] == tight
    price = tight - 1 if side == OrderSide.BUY else tight + 1
    state = MarketState(prices={SYMBOL: Decimal(str(price))}, symbol=SYMBOL, price=price)
    assert await agent.should_exit(position(side=side), state)
    if isinstance(agent, trend.TrendFollower):
        await agent._close_position(SYMBOL, "trailing_stop")
    else:
        await agent._exit(SYMBOL, price, "trailing_stop")
    assert agent._consecutive_losses == 1 and SYMBOL not in agent._trailing_stops
    assert not await agent.should_exit(position(side=side), state)


@pytest.mark.parametrize("side", [OrderSide.BUY, OrderSide.SELL])
async def test_mean_reversion_open_close_and_loss_tracking(side):
    agent = wire(mean.MeanReversion())
    agent._bars[SYMBOL].extend(candle_window(70))
    price = 90 if side == OrderSide.BUY else 110
    await agent._open_position(
        SYMBOL, side, price, -2.5 if side == OrderSide.BUY else 2.5, 0.3, 100, 20
    )
    proposal = TradeProposal.model_validate(agent.publish.await_args.kwargs["payload"])
    assert proposal.take_profit == 100 and proposal.side == side
    await agent._close_position(SYMBOL, "zscore_stop")
    assert agent._consecutive_losses == 1 and not agent._position_side
    await agent._close_position(SYMBOL, "reversion_complete")
    assert agent._consecutive_losses == 0


@pytest.mark.parametrize(
    "close,entry,expected",
    [
        (85, None, "BUY"),
        (115, None, "SELL"),
        (100, -2.5, "reversion_complete"),
        (120, 2.5, "zscore_stop"),
    ],
)
async def test_mean_reversion_evaluation_respects_bands_and_hurst(
    close, entry, expected, monkeypatch
):
    agent = wire(mean.MeanReversion())
    agent._bars[SYMBOL].extend(candle_window(70))
    frame = pd.DataFrame(
        {
            "close": [close] * 70,
            "BBU_20_2.0": [110] * 70,
            "BBL_20_2.0": [90] * 70,
            "BBM_20_2.0": [100] * 70,
        }
    )
    agent._compute_indicators = MagicMock(return_value=frame)
    monkeypatch.setattr(mean, "_hurst_exponent", lambda values: 0.3)
    agent._open_position = AsyncMock()
    agent._close_position = AsyncMock()
    if entry is not None:
        agent._position_z[SYMBOL] = entry
    await agent._evaluate(SYMBOL)
    if entry is None:
        assert agent._open_position.await_args.args[1].value == expected
    else:
        assert agent._close_position.await_args.args[1] == expected
    monkeypatch.setattr(mean, "_hurst_exponent", lambda values: 0.8)
    agent._open_position.reset_mock()
    agent._close_position.reset_mock()
    await agent._evaluate(SYMBOL)
    agent._open_position.assert_not_awaited()
    agent._close_position.assert_not_awaited()


async def test_macro_reads_nested_signals_and_real_price_cache():
    agent = wire(macro.MacroRotator())
    assert agent._majority_regime() == MarketRegime.NEUTRAL
    for _ in range(12):
        await agent._ingest_signal(
            {"topic": KafkaTopic.MACRO_REGIME.value, "payload": {"regime": "RISK_ON"}}
        )
    assert len(agent._regime_votes) == 10 and agent._current_regime == MarketRegime.RISK_ON
    await agent._ingest_signal(
        {"topic": KafkaTopic.VOLATILITY_FORECAST.value, "payload": {"regime": "VOLATILE"}}
    )
    await agent._ingest_signal(
        {"topic": KafkaTopic.MACRO_REGIME.value, "payload": {"regime": "INVALID"}}
    )
    agent.state.redis.get.return_value = b'{"price":"100"}'
    await agent._rebalance()
    assert len(agent._active_positions) == len(macro._RISK_ON_ASSETS)
    for call in agent.publish.await_args_list:
        proposal = TradeProposal.model_validate(call.args[1])
        assert proposal.size == proposal.size_usd / 100
    agent._current_regime = MarketRegime.CRISIS
    await agent._rebalance()
    assert not agent._active_positions
    assert await agent.should_exit(position(), None)


@pytest.mark.parametrize("direction", ["long_spread", "short_spread"])
async def test_stat_arb_pair_proposals_preserve_hedge_ratio(direction):
    agent = wire(arb.StatArb())
    pair = (SYMBOL, "ETH/USDT")
    await agent._enter_pair(
        pair, direction, 2.5, bar(close=100), bar(symbol="ETH/USDT", close=50), 2, 1
    )
    proposals = [
        TradeProposal.model_validate(call.args[1]) for call in agent.publish.await_args_list
    ]
    assert len(proposals) == 2 and proposals[0].side != proposals[1].side
    assert proposals[1].size == proposals[0].size * 2
    assert pair in agent._active_pairs
    await agent._exit_pair(pair, "reversion", 0)
    assert not agent._active_pairs


@pytest.mark.parametrize(
    "factory", [YieldFarmerAgent, DEXArbitrageurAgent, MEVHunterAgent, BridgeStrategistAgent]
)
@pytest.mark.parametrize("environment", ["development", "paper_trading", "live"])
async def test_defi_skeletons_never_emit_orders_or_pass_backtests(
    factory, environment, monkeypatch
):
    monkeypatch.setattr(settings, "environment", environment)
    monkeypatch.setattr(settings, "enable_defi_agents", False)
    agent = wire(factory())
    with pytest.raises(RuntimeError, match="disabled"):
        await agent.initialize()
    state = MarketState(prices={SYMBOL: Decimal(100)}, symbol=SYMBOL, price=100)
    assert await agent.generate_signal(state) is None
    with pytest.raises(NotImplementedError):
        agent.backtest(pd.DataFrame(), {})
    await agent.should_exit(position(), state)
    agent.publish.assert_not_awaited()
    await agent.shutdown()


def test_hurst_estimator_falls_back_for_short_constant_data():
    assert mean._hurst_exponent(np.ones(5)) == 0.5
    assert mean._hurst_exponent(np.ones(100)) == 0.5
    assert 0 <= mean._hurst_exponent(np.exp(np.random.default_rng(1).normal(size=200))) <= 1
