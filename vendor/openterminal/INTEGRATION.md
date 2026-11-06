# ALGHREST local integration

This is a pinned runtime snapshot of ErTasselli/OpenTerminal, licensed under MIT.
See `LICENSE` and `UPSTREAM.json` for attribution and source identities.

Run from the ALGHREST root with `node scripts/openterminal.mjs` after `npm ci`
in this folder. The web interface is at `http://127.0.0.1:3001`; its API is at
`http://127.0.0.1:4001`. The root launcher isolates environment variables and checks
ports before starting. AI is disabled. Manual portfolio entries belong to this
workspace alone. Its journal and generated key are kept in this folder's ignored
`data/` directory.

Integration instructions and limits are in
`../../docs/maintenance/openterminal-integration.md`. `README.md` is retained from
upstream and describes upstream defaults, rather than the integrated launcher.

The complete workspace runs with `node scripts/run_research.mjs` from the
ALGHREST root. `/research` embeds the terminal and analyzes its actual selected
symbol using local quotes, six-month history and news. No MES/MNQ mapping or
external futures file is required there. `IntegrationBridge.tsx` synchronizes
public symbols with the fixed parent origin; it transfers no credentials,
account state or quotes. The manual assistant remains separately available.

The local interface also supports English and Arabic. Its header language
selector follows the parent dashboard while embedded and saves a preference
when used separately. Language messages contain only a validated `en`/`ar` code
and use the existing parent origin/window checks. Local dictionaries in
`web/i18n/` translate interface text without external translation calls; original
news, names, user entries and video content remain in their source language.

Yahoo requests use Node's native User-Agent by default. The previous random
browser identities returned HTTP 429 for public chart requests that succeeded
with Node's default, causing `/api/quotes` and `/api/history/:symbol` to return
502 when other providers failed. An explicit `YAHOO_USER_AGENT` override remains
supported. `server/src/providers/yahoo.test.ts` covers the history route's
recovery and the explicit override. Live verification after the change returned
200 through the web proxy for AAPL, BTC-USD and ES=F quotes and ES=F 5-minute
history. Public-provider availability and data freshness remain independent.
