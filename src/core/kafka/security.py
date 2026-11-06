"""Kafka client authentication, SASL/SCRAM builders, and worker ACL matrix."""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import Any, Final, Literal

from core.config import settings
from core.data.models import KafkaTopic

SupportedSaslMechanism = Literal["PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"]
SUPPORTED_SASL_MECHANISMS: Final[frozenset[str]] = frozenset(
    {"PLAIN", "SCRAM-SHA-256", "SCRAM-SHA-512"}
)


@dataclass(frozen=True)
class KafkaRoleACL:
    """Least-privilege Kafka ACL policy for a worker principal."""

    principal: str
    allow_write_topics: frozenset[str]
    allow_read_topics: frozenset[str]
    deny_write_topics: frozenset[str]
    consumer_group_prefix: str


_EXECUTION_CRITICAL_TOPICS: Final[frozenset[str]] = frozenset(
    {
        KafkaTopic.PROPOSALS_APPROVED.value,
        KafkaTopic.ORDERS_PENDING.value,
        KafkaTopic.ORDERS_APPROVED.value,
        KafkaTopic.ORDERS_EXECUTED.value,
        KafkaTopic.FILLS_CONFIRMED.value,
    }
)

KAFKA_ROLE_ACLS: Final[dict[str, KafkaRoleACL]] = {
    "tier1_executive": KafkaRoleACL(
        principal="User:tier1_executive",
        allow_write_topics=frozenset(
            {
                KafkaTopic.PROPOSALS_APPROVED.value,
                KafkaTopic.RISK_ALERTS.value,
            }
        ),
        allow_read_topics=frozenset(
            {
                KafkaTopic.PROPOSALS_BUS.value,
                KafkaTopic.MACRO_REGIME.value,
                KafkaTopic.PORTFOLIO_STATE.value,
                KafkaTopic.FILLS_CONFIRMED.value,
                KafkaTopic.ORDERS_EXECUTED.value,
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.RISK_ALERTS.value,
            }
        ),
        deny_write_topics=frozenset(
            {
                KafkaTopic.ORDERS_PENDING.value,
                KafkaTopic.ORDERS_APPROVED.value,
                KafkaTopic.ORDERS_EXECUTED.value,
                KafkaTopic.FILLS_CONFIRMED.value,
            }
        ),
        consumer_group_prefix="alghrest.tier1.",
    ),
    "tier2_intelligence": KafkaRoleACL(
        principal="User:tier2_intelligence",
        allow_write_topics=frozenset(
            {
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.NEWS_TAGGED.value,
                KafkaTopic.SENTIMENT_SCORED.value,
                KafkaTopic.ONCHAIN_SIGNALS.value,
                KafkaTopic.MACRO_REGIME.value,
            }
        ),
        allow_read_topics=frozenset(
            {
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.RISK_ALERTS.value,
            }
        ),
        deny_write_topics=_EXECUTION_CRITICAL_TOPICS | {KafkaTopic.PROPOSALS_BUS.value},
        consumer_group_prefix="alghrest.tier2.",
    ),
    "tier3_quant": KafkaRoleACL(
        principal="User:tier3_quant",
        allow_write_topics=frozenset(
            {
                KafkaTopic.INDICATORS_COMPUTED.value,
                KafkaTopic.PATTERNS_DETECTED.value,
                KafkaTopic.VOLATILITY_FORECAST.value,
                KafkaTopic.CORRELATION_MATRIX.value,
            }
        ),
        allow_read_topics=frozenset(
            {
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.NEWS_TAGGED.value,
                KafkaTopic.SENTIMENT_SCORED.value,
                KafkaTopic.ONCHAIN_SIGNALS.value,
                KafkaTopic.MACRO_REGIME.value,
                KafkaTopic.RISK_ALERTS.value,
            }
        ),
        deny_write_topics=_EXECUTION_CRITICAL_TOPICS | {KafkaTopic.PROPOSALS_BUS.value},
        consumer_group_prefix="alghrest.tier3.",
    ),
    "tier4_strategy": KafkaRoleACL(
        principal="User:tier4_strategy",
        allow_write_topics=frozenset({KafkaTopic.PROPOSALS_BUS.value}),
        allow_read_topics=frozenset(
            {
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.INDICATORS_COMPUTED.value,
                KafkaTopic.PATTERNS_DETECTED.value,
                KafkaTopic.VOLATILITY_FORECAST.value,
                KafkaTopic.CORRELATION_MATRIX.value,
                KafkaTopic.MACRO_REGIME.value,
                KafkaTopic.SENTIMENT_SCORED.value,
                KafkaTopic.ONCHAIN_SIGNALS.value,
                KafkaTopic.PORTFOLIO_STATE.value,
                KafkaTopic.RISK_ALERTS.value,
                KafkaTopic.RL_PARAM_UPDATES.value,
            }
        ),
        deny_write_topics=_EXECUTION_CRITICAL_TOPICS,
        consumer_group_prefix="alghrest.tier4.",
    ),
    "tier5_router": KafkaRoleACL(
        principal="User:tier5_router",
        allow_write_topics=frozenset(
            {
                KafkaTopic.ORDERS_PENDING.value,
                KafkaTopic.PROPOSALS_BUS.value,
            }
        ),
        allow_read_topics=frozenset(
            {
                KafkaTopic.PROPOSALS_APPROVED.value,
                KafkaTopic.ORDERS_PENDING.value,
                KafkaTopic.PORTFOLIO_STATE.value,
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.RISK_ALERTS.value,
            }
        ),
        deny_write_topics=frozenset(
            {
                KafkaTopic.PROPOSALS_APPROVED.value,
                KafkaTopic.ORDERS_EXECUTED.value,
                KafkaTopic.FILLS_CONFIRMED.value,
            }
        ),
        consumer_group_prefix="alghrest.tier5.",
    ),
    "tier5_executor": KafkaRoleACL(
        principal="User:tier5_executor",
        allow_write_topics=frozenset(
            {
                KafkaTopic.ORDERS_EXECUTED.value,
                KafkaTopic.FILLS_CONFIRMED.value,
            }
        ),
        allow_read_topics=frozenset(
            {
                KafkaTopic.ORDERS_PENDING.value,
                KafkaTopic.RISK_ALERTS.value,
            }
        ),
        deny_write_topics=frozenset(
            {
                KafkaTopic.PROPOSALS_BUS.value,
                KafkaTopic.PROPOSALS_APPROVED.value,
                KafkaTopic.ORDERS_PENDING.value,
            }
        ),
        consumer_group_prefix="alghrest.tier5.",
    ),
    "tier7_monitoring": KafkaRoleACL(
        principal="User:tier7_monitoring",
        allow_write_topics=frozenset(
            {
                KafkaTopic.PORTFOLIO_STATE.value,
                KafkaTopic.RISK_ALERTS.value,
                KafkaTopic.RL_PARAM_UPDATES.value,
            }
        ),
        allow_read_topics=frozenset(
            {
                KafkaTopic.FILLS_CONFIRMED.value,
                KafkaTopic.ORDERS_EXECUTED.value,
                KafkaTopic.ORDERS_PENDING.value,
                KafkaTopic.PROPOSALS_BUS.value,
                KafkaTopic.PROPOSALS_APPROVED.value,
                KafkaTopic.PORTFOLIO_STATE.value,
                KafkaTopic.RISK_ALERTS.value,
                KafkaTopic.PRICES_REALTIME.value,
            }
        ),
        deny_write_topics=_EXECUTION_CRITICAL_TOPICS,
        consumer_group_prefix="alghrest.tier7.",
    ),
    "advisory_reader": KafkaRoleACL(
        principal="User:advisory_reader",
        allow_write_topics=frozenset(),
        allow_read_topics=frozenset(
            {
                KafkaTopic.PRICES_REALTIME.value,
                KafkaTopic.NEWS_TAGGED.value,
                KafkaTopic.SENTIMENT_SCORED.value,
                KafkaTopic.MACRO_REGIME.value,
                KafkaTopic.INDICATORS_COMPUTED.value,
            }
        ),
        deny_write_topics=frozenset(t.value for t in KafkaTopic),
        consumer_group_prefix="alghrest.advisory.",
    ),
}


def authorize_topic_operation(
    role: str,
    topic: str,
    operation: Literal["Read", "Write"],
) -> bool:
    """Evaluate default-deny + explicit-deny Kafka ACL semantics for a worker role."""
    acl = KAFKA_ROLE_ACLS.get(role)
    if acl is None:
        return False
    if operation == "Write":
        if topic in acl.deny_write_topics:
            return False
        return topic in acl.allow_write_topics
    return topic in acl.allow_read_topics


def scram_jaas_config(username: str, password: str) -> str:
    """Build a Kafka SCRAM JAAS login module string."""
    if not username or not password:
        raise ValueError("SCRAM JAAS requires non-empty username and password")
    return (
        "org.apache.kafka.common.security.scram.ScramLoginModule required "
        f'username="{username}" password="{password}";'
    )


def aiokafka_security(service: Literal["trading", "advisory"] = "trading") -> dict[str, Any]:
    prefix = "kafka" if service == "trading" else "advisory_kafka"
    protocol = getattr(settings, f"{prefix}_security_protocol")
    mechanism = str(getattr(settings, f"{prefix}_sasl_mechanism", "PLAIN"))
    username = getattr(settings, f"{prefix}_sasl_username")
    password = getattr(settings, f"{prefix}_sasl_password").get_secret_value()
    cafile = getattr(settings, f"{prefix}_ssl_cafile")
    if protocol == "PLAINTEXT":
        if settings.is_live:
            raise ValueError("Live Kafka requires authenticated TLS (SASL_SSL)")
        return {}
    if settings.is_live and protocol != "SASL_SSL":
        raise ValueError("Live Kafka requires authenticated TLS (SASL_SSL)")
    if mechanism not in SUPPORTED_SASL_MECHANISMS:
        raise ValueError(f"Unsupported Kafka SASL mechanism: {mechanism}")
    if not username or not password:
        raise ValueError("Kafka SASL credentials are required")
    options: dict[str, Any] = {
        "security_protocol": protocol,
        "sasl_mechanism": mechanism,
        "sasl_plain_username": username,
        "sasl_plain_password": password,
    }
    if protocol == "SASL_SSL":
        options["ssl_context"] = ssl.create_default_context(cafile=cafile or None)
    return options


def confluent_security() -> dict[str, Any]:
    options = aiokafka_security()
    if not options:
        return {}
    result = {
        "security.protocol": options["security_protocol"],
        "sasl.mechanism": options["sasl_mechanism"],
        "sasl.username": options["sasl_plain_username"],
        "sasl.password": options["sasl_plain_password"],
    }
    if settings.kafka_ssl_cafile:
        result["ssl.ca.location"] = settings.kafka_ssl_cafile
    return result
