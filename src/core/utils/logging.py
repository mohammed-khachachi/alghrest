"""
ALGHREST — Structured Logging
Configures structlog with JSON output in production, human-readable in dev.
All agents share this configuration — call configure_logging() once at startup.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, cast

import structlog


def configure_logging(log_level: str = "INFO", environment: str = "development") -> None:
    """Initialize structlog. Call once per process at startup."""
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.dev.ConsoleRenderer | structlog.processors.JSONRenderer
    if environment == "development":
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, structlog.processors.ExceptionRenderer(), renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Also configure stdlib logging so third-party libs are captured
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.getLevelName(log_level.upper()),
    )

    # Silence noisy third-party loggers
    for noisy in ("aiokafka", "ccxt", "urllib3", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str, **ctx: Any) -> structlog.BoundLogger:
    """Get a context-bound logger. Pass agent=name, tier=N, etc."""
    return cast(structlog.BoundLogger, structlog.get_logger(name).bind(**ctx))
