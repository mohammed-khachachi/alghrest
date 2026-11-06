#!/bin/bash
# =============================================================================
# ALGHREST — Kafka Topic Initialization Script
# Creates all 16 system topics with production-grade configurations.
# Idempotent: --if-not-exists prevents errors on re-runs.
# =============================================================================

set -euo pipefail

BOOTSTRAP="${BOOTSTRAP_SERVERS:-kafka-1:29092,kafka-2:29092,kafka-3:29092}"
REPLICATION=3
COMMAND_CONFIG="${KAFKA_COMMAND_CONFIG:-/run/secrets/kafka-client.properties}"
CMD="kafka-topics --bootstrap-server ${BOOTSTRAP} --command-config ${COMMAND_CONFIG}"

echo "========================================================"
echo " ALGHREST Kafka Topic Initialization"
echo " Bootstrap: ${BOOTSTRAP}"
echo "========================================================"

wait_for_kafka() {
    echo "Waiting for Kafka cluster to be ready..."
    local max_attempts=60
    local attempt=0
    until ${CMD} --list >/dev/null 2>&1; do
        attempt=$((attempt + 1))
        if [ ${attempt} -ge ${max_attempts} ]; then
            echo "ERROR: Kafka not ready after ${max_attempts} attempts. Exiting."
            exit 1
        fi
        echo "  Attempt ${attempt}/${max_attempts} — sleeping 5s..."
        sleep 5
    done
    echo "Kafka cluster is ready."
}

create_topic() {
    local topic=$1
    local partitions=$2
    local retention_ms=$3
    local extra_configs="${4:-}"

    local config_args="--config retention.ms=${retention_ms} --config compression.type=lz4"
    if [ -n "${extra_configs}" ]; then
        config_args="${config_args} ${extra_configs}"
    fi

    ${CMD} --create \
        --if-not-exists \
        --topic "${topic}" \
        --partitions "${partitions}" \
        --replication-factor "${REPLICATION}" \
        ${config_args}

    echo "  [OK] ${topic} (${partitions} partitions, retention=${retention_ms}ms)"
}

wait_for_kafka

echo ""
echo "Creating Tier 2 → All: Market Data Topics"
echo "─────────────────────────────────────────"

# High-throughput price feed — short retention, many partitions
# Partitioned by symbol hash for ordered per-symbol processing
create_topic "prices.realtime"    12  3600000  \
    "--config max.message.bytes=1048576 --config segment.ms=3600000"

echo ""
echo "Creating Tier 2 → Tier 3: Intelligence Topics"
echo "─────────────────────────────────────────────"

# News — moderate volume, 7 day retention
create_topic "news.tagged"         3  604800000  \
    "--config max.message.bytes=5242880"

# Sentiment scores per asset — hourly computation
create_topic "sentiment.scored"    6  604800000

# On-chain metrics and whale alerts
create_topic "onchain.signals"     3  604800000  \
    "--config max.message.bytes=2097152"

echo ""
echo "Creating Tier 2 → Tier 1: Macro Regime Topic"
echo "─────────────────────────────────────────────"

# Single partition — regime is a global signal, order matters
# 30-day retention for historical regime analysis
create_topic "macro.regime"        1  2592000000  \
    "--config cleanup.policy=compact,delete --config min.cleanable.dirty.ratio=0.1"

echo ""
echo "Creating Tier 3 → Tier 4: Quantitative Signal Topics"
echo "─────────────────────────────────────────────────────"

# Technical indicators — computed per-symbol, high volume
create_topic "indicators.computed" 12  3600000  \
    "--config max.message.bytes=2097152"

# CV pattern detections — low frequency but large payloads (images)
create_topic "patterns.detected"   3  604800000  \
    "--config max.message.bytes=10485760"

# Volatility forecasts per asset — 7-day retention
create_topic "volatility.forecast" 6  604800000

# Correlation matrix — compact (only latest matters), 30d history
create_topic "correlation.matrix"  1  2592000000  \
    "--config cleanup.policy=compact,delete --config min.cleanable.dirty.ratio=0.1"

echo ""
echo "Creating Tier 4 → Tier 1: Strategy Proposal Topics"
echo "────────────────────────────────────────────────────"

# Trade proposals — compliance-grade retention (90 days)
create_topic "proposals.bus"       6  7776000000  \
    "--config max.message.bytes=1048576"

echo ""
echo "Creating Tier 1 → Tier 5: Approved Proposal & Order Topics"
echo "──────────────────────────────────────────────────────────"

# Proposals approved by gateway (Tier 1 ProposalApprover) — 90-day audit
create_topic "proposals.approved"  6  7776000000

# Orders pending exchange placement (post-routing/optimisation)
create_topic "orders.pending"      6  7776000000

# Legacy alias kept for backwards compatibility (not used by new pipeline)
create_topic "orders.approved"     6  7776000000

echo ""
echo "Creating Tier 5 → Tier 7: Execution Confirmation Topics"
echo "────────────────────────────────────────────────────────"

# Execution confirmations — compliance retention (90 days)
create_topic "orders.executed"     6  7776000000

# Exchange fills — long retention (1 year) for audit/tax
create_topic "fills.confirmed"     6  31536000000  \
    "--config max.message.bytes=524288"

echo ""
echo "Creating Tier 7 → All: Portfolio State Topic"
echo "─────────────────────────────────────────────"

# Portfolio state — compacted, single source of truth
# Keep last known state forever (compacted)
create_topic "portfolio.state"     1  -1  \
    "--config cleanup.policy=compact --config min.cleanable.dirty.ratio=0.01 --config segment.ms=86400000"

echo ""
echo "Creating Tier 1 (CRO) → All: Risk Alert Topics"
echo "─────────────────────────────────────────────────"

# Risk alerts — compliance retention (1 year), immutable audit log
create_topic "risk.alerts"         3  31536000000  \
    "--config max.message.bytes=524288"

echo ""
echo "Creating Tier 7 (RL) → Tier 4: Parameter Update Topics"
echo "────────────────────────────────────────────────────────"

# RL parameter updates — compact (only latest params needed)
# 1-year retention for reproducibility
create_topic "rl.param.updates"    1  31536000000  \
    "--config cleanup.policy=compact --config min.cleanable.dirty.ratio=0.1"

echo ""
echo "========================================================"
echo " Verifying all topics exist..."
echo "========================================================"
${CMD} --list | sort

EXPECTED_TOPICS=(
    "prices.realtime"
    "news.tagged"
    "sentiment.scored"
    "onchain.signals"
    "macro.regime"
    "indicators.computed"
    "patterns.detected"
    "volatility.forecast"
    "correlation.matrix"
    "proposals.bus"
    "proposals.approved"
    "orders.pending"
    "orders.approved"
    "orders.executed"
    "fills.confirmed"
    "portfolio.state"
    "risk.alerts"
    "rl.param.updates"
)

missing=0
for topic in "${EXPECTED_TOPICS[@]}"; do
    if ! ${CMD} --list 2>/dev/null | grep -q "^${topic}$"; then
        echo "  [MISSING] ${topic}"
        missing=$((missing + 1))
    fi
done

if [ ${missing} -gt 0 ]; then
    echo "ERROR: ${missing} topics are missing!"
    exit 1
fi

echo ""
echo "========================================================"
echo " All 18 Kafka topics initialized successfully."
echo "========================================================"

if [ -f "/kafka-acls.sh" ]; then
    /bin/bash /kafka-acls.sh
elif [ -f "$(dirname "$0")/kafka-acls.sh" ]; then
    /bin/bash "$(dirname "$0")/kafka-acls.sh"
fi
