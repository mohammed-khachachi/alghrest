"""Opt-in SASL wire test on an ephemeral local broker, no runtime topics/volumes."""

import asyncio
import os
import secrets
import socket
import subprocess
from uuid import uuid4

import pytest
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.admin import AIOKafkaAdminClient, NewTopic
from aiokafka.errors import (
    KafkaConnectionError,
    SaslAuthenticationFailed,
    TopicAuthorizationFailedError,
)
from aiokafka.structs import TopicPartition
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
    strategy_password = secrets.token_urlsafe(36)
    jaas = f'org.apache.kafka.common.security.plain.PlainLoginModule required username="alghrest" password="{password}" user_alghrest="{password}" user_strategy="{strategy_password}";'
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
        "KAFKA_AUTHORIZER_CLASS_NAME": "org.apache.kafka.metadata.authorizer.StandardAuthorizer",
        "KAFKA_ALLOW_EVERYONE_IF_NO_ACL_FOUND": "false",
        # The anonymous principal exists only on the unexposed local controller
        # channel; external listeners still require a successful SASL exchange.
        "KAFKA_SUPER_USERS": "User:alghrest;User:ANONYMOUS",
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
    producer, consumer, strategy, probe = AlghrestProducer(), None, None, None
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
        forbidden = "orders.pending"
        await admin.create_topics(
            [NewTopic(t, num_partitions=1, replication_factor=1) for t in (topic, forbidden)]
        )
        properties = (
            "security.protocol=SASL_PLAINTEXT\nsasl.mechanism=PLAIN\nsasl.jaas.config="
            + jaas
            + "\n"
        )
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                name,
                "sh",
                "-c",
                "umask 077; cat > /tmp/auth-admin.properties",
            ],
            input=properties.encode(),
            capture_output=True,
            check=True,
            timeout=15,
        )
        subprocess.run(
            [
                "docker",
                "exec",
                name,
                "/opt/kafka/bin/kafka-acls.sh",
                "--bootstrap-server",
                "localhost:29092",
                "--command-config",
                "/tmp/auth-admin.properties",
                "--add",
                "--allow-principal",
                "User:strategy",
                "--operation",
                "Write",
                "--operation",
                "Describe",
                "--topic",
                topic,
            ],
            capture_output=True,
            check=True,
            timeout=30,
        )
        await producer.initialize()
        consumer = AlghrestConsumer("auth-test", [topic], auto_offset_reset="earliest")
        await consumer.initialize()
        await producer.send_raw(topic, {"authenticated": True})
        async with asyncio.timeout(10):
            async for value in consumer.stream():
                assert value == {"authenticated": True}
                break
        strategy = AIOKafkaProducer(
            bootstrap_servers=settings.kafka_servers_list,
            request_timeout_ms=2000,
            **{
                **aiokafka_security(),
                "sasl_plain_username": "strategy",
                "sasl_plain_password": strategy_password,
            },
        )
        await strategy.start()
        with pytest.raises(TopicAuthorizationFailedError):
            async with asyncio.timeout(5):
                await strategy.send_and_wait(forbidden, b'{"unauthorized":true}')
        await strategy.send_and_wait(topic, b'{"role_authorized":true}')
        async with asyncio.timeout(10):
            async for value in consumer.stream():
                assert value == {"role_authorized": True}
                break
        probe = AIOKafkaConsumer(
            bootstrap_servers=settings.kafka_servers_list,
            **aiokafka_security(),
        )
        await probe.start()
        assert (await probe.end_offsets([TopicPartition(forbidden, 0)]))[
            TopicPartition(forbidden, 0)
        ] == 0
    finally:
        if probe:
            await probe.stop()
        if strategy:
            await strategy.stop()
        if consumer:
            await consumer.shutdown()
        await producer.shutdown()
        for client in clients:
            await client.close()
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=30, check=False)
