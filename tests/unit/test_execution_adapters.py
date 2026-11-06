"""Exchange pagination protocols, uncertain identity lookup and live-write guards."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import ccxt.pro as ccxtpro
import pytest

from connectors.exchanges.ccxt_connector import (
    ExchangeConnector,
    is_dict_list,
    is_str_object_dict,
)
from connectors.exchanges.recovery import SpotRecoveryAdapter
from core.config import settings
from core.data.models import Exchange, Order, OrderSide, OrderType
from core.execution.contracts import RecoveryBlockedError, balance_differences

pytestmark = pytest.mark.unit


def trade(tid="1", **changes):
    return (
        dict(
            id=tid,
            order="order",
            symbol="BTC/USD",
            side="buy",
            amount="1",
            price="100",
            timestamp=1000,
            fee={"currency": "USD", "cost": "0.1"},
        )
        | changes
    )


def adapter(exchange):
    connector = ExchangeConnector(exchange)
    connector._client = MagicMock()
    connector._client.market.return_value = {"id": "BTCUSD"}
    connector._client.parse_trade.side_effect = lambda raw, market: raw
    connector._client.parse_order.side_effect = lambda raw, market=None: raw
    return SpotRecoveryAdapter(connector)


def order(exchange):
    return Order(
        symbol="BTC/USD",
        exchange=exchange,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal(1),
        strategy_id="test",
        agent_id=12,
    )


async def test_binance_subdivides_saturated_window_without_advancing_past_timestamp_ties():
    venue = adapter(Exchange.BINANCE)
    trades = [trade(str(i), timestamp=1000 + i // 2) for i in range(1200)]

    async def fetch(symbol, start, limit, params):
        return [t for t in trades if start <= t["timestamp"] <= params["until"]][:limit]

    venue.client.fetch_my_trades = AsyncMock(side_effect=fetch)
    ids, cursor, calls = set(), None, 0
    while True:
        page = await venue.history_page("BTC/USD", 1000, 2000, cursor)
        ids.update(f.exchange_trade_id for f in page.fills)
        cursor = page.cursor
        calls += 1
        if cursor is None:
            break
        assert calls < 20
    assert len(ids) == 1200
    assert calls > 1


async def test_binance_single_timestamp_saturation_or_outside_window_blocks():
    venue = adapter(Exchange.BINANCE)
    venue.client.fetch_my_trades = AsyncMock(return_value=[trade(str(i)) for i in range(1000)])
    with pytest.raises(RecoveryBlockedError, match="saturated"):
        await venue.history_page("BTC/USD", 1000, 1000, None)
    with pytest.raises(RecoveryBlockedError, match="outside"):
        await venue.history_page("BTC/USD", 2000, 3000, None)


@pytest.mark.parametrize("exchange", [Exchange.BYBIT, Exchange.COINBASE])
async def test_native_cursor_followed_even_for_short_page(exchange):
    venue = adapter(exchange)
    responses = (
        [
            {"result": {"list": [trade()], "nextPageCursor": "next"}},
            {"result": {"list": [trade("2")], "nextPageCursor": ""}},
        ]
        if exchange == Exchange.BYBIT
        else [
            {"fills": [trade()], "cursor": "next"},
            {"fills": [trade("2", timestamp=10)], "cursor": ""},
        ]
    )
    endpoint = AsyncMock(side_effect=responses)
    if exchange == Exchange.BYBIT:
        venue.client.privateGetV5ExecutionList = endpoint
    else:
        venue.client.v3PrivateGetBrokerageOrdersHistoricalFills = endpoint
    first = await venue.history_page("BTC/USD", 1000, 2000, None)
    second = await venue.history_page("BTC/USD", 1000, 2000, first.cursor)
    assert second.cursor is None and second.fills[0].exchange_trade_id == "2"
    assert endpoint.await_args.args[0]["cursor"] == "next"
    # Coinbase execution time can precede the sequence-time query window.
    assert len(second.fills) == 1


async def test_kraken_counts_unfiltered_account_history_and_preserves_other_symbols():
    venue = adapter(Exchange.KRAKEN)
    venue.client.privatePostTradesHistory = AsyncMock(
        side_effect=[
            {"result": {"trades": {"one": trade(symbol="ETH/USD")}, "count": 2}},
            {"result": {"trades": {"two": trade()}, "count": 2}},
        ]
    )
    first = await venue.history_page("*", 1000, 2000, None)
    second = await venue.history_page("*", 1000, 2000, first.cursor)
    assert first.fills[0].symbol == "ETH/USD"
    assert second.cursor is None
    assert venue.client.privatePostTradesHistory.await_args.args[0]["ofs"] == 1
    venue.client.privatePostTradesHistory.side_effect = None
    venue.client.privatePostTradesHistory.return_value = {"result": {"trades": {}, "count": 2}}
    with pytest.raises(RecoveryBlockedError, match="Incomplete"):
        await venue.history_page("*", 1000, 2000, None)


@pytest.mark.parametrize("exchange", [Exchange.BINANCE, Exchange.BYBIT])
async def test_ambiguous_lookup_requires_matching_client_id(exchange):
    venue = adapter(exchange)
    intent = order(exchange)
    raw = dict(
        id="one",
        symbol="BTC/USD",
        side="buy",
        type="market",
        amount="1",
        filled="0",
        status="open",
        clientOrderId=str(intent.client_order_id),
    )
    venue.client.fetch_order = AsyncMock(return_value=raw)
    venue.client.privateGetV5OrderRealtime = AsyncMock(return_value={"result": {"list": [raw]}})
    assert (await venue.lookup(intent)).exchange_order_id == "one"
    raw["clientOrderId"] = str(uuid4())
    with pytest.raises(RecoveryBlockedError, match="different order"):
        await venue.lookup(intent)


async def test_coinbase_client_lookup_paginates_closed_history():
    venue = adapter(Exchange.COINBASE)
    intent = order(Exchange.COINBASE)
    raw = dict(
        id="one",
        symbol="BTC/USD",
        side="buy",
        type="market",
        amount="1",
        filled="1",
        status="closed",
        client_order_id=str(intent.client_order_id),
        clientOrderId=str(intent.client_order_id),
    )
    venue.client.v3PrivateGetBrokerageOrdersHistoricalBatch = AsyncMock(
        side_effect=[
            {"orders": [], "has_next": True, "cursor": "next"},
            {"orders": [raw], "has_next": False},
        ]
    )
    assert (await venue.lookup(intent)).exchange_order_id == "one"
    assert venue.client.v3PrivateGetBrokerageOrdersHistoricalBatch.await_count == 2


async def test_kraken_unknown_submission_scans_closed_orders_by_client_identity():
    venue = adapter(Exchange.KRAKEN)
    intent = order(Exchange.KRAKEN)
    venue.client.privatePostOpenOrders = AsyncMock(return_value={"result": {"open": {}}})
    raw = dict(
        symbol="BTC/USD",
        side="buy",
        type="market",
        amount="1",
        filled="1",
        status="closed",
        cl_ord_id=str(intent.client_order_id),
    )
    venue.client.privatePostClosedOrders = AsyncMock(
        return_value={"result": {"closed": {"one": raw}, "count": 1}}
    )
    assert (await venue.lookup(intent)).exchange_order_id == "one"


@pytest.mark.parametrize("environment", ["development", "paper_trading"])
async def test_nonlive_connector_never_calls_private_write_api(monkeypatch, environment):
    monkeypatch.setattr(settings, "environment", environment)
    conn = ExchangeConnector(Exchange.BINANCE)
    conn._client = SimpleNamespace(
        create_market_order=AsyncMock(), create_limit_order=AsyncMock(), cancel_order=AsyncMock()
    )
    for operation in (
        conn.place_market_order("BTC/USD", OrderSide.BUY, Decimal(1)),
        conn.place_limit_order("BTC/USD", OrderSide.BUY, Decimal(1), Decimal(100)),
        conn.cancel_order("one", "BTC/USD"),
    ):
        with pytest.raises(RuntimeError, match="ENVIRONMENT=live"):
            await operation
    conn._client.create_market_order.assert_not_awaited()
    conn._client.cancel_order.assert_not_awaited()


async def test_unverified_live_protective_bundle_is_rejected_before_venue_contact():
    venue = adapter(Exchange.BINANCE)
    with pytest.raises(RecoveryBlockedError, match="protective-order"):
        await venue.place(order(Exchange.BINANCE).model_copy(update={"stop_price": Decimal(90)}))
    assert not venue.client.mock_calls


async def test_live_ambiguous_create_is_never_retried(monkeypatch):
    monkeypatch.setattr(settings, "environment", "live")
    conn = ExchangeConnector(Exchange.BINANCE)
    conn._client = SimpleNamespace(
        create_market_order=AsyncMock(side_effect=ccxtpro.NetworkError("response lost"))
    )
    with pytest.raises(ccxtpro.NetworkError):
        await conn.place_market_order("BTC/USD", OrderSide.BUY, Decimal(1), str(uuid4()))
    conn._client.create_market_order.assert_awaited_once()


def test_native_balance_comparison_requires_explicit_tolerance_includes_liabilities():
    assert balance_differences({"USD": Decimal(100)}, {"USD": Decimal("100.01")}, {})
    assert not balance_differences(
        {"USD": Decimal(100)}, {"USD": Decimal("100.01")}, {"USD": Decimal("0.01")}
    )
    assert "BNB" in balance_differences({}, {"BNB": Decimal("-0.1")}, {})
    with pytest.raises(ValueError):
        balance_differences({}, {"USD": Decimal("NaN")}, {})


@pytest.mark.parametrize(
    "exchange", [Exchange.BINANCE, Exchange.BYBIT, Exchange.COINBASE, Exchange.KRAKEN]
)
async def test_open_order_scan_includes_unconfigured_markets(exchange):
    venue = adapter(exchange)
    raw = dict(
        id="one",
        symbol="ETH/USD",
        side="buy",
        type="limit",
        amount="1",
        filled="0",
        status="open",
        clientOrderId="external",
    )
    if exchange == Exchange.BINANCE:
        venue.client.fetch_open_orders = AsyncMock(return_value=[raw])
    elif exchange == Exchange.KRAKEN:
        venue.client.privatePostOpenOrders = AsyncMock(
            return_value={"result": {"open": {"one": raw}}}
        )
    elif exchange == Exchange.BYBIT:
        venue.client.privateGetV5OrderRealtime = AsyncMock(
            side_effect=[
                {"result": {"list": [], "nextPageCursor": "next"}},
                {"result": {"list": [raw], "nextPageCursor": ""}},
            ]
        )
    else:
        venue.client.v3PrivateGetBrokerageOrdersHistoricalBatch = AsyncMock(
            side_effect=[
                {"orders": [], "has_next": True, "cursor": "next"},
                {"orders": [raw], "has_next": False},
            ]
        )
    orders = await venue.open_orders()
    assert len(orders) == 1 and orders[0].symbol == "ETH/USD"


async def test_missing_submission_and_repeated_open_cursor_remain_unresolved():
    venue = adapter(Exchange.BINANCE)
    venue.client.fetch_order = AsyncMock(side_effect=ccxtpro.OrderNotFound())
    assert await venue.lookup(order(Exchange.BINANCE)) is None
    venue = adapter(Exchange.BYBIT)
    venue.client.privateGetV5OrderRealtime = AsyncMock(
        return_value={"result": {"list": [], "nextPageCursor": "same"}}
    )
    with pytest.raises(RecoveryBlockedError, match="cursor repeated"):
        await venue.open_orders()


async def test_adapter_passes_stable_submission_id_and_cancel_failure_is_not_success():
    venue = adapter(Exchange.BINANCE)
    intent = order(Exchange.BINANCE)
    venue.connector.place_market_order = AsyncMock(return_value=intent)
    await venue.place(intent)
    assert venue.connector.place_market_order.await_args.kwargs["client_order_id"] == str(
        intent.client_order_id
    )
    venue.connector.place_limit_order = AsyncMock(return_value=intent)
    await venue.place(
        intent.model_copy(update={"order_type": OrderType.LIMIT, "price": Decimal(99)})
    )
    venue.connector.place_limit_order.assert_awaited_once()
    with pytest.raises(RecoveryBlockedError, match="unidentified"):
        await venue.cancel(intent)
    venue.connector.cancel_order = AsyncMock(return_value=False)
    with pytest.raises(RecoveryBlockedError, match="not confirmed"):
        await venue.cancel(intent.model_copy(update={"exchange_order_id": "one"}))


async def test_testnet_uses_sandbox_urls_and_never_falls_back_to_live_credentials(monkeypatch):
    monkeypatch.setattr(settings, "binance_testnet", True)
    monkeypatch.setattr(settings, "binance_testnet_api_key", "")
    monkeypatch.setattr(settings, "binance_testnet_secret", "")
    monkeypatch.setattr(settings, "binance_api_key", "synthetic-live-key")
    monkeypatch.setattr(settings, "binance_secret", "synthetic-live-secret")
    client = SimpleNamespace(
        set_sandbox_mode=MagicMock(), load_markets=AsyncMock(), close=AsyncMock()
    )
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(ccxtpro, "binance", factory)
    connector = ExchangeConnector(Exchange.BINANCE)
    await connector.connect()
    client.set_sandbox_mode.assert_called_once_with(True)
    assert factory.call_args.args[0]["apiKey"] == ""
    assert factory.call_args.args[0]["secret"] == ""
    await connector.close()


async def test_ccxt_type_guards_and_disconnected_client_rejection():
    assert is_str_object_dict({"symbol": "BTC/USD", "last": 50000})
    assert not is_str_object_dict(["not", "a", "dict"])
    assert not is_str_object_dict({1: "non-string-key"})
    assert is_dict_list([{"id": "1"}, {"id": "2"}])
    assert not is_dict_list([{"id": "1"}, "not-a-dict"])

    disconnected = ExchangeConnector(Exchange.BINANCE)
    with pytest.raises(RuntimeError, match="not connected"):
        await disconnected.fetch_balance()
    with pytest.raises(RuntimeError, match="not connected"):
        _ = SpotRecoveryAdapter(disconnected).client

    conn = ExchangeConnector(Exchange.BINANCE)
    conn._client = SimpleNamespace(
        fetch_ticker=AsyncMock(return_value=["malformed"]),
        fetch_open_orders=AsyncMock(return_value={"not": "a-list"}),
    )
    with pytest.raises(ValueError, match="Expected dict payload"):
        await conn.fetch_ticker("BTC/USD")
    with pytest.raises(ValueError, match="Expected list\\[dict\\] payload"):
        await conn.fetch_open_orders("BTC/USD")
