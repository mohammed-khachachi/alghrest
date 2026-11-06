# ALGHREST × OpenTerminal: complementary research workspace

OpenTerminal provides charts, public quotes, headlines and market exploration.
ALGHREST calculates descriptive market analysis from these data. Its existing
manual journal and risk tools remain separately accessible. Both research interfaces appear at
`http://127.0.0.1:5173/research`, with a read-only data connection. OpenTerminal supplies the instruments and data
used by the research analysis.

## Run the complete integrated workspace

From the ALGHREST project root:

```bash
node scripts/run_research.mjs
```

Open `http://127.0.0.1:5173/research` and sign in with your existing local assistant
access token. Never paste the token into OpenTerminal. The launcher starts the
ALGHREST assistant API (8011), dashboard (5173), OpenTerminal web (3001) and its
API (4001). Ctrl+C stops only the processes it started. Occupied ports cause an
explicit error; their owners are not terminated. Check readiness with:

```bash
node scripts/run_research.mjs --check
```

Dependencies are installed on the current machine. On a fresh checkout, install
the Python project into `.venv`, and run `npm ci` separately in `dashboard/` and
`vendor/openterminal/`. Node 22.12+ is recommended for this pinned dependency set.
The assistant still needs its normal local configuration and access token.
Windows launch paths exist, but Windows runtime shutdown has not been verified.

This command runs the complete **research integration**. It does not start Docker,
Kafka agents, broker execution, copy trading or DeFi. The assistant starts in
`development` with DeFi disabled and its Kafka address empty.

## How the programs complement each other

OpenTerminal is now the data foundation for `/research`. ALGHREST follows its
actual selected symbol, rather than mapping SPY/QQQ to MES/MNQ or requesting an
external futures file. The embedded chart and the research symbol input share
the selection. AAPL, SPY, QQQ, BTC-USD and other symbols use the terminal's own
provider support; unavailable instruments remain unavailable.

ALGHREST reads three fixed local endpoints through authenticated
`GET /assistant-api/openterminal-research/{symbol}`:

- `/api/quotes?symbols={symbol}` supplies the reported quote, currency, provider
  and source time when present.
- `/api/history/{symbol}?range=6M&metadata=1` supplies the OHLCV series. ALGHREST calculates
  SMA20, SMA50, simple-window RSI14, simple-window ATR14 and the last 20 bars'
  high/low. It describes the last historical close relative to the averages.
- `/api/news?symbol={symbol}` supplies up to eight sanitized public headlines.

RSI is 100 times positive close changes divided by all absolute close changes
across the last 14 changes; an entirely flat window returns 50. ATR is the simple
mean of 14 true ranges against each preceding close. These are explicitly simple
windows, not Wilder smoothing. Averages use actual bar counts. Less than 20/50
bars leave the corresponding average missing; RSI/ATR need 15 bars. No missing
candles or volumes are invented. Invalid OHLC envelopes, duplicate/out-of-order
or future timestamps invalidate the historical series. Other valid source
results can still be displayed when one feed fails.

The requested history range is six months. Upstream provider fallbacks can return
a different effective period or frequency. The page shows the actual first/last
timestamps and bar count; the metadata response identifies the successful provider and the interval requested
from that provider where explicitly configured. Nasdaq and FRED do not declare a
request interval in this adapter, so their interval remains UNVERIFIED. Quote
currency and provider are preserved. The current quote and historical last close
are separate readings and are never combined as if they had the same timestamp.

Refresh explicitly; the displayed report expires after 90 seconds. A slow or
unavailable public source is shown as unavailable. Receipt time is not market
freshness. These descriptive indicators are available without ALGHREST's
futures catalog, imported data, account setup or evaluation-policy prerequisites.

The iframe exchanges only a public symbol and a message type, with fixed origins
and window identity checks. Prices, tokens and account data do not cross that
bridge. Python separately reads three fixed local GET routes, caps payload sizes,
preserves decimal numbers and retains each source response's SHA-256 identity.
No credentials are forwarded.

The manual assistant and its existing account/risk policies remain available at
`/assistant`, via an optional link. OpenTerminal's manual portfolio is a separate
bookkeeping journal. This new market-research page does not apply MES/MNQ point
values or account permissions to stock/ETF/crypto quotes. It does not enable
orders, infer event completeness or establish trading edge/passing probability.
The earlier `/assistant-api/openterminal-context/{MES|MNQ}` proxy context remains
for compatibility with the existing manual assistant, not the `/research` flow.

## Data status and clock meanings

The research page displays a separate status card for quotes, candles and news.
Times use Africa/Casablanca and are labelled as Morocco time.

- Candle provider is the successful provider for the exact cached series, including
  fallbacks. A provider returning an empty array now allows the next fallback.
- Timeframe is the configured provider request: Yahoo's interval, Stooq's daily
  request or Binance's shared kline configuration. It is not inferred from a
  six-month range or gaps between timestamps. Missing intervals say not declared.
- Last candle time and its elapsed age come from the actual series. OpenTerminal
  fetch time records when a provider request completed successfully. ALGHREST
  receipt time records when the local response arrived. They are separate clocks.
- A cache hit retains the original provider, interval and fetch time. A failed
  refresh that returns a previous snapshot is explicitly marked stale. No cached
  copy gets a new fetch time until a provider succeeds.
- Quote market timestamps are displayed when supplied. An age over 15 minutes
  produces a labelled display-age warning; this is not an exchange-session or
  provider-latency diagnosis. A missing timestamp remains unknown.
- News shows the newest valid publication time and its age. An empty valid news
  response, unavailable response and rejected response are distinct states.

The adapter validates metadata identity, range, clocks and interval basis. Legacy
array-only responses remain usable with unknown provenance. Existing terminal
chart clients still receive the original candle array unless they request
`metadata=1`. Metadata and the series are cached together; there is no extra
provider fetch just to populate status. Market freshness/event completeness stay
UNKNOWN; weekend/session gaps alone are not labelled as feed outages.

## Per-symbol research summary

The Arabic research summary uses the same validated snapshot as the status cards.
It adds no network requests, model calls, dependencies or trading actions. Symbol
changes and the existing 90-second display expiry also clear the summary.

- Trend explains the ordering of the last candle close, SMA20 and SMA50, and
  shows the percentage distance from SMA20. It never substitutes the latest quote.
- Momentum explains the simple RSI14 gain/loss balance against 50, including the
  balanced/unchanged case. It does not predict reversals.
- Volatility explains simple ATR14 in candle price units and as a percentage of
  that same historical close. It does not assign high/low labels without a baseline.
- Insufficient samples, missing candles, unknown intervals and stale snapshots
  retain explicit qualifications. Periods mean candles, not automatically days.
- Up to three headlines prioritize exact symbol/name mentions and then publication
  time. Matching is a conservative title heuristic, not entity verification.
  Unmatched headlines remain labelled as context with uncertain direct relevance.
  Reading cues identify title topics (results, products, forecasts, holdings) and
  what to check in the article; article bodies are not fetched or summarized.
- Publisher links and publication times accompany headlines. The candle source
  details retain the snapshot hash, provider and clocks. The raw-data link opens
  the current OpenTerminal response and is explicitly not an immutable snapshot.

Summary evidence: `openterminal-summary-verification.json` and
`artifacts/openterminal-summary-20261015/`. Earlier receipts remain historical.

## Candle quality and conclusion eligibility

New research responses include `data_quality` (`candle-quality-v1`). The Arabic
summary and watchlist show **usable**, **limited**, or **unavailable**, with observed
counts and reasons. The check describes integrity of the returned OpenTerminal
series; `freshness` and event completeness remain `UNKNOWN`.

The adapter counts malformed candles, missing/invalid timestamps, repeated times,
reversed adjacent pairs and future timestamps before calculating indicators. It
does not sort, merge, drop or interpolate defects. Structural defects and
inconsistent fetch clocks make the series unavailable for analysis; quote and
headline feeds remain independent. Counts that could not be observed stay null.

For a declared fixed interval, the report counts adjacent gaps longer than that
interval and the largest observed gap. Only Binance fixed-interval history is
treated as a continuous grid for missing-slot checks. Other providers need a
verified session/holiday calendar: their long gaps do not prove missing candles,
so missing-slot counts remain unknown and descriptive calculations are labelled
limited. Unknown intervals are not inferred from spacing. Monthly intervals are
not converted to a fixed number of seconds.

Confirmed gaps or off-grid spacing suppress only conclusions whose trailing
window contains the defect: 50 candles for trend, 15 for simple RSI/ATR. A gap
outside all three windows leaves those calculations available with a series-level
warning. Short samples suppress the affected conclusions. An explicitly reported
stale cache suppresses all three current conclusions while retaining the original
close and source clocks. The API returns blocked indicator values as null, and
frontend validation rejects contradictory quality flags/metrics.

Snapshots store the assessment with its original evidence. Older snapshots without
this optional field remain readable and carry an explicit **quality not assessed**
label; they are not retrospectively recertified or rewritten. PDF briefs include
the quality counts, limitations and suppression reasons from saved snapshots.

Verification: `openterminal-quality-verification.json` and
`artifacts/openterminal-quality-20261016/`. The repeatable workflow command includes
the quality regression suite.

## Research watchlist and saved snapshots

On `/research`, choose a symbol and use **إضافة … للمتابعة**. Saved watchlist
buttons reopen that symbol in both the research panel and native chart. This list
is separate from the manual assistant's futures watchlist and OpenTerminal's own
widget list.

**جلب وحفظ لقطة …** asks the server to fetch a new public research reading and
append it to the local advisory SQLite database. The UI switches to that saved
snapshot and marks it as historical. The selector can reopen any of the last
100 saved snapshots for that symbol or return to the current reading. Existing
90-second live-display expiry remains in force; historical snapshots are validated
against their original save clock and never become live merely by reopening them.

- Saved reports preserve the original indicators, source response hashes, candle
  provider, declared timeframe, cache state, fetch/receipt times and headline links.
- The comparison uses the most recent snapshot with an earlier assessment time.
  It shows before/after values for trend, RSI, ATR, moving averages and close, plus
  feed availability and candle cache status. Numeric differences are withheld when
  provider/timeframe identity is missing or differs; separate values stay visible.
- News comparison distinguishes newly returned URLs, edited titles/metadata and
  URLs no longer returned. If either news feed is unavailable, it does not claim
  that headlines disappeared. Returned headline sets are not complete event lists.
- Removing a watch preserves all its snapshots; add the symbol again to resume.
  Limits are 50 watched symbols, 100 snapshots per symbol and 5,000 total snapshots.
  Reaching a limit rejects further saves instead of deleting history automatically.
- Save requests carry a retry identity. Retrying a lost response returns the same
  saved record and does not fetch or append another copy. The server collects the
  report; clients cannot submit arbitrary reports to the snapshot endpoint.

Authenticated endpoints: `GET /assistant-api/research-watchlist`,
`PUT /assistant-api/research-watchlist/{symbol}` with `{ "watched": true|false }`,
and `GET|POST /assistant-api/research-snapshots/{symbol}`. POST accepts an `id`
containing 32 lowercase hexadecimal characters. Writes require the existing
dashboard client header. There are no delete-snapshot or background refresh jobs.

Verification: `openterminal-watchlist-verification.json` and
`artifacts/openterminal-watchlist-20261015/`; browser checks use an isolated
synthetic account database, with public market responses clearly distinguished
from deterministic test fixtures.

## Watchlist overview and manual refresh

The watchlist overview shows one row per saved symbol: trend, simple RSI14,
simple ATR14 (also as a percentage of the historical close), changed-item count,
newly returned headline count, provider and data-status warnings. Each row has
**التفاصيل** and **تحديث** actions. Details selects the symbol in both workspaces,
scrolls to its research panel and requests a new detailed reading.

On load, the overview reads only the latest two saved snapshots per symbol using
`GET /assistant-api/research-snapshots/{symbol}?limit=2`. The optional limit is
validated from 1 to 100; existing history callers retain the 100-record default.
Loading the overview itself does not fetch external market data. With no saved
snapshot, the row explicitly says it has no reading.

**تحديث الكل** manually requests current research through the existing read-only
endpoint, with at most two symbol requests in flight. It does not create snapshots.
Progress counts successful responses, request errors and skipped symbols separately;
a successful HTTP response may still contain unavailable market/news data, which
remains visible in that row. Each symbol can be retried individually. **إيقاف
المتبقي** skips queued symbols and lets the running requests finish. Changing the
watchlist membership also stops the remainder of an active batch.

Current readings keep the 90-second display expiry. Afterwards the overview
falls back to a clearly labelled saved snapshot, if available, rather than keeping
expired indicators marked current. A failed refresh leaves the prior valid reading
or saved snapshot visible with its original clock and a failure message. Comparisons
retain the same provider/timeframe qualifications and headline-set limitations as
the individual research view. No periodic market polling or background jobs are added.

Verification: `openterminal-overview-verification.json` and
`artifacts/openterminal-overview-20261015/`.

## Exportable daily research brief

Use **تحميل موجز البحث PDF** above the overview. The app downloads a dated Arabic
PDF covering every watched symbol, including those with no saved snapshot. It
uses the newest two saved snapshots, read in one SQLite transaction. Unsaved
manual-refresh readings are excluded; save a snapshot first to include a new
reading. The export does not fetch market data or change watch membership/history.

The report includes a watchlist index, plain-language indicator explanations,
before/after values and data-availability changes, relevant headline links,
publication times, providers, declared candle intervals, original fetch/receipt
clocks, snapshot identities and source response hashes. Unknown timestamps and
intervals remain unknown. Stale cached candles and older quote timestamps carry
explicit qualifications. Report creation time is distinct from saved market times;
dates and clocks in the report use Africa/Casablanca.

`GET /assistant-api/research-brief.pdf` requires the existing advisory token and
returns a no-store PDF attachment. The browser sends the token in the header and
downloads a validated PDF blob; tokens never enter file URLs, filenames or content.
The download is bounded to 12 MB. The ready-file link can download the same bytes
again. Export failures display an error and preserve the source records.

ReportLab, arabic-reshaper and python-bidi are locked project dependencies. Run
`poetry install` after updating the project. The renderer embeds the bundled
DejaVu Sans font and its license under `src/api/assets/research_pdf/`; the wheel
includes both files. Rendering is local and serialized because the shared dynamic
font cannot safely serve simultaneous ReportLab documents. The renderer is loaded
only when PDF export is requested, keeping other assistant features available if
an older environment lacks PDF dependencies.

Verification: `openterminal-brief-verification.json` and
`artifacts/openterminal-brief-20261016/`. The example report under `output/pdf/`
uses the isolated test journal with public snapshots; missing snapshots are
labelled explicitly. It contains no real account information or credentials.

## Repeatable workflow reliability check

Stop the local research services first, then run from the repository root:

```powershell
node scripts/check_research.mjs
```

The command requires the installed project environment, dashboard dependencies,
terminal dependencies and PDF dependencies. It runs launcher tests, focused Python
research/API regressions, dashboard contract tests and native terminal tests. It
then starts the actual API, Vite dashboard, native terminal API and Next.js app
on the usual loopback ports, using a separate temporary assistant database and
terminal data directory. No real account or credentials are used.

The workflow checks authentication, actual symbol identity, snapshot save/retry,
explicit missing-data behavior when the owned market API is stopped, saved-history
and PDF availability during that outage, service recovery, full restart and exact
snapshot preservation. Removing a watched symbol must retain its saved history.
Public-data availability is recorded separately; external-provider failures are
not converted to fake prices or a market-freshness pass.

Each run creates `artifacts/research-check-<UTC-time>/verification.json` plus logs,
public source states and snapshot fingerprints. Failure exits nonzero and keeps
its temporary data for investigation. Success removes its temporary data and
confirms all owned services stopped. The command refuses occupied ports and never
stops a pre-existing workspace.

Optional `--preview` pauses at the normal, market-unavailable and restarted
checkpoints for manual browser inspection. Press Enter in the check terminal to
advance, or Ctrl+C to stop and clean up owned services. It uses a disposable
synthetic fixture key defined in the check script, not the operator's access key.
Browser interactions are verified separately from the automated service/API
checks. Normal `node scripts/run_research.mjs` startup retains the existing local
operator access configuration.

The process supervisors now clean the owned process group even if its npm/Node
leader exits before a child server. A regression test reproduces the original
orphaned-listener failure and verifies the port is released after cleanup. Windows
command plans are tested, but native Windows process cleanup still requires a
Windows runtime check.

Verified on Linux on 2026-10-16: 364 focused tests passed, followed by the full
unattended workflow. Browser checks covered rapid symbol changes, explicit data
outage, historical snapshot access, PDF export and restart recovery. See
`openterminal-workflow-verification.json` and
`artifacts/research-reliability-20261016/` for the scoped change record,
screenshots and automated receipt. The deliberate Ctrl+C preview run is retained
separately as interruption-cleanup evidence.

## Source-reported session and quote clocks

The research bridge opts into `/api/quotes?symbols={symbol}&metadata=1`. Each
quote carries its original successful fetch clock and a fetched/cached/stale
label. Cache hits and failed refreshes preserve that clock; an HTTP response
received now cannot make an older quote current. Normal terminal clients retain
the original array format without the additional observation field.

The data-status cards and saved PDF distinguish the provider's price timestamp,
terminal fetch time, ALGHREST receipt time and source-declared session state.
Only Nasdaq/Yahoo session values actually returned by those providers receive
a provider basis. Binance's adapter assumption that a market is open is explicitly
unverified. Unknown provider labels remain unknown.

A price timestamp within 15 minutes is only within the display window, not a
real-time guarantee. An older timestamp is qualified by a recent provider report
of an open or closed session when available. Session context expires after 90
seconds or immediately for a stale fallback. Neither exchange holidays nor
session calendars are inferred. Candle timestamp age may describe the beginning
of a bar; it does not establish the last update or completion of that bar.
Missing candle intervals remain undeclared. Overall freshness and event coverage
remain `UNKNOWN`, and historical records retain their original clocks.

## Research backup and merge restoration

Expand **نسخ البحث احتياطيًا واستعادته** in the research journal. Download exports
watch membership and every saved research snapshot, including history belonging
to symbols no longer watched. It excludes account journals, access tokens and
terminal keys. The versioned JSON archive has a 32 MiB bound and a content hash
for corruption detection; the hash does not establish publisher authenticity.

Select a local JSON file to preview counts, then choose **استعادة السجلات الإضافية**.
The server validates the complete archive and merges it in one transaction.
Identical records remain unchanged. A conflicting snapshot identity, invalid
record, corrupt checksum or exceeded journal limit rejects the whole operation.
No existing snapshot is replaced or deleted. Imported records receive an
explicit restoration annotation while their stored payload bytes and original
timestamps remain unchanged. Preview counts can change if another request saves
research before restore; the server revalidates every constraint when applying.

The same authenticated API exposes `GET /assistant-api/research-backup` and
`POST /assistant-api/research-backup/{preview|restore}`. Restore writes require
the existing dashboard client header. No account database file is uploaded.

For local maintenance, use the configured research database path without putting
credentials in commands. The CLI refuses to overwrite an existing export and
creates a private file on Unix. Restore defaults to preview; `--apply` performs
the merge:

```bash
PYTHONPATH=src .venv/bin/python scripts/research_backup.py export --database /path/to/advisory.sqlite3 --file /private/path/research-backup.json
PYTHONPATH=src .venv/bin/python scripts/research_backup.py restore --database /path/to/restored.sqlite3 --file /private/path/research-backup.json
PYTHONPATH=src .venv/bin/python scripts/research_backup.py restore --database /path/to/restored.sqlite3 --file /private/path/research-backup.json --apply
```

These are Unix examples; the browser workflow works without shell commands.
Keep archives private because watchlists and saved research may reveal interests.
The operator backup created on 2026-10-16 contains zero watched symbols and zero
snapshots, matching the actual journal at that time. Nonempty restoration is
verified separately using isolated fixture and public-data journals.

## Bounded multi-symbol observation

With the normal research workspace running, the following records 30 minutes
of live read-only service checks. It never restarts services and uses a separate
temporary journal for snapshot, backup, exact restoration and PDF checks:

```bash
PYTHONPATH=src .venv/bin/python scripts/check_research_soak.py --minutes 30 --interval-seconds 60 --symbols AAPL MSFT BTC '^VIX'
```

The run records provider availability, declared session context, quote/candle
quality, request latency and sample gaps under `artifacts/research-observation-*/`.
Application identity/permission errors, service loss, source changes or a sample
gap above five minutes fail the check. Missing external feeds remain explicit
and are counted separately. An interrupted run cannot become a success.
Success verifies only the recorded duration; it does not establish 24-hour or
multi-session stability, data latency guarantees or trading readiness.

## Runtime isolation

ALGHREST retains React 18/Vite; OpenTerminal retains Next.js/React 19 and its own
lockfile. The research route uses advisory navigation and does not connect the
legacy trading WebSocket. The launchers pass an OS/runtime environment allowlist;
OpenTerminal receives no ALGHREST keys, assistant token, database, Redis or Kafka
configuration. Generated terminal keys and journal files remain ignored under
`vendor/openterminal/data/`.

OpenTerminal AI is disabled at the API entrypoint; status reports `ai: false` and
`execution_enabled: false`. No trading execution services were changed.

The MIT upstream snapshot is pinned to
[`aed097c680cd8ec1c391ae06966babe7d6d91fc6`](https://github.com/ErTasselli/OpenTerminal/commit/aed097c680cd8ec1c391ae06966babe7d6d91fc6).
`vendor/openterminal/UPSTREAM.json` preserves original per-file SHA-256 identities,
the explicit lists of local modifications and integration additions. There is no nested Git repo.
Local adaptations cover loopback ports, coordinated shutdown, disabled AI,
research labels/return navigation, limited build workers and ignored generated
files, plus history provenance and cache status. `IntegrationBridge.tsx` and
`server/src/historyStatus.ts` are ALGHREST additions. Review future upstream
commits before replaying these adaptations; do not combine package dependencies.

## Verification

Current data-status evidence: `openterminal-data-status-verification.json` and
`artifacts/openterminal-data-status-20261015/`. The browser used an isolated
synthetic account database and token. Public market responses were observed;
this does not certify their freshness or quality. Existing account data and
credentials were not included in evidence.

`openterminal-verification.json`, `openterminal-complementary-verification.json`
and `openterminal-data-first-verification.json`
document earlier integration stages and are retained as historical evidence.
The stabilization work on 2026-10-16 additionally runs the non-live unit and
integration suite with the existing 70% coverage gate, alongside focused
Python/dashboard/terminal regressions, type checks, production builds and Linux
startup/shutdown checks. Infrastructure tests that require a disposable database,
Redis, Kafka/Docker or an explicit paper-runtime opt-in remain skipped when those
prerequisites are absent. Exact counts, scope and the bounded observation receipt
are recorded in `research-stabilization-verification.json` once verification
finishes. This integration is local desktop only; loopback URLs do not provide a
remote deployment.

### Provider diagnostics and research change alerts

After selecting a symbol, **تشخيص مزودي البيانات** shows observations for quotes,
OHLC history, Yahoo RSS and Google RSS from the current native process. Each
provider has its last attempted request state, last successful request and last
failure with a safe reason code. A recovered provider retains its last failure.
These observations are bounded process memory, shared with native widgets;
they reset on restart or eviction and are not an uptime audit. Cached data does
not advance a successful provider clock. News requests can succeed with no
headlines; success does not certify coverage, relevance or freshness.

Nasdaq's supplied `lastTradeTimestamp` stays labelled as unconverted provider
text, including its ET label. Binance `closeTime` is labelled as the ticker
statistics window close, never the last trade time. FRED's VIX fallback quote
carries a daily close date. Missing UTC price times and Nasdaq's undeclared
candle interval remain unknown. VIX OHLC history now comes from Yahoo with a
Stooq fallback; FRED daily closes are not manufactured into candles.

**تنبيهات تغير البحث** compares the displayed report against its previous saved
snapshot. Save a baseline, then refresh research after a newer bar is supplied.
It describes changes in SMA20/SMA50 ordering, RSI14 crossings of 30/70, and
ATR14/close movement of at least 25% relative and 0.25 percentage points absolute.
Each event includes numbers, the declared provider/timeframe, both bar/fetch
clocks and the history-response hashes. Thresholds are transparent display
choices, not calibrated trading rules. Last bars may be forming, so events are
explicitly provisional. There is no background alert scheduler or external
notification. Historical selections remain historical.

Alerts require matching known history provider/timeframe, newer bars, advancing
successful fetch clocks and usable indicator evidence in both readings. Stale,
old, missing, incomparable or restored-from-backup evidence suppresses events
with an explanation. An unverified session calendar remains an explicit limit;
opening/closing sessions are never inferred. Quotes or headlines are not used
to fill missing candle conclusions. Snapshot bytes and schemas remain unchanged.

See [the scoped plan](research-reliability-alerts-plan.md). Diagnostic API:
`GET /assistant-api/research-diagnostics/{symbol}`, using the existing assistant
access gate. Native diagnostic reads never contact providers; refreshing the
research report does. No access token is forwarded to OpenTerminal or providers.

### English and Arabic interface

Choose **English** or **العربية** in the language selector on the access page or
in the header. The same selector is available in OpenTerminal. When embedded,
OpenTerminal and ALGHREST synchronize the choice in both directions. Changing
language updates interface text without navigating, remounting the workspace,
or clearing input fields. The preference is saved as `alghrest.language` in each
origin's local storage; it contains only `en` or `ar`. Arabic is the default.

Arabic sets the document language to `ar` and direction to `rtl`. English uses
`en` and `ltr`. Symbol/access-key fields and chart axes keep left-to-right
notation. The language switch affects interface labels, help text, status and
known diagnostic messages. Public news, company names, user notes, external
video and other original source content retain their original text. PDF exports
retain the existing report generator's language. This feature makes no external
translation requests and does not change API payloads or stored research data.

The dashboard translation entry point is `dashboard/src/i18n/index.tsx`, with a
pure translation/store module in `core.ts`. Components call `useLanguage()` to
subscribe and `tr()` only when displaying interface text. Labels use exact
source text as keys in `messages.json`; each entry contains `[English, Arabic]`.
Known templates use numbered placeholders such as `{0}` and preserve their
interpolated values. Unknown source text passes through. Keep news/user content
outside `tr()`. Use `currentLocale()` for interface date and number formatting.

OpenTerminal carries an independent copy under `web/i18n/` so its React 19
runtime does not import the React 18 dashboard. Keep both copies synchronized;
`dashboard/tests/language.test.ts` validates catalog equality, placeholder
integrity, source/value preservation, storage behavior and the strict language
message schema. Existing origin and window-source guards also apply to language
messages, which contain only `type` and `language`.

Run the dashboard production build and OpenTerminal TypeScript check after
changing the catalog or translation code. From the repository root:

```bash
npm --prefix dashboard run build
vendor/openterminal/node_modules/.bin/tsc --project vendor/openterminal/web/tsconfig.json --noEmit --incremental false
node <<'NODE'
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const esbuild = require('./dashboard/node_modules/esbuild');
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'alghrest-dashboard-tests-'));
for (const file of fs.readdirSync('dashboard/tests').filter(name => name.endsWith('.test.ts')).sort()) {
  const output = path.join(directory, file.replace(/\.ts$/, '.cjs'));
  esbuild.buildSync({ entryPoints: ['dashboard/tests/' + file], bundle: true,
    platform: 'node', format: 'cjs', outfile: output });
  require(output);
}
NODE
```

The last command executes the compiled suites in the same Node process and
prints their TAP test results. A failed assertion sets a nonzero exit status.
The broader `node scripts/check_research.mjs` workflow also includes the language
suite, but starts an isolated workspace and requires all four ports to be free.
A build/type check does not replace visual review of both languages.
