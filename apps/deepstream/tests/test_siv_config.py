"""Tests for RM-11.SIV's new settings files (config.py extensions):
configs/models.yaml, configs/logging.yaml, configs/validation.yaml."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from apps.deepstream.app.config import (
    DEFAULT_LOGGING_PATH,
    DEFAULT_MODELS_PATH,
    DEFAULT_VALIDATION_PATH,
    load_logging_settings,
    load_models_settings,
    load_validation_settings,
)


class TestModelsSettings:
    def test_checked_in_models_yaml_is_valid(self) -> None:
        settings = load_models_settings(DEFAULT_MODELS_PATH)
        assert settings.pgie.unique_id == 1
        assert settings.sgie.unique_id == 2

    def test_precision_maps_to_expected_literal_values(self, tmp_path: Path) -> None:
        path = tmp_path / "models.yaml"
        path.write_text(
            yaml.safe_dump(
                {
                    "pgie": {
                        "model_file": "m.onnx",
                        "engine_file": "m.engine",
                        "labels": "labels.txt",
                        "unique_id": 1,
                        "precision": "int8",
                    },
                    "sgie": {
                        "model_file": "s.onnx",
                        "engine_file": "s.engine",
                        "labels": "labels2.txt",
                        "unique_id": 2,
                    },
                }
            ),
            encoding="utf-8",
        )

        settings = load_models_settings(path)

        assert settings.pgie.precision == "int8"
        assert settings.sgie.precision == "fp16"  # default

    def test_missing_required_field_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "models.yaml"
        path.write_text(
            yaml.safe_dump({"pgie": {"unique_id": 1}, "sgie": {"unique_id": 2}}),
            encoding="utf-8",
        )

        with pytest.raises(ValidationError):
            load_models_settings(path)


class TestLoggingSettings:
    def test_checked_in_logging_yaml_is_valid(self) -> None:
        settings = load_logging_settings(DEFAULT_LOGGING_PATH)
        assert settings.default_level == "INFO"
        assert settings.loggers["pgie"] == "INFO"

    def test_defaults_when_file_omits_loggers(self, tmp_path: Path) -> None:
        path = tmp_path / "logging.yaml"
        path.write_text("default_level: WARNING\n", encoding="utf-8")

        settings = load_logging_settings(path)

        assert settings.default_level == "WARNING"
        assert settings.loggers == {}


class TestValidationSettings:
    def test_checked_in_validation_yaml_is_valid(self) -> None:
        settings = load_validation_settings(DEFAULT_VALIDATION_PATH)
        assert settings.frame_trace.enabled is False
        assert settings.watchdog.stale_after_seconds.pgie == 5.0
        assert settings.feature_flags.enable_calibration is True

    def test_defaults_when_file_is_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "validation.yaml"
        path.write_text("", encoding="utf-8")

        settings = load_validation_settings(path)

        assert settings.frame_trace.enabled is False
        assert settings.watchdog.check_interval_seconds == 2.0
