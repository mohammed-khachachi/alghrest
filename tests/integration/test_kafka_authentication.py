"""Opt-in SASL wire test on an ephemeral local broker, no runtime topics/volumes."""

import asyncio
import os
import secrets
import socket
import subprocess
from uuid import uuid4

import pytest
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import KafkaConnectionError, SaslAuthenticationFailed
from pydantic import SecretStr

from core.config import settings
from core.kafka.security import aiokafka_security
from core.orchestrator.message_bus import AlghrestConsumer, AlghrestProducer

pytestmark = pytest.mark.integration


async def test_real_broker_rejects_anonymous_and_wrong_key_allows_authenticated_bus(monkeypatch):
    if os.getenv("KAFKA_AUTH_TESTS") != "1":
        pytest.skip("Set KAFKA_AUTH_TESTS=1; requires cached apache/kafka:4.3.1 and Docker")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    name = "alghrest-auth-test-" + uuid4().hex[:12]
    password = secrets.token_urlsafe(36)
    jaas = f'org.apache.kafka.common.security.plain.PlainLoginModule required username="alghrest" password="{password}" user_alghrest="{password}";'
    config = {
        "KAFKA_NODE_ID": "1",
        "KAFKA_PROCESS_ROLES": "broker,controller",
        "KAFKA_LISTENERS": "INTERNAL://:29092,EXTERNAL://:9092,CONTROLLER://127.0.0.1:9093",
        "KAFKA_ADVERTISED_LISTENERS": f"INTERNAL://localhost:29092,EXTERNAL://127.0.0.1:{port}",
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP": "INTERNAL:SASL_PLAINTEXT,EXTERNAL:SASL_PLAINTEXT,CONTROLLER:PLAINTEXT",
        "KAFKA_INTER_BROKER_LISTENER_NAME": "INTERNAL",
        "KAFKA_CONTROLLER_LISTENER_NAMES": "CONTROLLER",
        "KAFKA_CONTROLLER_QUORUM_VOTERS": "1@127.0.0.1:9093",
        "KAFKA_SASL_ENABLED_MECHANISMS": "PLAIN",
        "KAFKA_SASL_MECHANISM_INTER_BROKER_PROTOCOL": "PLAIN",
        "KAFKA_LISTENER_NAME_INTERNAL_PLAIN_SASL_JAAS_CONFIG": jaas,
        "KAFKA_LISTENER_NAME_EXTERNAL_PLAIN_SASL_JAAS_CONFIG": jaas,
        "KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR": "1",
        "KAFKA_GROUP_INITIAL_REBALANCE_DELAY_MS": "0",
        "KAFKA_AUTO_CREATE_TOPICS_ENABLE": "false",
        "KAFKA_HEAP_OPTS": "-Xmx256m -Xms256m",
    }
    # Values are passed through inherited env, never command arguments/log output.
    command = [
        "docker",
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "--memory",
        "512m",
        "-p",
        f"127.0.0.1:{port}:9092",
    ]
    for key in config:
        command += ["-e", key]
    command += ["apache/kafka:4.3.1"]
    clients = []
    producer, consumer = AlghrestProducer(), None
    try:
        subprocess.run(
            command, env={**os.environ, **config}, check=True, capture_output=True, timeout=30
        )
        monkeypatch.setattr(settings, "kafka_bootstrap_servers", f"127.0.0.1:{port}")
        monkeypatch.setattr(settings, "kafka_security_protocol", "SASL_PLAINTEXT")
        monkeypatch.setattr(settings, "kafka_sasl_username", "alghrest")
        monkeypatch.setattr(settings, "kafka_sasl_password", SecretStr(password))
        async with asyncio.timeout(60):
            while True:
                admin = AIOKafkaAdminClient(
                    bootstrap_servers=settings.kafka_servers_list,
                    request_timeout_ms=2000,
                    **aiokafka_security(),
                )
                try:
                    await admin.start()
                    clients.append(admin)
                    break
                except KafkaConnectionError:
                    await admin.close()
                    await asyncio.sleep(1)
        for auth in ({}, {**aiokafka_security(), "sasl_plain_password": "wrong"}):
            bad = AIOKafkaAdminClient(
                bootstrap_servers=settings.kafka_servers_list, request_timeout_ms=2000, **auth
            )
            clients.append(bad)
            with pytest.raises((KafkaConnectionError, SaslAuthenticationFailed, TimeoutError)):
                async with asyncio.timeout(5):
                    await bad.start()
        topic = "isolated-auth-test"
        await admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
        await producer.initialize()
        consumer = AlghrestConsumer("auth-test", [topic], auto_offset_reset="earliest")
        await consumer.initialize()
        await producer.send_raw(topic, {"authenticated": True})
        async with asyncio.timeout(10):
            async for value in consumer.stream():
                assert value == {"authenticated": True}
                break
    finally:
        if consumer:
            await consumer.shutdown()
        await producer.shutdown()
        for client in clients:
            await client.close()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30, check=False)
