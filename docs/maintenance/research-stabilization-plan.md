# Research stabilization goal - 2026-10-16

User-authorized sequence: freshness/session context, backup/restore, extended
multi-symbol research check, then scoped review, broader validation and a Git
checkpoint. Research only; no execution services or real-money mutations.

## Acceptance criteria

1. Preserve provider-declared market state and quote fetch/cache provenance.
   Distinguish provider reports from adapter assumptions. Display quote age,
   source-reported closed/open context and candle-time limitations without
   inventing session/holiday calendars, latency guarantees or freshness passes.
   Old snapshots stay readable with original clocks. Test clock/cache/session
   boundaries and show the same limitations in PDF exports.
2. Export only research watch membership and immutable snapshot payloads; exclude
   account journals, credentials, other advisory tables and terminal API keys.
   Validate schema, counts, identities and a content checksum before restoration.
   Merge atomically, reject conflicting identities or exceeded limits, never
   overwrite/delete existing records, and prove repeatable restoration into an
   isolated database. Protect the operator's real journal.
3. Run a bounded 30-minute check with multiple actual OpenTerminal symbols and
   periodic samples. Record source states, quality, response times, source-declared
   session context and process/HTTP availability. Keep missing feeds explicit,
   check research archive/PDF/restore in an isolated journal, record every gap,
   fail on application/identity/permission errors, and do not auto-restart a failed
   run. This establishes only the observed duration, not multi-session or 24-hour
   stability. Source/session diversity is reported rather than manufactured.
4. Review the scoped changes and their requirements, run focused and broader
   non-live regressions, builds, architecture and applicable static checks.
   Record infrastructure-dependent coverage limitations without weakening gates.
   Preserve unrelated working-tree content and credentials. Produce a local Git
   checkpoint only for the authorized integration scope; do not push.

## Progress

- Goal created and initial working-tree/source evidence preserved.
- Phase 1: implemented and verified with Python/browser/native contract tests,
  live browser inspection and a rendered five-page PDF example.
- Phase 2: implemented and verified with conflict/limit/atomicity regressions,
  authenticated HTTP preview/restore, exact raw payload preservation, repeated
  restore and an isolated check of the operator's private empty research archive.
- Phase 3: passed, 2026-10-16 10:01:31–10:31:51 UTC: 1,820.26 seconds,
  31 cycles and 124 symbol readings. Maximum sample gap: 60.001 seconds. All
  four services stayed available without restart. AAPL/MSFT/BTC quotes, history
  and news were available; VIX quote/history were unavailable throughout while
  its news remained available. Only pre-market source declarations for equities
  and unknown sessions for BTC/VIX were observed. Exact restoration of all 124
  isolated snapshot payloads, idempotent retry and PDF generation passed.
- Phase 4: implementation self-review and production builds passed. The current
  workspace's broader suite passed 2,838 tests with 53 infrastructure-dependent
  skips and 82.00% aggregate coverage. The independently materialized scoped Git
  candidate passed 2,470 tests with 53 skips and 80.81% coverage. Both retain the
  70% gate. The scoped candidate also passed authenticated live HTTP capture,
  backup/restore and PDF checks on its own temporary port/database. The local
  checkpoint is retained on `codex/research-stabilization`; the current branch,
  ordinary Git index and unrelated work are preserved. Nothing is pushed.

All four phases are complete. Verification and limitations are retained in
`research-stabilization-verification.json`; the exact checkpoint identity is in
`artifacts/research-stabilization-20261016/checkpoint.json`.

Evidence: `artifacts/research-stabilization-20261016/`.
