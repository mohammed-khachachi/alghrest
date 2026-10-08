"""Isolation and lifecycle configuration for the long-running deployment test."""

from pathlib import Path

import pytest
import yaml
from dotenv import dotenv_values

from scripts import deployment_soak as soak

pytestmark = pytest.mark.unit


def test_prepare_is_isolated_and_preserves_generated_credentials(monkeypatch, tmp_path):
    monkeypatch.setattr(soak, "RUN", tmp_path / "soak")
    soak.prepare()
    credentials = (soak.RUN / ".env").read_bytes()
    soak.prepare()
    assert (soak.RUN / ".env").read_bytes() == credentials
    values = dotenv_values(soak.RUN / ".env")
    assert values["ENVIRONMENT"] == "paper_trading"
    assert values["ACCOUNTING_BOOK"].startswith("soak-")
    assert values["AI_DAILY_MAX_CALLS"] == "0"
    assert not values.get("ANTHROPIC_API_KEY")
    assert values["KAFKA_APP_PASSWORD"] != values["KAFKA_BROKER_PASSWORD"]
    assert (soak.RUN.stat().st_mode & 0o777) == 0o700
    assert ((soak.RUN / ".env").stat().st_mode & 0o777) == 0o600
    config = yaml.safe_load((soak.RUN / "compose.yml").read_text())
    assert config["name"] == "alghrest-soak"
    for service in config["services"].values():
        assert "container_name" not in service
        assert "env_file" not in service
        assert service["restart"] == "no"
        assert all(port.startswith("127.0.0.1:") for port in service.get("ports", []))
        assert all(".secrets/" not in v for v in service.get("volumes", []))
    for number in (1, 2, 3):
        broker = config["services"][f"kafka-{number}"]
        assert broker["environment"]["KAFKA_MIN_INSYNC_REPLICAS"] == 2
        assert broker["environment"]["KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR"] == 3
        assert broker["mem_limit"] == "640m"
    assert config["services"]["prometheus"]["network_mode"] == "host"
    assert "--web.listen-address=127.0.0.1:29090" in config["services"]["prometheus"]["command"]


def test_child_environment_does_not_inherit_external_keys(monkeypatch):
    monkeypatch.setenv("BINANCE_API_KEY", "must-not-copy")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-copy")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "must-not-copy")
    monkeypatch.setenv("DATABASE_URL", "must-not-copy")
    assert set(soak.child_env()) == {"PATH", "HOME", "PYTHONPATH", "PYTHONUNBUFFERED"}


def test_atomic_status_replaces_previous_value(tmp_path):
    path = tmp_path / "status.json"
    soak.atomic_json(path, {"phase": "starting"})
    soak.atomic_json(path, {"phase": "soaking"})
    assert "soaking" in path.read_text()
    assert not Path(str(path.with_suffix(".tmp"))).exists()


def test_sleep_inhibitor_wraps_worker_not_detached_launcher(monkeypatch):
    monkeypatch.setattr(soak.shutil, "which", lambda name: "/usr/bin/systemd-inhibit")
    command = soak.worker_command(24, "owned-token", True)
    assert command[0] == "/usr/bin/systemd-inhibit"
    assert "--what=idle:sleep" in command
    assert "run" in command and "start" not in command
    assert command[-1] == "owned-token"


def test_requested_sleep_inhibition_never_silently_falls_back(monkeypatch):
    monkeypatch.setattr(soak.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="unavailable"):
        soak.worker_command(24, "token", True)
