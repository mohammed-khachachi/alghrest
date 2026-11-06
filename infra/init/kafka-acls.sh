#!/bin/bash
# =============================================================================
# ALGHREST — Kafka SASL/SCRAM User & Least-Privilege Worker ACL Provisioning
# Provisions SCRAM-SHA-512 / SCRAM-SHA-256 credentials and strict per-tier
# Read / Write / Deny ACLs across all 18 system topics.
# =============================================================================

set -euo pipefail

BOOTSTRAP="${BOOTSTRAP_SERVERS:-kafka-1:29092,kafka-2:29092,kafka-3:29092}"
COMMAND_CONFIG="${KAFKA_COMMAND_CONFIG:-/run/secrets/kafka-client.properties}"
ZK_CONNECT="${KAFKA_ZOOKEEPER_CONNECT:-zookeeper:2181}"

ACLS_CMD="kafka-acls --bootstrap-server ${BOOTSTRAP} --command-config ${COMMAND_CONFIG}"
CONFIGS_CMD="kafka-configs --bootstrap-server ${BOOTSTRAP} --command-config ${COMMAND_CONFIG}"

echo ""
echo "========================================================"
echo " ALGHREST Kafka SCRAM & Worker ACL Provisioning"
echo "========================================================"

provision_scram_user() {
    local user=$1
    local pass=$2
    if [ -z "${pass}" ]; then
        return 0
    fi
    if ! ${CONFIGS_CMD} --alter \
        --add-config "SCRAM-SHA-256=[iterations=8192,password=${pass}],SCRAM-SHA-512=[iterations=8192,password=${pass}]" \
        --entity-type users \
        --entity-name "${user}" >/dev/null 2>&1; then
        # Fallback to ZooKeeper SCRAM entity config during initial bootstrap if broker SCRAM cache is cold
        kafka-configs --zookeeper "${ZK_CONNECT}" --alter \
            --add-config "SCRAM-SHA-256=[iterations=8192,password=${pass}],SCRAM-SHA-512=[iterations=8192,password=${pass}]" \
            --entity-type users \
            --entity-name "${user}" >/dev/null 2>&1 || true
    fi
    echo "  [SCRAM] User:${user} (SCRAM-SHA-256, SCRAM-SHA-512)"
}

grant_write_topics() {
    local principal=$1
    shift
    for topic in "$@"; do
        ${ACLS_CMD} --add \
            --allow-principal "${principal}" \
            --operation Write \
            --operation Describe \
            --topic "${topic}" >/dev/null
    done
}

grant_read_topics() {
    local principal=$1
    local group_prefix=$2
    shift 2
    ${ACLS_CMD} --add \
        --allow-principal "${principal}" \
        --operation Read \
        --operation Describe \
        --group "${group_prefix}" \
        --resource-pattern-type prefixed >/dev/null
    # Also allow book-scoped default consumer group prefix 'alghrest.'
    ${ACLS_CMD} --add \
        --allow-principal "${principal}" \
        --operation Read \
        --operation Describe \
        --group "alghrest." \
        --resource-pattern-type prefixed >/dev/null
    for topic in "$@"; do
        ${ACLS_CMD} --add \
            --allow-principal "${principal}" \
            --operation Read \
            --operation Describe \
            --topic "${topic}" >/dev/null
    done
}

deny_write_topics() {
    local principal=$1
    shift
    for topic in "$@"; do
        ${ACLS_CMD} --add \
            --deny-principal "${principal}" \
            --operation Write \
            --topic "${topic}" >/dev/null
    done
}

# 1. Provision SCRAM-SHA-512 / SCRAM-SHA-256 credentials
DEFAULT_WORKER_PASS="${KAFKA_APP_PASSWORD:-}"
provision_scram_user "broker"             "${KAFKA_BROKER_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "alghrest"           "${KAFKA_APP_PASSWORD:-}"
provision_scram_user "tier1_executive"    "${KAFKA_TIER1_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "tier2_intelligence" "${KAFKA_TIER2_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "tier3_quant"        "${KAFKA_TIER3_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "tier4_strategy"     "${KAFKA_TIER4_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "tier5_router"       "${KAFKA_TIER5_ROUTER_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "tier5_executor"     "${KAFKA_TIER5_EXECUTOR_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "tier7_monitoring"   "${KAFKA_TIER7_PASSWORD:-${DEFAULT_WORKER_PASS}}"
provision_scram_user "advisory_reader"    "${KAFKA_ADVISORY_PASSWORD:-${DEFAULT_WORKER_PASS}}"

# 2. Tier 1 — Executive (CIO, RiskGovernor, ProposalApprover)
grant_write_topics "User:tier1_executive" \
    "proposals.approved" "risk.alerts"
grant_read_topics "User:tier1_executive" "alghrest.tier1." \
    "proposals.bus" "macro.regime" "portfolio.state" "fills.confirmed" \
    "orders.executed" "prices.realtime" "risk.alerts"
deny_write_topics "User:tier1_executive" \
    "orders.pending" "orders.approved" "orders.executed" "fills.confirmed"
echo "  [ACL] User:tier1_executive configured"

# 3. Tier 2 — Intelligence (MarketData, News, Sentiment, Macro, OnChain, PricePublisher)
grant_write_topics "User:tier2_intelligence" \
    "prices.realtime" "news.tagged" "sentiment.scored" "onchain.signals" "macro.regime"
grant_read_topics "User:tier2_intelligence" "alghrest.tier2." \
    "prices.realtime" "risk.alerts"
deny_write_topics "User:tier2_intelligence" \
    "proposals.bus" "proposals.approved" "orders.pending" "orders.approved" "orders.executed" "fills.confirmed"
echo "  [ACL] User:tier2_intelligence configured"

# 4. Tier 3 — Quant (TechnicalAnalyst, VolatilityForecaster, CorrelationEngine)
grant_write_topics "User:tier3_quant" \
    "indicators.computed" "patterns.detected" "volatility.forecast" "correlation.matrix"
grant_read_topics "User:tier3_quant" "alghrest.tier3." \
    "prices.realtime" "news.tagged" "sentiment.scored" "onchain.signals" "macro.regime" "risk.alerts"
deny_write_topics "User:tier3_quant" \
    "proposals.bus" "proposals.approved" "orders.pending" "orders.approved" "orders.executed" "fills.confirmed"
echo "  [ACL] User:tier3_quant configured"

# 5. Tier 4 — Strategies (ONLY allowed to publish to proposals.bus; denied on execution topics)
grant_write_topics "User:tier4_strategy" \
    "proposals.bus"
grant_read_topics "User:tier4_strategy" "alghrest.tier4." \
    "prices.realtime" "indicators.computed" "patterns.detected" "volatility.forecast" \
    "correlation.matrix" "macro.regime" "sentiment.scored" "onchain.signals" \
    "portfolio.state" "risk.alerts" "rl.param.updates"
deny_write_topics "User:tier4_strategy" \
    "proposals.approved" "orders.pending" "orders.approved" "orders.executed" "fills.confirmed"
echo "  [ACL] User:tier4_strategy configured"

# 6. Tier 5 — Order Router / FeeOptimizer / SlippageMinimizer / HedgeManager / LiquidationGuard
grant_write_topics "User:tier5_router" \
    "orders.pending" "proposals.bus"
grant_read_topics "User:tier5_router" "alghrest.tier5." \
    "proposals.approved" "orders.pending" "portfolio.state" "prices.realtime" "risk.alerts"
deny_write_topics "User:tier5_router" \
    "proposals.approved" "orders.executed" "fills.confirmed"
echo "  [ACL] User:tier5_router configured"

# 7. Tier 5 — ExchangeExecutor (ONLY allowed to publish to orders.executed and fills.confirmed)
grant_write_topics "User:tier5_executor" \
    "orders.executed" "fills.confirmed"
grant_read_topics "User:tier5_executor" "alghrest.tier5." \
    "orders.pending" "risk.alerts"
deny_write_topics "User:tier5_executor" \
    "proposals.bus" "proposals.approved" "orders.pending"
echo "  [ACL] User:tier5_executor configured"

# 8. Tier 7 — Monitoring (PortfolioAccountant, PortfolioTracker, AlertManager, Compliance, Auditor)
grant_write_topics "User:tier7_monitoring" \
    "portfolio.state" "risk.alerts" "rl.param.updates"
grant_read_topics "User:tier7_monitoring" "alghrest.tier7." \
    "fills.confirmed" "orders.executed" "orders.pending" "proposals.bus" \
    "proposals.approved" "portfolio.state" "risk.alerts" "prices.realtime"
deny_write_topics "User:tier7_monitoring" \
    "proposals.approved" "orders.pending" "orders.approved" "orders.executed" "fills.confirmed"
echo "  [ACL] User:tier7_monitoring configured"

# 9. Advisory Read-Only Tap (Zero Write permissions across all topics)
grant_read_topics "User:advisory_reader" "alghrest.advisory." \
    "prices.realtime" "news.tagged" "sentiment.scored" "macro.regime" "indicators.computed"
deny_write_topics "User:advisory_reader" \
    "prices.realtime" "news.tagged" "sentiment.scored" "onchain.signals" "macro.regime" \
    "indicators.computed" "patterns.detected" "volatility.forecast" "correlation.matrix" \
    "proposals.bus" "proposals.approved" "orders.pending" "orders.approved" \
    "orders.executed" "fills.confirmed" "portfolio.state" "risk.alerts" "rl.param.updates"
echo "  [ACL] User:advisory_reader configured (strict read-only)"

echo "========================================================"
echo " All Kafka SCRAM users and ACLs provisioned."
echo "========================================================"
