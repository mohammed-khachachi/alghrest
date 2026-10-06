# 0002 — Explicit runtime modes and bounded research work

Date: 2026-09-29
Status: Accepted; initial implementation verified

## Context

ALGHREST already has durable accounting and execution recovery, six application
packages with enforced dependency direction, an isolated manual assistant and a
small paper supervisor. Running the full Compose topology is unnecessarily heavy
for manual research or the seven-agent paper pipeline. Within the assistant,
each market downloaded the same five RSS feeds. Dashboard builders continued
reading state without viewers. BaseAgent imported Pandas for a type annotation.

## Decision

Keep one repository with cohesive domain modules (`core/accounting`,
`core/execution`, `core/risk`, `core/advisory`) and explicit process boundaries.
Agents continue to exchange Kafka/Redis contracts; accounting truth stays in
PostgreSQL. Research must not own financial state or bypass approval/risk gates.
Do not merge the execution, accountant and research processes to save memory:
shared failures, credentials and event-loop stalls would enlarge their impact.

Provide a mode-aware operator command that reuses the maintained deployments:

- `research`: the standalone manual assistant, bounded HTTP concurrency, a
  separate SQLite volume, no trading environment file or broker connection.
- `paper`: the existing single-broker local infrastructure plus seven supervised
  agents. Explicit statement-backed opening balances remain required. No CIO,
  strategies, Telegram or LLM calls are introduced by this mode.
- `full`: the existing larger Compose topology, explicitly selected, intended
  here for development/paper only. The convenience launcher refuses a live host
  setting or a resolved live container setting. This is not production approval.

Heavy research runs on report requests, with the existing 25-second overall
limit, one report refresh at a time, a 60-second report cache and a minimum
three-second refresh interval. Feed downloads are shared across markets within
that service process, before instrument/interest filtering. Successful feeds
expire after 300 seconds; outages retry after 30 seconds. No failed refresh
returns an old success as current. Parsing runs off the event loop with a
one-megabyte decoded RSS limit and a maximum of 50 headlines per feed.

Display-only periodic builders wait while there are no WebSocket clients.
Risk-alert subscription, the Risk Governor, accounting, recovery and all hard
limits continue independently. A reconnect still receives the full snapshot.
Browser routes load lazily, leaving the assistant independent of the trading
WebSocket connection.

The existing GARCH forecast is unchanged; the unused EGARCH diagnostic fit is
removed from its runtime path. EGARCH's helper remains available for explicit
research. Numerical replay compares complete forecast fields, excluding generated
identity and creation time. Pandas is imported by modules that use it at runtime,
not by BaseAgent merely to annotate a backtest method.

## Enforcement and validation

The architecture checker now rejects manual-assistant imports of accounting,
execution, Redis, PostgreSQL and exchange adapters in addition to the existing
package rules. Like the original checker, this is a static guard, not proof
against dynamic imports or a replacement for network/credential isolation.

Tests cover shared concurrent fetches, independent market filtering, publication
age, outage TTL and recovery, cancellation, oversized RSS, viewer disconnect/
reconnect and runtime mode selection. The full suite retains its 70% gate and
exercises real PostgreSQL/Redis and an isolated Kafka crash/replay workflow.
See [measured results](../maintenance/runtime-efficiency.md).

## Tradeoffs and remaining boundaries

The cache is process-local: two API workers have two caches. Use the supplied
single-worker assistant deployment; do not add Redis access to this isolated
process just to share its cache. Other intelligence services retain their own
contracts and source collection. This change does not consolidate all news
collection across the system.

The full deployment, LLM decision policies and indicator mathematics retain
existing semantics. No new agent framework or always-running coordinator was
added. Global LLM spending limits, model routing, distributed feed collection,
and consolidation of additional analytical workers need their own workload
measurements and decision-quality evaluations before implementation.

The earlier security findings are separate outstanding work; these performance
changes do not claim to remediate them. A full-stack latency, Kafka lag, CPU and
LLM-billing baseline was unavailable because no matching host application
processes were observed. Import and controlled-workload results must not be
reported as whole-system savings or investment performance.

## Research informing the decision

- [Towards a Science of Scaling Agent Systems, revised April 2026](https://arxiv.org/abs/2512.08296): coordination benefits depend on task structure.
- [Why Do Multi-Agent LLM Systems Fail?, revised October 2025](https://arxiv.org/abs/2503.13657): system design, alignment and verification are recurring failure categories.
- [Anthropic: Decoupling the brain from the hands, April 2026](https://www.anthropic.com/engineering/managed-agents): durable state and independently replaceable orchestration/tools.

These sources concern agent systems; they do not establish a universal optimum
for trading infrastructure. The specific boundaries above are our engineering
choice for this repository and its current operating scale.
