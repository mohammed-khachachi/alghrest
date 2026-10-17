# Research reliability and per-symbol alerts

Scope approved in chat on 2026-10-16, tracked by the active Goal.

1. Replace VIX close-only synthetic candles with genuine OHLC from Yahoo; bounded Stooq fallback. Keep unavailable explicit if both fail. Keep FRED daily-close quote fallback, label its date accurately and bound network calls.
2. Keep original quote timestamps and provider-supplied labels distinct from receipt time. Nasdaq ET text stays unconverted; Binance ticker window close is not called a trade timestamp. Never infer Nasdaq candle frequency from sample spacing.
3. Expose per-symbol/feed/provider diagnostic attempts (quotes, history, Yahoo RSS and Google RSS), safe failure codes, last successful request and last failure. Diagnostics are bounded in-memory observations since the native process started, never a reconstructed uptime history. Cache reads do not count as new successful requests. Authenticated ALGHREST bridge forwards no access token to native providers.
4. Add deterministic descriptive alerts in the research journal, comparing the displayed report with its prior snapshot. Rules: trend enters/leaves an ordered SMA20/SMA50 arrangement; RSI crosses 30/70; ATR/close changes by at least 25% relative AND 0.25 percentage points absolute. These are transparent UI thresholds, not calibrated trading recommendations. Require matching known provider/timeframe, a newer bar, increasing fetch clocks, current usable indicator guards, and bounded bar age. The feed includes a potentially forming last bar, so alerts are explicitly provisional; completion is not inferred from exchange hours. Suppress unverified, stale, imported, same-bar or incomparable readings. No background watcher or messages. Historical selections are explicitly dated.

Acceptance: red regression for VIX first; provider timeout/error/cache/clock tests; bridge identity/auth/sanitization tests; alert trigger and suppression tests; native and dashboard builds; existing research regression suites; real local provider checks where available; browser review. Preserve operator journal payloads and unrelated dirty files. No execution agents, orders, broker connections, .env edits, monitoring restart or Git publication.

Baseline and receipts: artifacts/research-reliability-alerts-20261016/.

Evidence: the native VIX HTTP request exceeded 30 seconds. Bounded public probes: FRED timed out at six seconds; Yahoo returned 132 VIX bars in 309 ms. Nasdaq primaryData includes lastTradeTimestamp text with ET, and Binance includes closeTime. These are one-time observations, not availability guarantees.

Primary references: [FRED VIXCLS](https://fred.stlouisfed.org/series/VIXCLS) declares Daily, Close; [Binance market data](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market) documents ticker window clocks separately from trade timestamps.
