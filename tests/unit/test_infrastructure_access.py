"""Configuration contracts: preserve credentials, no remote unauthenticated listeners."""

from pathlib import Path

import pytest
import yaml
from dotenv import dotenv_values
from pydantic import SecretStr

from core.config import Settings, settings
from core.data.models import KafkaTopic
from core.kafka.security import (
    KAFKA_ROLE_ACLS,
    aiokafka_security,
    authorize_topic_operation,
    confluent_security,
    scram_jaas_config,
)
from scripts.configure_access import configure

pytestmark = pytest.mark.unit
ROOT = Path(__file__).resolve().parents[2]


def test_generate_independent_credentials_once_without_replacing_existing(tmp_path):
    env = tmp_path / ".env"
    env.write_text("ENVIRONMENT=paper_trading\nDATABASE_URL=keep-me\n")
    configure(tmp_path)
    first = env.read_text()
    configure(tmp_path)
    assert env.read_text() == first
    values = dotenv_values(env)
    assert values["DATABASE_URL"] == "keep-me"
    assert values["API_ACCESS_TOKEN"] != values["ADVISORY_ACCESS_TOKEN"]
    assert (env.stat().st_mode & 0o777) == 0o600
    assert ((tmp_path / ".secrets").stat().st_mode & 0o777) == 0o700
    assert (tmp_path / ".secrets/api_access_token").read_text() == values["API_ACCESS_TOKEN"]
    assert values["KAFKA_SSL_KEYSTORE_PASSWORD"] == values["KAFKA_SSL_KEY_PASSWORD"]
    assert values["KAFKA_TIER5_EXECUTOR_PASSWORD"]
    assert (tmp_path / ".secrets/tls/ca.crt").is_file()
    assert (tmp_path / ".secrets/tls/kafka.broker.keystore.p12").is_file()
    assert (tmp_path / ".secrets/tls/kafka.broker.truststore.p12").is_file()
    assert (tmp_path / ".secrets/tls/kafka-client-tls.properties").is_file()


def test_bad_existing_key_is_not_silently_rotated(tmp_path):
    env = tmp_path / ".env"
    env.write_text("API_ACCESS_TOKEN=short\n")
    with pytest.raises(ValueError, match="API_ACCESS_TOKEN"):
        configure(tmp_path)
    assert env.read_text() == "API_ACCESS_TOKEN=short\n"


def test_full_compose_binds_local_and_authenticates_every_broker_listener():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    for service in compose["services"].values():
        assert all(p.startswith("127.0.0.1:") for p in service.get("ports", []))
    for name in ("kafka-1", "kafka-2", "kafka-3"):
        env = compose["services"][name]["environment"]
        assert (
            env["KAFKA_LISTENER_SECURITY_PROTOCOL_MAP"]
            == "INTERNAL:SASL_PLAINTEXT,EXTERNAL:SASL_PLAINTEXT"
        )
        assert "user_alghrest" in env["KAFKA_LISTENER_NAME_INTERNAL_PLAIN_SASL_JAAS_CONFIG"]
        assert (
            env["KAFKA_LISTENER_NAME_EXTERNAL_PLAIN_SASL_JAAS_CONFIG"]
            == env["KAFKA_LISTENER_NAME_INTERNAL_PLAIN_SASL_JAAS_CONFIG"]
        )
    assert ":?" in compose["services"]["timescaledb"]["environment"]["POSTGRES_PASSWORD"]
    assert "alghrest_secure_pass_2024" not in (ROOT / "docker-compose.yml").read_text()
    assert Settings.model_fields["database_url"].default == ""


def test_client_auth_options_and_live_downgrade_guard(monkeypatch):
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(settings, "kafka_security_protocol", "SASL_PLAINTEXT")
    monkeypatch.setattr(settings, "kafka_sasl_username", "app")
    monkeypatch.setattr(settings, "kafka_sasl_password", SecretStr(""))
    with pytest.raises(ValueError, match="credentials"):
        aiokafka_security()
    monkeypatch.setattr(settings, "kafka_sasl_password", SecretStr("secret"))
    assert aiokafka_security()["sasl_plain_password"] == "secret"
    assert confluent_security()["sasl.username"] == "app"
    monkeypatch.setattr(settings, "environment", "live")
    with pytest.raises(ValueError, match="TLS"):
        aiokafka_security()
    monkeypatch.setattr(settings, "kafka_security_protocol", "PLAINTEXT")
    with pytest.raises(ValueError, match="TLS"):
        aiokafka_security()
    monkeypatch.setattr(settings, "kafka_security_protocol", "SASL_SSL")
    assert aiokafka_security()["ssl_context"].check_hostname


def test_advisory_kafka_credentials_are_independent(monkeypatch):
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(settings, "kafka_sasl_username", "trading")
    monkeypatch.setattr(settings, "kafka_sasl_password", SecretStr("trade-secret"))
    monkeypatch.setattr(settings, "advisory_kafka_security_protocol", "SASL_PLAINTEXT")
    monkeypatch.setattr(settings, "advisory_kafka_sasl_username", "research-reader")
    monkeypatch.setattr(settings, "advisory_kafka_sasl_password", SecretStr("read-secret"))
    assert aiokafka_security("advisory")["sasl_plain_username"] == "research-reader"
    assert aiokafka_security("advisory")["sasl_plain_password"] == "read-secret"
    monkeypatch.setattr(settings, "advisory_kafka_sasl_password", SecretStr(""))
    with pytest.raises(ValueError, match="credentials"):
        aiokafka_security("advisory")


def test_unsupported_platform_fails_before_touching_env(monkeypatch, tmp_path):
    with monkeypatch.context() as scoped:
        scoped.setattr("scripts.configure_access.os.name", "nt")
        with pytest.raises(RuntimeError, match="WSL"):
            configure(tmp_path)
    assert not (tmp_path / ".env").exists()


def test_scram_mechanisms_and_jaas_builder(monkeypatch):
    monkeypatch.setattr(settings, "environment", "paper_trading")
    monkeypatch.setattr(settings, "kafka_security_protocol", "SASL_SSL")
    monkeypatch.setattr(settings, "kafka_sasl_mechanism", "SCRAM-SHA-512")
    monkeypatch.setattr(settings, "kafka_sasl_username", "tier5_executor")
    monkeypatch.setattr(settings, "kafka_sasl_password", SecretStr("scram-secret"))

    opts = aiokafka_security()
    assert opts["security_protocol"] == "SASL_SSL"
    assert opts["sasl_mechanism"] == "SCRAM-SHA-512"
    assert opts["sasl_plain_username"] == "tier5_executor"
    assert opts["sasl_plain_password"] == "scram-secret"

    c_opts = confluent_security()
    assert c_opts["security.protocol"] == "SASL_SSL"
    assert c_opts["sasl.mechanism"] == "SCRAM-SHA-512"

    jaas = scram_jaas_config("tier5_executor", "scram-secret")
    assert "ScramLoginModule required" in jaas
    assert 'username="tier5_executor"' in jaas


def test_worker_role_acl_matrix_enforces_least_privilege():
    # Tier 4 strategies can publish ONLY to proposals.bus
    assert authorize_topic_operation("tier4_strategy", KafkaTopic.PROPOSALS_BUS.value, "Write")
    for restricted in (
        KafkaTopic.PROPOSALS_APPROVED.value,
        KafkaTopic.ORDERS_PENDING.value,
        KafkaTopic.ORDERS_APPROVED.value,
        KafkaTopic.ORDERS_EXECUTED.value,
        KafkaTopic.FILLS_CONFIRMED.value,
    ):
        assert not authorize_topic_operation("tier4_strategy", restricted, "Write")

    # Tier 5 executor can publish ONLY to orders.executed and fills.confirmed
    assert authorize_topic_operation("tier5_executor", KafkaTopic.ORDERS_EXECUTED.value, "Write")
    assert authorize_topic_operation("tier5_executor", KafkaTopic.FILLS_CONFIRMED.value, "Write")
    assert not authorize_topic_operation("tier5_executor", KafkaTopic.ORDERS_PENDING.value, "Write")
    assert authorize_topic_operation("tier5_executor", KafkaTopic.ORDERS_PENDING.value, "Read")

    # Advisory tap has strictly zero write permissions across all 18 topics
    for topic in KafkaTopic:
        assert not authorize_topic_operation("advisory_reader", topic.value, "Write")

    # Unknown principal is denied by default
    assert not authorize_topic_operation("unknown_role", KafkaTopic.PRICES_REALTIME.value, "Read")
    assert not authorize_topic_operation("unknown_role", KafkaTopic.PRICES_REALTIME.value, "Write")


def test_kafka_security_deployment_artifacts_enforce_scram_and_acls():
    server_props = (ROOT / "infra/kafka/server.properties").read_text()
    assert "listener.security.protocol.map=INTERNAL:SASL_SSL,EXTERNAL:SASL_SSL" in server_props
    assert "sasl.enabled.mechanisms=SCRAM-SHA-512,SCRAM-SHA-256,PLAIN" in server_props
    assert "allow.everyone.if.no.acl.found=false" in server_props
    assert "auto.create.topics.enable=false" in server_props

    tls_overlay = yaml.safe_load((ROOT / "docker-compose.kafka-tls.yml").read_text())
    for broker in ("kafka-1", "kafka-2", "kafka-3"):
        env = tls_overlay["services"][broker]["environment"]
        assert env["KAFKA_LISTENER_SECURITY_PROTOCOL_MAP"] == "INTERNAL:SASL_SSL,EXTERNAL:SASL_SSL"
        assert "SCRAM-SHA-512" in env["KAFKA_SASL_ENABLED_MECHANISMS"]
        assert env["KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND"] == "false"

    acls_script = (ROOT / "infra/init/kafka-acls.sh").read_text()
    for role in KAFKA_ROLE_ACLS:
        assert f"User:{role}" in acls_script

    tf_main = (ROOT / "infra/terraform/main.tf").read_text()
    assert 'resource "aws_msk_cluster" "kafka"' in tf_main
    assert "allow.everyone.if.no.acl.found=false" in tf_main
    assert "scram = true" in tf_main
