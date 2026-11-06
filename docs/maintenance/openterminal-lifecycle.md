# OpenTerminal lifecycle diagnostics

The launchers `scripts/openterminal.mjs` and `scripts/run_research.mjs` emit
structured stderr lines beginning with `[research-lifecycle] `. Each line contains
one JSON object with these fields:

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC ISO timestamp for this observation |
| `launcher`, `launcher_pid`, `launcher_ppid` | Recording launcher and its process ancestry at observation time |
| `event` | Spawn, signal, child exit, shutdown request, or cleanup event |
| `service`, `child_pid` | Owned child where applicable, otherwise null |
| `reason` | Trigger such as `supervisor_signal`, `unexpected_child_exit`, `child_start_error`, `owned_group_cleanup`, or `shutdown_timeout` |
| `signal`, `code` | Signal name and numeric exit code separately; absent values are null |
| `sender`, `sender_pid` | `launcher` and its PID for its own signal requests; `unknown` and null for received signals and observed exits |
| `error_code` | OS error identifier where available, otherwise null |

The records exclude environment values, command arguments, tokens, and raw child
output. Normal application stdout/stderr still passes through separately and must
not be treated as sanitized lifecycle metadata.

An unexpected child SIGTERM now reports `signal SIGTERM; code null`, rather than
`exited (null)`. An external SIGTERM or SIGINT received by the launcher is recorded
before it forwards shutdown to owned child groups. Repeated signals remain handled
while cleanup finishes. An exited leader does not exempt its remaining descendants
from group cleanup. Existing environment allowlists and restart policy are unchanged.

On POSIX, `signal_sent` means the operating system accepted the launcher's signal
request; it does not prove every descendant has exited. `signal_skipped` with
`ESRCH` means the target group no longer exists. On Windows, `signal_requested`
records invocation of `taskkill`; `signal_sent` is emitted only after `taskkill`
exits successfully, and errors are recorded separately. Runtime signal tests run
on Linux; Windows process termination has not been validated here.

These diagnostics cannot recover the sender of a past signal. Node's signal event
does not provide the sender PID; parent PID is not sender evidence. Correlate an
observed receipt with a matching `signal_sent` record from a known parent launcher,
or use an explicitly authorized OS-level tracer for future events. Do not infer an
external sender solely from timing or process ancestry.

The launchers write lifecycle metadata to stderr. The launch environment must
retain those records (for example through a service journal) for later analysis.
No persistent application log or automatic restart was introduced by this change.
An already running launcher must be replaced during an authorized restart before
it can emit these new records.

## Regression checks

```bash
node --test tests/research-lifecycle.test.mjs tests/research-supervisor.test.mjs tests/research-launcher.test.mjs tests/openterminal-launcher.test.mjs
```

Fixtures launch disposable Node processes with empty environments. They cover
real child SIGTERM, external supervisor shutdown, repeated signals, safe spawn
failure reporting, descendant cleanup, busy-port preservation, and credential
isolation. They do not establish long-running service stability or identify the
historical SIGTERM sender.
