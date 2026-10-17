"""Continuous, bounded research observation; no service restart or journal writes."""

import argparse
import asyncio
import hashlib
import json
import os
import signal
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from pydantic import TypeAdapter

from core.advisory.models import utcnow
from core.advisory.openterminal_research import TerminalResearch, TerminalSymbol, valid_symbol
from core.advisory.research_freshness import quote_freshness
from core.config import settings

ROOT = Path(__file__).resolve().parents[1]
MAX_LOG_BYTES = 128 * 1024 * 1024


def source_manifest() -> dict[str, str]:
    files = [Path(__file__).resolve()]
    for base in (
        "src/core/advisory",
        "src/connectors/advisory",
        "src/api",
        "dashboard/src",
        "vendor/openterminal/server/src",
    ):
        files.extend(p for p in (ROOT / base).rglob("*") if p.suffix in {".py", ".ts", ".tsx"})
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write("\n")
    os.replace(temporary, path)


def append_json(path: Path, value: dict[str, Any]) -> None:
    raw = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_LOG_BYTES or (
        path.exists() and path.stat().st_size + len(raw) > MAX_LOG_BYTES
    ):
        raise RuntimeError("Evidence file reached its size bound; no records were removed")
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "ab") as out:
        out.write(raw)


def sample_gap(previous: datetime | None, now: datetime) -> float:
    gap = (now - previous).total_seconds() if previous else 0.0
    if not 0 <= gap <= 300:
        raise RuntimeError("Observation clock moved backwards or sample gap exceeded five minutes")
    return gap


def reading(report: TerminalResearch, now: datetime, latency: float) -> dict[str, Any]:
    if not 0 <= (now - report.assessed_at).total_seconds() < 90:
        raise RuntimeError("Research response assessment clock is invalid")
    q, a = report.quote, report.analysis
    observation = q.observation if q else None
    fresh_state = bool(
        observation
        and observation.market_state_basis == "provider"
        and observation.cache_state != "stale"
        and 0 <= (now - observation.fetched_at).total_seconds() < 90
    )
    context = quote_freshness(report, now)
    return {
        "symbol": report.symbol,
        "assessed_at": report.assessed_at.isoformat(),
        "latency_seconds": latency,
        "sources": {s.kind: s.state for s in report.sources},
        "source_hashes": {s.kind: s.response_sha256 for s in report.sources},
        "quote": q.model_dump(mode="json") if q else None,
        "analysis": a.model_dump(mode="json") if a else None,
        "quality": report.data_quality.status if report.data_quality else "unassessed",
        "quote_context": context,
        "current_provider_session": context["session"] if fresh_state else "unknown",
        "provider_session_recent": fresh_state,
        "freshness_certified": False,
        "execution_enabled": False,
    }


async def health(client: httpx.AsyncClient, token: str) -> None:
    urls = {
        "assistant": "http://127.0.0.1:8011/assistant-api/health",
        "dashboard": "http://127.0.0.1:5173/research",
        "terminal_web": "http://127.0.0.1:3001/",
        "terminal_api": "http://127.0.0.1:4001/api/status",
    }

    async def check(name: str, url: str) -> None:
        response = await client.get(
            url,
            headers=(
                {"Authorization": "Bearer " + token}
                if name == "assistant"
                else {"Authorization": ""}
            ),
        )
        if response.status_code != 200:
            raise RuntimeError(f"Service unavailable: {name}")
        if name in {"assistant", "terminal_api"}:
            body = response.json()
            if body.get("execution_enabled") is not False:
                raise RuntimeError("Execution boundary changed")
            if name == "assistant" and (
                body.get("service") != "manual-research"
                or body.get("agent_tap_enabled") is not False
            ):
                raise RuntimeError("Assistant identity or agent boundary changed")
            if name == "terminal_api" and (
                body.get("integration") != "alghrest-research" or body.get("ai") is not False
            ):
                raise RuntimeError("Terminal identity or AI boundary changed")

    await asyncio.gather(*(check(name, url) for name, url in urls.items()))


async def run(hours: float, interval: float, symbols: list[str], output: Path) -> None:
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    original = source_manifest()
    write_json(output / "source-manifest.json", original)
    started, monotonic = utcnow(), time.monotonic()
    state: dict[str, Any] = {
        "schema": "continuous-research-observation-v1",
        "status": "starting",
        "pid": os.getpid(),
        "started_at": started.isoformat(),
        "planned_end_at": (started + timedelta(hours=hours)).isoformat(),
        "requested_hours": hours,
        "interval_seconds": interval,
        "symbols": symbols,
        "cycles": 0,
        "last_sample_at": None,
        "max_sample_gap_seconds": 0.0,
        "failure": None,
        "source_states": {},
        "reported_sessions": {},
        "latest": {},
        "limits": [
            "Only continuous recorded samples count; no unobserved uptime is inferred",
            "Missing feeds and provider sessions are reported without an exchange calendar",
            "No operator journal writes, service restarts, broker actions or execution",
            "Computer sleep, lost process, source changes or gaps above five minutes invalidate the run",
        ],
    }
    write_json(output / "status.json", state)
    stop = False

    def interrupt(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    previous = None
    counts: Counter[str] = Counter()
    sessions: Counter[str] = Counter()
    token = settings.advisory_access_token.get_secret_value()
    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
            due, deadline = monotonic, monotonic + hours * 3600
            guard = asyncio.Semaphore(2)
            while True:
                while time.monotonic() < due and not stop:
                    await asyncio.sleep(min(1, due - time.monotonic()))
                if stop:
                    raise RuntimeError("Observation interrupted; services were not restarted")
                at = utcnow()
                gap = sample_gap(previous, at)
                if source_manifest() != original:
                    raise RuntimeError(
                        "Application source changed; retain evidence and review before a new run"
                    )
                await health(client, token)

                async def collect(symbol: str) -> dict[str, Any]:
                    async with guard:
                        begin = time.monotonic()
                        response = await client.get(
                            f"http://127.0.0.1:8011/assistant-api/openterminal-research/{symbol}",
                            headers={"Authorization": "Bearer " + token},
                        )
                        if response.status_code != 200:
                            raise RuntimeError(f"Research response failed: {symbol}")
                        report = TerminalResearch.model_validate(response.json())
                        if report.symbol != symbol:
                            raise RuntimeError("Research symbol identity mismatch")
                        return reading(report, utcnow(), time.monotonic() - begin)

                values = await asyncio.gather(*(collect(symbol) for symbol in symbols))
                if source_manifest() != original:
                    raise RuntimeError("Application source changed while collecting a sample")
                if stop:
                    raise RuntimeError("Observation interrupted; services were not restarted")
                for value in values:
                    symbol = value["symbol"]
                    for kind, status in value["sources"].items():
                        counts[f"{symbol}:{kind}:{status}"] += 1
                    sessions[f"{symbol}:{value['current_provider_session']}"] += 1
                    prior = state["latest"].get(symbol)
                    if prior:
                        for field in ("sources", "quality", "current_provider_session"):
                            if prior[field] != value[field]:
                                append_json(
                                    output / "events.jsonl",
                                    {
                                        "at": at.isoformat(),
                                        "symbol": symbol,
                                        "field": field,
                                        "before": prior[field],
                                        "after": value[field],
                                    },
                                )
                    state["latest"][symbol] = value
                state["cycles"] += 1
                append_json(
                    output / "samples.jsonl",
                    {
                        "cycle": state["cycles"],
                        "sample_started_at": at.isoformat(),
                        "readings": values,
                    },
                )
                previous = at
                state.update(
                    status="running",
                    last_sample_at=at.isoformat(),
                    max_sample_gap_seconds=max(state["max_sample_gap_seconds"], gap),
                    observed_seconds=time.monotonic() - monotonic,
                    source_states=dict(counts),
                    reported_sessions=dict(sessions),
                )
                write_json(output / "status.json", state)
                if time.monotonic() >= deadline:
                    state["status"] = "passed"
                    break
                due = min(max(due + interval, time.monotonic()), deadline)
    except Exception as exc:
        state.update(
            status="failed",
            failure=str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__,
        )
    finally:
        state.update(
            finished_at=utcnow().isoformat(), observed_seconds=time.monotonic() - monotonic
        )
        write_json(output / "status.json", state)
        write_json(output / "verification.json", state)
    if state["status"] != "passed":
        raise SystemExit("Research monitoring failed; preserved evidence; no automatic restart")
    print(
        "Research monitoring completed; inspect the recorded interval and explicit source limitations."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=120)
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "BTC", "^VIX"])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 0.001 <= args.hours <= 168 or not 1 <= args.interval_seconds <= 240:
        parser.error("Choose a duration up to seven days and an interval of 1-240 seconds")
    if not 1 <= len(args.symbols) <= 6 or len(set(args.symbols)) != len(args.symbols):
        parser.error("Choose 1-6 distinct terminal symbols")
    symbols = [valid_symbol(TypeAdapter(TerminalSymbol).validate_python(s)) for s in args.symbols]
    asyncio.run(run(args.hours, args.interval_seconds, symbols, args.output))


if __name__ == "__main__":
    main()
