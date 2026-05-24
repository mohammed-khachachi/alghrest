"""
main.py - HMM Trading Pipeline Entry Point
Usage: python main.py
       python main.py --config configs/default.json
"""

import argparse
from pathlib import Path

from src.core.config import load_config, validate_config
from src.pipeline.runner import run


def main():
    parser = argparse.ArgumentParser(description="HMM Market Regime Detection")
    parser.add_argument(
        "--config",
        default="configs/default.json",
        help="Path to config JSON file",
    )
    args = parser.parse_args()
    config = load_config(args.config)
    validate_config(config)
    result = run(config)
    print(f"\n[DONE] Pipeline status: {result['status']}")
    print(f"[DONE] Regimes detected: {result['n_states']}")


if __name__ == "__main__":
    main()
