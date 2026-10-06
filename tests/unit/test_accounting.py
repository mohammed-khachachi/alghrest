"""Economic invariants and failure boundaries for durable spot accounting."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka.structs import TopicPartition

from core.accounting.engine import apply_fill, fingerprint
from core.accounting.models import BookState, CashBalance, OpeningBalances, key
from core.accounting.valuation import MissingValuationError, Valuation
from core.data.models import Exchange, Fill, FillFee, OrderSide
from core.orchestrator.message_bus import AlghrestConsumer

pytestmark = pytest.mark.unit
D = Decimal
NOW = datetime(2026, 1, 5, 12, tzinfo=UTC)


def fill(side="BUY", size="1", price="100", **kwargs):
    return Fill(
        order_id=uuid4(),
        exchange_order_id="order",
        exchange_trade_id=str(uuid4()),
        symbol="BTC/USD",
        exchange=Exchange.BINANCE,
        side=OrderSide(side),
        fill_size=D(size),
        fill_price=D(price),
        timestamp=NOW,
        fees=[],
        **kwargs,
    )


def opening():
    return OpeningBalances(
        as_of=NOW - timedelta(days=1),
        reference="test statement",
        cash=[
            CashBalance(exchange=Exchange.BINANCE, currency="USD", amount=D("1000")),
        ],
    )


def cash(state, currency="USD"):
    return state.cash[key("binance", "default", currency)].amount


def position(state):
    return state.positions[key("binance", "default", "BTC/USD")]


def test_weighted_cost_partial_close_and_flat_conserve_cash():
    state = BookState.from_opening(opening())
    apply_fill(state, fill(size="2"))
    apply_fill(state, fill(size="1", price="160"))
    assert position(state).average_cost == 120
    assert cash(state) == 640
    pnl = apply_fill(state, fill("SELL", size="1", price="150"))
    assert pnl == {"USD": D(30)}
    assert position(state).quantity == 2
    assert position(state).average_cost == 120
    pnl = apply_fill(state, fill("SELL", size="2", price="90"))
    assert pnl == {"USD": D(-60)}
    assert state.positions == {}
    assert cash(state) == 970


def test_short_close_and_reversal():
    state = BookState.from_opening(opening())
    apply_fill(state, fill("SELL", size="2", price="100"))
    assert position(state).quantity == -2
    assert cash(state) == 1200
    pnl = apply_fill(state, fill("BUY", size="3", price="80"))
    assert pnl["USD"] == 40
    assert position(state).quantity == 1
    assert position(state).average_cost == 80
    assert cash(state) == 960


def test_quote_base_and_third_currency_fees_and_rebates():
    state = BookState.from_opening(opening())
    buy = fill(size="2").model_copy(
        update={
            "fees": [
                FillFee(currency="BTC", amount=D("0.1")),
                FillFee(currency="USD", amount=D("1")),
                FillFee(currency="BNB", amount=D("0.02")),
            ]
        }
    )
    realized = apply_fill(state, buy)
    assert cash(state) == 799
    assert cash(state, "BNB") == D("-0.02")
    assert position(state).quantity == D("1.9")
    assert realized["BNB"] == D("-0.02")
    sell = fill("SELL", size="1.9", price="120").model_copy(
        update={
            "fees": [FillFee(currency="USD", amount=D("-1"))],
        }
    )
    pnl = apply_fill(state, sell)
    assert pnl["USD"] == pytest.approx(D(28))
    assert cash(state) == 1028
    assert not state.positions


def test_replay_fingerprint_ignores_internal_uuid_and_decimal_format():
    original = fill(size="1.00", price="100.00")
    replay = original.model_copy(
        update={"fill_id": uuid4(), "order_id": uuid4(), "fill_size": D(1)}
    )
    assert fingerprint(original) == fingerprint(replay)
    assert fingerprint(original) != fingerprint(original.model_copy(update={"fill_price": D(101)}))


@pytest.mark.parametrize(
    "changes",
    [
        {"exchange_trade_id": None},
        {"fill_size": D(0)},
        {"fill_price": D("NaN")},
        {"symbol": "BTC/USDT:USDT"},
        {"fees": [FillFee(currency="BTC", amount=D(2))]},
    ],
)
def test_invalid_fill_is_rejected(changes):
    with pytest.raises(ValueError):
        apply_fill(BookState.from_opening(opening()), fill().model_copy(update=changes))


@pytest.mark.asyncio
async def test_nav_matches_cash_plus_marked_inventory():
    state = BookState.from_opening(opening())
    apply_fill(state, fill(size="2"))
    marks = SimpleNamespace(
        get_json=AsyncMock(return_value={"price": "120", "timestamp": NOW.isoformat()})
    )
    result = await Valuation(marks, NOW, []).portfolio("test", state, [])
    assert result.total_capital == 1000
    assert result.unrealized_pnl == 40
    assert result.total_capital + result.unrealized_pnl == 1040
    assert result.available_capital == 800
    assert result.total_exposure_usd == 240
    assert result.accounting_book_id == "test"
    marks.get_json.assert_awaited_with("accounting:mark:binance:BTC/USD")


@pytest.mark.asyncio
async def test_usdt_is_not_silently_treated_as_usd_and_stale_marks_fail():
    marks = SimpleNamespace(get_json=AsyncMock(return_value=None))
    with pytest.raises(MissingValuationError):
        await Valuation(marks, NOW, []).usd("binance", "USDT")
    assert await Valuation(marks, NOW, ["USDT"]).usd("binance", "USDT") == 1
    marks.get_json.return_value = {
        "price": "100",
        "timestamp": (NOW - timedelta(minutes=10)).isoformat(),
    }
    with pytest.raises(MissingValuationError):
        await Valuation(marks, NOW, []).mark("binance", "BTC/USD")


@pytest.mark.asyncio
async def test_foreign_cash_is_valued_and_exposed_in_gross_exposure():
    state = BookState.from_opening(
        OpeningBalances(
            as_of=NOW - timedelta(days=1),
            reference="test",
            cash=[
                CashBalance(exchange=Exchange.BINANCE, currency="BNB", amount=D("-0.2")),
            ],
        )
    )
    marks = SimpleNamespace(
        get_json=AsyncMock(return_value={"price": "300", "timestamp": NOW.isoformat()})
    )
    result = await Valuation(marks, NOW, []).portfolio("test", state, [])
    assert result.total_capital == -60
    assert result.available_capital == 0
    assert result.total_exposure_usd == 60
    assert result.cash_currency_exposure_usd == 60


@pytest.mark.asyncio
async def test_daily_weekly_pnl_and_short_collateral():
    state = BookState.from_opening(opening())
    apply_fill(state, fill("SELL", size="2"))
    marks = SimpleNamespace(
        get_json=AsyncMock(return_value={"price": "110", "timestamp": NOW.isoformat()})
    )
    rows = [
        {"exchange": "binance", "occurred_at": NOW, "realized": '{"USD":"12"}'},
        {"exchange": "binance", "occurred_at": NOW - timedelta(days=1), "realized": '{"USD":"99"}'},
    ]
    result = await Valuation(marks, NOW, []).portfolio("test", state, rows)
    assert result.total_capital + result.unrealized_pnl == 980
    assert result.available_capital == 760  # 1,200 proceeds/cash minus 440 collateral
    assert result.daily_pnl == result.weekly_pnl == 12  # Monday UTC boundary


class Records:
    def __init__(self):
        self.commit = AsyncMock()

    def __aiter__(self):
        async def records():
            for offset in range(2):
                yield SimpleNamespace(
                    topic="fills.confirmed", partition=0, offset=offset, value={"offset": offset}
                )

        return records()


@pytest.mark.asyncio
async def test_handler_failure_never_commits_or_skips_a_fill():
    consumer = AlghrestConsumer("test", [])
    consumer._consumer = Records()
    handler = AsyncMock(side_effect=RuntimeError("database unavailable"))
    with pytest.raises(RuntimeError, match="database unavailable"):
        await consumer.process(handler)
    consumer._consumer.commit.assert_not_awaited()
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_is_after_success_and_scoped_to_processed_partition():
    consumer = AlghrestConsumer("test", [])
    consumer._consumer = Records()
    events = []

    async def handle(message):
        events.append(("durable", message["offset"]))

    async def commit(offsets):
        events.append(("ack", offsets[TopicPartition("fills.confirmed", 0)]))

    consumer._consumer.commit.side_effect = commit
    await consumer.process(handle)
    assert events == [("durable", 0), ("ack", 1), ("durable", 1), ("ack", 2)]
