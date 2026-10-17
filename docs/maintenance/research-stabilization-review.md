# Research stabilization review — 2026-10-16

This is an implementation self-review against `research-stabilization-plan.md`.
It is not an independent security audit or a trading-readiness assessment.

## Contract and source identity

- The research quote endpoint opts into metadata. Ordinary terminal quote arrays
  retain their contract. Quote/cache observation fields are optional so existing
  saved snapshots remain readable without inventing past source clocks.
- The native quote cache stores the quote and its successful fetch observation
  together. Cache/stale delivery preserves that observation. Provider session
  declarations require Nasdaq/Yahoo provenance; an adapter's `Open` assumption
  cannot become a provider declaration.
- Python and browser validators reject future or incoherent fetch clocks and
  source/provider identities. Display context never changes the overall
  `freshness=UNKNOWN`, event-risk or execution/advisory boundaries.
- Source-reported market closure only qualifies a dated price observation.
  Session context expires after 90 seconds; the 15-minute price display threshold
  does not establish real-time data. No holiday calendar or candle completion
  guarantee is inferred. PDF exports retain these limitations.

## Archive and persistence

- Export uses one read transaction and includes research watch membership plus
  immutable snapshot rows, including unwatched history. Account tables and
  terminal/assistant credentials are excluded.
- Schema, unique identities, symbols, source/save clocks, raw payload limits,
  total bytes and content checksum are validated before restore. A checksum
  detects corruption, not trusted authorship; imported evidence is labelled.
- Restore revalidates conflicts and aggregate limits inside `BEGIN IMMEDIATE`.
  All insertions, watch additions and restoration annotations commit together.
  A failure rolls back every insertion. No record replacement, automatic
  trimming, account mutation or snapshot deletion is introduced.
- Exact raw JSON payloads and stored save strings are preserved. Repeating the
  same restore adds nothing. Removing a watch preserves snapshots. The browser
  previews counts, then applies a merge; concurrent writes may change counts but
  cannot bypass the server's conflict/limit checks.
- Download/upload paths use existing authentication and explicit write-client
  requirements. Tokens stay in headers, and download streams and request bodies
  have byte bounds. CLI output is created exclusively and privately on Unix.

## Runtime and failure handling

- Launchers start only four local research services with an environment
  allowlist. Broker, agent, DeFi and execution services are not started.
- The workflow regression covers outages, original snapshot preservation,
  restoration, PDF availability, recovery, full restart and owned-process cleanup.
- The time-bounded observer samples real read-only HTTP reports for four symbols
  and saves them only in its own disposable journal. It checks clocks, identities,
  disabled execution/AI and unchanged application source. It records missing
  feeds separately from service errors and fails on excessive gaps/interruption.
- A successful 30-minute run cannot establish multiple market sessions or a
  24-hour operational result. Native Windows cleanup remains unverified.

## Local checkpoint scope

The checkpoint combines the authorized OpenTerminal integration and this
stabilization increment with the repository's existing HEAD. An alternate Git
index composes mixed application/router files without unrelated briefing,
personal-policy or demo-feed changes. The current branch, working files and
normal Git index remain intact. The candidate is materialized separately and
verified there before its local branch is created. No push is performed.

The Git whitespace check retains four original-source exceptions: a trailing
space in the bundled font license and a final blank line in each upstream cache,
Nasdaq and Yahoo provider file. The three upstream SHA-256 identities match the
pinned manifest. These original files are preserved rather than reformatted.

Verification counts, exact receipts and remaining infrastructure limits belong
to `research-stabilization-verification.json`. Local artifacts retain test logs,
screenshots, source hashes, original diffs and the private operator-backup receipt.
