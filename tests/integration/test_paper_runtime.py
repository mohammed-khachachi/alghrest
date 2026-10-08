"""Opt-in real Kafka/PG/Redis smoke on the dedicated local paper infrastructure.

All balances are explicitly synthetic, in a unique test book, topic and Redis DB.
No events enter the runtime orders/fills topics. All test data is removed.
"""

import asyncio
import json
import os
import statistics
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import psutil
import pytest
from aiokafka.admin import AIOKafkaAdminClient, NewTopic

from agents.tier1_executive.proposal_approver import ProposalApprover
from agents.tier5_execution.exchange_executor import ExchangeExecutor
from agents.tier5_execution.order_router import OrderRouter
from agents.tier7_monitoring.portfolio_accountant import PortfolioAccountant
from connectors.exchanges.paper import PaperVenue
from core.accounting.models import CashBalance, OpeningBalances
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import AgentMessage, Exchange, KafkaTopic, OrderSide, OrderType, TradeProposal
from core.execution.contracts import AccountScope
from core.execution.recovery import RecoveryCoordinator
from core.execution.store import ExecutionStore
from core.orchestrator.message_bus import AlghrestConsumer, AlghrestProducer
from core.orchestrator.state_manager import StateManager
from scripts.paper_runtime import require_local_paper
from tests.factories import persist_snapshot

pytestmark = pytest.mark.integration


async def test_durable_fill_survives_real_kafka_consumer_restart(monkeypatch):
    if os.getenv("PAPER_RUNTIME_TESTS") != "1":
        pytest.skip("Set PAPER_RUNTIME_TESTS=1 with the isolated paper infrastructure running")
    require_local_paper()
    token = uuid4().hex
    monkeypatch.setattr(settings, "accounting_book", f"smoke-{token}")
    monkeypatch.setattr(settings, "redis_db_state", 15)
    topics = {
        kind: f"paper-smoke-{token}-{kind.name.lower()}"
        for kind in (
            KafkaTopic.PROPOSALS_BUS,
            KafkaTopic.PROPOSALS_APPROVED,
            KafkaTopic.ORDERS_PENDING,
            KafkaTopic.FILLS_CONFIRMED,
        )
    }
    account = AccountScope(exchange=Exchange.BINANCE, symbols=["BTC/USDT", "SOL/USDT", "GALA/USDT"])
    monkeypatch.setattr(settings, "execution_accounts", [account])
    proposals = []
    last_fill = None
    ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
    store = ExecutionStore(ledger)
    state, producer = StateManager(), AlghrestProducer()
    admin = AIOKafkaAdminClient(bootstrap_servers=settings.kafka_servers_list)
    consumers, tasks = [], []
    try:
        await admin.start()
        await admin.create_topics(
            [NewTopic(topic, num_partitions=1, replication_factor=1) for topic in topics.values()]
        )
        await state.initialize()
        now = datetime.now(UTC)
        for symbol, price in (("SOL/USDT", "100"), ("USDT/USD", "1")):
            await state.set_accounting_mark(
                "binance", symbol, price, now.isoformat(), int(now.timestamp() * 1000)
            )
        await ledger.open_book(
            OpeningBalances(
                as_of=now - timedelta(minutes=1),
                reference="isolated synthetic transport smoke",
                cash=[CashBalance(exchange=Exchange.BINANCE, currency="USDT", amount=Decimal(150))],
            )
        )
        await ledger.claim_writer()
        await store.claim_writer()
        await store.configure([account])
        paper = PaperVenue(store, account, state)
        await paper.initialize()
        await producer.initialize()

        async def publish(source_topic, payload, message_type):
            if source_topic == KafkaTopic.RISK_ALERTS:
                if await state.is_kill_switch_active():
                    assert "system kill switch active" in payload["message"]
                    return
                raise AssertionError(payload)
            if source_topic in topics:
                await producer.send(
                    topics[source_topic],
                    AgentMessage(
                        source_agent_id=26,
                        topic=source_topic,
                        message_type=message_type,
                        payload=payload,
                    ),
                )

        recovery = RecoveryCoordinator(store, [account], {account.key: paper}, state, publish)
        await state.set_accounting_portfolio(await persist_snapshot(ledger, state))
        assert (await recovery.run_once())["ready"]
        assert await state.trading_ready()
        approver, router, executor = ProposalApprover(), OrderRouter(), ExchangeExecutor()
        for component in (approver, router, executor):
            component.state = state
            component.publish = publish
        executor.store, executor.venues = store, {account.key: paper}
        agent = PortfolioAccountant()
        agent.ledger = ledger
        proposal = TradeProposal(
            symbol="SOL/USDT",
            exchange=Exchange.BINANCE,
            asset_class="CRYPTO",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            size=Decimal("0.05"),
            size_usd=Decimal(5),
            limit_price=Decimal(100),
            stop_loss=Decimal(99),
            confidence_score=0.9,
            strategy_id="synthetic-smoke",
            agent_id=12,
        )
        proposals.append(proposal)

        async def dispatch(message, fill_handler):
            kind, payload = message["topic"], message["payload"]
            if kind == KafkaTopic.PROPOSALS_BUS:
                await approver._process(payload)
            elif kind == KafkaTopic.PROPOSALS_APPROVED:
                await router._route(payload)
            elif kind == KafkaTopic.ORDERS_PENDING:
                await executor.handle_order(message)
                await recovery.run_once()
            else:
                await fill_handler(message)

        async def crash_after_commit(message):
            await agent.handle_fill(message)
            raise RuntimeError("simulated process failure after database commit")

        first = AlghrestConsumer(
            agent_name=token, topics=list(topics.values()), auto_offset_reset="earliest"
        )
        consumers.append(first)
        await first.initialize()

        async def first_dispatch(message):
            await dispatch(message, crash_after_commit)

        processing = asyncio.create_task(first.process(first_dispatch))
        tasks.append(processing)
        await publish(KafkaTopic.PROPOSALS_BUS, proposal.model_dump(mode="json"), "TradeProposal")
        with pytest.raises(RuntimeError, match="after database commit"):
            await asyncio.wait_for(processing, timeout=30)
        assert (await ledger.load()).revision == 1
        assert not await first.caught_up()  # fill committed to PG but never acknowledged to Kafka
        await first.shutdown()
        consumers.remove(first)
        # Recreate every durable execution/accounting object, not just the consumer.
        await store.close()
        ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        await ledger.claim_writer()
        store = ExecutionStore(ledger)
        await store.claim_writer()
        await store.configure([account])
        paper = PaperVenue(store, account, state)
        await paper.initialize()
        assert (await paper.balances())["USDT"] == Decimal("144.995")
        recovery = RecoveryCoordinator(store, [account], {account.key: paper}, state, publish)
        executor.store, executor.venues = store, {account.key: paper}
        agent.ledger = ledger

        second = AlghrestConsumer(
            agent_name=token, topics=list(topics.values()), auto_offset_reset="earliest"
        )
        consumers.append(second)
        await second.initialize()
        seen = asyncio.Event()

        async def replay(message):
            nonlocal last_fill
            last_fill = message
            await agent.handle_fill(message)
            seen.set()

        async def second_dispatch(message):
            await dispatch(message, replay)

        processing = asyncio.create_task(second.process(second_dispatch))
        tasks.append(processing)
        await asyncio.wait_for(seen.wait(), timeout=30)
        async with asyncio.timeout(10):
            while not await second.caught_up():
                await asyncio.sleep(0.05)
        assert (await ledger.load()).revision == 1
        assert (await paper.balances())["USDT"] == Decimal("144.995")
        portfolio = await persist_snapshot(ledger, state)
        assert (await recovery.run_once())["ready"]
        await state.set_accounting_portfolio(portfolio)
        assert await state.trading_ready()
        assert portfolio.total_capital + portfolio.unrealized_pnl == Decimal("149.995")
        assert len(portfolio.positions) == 1 and portfolio.positions[0].size == Decimal("0.05")
        # Close through the same approval and Kafka path, then reconcile exact fees.
        closing = proposal.model_copy(update={"proposal_id": uuid4(), "side": OrderSide.SELL})
        proposals.append(closing)
        seen.clear()
        await publish(KafkaTopic.PROPOSALS_BUS, closing.model_dump(mode="json"), "TradeProposal")
        async with asyncio.timeout(30):
            while (await ledger.load()).revision != 2:
                await asyncio.sleep(0.05)
            while not await second.caught_up():
                await asyncio.sleep(0.05)
        await persist_snapshot(ledger, state)
        assert (await recovery.run_once())["ready"]
        book = await ledger.load()
        assert not book.positions
        assert (await paper.balances())["USDT"] == Decimal("149.990")
        assert (
            await ledger.pool.fetchval(
                "SELECT count(*) FROM execution.paper_orders WHERE book_id=$1", ledger.book_id
            )
            == 2
        )
        assert (
            await ledger.pool.fetchval(
                "SELECT count(*) FROM accounting.fills WHERE book_id=$1", ledger.book_id
            )
            == 2
        )
        assert approver._approved_count == executor._placed_count == 2
        final = await persist_snapshot(ledger, state)
        await state.set_accounting_portfolio(final)
        assert (
            final.total_capital + final.unrealized_pnl == Decimal("149.990")
            and await state.trading_ready()
        )

        # Sustained bounded order flow on synthetic funds, then a duplicate burst.
        process = psutil.Process()
        memory_before = process.memory_info().rss
        cpu_before = sum(process.cpu_times()[:2])
        started = time.perf_counter()
        latencies = []
        for index in range(20):
            next_proposal = proposal.model_copy(
                update={
                    "proposal_id": uuid4(),
                    "created_at": datetime.now(UTC),
                    "side": OrderSide.BUY if index % 2 == 0 else OrderSide.SELL,
                }
            )
            proposals.append(next_proposal)
            tick = time.perf_counter()
            await publish(
                KafkaTopic.PROPOSALS_BUS, next_proposal.model_dump(mode="json"), "TradeProposal"
            )
            async with asyncio.timeout(30):
                while (await ledger.load()).revision != index + 3 or not await second.caught_up():
                    if processing.done():
                        processing.result()
                    await asyncio.sleep(0.01)
            latencies.append((time.perf_counter() - tick) * 1000)
            await state.set_accounting_portfolio(await persist_snapshot(ledger, state))
            assert (await recovery.run_once())["ready"]
        assert last_fill is not None
        await asyncio.gather(
            *(publish(KafkaTopic.FILLS_CONFIRMED, last_fill["payload"], "Fill") for _ in range(100))
        )
        async with asyncio.timeout(30):
            while not await second.caught_up():
                await asyncio.sleep(0.01)
        book = await ledger.load()
        assert book.revision == 22 and not book.positions
        assert (await paper.balances())["USDT"] == Decimal("149.890")
        assert approver._approved_count == executor._placed_count == 22
        # A halt still prevents admission after the burst (on test Redis DB 15).
        await state.activate_kill_switch("isolated load-test halt")
        halt_start = time.perf_counter()
        blocked = proposal.model_copy(
            update={"proposal_id": uuid4(), "created_at": datetime.now(UTC)}
        )
        proposals.append(blocked)
        await approver._process(blocked.model_dump(mode="json"))
        assert approver._rejected_count == 1 and executor._placed_count == 22
        print(
            "PAPER_LOAD "
            + json.dumps(
                {
                    "executed_orders": 22,
                    "duplicate_fills": 100,
                    "cash_usdt": "149.890",
                    "latency_p50_ms": round(statistics.median(latencies), 2),
                    "latency_p95_ms": round(sorted(latencies)[18], 2),
                    "halt_admission_ms": round((time.perf_counter() - halt_start) * 1000, 2),
                    "elapsed_s": round(time.perf_counter() - started, 2),
                    "cpu_s": round(sum(process.cpu_times()[:2]) - cpu_before, 3),
                    "rss_before_mb": round(memory_before / 1024**2, 2),
                    "rss_after_mb": round(process.memory_info().rss / 1024**2, 2),
                }
            )
        )
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for consumer in consumers:
            await consumer.shutdown()
        await producer.shutdown()
        try:
            await admin.delete_topics(list(topics.values()))
        finally:
            await admin.close()
        if state._redis is not None:
            await state.redis.delete(
                "accounting:mark:binance:SOL/USDT",
                "accounting:mark:binance:USDT/USD",
                *(f"proposal_review:{p.proposal_id}" for p in proposals),
                "alghrest:portfolio:current",
                "alghrest:kill_switch:active",
                f"alghrest:reconciliation:{ledger.book_id}",
            )
            await state.shutdown()
        for table in (
            "paper_fills",
            "paper_orders",
            "paper_accounts",
            "outbox",
            "fills",
            "cursors",
            "orders",
            "books",
        ):
            await ledger.pool.execute(
                f"DELETE FROM execution.{table} WHERE book_id=$1", ledger.book_id
            )
        await ledger.pool.execute("DELETE FROM accounting.fills WHERE book_id=$1", ledger.book_id)
        await ledger.pool.execute("DELETE FROM accounting.books WHERE book_id=$1", ledger.book_id)
        await store.close()
