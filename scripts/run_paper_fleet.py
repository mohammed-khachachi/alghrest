"""ALGHREST Paper Trading Fleet Supervisor.

Launches and supervises the 8 core paper-trading agents with tier-scoped
Kafka SASL credentials and consumer group prefixes.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "artifacts/live-fleet-logs"

AGENTS = [
    ("agents.tier2_intelligence.paper_market_feed", "PaperMarketFeed", "tier2_intelligence", "KAFKA_TIER2_PASSWORD", "alghrest.tier2"),
    ("agents.tier7_monitoring.portfolio_accountant", "PortfolioAccountant", "tier7_monitoring", "KAFKA_TIER7_PASSWORD", "alghrest.tier7"),
    ("agents.tier5_execution.exchange_executor", "ExchangeExecutor", "tier5_executor", "KAFKA_TIER5_EXECUTOR_PASSWORD", "alghrest.tier5"),
    ("agents.tier1_executive.risk_governor", "RiskGovernor", "tier1_executive", "KAFKA_TIER1_PASSWORD", "alghrest.tier1"),
    ("agents.tier7_monitoring.portfolio_tracker", "PortfolioTracker", "tier7_monitoring", "KAFKA_TIER7_PASSWORD", "alghrest.tier7"),
    ("agents.tier1_executive.proposal_approver", "ProposalApprover", "tier1_executive", "KAFKA_TIER1_PASSWORD", "alghrest.tier1"),
    ("agents.tier5_execution.order_router", "OrderRouter", "tier5_router", "KAFKA_TIER5_ROUTER_PASSWORD", "alghrest.tier5"),
    ("agents.tier5_execution.slippage_minimizer", "SlippageMinimizer", "tier5_router", "KAFKA_TIER5_ROUTER_PASSWORD", "alghrest.tier5"),
]


def main() -> None:
    env_vals = dotenv_values(ROOT / ".env")
    base_env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    procs: list[tuple[str, subprocess.Popen]] = []

    def handle_signal(_sig: int, _frame: object) -> None:
        print("\nShutting down paper fleet gracefully...")
        for name, p in reversed(procs):
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
        time.sleep(2)
        for name, p in procs:
            if p.poll() is None:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    for mod, cls, user, pw_key, grp in AGENTS:
        pw = env_vals.get(pw_key, "")
        agent_env = {
            **base_env,
            "KAFKA_SASL_USERNAME": user,
            "KAFKA_SASL_PASSWORD": pw,
            "KAFKA_CONSUMER_GROUP_PREFIX": grp,
        }
        log_file = (LOG_DIR / f"{cls}.log").open("wb")
        p = subprocess.Popen(
            [sys.executable, "run_agent.py", mod, cls],
            cwd=str(ROOT),
            env=agent_env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        procs.append((cls, p))
        print(f"Started {cls} (pid={p.pid}, user={user}, prefix={grp})")

    try:
        while True:
            time.sleep(5)
            for name, p in procs:
                ret = p.poll()
                if ret is not None:
                    print(f"WARNING: Agent {name} exited with code {ret}")
    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)


if __name__ == "__main__":
    main()
