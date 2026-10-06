# Recovery and advisory isolation increment — 2026-10-04

## Scope and provenance

This is a filesystem checkpoint, not a Git commit. The requested status, diff,
diff-stat, log, branch and remote inspections cannot resolve a repository. The
visible `.git` directory is empty; branch, history, remote and local divergence
remain unknown. No Git initialization, reset, clean, checkout, pull or commit was
performed. The absence of visible metadata does not establish its absence on the
original computer.

## Checkpoint

Evidence directory: `artifacts/recovery-20261004/` (ignored local artifacts).

- `source.tar.gz`: 395 reviewable UTF-8 source/configuration/documentation files.
- `manifest.json`: paths, byte counts, modes and SHA-256 for those source files.
- `local-state.tar.gz.aesgcm`: authenticated encrypted snapshot of 868 files,
  including local configuration, raw soak evidence, local databases and research
  artifacts. No plaintext intermediate archive was written.
- Recovery key: `.secrets/recovery-20261004.key`, owner-only permissions, excluded
  from both snapshots and ordinary reports. Keep a separate secure copy of the
  key and encrypted archive; losing the key makes this snapshot unrecoverable.
- `verification.json`: archive hashes and separate restore verification results.

Both archives were restored into separate owner-only temporary directories and
every captured file compared byte-for-byte and by permissions. Source files were
also compared with the original tree after capture. The first restore's mode
check failed because Python's tar data filter normalizes write permissions; a
second restore explicitly applied recorded modes and passed. The archives were
not changed to conceal that initial verification failure.

Excluded: installed environments/dependencies, caches, generated HTML coverage,
protected `.git/.agents/.codex/.aws` surfaces and symlink targets. This is not an
external Docker-volume or whole-machine backup. Existing excluded state was not
modified. The ordinary source archive excludes local credential files, raw logs,
databases and opaque artifacts; candidate text was screened against local secret
values held only in memory and selected credential patterns. This is not a claim
that arbitrary previously unknown credentials can be recognized perfectly.

## Pre-existing failed soak — do not restart automatically

The original `artifacts/deployment-soak/` evidence is preserved unchanged and also
captured in the encrypted snapshot. Saved status: **failed**, **564 cycles**,
operation `await_fill`, `PortfolioAccountant` exited with code 1. Its log includes:

```text
asyncpg.exceptions._base.InterfaceError: cannot perform operation: another operation is in progress
```

This is a pre-existing failure, not a regression from the boundary increment.
The error alone does not establish its precise concurrency root cause. No soak
service was restarted, repaired, or repurposed. Existing paper services were not
used as test databases.

## Baseline and increment results

Results and exact command records will be appended after validation. Baseline
tests use the credential-free restored source tree and separate disposable
PostgreSQL/Redis containers on loopback ports 35432/36379. The first sandboxed
attempt could not access services reliably and timed out in Starlette TestClient;
its log is retained separately from the unrestricted baseline. No coverage
threshold or application behavior has been changed for baseline collection.
