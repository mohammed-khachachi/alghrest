# Local access and bounded AI operation

This setup targets a single operator on a trusted Linux/WSL host. It does not
turn the full stack into an Internet-facing deployment. Keep `ENVIRONMENT` in
`paper_trading` or `development` and DeFi disabled.

## Prepare access

From the repository root, run `python -m scripts.configure_access` in the project
environment. On Windows, run this step inside WSL: native Windows ACL setup is
not implemented and the command stops before writing anything there.

The command creates missing API, advisory, Kafka and full-stack PostgreSQL keys
in `.env`, preserves existing values, and generates the two read-only container
credential files in `.secrets/`. It never prints secrets. The host directory is
owner-only; the individual mounted files are readable by the container service
UIDs. Both locations are excluded from version control and image builds. `.env`
is replaced atomically with owner-only permissions. Existing unsafe values are
reported, not silently rotated.

Start only the mode you need with `python -m scripts.runtime research|paper|full
start` (replace the mode alternatives with one mode). In the dashboard, enter
`API_ACCESS_TOKEN` from your local `.env`; on the research page, enter the
separate `ADVISORY_ACCESS_TOKEN`. Do not paste these into a conversation. Tokens
stay in page memory and must be re-entered after reloading. HTTP uses a bearer
header; browser WebSockets offer `alghrest.v1` plus an authentication protocol,
and the server selects only `alghrest.v1`, never the token. The demo mock server
continues to accept a blank key and must stay local.

Missing/weak server tokens fail closed. HTTP `/health/live` is deliberately
public and returns only liveness. Financial health, readiness, metrics, docs and
all WebSockets require authentication. Prometheus reads its bearer token from
the generated file. CORS preflight is permitted without granting data access.
Use the configured origin lists when changing the dashboard's local URL.

Telegram commands, including reads and `/start`, require the configured
administrator in their own private chat. Broadcasts go only to the explicitly
configured administrator/chat. Historical Redis subscriptions grant no access.

## Infrastructure boundaries

Full Compose publishes ports on `127.0.0.1` only. Both Kafka broker client
listeners require SASL/PLAIN, with distinct broker and application passwords.
The initializer, schema registry, metrics reader and Kafka UI use authentication.
Kafka UI, Redis, monitoring and the Docker bridge remain trusted administrative
surfaces: application-level credentials and topic ACLs per agent are **not**
provided by this deployment. Do not attach untrusted containers to that bridge.

SASL_PLAINTEXT authenticates but does not encrypt traffic. The default full stack
is for one trusted host. For remote/live operation, provision TLS listeners and
use `KAFKA_SECURITY_PROTOCOL=SASL_SSL` plus `KAFKA_SSL_CAFILE` as appropriate.
Live clients reject plaintext transports. Do not expose services by simply
changing the bind address. The independent local paper/test stack remains on
its dedicated loopback ports and uses plaintext Kafka; it is not a live target.

There is no database password fallback. An existing PostgreSQL volume keeps its
original database password: changing `.env` does not rotate a database user.
Migrate/rotate an existing deployment deliberately; never delete its volume to
apply these settings. This work did not rotate existing database users.

The research Compose project gets only its own UI key, isolated storage and no
trading network. Its optional Kafka tap remains disabled. To enable a tap in a
custom deployment, first provision a **separate read-only Kafka principal** with
READ/DESCRIBE on `news.tagged`, `indicators.computed`, `macro.regime`,
`sentiment.scored`, `volatility.forecast`, and access to group
`alghrest.manual-assistant.readonly.v1`. Set `ADVISORY_KAFKA_SERVERS`,
`ADVISORY_KAFKA_SECURITY_PROTOCOL`, `ADVISORY_KAFKA_SASL_USERNAME`,
`ADVISORY_KAFKA_SASL_PASSWORD` and optionally `ADVISORY_KAFKA_SSL_CAFILE`.
The tap never falls back to trading credentials. Broker ACL provisioning and
cross-network access are not enabled automatically. `agent_tap_enabled` means
configured, not connected; freshness of received intelligence remains decisive.

## AI allowance

Apply `infra/migrations/004_ai_budget.sql` to the configured database before
running AI agents. Local paper provisioning applies it idempotently:
`python -m scripts.paper provision`. New full-stack databases apply it on first
initialization; existing volumes require migration separately.

Defaults shared across CIO/news workers in the same environment/database:

| Setting | Default | Meaning |
| --- | --- | --- |
| `AI_DAILY_BUDGET_USD` | 1 | Maximum daily reserved cost estimate, UTC |
| `AI_DAILY_MAX_CALLS` | 200 | Maximum reserved calls, including failures |
| `AI_REQUEST_TIMEOUT_SECONDS` | 30 | Bound on an individual paid request |
| `AI_MAX_PROMPT_BYTES` | 32768 | System + user UTF-8 input bound |
| `AI_DECISION_REFRESH_SECONDS` | 900 | Refresh unchanged CIO inputs at most this often |

Before contacting Claude, workers atomically reserve in PostgreSQL. Concurrent
workers and restarts cannot reset the daily row, and Redis eviction cannot erase
it. A missing table/database, exhausted allowance or oversized prompt blocks the
call. Timeouts and uncertain failures retain reservations; SDK retries are off.
Set either daily limit to zero to stop paid calls. This work made no paid calls.

The estimate conservatively counts input UTF-8 bytes plus 1,024 framing tokens,
uses cache-write rates and reserves all allowed output tokens (512 CIO / 256
news), with no refund for cache hits or shorter answers. It is an application
allowance, not an authoritative invoice cap: maintain provider-side billing
limits and review the pinned rates when models/pricing change. Current rates in
`core/ai/budget.py` come from [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing).

CIO skips unchanged summarized inputs, prunes expired signals even when ingestion
is idle, bounds the signal window to 20 entries, and unwraps agent payloads.
Invalid/unknown/negative/non-finite/over-allocated strategy weights are rejected.
A failed request retains the current allocation and is eligible for a later
retry. News without a model or allowance is not published as fabricated neutral
analysis. Existing trade sizing, kill-switch and loss limits still apply.

## Reproduce validation

Use `python -m scripts.test_with_services` with the isolated paper stack for the
complete suite and unchanged 70% branch-coverage gate. Set `KAFKA_AUTH_TESTS=1`
to include the disposable SASL broker test; it uses the paper stack's cached
`apache/kafka:4.3.1` image, no runtime topics and no persistent volume. Full
Confluent 7.6 multi-broker deployment is a separate validation step.

The paper transport test uses synthetic funds in a unique book/topic and Redis
DB 15. It verifies crash/replay, 22 orders, 100 duplicate fills, exact fees,
portfolio reconciliation and halt admission; it cleans its own records. The
latency/RSS/CPU output describes that bounded test process, not the entire
37-service stack or real exchange execution. Run it with `-s` to see `PAPER_LOAD`.
AI quality checks here concern input/output and failure behavior; they do not
establish forecast accuracy or trading profitability.
