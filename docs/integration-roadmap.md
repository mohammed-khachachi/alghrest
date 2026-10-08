# ALGHREST ↔ HMM_Trading Integration Roadmap

This document describes how ALGHREST (the root multi-agent trading platform) and HMM_Trading (the educational/research subproject under `research/hmm_trading/`) should be connected over time.

It is documentation only. No integration code exists yet, and none should be written until the design questions in this document are explicitly answered for the relevant level.

## 1. Scope and intent

HMM_Trading produces market-regime classifications and educational backtest results. ALGHREST consumes market intelligence from many sources (news, sentiment, on-chain, macro, technical). At some point a regime signal could become another input ALGHREST uses to bias allocation or strategy selection.

That eventual flow is the **only** motivation for integration. Until it is genuinely needed, the two projects should remain decoupled, because:

- HMM_Trading must keep running standalone with a tiny dependency surface.
- ALGHREST must not gain a runtime dependency on HMM_Trading internals.
- The integration boundary should be **boring on purpose** — easy to test, easy to monitor, easy to replace.

This roadmap stages that work in three levels, smallest first.

## 2. Current state (Level 0 — no integration)

As of branch `docs/monorepo-workflow` on 2026-05-17:

- HMM_Trading lives at `research/hmm_trading/` and is fully self-contained.
- HMM_Trading writes generated artifacts to `research/hmm_trading/outputs/` (gitignored).
- ALGHREST has **no** code that reads HMM_Trading outputs, imports HMM_Trading modules, or shells out to HMM_Trading.
- No Kafka topic, REST endpoint, or Redis key inside ALGHREST is reserved for HMM regime data yet.

This is the correct state until the trigger conditions in Level 1 are met.

## 3. Level 1 — File-based CSV/JSONL artifacts (next planned step)

**Goal.** ALGHREST consumes HMM_Trading outputs as static files. HMM_Trading does not change. ALGHREST gains a small read-only adapter and nothing else.

**Why this level first.** It creates a clear contract (a file path and a column schema) without coupling either side to the other's runtime, dependencies, or Python imports. Either project can be torn out and replaced without breaking the other.

**Source artifacts.** HMM_Trading already produces these under `research/hmm_trading/outputs/results/`:

| File | Purpose |
|---|---|
| `hmm_regimes.csv` | Per-bar regime classification time series |
| `state_summary.csv` | Per-regime summary statistics |
| `backtest_metrics.csv` | Educational backtest summary metrics |
| `transition_matrix.csv` | Regime transition probabilities |

`hmm_regimes.csv` is the most useful candidate for an ALGHREST signal, because it is a time series keyed by date. The other three are summary tables intended for inspection, not streaming consumption.

**Trigger conditions (all must be true before starting Level 1).**

- A specific ALGHREST consumer is identified — e.g., an analyst agent that will publish to a `regime.*` Kafka topic, or a dashboard panel that will render HMM regimes alongside ALGHREST's own signals.
- The exact CSV/JSONL column schema is agreed and committed to this document.
- The refresh cadence is agreed (one-shot on demand, hourly, daily, end-of-day).
- A staleness policy is agreed (what happens when the file is missing or older than N hours).
- A test plan exists that can run without HMM_Trading installed (use a fixture CSV).

**Design constraints for the Level 1 adapter.**

- Lives **inside ALGHREST**, not inside HMM_Trading. HMM_Trading must remain unaware of ALGHREST.
- Reads files only. Never imports `src/` from HMM_Trading. Never invokes the HMM pipeline.
- Treats the file path as configuration (e.g., `HMM_OUTPUT_DIR` env var), with a sensible default of `research/hmm_trading/outputs/results/`.
- Validates the schema on load and fails closed (no regime signal) on schema mismatch.
- Has its own unit tests under `tests/unit/` that read a fixture CSV checked into the test tree.

**Explicitly out of scope for Level 1.**

- Streaming, Kafka topics dedicated to HMM, websockets.
- Any change to HMM_Trading source.
- Any HMM_Trading dependency appearing in the root `pyproject.toml`.
- Calling `main.py` from ALGHREST code.

**Do not implement the Level 1 adapter yet.** This document records the intent. The implementation requires the trigger conditions above to be met first, in a dedicated branch and PR.

## 4. Level 2 — CLI integration (optional, later)

**Goal.** ALGHREST can ask HMM_Trading to regenerate outputs on demand by invoking the HMM CLI as a subprocess. The contract is still file-based — Level 2 only adds the ability to trigger a refresh.

**Trigger conditions.**

- Level 1 has been in production-equivalent use long enough to validate the column schema.
- There is a real need for ALGHREST to drive HMM_Trading runs (for example, parameter sweeps, on-demand regime recomputation after a market event).
- HMM_Trading's `main.py` accepts an explicit output directory and configuration argument so ALGHREST can sandbox each run.

**Design constraints.**

- ALGHREST shells out to `python main.py` from inside `research/hmm_trading/` using HMM_Trading's own venv. It does **not** install HMM_Trading dependencies into the ALGHREST venv.
- Subprocess invocation, timeouts, and output capture follow the existing ALGHREST connector patterns under `connectors/`.
- Failure modes are explicit: HMM not installed, HMM venv missing, run timed out, run failed, outputs missing. Each maps to a defined ALGHREST behavior (skip signal, fall back to last known regime, raise).
- Still no Python imports across the boundary.

**Out of scope for Level 2.** Anything Level 3.

## 5. Level 3 — Python API integration (only if necessary)

**Goal.** ALGHREST imports a packaged, versioned HMM module directly and calls it in-process.

**Trigger conditions.**

- Levels 1 and 2 are demonstrably insufficient — e.g., per-tick regime updates with latency that the file/CLI contract cannot meet.
- HMM_Trading has a **stable public API** documented in `research/hmm_trading/docs/` and a versioning policy.
- HMM_Trading is packaged (a real `pyproject.toml` build target, importable as a single module name with a defined surface area).
- The ALGHREST and HMM_Trading dependency graphs are compatible — same Python version, no conflicting library pins.

**Design constraints.**

- Only the public API is imported. Internal modules (`src/pipeline/`, `src/models/`, `src/analysis/`) remain off-limits.
- HMM_Trading still runs standalone. Its tests do not depend on ALGHREST being installed.
- The dependency is added to the root `pyproject.toml` as a normal package pin (eventually a path dependency or a published wheel), not as a sibling-directory import hack.

Most projects never need Level 3. Treat it as an escape hatch, not a default.

## 6. Tracking and review

When a Level is proposed, open a tracking issue with this template:

- **Level**: 1 / 2 / 3
- **Consumer**: which ALGHREST module will consume the signal
- **Schema**: file format, columns, types, units, ID for the column that joins to ALGHREST data
- **Cadence**: how often the signal is produced or consumed
- **Failure policy**: what ALGHREST does when the HMM signal is missing, stale, or invalid
- **Test plan**: how the adapter is tested without depending on a live HMM_Trading run

The issue must be resolved before any code under either project is touched.

## 7. Rules that apply at every level

- HMM_Trading remains independent. Its tests, its `requirements.txt`, its `pyproject.toml`, and its venv are not affected by ALGHREST.
- ALGHREST never modifies HMM_Trading source as part of an integration change.
- HMM_Trading source never imports anything from ALGHREST.
- Cross-project changes ship in dedicated branches and PRs, and call out both projects in the description.
- Documentation in `docs/monorepo-workflow.md` and this file stays the source of truth for what is and is not allowed across the boundary.

## 8. Where to look next

- Monorepo layout and workflow: `docs/monorepo-workflow.md`
- ALGHREST top-level overview: `README.md`, `CLAUDE.md`
- HMM_Trading overview: `research/hmm_trading/README.md`
- HMM_Trading architecture (sections 9 and 11 describe the integration boundary from the HMM side): `research/hmm_trading/docs/architecture.md`
