"""Isolated Confluent deployment and bounded paper soak (Linux/WSL).

prepare/start/status/stop; no runtime .env, volumes, topics or balances are reused.
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import fcntl
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psutil
import yaml
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "artifacts/deployment-soak"
PROJECT = "alghrest-soak"
AGENTS = [
    ("agents.tier7_monitoring.portfolio_accountant", "PortfolioAccountant", 37),
    ("agents.tier5_execution.exchange_executor", "ExchangeExecutor", 26),
    ("agents.tier1_executive.proposal_approver", "ProposalApprover", 3),
    ("agents.tier5_execution.order_router", "OrderRouter", 20),
    ("agents.tier1_executive.risk_governor", "RiskGovernor", 2),
    ("agents.tier7_monitoring.portfolio_tracker", "PortfolioTracker", 30),
]


def atomic_json(path: Path, data: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n")
    temporary.replace(path)


def compose(*args: str, timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-name",
            PROJECT,
            "--env-file",
            str(RUN / ".env"),
            "-f",
            str(RUN / "compose.yml"),
            *args,
        ],
        cwd=RUN,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def child_env() -> dict[str, str]:
    # Do not inherit exchange/Telegram/Anthropic credentials from a host shell.
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONPATH": f"{ROOT / 'src'}:{ROOT}",
        "PYTHONUNBUFFERED": "1",
    }


def owned() -> dict:
    try:
        state = json.loads((RUN / "status.json").read_text())
        args = psutil.Process(state["pid"]).cmdline()
        if state["token"] in args and "run" in args and str(Path(__file__).resolve()) in args:
            return state
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return {}


def worker_command(hours: float, token: str, inhibit_sleep: bool = False) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "run",
        "--hours",
        str(hours),
        "--token",
        token,
    ]
    if inhibit_sleep:
        inhibitor = shutil.which("systemd-inhibit")
        if inhibitor is None:
            raise RuntimeError("systemd-inhibit is unavailable; sleep inhibition was requested")
        command = [
            inhibitor,
            "--what=idle:sleep",
            "--mode=block",
            "--who=ALGHREST-soak",
            "--why=Isolated paper soak in progress",
            *command,
        ]
    return command


def prepare() -> None:
    RUN.mkdir(parents=True, exist_ok=True, mode=0o700)
    RUN.chmod(0o700)
    previous = (
        json.loads((RUN / "manifest.json").read_text())
        if (RUN / "manifest.json").exists()
        else None
    )
    if owned():
        raise RuntimeError("Stop the owned worker before refreshing configuration")
    original = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = {
        name: copy.deepcopy(original["services"][name])
        for name in (
            "timescaledb",
            "redis",
            "zookeeper",
            "kafka-1",
            "kafka-2",
            "kafka-3",
            "kafka-init",
            "prometheus",
        )
    }
    run_id = previous["run_id"] if previous else uuid4().hex
    values = {
        "ENVIRONMENT": "paper_trading",
        "ENABLE_DEFI_AGENTS": "false",
        "POSTGRES_PASSWORD": secrets.token_urlsafe(36),
        "KAFKA_APP_PASSWORD": secrets.token_urlsafe(36),
        "KAFKA_BROKER_PASSWORD": secrets.token_urlsafe(36),
        "API_ACCESS_TOKEN": secrets.token_urlsafe(36),
        "ACCOUNTING_BOOK": "soak-" + run_id,
        "REDIS_URL": "redis://127.0.0.1:26379",
        "REDIS_DB_STATE": "2",
        "KAFKA_BOOTSTRAP_SERVERS": "127.0.0.1:29092,127.0.0.1:29093,127.0.0.1:29094",
        "KAFKA_SECURITY_PROTOCOL": "SASL_PLAINTEXT",
        "KAFKA_SASL_USERNAME": "alghrest",
        "EXECUTION_ACCOUNTS": '[{"exchange":"binance","symbols":["SOL/USDT"]}]',
        "AI_DAILY_MAX_CALLS": "0",
        "AI_DAILY_BUDGET_USD": "0",
        "LOG_LEVEL": "WARNING",
        "METRICS_BASE_PORT": "19200",
        "METRICS_BIND_HOST": "127.0.0.1",
    }
    values["KAFKA_SASL_PASSWORD"] = values["KAFKA_APP_PASSWORD"]
    values["DATABASE_URL"] = (
        f"postgresql://alghrest:{values['POSTGRES_PASSWORD']}@127.0.0.1:25432/alghrest"
    )
    if previous:
        values = dict(dotenv_values(RUN / ".env"))
    else:
        with os.fdopen(
            os.open(RUN / ".env", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w"
        ) as stream:
            stream.write("".join(f"{k}={v}\n" for k, v in values.items()))
    (RUN / "api_access_token").write_text(values["API_ACCESS_TOKEN"])
    (RUN / "kafka-client.properties").write_text(
        "security.protocol=SASL_PLAINTEXT\nsasl.mechanism=PLAIN\n"
        "sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required "
        f'username="alghrest" password="{values["KAFKA_APP_PASSWORD"]}";\n'
    )
    for service in services.values():
        service.pop("container_name", None)
        service.pop("deploy", None)
        service.pop("ports", None)
        service["restart"] = "no"
        service["networks"] = ["soak"]
        volumes = []
        for mount in service.get("volumes", []):
            source, target, *flags = mount.split(":")
            if source.startswith("./.secrets/"):
                source = str(RUN / Path(source).name)
            elif source.startswith("./"):
                staged = RUN / "mounts" / source[2:]
                staged.parent.mkdir(parents=True, exist_ok=True)
                original_path = ROOT / source[2:]
                if original_path.is_dir():
                    shutil.copytree(original_path, staged, dirs_exist_ok=True)
                else:
                    shutil.copyfile(original_path, staged)
                source = str(staged)
            if Path(source).is_absolute():
                flags = ["ro,z"]  # Share staged files under SELinux; never relabel source files.
            volumes.append(":".join([source, target, *flags]))
        service["volumes"] = volumes
        service["logging"] = {
            "driver": "json-file",
            "options": {"max-size": "10m", "max-file": "2"},
        }
    db = services["timescaledb"]
    db["ports"] = ["127.0.0.1:25432:5432"]
    db["command"] = (
        "postgres -c shared_preload_libraries=timescaledb,pg_stat_statements -c shared_buffers=128MB -c max_connections=100"
    )
    db["mem_limit"] = "512m"
    redis = services["redis"]
    redis["ports"] = ["127.0.0.1:26379:6379"]
    redis["command"] = (
        "redis-server --appendonly yes --maxmemory 64mb --maxmemory-policy allkeys-lru"
    )
    redis["mem_limit"] = "160m"
    services["zookeeper"]["environment"]["KAFKA_HEAP_OPTS"] = "-Xmx128m -Xms128m"
    services["zookeeper"]["mem_limit"] = "384m"
    for i in (1, 2, 3):
        broker = services[f"kafka-{i}"]
        broker["environment"][
            "KAFKA_ADVERTISED_LISTENERS"
        ] = f"INTERNAL://kafka-{i}:29092,EXTERNAL://127.0.0.1:{29091+i}"
        broker["environment"]["KAFKA_HEAP_OPTS"] = "-Xmx256m -Xms256m"
        broker["mem_limit"] = "640m"
        broker["cpus"] = 1.0
        broker["stop_grace_period"] = "60s"
        broker["ports"] = [f"127.0.0.1:{29091+i}:{9091+i}"]
    prom = services["prometheus"]
    prom.pop("networks")
    prom["network_mode"] = "host"
    prom["command"] = [
        "--config.file=/etc/prometheus/prometheus.yml",
        "--storage.tsdb.path=/prometheus",
        "--storage.tsdb.retention.time=2d",
        "--storage.tsdb.retention.size=256MB",
        "--web.listen-address=127.0.0.1:29090",
    ]
    prom["volumes"] = [
        f"{RUN / 'prometheus.yml'}:/etc/prometheus/prometheus.yml:ro,z",
        f"{RUN / 'api_access_token'}:/run/secrets/api_access_token:ro,z",
        "prometheus-data:/prometheus",
    ]
    prom["mem_limit"] = "192m"
    prom["healthcheck"]["test"] = [
        "CMD-SHELL",
        "wget --quiet --spider http://127.0.0.1:29090/-/healthy",
    ]
    prometheus = {
        "global": {"scrape_interval": "15s"},
        "scrape_configs": [
            {
                "job_name": "soak-api",
                "authorization": {
                    "type": "Bearer",
                    "credentials_file": "/run/secrets/api_access_token",
                },
                "static_configs": [{"targets": ["127.0.0.1:28000"]}],
            },
            {
                "job_name": "soak-agents",
                "static_configs": [{"targets": [f"127.0.0.1:{19200+a[2]}" for a in AGENTS]}],
            },
        ],
    }
    (RUN / "prometheus.yml").write_text(yaml.safe_dump(prometheus))
    (RUN / "compose.yml").write_text(
        yaml.safe_dump(
            {
                "name": PROJECT,
                "services": services,
                "networks": {"soak": {"driver": "bridge"}},
                "volumes": original["volumes"],
            },
            sort_keys=False,
        )
    )
    atomic_json(
        RUN / "manifest.json",
        {
            "run_id": run_id,
            "book": values["ACCOUNTING_BOOK"],
            "source_compose": str(ROOT / "docker-compose.yml"),
            "created_at": previous["created_at"] if previous else datetime.now(UTC).isoformat(),
            "scope": "3 CP 7.6 brokers, PostgreSQL/Timescale, Redis, ZooKeeper, Prometheus; six host agents and API; synthetic paper only",
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "start", "run", "status", "stop"])
    parser.add_argument("--hours", type=float, default=24)
    parser.add_argument("--token", default="")
    parser.add_argument(
        "--inhibit-sleep", action="store_true", help="Hold a systemd sleep inhibitor while running"
    )
    args = parser.parse_args()
    if not 0 < args.hours <= 24:
        parser.error("hours must be >0 and <=24")
    if args.command == "prepare":
        prepare()
        print(json.dumps({"prepared": str(RUN), "credentials": "not displayed"}))
    elif args.command == "status":
        print((RUN / "status.json").read_text() if (RUN / "status.json").exists() else "{}")
    elif args.command == "stop":
        if current := owned():
            os.kill(current["pid"], signal.SIGTERM)
        else:
            result = compose("stop")
            print(json.dumps({"stopped": result.returncode == 0}))
    elif args.command == "start":
        if owned():
            raise SystemExit("An owned soak is already running")
        if not (RUN / "manifest.json").exists():
            raise SystemExit("Prepare the isolated configuration first")
        with (RUN / "runner.log").open("ab", buffering=0) as log:
            subprocess.Popen(
                worker_command(args.hours, uuid4().hex, args.inhibit_sleep),
                cwd=RUN,
                env=child_env(),
                start_new_session=True,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        for _ in range(20):
            time.sleep(0.25)
            if owned():
                print(json.dumps({"started": True, "status": str(RUN / "status.json")}))
                return
        raise SystemExit("Runner did not start; inspect runner.log")
    else:
        os.chdir(RUN)
        with (RUN / "runner.lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            from scripts.deployment_workload import run

            asyncio.run(run(args.hours, args.token))


if __name__ == "__main__":
    main()
