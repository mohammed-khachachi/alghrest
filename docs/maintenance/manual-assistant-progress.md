# Manual assistant and paper activation — 2026-09-28

Implemented for Nasdaq NQ/MNQ manual research and Earn2Trade EOD evaluation
tracking. The assistant has no order or portfolio write path.

- [x] Account/venue-aware reducing orders; an isolated 5 USDT round-trip passes.
- [x] Public Binance spot marks and sourced Coinbase USDT/USD conversion.
- [x] Supervised local paper services; fixed RiskGovernor consumer startup.
- [x] Separate assistant API, SQLite watchlists/reports/evaluation journal.
- [x] Public news, optional crypto derivatives, dated-contract Nasdaq import.
- [x] Conditional scenarios, regular-hours clock, drawdown/daily-loss/consistency
  monitoring and constrained contract planning from explicit manual inputs.
- [x] Optional independent Kafka intelligence consumer; no producer.
- [x] Arabic dashboard page with lazy loading and separate service connection.
- [x] Unit/API/isolation tests, full 70% gate and dashboard build.
- [x] Browser verification of unavailable MNQ data and risk calculation.

Actual paper book remains paper_trading:paper-main, revision 0: 150 USDT,
no positions, fills or deposits. Paper readiness was verified with real public
marks. No strategies or live orders were enabled. Monthly funding remains an
explicit operator action, never automatic.

User inputs still needed for personal use: chosen Earn2Trade program/account
rules, and the user's licensed CME price feed/export. No plan size, broker,
subscription or market price was invented. These are configuration/data inputs,
not failed implementation gates. Funded-account trailing drawdown, live CME
streaming, full earnings calendars and automated news forecasts are not built.
See ../manual-assistant.md for the precise capabilities and limitations.
