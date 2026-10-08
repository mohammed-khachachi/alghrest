# Runtime efficiency — 2026-09-29

## Operating modes

Use the installed Python 3.12 environment from the repository root. Plans show
commands without starting services. Starting a mode is an explicit operator
command; there is no automatic transition between modes.

```bash
python -m scripts.runtime research plan
python -m scripts.runtime paper plan
python -m scripts.runtime full plan
```

| Mode | Starts | Requirements |
| --- | --- | --- |
| `research` | Standalone assistant Compose project `alghrest-research`, one API worker, separate SQLite volume | Docker; opens API on loopback 8011; no opening balances or trading infrastructure needed |
| `paper` | Isolated PostgreSQL/Redis/single Kafka plus the maintained seven-agent host supervisor | Linux supervisor, configured local paper endpoints, explicit account scope and previously imported opening statement |
| `full` | Existing full Compose topology | Deliberate development/paper deployment; heavier footprint; launcher rejects resolved live services |

Replace `plan` with `start`, `status` or `stop`. `stop` preserves volumes. The
paper start provisions schema/topics, then starts the supervisor; an earlier
step's failure prevents later steps. It never imports balances, deposits funds,
starts strategies or activates live trading. Check `python -m scripts.paper
preflight` after starting: process existence alone is not execution readiness.
See [paper preparation](../execution-recovery.md) for opening statements.

Research mode exposes the API only. For the existing dashboard, start its Vite
server separately and open `/assistant`; that route does not connect the trading
WebSocket. The Docker research mode has its own empty-on-first-use SQLite volume;
locally running `python -m api.advisor` continues to use its separately configured
file. No local journal was copied or discarded. Before introducing the named
Compose project, the workspace check found no existing manual-assistant Docker
container or research volume to migrate. The shared base image still contains
the project's broader dependencies; this change reduces active runtime work,
not image size.

`full` retains the existing deployment's limitations and security findings.
This launcher is not a live deployment certification. Switching modes does not
silently stop another deployment or reset its data. Do not run multiple
executors against the same book; existing durable writer leases remain enforced.

## Measured results

Controlled before/after tests and builds on this workspace:

| Workload | Before | After | What was checked |
| --- | --- | --- | --- |
| Six markets, same five RSS sources within TTL | 30 requests | 5 requests | Same filtered headlines and source errors, mocked HTTP |
| Dashboard without viewers, 2.2 seconds | 11 data-builder calls | 0 calls | Viewer connect/disconnect/resume also tested |
| Main minified JavaScript entry | 821.65 kB (232.39 gzip) | 310.90 kB (95.51 gzip) | All routes compiled as lazy chunks; no 500 kB warning |
| GARCH forecast output after removing unused EGARCH fit | Reference diagnostic enabled | Identical fields in 9 seeded cases | Excludes generated signal ID/time only; tests retain independent numerical assertions |

JavaScript entry size is not total page transfer: a visited page downloads its
own code and shared dependencies. For example, the shared chart chunk is
365.57 kB. This is route splitting, not removing the charting functionality.

Cold import measurements use three fresh Python processes per module. Values
below are medians. USS is private process memory, in MiB; RSS includes shared
pages and must not be summed as physical memory savings.

| Module | Before USS MiB | After USS MiB | Before seconds | After seconds |
| --- | ---: | ---: | ---: | ---: |
| `agents.base_agent` | 139.15 | 60.12 | 0.725 | 0.504 |
| `agents.tier5_execution.order_router` | 139.25 | 60.12 | 0.696 | 0.506 |
| `agents.tier5_execution.exchange_executor` | 218.54 | 138.94 | 1.254 | 1.705 |
| `api.advisor` | 54.61 | 54.88 | 0.518 | 0.867 |

The agent imports stopped loading Pandas through BaseAgent. Quantitative modules
still load their own necessary dependencies. Timing results are mixed and noisy:
these measurements do not establish a general startup or trading-latency
speedup. The historical September 28 `before.json` is retained but the table uses
the same-session September 29 `before-resume.json` comparison.

No matching host application processes were observed in either the sandboxed
or host-level sample. This is an unavailable runtime baseline, not zero resource
usage. The local paper PostgreSQL, Redis and Kafka containers were healthy.
Container CPU/RAM, Kafka lag, end-to-end order latency and LLM cost reductions
were not established by these probes. No trading process was started or stopped
for the measurement; no real exchange or Anthropic call was made.

## Reproduce and inspect

Final verification: **660 passed, no failures or skips**, with combined
statement/branch coverage **76.6393%** against the unchanged 70% gate. Ruff,
Black, isort, architecture checks and strict MyPy (99 source files) passed.
TypeScript/Vite production build passed. The tests report 471 non-failing
warnings, mostly existing deprecations. The real Kafka replay, PostgreSQL
accounting/recovery and Redis cases used isolated test books/data.

The assistant/paper Compose files validate. Mode plans and launch refusal/failure
paths were checked; the new launcher was not used to start the full deployment or
build/deploy the assistant container. Runtime live-market latency remains unmeasured.

```bash
python -m scripts.profile_runtime --imports --output artifacts/performance/sample.json
# For a longer sample of already-running host application processes:
python -m scripts.profile_runtime --samples 60 --interval 1 --output artifacts/performance/runtime.json
python scripts/check_architecture.py
python -m scripts.test_with_services --timeout=60 --timeout-method=thread -q --tb=short
```

The process probe records module identities, cumulative CPU time, RSS and USS.
It does not record command-line arguments, environment variables or credentials.
It does not start services, issue orders or read financial records. Container
monitoring remains in the existing monitoring stack.

Local, gitignored evidence under `artifacts/performance/`:

- `before-resume.json`, `after.json`, `host-runtime.json`: measurements and limitations.
- `dashboard-before.txt`, `dashboard-after.txt`: full build output.
- `workloads.json`, `compare_workloads.py`, `news-before.py`, `dashboard-ws-before.py`: controlled comparison and saved references.
- `full-tests.txt`, `tests.xml`, `coverage.json`: complete-suite validation.

Read [the architecture decision](../decisions/0002-runtime-boundaries.md) for
implemented boundaries and deferred structural changes. Existing accounting,
idempotency, recovery, risk limits and the 70% coverage threshold are preserved.

For UI keys, authenticated local infrastructure and AI allowances, see
[access and AI limits](access-and-ai-limits.md).
