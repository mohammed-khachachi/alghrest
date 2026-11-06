# OpenTerminal Linux session service

Use `node scripts/openterminal-service.mjs start` to run OpenTerminal in its own
systemd user service cgroup, independent of the launching shell or browser scope.
The helper creates a transient unit named `alghrest-openterminal.service`.
It does not install a unit file, enable boot startup, enable linger, or start any
ALGHREST trading infrastructure. The user manager must remain available; this is
not a promise of persistence after logout or reboot.

The command uses `/usr/bin/env -i`, the existing research environment allowlist,
and an explicit Node executable path. Parent and user-manager credentials and
`NODE_OPTIONS` are excluded. Repository paths with spaces are passed as individual
arguments. Ports 3001/4001 must be free; an existing listener is never killed.
An already active unit is reported, not restarted; use the probe to establish
identity and readiness. A failed existing unit requires inspection and explicit
stop before a fresh start. This helper does not restart assistant8011/dashboard5173.

```bash
node scripts/openterminal-service.mjs plan
node scripts/openterminal-service.mjs start
node scripts/openterminal-service.mjs status
node scripts/openterminal-service.mjs logs
node scripts/openterminal-service.mjs stop
```

`Restart=always`, `RestartSec=3s`, `StartLimitIntervalSec=60s` and
`StartLimitBurst=3` recover accidental exits, including a clean SIGTERM exit,
while bounding rapid failure loops. Explicit `stop` stays stopped.
`KillMode=control-group` and a 15-second stop timeout cover descendants. Inspect
`NRestarts`, invocation ID, lifecycle logs and exit status after any incident.
On systemd 259.9 the last failure Result may remain `exit-code` after the start
limit is reached; the journal records `Start request repeated too quickly`.
The test therefore checks stopped/bounded behavior and the journal event.

`logs` prints only the repository's structured `[research-lifecycle]` records,
with approved fields. It omits vendor output, environment and command arguments.
Avoid sharing unfiltered journals; third-party output can contain sensitive data.
See [lifecycle recording](openterminal-lifecycle.md) for event meanings.

## Bounded observation

```bash
node scripts/openterminal-service.mjs observe --seconds 600 --interval 15 --output /tmp/openterminal-observation.jsonl
```

Choose a new output filename: existing files are never overwritten. Each JSONL
sample retains service invocation/restart count, cgroup process PID/start ticks,
listener ownership and HTTP results. Acceptance requires localhost web HTTP200,
API `/api/status` HTTP200 with `integration=alghrest-research`, `ok=true`, `ai=false`
and `execution_enabled=false`, and no process/invocation/restart identity changes.
An automatic recovery fails uninterrupted stability. The first snapshot, a final
snapshot at/after the requested duration, minimum sample count and maximum gap
(interval plus 15 seconds) are required. Both wall and monotonic clocks are used
for gap detection; command timeouts prevent indefinite stalls. The summary gives
the actual observation span, sample count, largest gap and failures.

A passing run establishes only that bounded sampled interval, not indefinite
stability or absence of a sub-interval HTTP outage. Development-server restarts
from source edits also fail the identity check. Avoid editing watched sources
during observation.

## Verification and historical limits

```bash
node tests/openterminal-service.test.mjs
OPENTERMINAL_SYSTEMD_FIXTURE=1 node tests/openterminal-service-systemd.test.mjs
```

The host fixture creates only a uniquely named temporary user service. It checks
survival after the launching command exits, recovery after SIGTERM, intentional
stop and crash-loop limiting, then removes its fixture state. It never signals
OpenTerminal. The fixture opt-in needs access to the host user service manager.

The historical SIGTERM sender remains unknown. Moving out of a browser cgroup
removes an observed lifetime coupling; it does not establish who sent the earlier
signal. Node's ordinary signal callbacks do not expose sender PID/UID. Structured
logs identify signals this launcher sends and mark received-signal senders unknown.
Capturing a future external sender requires OS-level siginfo tracing (for example,
a carefully scoped `strace` signal trace) or audited kernel tracing with separate
permission; this workflow installs neither and cannot retroactively attribute a
signal. No new native dependencies, sudo, audit rules or kernel settings are used.
