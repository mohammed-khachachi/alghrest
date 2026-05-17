# CSV / File Adapter Contract — ALGHREST ↔ HMM_Trading

This document defines the file-based contract between **HMM_Trading** (producer of research regime signals) and **ALGHREST** (future consumer).

It is documentation only. No reader, writer, or runtime adapter exists yet, and none is implemented in this phase. The contract here is the design that any future Level 1 adapter (see `docs/integration-roadmap.md`) must conform to.

## 1. Purpose

Define a stable, file-based interface so that:

- HMM_Trading can produce regime classifications and supporting metadata without knowing anything about ALGHREST.
- ALGHREST can later consume those classifications without importing HMM_Trading code or running its dependencies.
- Either side can be replaced, paused, or re-implemented without breaking the other.

The contract is intentionally simple: timestamped rows of regime classifications, written to a well-known directory, in a well-known format, with a well-known schema.

## 2. Non-goals

- **Streaming.** This is a batch, file-based contract. No websockets, no Kafka, no tail-mode readers.
- **Bi-directional flow.** Files only move from HMM_Trading → ALGHREST. ALGHREST does not write into HMM_Trading.
- **Live trading signals.** HMM_Trading is educational/research. Regime labels are research outputs, not order instructions.
- **Schema evolution at runtime.** Schema changes are versioned (see §10), not inferred.
- **Implementation.** Neither the producer nor the consumer is built in this phase.

## 3. Producer / Consumer boundary

```
┌──────────────────────────┐                      ┌──────────────────────────┐
│  HMM_Trading (producer)  │                      │   ALGHREST (consumer)    │
│                          │                      │                          │
│  src/pipeline/runner.py  │   writes CSV/JSONL   │   future adapter under   │
│  src/reporting/...       │ ───────────────────► │   connectors/data_       │
│                          │                      │   providers/ or similar  │
│  Owns: schema producer,  │                      │   Owns: schema validator,│
│  file layout, format     │                      │   staleness policy,      │
│                          │                      │   failure handling       │
└──────────────────────────┘                      └──────────────────────────┘
                  │                                            │
                  ▼                                            ▼
       alghrest-test/HMM_Trading/                 reads files only; never
       outputs/results/*.csv  (gitignored)        imports HMM_Trading code
```

Producer responsibilities (HMM_Trading):

- Write files atomically (write to a temp name in the same directory, `fsync`, then rename — never leave a half-written file at the canonical path).
- Conform to the schema and version declared in §6–§11.
- Never depend on ALGHREST being installed or running.

Consumer responsibilities (ALGHREST, future):

- Read files only. Never import HMM_Trading source. Never call `main.py`. (CLI invocation is Level 2, not this contract.)
- Validate schema and version on every read; fail closed on mismatch.
- Apply a staleness policy (configurable; default suggested below).
- Surface failure modes as structured errors, not silent fallbacks.

Neither side imports the other.

## 4. File location

The canonical producer output directory is:

```text
alghrest-test/HMM_Trading/outputs/results/
```

ALGHREST should treat this as a **default**, not a hard-coded constant. The Level 1 adapter must accept the directory via configuration (e.g., an env var such as `HMM_OUTPUT_DIR`) so the path can be redirected for tests, CI, or alternate deployments.

`outputs/` is gitignored on the producer side. No regime CSV/JSONL files are ever committed to the repository.

## 5. Filename convention

The contract defines two filename forms:

### 5a. Canonical "latest" filenames (current HMM_Trading behavior)

These are the files HMM_Trading already writes today. They are overwritten on every pipeline run:

| File | Role |
|---|---|
| `hmm_regimes.csv` | Per-bar regime classification time series (**primary signal**) |
| `state_summary.csv` | Per-state descriptive statistics |
| `transition_matrix.csv` | State-to-state transition probabilities |
| `backtest_metrics.csv` | Educational backtest summary metrics |
| `backtest_results.csv` | Per-bar backtest equity curves |
| `run_config.json` | The exact config used for this run |

`hmm_regimes.csv` is the only file the Level 1 adapter is required to consume. The rest are informational and may be consumed later.

### 5b. Optional dated snapshots (recommended for production)

To support reproducible reads, audit trails, and rollback, HMM_Trading may additionally write timestamped snapshots alongside the canonical files:

```text
hmm_regimes_<ticker>_<YYYYMMDDTHHMMSSZ>.csv
hmm_regimes_BTC-USD_20260518T143000Z.csv
```

Rules:

- Lowercase `hmm_regimes_`, uppercase ticker (with `-` separator, see §8), ISO-8601 basic UTC timestamp (`YYYYMMDDTHHMMSSZ`), `.csv` suffix.
- Snapshots are immutable. Never overwrite an existing dated file.
- The canonical `hmm_regimes.csv` continues to point at the most recent run (it is a copy or a symlink, producer's choice).

Dated snapshots are **optional** for Level 1. The consumer must work using only the canonical filename.

## 6. CSV schema — `hmm_regimes.csv`

UTF-8 encoded, comma-separated, with a header row. Newlines are `\n` (LF). The first column is a date or timestamp; the remaining columns describe the regime classification for that bar.

### Required columns

| Column | Type | Description |
|---|---|---|
| `timestamp` | ISO-8601 UTC string (see §7) | Bar end time |
| `symbol` | string (see §8) | Instrument the classification applies to |
| `state` | integer ≥ 0 | Raw HMM state index from the model |
| `regime_label` | string (see §9) | Human-readable regime label |
| `schema_version` | integer | Schema version this row was produced against (see §10) |

### Optional columns

These are reserved names. If a producer chooses to emit them, they must conform to the types below. Consumers must tolerate their absence.

| Column | Type | Description |
|---|---|---|
| `confidence` | float in `[0.0, 1.0]` (see §11) | Producer's confidence in the classification |
| `state_probabilities` | JSON-encoded array of floats summing to ~1.0 | Posterior probability per state, length = `n_states` |
| `n_states` | integer ≥ 2 | Number of states in the model that produced this row |
| `direction` | enum string | `Bullish` / `Bearish` / `Sideways` (parsed from `regime_label`) |
| `vol_level` | enum string | `Low-Vol` / `Moderate-Vol` / `High-Vol` (parsed from `regime_label`) |
| `model_id` | string | Identifier for the trained model that produced the row (e.g., `gaussian-hmm-3s-v1`) |
| `run_id` | string | UUID or timestamped run identifier; matches a `run_config.json` snapshot |

Producers must **not** invent new columns outside this list at schema version 1. New optional columns require a schema version bump (§10).

### Example (illustrative — do not check into the repo)

```csv
timestamp,symbol,state,regime_label,schema_version,confidence
2026-05-18T00:00:00Z,BTC-USD,0,Bullish / Low-Vol,1,0.82
2026-05-18T01:00:00Z,BTC-USD,0,Bullish / Low-Vol,1,0.79
2026-05-18T02:00:00Z,BTC-USD,2,Sideways / Moderate-Vol,1,0.61
```

## 6b. Optional JSONL schema — `hmm_regimes.jsonl`

JSONL is offered as an **optional** alternate format for producers that want one row per record without the quoting pitfalls of CSV for nested fields (notably `state_probabilities`).

- One JSON object per line, UTF-8, newline-delimited (`\n`).
- Same required and optional fields as the CSV schema, with the same types and the same semantics.
- File extension `.jsonl`.
- Same filename convention as §5, replacing `.csv` with `.jsonl`.

The Level 1 adapter is required to handle CSV. JSONL support is **optional** for both producer and consumer.

Illustrative single line:

```json
{"timestamp":"2026-05-18T00:00:00Z","symbol":"BTC-USD","state":0,"regime_label":"Bullish / Low-Vol","schema_version":1,"confidence":0.82,"state_probabilities":[0.82,0.10,0.08]}
```

## 7. Date / time format

- Wire format on disk: **ISO-8601 in UTC with the `Z` suffix**, e.g., `2026-05-18T00:00:00Z`.
- Producers must emit UTC. Local timezones are not permitted.
- Bar end time is the convention. A row labeled `2026-05-18T00:00:00Z` covers the bar that *ends* at that timestamp.
- For daily bars where intra-day precision is not meaningful, producers may emit `2026-05-18T00:00:00Z` (midnight UTC) — the time component is required for consistency with intraday cases.
- Consumers must parse with a strict UTC parser; "naive" datetimes (no timezone) are a schema violation.

## 8. Symbol format

- Single string, no spaces.
- Crypto: `<BASE>-<QUOTE>` with uppercase letters and digits, e.g., `BTC-USD`, `ETH-USD`, `SOL-USDT`.
- Equity: ticker as uppercase letters, e.g., `AAPL`, `TSLA`. No exchange suffix unless required to disambiguate.
- FX: `<BASE>-<QUOTE>` with uppercase 3-letter ISO codes, e.g., `EUR-USD`. (Note: ALGHREST's existing dashboard uses `EUR/USD`; this contract uses `-` to avoid the slash colliding with filename rules. Consumers must convert at the boundary, not at the file level.)
- One symbol per row. A file may contain rows for multiple symbols but the same `(timestamp, symbol)` pair must be unique.

## 9. Regime labels

Regime labels are human-readable strings of the form:

```text
<Direction> / <Vol-Level>
```

with the following allowed values (matching HMM_Trading's current `assign_regime_labels` behavior):

- **Direction**: `Bullish`, `Bearish`, `Sideways`
- **Vol-Level**: `Low-Vol`, `Moderate-Vol`, `High-Vol`

Full label set (9 values):

```text
Bullish / Low-Vol         Bullish / Moderate-Vol         Bullish / High-Vol
Bearish / Low-Vol         Bearish / Moderate-Vol         Bearish / High-Vol
Sideways / Low-Vol        Sideways / Moderate-Vol        Sideways / High-Vol
```

Spacing around the `/` separator is significant: exactly one space on each side. Consumers should compare against the canonical strings, not lowercase them or strip whitespace defensively.

If HMM_Trading later adds new direction or volatility categories, that is a schema change and requires a `schema_version` bump.

## 10. Versioning strategy

The `schema_version` column is **mandatory** and is the primary versioning mechanism.

- Schema version 1 is defined by this document.
- Any breaking change (renamed column, changed type, new required column, removed required column, expanded enum) increments `schema_version` to the next integer.
- Producers tag every row with the version they were built against.
- Consumers declare a supported version range and refuse to parse rows outside it (fail closed; do not auto-coerce).

A `SCHEMA.md` file inside `alghrest-test/HMM_Trading/outputs/` may be added later to record the producer's current version explicitly. It is not required for Level 1.

Additive changes that introduce only **new optional columns** do not require a version bump, provided the column names are drawn from the reserved list in §6.

## 11. Confidence score format

When present, `confidence` is:

- A float in the closed interval `[0.0, 1.0]`.
- 0.0 = no confidence; 1.0 = certainty.
- Producer-defined semantics — typically the posterior probability of the assigned state from the Viterbi or forward-backward output.
- Optional. Absence of the column does not imply zero confidence; it means the producer did not export it.

Consumers must treat `confidence` as advisory unless they pin their behavior to a specific producer version.

## 12. Validation rules

A Level 1 adapter must reject a file as invalid if **any** of the following is true:

1. The file is missing at the configured path.
2. The header row is missing or does not contain all five required column names from §6.
3. `schema_version` is missing, empty, or outside the consumer's supported range.
4. Any `timestamp` cannot be parsed as a UTC ISO-8601 datetime.
5. Any `state` value is not a non-negative integer.
6. Any `regime_label` is not one of the nine canonical strings in §9 (for schema version 1).
7. Any `(timestamp, symbol)` pair is duplicated within the file.
8. The file is older than the configured staleness threshold (see §13).
9. The file's byte size exceeds a configured maximum (default suggested: 100 MB, to bound memory and DoS surface).
10. For JSONL: any line is not valid JSON, or any object is missing a required field.

Validation results should be structured: which rule failed, on which row, with what value. Consumers should log the first N failures (e.g., 10) and stop, rather than scanning the entire file.

## 13. Error handling rules

Failure modes the Level 1 adapter must define and surface:

| Condition | Recommended consumer behavior |
|---|---|
| File missing | Skip the regime signal for this cycle. Emit a metric/log. Do not raise. |
| File present but stale (older than threshold) | Skip the regime signal. Emit a separate "stale" metric distinct from "missing". Default threshold: 24h for daily bars, 2h for intraday. |
| Schema version unsupported | Refuse to consume. Raise a structured error. Do not attempt coercion. |
| Schema valid but row-level validation fails | Skip the bad row, log it, continue with valid rows. If more than a configured fraction of rows are bad (default: 5%), treat the whole file as invalid. |
| File larger than configured cap | Refuse to read. Raise a structured error. |
| Read I/O error | Treat as "file missing" for this cycle. Retry on the next cycle, do not retry within the same cycle. |
| Atomic-write violation (partial file) | The producer's atomic-write rule (§3) should prevent this. If the consumer encounters a parse error on the last row only, retry once after a short wait before declaring failure. |

The consumer must never silently substitute a fallback regime label. Missing or stale data is a distinct state from "Sideways"; collapsing them hides producer health from monitoring.

## 14. Security / safety notes

- **No secrets in producer output.** `hmm_regimes.csv`, `run_config.json`, and all other artifacts are research outputs. They must not contain API keys, exchange credentials, wallet keys, or PII.
- **No untrusted file paths.** The consumer reads from a configured directory only. It must not follow symbolic links out of that directory, and it must not honor pathnames embedded inside the CSV.
- **No code execution.** The CSV/JSONL formats are data-only. The consumer must never `eval`, `exec`, or import based on file contents. JSON parsing must use a safe parser.
- **Bounded reads.** The byte-size cap in §12 prevents a runaway producer (or a malicious file dropped in the directory) from exhausting memory.
- **File ownership.** On multi-user systems, the consumer should verify the file is owned by the expected user/service before reading. Out of scope for Level 1 but worth recording.
- **Disclaimer surface.** Regime labels are research signals from an educational subproject. ALGHREST must not route them directly into order placement without a human-supervised intermediate layer.

## 15. Future implementation phases

This contract is the design artifact for Level 1 of the integration roadmap. See `docs/integration-roadmap.md` for the full staging.

Once the contract is approved:

1. **Producer alignment (HMM_Trading).** Update `src/pipeline/runner.py` and `src/reporting/exporter.py` to emit `timestamp`, `symbol`, `state`, `regime_label`, and `schema_version` columns explicitly, with atomic writes. Add `confidence` and other optional columns as the model exposes them. *Out of scope for Phase C.*
2. **Consumer adapter (ALGHREST).** Implement a read-only file adapter, likely under `connectors/data_providers/`, with schema validation, staleness checks, and structured errors. *Out of scope for Phase C.*
3. **Test fixtures.** Add a small, checked-in CSV fixture under `tests/unit/fixtures/` so the consumer adapter can be tested without HMM_Trading installed.
4. **End-to-end smoke.** A nightly job (or manual procedure) that runs HMM_Trading, then runs the ALGHREST adapter against the produced file, then publishes a "regime adapter healthy" metric.
5. **Schema version 2.** Tracked in this document when the first breaking change is proposed.

Each step ships in its own branch and PR. The producer side does not block on the consumer side, and vice versa, because the contract is the only thing they share.

## 16. Related documents

- `docs/monorepo-workflow.md` — repo layout and the rules that keep ALGHREST and HMM_Trading independent.
- `docs/integration-roadmap.md` — the three-level integration plan; this contract is the design for Level 1.
- `alghrest-test/HMM_Trading/README.md` — producer-side overview.
- `alghrest-test/HMM_Trading/docs/architecture.md` — producer-side internal architecture (the §9 "Integration Boundary" subsection mirrors this contract from the HMM side).
- `README.md` — top-level ALGHREST overview with cross-links to this document.
