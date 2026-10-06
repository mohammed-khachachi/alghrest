"""Prepare local access keys without displaying them or changing existing credentials.

Run before starting full/research Compose. This does not alter database users or
any existing volume. Read the generated .env locally when logging into the UI.
"""

from __future__ import annotations

import os
import re
import secrets
import tempfile
from pathlib import Path

from dotenv import dotenv_values

KEYS = (
    "POSTGRES_PASSWORD",
    "API_ACCESS_TOKEN",
    "ADVISORY_ACCESS_TOKEN",
    "KAFKA_APP_PASSWORD",
    "KAFKA_BROKER_PASSWORD",
)
SAFE = re.compile(r"[A-Za-z0-9_-]{32,256}\Z")


def configure(root: Path) -> None:
    if os.name != "posix":
        raise RuntimeError(
            "Run access setup in Linux or WSL; native Windows ACL setup is not supported"
        )
    env = root / ".env"
    if env.is_symlink() or (root / ".secrets").is_symlink():
        raise ValueError("Refusing symlinked secret locations")
    existing = dotenv_values(env, interpolate=False) if env.exists() else {}
    values = {}
    for key in KEYS:
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
    }
    for name, content in files.items():
        path = directory / name
        if path.is_symlink():
            raise ValueError("Refusing symlinked secret file")
        # Directory is owner-only on the host; container UIDs need read access
        # to the individual read-only bind mount (no directory is mounted).
        path.write_text(content)
        path.chmod(0o644)


def main() -> None:
    configure(Path(__file__).resolve().parents[1])
    print(
        "Access keys prepared in .env and .secrets; existing keys preserved. No services restarted."
    )


if __name__ == "__main__":
    main()
