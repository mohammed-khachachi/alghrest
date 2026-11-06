"""Prepare local access keys and Kafka TLS keystores without displaying them or changing existing credentials.

Run before starting full/research Compose. This does not alter database users or
any existing volume. Read the generated .env locally when logging into the UI.
"""

from __future__ import annotations

import ipaddress
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_VENV_PYTHON = _ROOT / ".venv" / "bin" / "python"
if (
    __name__ == "__main__"
    and sys.prefix == sys.base_prefix
    and _VENV_PYTHON.is_file()
    and os.environ.get("_ALGHREST_VENV_BOOTSTRAPPED") != "1"
):
    os.environ["_ALGHREST_VENV_BOOTSTRAPPED"] = "1"
    os.execv(
        str(_VENV_PYTHON),
        [str(_VENV_PYTHON), "-m", "scripts.configure_access", *sys.argv[1:]],
    )

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.hazmat.primitives.serialization import pkcs12  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID  # noqa: E402
from dotenv import dotenv_values  # noqa: E402

KEYS = (
    "POSTGRES_PASSWORD",
    "API_ACCESS_TOKEN",
    "ADVISORY_ACCESS_TOKEN",
    "KAFKA_APP_PASSWORD",
    "KAFKA_BROKER_PASSWORD",
    "KAFKA_TIER1_PASSWORD",
    "KAFKA_TIER2_PASSWORD",
    "KAFKA_TIER3_PASSWORD",
    "KAFKA_TIER4_PASSWORD",
    "KAFKA_TIER5_ROUTER_PASSWORD",
    "KAFKA_TIER5_EXECUTOR_PASSWORD",
    "KAFKA_TIER7_PASSWORD",
    "KAFKA_ADVISORY_PASSWORD",
    "KAFKA_SSL_KEYSTORE_PASSWORD",
    "KAFKA_SSL_KEY_PASSWORD",
    "KAFKA_SSL_TRUSTSTORE_PASSWORD",
)
SAFE = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")


def _ensure_tls_artifacts(
    tls_dir: Path,
    keystore_password: str,
    truststore_password: str,
) -> None:
    """Generate local CA and broker PKCS12 keystore/truststore if not already present."""
    if tls_dir.is_symlink():
        raise ValueError("Refusing symlinked TLS secret directory")
    # If Docker previously auto-created ca.crt as an empty directory, remove that empty dir.
    ca_crt_path = tls_dir / "ca.crt"
    if ca_crt_path.is_dir():
        ca_crt_path.rmdir()
    tls_dir.mkdir(mode=0o755, exist_ok=True)
    tls_dir.chmod(0o755)

    ca_key_path = tls_dir / "ca.key"
    keystore_path = tls_dir / "kafka.broker.keystore.p12"
    truststore_path = tls_dir / "kafka.broker.truststore.p12"

    for p in (ca_crt_path, ca_key_path, keystore_path, truststore_path):
        if p.exists() and p.is_symlink():
            raise ValueError(f"Refusing symlinked TLS file: {p}")

    if ca_crt_path.is_file() and keystore_path.is_file() and truststore_path.is_file():
        return

    now = datetime.now(UTC)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "alghrest-kafka-local-ca")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(ca_key, hashes.SHA256())
    )

    broker_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    broker_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "kafka-broker.alghrest")])
    san = x509.SubjectAlternativeName(
        [
            x509.DNSName("localhost"),
            x509.DNSName("kafka-1"),
            x509.DNSName("kafka-2"),
            x509.DNSName("kafka-3"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
    )
    broker_cert = (
        x509.CertificateBuilder()
        .subject_name(broker_name)
        .issuer_name(ca_name)
        .public_key(broker_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(san, critical=False)
        .add_extension(
            x509.ExtendedKeyUsage(
                [ExtendedKeyUsageOID.SERVER_AUTH, ExtendedKeyUsageOID.CLIENT_AUTH]
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    ca_key_path.write_bytes(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    ca_key_path.chmod(0o600)

    ca_crt_path.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    ca_crt_path.chmod(0o644)

    keystore_bytes = pkcs12.serialize_key_and_certificates(
        name=b"kafka-broker",
        key=broker_key,
        cert=broker_cert,
        cas=[ca_cert],
        encryption_algorithm=serialization.BestAvailableEncryption(
            keystore_password.encode("utf-8")
        ),
    )
    keystore_path.write_bytes(keystore_bytes)
    keystore_path.chmod(0o644)

    keytool_bin = shutil.which("keytool")
    if keytool_bin is not None:
        truststore_path.unlink(missing_ok=True)
        subprocess.run(
            [
                keytool_bin,
                "-importcert",
                "-noprompt",
                "-alias",
                "alghrest-ca",
                "-file",
                str(ca_crt_path),
                "-keystore",
                str(truststore_path),
                "-storetype",
                "PKCS12",
                "-storepass",
                truststore_password,
            ],
            check=True,
            capture_output=True,
        )
    else:
        truststore_bytes = pkcs12.serialize_key_and_certificates(
            name=b"alghrest-ca",
            key=None,
            cert=None,
            cas=[ca_cert],
            encryption_algorithm=serialization.BestAvailableEncryption(
                truststore_password.encode("utf-8")
            ),
        )
        truststore_path.write_bytes(truststore_bytes)
    truststore_path.chmod(0o644)


def configure(root: Path) -> None:
    if os.name != "posix":
        raise RuntimeError(
            "Run access setup in Linux or WSL; native Windows ACL setup is not supported"
        )
    env = root / ".env"
    if env.is_symlink() or (root / ".secrets").is_symlink():
        raise ValueError("Refusing symlinked secret locations")
    existing = dotenv_values(env, interpolate=False) if env.exists() else {}
    values: dict[str, str] = {}
    for key in KEYS:
        if key == "KAFKA_SSL_KEY_PASSWORD" and not existing.get(key):
            value = values["KAFKA_SSL_KEYSTORE_PASSWORD"]
        else:
            value = existing.get(key) or secrets.token_urlsafe(36)
        if not SAFE.fullmatch(value):
            raise ValueError(
                f"{key} must contain 32-256 URL-safe characters; existing value unchanged"
            )
        values[key] = value
    if values["API_ACCESS_TOKEN"] == values["ADVISORY_ACCESS_TOKEN"]:
        raise ValueError("Trading and advisory keys must be distinct")
    lines = env.read_text().splitlines() if env.exists() else []
    for key, value in values.items():
        if not existing.get(key):
            lines = [line for line in lines if not re.match(rf"\s*(?:export\s+)?{key}\s*=", line)]
            lines.append(f"{key}={value}")
    # Atomic replacement: a crash cannot truncate the user's existing .env.
    fd, temporary = tempfile.mkstemp(prefix=".env-access-", dir=root)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write("\n".join(lines) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, env)
    finally:
        Path(temporary).unlink(missing_ok=True)
    directory = root / ".secrets"
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    files = {
        "api_access_token": values["API_ACCESS_TOKEN"],
        "kafka-client.properties": (
            "security.protocol=SASL_PLAINTEXT\nsasl.mechanism=PLAIN\n"
            "sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required "
            f'username="alghrest" password="{values["KAFKA_APP_PASSWORD"]}";\n'
        ),
        "kafka-client-scram.properties": (
            "security.protocol=SASL_PLAINTEXT\nsasl.mechanism=SCRAM-SHA-512\n"
            "sasl.jaas.config=org.apache.kafka.common.security.scram.ScramLoginModule required "
            f'username="alghrest" password="{values["KAFKA_APP_PASSWORD"]}";\n'
        ),
        "kafka-client-tls.properties": (
            "security.protocol=SASL_SSL\nsasl.mechanism=PLAIN\n"
            "ssl.truststore.type=PKCS12\n"
            "ssl.truststore.location=/etc/kafka/secrets/kafka.broker.truststore.p12\n"
            f"ssl.truststore.password={values['KAFKA_SSL_TRUSTSTORE_PASSWORD']}\n"
            "sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required "
            f'username="alghrest" password="{values["KAFKA_APP_PASSWORD"]}";\n'
        ),
    }
    for name, content in files.items():
        path = directory / name
        if path.is_symlink():
            raise ValueError("Refusing symlinked secret file")
        # Directory is owner-only on the host; container UIDs need read access
        # to the individual read-only bind mount (no directory is mounted).
        path.write_text(content)
        path.chmod(0o644)

    _ensure_tls_artifacts(
        directory / "tls",
        keystore_password=values["KAFKA_SSL_KEYSTORE_PASSWORD"],
        truststore_password=values["KAFKA_SSL_TRUSTSTORE_PASSWORD"],
    )
    tls_client_props = directory / "tls" / "kafka-client-tls.properties"
    if tls_client_props.is_symlink():
        raise ValueError("Refusing symlinked TLS client properties file")
    tls_client_props.write_text(files["kafka-client-tls.properties"])
    tls_client_props.chmod(0o644)

    chcon_bin = shutil.which("chcon")
    if chcon_bin is not None:
        targets = [str(directory)]
        if (root / "infra").is_dir():
            targets.append(str(root / "infra"))
        subprocess.run(
            [chcon_bin, "-Rt", "svirt_sandbox_file_t", *targets],
            check=False,
            capture_output=True,
        )


def main() -> None:
    configure(Path(__file__).resolve().parents[1])
    print(
        "Access keys and TLS stores prepared in .env and .secrets; existing keys preserved. No services restarted."
    )


if __name__ == "__main__":
    main()
