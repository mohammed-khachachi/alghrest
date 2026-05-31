"""TimescaleDB persistence helpers for Kafka event sinks."""

from core.persistence.database import TimescaleSessionManager, timescale_session_manager
from core.persistence.events import (
    PERSISTED_TOPICS,
    PersistenceMappingError,
    PersistenceStatement,
    build_persistence_statements,
    normalize_kafka_message,
)
from core.persistence.repository import TimescalePersistenceRepository

__all__ = [
    "PERSISTED_TOPICS",
    "PersistenceMappingError",
    "PersistenceStatement",
    "TimescalePersistenceRepository",
    "TimescaleSessionManager",
    "build_persistence_statements",
    "normalize_kafka_message",
    "timescale_session_manager",
]
