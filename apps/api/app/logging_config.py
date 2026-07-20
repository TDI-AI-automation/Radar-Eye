"""Structured JSON logging setup, using python-json-logger."""

from __future__ import annotations

import logging
import sys

try:  # python-json-logger >= 3.0
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # pragma: no cover - fallback for python-json-logger < 3.0
    from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[no-redef]

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(log_level: str = "INFO") -> None:
    """Configure the root logger to emit structured JSON to stdout.

    Safe to call more than once (e.g. across repeated app instantiation in
    tests) -- existing handlers are cleared first so log lines are never
    duplicated.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level.upper())
    root_logger.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter(_LOG_FORMAT))
    root_logger.addHandler(handler)
