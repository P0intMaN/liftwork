"""Structured logging via structlog.

Single entrypoint: `configure_logging()` is called once at process start
(API, worker, alembic). After that, every module gets a logger from
`get_logger()`.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import Processor


def configure_logging(level: str = "INFO", *, json_logs: bool = True) -> None:
    log_level = logging.getLevelNamesMapping().get(level.upper(), logging.INFO)

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if json_logs
        else structlog.dev.ConsoleRenderer(colors=True)
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib logging through structlog formatting.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_StdlibFormatter(shared_processors, renderer))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    # Quiet down noisy libraries by default.
    for noisy in ("uvicorn.access", "asyncio", "urllib3"):
        logging.getLogger(noisy).setLevel(max(log_level, logging.WARNING))


class _StdlibFormatter(logging.Formatter):
    def __init__(self, processors: list[Processor], renderer: Processor) -> None:
        super().__init__()
        self._processors: list[Processor] = [*processors, renderer]

    def format(self, record: logging.LogRecord) -> str:
        payload: Any = {
            "event": record.getMessage(),
            "logger": record.name,
            "level": record.levelname.lower(),
        }
        if record.exc_info:
            payload["exc_info"] = record.exc_info
        for proc in self._processors:
            payload = proc(None, record.levelname.lower(), payload)
        return payload if isinstance(payload, str) else str(payload)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
