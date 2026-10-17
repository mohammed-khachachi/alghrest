"""Bounded read-only HTTP observation with an isolated research journal and exact restore."""

import argparse
import asyncio
import hashlib
import json
import secrets
import shutil
import signal
import tempfile
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

import httpx
from pydantic import TypeAdapter

from api.services.research_pdf import render_research_pdf
from connectors.advisory.research_backup import export_research, restore_research
from connectors.advisory.research_journal import ResearchJournal
from connectors.advisory.storage import AdvisoryStore
from core.advisory.models import utcnow
from core.advisory.openterminal_research import TerminalResearch, TerminalSymbol, valid_symbol
from core.advisory.research_freshness import quote_freshness
from core.advisory.research_journal import ResearchSnapshot
from core.config import settings


async def run(minutes: float, interval: float, symbols: list[str], output: Path) -> None:
    started = utcnow()
    begin = time.monotonic()
    duration = minutes * 60
    output.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]

    def sources() -> dict[str, str]:
        return {
            str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for base in (
                "src/core/advisory",
                "src/connectors/advisory",
                "src/api",
                "dashboard/src",
                "vendor/openterminal/server/src",
            )
            for p in (root / base).rglob("*")
            if p.is_file() and p.suffix in {".py", ".ts", ".tsx"}
        }

    original_sources = sources()
    (output / "source-manifest.json").write_text(json.dumps(original_sources, indent=2) + "\n")
    work = Path(tempfile.mkdtemp(prefix="alghrest-research-soak-"))
    journal = ResearchJournal(AdvisoryStore(str(work / "research.sqlite3")))
    for symbol in symbols:
        journal.watch(symbol, True)
    stop = False

    def interrupt(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    headers = {"Authorization": "Bearer " + settings.advisory_access_token.get_secret_value()}
    cycles = 0
    states: Counter[str] = Counter()
    sessions: Counter[str] = Counter()
    gaps = []
    last = None
    failure = None
    receipt = {
        "schema": "research-observation-v1",
        "started_at": started.isoformat(),
        "requested_seconds": duration,
        "symbols": symbols,
        "interval_seconds": interval,
        "isolation": "Live HTTP reads only; snapshot/PDF/backup operations use a separate disposable journal",
        "status": "running",
    }

    def status() -> None:
        (output / "status.json").write_text(
            json.dumps(
                {
                    **receipt,
                    "cycles": cycles,
                    "elapsed_seconds": time.monotonic() - begin,
                    "last_sample_at": last,
                    "source_states": states,
                    "reported_sessions": sessions,
                    "failure": failure,
                },
                indent=2,
            )
            + "\n"
        )

    try:
        async with httpx.AsyncClient(timeout=30, trust_env=False, headers=headers) as client:
            due = begin
            guard = asyncio.Semaphore(2)
            while True:
                while time.monotonic() < due:
                    if stop:
                        raise RuntimeError("Observation interrupted; no service was restarted")
                    await asyncio.sleep(min(1, due - time.monotonic()))
                if stop:
                    raise RuntimeError("Observation interrupted; no service was restarted")
                sample_start = utcnow()
                if last:
                    gap = (sample_start - datetime.fromisoformat(last)).total_seconds()
                    gaps.append(gap)
                    if gap > 300:
                        raise RuntimeError("Observation sample gap exceeded five minutes")
                checks = {
                    "assistant": "http://127.0.0.1:8011/assistant-api/health",
                    "dashboard": "http://127.0.0.1:5173/research",
                    "terminal_web": "http://127.0.0.1:3001/",
                    "terminal_api": "http://127.0.0.1:4001/api/status",
                }

                async def health(name: str, url: str) -> None:
                    # Never forward the assistant credential to another service.
                    response = await client.get(
                        url, headers=headers if name == "assistant" else {"Authorization": ""}
                    )
                    if response.status_code != 200:
                        raise RuntimeError(f"Service unavailable: {name}")
                    if name in {"assistant", "terminal_api"}:
                        value = response.json()
                        if value.get("execution_enabled") is not False:
                            raise RuntimeError("Execution boundary changed")
                        if name == "assistant" and value.get("agent_tap_enabled") is not False:
                            raise RuntimeError("Agent tap unexpectedly enabled")
                        if name == "terminal_api" and value.get("ai") is not False:
                            raise RuntimeError("Terminal AI unexpectedly enabled")

                await asyncio.gather(*(health(n, u) for n, u in checks.items()))

                async def sample(symbol: str) -> dict[str, object]:
                    async with guard:
                        request_start = time.monotonic()
                        response = await client.get(
                            f"http://127.0.0.1:8011/assistant-api/openterminal-research/{symbol}"
                        )
                        if response.status_code != 200:
                            raise RuntimeError(f"Research response failed: {symbol}")
                        report = TerminalResearch.model_validate(response.json())
                        now = utcnow()
                        if (
                            report.symbol != symbol
                            or not 0 <= (now - report.assessed_at).total_seconds() < 90
                        ):
                            raise RuntimeError("Research identity/clock mismatch")
                        journal.save(
                            ResearchSnapshot(id=secrets.token_hex(16), saved_at=now, report=report)
                        )
                        context = quote_freshness(report)
                        for source in report.sources:
                            states[f"{symbol}:{source.kind}:{source.state}"] += 1
                        sessions[f"{symbol}:{context['session']}"] += 1
                        return {
                            "symbol": symbol,
                            "assessed_at": report.assessed_at.isoformat(),
                            "latency_seconds": time.monotonic() - request_start,
                            "sources": {s.kind: s.state for s in report.sources},
                            "quality": (
                                report.data_quality.status if report.data_quality else "unassessed"
                            ),
                            "quote_context": context,
                            "history_provider": (
                                report.analysis.history_provider if report.analysis else None
                            ),
                            "quote_observed_at": (
                                report.quote.observation.fetched_at.isoformat()
                                if report.quote and report.quote.observation
                                else None
                            ),
                        }

                readings = await asyncio.gather(*(sample(s) for s in symbols))
                if stop:
                    raise RuntimeError("Observation interrupted; no service was restarted")
                cycles += 1
                last = sample_start.isoformat()
                with (output / "samples.jsonl").open("a") as log:
                    log.write(
                        json.dumps(
                            {"cycle": cycles, "sample_started_at": last, "readings": readings}
                        )
                        + "\n"
                    )
                status()
                if time.monotonic() - begin >= duration:
                    break
                due = max(due + interval, time.monotonic())
            raw = export_research(journal, utcnow())
            (output / "isolated-research-backup.json").write_bytes(raw)
            restored = ResearchJournal(AdvisoryStore(str(work / "restored.sqlite3")))
            result = restore_research(restored, raw, utcnow())
            repeat = restore_research(restored, raw, utcnow())
            if repeat["snapshots_added"] != 0:
                raise RuntimeError("Repeated restore was not idempotent")

            def fingerprint(value: ResearchJournal) -> str:
                with value.store.connect() as db:
                    rows = db.execute(
                        "SELECT id,symbol,saved,payload FROM research_snapshots ORDER BY id"
                    ).fetchall()
                return hashlib.sha256(json.dumps(rows).encode()).hexdigest()

            if fingerprint(journal) != fingerprint(restored):
                raise RuntimeError("Restored snapshot bytes changed")
            pdf = render_research_pdf(restored.brief(now=utcnow()))
            if not pdf.startswith(b"%PDF-") or b"/FontFile2" not in pdf:
                raise RuntimeError("Restored PDF export failed")
            (output / "restore-check.json").write_text(
                json.dumps(
                    {
                        **result,
                        "raw_snapshot_sha256": fingerprint(journal),
                        "pdf_bytes": len(pdf),
                        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
                    },
                    indent=2,
                )
                + "\n"
            )
            if sources() != original_sources:
                raise RuntimeError(
                    "Application source changed during observation; rerun the check for the final source"
                )
            if stop:
                raise RuntimeError("Observation interrupted; no service was restarted")
            shutil.rmtree(work)
            receipt["status"] = "passed"
    except Exception as exc:
        # Error classes only: request headers/configuration and private values stay out of evidence.
        failure = str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__
        receipt["status"] = "failed"
    finally:
        receipt.update(
            {
                "finished_at": utcnow().isoformat(),
                "observed_seconds": time.monotonic() - begin,
                "max_sample_gap_seconds": max(gaps, default=0),
                "limits": [
                    "Only the recorded interval and source/session states were observed; no 24-hour or multi-session stability claim",
                    "Feed failures remain explicit; market freshness/event completeness are not certified",
                    "No service restart, broker, execution or user-journal mutation",
                ],
            }
        )
        status()
        (output / "verification.json").write_text((output / "status.json").read_text())
    if failure:
        raise SystemExit("Research observation failed; inspect its saved verification receipt")
    print(
        f"Research observation passed: {cycles} cycles, {time.monotonic()-begin:.1f} seconds; exact restore and PDF passed."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=30)
    parser.add_argument("--interval-seconds", type=float, default=60)
    parser.add_argument("--symbols", nargs="+", default=["AAPL", "MSFT", "BTC", "^VIX"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (
        not 0 < args.minutes <= 90
        or not 1 <= args.interval_seconds <= 300
        or not 1 <= len(args.symbols) <= 6
        or len(set(args.symbols)) != len(args.symbols)
    ):
        parser.error("Invalid bounded duration/interval/symbol count")
    if args.minutes * 60 / args.interval_seconds + 1 > 100:
        parser.error(
            "Choose an interval that stays within the 100-snapshot per-symbol journal limit"
        )
    symbols = [valid_symbol(TypeAdapter(TerminalSymbol).validate_python(s)) for s in args.symbols]
    output = args.output or Path("artifacts") / (
        "research-observation-" + utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    )
    asyncio.run(run(args.minutes, args.interval_seconds, symbols, output))


if __name__ == "__main__":
    main()
