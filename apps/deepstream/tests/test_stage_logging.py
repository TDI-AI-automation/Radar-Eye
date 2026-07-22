"""Tests for stage_logging.py -- RM-11.SIV Pipeline Instrumentation / Audit Logger."""

from __future__ import annotations

import logging

import pytest

from apps.deepstream.app.config import LoggingSettings
from apps.deepstream.app.stage_logging import (
    AUDIT_LOGGER_NAME,
    configure_stage_logging,
    get_audit_logger,
    get_stage_logger,
)


def test_get_stage_logger_returns_correctly_prefixed_logger() -> None:
    logger = get_stage_logger("pgie")
    assert logger.name == "radar_eye.stage.pgie"


def test_get_stage_logger_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown stage logger name"):
        get_stage_logger("not_a_real_stage")


def test_get_audit_logger_name() -> None:
    assert get_audit_logger().name == AUDIT_LOGGER_NAME


def test_configure_stage_logging_applies_per_logger_overrides() -> None:
    settings = LoggingSettings(default_level="INFO", loggers={"pgie": "DEBUG"})

    configure_stage_logging(settings)

    assert get_stage_logger("pgie").level == logging.DEBUG
    assert get_stage_logger("sgie").level == logging.INFO  # falls back to default


def test_configure_stage_logging_never_silences_audit_logger() -> None:
    settings = LoggingSettings(default_level="ERROR", loggers={})

    configure_stage_logging(settings)

    assert get_audit_logger().level == logging.INFO


def test_all_seventeen_stage_names_get_a_logger() -> None:
    from apps.deepstream.app.config import STAGE_LOGGER_NAMES

    settings = LoggingSettings()
    configure_stage_logging(settings)

    assert len(STAGE_LOGGER_NAMES) == 17
    for name in STAGE_LOGGER_NAMES:
        assert get_stage_logger(name).level == logging.INFO
