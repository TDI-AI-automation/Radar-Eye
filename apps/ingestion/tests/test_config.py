"""Tests for apps.ingestion.app.config -- specifically that
DEFAULT_INGESTION_PATH actually resolves to the real
configs/ingestion.yaml. A prior version of REPO_ROOT's parents[] index
was one level too shallow (resolved to .../apps instead of the repo
root), so the default path never existed and load_settings() silently
fell back to hardcoded Pydantic defaults instead of the YAML file --
undetected because those defaults happened to match the YAML's own
values. This test would have caught that regression.
"""

from __future__ import annotations

from apps.ingestion.app.config import DEFAULT_INGESTION_PATH, IngestionSettings, load_settings


def test_default_ingestion_path_resolves_to_the_real_configs_file() -> None:
    assert DEFAULT_INGESTION_PATH.is_file()
    assert DEFAULT_INGESTION_PATH.name == "ingestion.yaml"
    assert DEFAULT_INGESTION_PATH.parent.name == "configs"


def test_load_settings_reads_the_real_file_not_just_defaults() -> None:
    settings = load_settings()
    assert isinstance(settings, IngestionSettings)
    assert settings.publish_rtsp_port == 8600


def test_load_settings_falls_back_to_defaults_for_a_missing_path(tmp_path) -> None:
    missing = tmp_path / "does-not-exist.yaml"
    settings = load_settings(missing)
    assert settings == IngestionSettings()
