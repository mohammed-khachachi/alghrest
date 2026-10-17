"""Bounded portable research archive; hashes detect corruption, not publisher authenticity."""

import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator

from core.advisory.models import Strict, UTCDateTime
from core.advisory.openterminal_research import TerminalSymbol, valid_symbol
from core.advisory.research_journal import ResearchSnapshot

MAX_BACKUP_BYTES = 32 * 1024 * 1024


class BackupRecord(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    symbol: TerminalSymbol
    stored_saved: str = Field(max_length=64)
    payload: str = Field(max_length=64000)

    @model_validator(mode="after")
    def identity(self) -> Self:
        record = ResearchSnapshot.model_validate_json(self.payload)
        if (
            len(self.payload.encode()) > 64000
            or (record.id, record.report.symbol) != (self.id, self.symbol)
            or record.saved_at != datetime.fromisoformat(self.stored_saved)
        ):
            raise ValueError("Backup record identity/time mismatch")
        return self


class ResearchBackup(Strict):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["research-backup-v1"] = "research-backup-v1"
    created_at: UTCDateTime
    watches: tuple[TerminalSymbol, ...] = Field(max_length=50)
    snapshots: tuple[BackupRecord, ...] = Field(max_length=5000)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("watches")
    @classmethod
    def watch_identity(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("Duplicate backup watch")
        return tuple(valid_symbol(v) for v in values)

    @model_validator(mode="after")
    def integrity(self) -> Self:
        if len({r.id for r in self.snapshots}) != len(self.snapshots) or any(
            n > 100 for n in Counter(r.symbol for r in self.snapshots).values()
        ):
            raise ValueError("Duplicate identities or snapshot limit exceeded")
        if any(
            ResearchSnapshot.model_validate_json(r.payload).saved_at > self.created_at
            for r in self.snapshots
        ):
            raise ValueError("Backup creation precedes saved research")
        content = self.model_dump(mode="json", exclude={"sha256"})
        if self.sha256 != backup_checksum(content):
            raise ValueError("Backup checksum mismatch")
        return self


def backup_checksum(content: dict[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def read_backup(raw: bytes, now: datetime) -> ResearchBackup:
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError("Backup exceeds 32 MiB")
    backup = ResearchBackup.model_validate_json(raw)
    if backup.created_at > now:
        raise ValueError("Future backup creation time")
    return backup
