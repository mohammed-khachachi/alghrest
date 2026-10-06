"""Explicit deployment modes. Plan is read-only; start/stop are operator actions.

python -m scripts.runtime research|paper|full plan|start|stop|status
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = {
    "research": "docker-compose.advisor.yml",
    "paper": "docker-compose.paper.yml",
    "full": "docker-compose.yml",
}


def contains_live_services(config: dict) -> bool:
    return any(
        key.lower() == "environment" and value == "live"
        for service in config.get("services", {}).values()
        for key, value in service.get("environment", {}).items()
    )


def commands(mode: str, action: str) -> list[list[str]]:
    compose = ["docker", "compose", "-f", COMPOSE[mode]]
    supervisor = [sys.executable, "-m", "scripts.paper_services"]
    if action == "start":
        steps = [[*compose, "up", "-d", "--wait", "--wait-timeout", "180"]]
        if mode == "paper":
            steps.extend(
                [
                    [sys.executable, "-m", "scripts.paper", "provision"],
                    [*supervisor, "start"],
                ]
            )
        return steps
    if action == "stop":
        steps = [[*supervisor, "stop"]] if mode == "paper" else []
        steps.append([*compose, "stop"])
        return steps
    steps = [[*compose, "ps"]]
    if mode == "paper":
        steps.append([*supervisor, "status"])
    return steps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=COMPOSE)
    parser.add_argument(
        "action", choices=["plan", "start", "stop", "status"], default="plan", nargs="?"
    )
    args = parser.parse_args()
    if args.action == "plan":
        print(
            json.dumps(
                {
                    "mode": args.mode,
                    "compose": COMPOSE[args.mode],
                    "start": commands(args.mode, "start"),
                    "stop": commands(args.mode, "stop"),
                    "status": commands(args.mode, "status"),
                    "opening_balances": (
                        "Not used by research mode."
                        if args.mode == "research"
                        else "Explicit import required; never seeded by this launcher."
                    ),
                },
                indent=2,
            )
        )
        return 0
    if args.mode in {"paper", "full"} and args.action == "start":
        from core.config import settings

        settings.require_order_execution()
    if args.mode == "paper":
        from scripts.paper_runtime import require_local_paper

        require_local_paper()
        if args.action == "start":
            from core.config import settings

            if not settings.execution_accounts:
                parser.error(
                    "Paper mode requires an explicit execution account scope/opening import"
                )
    elif args.mode == "full" and args.action == "start":
        from core.config import settings

        if settings.is_live:
            parser.error(
                "This convenience launcher supports development/paper only; use the live runbook"
            )
        # env_file can differ from host-shell Settings. Do not print the resolved
        # Compose configuration: its environment may contain credentials.
        config = subprocess.run(
            ["docker", "compose", "-f", COMPOSE[args.mode], "config", "--format", "json"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if config.returncode:
            parser.error("Cannot validate full Compose configuration")
        if contains_live_services(json.loads(config.stdout)):
            parser.error(
                "Full Compose resolves to live services; this launcher refuses live startup"
            )
    for command in commands(args.mode, args.action):
        result = subprocess.run(command, cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
