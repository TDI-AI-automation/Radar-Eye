"""Tests for models_config.py -- RM-11.SIV Decision C.

SDK-free: ModelConfigResolver only reads/writes plain files, no pyds/gi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.deepstream.app.config import ModelsSettings
from apps.deepstream.app.models_config import ModelConfigError, ModelConfigResolver


def _models_settings(tmp_path: Path, **overrides) -> ModelsSettings:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"fake-onnx")
    labels_file = tmp_path / "labels.txt"
    labels_file.write_text("weapon\nnot_weapon\n\n", encoding="utf-8")  # trailing blank line

    pgie = {
        "enabled": True,
        "model_file": str(model_file),
        "engine_file": str(tmp_path / "model.engine"),
        "labels": str(labels_file),
        "unique_id": 1,
        **overrides.get("pgie", {}),
    }
    sgie = {
        "enabled": True,
        "model_file": str(model_file),
        "engine_file": str(tmp_path / "model2.engine"),
        "labels": str(labels_file),
        "unique_id": 2,
        **overrides.get("sgie", {}),
    }
    return ModelsSettings(pgie=pgie, sgie=sgie)


class TestDisabledStagesFallBackToPlaceholder:
    def test_pgie_disabled_returns_placeholder(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path, pgie={"enabled": False})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_pgie(models)

        assert resolved.is_placeholder is True
        assert str(resolved.config_file_path).endswith("pgie_placeholder.txt")

    def test_sgie_disabled_returns_placeholder(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path, sgie={"enabled": False})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_sgie(models)

        assert resolved.is_placeholder is True
        assert str(resolved.config_file_path).endswith("sgie_placeholder.txt")


class TestFailFastOnMissingFiles:
    def test_missing_pgie_model_file_names_the_key(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path, pgie={"model_file": str(tmp_path / "missing.onnx")})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        with pytest.raises(ModelConfigError, match="pgie.model_file"):
            resolver.resolve_pgie(models)

    def test_missing_pgie_labels_names_the_key(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path, pgie={"labels": str(tmp_path / "missing_labels.txt")})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        with pytest.raises(ModelConfigError, match="pgie.labels"):
            resolver.resolve_pgie(models)

    def test_missing_sgie_model_file_names_the_key(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path, sgie={"model_file": str(tmp_path / "missing.onnx")})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        with pytest.raises(ModelConfigError, match="sgie.model_file"):
            resolver.resolve_sgie(models)

    def test_missing_engine_file_does_not_raise(self, tmp_path: Path) -> None:
        """engine_file is not existence-checked -- nvinfer builds/caches it
        on first run if absent (see models_config.py's docstring)."""
        engine_path = str(tmp_path / "not_yet_built.engine")
        models = _models_settings(tmp_path, pgie={"engine_file": engine_path})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolver.resolve_pgie(models)  # must not raise


class TestRenderedConfig:
    def test_pgie_config_contains_substituted_values(self, tmp_path: Path) -> None:
        models = _models_settings(
            tmp_path, pgie={"batch_size": 4, "confidence_threshold": 0.7, "precision": "int8"}
        )
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_pgie(models)

        assert resolved.is_placeholder is False
        contents = resolved.config_file_path.read_text(encoding="utf-8")
        assert "batch-size=4" in contents
        assert "pre-cluster-threshold=0.7" in contents
        assert "network-mode=1" in contents  # int8
        assert "gie-unique-id=1" in contents
        # 2 non-blank label lines -> num-detected-classes=2
        assert "num-detected-classes=2" in contents

    def test_sgie_config_references_pgie_unique_id(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path, pgie={"unique_id": 7}, sgie={"unique_id": 9})
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_sgie(models)

        contents = resolved.config_file_path.read_text(encoding="utf-8")
        assert "operate-on-gie-id=7" in contents
        assert "gie-unique-id=9" in contents

    def test_generated_file_written_under_generated_dir(self, tmp_path: Path) -> None:
        models = _models_settings(tmp_path)
        generated_dir = tmp_path / "generated"
        resolver = ModelConfigResolver(generated_dir=generated_dir)

        resolved = resolver.resolve_pgie(models)

        assert resolved.config_file_path.parent == generated_dir
        assert resolved.config_file_path.is_file()
