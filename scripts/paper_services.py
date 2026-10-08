"""Supervise only the configured paper pipeline. No strategy generation or live orders.

python -m scripts.paper_services start|status|stop
"""

import argparse
import asyncio
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from core.accounting.repository import Ledger
from core.config import settings
from core.execution.store import ExecutionStore
from scripts.paper_runtime import require_local_paper

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "artifacts/paper-runtime"
MODULES = [
    ("agents.tier2_intelligence.paper_market_feed", "PaperMarketFeed"),
    ("agents.tier7_monitoring.portfolio_accountant", "PortfolioAccountant"),
    ("agents.tier5_execution.exchange_executor", "ExchangeExecutor"),
    ("agents.tier1_executive.risk_governor", "RiskGovernor"),
    ("agents.tier7_monitoring.portfolio_tracker", "PortfolioTracker"),
    ("agents.tier1_executive.proposal_approver", "ProposalApprover"),
    ("agents.tier5_execution.order_router", "OrderRouter"),
]


def owned() -> dict:
    try:
        value = json.loads((STATE / "supervisor.json").read_text())
        command = Path(f"/proc/{value['pid']}/cmdline").read_bytes().split(b"\0")
        if value["token"].encode() in command and b"scripts.paper_services" in command:
            return value
    except (OSError, ValueError, KeyError):
        pass
    return {}


async def block() -> None:
    ledger = await Ledger.connect(settings.database_url, settings.accounting_book_id)
    try:
        await ExecutionStore(ledger).block("paper supervisor stopped")
    finally:
        await ledger.close()


def supervise(token: str) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    children = []
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with (STATE / "supervisor.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            for module, cls in MODULES:
                with (STATE / f"{cls}.log").open("ab", buffering=0) as log:
                    child = subprocess.Popen(
                        [sys.executable, "run_agent.py", module, cls],
                        cwd=ROOT,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                    children.append(child)
            record = {
                "pid": os.getpid(),
                "token": token,
                "book_id": settings.accounting_book_id,
                "children": {
                    cls: child.pid for (_, cls), child in zip(MODULES, children, strict=True)
                },
            }
            (STATE / "supervisor.json").write_text(json.dumps(record, indent=2))
            while not stopping:
                if any(child.poll() is not None for child in children):
                    raise RuntimeError("A paper service exited; see its log. Pipeline stopped.")
                time.sleep(1)
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.send_signal(signal.SIGINT)
            for child in children:
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            asyncio.run(block())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["start", "run", "status", "stop"])
    parser.add_argument("--token", default="")
    args = parser.parse_args()
    require_local_paper()
    current = owned()
    if args.command == "status":
        print(json.dumps({"running": bool(current), **current}, indent=2))
    elif args.command == "stop":
        if current:
            os.kill(current["pid"], signal.SIGTERM)
            for _ in range(30):
                if not owned():
                    break
                time.sleep(1)
        print(json.dumps({"running": bool(owned())}))
    elif args.command == "run":
        supervise(args.token or uuid4().hex)
    elif current:
        print(json.dumps({"running": True, **current}, indent=2))
    else:
        STATE.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        with (STATE / "supervisor.log").open("ab", buffering=0) as log:
            child = subprocess.Popen(
                [sys.executable, "-m", "scripts.paper_services", "run", "--token", token],
                cwd=ROOT,
                start_new_session=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        for _ in range(10):
            if child.poll() is not None:
                raise RuntimeError(
                    "Paper supervisor failed; inspect artifacts/paper-runtime/supervisor.log"
                )
            if owned():
                print(json.dumps({"running": True, **owned()}, indent=2))
                return
            time.sleep(0.5)
        raise RuntimeError("Paper supervisor did not become ready")


if __name__ == "__main__":
    main()
