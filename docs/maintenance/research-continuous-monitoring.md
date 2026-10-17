# Research observation — closed early on 2026-10-16

The human explicitly ended this observation early on 2026-10-16. The worker and
its four owned research services are stopped, and heartbeat `alghrest-2` is
PAUSED. The preserved sample-start span is 2 hours 43 minutes (164 cycles and
656 symbol readings); the planned 120-hour run was not completed. The raw worker
records the requested SIGTERM as an interruption. Its original status remains
unchanged; `user-stop.json` explains the user-requested termination.

Final report: `artifacts/research-monitor-20261016-5days/final-report.md` and
`final-report.json`. Shutdown verification confirms no listeners on research
ports 8011, 5173, 3001 or 4001. The following sections describe the original
setup, not an active observation. Do not restart it without a new user request.

The authorized workflow added AAPL and BTC to the actual research watchlist,
saved two server-collected public-data readings per symbol, compared them and
exported an Arabic PDF plus a research-only backup. The existing journal was
exported before any watch addition. The new archive was restored into a separate
database and a repeated restore added nothing. Account tables and credentials
were excluded. Private output and the receipt are under
`artifacts/research-use-20261016/`; the PDF is
`output/pdf/ALGHREST-research-live-20261016.pdf`.

## Continuous observation

`scripts/monitor_research.py` runs for 120 hours with a 60-second sample interval
and at most two concurrent symbol reads. The initial symbol set is AAPL, MSFT,
BTC and ^VIX. Its output is `artifacts/research-monitor-20261016-5days/`.

The process reads the existing four local services. It does not write snapshots
to the user's journal, change watches, call broker APIs, start agents or restart
services. Sampling evidence is independent of the journal's 100-snapshot limit.
Each sample preserves quote/analysis clocks, source response hashes, provider
availability, quality and dated provider session context. Adapter assumptions
cannot become reported open/closed sessions. A missing external feed remains
explicit and does not become a zero price or a freshness pass.

`status.json` is replaced atomically. `samples.jsonl` retains every successful
cycle; `events.jsonl` records source, quality and session transitions. Logs have
byte bounds and never trim old evidence automatically. Private directories/files
use Unix 0700/0600. The monitor refuses an existing output directory, preserving
earlier evidence instead of resuming or overwriting a run.

Service/permission/identity errors, changed execution or AI boundaries, changed
application source, interruption, a backward clock or a sample gap above five
minutes fail the run and preserve a final receipt. Source hashes are checked
before and after collection. There is no automatic restart or recovery claim.
An unavailable public quote/history/news feed is counted separately from an
application failure.

The computer, research services and desktop scheduler must remain available.
Sleep, shutdown or a lost process can invalidate continuity. A scheduled check
cannot manufacture samples for an offline interval. Five calendar days are the
planned bound, not evidence that five days have already passed. Market sessions
are counted only when providers declare them; no exchange calendar is inferred.

## Follow-up

A thread heartbeat checks the existing worker hourly. It stays quiet when the
state is unchanged or non-actionable, reports meaningful source/session changes,
and notifies in Arabic on failure or completion. On terminal failure it preserves
the records and pauses itself; it never starts another worker. On completion it
summarizes observed duration, gaps, states and limitations, then pauses itself.
Notification latency can therefore be up to approximately an hour while the
desktop scheduler is available; this is not a trading alert service.

The exact automation identifier and process identity are recorded in the local
launch/follow-up receipts. No credentials enter those receipts.

## Validation

- 60 focused Python tests passed, including 15 monitor cases for gap/clock
  rejection, unverified crypto session handling, source-change termination,
  service identity/AI/execution boundaries, credential isolation and byte limits.
- A separate short live trial passed three AAPL sample cycles; this is startup
  evidence, not multi-day evidence.
- Ruff, Black and strict MyPy passed for the new monitor scope.
- The exported five-page PDF was rendered and visually reviewed.

To start a separately authorized future run with a new output directory:

```bash
PYTHONPATH=src .venv/bin/python scripts/monitor_research.py --hours 120 --interval-seconds 60 --symbols AAPL MSFT BTC '^VIX' --output artifacts/research-monitor-NEW-RUN
```

Do not reuse the closed run's output directory. A separately authorized future
observation needs a new directory and must retain the old run's evidence.
