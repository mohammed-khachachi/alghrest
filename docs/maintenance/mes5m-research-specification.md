# MES 5m frozen research specification

This preserves the protocol approved in the original Phase 6A conversation
`01a1506b-8872-76f1-ba51-93917b7c9f2d` (proposal and subsequent explicit approval).
The original proposed rules below are the frozen implementation contract. Source
references retain their original context and were not refreshed during closure.
No parameter selection or historical strategy-performance calculation occurred.

The development-only command is:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. .venv/bin/python -B scripts/qualify_mes5m.py --partition development
```

The pinned JSON is `research/mes5m/mes5m-h26-v1.json`. The command verifies its
frozen values and the preserved source digest, filters authorized development
rows before numeric parsing, and returns structural counts with `PARTIAL` data
status. Exit zero means the structural check completed; it never means trading
qualification. Validation/holdout inputs, historical signals, fills, performance,
account simulation and execution remain unauthorized. The separate signal module
accepts synthetic windows only. It produces plans, never fills or returns.

The original partial implementation's missing JSON and documentation are restored;
the inherited Decimal typing error is corrected without changing the value.
Current tests and verification are recorded under
`artifacts/earn2trade-tcp25-readiness/mes5m-research-spec-v1/`.
The original ten-path/twelve-artifact allowance remains the boundary.

## Original approved protocol

**GO for implementing a bounded MES 5m specification, data preflight and synthetic signal tests. NO-GO for historical performance runs, holdout evaluation or TCP25 qualification at this checkpoint.**

MES 5m remains the provisional candidate. No stronger existing evidence establishes another choice. The design below is proposed for approval; no files were changed.

**Research identity and compatibility**

Proposed experiment: `mes5m-range-volume-h26-v1`.

Reuse:

- The existing [VolumeBreakoutKernel](</home/xsabo/Projects/MY project/alghrest-main/src/core/strategy_signals.py>) for deterministic range/volume signals.
- Existing candle, Decimal, timestamp and contract models.
- The existing [FirstRate 5m normalization rules](</home/xsabo/Projects/MY project/alghrest-main/scripts/advisory_firstrate_intake.py:117>) on partition-filtered inputs.

Use a separate versioned research specification. The existing [daily StrategyDefinition](</home/xsabo/Projects/MY project/alghrest-main/src/core/advisory/strategies.py:68>), daily futures runner, SQLite registry, personal worksheet, APIs and frontend remain unchanged. Their historical schemas and source hashes retain their meaning.

The Phase 4/5 evidence supports aggregation mechanics and a provisional candidate. It does not establish complete data, actual execution costs, an untouched performance holdout or firm eligibility.

**Dataset admissibility matrix**

| Input or period | Proposed treatment | Qualification |
|---|---|---|
| Preserved `MES_H26_1min.csv` | Sole price/volume source; pin its full SHA-256 from the private manifest | Local identity verified; exchange completeness unresolved |
| Before 2025-12-15 | Exclude from this experiment | Deferred-contract history; no active-contract representation assumed |
| 2025-12-15 through 2026-03-13 | Candidate research envelope, subject to partitions and exclusions below | Conditional admissibility |
| 2026-03-16 onward | Exclude | Beyond the selected customary lead-contract period |
| Continuous and daily files | Exclude | No continuous-series reconstruction or settlement-price substitution |
| MNQ and other contracts/timeframes | Exclude | Require separate experiment identities |
| Unknown calendar, missing or invalid input | Abstain or mark incomplete as specified below | Never silently convert to usable evidence |

CME lists customary equity-index roll dates of **15 December 2025** and **16 March 2026**. These support the chosen research convention; they do not prove actual liquidity dominance or impose a firm rule. [CME roll calendar](https://www.cmegroup.com/trading/equity-index/rolldates.html)

The source remains the preserved file documented in the [provenance manifest](</home/xsabo/Projects/MY project/alghrest-main/data/private/firstrate/2026-10-09-free-samples/source-manifest.json>). No replacement or corrected download is proposed.

**Gap, calendar and aggregation policy**

The fixed personal research window remains **07:00–14:00 UTC**. Use UTC for event ordering, `America/New_York` for source timestamps, and `America/Chicago` for account-day accounting.

Proposed conservative **personal exclusions**, without claiming these dates were entirely exchange-closed:

- 24–26 December 2025.
- 31 December 2025–2 January 2026.
- 19–20 January 2026.
- 16–17 February 2026.

Applicable exchange exceptions still require dated support. Unknown calendar applicability remains visible; these exclusions do not manufacture a complete historical calendar. CME itself distinguishes regular schedules from holiday exceptions. [CME trading hours](https://www.cmegroup.com/trading-hours.html)

| Interval condition | Treatment |
|---|---|
| Supported scheduled closure | `SCHEDULED_CLOSED`; no expected bars |
| Explicit experiment exclusion | `PERSONAL_EXCLUSION`; retain its reason |
| Absent minute during a candidate-open interval | `UNCLASSIFIED_MISSING`; no zero-volume or flat-price insertion |
| Duplicate, malformed, off-tick or ambiguous timestamp | Reject affected input; preserve diagnostics |
| Missing interval while flat | Cancel unsubmitted intent, reset warmup and record abstention |
| Missing interval during simulated exposure | Mark the position/path `INCOMPLETE`; halt that path pending reconciliation |
| Missing exit price | Do not invent liquidation at the last known close |

**Do not select trading days using their future completeness.** Full-day completeness is an audit statistic. At decision time, only information available by that time may control entry.

Aggregation is fixed:

- UTC buckets `[t, t+5 minutes)`, aligned to five-minute boundaries.
- Exactly five consecutive native minute starts.
- First open, maximum high, minimum low, last close, summed volume.
- Availability only at the true interval end.
- Preserve `available_at` separately from any inclusive candle-close representation.
- No sorting that conceals source disorder, forward filling, interpolation or crossing a session/contract boundary.

Source acquisition time and historical event time remain separate. Historical bar publication latency is unavailable; modeled availability is an assumption.

**Single hypothesis and frozen parameters**

Hypothesis: **a volume-confirmed close beyond the previous hour’s range exhibits enough short-term continuation to produce positive net outcomes under predefined costs.**

This is untested. Parameters are proposed conventions, selected without performance optimization.

| Component | Frozen rule |
|---|---|
| Instrument/timeframe | MES H26, 5m |
| Range | Previous **12** complete consecutive bars; exclude current signal bar |
| Volume baseline | Arithmetic mean volume of those same 12 bars |
| Confirmation | Current volume **≥1.5×** baseline; nonpositive baseline means abstain |
| Long | Current close strictly above previous range high |
| Short | Current close strictly below previous range low |
| Warmup | **13 consecutive complete 5m bars** including the signal bar |
| Daily reset | Clear indicators, pending intent and warmup at each 07:00 UTC window start |
| Gap reset | Clear warmup after any missing/invalid interval; require 13 new consecutive bars |
| Decision times | Completed-bar boundaries **08:05 ≤ time <12:55 UTC** |
| Entry timing | Hypothetical market entry at the native minute open **60 seconds after the decision** |
| Long stop | Signal-bar low minus one MES tick |
| Short stop | Signal-bar high plus one MES tick |
| Target | Signal close ± **2×** the signal-close-to-stop distance |
| Trailing/averaging | None |
| Time exit | Earlier of entry time + **60 minutes** or **13:55 UTC** |
| Exposure | One simulated MES contract maximum; no pyramiding or concurrent positions |
| Frequency | Maximum **two executed entries per UTC window** |
| Loss pause | Pause after **five consecutive losing trades**; no automatic historical resume |

A pending entry is not retrospectively canceled because the next opening price is unfavorable. Missing required pre-entry information causes abstention. A gap through a protective level after entry must be represented as an immediate adverse exit, not a canceled losing trade.

A missing price at the scheduled entry cannot be treated as proof that no fill occurred.

**Position sizing and personal stopping**

Use hypothetical research account state, with no connection to the personal worksheet or an assigned account.

Proposed planned-risk budget:

```text
B = min(
  $100,
  1% of reconciled shadow equity,
  $200 + current-day net PnL,
  $550 + current-day net PnL - $100,
  shadow equity - shadow drawdown floor - $100
)
```

All PnL includes modeled costs. Nonpositive budget means abstain.

Let `D` be the signal-close-to-stop distance in MES points. One contract is permitted in the research plan only when:

```text
5 × D + $14 severe-scenario costs + $5 gap reserve <= B
```

Otherwise research quantity is zero. Gap losses can exceed this planned budget; the simulation must report that rather than cap losses artificially.

The **$100 trade budget, $200 daily stop and reserves are personal research controls**. They are not Earn2Trade requirements. Ten Micros remains the separate aggregate personal ceiling; this experiment uses the stricter one-Micro research limit. The exclusive one-Mini OR ten-Micro policy remains intact, with Mini support deferred.

**Cost and fill assumptions matrix**

Current official text gives a general Micro commission example of **$0.82–$1.20 per side**, but exact assigned MES charges remain unknown. [Earn2Trade commissions](https://help.earn2trade.com/en/articles/2425493-what-is-the-commission-on-earn2trade-evaluations)

| Scenario | Assumed commission/side | Assumed adverse ticks/side | Round-trip modeled cost, one MES |
|---|---:|---:|---:|
| Baseline hypothesis | $1.20 | 1 | $4.90 |
| Adverse hypothesis | $1.50 | 2 | $8.00 |
| Severe sensitivity | $2.00 | 4 | $14.00 |

**All three are assumptions, not observed costs or guaranteed bounds.** Until fee components are confirmed, commission represents a hypothetical total charge. Do not add exchange/platform fees again without establishing whether they are already included.

Future fill requirements:

- Use native **1m** observations beneath 5m decisions.
- Apply adverse slippage on entry and market exits.
- Model the target as a market-exit trigger, not a guaranteed limit fill.
- Gap-through stops use the worse available opening price before adverse slippage.
- Do not credit favorable target-gap improvement.
- If stop and target occur within the same minute, use **stop first** and flag ambiguity.
- Retain ambiguity counts and sensitivity results.
- Do not infer Bid/Ask, queue position, tick sequence or achievable latency from OHLCV.

**Chronological validation protocol**

All dates are inclusive; daily data use the fixed UTC window.

| Partition | Dates | Calendar-only maximum after proposed exclusions |
|---|---|---:|
| Development | 2025-12-15–2026-01-23 | 22 dates |
| Embargo | 2026-01-24–2026-01-26 | No observations used |
| Validation | 2026-01-27–2026-02-13 | 14 dates |
| Embargo | 2026-02-14–2026-02-17 | No observations used |
| Performance-sealed holdout | 2026-02-18–2026-03-13 | 18 dates |

These are calendar upper bounds, not newly inspected holdout coverage.

Protocol:

1. Freeze specification, source identities and partitions before historical performance execution.
2. Development checks implementation and produces descriptive results; no parameter search.
3. Validation uses unchanged rules. Failure cannot trigger silent tuning.
4. Holdout execution requires a separate approval after implementation and validation review.
5. Reset indicators, positions and hypothetical account state between partitions. Report each separately; do not splice account paths.
6. Any strategy, date-selection or cost-selection change creates a new experiment identity and records its ancestry.
7. Record failures, abstentions and censored exposure. Never discard them to improve results.

The proposed holdout was previously inspected for structural quality and aggregate coverage. It can be **prospectively sealed against strategy-performance access**; it cannot be certified as historically unseen.

The fixed UTC window also changes its relationship to US market hours after March DST. Record both timezone regimes without changing the window retrospectively.

**Minimum evidence requirements**

For a **preliminary descriptive experiment**, predeclare:

- At least **40 admissible dates spanning eight calendar weeks**.
- At least **15 development, 10 validation and 10 holdout dates**.
- At least **30 closed trades overall**, including 10/5/10 respectively.
- At least five long and five short outcomes.
- At least five admissible dates under each Eastern UTC offset.
- At least five outcomes in each causal range condition: previous six bars’ total range greater than the preceding six, versus less than or equal.
- No unresolved open position for a partition-level net-performance conclusion.

These are screening floors, not a statistical power calculation. Missing a floor means **INSUFFICIENT EVIDENCE**, without lowering it after seeing results.

The primary descriptive statistic is mean net USD per closed trade, reported with all denominators and incomplete paths. Nonpositive validation or holdout expectancy under baseline costs contradicts the proposed positive-continuation hypothesis. Positive results remain preliminary; adverse-cost results must accompany them.

Any later uncertainty analysis must respect session dependence. Trade-level IID intervals and overlapping evaluation starts are not acceptable substitutes.

Current H26 data cannot establish broad regime robustness, rollover behavior or passing probability. Larger confirmatory work would require separately justified sample size, multiple dated contracts and substantially wider market coverage.

**Account-level simulation requirements**

A later, separately scoped engine must:

- Apply $25,000 / $1,750 / $550 / $1,500 as an explicitly **hypothetical application of public TCP25 terms**.
- Reconcile cash, fees, open equity, session baselines and EOD floor updates.
- Preserve Chicago DST/session rules and threshold equality behavior.
- Track personal stops separately from firm-rule breaches.
- Report breach-time intervals when tick timing is unavailable.
- Keep progression, order-state, assigned-margin and threshold synchronization unknown where unsupported.
- Never backdate rule confirmation or change `known_at` to make historical evidence appear qualified.
- Keep firm completion **BLOCKED/UNKNOWN** wherever required evidence is missing.

No account-level PASS classification is authorized by this preliminary specification.

**Experiment registry schema**

Proposed immutable schemas:

- `mes5m-research-spec-v1`
- `mes5m-data-manifest-v1`
- `mes5m-experiment-event-v1`
- `mes5m-qualification-v1`

Registry records contain experiment/parent IDs, hypothesis and parameter identities, source/configuration hashes, partition boundaries, calendar version, cost scenarios, access authorizations, tested variants, defects, decisions and limitations.

Each event has an event hash and preceding-event hash. Historical packets remain immutable; subsequent packets reference them. Financial values use Decimal strings, timestamps include UTC, unknown evidence remains explicit, and extra fields are rejected.

Holdout custody records must disclose prior quality inspection and uncertain historical performance access. Engineering success never changes permission fields or authorizes a run.

**Exact proposed implementation allowlist**

All ten paths are new; none currently exists.

| Path | Purpose |
|---|---|
| `src/backtesting/mes5m_spec.py` | Frozen specification, partition, cost and registry models |
| `src/backtesting/mes5m_data.py` | Partition-aware data preparation and aggregation checks |
| `src/backtesting/mes5m_signals.py` | Guarded kernel wrapper, proposed levels, sizing and event schedule |
| `scripts/qualify_mes5m.py` | Offline development-partition preflight; no performance runner |
| `tests/unit/test_mes5m_spec.py` | Schema, identity, permission and partition boundaries |
| `tests/unit/test_mes5m_data.py` | Aggregation, gaps, timestamps and partition isolation |
| `tests/unit/test_mes5m_signals.py` | Synthetic signal, risk and scheduling cases |
| `tests/unit/test_mes5m_qualification_cli.py` | CLI containment, output and holdout-denial tests |
| `docs/maintenance/mes5m-research-specification.md` | Approved protocol and limitations |
| `research/mes5m/mes5m-h26-v1.json` | Research-only frozen configuration |

The existing intake validates its whole supplied payload. Therefore the new data boundary must isolate the authorized partition **before OHLCV parsing and normalization**. Whole-file checksum verification is allowed; holdout prices must not enter feature calculations or ordinary diagnostics.

Twelve new evidence outputs, only under:

`artifacts/earn2trade-tcp25-readiness/mes5m-research-spec-v1/`

```text
specification.json
admissibility.json
gap-calendar-policy.json
cost-fill-assumptions.json
partition-seal.json
registry-schema.json
registry.jsonl
tests.xml
checks.log
verification.json
preservation.json
source-manifest.json
```

No historical file updates or before-archives are needed because this scope modifies no existing files.

**Acceptance and review checkpoint**

Implementation acceptance requires:

- Exact approved parameters and schemas; all permissions remain closed.
- Synthetic tests for strict breakout comparisons, volume equality, warmup/reset, future-bar rejection, entry delay, sizing boundaries and missing information.
- Aggregation tests at completion minus one microsecond, exact completion and after completion; duplicates, DST ambiguity, gaps and volume conservation.
- Holdout access denied through the normal CLI and data interfaces.
- Deterministic repeated preflight outputs, separate from operational timestamps.
- Existing FirstRate, strategy-signal and futures evidence/validation regressions.
- Ruff, Black/isort checks, strict MyPy for new source, architecture checks and preservation verification.
- No historical strategy performance, fill simulation or account evaluation run in this increment.

The current dataset may support a limited preliminary experiment after remediation, but the proposed calendar permits **at most 54 dates**, before further exclusions and missing data. Whether it meets trade-count and regime floors remains unknown.

The monitored **5,633-file inventory remained unchanged** during this planning pass.

```text
firm_eligibility = BLOCKED
qualified_contracts = 0
passing_probability = UNKNOWN
execution_permissions = false
```
