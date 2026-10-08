"""Kafka client authentication shared by the trading bus and its metrics reader."""

import ssl
from typing import Any, Literal

from core.config import settings


def aiokafka_security(service: Literal["trading", "advisory"] = "trading") -> dict[str, Any]:
    prefix = "kafka" if service == "trading" else "advisory_kafka"
    protocol = getattr(settings, f"{prefix}_security_protocol")
    username = getattr(settings, f"{prefix}_sasl_username")
    password = getattr(settings, f"{prefix}_sasl_password").get_secret_value()
    cafile = getattr(settings, f"{prefix}_ssl_cafile")
    if protocol == "PLAINTEXT":
        if settings.is_live:
            raise ValueError("Live Kafka requires authenticated TLS (SASL_SSL)")
        return {}
    if settings.is_live and protocol != "SASL_SSL":
        raise ValueError("Live Kafka requires authenticated TLS (SASL_SSL)")
    if not username or not password:
        raise ValueError("Kafka SASL credentials are required")
    options: dict[str, Any] = {
        "security_protocol": protocol,
        "sasl_mechanism": "PLAIN",
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
        "sasl.mechanism": "PLAIN",
        "sasl.username": options["sasl_plain_username"],
        "sasl.password": options["sasl_plain_password"],
    }
    if settings.kafka_ssl_cafile:
        result["ssl.ca.location"] = settings.kafka_ssl_cafile
    return result
