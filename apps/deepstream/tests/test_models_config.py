"""Tests for models_config.py -- RM-11.SIV Decision C.

SDK-free: ModelConfigResolver only reads/writes plain files, no pyds/gi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.deepstream.app.config import ModelsSettings, ModelStageSettings
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
    return ModelsSettings(pgie=ModelStageSettings(**pgie), sgie=ModelStageSettings(**sgie))


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

    def test_default_stage_has_no_extra_properties(self, tmp_path: Path) -> None:
        """The placeholder/stock-model path (nothing set) must render with
        none of the custom-model-only properties present at all."""
        models = _models_settings(tmp_path)
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_pgie(models)

        contents = resolved.config_file_path.read_text(encoding="utf-8")
        for prop in (
            "custom-lib-path",
            "parse-bbox-func-name",
            "network-type",
            "maintain-aspect-ratio",
            "symmetric-padding",
            "operate-on-class-ids",
            "input-object-min-width",
            "infer-dims",
        ):
            # "=" form only -- some of these names also appear in prose
            # comments explaining what the marker inserts.
            assert f"{prop}=" not in contents


class TestCustomModelProperties:
    """RM-11.SIV Decision C extension -- custom-trained models (e.g. a
    custom YOLO export via a vendored bbox parser plugin, see
    apps/deepstream/native/README.md) need properties the stock/placeholder
    path never uses."""

    def test_custom_lib_path_must_exist(self, tmp_path: Path) -> None:
        models = _models_settings(
            tmp_path,
            pgie={
                "custom_lib_path": str(tmp_path / "missing.so"),
                "parse_bbox_func_name": "NvDsInferParseYolo",
            },
        )
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        with pytest.raises(ModelConfigError, match="pgie.custom_lib_path"):
            resolver.resolve_pgie(models)

    def test_custom_parser_properties_appear_when_configured(self, tmp_path: Path) -> None:
        custom_lib = tmp_path / "libnvdsinfer_custom_impl_Yolo.so"
        custom_lib.write_bytes(b"fake-so")
        models = _models_settings(
            tmp_path,
            pgie={
                "custom_lib_path": str(custom_lib),
                "parse_bbox_func_name": "NvDsInferParseYolo",
                "cluster_mode": 4,
                "network_type": 0,
                "maintain_aspect_ratio": True,
                "symmetric_padding": True,
                "topk": 300,
                "infer_dims": "3;640;640",
            },
        )
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_pgie(models)

        contents = resolved.config_file_path.read_text(encoding="utf-8")
        assert f"custom-lib-path={custom_lib}" in contents
        assert "parse-bbox-func-name=NvDsInferParseYolo" in contents
        assert "cluster-mode=4" in contents
        assert "network-type=0" in contents
        assert "maintain-aspect-ratio=1" in contents
        assert "symmetric-padding=1" in contents
        assert "infer-dims=3;640;640" in contents
        assert "topk=300" in contents

    def test_sgie_operate_on_class_ids_and_min_size(self, tmp_path: Path) -> None:
        models = _models_settings(
            tmp_path,
            sgie={
                "operate_on_class_ids": "3",
                "input_object_min_width": 32,
                "input_object_min_height": 64,
                "model_color_format": 0,
                "network_type": 1,
                "maintain_aspect_ratio": False,
            },
        )
        resolver = ModelConfigResolver(generated_dir=tmp_path / "generated")

        resolved = resolver.resolve_sgie(models)

        contents = resolved.config_file_path.read_text(encoding="utf-8")
        assert "operate-on-class-ids=3" in contents
        assert "input-object-min-width=32" in contents
        assert "input-object-min-height=64" in contents
        assert "model-color-format=0" in contents
        assert "network-type=1" in contents
        assert "maintain-aspect-ratio=0" in contents
