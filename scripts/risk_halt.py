"""Inspect or explicitly reset the durable halt of a local paper book.

RISK_RESET_TOKEN is supplied through secure process environment, never argv/logs.
Reset also requires the current generation, named operator, and review reason.
"""

import argparse
import asyncio
import json
import os

from core.orchestrator.state_manager import StateManager
from scripts.paper_runtime import require_local_paper


async def operate(args: argparse.Namespace) -> None:
    require_local_paper()
    state = StateManager()
    try:
        await state.initialize()
        store = await (state.global_halt_store() if args.scope == "global" else state.halt_store())
        if args.command == "reset":
            reset = (
                state.deactivate_global_kill_switch
                if args.scope == "global"
                else state.deactivate_kill_switch
            )
            await reset(
                actor=args.actor,
                reason=args.reason,
                authorization=os.environ.get(
                    "RISK_GLOBAL_RESET_TOKEN" if args.scope == "global" else "RISK_RESET_TOKEN", ""
                ),
                expected_generation=args.generation,
            )
        status = await store.status()
        print(json.dumps(status, default=str))
    finally:
        await state.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["status", "reset"])
    parser.add_argument("--scope", choices=["book", "global"], default="book")
    parser.add_argument("--actor", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--generation", type=int, default=-1)
    asyncio.run(operate(parser.parse_args()))


if __name__ == "__main__":
    main()
