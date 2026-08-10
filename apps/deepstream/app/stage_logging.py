"""Per-subsystem stage loggers + the operator-facing audit logger -- RM-11.SIV.

Source: RM-11.SIV Principal Engineer approval, "Pipeline Instrumentation"
(17 named subsystems, one logger each) and "Additional Requirement -- Audit
Logger".

Deliberately separate from, and additive to, the existing application-wide
logger (``apps.api.app.logging_config.configure_logging``, called once at
process startup): these are child loggers of the same root logger
(``radar_eye.stage.<name>`` / ``radar_eye.audit``), so they inherit the
root's stdout JSON handler for free -- ``configure_stage_logging`` only ever
calls ``setLevel``, never touches handlers, so there is exactly one place in
the repository that decides how log records are formatted/emitted.

Every stage logger name is fixed (``config.STAGE_LOGGER_NAMES``) -- callers
ask for one by name via ``get_stage_logger`` rather than constructing the
``radar_eye.stage.`` prefix themselves, so a typo'd stage name fails loudly
at the call site instead of silently creating an unconfigured logger no one
notices.
"""

from __future__ import annotations

import logging

from apps.deepstream.app.config import STAGE_LOGGER_NAMES, LoggingSettings
from apps.deepstream.app.pipeline_trace import get_trace_logger

_STAGE_PREFIX = "radar_eye.stage"
AUDIT_LOGGER_NAME = "radar_eye.audit"


def get_stage_logger(name: str) -> logging.Logger:
    if name not in STAGE_LOGGER_NAMES:
        raise ValueError(
            f"Unknown stage logger name '{name}' -- must be one of {STAGE_LOGGER_NAMES}"
        )
    return logging.getLogger(f"{_STAGE_PREFIX}.{name}")


def get_audit_logger() -> logging.Logger:
    """``radar_eye.audit`` -- operator-facing major events only (camera
    connect/disconnect, HIGH/MEDIUM threats, incidents, alarms, pipeline
    restarts, watchdog warnings). Engineering diagnostics belong on the
    stage loggers instead, never here."""
    return logging.getLogger(AUDIT_LOGGER_NAME)


def configure_stage_logging(settings: LoggingSettings) -> None:
    """Applies configs/logging.yaml's per-logger level overrides. Safe to
    call more than once (mirrors apps.api.app.logging_config.configure_logging's
    idempotency).

    radar_eye.audit is always INFO and is not present in
    ``settings.loggers`` -- it is never independently silenced, per the
    RM-11.SIV approval ("This is intended for operators").
    """
    default_level = settings.default_level.upper()
    for name in STAGE_LOGGER_NAMES:
        level = settings.loggers.get(name, default_level).upper()
        get_stage_logger(name).setLevel(level)
    get_audit_logger().setLevel(logging.INFO)


def enable_maximum_observability() -> None:
    """Production Validation Mode's logging half: elevates every
    ``radar_eye.stage.*`` logger (regardless of what
    ``configs/logging.yaml`` set) plus the frame-trace logger to DEBUG.
    Call once at startup, after ``configure_stage_logging()``, only when
    ``validation.production_validation_mode.enabled`` is true -- an
    override layered on top of the normal config-driven levels, not a
    replacement for them (calling ``configure_stage_logging()`` again
    would restore the configured levels). Never called in normal
    production operation, so this has zero effect on today's default
    logging behavior."""
    for name in STAGE_LOGGER_NAMES:
        get_stage_logger(name).setLevel(logging.DEBUG)
    get_trace_logger().setLevel(logging.DEBUG)
