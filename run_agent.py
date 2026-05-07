"""
ALGHREST — Universal Agent Runner
Usage:
    python run_agent.py <agent_module_path>
Example:
    python run_agent.py agents.tier1_executive.cio_agent CIOAgent
    python run_agent.py agents.tier2_intelligence.market_data_hub MarketDataHub
"""
from __future__ import annotations

import asyncio
import importlib
import sys


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python run_agent.py <module_path> <ClassName>")
        print("Example: python run_agent.py agents.tier1_executive.cio_agent CIOAgent")
        sys.exit(1)

    module_path = sys.argv[1]
    class_name = sys.argv[2]

    module = importlib.import_module(module_path)
    agent_class = getattr(module, class_name)
    agent = agent_class()

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print(f"\n{class_name} stopped.")


if __name__ == "__main__":
    main()
