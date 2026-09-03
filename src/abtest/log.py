"""Logging setup.

The library attaches a ``NullHandler`` and never configures the root logger -
that is the application's job. ``configure_logging`` exists for the two
applications in this repository (the CLI and, later, the API service), where
plain text is right for a terminal and JSON is right for a log aggregator.

What gets logged is chosen for operability: the start and end of anything
slow enough for a user to wonder whether it hung, and every trust-check
failure, since that is the event someone will have to explain afterwards.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager

_PACKAGE_LOGGER = logging.getLogger("abtest")
_PACKAGE_LOGGER.addHandler(logging.NullHandler())


def get_logger(name: str) -> logging.Logger:
    """Return the module logger for ``name`` (use ``__name__``)."""
    return logging.getLogger(name)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for log aggregators that parse structure."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # Anything passed through `extra=` lands on the record; carry it over.
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord("", 0, "", 0, "", None, None).__dict__ and key not in payload:
                payload[key] = value
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None, json_format: bool | None = None) -> None:
    """Configure root logging for an application entry point.

    Reads ``LOG_LEVEL`` and ``LOG_FORMAT`` from the environment when the
    arguments are omitted, so the same code behaves correctly in a terminal
    and in a container without a code change.
    """
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    if json_format is None:
        json_format = os.getenv("LOG_FORMAT", "text").lower() == "json"

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_format
        else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S")
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


@contextmanager
def log_duration(logger: logging.Logger, message: str, **fields):
    """Log the duration of a slow operation, and log failures with context.

    Used around permutation tests and full analyses - operations where the
    difference between "working" and "hung" is invisible without a timer.
    """
    start = time.perf_counter()
    try:
        yield
    except Exception:
        logger.exception("%s failed after %.2fs", message, time.perf_counter() - start, extra=fields)
        raise
    else:
        logger.info("%s in %.2fs", message, time.perf_counter() - start, extra=fields)
