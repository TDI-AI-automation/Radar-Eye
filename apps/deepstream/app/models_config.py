"""External model configuration resolution -- RM-11.SIV Decision C.

nvinfer's per-class confidence threshold (`pre-cluster-threshold`/
`classifier-threshold`) and NMS IoU threshold only exist in its `.txt`
config-file format -- neither is a settable GObject property -- so external
model configuration is applied by rendering a config file from a template,
not by GObject property overrides after element construction. That keeps
one mechanism covering every property in configs/models.yaml uniformly,
rather than splitting the model config across "properties set in Python"
and "properties set in a text file" with an implicit precedence order
between them.

Two checked-in templates (apps/deepstream/configs/pgie.template.txt,
sgie.template.txt) hold only mechanics that never vary by model. Everything
that does vary by model comes from configs/models.yaml (ModelsSettings, see
config.py) and is substituted in here, at pipeline-build time, producing
apps/deepstream/configs/generated/{pgie,sgie}_resolved.txt (gitignored --
machine-generated, not source).

"Do not hardcode paths. Do not assume model locations. Fail fast" (RM-11.SIV
Decision C): every path in a ModelStageSettings is checked to exist before
any file is written; the raised error names the exact configs/models.yaml
key that is wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from string import Template

from apps.deepstream.app.config import ModelsSettings, ModelStageSettings

logger = logging.getLogger(__name__)

_PRECISION_TO_NETWORK_MODE = {"fp32": 0, "int8": 1, "fp16": 2}

_PGIE_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "configs" / "pgie.template.txt"
_SGIE_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "configs" / "sgie.template.txt"
_DEFAULT_GENERATED_DIR = Path(__file__).resolve().parents[1] / "configs" / "generated"

_PGIE_PLACEHOLDER_PATH = "apps/deepstream/configs/pgie_placeholder.txt"
_SGIE_PLACEHOLDER_PATH = "apps/deepstream/configs/sgie_placeholder.txt"

_EXTRA_PROPERTIES_MARKER = "# RM11SIV_EXTRA_PROPERTIES"
"""Matches the marker line in pgie.template.txt/sgie.template.txt --
replaced with zero or more optional nvinfer properties, or removed
entirely (a custom-trained-model stage that needs none of them)."""


class ModelConfigError(RuntimeError):
    """A configs/models.yaml entry references a file that does not exist.
    Always names the exact stage and key at fault -- RM-11.SIV Decision C's
    fail-fast requirement, not a generic DeepStream/GStreamer error."""


@dataclass(frozen=True)
class ResolvedModelConfig:
    config_file_path: Path
    is_placeholder: bool


def _require_file(*, stage: str, key: str, path_str: str) -> Path:
    path = Path(path_str)
    if not path.is_file():
        raise ModelConfigError(
            f"configs/models.yaml: {stage}.{key} = '{path_str}' does not exist "
            f"or is not a file. Fix this path before starting the pipeline -- "
            f"RM-11.SIV Decision C: model locations are never assumed."
        )
    return path


def _count_labels(labels_path: Path) -> int:
    lines = labels_path.read_text(encoding="utf-8").splitlines()
    return len([line for line in lines if line.strip()])


def _bool_to_nvinfer(value: bool) -> int:
    return 1 if value else 0


def _extra_property_lines(stage: ModelStageSettings, *, stage_name: str) -> list[str]:
    """Optional properties only a custom-trained model needs -- see
    ModelStageSettings' docstrings. Only emitted when actually configured,
    so the placeholder/stock-model path (nothing set) renders no extra
    lines at all."""
    lines: list[str] = []
    if stage.infer_dims is not None:
        lines.append(f"infer-dims={stage.infer_dims}")
    if stage.network_type is not None:
        lines.append(f"network-type={stage.network_type}")
    if stage.maintain_aspect_ratio is not None:
        lines.append(f"maintain-aspect-ratio={_bool_to_nvinfer(stage.maintain_aspect_ratio)}")
    if stage.symmetric_padding is not None:
        lines.append(f"symmetric-padding={_bool_to_nvinfer(stage.symmetric_padding)}")
    if stage.custom_lib_path is not None:
        custom_lib_path = _require_file(
            stage=stage_name, key="custom_lib_path", path_str=stage.custom_lib_path
        )
        lines.append(f"custom-lib-path={custom_lib_path}")
    if stage.parse_bbox_func_name is not None:
        lines.append(f"parse-bbox-func-name={stage.parse_bbox_func_name}")
    if stage.operate_on_class_ids is not None:
        lines.append(f"operate-on-class-ids={stage.operate_on_class_ids}")
    if stage.input_object_min_width is not None:
        lines.append(f"input-object-min-width={stage.input_object_min_width}")
    if stage.input_object_min_height is not None:
        lines.append(f"input-object-min-height={stage.input_object_min_height}")
    return lines


class ModelConfigResolver:
    """Resolves the PGIE/SGIE nvinfer config file to actually load, per
    camera pipeline build. Stateless aside from the output directory."""

    def __init__(self, *, generated_dir: Path | None = None) -> None:
        self._generated_dir = generated_dir or _DEFAULT_GENERATED_DIR

    def resolve_pgie(self, models: ModelsSettings) -> ResolvedModelConfig:
        if not models.pgie.enabled:
            logger.info("PGIE: models.yaml pgie.enabled=false -- using placeholder config")
            return ResolvedModelConfig(
                config_file_path=Path(_PGIE_PLACEHOLDER_PATH), is_placeholder=True
            )
        return ResolvedModelConfig(
            config_file_path=self._render_pgie(models.pgie), is_placeholder=False
        )

    def resolve_sgie(self, models: ModelsSettings) -> ResolvedModelConfig:
        if not models.sgie.enabled:
            logger.info("SGIE: models.yaml sgie.enabled=false -- using placeholder config")
            return ResolvedModelConfig(
                config_file_path=Path(_SGIE_PLACEHOLDER_PATH), is_placeholder=True
            )
        return ResolvedModelConfig(
            config_file_path=self._render_sgie(models.sgie, pgie=models.pgie),
            is_placeholder=False,
        )

    def _render_pgie(self, stage: ModelStageSettings) -> Path:
        model_file = _require_file(stage="pgie", key="model_file", path_str=stage.model_file)
        labels_file = _require_file(stage="pgie", key="labels", path_str=stage.labels)
        # engine_file is intentionally not existence-checked -- nvinfer
        # builds and caches it here on first run if absent (standard
        # DeepStream behavior; see ModelStageSettings.engine_file's docstring).

        template = Template(_PGIE_TEMPLATE_PATH.read_text(encoding="utf-8"))
        rendered = template.substitute(
            gpu_id=stage.gpu_id,
            model_file=model_file,
            engine_file=stage.engine_file,
            labels_file=labels_file,
            batch_size=stage.batch_size,
            model_color_format=stage.model_color_format,
            network_mode=_PRECISION_TO_NETWORK_MODE[stage.precision],
            num_detected_classes=_count_labels(labels_file),
            interval=stage.interval,
            unique_id=stage.unique_id,
            cluster_mode=stage.cluster_mode,
            topk=stage.topk,
            nms_iou_threshold=stage.nms_iou_threshold,
            confidence_threshold=stage.confidence_threshold,
        )
        rendered = self._insert_extra_properties(rendered, stage, stage_name="pgie")
        return self._write_generated("pgie_resolved.txt", rendered)

    def _render_sgie(self, stage: ModelStageSettings, *, pgie: ModelStageSettings) -> Path:
        model_file = _require_file(stage="sgie", key="model_file", path_str=stage.model_file)
        labels_file = _require_file(stage="sgie", key="labels", path_str=stage.labels)

        template = Template(_SGIE_TEMPLATE_PATH.read_text(encoding="utf-8"))
        rendered = template.substitute(
            gpu_id=stage.gpu_id,
            model_file=model_file,
            engine_file=stage.engine_file,
            labels_file=labels_file,
            batch_size=stage.batch_size,
            model_color_format=stage.model_color_format,
            network_mode=_PRECISION_TO_NETWORK_MODE[stage.precision],
            confidence_threshold=stage.confidence_threshold,
            operate_on_gie_id=pgie.unique_id,
            unique_id=stage.unique_id,
        )
        rendered = self._insert_extra_properties(rendered, stage, stage_name="sgie")
        return self._write_generated("sgie_resolved.txt", rendered)

    @staticmethod
    def _insert_extra_properties(
        rendered: str, stage: ModelStageSettings, *, stage_name: str
    ) -> str:
        extra_lines = _extra_property_lines(stage, stage_name=stage_name)
        replacement = "\n".join(extra_lines) if extra_lines else ""
        return rendered.replace(_EXTRA_PROPERTIES_MARKER, replacement)

    def _write_generated(self, filename: str, contents: str) -> Path:
        self._generated_dir.mkdir(parents=True, exist_ok=True)
        path = self._generated_dir / filename
        path.write_text(contents, encoding="utf-8")
        return path
