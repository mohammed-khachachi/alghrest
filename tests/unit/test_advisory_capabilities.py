"""Advisory capability denial must precede every order-capable side effect."""

import sys
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from pydantic import ValidationError

from agents import base_agent
from agents.tier5_execution import exchange_executor
from connectors.exchanges import ccxt_connector
from connectors.exchanges.paper import PaperVenue
from connectors.exchanges.recovery import SpotRecoveryAdapter
from core.config import OrderExecutionDisabledError, Settings, settings
from core.data.models import AgentMessage, Exchange, KafkaTopic, Order, OrderSide, OrderType
from core.execution.contracts import AccountScope
from core.execution.recovery import RecoveryCoordinator
from core.orchestrator import message_bus

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(
    params=[
        (profile, environment)
        for profile in ("earn2trade_tcp25", "earn2trade_tcp50")
        for environment in ("development", "paper_trading", "live")
    ]
)
def advisory(monkeypatch, request):
    profile, environment = request.param
    monkeypatch.setattr(settings, "operating_profile", profile)
    monkeypatch.setattr(settings, "environment", environment)


@pytest.fixture
def order():
    return Order(
        symbol="BTC/USD",
        exchange=Exchange.BINANCE,
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        size=Decimal("1"),
        strategy_id="capability-test",
        agent_id=12,
        exchange_order_id="existing-order",
    )


class InertAgent(base_agent.BaseAgent):
    async def initialize(self):
        pass

    async def run(self):
        pass

    async def shutdown(self):
        pass


@pytest.mark.parametrize("environment", ["development", "paper_trading", "live"])
@pytest.mark.parametrize("profile", ["earn2trade_tcp25", "earn2trade_tcp50"])
def test_profile_capability_is_independent_of_environment(environment, profile):
    general = Settings(_env_file=None, environment=environment, operating_profile="general")
    general.require_order_execution()
    advisor = Settings(_env_file=None, environment=environment, operating_profile=profile)
    with pytest.raises(OrderExecutionDisabledError):
        advisor.require_order_execution()


@pytest.mark.parametrize("profile", ["", "tcp25", "GENERAL", "unknown"])
def test_unknown_configuration_fails_closed(profile):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, operating_profile=profile)
    unsafe_copy = Settings(_env_file=None).model_copy(update={"operating_profile": profile})
    with pytest.raises(OrderExecutionDisabledError):
        unsafe_copy.require_order_execution()


async def test_agent_start_denied_before_any_initialization(advisory, monkeypatch):
    agent = InertAgent(99, 1, "capability-test")
    agent.state = AsyncMock()
    agent.producer = AsyncMock()
    metrics = MagicMock()
    logging = MagicMock()
    monkeypatch.setattr(base_agent, "start_metrics_server", metrics)
    monkeypatch.setattr(base_agent, "configure_logging", logging)
    with pytest.raises(OrderExecutionDisabledError):
        await agent.start()
    assert agent.state.mock_calls == agent.producer.mock_calls == []
    metrics.assert_not_called()
    logging.assert_not_called()


async def test_agent_publish_denied_even_with_replaced_producer(advisory):
    agent = InertAgent(99, 1, "capability-test")
    agent.producer = AsyncMock()
    with pytest.raises(OrderExecutionDisabledError):
        await agent.publish(KafkaTopic.PROPOSALS_APPROVED, {"intent": "buy"})
    assert agent.producer.mock_calls == []
    assert agent._messages_processed == 0


async def test_producer_denied_before_client_construction(advisory, monkeypatch):
    constructor = MagicMock()
    monkeypatch.setattr(message_bus, "AIOKafkaProducer", constructor)
    producer = message_bus.AlghrestProducer()
    with pytest.raises(OrderExecutionDisabledError):
        await producer.initialize()
    constructor.assert_not_called()
    assert producer._producer is None


@pytest.mark.parametrize("topic", list(KafkaTopic))
async def test_producer_blocks_all_legacy_topics_and_raw_publication(advisory, topic):
    producer = message_bus.AlghrestProducer()
    producer._producer = AsyncMock()
    message = AgentMessage(source_agent_id=12, topic=topic, message_type="test", payload={})
    with pytest.raises(OrderExecutionDisabledError):
        await producer.send(topic, message)
    with pytest.raises(OrderExecutionDisabledError):
        await producer.send_raw(topic.value, {})
    assert producer._producer.mock_calls == []


async def test_exchange_connection_denied_before_credentials_or_network(advisory, monkeypatch):
    constructor = MagicMock()
    monkeypatch.setattr(ccxt_connector.ccxtpro, "binance", constructor)
    connector = ccxt_connector.ExchangeConnector(Exchange.BINANCE)
    with pytest.raises(OrderExecutionDisabledError):
        await connector.connect()
    constructor.assert_not_called()
    assert connector._client is None


@pytest.mark.parametrize(
    "method,args",
    [
        ("place_limit_order", ("BTC/USD", OrderSide.BUY, Decimal("1"), Decimal("100"))),
        ("place_market_order", ("BTC/USD", OrderSide.BUY, Decimal("1"))),
        ("cancel_order", ("existing-order", "BTC/USD")),
        ("cancel_all_orders", ("BTC/USD",)),
    ],
)
async def test_direct_broker_mutation_denied_on_existing_client(advisory, method, args):
    connector = ccxt_connector.ExchangeConnector(Exchange.BINANCE)
    connector._client = AsyncMock()
    with pytest.raises(OrderExecutionDisabledError):
        await getattr(connector, method)(*args)
    assert connector._client.mock_calls == []


@pytest.mark.parametrize("method", ["initialize", "place", "lookup", "cancel"])
async def test_paper_mutations_and_matching_lookup_denied(advisory, order, method):
    store, state = MagicMock(), MagicMock()
    venue = PaperVenue(store, AccountScope(exchange=Exchange.BINANCE, symbols=["BTC/USD"]), state)
    with pytest.raises(OrderExecutionDisabledError):
        await getattr(venue, method)(*(() if method == "initialize" else (order,)))
    assert store.mock_calls == state.mock_calls == []


@pytest.mark.parametrize("method", ["place", "cancel"])
async def test_spot_adapter_denies_even_a_connector_without_guards(advisory, order, method):
    connector = MagicMock(exchange_id=Exchange.BINANCE, account_id="default")
    venue = SpotRecoveryAdapter(connector)
    with pytest.raises(OrderExecutionDisabledError):
        await getattr(venue, method)(order)
    assert connector.mock_calls == []


@pytest.mark.parametrize("method", ["initialize", "handle_order", "_place_order", "_submit"])
async def test_executor_denied_before_store_or_venue_contact(advisory, order, method, monkeypatch):
    executor = exchange_executor.ExchangeExecutor()
    executor.store = MagicMock()
    executor.state = MagicMock()
    venue = AsyncMock()
    executor.venues = {"stub": venue}
    connect = AsyncMock()
    monkeypatch.setattr(exchange_executor.Ledger, "connect", connect)
    args = (
        ()
        if method == "initialize"
        else ({"payload": order.model_dump()},) if method == "handle_order" else (order,)
    )
    with pytest.raises(OrderExecutionDisabledError):
        await getattr(executor, method)(*args)
    connect.assert_not_called()
    assert executor.store.mock_calls == executor.state.mock_calls == venue.mock_calls == []


@pytest.mark.parametrize("method", ["flush", "recover_orders", "_recover_orders", "run_once"])
async def test_recovery_denies_cancellation_and_outbox_before_store_contact(advisory, method):
    store, state, venue, publish = MagicMock(), MagicMock(), AsyncMock(), AsyncMock()
    recovery = RecoveryCoordinator(store, [], {"stub": venue}, state, publish)
    with pytest.raises(OrderExecutionDisabledError):
        await getattr(recovery, method)(*((True,) if "recover_orders" in method else ()))
    assert store.mock_calls == state.mock_calls == venue.mock_calls == publish.mock_calls == []


def test_runner_denies_before_dynamic_agent_import(advisory, monkeypatch):
    import run_agent

    importer = MagicMock()
    monkeypatch.setattr(run_agent.importlib, "import_module", importer)
    monkeypatch.setattr(sys, "argv", ["run_agent.py", "agents.fake", "FakeAgent"])
    with pytest.raises(OrderExecutionDisabledError):
        run_agent.main()
    importer.assert_not_called()


@pytest.mark.parametrize("mode", ["paper", "full"])
def test_launcher_denies_before_subprocess_start(advisory, monkeypatch, mode):
    from scripts import runtime

    run = MagicMock()
    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["runtime", mode, "start"])
    with pytest.raises(OrderExecutionDisabledError):
        runtime.main()
    run.assert_not_called()


@pytest.mark.parametrize("mode", ["research", "paper", "full"])
def test_read_only_launch_plan_remains_available(advisory, monkeypatch, mode, capsys):
    from scripts import runtime

    run = MagicMock()
    monkeypatch.setattr(runtime.subprocess, "run", run)
    monkeypatch.setattr(sys, "argv", ["runtime", mode, "plan"])
    assert runtime.main() == 0
    assert mode in capsys.readouterr().out
    run.assert_not_called()


async def test_trading_api_denied_before_redis_background_tasks_or_telegram(advisory, monkeypatch):
    from api import main

    state, loops = MagicMock(), AsyncMock()
    monkeypatch.setattr(main, "state_manager", state)
    monkeypatch.setattr(main, "start_background_loops", loops)
    with pytest.raises(OrderExecutionDisabledError):
        async with main.lifespan(main.app):
            pytest.fail("Trading API started under advisory profile")
    assert state.mock_calls == loops.mock_calls == []


def test_compose_profile_propagation_and_research_isolation():
    full = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    agents = [s for s in full["services"].values() if "run_agent.py" in s.get("command", "")]
    assert agents
    for service in agents:
        assert service["environment"]["OPERATING_PROFILE"] == "${OPERATING_PROFILE:-general}"
    research = yaml.safe_load((ROOT / "docker-compose.advisor.yml").read_text())
    assistant = research["services"]["manual-assistant"]
    assert assistant["environment"]["OPERATING_PROFILE"] == "earn2trade_tcp50"
    assert "env_file" not in assistant
    assert "api.advisor:app" in assistant["command"]
    assert assistant["ports"] == ["127.0.0.1:8011:8011"]
    assert assistant["environment"]["ADVISORY_KAFKA_SERVERS"] == ""
    assert set(assistant["environment"]) == {
        "OPERATING_PROFILE",
        "ADVISORY_ACCESS_TOKEN",
        "ADVISORY_DB_PATH",
        "ADVISORY_KAFKA_SERVERS",
    }
    assert assistant["volumes"] == ["research:/research"]
    assert assistant["read_only"] and assistant["cap_drop"] == ["ALL"]
    assert assistant["security_opt"] == ["no-new-privileges:true"]
    assert (
        not {"depends_on", "env_file", "links", "networks", "privileged", "devices"}
        & assistant.keys()
    )
