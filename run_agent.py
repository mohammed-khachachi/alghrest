"""
ALGHREST — Universal Agent Runner
Usage:
    python run_agent.py <agent_module_path> <ClassName>
Example:
    python run_agent.py agents.tier1_executive.cio_agent CIOAgent
    python run_agent.py agents.tier2_intelligence.market_data_hub MarketDataHub
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_VENV_PYTHON = _ROOT / ".venv" / "bin" / "python"
if (
    __name__ == "__main__"
    and sys.prefix == sys.base_prefix
    and _VENV_PYTHON.is_file()
    and os.environ.get("_ALGHREST_VENV_BOOTSTRAPPED") != "1"
):
    os.environ["_ALGHREST_VENV_BOOTSTRAPPED"] = "1"
    os.execv(str(_VENV_PYTHON), [str(_VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])

from core.config import settings  # noqa: E402


def main() -> None:
    if len(sys.argv) < 3:
        print("Usage: python run_agent.py <module_path> <ClassName>")
        print("Example: python run_agent.py agents.tier1_executive.cio_agent CIOAgent")
        sys.exit(1)

    module_path = sys.argv[1]
    class_name = sys.argv[2]

    settings.require_order_execution()
    module = importlib.import_module(module_path)
    agent_class = getattr(module, class_name)
    agent = agent_class()

    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        print(f"\n{class_name} stopped.")


if __name__ == "__main__":
    main()
