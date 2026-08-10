from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.app.config import get_settings, load_settings


def test_loads_existing_yaml_fields() -> None:
    settings = load_settings()

    assert settings.environment == "development"
    assert settings.database.host == "localhost"
    assert settings.database.port == 5432
    assert settings.database.name == "radar_eye"
    assert settings.recording.retention_days == 30
    assert settings.threat_engine.enabled is True


def test_db_credentials_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_EYE_DB_USER", "custom_user")
    monkeypatch.setenv("RADAR_EYE_DB_PASSWORD", "custom_password")

    settings = load_settings()

    assert settings.database.user == "custom_user"
    assert settings.database.password.get_secret_value() == "custom_password"


def test_log_level_defaults_to_info(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAR_EYE_LOG_LEVEL", raising=False)

    settings = load_settings()

    assert settings.log_level == "INFO"


def test_log_level_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_EYE_LOG_LEVEL", "DEBUG")

    settings = load_settings()

    assert settings.log_level == "DEBUG"


def test_missing_db_user_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAR_EYE_DB_USER", raising=False)

    with pytest.raises(ValidationError):
        load_settings()


def test_missing_db_password_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAR_EYE_DB_PASSWORD", raising=False)

    with pytest.raises(ValidationError):
        load_settings()


def test_encryption_key_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_EYE_ENCRYPTION_KEY", "custom-key-value")

    settings = load_settings()

    assert settings.encryption_key.get_secret_value() == "custom-key-value"


def test_missing_encryption_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAR_EYE_ENCRYPTION_KEY", raising=False)

    with pytest.raises(ValidationError):
        load_settings()


def test_get_settings_is_cached() -> None:
    first = get_settings()
    second = get_settings()

    assert first is second
