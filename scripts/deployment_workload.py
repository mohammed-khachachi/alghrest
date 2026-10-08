"""Worker for deployment_soak; uses real services and synthetic, fixed-price paper orders."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import asyncpg
import httpx
import psutil
from aiokafka import AIOKafkaConsumer
from aiokafka.admin import AIOKafkaAdminClient
from aiokafka.errors import KafkaConnectionError, SaslAuthenticationFailed
from websockets.asyncio.client import connect

from core.accounting.models import CashBalance, OpeningBalances, key
from core.accounting.repository import Ledger
from core.config import settings
from core.data.models import (
    AgentMessage,
    Exchange,
    KafkaTopic,
    OrderSide,
    OrderType,
    TradeProposal,
    TradeProposalReview,
    TradeProposalStatus,
)
from core.kafka.security import aiokafka_security
from core.orchestrator.message_bus import AlghrestProducer
from core.orchestrator.state_manager import StateManager
from scripts.deployment_soak import AGENTS, ROOT, RUN, atomic_json, child_env, compose


class TransientProposalRejectionError(RuntimeError):
    """Confirmed pre-execution rejection while portfolio evidence refreshes."""


class Workload:
    def __init__(self, hours: float, token: str) -> None:
        self.hours = hours
        self.state = StateManager()
        self.ledger: Ledger | None = None
        self.producer = AlghrestProducer()
        self.children: dict[str, subprocess.Popen] = {}
        self.latencies: list[float] = []
        self.stop = asyncio.Event()
        self.info = {
            "pid": os.getpid(),
            "token": token,
            "phase": "starting",
            "errors": [],
            "started_at": datetime.now(UTC).isoformat(),
            "hours": hours,
            "cycles": 0,
            "fault_checks": [],
            "book_id": settings.accounting_book_id,
        }
        self.mark_task: asyncio.Task | None = None

    def save(self) -> None:
        self.info["updated_at"] = datetime.now(UTC).isoformat()
        self.info["children"] = {name: process.pid for name, process in self.children.items()}
        atomic_json(RUN / "status.json", self.info)

    async def infrastructure(self, *args: str) -> None:
        result = await asyncio.to_thread(compose, *args, timeout=240)
        if result.returncode:
            # Compose progress contains names/errors, not environment dumps.
            (RUN / "compose-error.log").write_text(result.stderr[-12000:])
            raise RuntimeError("Isolated Compose operation failed; see compose-error.log")

    def launch(self, name: str) -> None:
        if name == "API":
            command = [
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "28000",
                "--log-level",
                "warning",
            ]
        else:
            module, cls, _ = next(a for a in AGENTS if a[1] == name)
            command = [sys.executable, str(ROOT / "run_agent.py"), module, cls]
        with (RUN / f"{name}.log").open("ab", buffering=0) as log:
            self.children[name] = subprocess.Popen(
                command, cwd=RUN, env=child_env(), stdout=log, stderr=subprocess.STDOUT
            )

    async def stop_agents(self, names: list[str] | None = None, crash: bool = False) -> None:
        for name in names or list(self.children):
            process = self.children.pop(name)
            if process.poll() is None:
                process.send_signal(signal.SIGKILL if crash else signal.SIGINT)
            try:
                await asyncio.to_thread(process.wait, timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                await asyncio.to_thread(process.wait, timeout=5)

    def healthy_processes(self) -> None:
        failed = [
            f"{name} (exit {proc.returncode})"
            for name, proc in self.children.items()
            if proc.poll() is not None
        ]
        if failed:
            raise RuntimeError("Exited process: " + ", ".join(failed))
        if psutil.virtual_memory().available < 512 * 1024**2:
            raise RuntimeError("Host memory headroom below 512 MiB; soak stopped")

    async def marks(self) -> None:
        while not self.stop.is_set():
            now = datetime.now(UTC)
            try:
                for symbol, price in (("SOL/USDT", "100"), ("USDT/USD", "1")):
                    await self.state.set_accounting_mark(
                        "binance", symbol, price, now.isoformat(), int(now.timestamp() * 1000)
                    )
            except Exception:
                pass  # Outage drill: missing marks fail closed until Redis returns.
            await asyncio.sleep(2)

    async def ready(self, seconds: float = 90) -> None:
        async with asyncio.timeout(seconds):
            while True:
                self.healthy_processes()
                if await self.state.trading_ready():
                    return
                await asyncio.sleep(0.5)

    async def assert_book(self) -> int:
        assert self.ledger is not None
        book = await self.ledger.load()
        orders = await self.ledger.pool.fetchval(
            "SELECT count(*) FROM execution.paper_orders WHERE book_id=$1", self.ledger.book_id
        )
        fills = await self.ledger.pool.fetchval(
            "SELECT count(*) FROM accounting.fills WHERE book_id=$1", self.ledger.book_id
        )
        if orders != book.revision or fills != book.revision:
            raise AssertionError("Fill/order/revision counts diverged")
        held = Decimal("0.05") if book.revision % 2 else Decimal(0)
        cash = book.cash[key("binance", "default", "USDT")].amount
        expected = Decimal(150) - held * 100 - Decimal("0.005") * book.revision
        if cash != expected or (sum(p.quantity for p in book.positions.values()) != held):
            raise AssertionError("Synthetic cash or position conservation failed")
        self.info.update(revision=book.revision, cash_usdt=str(cash), position_sol=str(held))
        return book.revision

    async def trade(self) -> None:
        for attempt in range(3):
            try:
                await self._trade_once()
                return
            except TransientProposalRejectionError as exc:
                self.info.setdefault("transient_rejections", []).append(
                    {
                        "proposal_id": self.info["active_proposal_id"],
                        "reason": str(exc),
                        "at": datetime.now(UTC).isoformat(),
                    }
                )
                self.save()
                if attempt == 2 or self.stop.is_set():
                    raise
                # Only explicit, pre-execution transient rejections are retried.
                # Every new proposal traverses all risk gates again.
                await asyncio.sleep(5)

    async def wait_for_fill(self, proposal: TradeProposal, revision: int) -> None:
        assert self.ledger is not None
        self.info["operation"] = "await_fill"
        try:
            async with asyncio.timeout(60):
                while True:
                    current = (await self.ledger.load()).revision
                    if current == revision + 1:
                        return
                    if current != revision:
                        raise AssertionError("Unexpected ledger revision while awaiting fill")
                    self.healthy_processes()
                    raw = await self.state.get_json(f"proposal_review:{proposal.proposal_id}")
                    if raw:
                        review = TradeProposalReview.model_validate(raw)
                        if (
                            review.proposal_id != proposal.proposal_id
                            or review.reviewer_agent_id != 3
                        ):
                            raise RuntimeError("Proposal review identity mismatch")
                        if review.decision == TradeProposalStatus.REJECTED:
                            orders = await self.ledger.pool.fetchval(
                                "SELECT count(*) FROM execution.orders WHERE book_id=$1 "
                                "AND request->>'proposal_id'=$2",
                                self.ledger.book_id,
                                str(proposal.proposal_id),
                            )
                            if orders:
                                raise RuntimeError(
                                    "Rejected proposal has execution records; no retry"
                                )
                            if review.reason in {
                                "no portfolio snapshot available",
                                "portfolio exchange reconciliation is unavailable or disagrees",
                            }:
                                raise TransientProposalRejectionError(review.reason)
                            raise RuntimeError(f"Proposal rejected: {review.reason}")
                    await asyncio.sleep(0.1)
        except TimeoutError as exc:
            raise TimeoutError(
                f"No confirmed fill within 60s for proposal {proposal.proposal_id}; "
                f"expected ledger revision {revision + 1}. No automatic retry."
            ) from exc

    async def _trade_once(self) -> None:
        assert self.ledger is not None
        self.info["active_proposal_id"] = None
        self.info["operation"] = "await_trading_ready"
        await self.ready()
        revision = await self.assert_book()
        proposal = TradeProposal(
            symbol="SOL/USDT",
            exchange=Exchange.BINANCE,
            asset_class="CRYPTO",
            side=OrderSide.BUY if revision % 2 == 0 else OrderSide.SELL,
            order_type=OrderType.LIMIT,
            size=Decimal("0.05"),
            size_usd=Decimal(5),
            limit_price=Decimal(100),
            stop_loss=Decimal(99),
            confidence_score=0.9,
            strategy_id="isolated-soak",
            agent_id=12,
        )
        self.info["active_proposal_id"] = str(proposal.proposal_id)
        self.info["operation"] = "publish_proposal"
        self.save()
        tick = time.monotonic()
        await self.producer.send(
            KafkaTopic.PROPOSALS_BUS,
            AgentMessage(
                source_agent_id=12,
                topic=KafkaTopic.PROPOSALS_BUS,
                message_type="TradeProposal",
                payload=proposal.model_dump(mode="json"),
            ),
        )
        await self.wait_for_fill(proposal, revision)
        self.info["operation"] = "await_post_fill_reconciliation"
        await self.ready()
        await self.assert_book()
        self.latencies.append((time.monotonic() - tick) * 1000)
        self.info["operation"] = "idle"

    async def api_checks(self) -> None:
        headers = {"Authorization": "Bearer " + settings.api_access_token.get_secret_value()}
        async with httpx.AsyncClient(timeout=10) as client:
            async with asyncio.timeout(60):
                while True:
                    try:
                        if (
                            await client.get("http://127.0.0.1:28000/health/live")
                        ).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    await asyncio.sleep(1)
            assert (await client.get("http://127.0.0.1:28000/api/v1/portfolio")).status_code == 401
            assert (
                await client.get("http://127.0.0.1:28000/api/v1/portfolio", headers=headers)
            ).status_code == 200
            async with connect(
                "ws://127.0.0.1:28000/ws/dashboard",
                subprotocols=[
                    "alghrest.v1",
                    "auth." + settings.api_access_token.get_secret_value(),
                ],
                open_timeout=10,
            ) as ws:
                assert ws.subprotocol == "alghrest.v1"
                async with asyncio.timeout(15):
                    json.loads(await ws.recv())
            async with asyncio.timeout(60):
                while True:
                    result = (await client.get("http://127.0.0.1:29090/api/v1/targets")).json()
                    targets = result["data"]["activeTargets"]
                    if len(targets) == 7 and all(t["health"] == "up" for t in targets):
                        break
                    await asyncio.sleep(2)
        self.info["api_and_monitoring"] = "authenticated HTTP + WS; all 7 scrape targets up"

    async def kafka_check(self) -> None:
        admin = AIOKafkaAdminClient(
            bootstrap_servers=settings.kafka_servers_list, **aiokafka_security()
        )
        try:
            await admin.start()
            async with asyncio.timeout(60):
                while True:
                    topics = await admin.describe_topics(
                        [KafkaTopic.FILLS_CONFIRMED.value, KafkaTopic.PROPOSALS_BUS.value]
                    )
                    if all(
                        len(p["replicas"]) == 3 and len(p["isr"]) == 3
                        for topic in topics
                        for p in topic["partitions"]
                    ):
                        break
                    await asyncio.sleep(1)
            if not self.info.get("negative_auth"):
                for server in settings.kafka_servers_list:
                    for auth in ({}, {**aiokafka_security(), "sasl_plain_password": "wrong"}):
                        bad = AIOKafkaAdminClient(
                            bootstrap_servers=server, request_timeout_ms=2000, **auth
                        )
                        try:
                            async with asyncio.timeout(5):
                                try:
                                    await bad.start()
                                except (KafkaConnectionError, SaslAuthenticationFailed):
                                    continue
                                raise AssertionError("Kafka accepted an unauthorized client")
                        finally:
                            await bad.close()
                try:
                    connection = await asyncpg.connect(
                        "postgresql://alghrest:alghrest_secure_pass_2024@127.0.0.1:25432/alghrest",
                        timeout=5,
                    )
                except asyncpg.InvalidPasswordError:
                    pass
                else:
                    await connection.close()
                    raise AssertionError("Database accepted the old default password")
                self.info["negative_auth"] = (
                    "all 3 Kafka listeners reject anonymous/wrong keys; PostgreSQL rejects old default"
                )
            self.info["kafka_replication"] = "3 replicas, all in sync"
        finally:
            await admin.close()

    async def lag(self) -> dict[str, int]:
        admin = AIOKafkaAdminClient(
            bootstrap_servers=settings.kafka_servers_list, **aiokafka_security()
        )
        reader = AIOKafkaConsumer(
            bootstrap_servers=settings.kafka_servers_list, **aiokafka_security()
        )
        result = {}
        try:
            await admin.start()
            await reader.start()
            for group, _ in await admin.list_consumer_groups():
                offsets = await admin.list_consumer_group_offsets(group)
                if offsets:
                    ends = await reader.end_offsets(list(offsets))
                    result[group] = sum(
                        max(0, ends[part] - value.offset)
                        for part, value in offsets.items()
                        if value.offset >= 0
                    )
        finally:
            await admin.close()
            await reader.stop()
        return result

    async def sample(self) -> None:
        previous = self.info.get("last_sample")
        if (
            previous
            and (datetime.now(UTC) - datetime.fromisoformat(previous["at"])).total_seconds() > 300
        ):
            raise RuntimeError(
                "Measurement gap exceeded 5 minutes; continuous soak is not validated"
            )
        self.healthy_processes()
        memory = []
        for name, process in self.children.items():
            proc = psutil.Process(process.pid)
            memory.append(
                {
                    "name": name,
                    "rss_bytes": proc.memory_info().rss,
                    "cpu_seconds": sum(proc.cpu_times()[:2]),
                }
            )
        ids = (await asyncio.to_thread(compose, "ps", "-q")).stdout.split()
        if not ids:
            raise RuntimeError("No isolated containers available for measurement")
        stats = await asyncio.to_thread(
            subprocess.run,
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", *ids],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        record = {
            "at": datetime.now(UTC).isoformat(),
            "lag": await self.lag(),
            "processes": memory,
            "containers": [json.loads(line) for line in stats.stdout.splitlines()],
            "host_available_bytes": psutil.virtual_memory().available,
            "revision": self.info.get("revision"),
            "trade_latency_ms": self.latencies[-1] if self.latencies else None,
        }
        with (RUN / "samples.jsonl").open("a") as stream:
            stream.write(json.dumps(record) + "\n")
        self.info["last_sample"] = record
        if max(record["lag"].values(), default=0) > 100:
            raise RuntimeError("Consumer lag exceeded 100 messages after settled cycle")
        self.save()

    async def drills(self) -> None:
        assert self.ledger is not None
        self.info["phase"] = "recovery_drills"
        self.save()
        baseline = await self.assert_book()
        await self.trade()
        # Restart the accountant and replay already committed fills.
        await self.stop_agents(["PortfolioAccountant"], crash=True)
        raw = await self.ledger.pool.fetchval(
            "SELECT payload FROM accounting.fills WHERE book_id=$1 LIMIT 1", self.ledger.book_id
        )
        payload = json.loads(raw) if isinstance(raw, str) else raw
        for _ in range(20):
            await self.producer.send(
                KafkaTopic.FILLS_CONFIRMED,
                AgentMessage(
                    source_agent_id=26,
                    topic=KafkaTopic.FILLS_CONFIRMED,
                    message_type="Fill",
                    payload=payload,
                ),
            )
        await self.state.invalidate_portfolio()
        self.launch("PortfolioAccountant")
        await self.ready()
        assert await self.assert_book() == baseline + 1
        self.info["fault_checks"].append(
            "accountant SIGKILL + 20 duplicate fills: no double accounting"
        )
        self.save()
        # Continue producing with one of three replicated brokers down.
        await self.infrastructure("stop", "kafka-1")
        try:
            await self.trade()
        finally:
            await self.infrastructure("up", "-d", "--no-deps", "--wait", "kafka-1")
        self.info["fault_checks"].append("order executed during single broker outage")
        self.save()
        await self.kafka_check()
        # Stop agents before the DB/cache restart; reopen every pool/writer afterwards.
        await self.stop_agents()
        await self.ledger.close()
        await self.infrastructure("restart", "timescaledb", "redis")
        await self.infrastructure("up", "-d", "--wait", "timescaledb", "redis")
        self.ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        await self.state.invalidate_portfolio()
        assert not await self.state.trading_ready()
        for _, cls, _ in AGENTS:
            self.launch(cls)
        self.launch("API")
        await self.ready()
        assert await self.assert_book() == baseline + 2
        await self.trade()
        await self.trade()
        self.info["fault_checks"].append(
            "DB + Redis + all agent/API restart: preserved book, blocked before reconciliation, recovered"
        )
        await self.api_checks()
        self.save()

    async def execute(self) -> None:
        if (
            settings.environment != "paper_trading"
            or not settings.accounting_book.startswith("soak-")
            or "127.0.0.1:25432/alghrest" not in settings.database_url
            or settings.redis_url != "redis://127.0.0.1:26379"
            or settings.kafka_servers_list
            != ["127.0.0.1:29092", "127.0.0.1:29093", "127.0.0.1:29094"]
        ):
            raise RuntimeError("Refusing non-isolated settings")
        if any(
            (
                settings.anthropic_api_key,
                settings.telegram_bot_token,
                settings.binance_api_key,
                settings.binance_secret,
            )
        ):
            raise RuntimeError("External account credentials must be absent")
        self.save()
        # ZooKeeper persists sessions across restarts. Allow stale ephemeral broker
        # registrations to expire before starting brokers with the same IDs.
        await self.infrastructure("up", "-d", "--wait", "zookeeper")
        with suppress(TimeoutError):
            await asyncio.wait_for(self.stop.wait(), timeout=45)
        if self.stop.is_set():
            self.info["phase"] = "stopped"
            return
        await self.infrastructure("up", "-d", "--wait", "--wait-timeout", "180")
        await self.infrastructure("wait", "kafka-init")
        self.ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
        # First run only. Resuming a completed experiment requires a new explicit manifest.
        exists = await self.ledger.pool.fetchval(
            "SELECT EXISTS(SELECT 1 FROM accounting.books WHERE book_id=$1)", self.ledger.book_id
        )
        if not exists:
            await self.ledger.open_book(
                OpeningBalances(
                    as_of=datetime.now(UTC) - timedelta(minutes=1),
                    reference="explicit synthetic isolated 24h deployment test",
                    cash=[
                        CashBalance(exchange=Exchange.BINANCE, currency="USDT", amount=Decimal(150))
                    ],
                )
            )
        await self.state.initialize()
        self.mark_task = asyncio.create_task(self.marks())
        for _, cls, _ in AGENTS:
            self.launch(cls)
        self.launch("API")
        await self.producer.initialize()
        await self.ready()
        await self.kafka_check()
        await self.api_checks()
        if (await self.assert_book()) % 2:
            await self.trade()  # Resume an interrupted synthetic book without reseeding.
        await self.drills()
        self.info["phase"] = "soaking"
        self.info["soak_started_at"] = datetime.now(UTC).isoformat()
        self.info["deadline_at"] = (datetime.now(UTC) + timedelta(hours=self.hours)).isoformat()
        self.save()
        deadline = time.monotonic() + self.hours * 3600
        while time.monotonic() < deadline and not self.stop.is_set():
            await self.trade()
            await self.trade()  # finish each cycle flat
            self.info["cycles"] += 1
            await self.sample()
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self.stop.wait(), timeout=min(120, max(0.01, deadline - time.monotonic()))
                )
        if not self.stop.is_set():
            await self.assert_book()
            await self.sample()  # Validate continuity through the end of the window.
        self.info["phase"] = "stopped" if self.stop.is_set() else "completed"
        self.info["latency_p50_ms"] = statistics.median(self.latencies)
        self.info["latency_p95_ms"] = sorted(self.latencies)[int(0.95 * (len(self.latencies) - 1))]

    async def cleanup(self) -> None:
        self.stop.set()
        if self.mark_task:
            self.mark_task.cancel()
            await asyncio.gather(self.mark_task, return_exceptions=True)
        await self.stop_agents()
        await self.producer.shutdown()
        await self.state.shutdown()
        if self.ledger:
            await self.ledger.close()
        # Keep ZooKeeper available while brokers close their sessions.
        await asyncio.to_thread(compose, "stop", "kafka-1", "kafka-2", "kafka-3")
        await asyncio.to_thread(compose, "stop")
        self.info["finished_at"] = datetime.now(UTC).isoformat()
        self.save()


async def run(hours: float, token: str) -> None:
    worker = Workload(hours, token)
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, worker.stop.set)
    try:
        await worker.execute()
    except Exception as exc:
        worker.info["phase"] = "failed"
        worker.info["errors"].append(
            {
                "type": type(exc).__name__,
                "message": str(exc)[:400],
                "operation": worker.info.get("operation", worker.info["phase"]),
                "proposal_id": worker.info.get("active_proposal_id"),
            }
        )
    finally:
        await worker.cleanup()
