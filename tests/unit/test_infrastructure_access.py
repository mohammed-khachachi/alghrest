"""Configuration contracts: preserve credentials, no remote unauthenticated listeners."""

from pathlib import Path

import pytest
import yaml
from dotenv import dotenv_values
from pydantic import SecretStr

from core.config import Settings, settings
from core.kafka.security import aiokafka_security, confluent_security
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
