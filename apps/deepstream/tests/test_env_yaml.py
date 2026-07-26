"""Tests for env_yaml.py -- RM-11.SIV Additional Requirement A.1, Option B."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.deepstream.app.env_yaml import (
    MissingEnvironmentVariableError,
    load_yaml_with_env_substitution,
)


def test_substitutes_env_vars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADAR_CAMERA_USERNAME", "operator")
    monkeypatch.setenv("RADAR_CAMERA_PASSWORD", "s3cret")
    path = tmp_path / "camera.yaml"
    path.write_text(
        "username: ${RADAR_CAMERA_USERNAME}\npassword: ${RADAR_CAMERA_PASSWORD}\n",
        encoding="utf-8",
    )

    result = load_yaml_with_env_substitution(path)

    assert result == {"username": "operator", "password": "s3cret"}


def test_raises_on_missing_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADAR_CAMERA_PASSWORD", raising=False)
    path = tmp_path / "camera.yaml"
    path.write_text("password: ${RADAR_CAMERA_PASSWORD}\n", encoding="utf-8")

    with pytest.raises(MissingEnvironmentVariableError, match="RADAR_CAMERA_PASSWORD"):
        load_yaml_with_env_substitution(path)


def test_plain_values_pass_through_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "camera.yaml"
    path.write_text("rtsp_url: rtsp://192.168.1.50:554/stream1\nfps: 30\n", encoding="utf-8")

    result = load_yaml_with_env_substitution(path)

    assert result == {"rtsp_url": "rtsp://192.168.1.50:554/stream1", "fps": 30}
