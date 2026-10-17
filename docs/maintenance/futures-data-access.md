# Futures data intake and provider access

## Preserved MES/MNQ data-quality review — 2026-10-11

The user approved exactly eleven files: two document updates and nine new
evidence files in
[`futures-data-quality-review-v1/`](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/).
Both documents' previous bytes are archived before edits. Source, configuration,
tests, policy, permission restrictions and private data remain unchanged. The
broader readiness Goal remains **PAUSED**; this increment does not complete it.

This preserves the **2026-10-10** read-only findings, with fresh local identity,
archive, replay and containment checks during preservation. Public text and the
provider mailbox were not re-read on October 11. The earlier no-reply observation
at October 10 01:48:34 UTC remains valid at its original checkpoint; the subsequent
FirstRateData reply received at **02:38:44 UTC** states OHLCV only, no historical
Bid/Ask or event-level trades for these products, and corrections overwrite
archives without version/changelog manifests. No historical dated-contract/outage
inventory was supplied. Its affirmative metadata wording conflicts with the
[official FAQ](https://firstratedata.com/about/FAQ) inspected October 10; this is
**UNRESOLVED**, not an inferred typo or a qualified metadata dataset.

| Observed historical sample | Native minute rows | Complete 5-minute buckets in weekday 07:00–14:00 UTC | Absent candidate minutes in that window |
| --- | ---: | ---: | ---: |
| MESH26 | 128,848 | 6,086 | 98,961 |
| MNQH26 | 142,658 | 6,554 | 87,401 |

These counts concern genuine historical provider samples, not synthetic prices.
Each recorded row passes all twelve structural/numeric/time checks. The weekday
window is a disclosed audit assumption, not a historical exchange holiday
calendar. Missing minutes are **UNCLASSIFIED**; no-trade minutes, filtering and
feed loss are not distinguished. Do not fill gaps or infer a loss percentage.
Incomplete five-minute buckets are excluded; only completed candles are used.
Both files end at March 20, 2026 13:30 UTC exclusive close, so they do not provide
current data or qualified multiyear active-contract history.

| Readiness item | Status in this review | Remaining acceptance evidence |
| --- | --- | --- |
| Preserved snapshot identity and recorded-row validity | VERIFIED for retained samples | Matching ZIP/CSV/receipt identities and repeatable full-file checks |
| Closed-bar aggregation and original-cut replay | VERIFIED mechanics | Exact original snapshot/count/health comparison; no gap filling |
| Active-contract metadata and calendar | PARTIAL | Inspectable dated metadata resolving the provider/FAQ conflict and historical sessions |
| Coverage and missing-minute classification | MISSING | Authoritative no-trade/outage and coverage evidence |
| Vendor correction/as-of history | MISSING | Version evidence, or separately reviewed limitations of immutable local capture |
| Bid/Ask and event-level execution | BLOCKED for this product | Another qualified source or a separately reviewed conservative method |
| Assigned MES/MNQ commissions, fees and slippage | MISSING | Applicable dated cost schedule and a validated execution-cost method |
| Untouched OOS edge and complete forward evaluations | MISSING in this review | Qualified history, frozen methodology, horizon, validated prospective rules and reproducible forward evidence |

The [report](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/read-only-review.md),
[methodology notebook](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/methodology.ipynb),
[source manifest](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/source-manifest.json)
and [verification receipt](../../artifacts/earn2trade-50k-readiness/futures-data-quality-review-v1/verification.json)
retain identities, commands, dates, warnings/limitations and exact scope.
The copied October 10 focused regression report records **64 passed, zero
failures/errors/skips, 0.72s**; no warnings appear in that log. It was not rerun
or combined with overlapping old test counts. Full suite, static checks, coverage
gate and strategy/evaluation simulations were not run in this documentation
increment. Existing futures/edge/walk artifacts are preserved by byte identity;
no new semantic verification of those envelopes is claimed here.

Local retention and internal research use follow the accepted
[FirstRateData license](https://firstratedata.com/about/license); interpreting
offline replay as internal research is an explicitly stated inference, not
authorization for live broker/exchange use. Raw data and correspondence stay
private. The archived October 10 audit initially used a mismatched JSON serializer;
only the audit was corrected to the original Pydantic serializer. No historical
hash, provenance or numerical outcome was patched.

Current htmlcov and .coverage identities are baselined for this increment. The
historical unbaselined htmlcov overwrite remains **UNKNOWN** and cannot be
retroactively certified. No .env edit, services, purchase, new agreement, download,
mail sending, tuning, new holdout access or failed-soak restart occurred.
No new PASS, FAIL or CENSORED simulation outcomes were generated.
**Official TCP50 positive allowances remain BLOCKED; passing probability UNKNOWN.**
The separate personal 20-Micro cap is not firm progression approval. Recheck public
rules and assigned terms at purchase. Stop for review before further work.

Reviewed: **2026-10-11** (preservation; data review: 2026-10-10). Target: **Earn2Trade TCP50 evaluation, not purchased**.
Public documents are prospective planning evidence. Recheck terms at purchase.

## Provider follow-up and preserved engineering evidence — 2026-10-10

The user approved the exact 17-file documentation/evidence checkpoint. The
previous bytes of this document and the readiness report are archived in
[`readiness-checkpoint-20261010/`](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/).
This increment preserves the already completed October 10 engineering reports
and user-provided Arabic rule screenshots; it does not qualify vendor data,
implement progression limits or rerun runtime tests. Source/configuration/tests
and the nine privately preserved sample/metadata files remain unchanged.

The read-only mailbox inspection at **2026-10-10 01:48:34 UTC** found no incoming
clarification in the two authorized provider/firm inquiry threads or bounded
sender/date search. One earlier firm promotional message is not a response.
This is a limited mailbox observation, not proof of absence on all channels.
The inquiries have already been sent; no duplicate message or raw correspondence
is published. Private mailbox identities and credentials stay out of evidence.

Contract activation/first trade, corrections/as-of versions, interpretation of
absent minutes, qualified Bid/Ask coverage and assigned MES/MNQ fees remain
unresolved. Keep the confirmed **07:00–14:00 UTC/GMT** research window and complete-
candle condition; neither is an enabled trading schedule or permission upgrade.
The free samples remain unqualified for a trading-edge or passing estimate.

The copied test reports retain their original date and bytes: 2,506 full-suite
passes with zero failures/skips, 562 warnings and 83.43% combined statement/branch
coverage against the unchanged 70% gate; the 544 focused passes overlap. They
prove engineering checks only. Poetry lock verification remains BLOCKED because
the CLI is absent. Current source/report identities and fresh public synthetic
replay are recorded in
[verification.json](../../artifacts/earn2trade-50k-readiness/readiness-checkpoint-20261010/verification.json).
The historical unbaselined htmlcov overwrite remains UNKNOWN.

No new data download, purchase, agreement acceptance, account activation,
provider/broker mutation, message, service or failed soak is authorized or
performed by this checkpoint. Stop for review before further implementation.
**TCP50 positive allowances remain BLOCKED; passing probability UNKNOWN.**
Earlier sections below preserve their original dated observations.

## CME metadata and confirmed UTC research window — 2026-10-10

The user approved exactly two document updates and eight new evidence files.
The previous bytes of this document and the readiness report are archived in
[`cme-metadata-review/`](../../artifacts/earn2trade-50k-readiness/cme-metadata-review/).
No converter, source, tests, configuration, policy or public interface changed.

The confirmed research window is **07:00–14:00 UTC/GMT fixed**. Count only complete
native minutes and five-consecutive-minute groups completing by 14:00. A group
starting at 14:00 is excluded. Monday–Friday is an audit assumption, not an enabled
runtime restriction. The audit retains the earlier Morocco-clock comparison but
uses the explicitly confirmed UTC scenario for conclusions. No strategy or live
schedule was enabled.

The existing catalog matches official outright specifications: MES tick size
0.25 points, $5 per point, $1.25 per tick; MNQ 0.25 points, $2 per point, $0.50 per
tick. [MES Chapter 353](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/IV/350/353/353.pdf),
[MNQ Chapter 361](https://www.cmegroup.com/content/dam/cmegroup/rulebook/CME/IV/350/361.pdf).
These are contract reference facts, not vendor-price authentication.

The live Micro FAQ still prints a 16:15–16:30 New York halt, but the applicable
[June 11, 2021 certification](https://www.cmegroup.com/market-regulation/rule-filings/2021/6/21-244R_1.pdf)
removed it effective trade date June 28, explicitly listing MES/MNQ. The captured
rows in that former interval are not scheduled-halt violations. Regular daily/
weekly closures and the dated January 9, 2025 exception are documented; complete
historical holiday/status matching intervals remain PARTIAL. Clearing, reporting
and settlement calendars are not substituted for Globex matching schedules.

The official expiration calendar confirms H26's March 20, 2026 date. The
rule-derived 13:30 UTC cutoff is compatible with both final 13:29 native minute
starts. Actual H26 activation/first trade and dated security-definition evidence
remain unverified; customary rolling is not an automatic vendor adjustment.

| Preserved H26 file | Native rows | Rows in confirmed UTC window | Complete five-minute groups | Candidate-open absent minutes in window |
| --- | ---: | ---: | ---: | ---: |
| MES | 128,848 | 37,509 | 6,086 | 98,961 |
| MNQ | 142,658 | 42,349 | 6,554 | 87,401 |

Only source-span interiors are counted. No zero filling, completeness percentage
or proven feed-loss label. Absence may reflect no trades, vendor filtering or
coverage limitations. Sparse deferred-contract history is not qualified active-
contract history. Corrections/as-of versions, coverage, Bid/Ask and exact assigned
costs remain unresolved; no current inbox or provider reply was inspected here.

Original ZIP/CSV hashes, acquisition receipts, ZIP CRC and exact member equality
are verified again. The saved notebook exposes the deterministic timestamp method
and bounded results without raw prices/volumes or personal input paths. Fresh
public run/edge/walk and separate legacy TCP25 PASS/FAIL/CENSORED replay use strict
source checks and exact comparisons. Old mismatched envelopes are rejected;
historical provenance is not patched. Details, commands, execution limitations
and containment are in
[verification.json](../../artifacts/earn2trade-50k-readiness/cme-metadata-review/verification.json)
and [source-manifest.json](../../artifacts/earn2trade-50k-readiness/cme-metadata-review/source-manifest.json).

No full test/static/coverage certification is claimed for documentation-only
work. Existing coverage outputs are preserved; the historical unbaselined
htmlcov overwrite remains UNKNOWN. No purchase, provider/broker mutation, services,
failed soak, new holdout access or trading execution. **TCP50 positive allowances
BLOCKED; passing probability UNKNOWN.** Stop for review before expanding scope.
Earlier sections below retain their original dated claims.

## Private sample preservation and independent review — 2026-10-09

The user approved the separately listed 19-file preservation/documentation scope.
The prior converter's two-axis review found no actionable Standards violation or
blocking Spec defect. Source/tests/configuration and core interfaces are unchanged.
The original version of this document is archived byte-for-byte in
[futures-data-access-before.md](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/futures-data-access-before.md).

Nine private sample/metadata files now reside in
`data/private/firstrate/2026-10-09-free-samples/`, covered by the existing `/data/`
ignore; the directory is 0700 and files 0600. Both original ZIPs and H26 minute CSVs
were copied with exact SHA256/bytes and reopened ZIP/member/CRC checks. Original
license/FAQ, retrieval and consent evidence are preserved, with a new private
source manifest; temporary originals remain untouched. Local copies are not an
off-machine backup. Keep original acquisition time, not the new copy time, as the
receipt input for reproducibility. Re-parsing at the original cut exactly matches
the previous snapshot/counts/health. Outputs remain UNHEALTHY/ABSTAIN, with no
source-quality or broker/firm permission upgrade.

The current [review and preservation receipt](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/verification.json)
records 64 fresh converter regression passes and new request-scoped public replay.
It does not claim another full coverage run. Initial full-suite evidence remains
unchanged; the historical unbaselined coverage overwrite remains UNKNOWN.
Exact TCP50 progression, assigned MES/MNQ costs, quote/fill/mark evidence and
qualified OOS/forward evaluations still block readiness. Unsent questions are in
[the rule/cost research note](../../artifacts/earn2trade-50k-readiness/firstrate-review-and-preservation/tcp50-rule-cost-research.md).
No support message, services or purchases. Stop for review; TCP50 allowance BLOCKED
and passing probability UNKNOWN.

## FirstRateData individual-contract CSV intake — 2026-10-09

This section records the original source increment; the latest preservation update is above.

The user accepted the [FirstRateData license](https://firstratedata.com/about/license)
and authorized two free sample downloads, then explicitly approved this 15-file
conversion/test/documentation increment. The license text describes local copies,
private use and derivative models; the converter does not authenticate permission
or set a licensed/READY flag. No purchase, subscription, provider login or broker
connection occurred. Provider attribution: [FirstRate Data](https://firstratedata.com).

`scripts/advisory_firstrate_intake.py` reads an existing individual-contract minute
CSV with exactly six columns: Eastern bar-start timestamp, open, high, low, close,
volume. The [provider FAQ](https://firstratedata.com/about/FAQ) defines Eastern/DST
starts and omitted no-trade minutes. Input names must explicitly identify MES/MNQ,
a quarterly expiry and a two/four-digit year: `MES_H26_1min.csv`, for example.
Names/clock/timezone are declarations, not verified listing/expiry metadata.
Renaming another series cannot authenticate it. Continuous, daily/settlement and
other-resolution names are rejected. Daily settlements are not intraday closes.

The entire input is checked before selection: UTF-8/optional BOM, exact timestamp
format, unique chronological UTC minutes, valid Eastern DST round trips, finite
Decimal prices, positive prices/on-tick OHLC, nonnegative integral contract volume,
completion by the reported receipt, and schema/limits. Ambiguous/nonexistent local
times are rejected. Limits are 30,000,000 bytes and 500,000 rows, with at most 500
output candles. Oversized/truncated inputs have no claimed whole-file hash.

Compose only buckets with five consecutive native minutes. Require the true
exclusive five-minute boundary to have elapsed at the explicit query cut before
serializing the existing inclusive close (boundary minus one microsecond).
Never fill gaps or insert no-trade bars. Counts disclose all observed/incomplete
buckets, their rows, native gaps, complete buckets after the cut and eligible
buckets excluded by the requested bar limit. Source hashes and first/last native
UTC starts remain visible. The selected output reuses `MarketDataQuery`, `Candle`,
`MarketSnapshot`, `bounded_snapshot` and `inspect_snapshot` without changing them.

Example for an already permitted local file; obtain the real receipt timestamp
from its acquisition record and supply an explicit research cut:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -B \
  -m scripts.advisory_firstrate_intake /tmp/private/MNQ_H26_1min.csv \
  --instrument MNQ --contract MNQH26 --source-timezone America/New_York \
  --fetched-at <actual-UTC-receipt> --as-of <explicit-UTC-cut> --max-bars 500
```

Do not paste the angle-bracket placeholders literally. Preserve the true receipt
clock even for an earlier cut: `future_capture` must not be hidden by backdating.
There is no source-quality, heartbeat, quote, cost, calendar or permission invention.
Structurally valid conversions remain UNKNOWN/UNHEALTHY with missing source evidence.
The CLI emits JSON on stdout and exits **2**; it never signals trading readiness.
Always retains `ABSTAIN`, false trade/execution permission, BLOCKED TCP50 allowance
and UNKNOWN passing probability. Outputs include private derived price/volume
candles, so keep CLI output private. Public receipts contain counts/hashes only.

The authorized samples contain **128,848 MES H26** and **142,658 MNQ H26** minute
rows. This importer composes **20,778 / 22,705** complete five-minute buckets and
reports **12,137 / 12,586** incomplete buckets; only the latest requested 500 are
emitted. Both remain UNHEALTHY (old bars/receipt, unresolved gaps, missing quality).
The archived ZIPs/CSVs remain byte-identical in the approved temporary directory;
no raw provider data was copied into the repository. Temporary data can be cleaned
by the host; a durable private destination requires a separate decision.

This is data-intake engineering. It enables no intraday strategy: the existing
breakout research helper currently supports daily candles. It does not establish
complete exchange history, executable bid/ask fills, costs, OOS/holdout edge or
TCP50 success. Review evidence and exact checks are recorded in
[`firstrate-intake/`](../../artifacts/earn2trade-50k-readiness/firstrate-intake/).
Stop for review before extending this scope.

## Massive offline adapter — 2026-10-09

`scripts/advisory_massive_intake.py` reads two existing JSON responses: aggregates
and a single point-in-time contract specification. It converts reported MES/MNQ
bars into the existing `MarketSnapshot` and calls the existing offline preflight.
It performs no download, credential/configuration read, database access or write.
Use only synthetic fixtures until the applicable recording/replay grant is
confirmed. No real provider rows or keys are included in this increment.

Native resolutions are `5min`, `15min`, `1hour` and `4hour`, matching existing
`5m`, `15m`, `1h` and `4h` intervals. `1min`, session and daily bars are rejected;
no minute aggregation, exchange-calendar inference or model expansion is added.
The three-minute access probe cannot be used as a five-minute snapshot.

Massive's one-digit year (for example `MNQZ6`) is resolved from matching expiry
metadata, never from the machine clock. The requested canonical identity must
match that expiry (`MNQZ26` or `MNQZ2026`). This bounded adapter accepts expiry
years 2000–2099 and requires outright, active XCME metadata, the expected root,
month, listing/date/expiry relationship and catalog tick size. These are checks
of reported input consistency, not independent authentication or firm permission.

Prices parse directly into Decimal; timestamps parse as integer nanoseconds.
Sub-microsecond starts are rejected instead of rounded to Python's microsecond
clock. Bars are sorted chronologically; duplicate/overlapping bars and unfinished
source intervals are rejected. Inclusive candle closes use the existing model's
last microsecond convention. Missing bars remain missing and are diagnosed by
the existing guard. A cut at the last microsecond before the source interval ends
is rejected; the complete interval must have elapsed. Gaps remain visible to
the guard without invented trading-session exceptions. Partial pages,
duplicate JSON keys, non-finite values, wrong identities and oversized inputs are
rejected. Each input is bounded to 500,000 bytes and 500 rows.

Example invocation for **permitted local files** (not a download command):

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -B \
  -m scripts.advisory_massive_intake /tmp/synthetic-bars.json /tmp/synthetic-contract.json \
  --instrument MNQ --contract MNQZ2026 --resolution 5min \
  --fetched-at 2026-01-01T12:15:00Z --as-of 2026-01-01T12:15:00Z --origin synthetic
```

The synthetic inputs can be reproduced from the explicit fixture in
`tests/unit/test_advisory_massive_intake.py`; it uses no random seed. Its calendar,
listing metadata and prices are **SYNTHETIC MECHANICS ONLY**. The result retains
SHA256 identities for both complete input byte streams and the normalized
snapshot preflight. Oversized inputs have no claimed complete-file hash. Only
the requested bounded window is emitted as `normalized_snapshot`; later capture
times are preserved, so an earlier cut cannot make a later observation causal.
Metadata, arbitrary source fields, request IDs and credentials are not echoed.

Conversion never invents source-quality/heartbeat/quote evidence. A structurally
valid conversion therefore remains UNKNOWN/UNHEALTHY under the existing health
guard; the CLI exits 2 and still emits diagnostics. It retains ABSTAIN, blocked
TCP50 sizing, false trading/execution permissions and UNKNOWN passing probability.
There is no licensed/READY switch or persistent verification cache. Run results
and containment evidence are recorded in the current readiness report.

### Verified account access; unresolved rights

On October 9 the authenticated dashboard showed **Futures Basic, Individual,
$0/month**. Four small browser REST queries returned HTTP 200/OK: single-contract
specifications for MESZ6/MNQZ6, then three one-minute bars per contract for October
8, 14:30–14:32 UTC. Only that sample's access, identities and basic field/time
consistency were checked. It is not a qualified history, fill model or edge test.
Raw rows were not saved in the repository. The dashboard's **No agreements**
message does not establish a storage/replay grant.

The user-authorized question about local retention, private automated research,
replay, TCP50 preparation and fees was sent to Massive support. At the observed
submission checkpoint the messenger confirmed delivery and showed **Waiting for
a teammate**. On October 9 the user supplied Anna's reply, which was then
independently read in the authenticated support conversation. Massive says its
published terms govern permitted use; it will not provide individual-use-case
legal interpretations, authorizations or addenda, and support replies do not
change the agreement. Consistent use is authorized by the applicable terms, not
by this reply. No key, contact details, signup, agreement acceptance, subscription
change or purchase is recorded here.

Official documentation reviewed October 9:
[contracts](https://massive.com/docs/rest/futures/contracts),
[aggregates](https://massive.com/docs/rest/futures/aggregates),
[personal application use](https://massive.com/knowledge-base/article/which-plan-do-i-need-to-show-massive-data-in-my-app)
and the [individuals terms](https://massive.com/legal/individuals-terms-of-service)
(updated July 18, 2025) and
[market-data terms](https://massive.com/legal/market-data-terms-of-service)
(updated August 28, 2025), freshly reopened after the reply. The personal-use FAQ
mentions own research/scripts. Market-data sections 1–2 limit use and default to
display unless another applicable agreement permits otherwise; section 5(d)
requires licensing for non-display/strategy use. Section 4.3 incorporates CME
terms and requires subscriber classification evidence; section 8 requires
deletion after termination, restriction or suspension. These clauses do not
establish the exact retention/replay or TCP50-use grant. No blanket ban on all
personal analysis, account classification or automatic paid-upgrade requirement
is inferred.

## Offline intake implemented

`scripts/advisory_intake.py` provides a local preflight for an existing MES/MNQ
`MarketSnapshot` JSON file. It reuses `MarketDataQuery`, `bounded_snapshot` and
`assess_market_data`. It does not start the API, load `.env`, initialize a store,
connect to a provider, import data into the application, or expose order methods.
Existing provider/replay, policy, financial arithmetic and evidence formats are
unchanged. This command is a file-inspection entry point, not a new data engine.

From the repository root on this Linux workspace:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python -B -m scripts.advisory_intake \
  artifacts/earn2trade-50k-readiness/offline-intake/synthetic-MNQ-snapshot.json \
  --instrument MNQ --contract MNQZ26 --interval 15m \
  --as-of 2026-01-01T19:59:59.999Z --origin synthetic
```

The included sample is **SYNTHETIC MECHANICS ONLY**, with 80 deterministic bars
from the existing test fixture. It is not market history, execution-quality
evidence, strategy performance, or an evaluation attempt. No random seed is used.
The dated contract is a syntax fixture, not evidence of actual listing/liquidity.
For your own file, use its actual contract/interval and an explicit observation
clock; the default origin is `unverified`. Never change the clock to make stale
data appear current. This command does not qualify replay, a live feed or a
dataset's licensing merely because the declared values pass checks.

The JSON result records the byte SHA256, query, declared origin, reviewed and
excluded bar counts, data-health reasons and independent unresolved gates.
Exit **0** means only that the input structure and selected closed-bar window
pass the existing health guard. Exit **2** means invalid arguments/file, invalid
structure or UNKNOWN/UNHEALTHY data. Argument/file errors use stderr; assessed
inputs produce JSON on stdout. Both successful and unsuccessful assessments
retain `ABSTAIN`, `trade_permitted=false`, `execution_enabled=false`, blocked
TCP50 allowance and UNKNOWN passing probability. There is no `licensed` shortcut.

Input is bounded to 500,000 bytes and the existing maximum 500 bars. Repeated
JSON keys, duplicate/overlapping candles, invalid OHLC, wrong identity, naive
timestamps and unfinished candles are rejected. Existing health checks diagnose
cadence gaps, off-tick prices, provider faults, missing quality and stale clocks.
No exchange calendar is invented to explain a futures gap. Quote evidence still
requires explicit limits; this command supplies no guessed quote/spread limits.
Earlier cuts exclude unfinished candles but do not turn a later capture's
heartbeat/context into historical evidence. Use the existing `ReplayProvider`
for separately qualified historical research. Raw input rows and validation
exception values are not echoed. Keep private inputs and their output private.

## Separate readiness dimensions

| Dimension | Current status | What is needed to advance |
| --- | --- | --- |
| Engineering | PARTIAL; offline intake, provider/replay, quality guards and advisory isolation exist | Integrate approved data through existing boundaries; test a bounded advisory session |
| Market-data access/licensing | PARTIAL: small Massive Basic REST sample works; recording/replay rights NOT ESTABLISHED | Clause-based evidence of the applicable grant/classification and a suitable qualified history |
| Evaluation rules | PARTIAL; TCP50 positive allowances BLOCKED | Complete progression/accounting semantics, then purchase-date assigned rules |
| Strategy validation | MISSING qualified evidence | Frozen strategy/costs, licensed chronological data, untouched OOS and sufficient samples |
| Live advisory readiness | CANNOT ASSESS | All relevant gates, fresh feed/account observations and forward reproducibility |

Missing provider permissions block provider connection and ingestion of restricted
data, not offline synthetic engineering. Missing progression semantics block
confirmed TCP50 sizing/compliance, not data-shape diagnostics. Suitable data,
costs, slippage, chronology and holdout protection are prerequisites for strategy
conclusions. Passing probability remains **UNKNOWN**.

## Earlier official provider findings — 2026-10-08

All sources below were accessed on **2026-10-08**. No login, API subscription,
agreement acceptance, account connection or support message was performed.

| Question | Rithmic | Tradovate |
| --- | --- | --- |
| Evaluation platform setup | Earn2Trade describes exchange agreements and a paper connection; a distinct practice simulator is provided alongside evaluation. [Setup; July 6, 2026](https://help.earn2trade.com/en/articles/6911655-how-do-i-set-up-my-rithmic-evaluation) | Earn2Trade describes agreements and simulation mode, but says only the evaluation account is supplied and orders count toward evaluation. [Setup; March 25, 2026](https://help.earn2trade.com/en/articles/14196947-how-do-i-set-up-my-tradovate-evaluation) |
| Custom API eligibility | Rithmic advertises C++/.NET R API+ and WebSocket/protobuf R Protocol API. Developer-kit/conformance processes exist. Earn2Trade user eligibility remains UNKNOWN. [Products](https://www.rithmic.com/products), [developer inquiry](https://www.rithmic.com/support/contact/form?category=api) | Public retail requirements list a LIVE account over $1,000, CME ILA and paid API Access. No evaluation-specific exemption was verified. [Official help; March 20, 2024](https://tradovate.zendesk.com/hc/en-us/articles/4408927027987-How-Do-I-Get-Access-to-the-Tradovate-API), [API documentation](https://api.tradovate.com/) |
| History and real time | Provider advertises live/delayed/historical data and history from December 2011. Its exchange page advertises 40 GB weekly history, resetting Sunday around noon Eastern. This is provider-level capability, not an assigned grant or a guarantee for all MES/MNQ dates/fields. [Technology](https://www.rithmic.com/technology), [exchange/history scope](https://www.rithmic.com/platforms/exchanges) | API documents market-data service and WebSockets. Actual evaluation history depth, ticks/bid-ask fields, quotas and grant remain UNKNOWN. [API documentation](https://api.tradovate.com/) |
| Simultaneous platform/custom session | Bookmap guide uses R Trader Pro plugins. It does not establish a custom ALGHREST plugin grant or a universal session count. [Official guide; March 17, 2026](https://help.earn2trade.com/en/articles/4634787-how-to-connect-rithmic-to-bookmap) | New supplied NinjaTrader access uses the unified Tradovate connection. Platform compatibility does not establish custom API entitlement or session limits. [Official connection guide](https://help.earn2trade.com/en/articles/4473826-how-to-connect-tradovate-to-ninjatrader) |
| Personal recording/replay/analysis | UNKNOWN for this user; obtain written permitted uses, retention and session terms | UNKNOWN for this user; obtain written permitted uses, retention and session terms |

The Tradovate retail article is dated 2024. Its current support URL returned HTTP
502 during this review; the older official help page and API documentation were
readable. They support a planning prerequisite, not a claim that no partner route
can exist. Do not fund a separate brokerage account or buy an add-on to resolve
this uncertainty without the user's separate decision and provider clarification.

Earn2Trade states that standard evaluation data is included for qualifying
non-professionals and excludes DOM. This does not establish custom API or storage
rights. [Data fees; June 3, 2026](https://help.earn2trade.com/en/articles/2825514-do-i-have-to-pay-for-data-fees-during-the-trader-career-path-gauntlet-mini).
Its funded-stage fee page distinguishes evaluation, LiveSim and Live, with separate
commissions; evaluation entitlements cannot be assumed to transfer.
[Funded fees; July 6, 2026](https://help.earn2trade.com/en/articles/2280137-what-is-the-fee-structure-on-the-live-or-livesim-accounts).

CME lists separate policies for non-display processing/analysis, historical
licensing and AI use. Personal/advisory-only status is not treated here as an
automatic permission. The applicable classification remains a provider/exchange
question. [CME policy center](https://www.cmegroup.com/market-data/license-data/market-data-policy-education-center.html).

Rithmic pages returned empty direct-open text in the web tool; official-domain
indexed text provided the stated capabilities. No source-byte HTML archive or
account entitlement receipt is claimed. The research helper wrote a draft before
its final turn hit a usage limit; the retained claims above were checked by the
parent against primary sources. No third-party forum claims are authoritative.

## Unsent inquiries for the user

**Earn2Trade:** I am planning TCP50 and have not purchased it. May a private
advisory-only application read MES/MNQ data through Rithmic or Tradovate custom
APIs while I trade manually? Please distinguish evaluation, LiveSim and Live,
and identify required application approval, agreements, data-only permissions,
fees, history coverage, concurrent platform sessions and local recording,
retention and replay rights, with governing terms/effective dates. This is an
information request only; do not activate access or charge fees.

Please also clarify progression for negative cumulative profit, cents between
$1,500/$1,501 and $2,000/$2,001, the exact P&L/equity field and fee timing,
11/20/21 MNQ, 1 NQ plus 10 MNQ, 6 MES plus 6 MNQ plus 6 MYM, and downward band
transitions while positions remain open. The printed chart alone does not resolve
these cases. [Official progression source](https://help.earn2trade.com/en/articles/5922873-what-is-the-progression-ladder-on-the-trader-career-path).

**Rithmic:** Does an Earn2Trade TCP50 evaluation user qualify for R Protocol API
or R API+ for data-only MES/MNQ access? Which developer registration, conformance,
sponsor approvals and exchange permissions apply? Please confirm history fields,
limits, retention/private replay rights and concurrent manual-platform sessions.
Can every order/account mutation be technically disabled? No activation requested.

**Tradovate:** Is there a supported Earn2Trade TCP50 custom data-only API route,
distinct from the supplied platform connection, or do retail API prerequisites
apply? Please confirm sponsor approval, data-only scopes, real-time/history
entitlements, quotas, sessions and local storage/replay rights for evaluation and
funded stages separately. No activation or subscription change requested.

## Next external evidence

Massive is now identified and a small REST access probe succeeded. Following
Anna's reply, the next review must map the actual personal/offline research,
retention, automated replay and prospective TCP50 uses to the applicable published
terms, incorporated CME agreement and subscriber facts. Record the exact clause
support and any unresolved conflict or missing grant. Waiting for a bespoke
authorization is no longer the proposed route. No purchase, further support
message or real-data retention is authorized by this engineering increment. The next
data milestone is a permitted small MES/MNQ sample inspected with this command,
then a documented quality review through the existing replay boundary; it is not
yet a backtest profitability conclusion or permission to touch the final holdout.
