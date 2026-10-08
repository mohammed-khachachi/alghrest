"""Read-only host-process and cold-import measurements; never starts trading services."""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[1]
IMPORTS = (
    "agents.base_agent",
    "agents.tier5_execution.order_router",
    "agents.tier5_execution.exchange_executor",
    "api.advisor",
)
PROBE = """
import importlib, json, sys, time, psutil
p = psutil.Process()
before = p.memory_full_info()
start = time.perf_counter()
importlib.import_module(sys.argv[1])
elapsed = time.perf_counter() - start
after = p.memory_full_info()
print(json.dumps({"seconds": elapsed, "rss_bytes": after.rss,
    "uss_bytes": getattr(after, "uss", None),
    "added_uss_bytes": getattr(after, "uss", 0) - getattr(before, "uss", 0),
    "pandas_loaded": "pandas" in sys.modules}))
"""


def host_sample() -> dict:
    """Only record identities/usage, never full command lines or environment secrets."""
    rows = []
    for proc in psutil.process_iter():
        try:
            if Path(proc.cwd()).resolve() != ROOT or proc.pid == psutil.Process().pid:
                continue
            args = proc.cmdline()
            name = next(
                (arg for arg in args if arg.startswith(("agents.", "api.", "ml.inference"))),
                "",
            )
            if not name:
                continue
            memory = proc.memory_full_info()
            cpu = proc.cpu_times()
            rows.append(
                {
                    "pid": proc.pid,
                    "created": proc.create_time(),
                    "module": name,
                    "rss_bytes": memory.rss,
                    "uss_bytes": getattr(memory, "uss", None),
                    "cpu_seconds": cpu.user + cpu.system,
                }
            )
        except (psutil.Error, OSError):
            continue
    return {"monotonic_seconds": time.monotonic(), "processes": rows}


def measure_imports(repeats: int) -> dict:
    results = {}
    for module in IMPORTS:
        samples = []
        for _ in range(repeats):
            result = subprocess.run(
                [sys.executable, "-c", PROBE, module],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=90,
                check=True,
            )
            samples.append(json.loads(result.stdout.splitlines()[-1]))
        results[module] = {
            "samples": samples,
            "median_seconds": statistics.median(s["seconds"] for s in samples),
            "median_uss_bytes": (
                statistics.median(s["uss_bytes"] for s in samples)
                if all(s["uss_bytes"] is not None for s in samples)
                else None
            ),
        }
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--imports", action="store_true")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not (1 <= args.samples <= 3600 and 0 < args.interval <= 60 and 1 <= args.repeats <= 10):
        parser.error("samples 1..3600, interval (0, 60], repeats 1..10 required")
    samples = []
    for i in range(args.samples):
        if i:
            time.sleep(args.interval)
        samples.append(host_sample())
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "python": sys.version.split()[0],
        "scope": "Matching host Python processes only; containers and other hosts excluded.",
        "runtime_observed": any(s["processes"] for s in samples),
        "host_samples": samples,
        "imports": measure_imports(args.repeats) if args.imports else {},
        "limitations": [
            "RSS includes shared pages; summed RSS is not physical memory savings.",
            "Cold-import timings include OS cache/noise; compare repeated runs on the same host.",
            "No matching process means unavailable runtime baseline, not zero system usage.",
            "Import costs do not measure trading latency, Kafka lag or LLM billing.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "runtime_observed": report["runtime_observed"]}))


if __name__ == "__main__":
    main()
