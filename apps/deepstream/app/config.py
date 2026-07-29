"""DeepStream pipeline settings.

Reads the ``deepstream:`` section of the same ``configs/settings.yaml`` used
by every other subsystem. Database and encryption secrets are not
duplicated here -- camera ingestion reuses
``apps.api.app.config.get_settings()`` for those (RM-03's established
pattern; ``services/calibration`` already imports ``apps.api.app.models`` /
``apps.api.app.repositories`` directly, per its RM-05 design review).

RM-11.SIV Decision C superseded ``pgie_config_path``/``pgie_is_placeholder``/
``sgie_config_path``/``sgie_is_placeholder`` (RM-11 Phase 1/2's mechanism) --
model configuration now lives entirely in ``configs/models.yaml``
(``ModelsSettings`` below) and is resolved by
``apps.deepstream.app.models_config.ModelConfigResolver``, which falls back
to the original placeholder configs itself when a stage is disabled. Those
four fields were removed rather than kept alongside the new mechanism, per
CLAUDE.md's "avoid backwards-compatibility hacks... if something is unused,
delete it completely" -- ``models.yaml`` is now the only source of truth.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "configs" / "settings.yaml"
DEFAULT_MODELS_PATH = REPO_ROOT / "configs" / "models.yaml"
DEFAULT_LOGGING_PATH = REPO_ROOT / "configs" / "logging.yaml"
DEFAULT_VALIDATION_PATH = REPO_ROOT / "configs" / "validation.yaml"
DEFAULT_VISUALIZATION_PATH = REPO_ROOT / "configs" / "visualization.yaml"


class DeepStreamSettings(BaseModel):
    """Reconnect backoff, heartbeat cadence, and streammux sizing.

    Source: DEEPSTREAM_PIPELINE_SPEC.md Stage 1 (reconnect) and Stage 2
    (StreamMux batching). No architecture document pins exact numeric
    defaults for these -- values below are conservative starting points,
    not benchmarked figures (see RM-11 design review, Decision C: model
    and performance numbers remain unvalidated pending real hardware).
    """

    reconnect_initial_backoff_seconds: float = 1.0
    reconnect_max_backoff_seconds: float = 30.0
    reconnect_backoff_multiplier: float = 2.0
    heartbeat_interval_seconds: float = 1.0
    streammux_batch_size: int = 20
    streammux_batched_push_timeout_us: int = 40000
    """RM-11.SIV real-hardware finding: without this, nvstreammux waits
    indefinitely to fill a full batch (streammux_batch_size) before pushing
    anything downstream. With fewer active sources than batch-size --
    exactly RM-11.SIV's one-camera case, and every case before RM-11 Phase
    3 reaches 20 cameras -- the pipeline reached PAUSED and never left it;
    zero frames ever flowed. Pre-existing gap since RM-11 Phase 0 (not
    something RM-11.SIV's instrumentation introduced), only ever exercised
    on real hardware here for the first time with a single-camera pipeline,
    which is exactly what RM-11.SIV's real-hardware run first caught it.
    40ms matches this value's common DeepStream reference-app default."""
    streammux_width: int = 1920
    streammux_height: int = 1080

    rtsp_default_latency_ms: int = 200
    """RM-11.SIV Decision B: folded into this existing section rather than
    a new configs/rtsp.yaml -- was previously hardcoded in
    ingestion/source.py's build_source_bin. Per-camera transport already
    comes from camera_stream_profiles.transport (DB); latency has no
    per-camera column, so it's a single pipeline-wide default here."""

    tracker_ll_lib_path: str = (
        "/opt/nvidia/deepstream/deepstream/lib/libnvds_nvmultiobjecttracker.so"
    )
    tracker_ll_config_path: str = (
        "/opt/nvidia/deepstream/deepstream/samples/configs/deepstream-app/config_tracker_NvDCF_perf.yml"
    )
    """Standard DeepStream SDK install paths (``deepstream`` symlinks to the
    installed version, e.g. ``deepstream-7.0``) -- not vendored into this
    repo, matching the same reasoning as the PGIE model files themselves."""
    tracker_width: int = 640
    tracker_height: int = 384

    metrics_sample_interval_seconds: float = 2.0
    """How often system-level metrics (GPU/CPU/memory) are sampled via
    subprocess/``/proc`` -- deliberately not per-frame, so instrumentation
    stays lightweight (RM-11 Phase 1 approval's instrumentation constraint)."""

    desired_state_sync_interval_seconds: float = 1.0
    """RM-12 Camera Runtime v1: how often runtime.py re-invokes the
    already-implemented DesiredStateSynchronizer.synchronize() after
    startup. synchronization.py's own docstring is explicit that Step 4
    deliberately did not wire any automatic trigger for it -- this is
    temporary polling infrastructure so UI-driven lifecycle/ai_enabled
    changes reach the running pipeline without a process restart, until a
    later milestone replaces it with event-driven synchronization."""


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(settings_path: Path | None = None) -> DeepStreamSettings:
    """Load the ``deepstream:`` section, uncached (mirrors apps.api.app.config)."""
    path = settings_path or DEFAULT_SETTINGS_PATH
    raw = _load_yaml(path)
    return DeepStreamSettings(**raw.get("deepstream", {}))


@lru_cache
def get_settings() -> DeepStreamSettings:
    return load_settings()


# ---------------------------------------------------------------------------
# RM-11.SIV -- configs/models.yaml, configs/logging.yaml, configs/validation.yaml
#
# Three separate files (RM-11.SIV Decision B), not new sections of
# settings.yaml -- these are new concerns with no existing convention to
# extend, unlike deepstream:/recording:/threat_engine: above. Each gets its
# own uncached load_*()/cached get_*() pair, mirroring load_settings()/
# get_settings() exactly.
# ---------------------------------------------------------------------------


class ModelStageSettings(BaseModel):
    """One PGIE or SGIE model's external location and inference properties.

    Source: RM-11.SIV Decision C. Every field here is either a real nvinfer
    GObject property or feeds ModelConfigResolver's template rendering
    (confidence_threshold/nms_iou_threshold aren't GObject properties --
    see models_config.py's docstring for why rendering, not property
    overrides, is the chosen mechanism).
    """

    enabled: bool = True
    model_file: str
    """Path to the trained model (.onnx/.etlt/.uff) -- never assumed,
    always read from configs/models.yaml (RM-11.SIV Decision C)."""
    engine_file: str
    """Path to the (optionally pre-built) TensorRT engine. If it doesn't
    exist or doesn't match model_file, nvinfer builds and caches it here on
    first run -- standard DeepStream behavior, not something this repo
    re-implements."""
    labels: str
    batch_size: int = 1
    precision: Literal["fp32", "int8", "fp16"] = "fp16"
    """Maps to nvinfer's network-mode: fp32=0, int8=1, fp16=2."""
    interval: int = 0
    confidence_threshold: float = 0.5
    gpu_id: int = 0
    unique_id: int
    nms_iou_threshold: float = 0.5
    topk: int = 20

    # -- Fields below exist for custom-trained models whose output nvinfer
    # cannot decode natively (e.g. a custom YOLO export) -- see
    # apps/deepstream/native/README.md. All optional; a stage that needs
    # none of them (the RM-11 Phase 1/2 placeholder path, still the default
    # via enabled=false) renders identically to before these were added.

    model_color_format: int = 0
    """0=RGB, 1=BGR."""
    cluster_mode: int = 2
    """1=DBSCAN, 2=NMS, 3=DBSCAN+NMS Hybrid, 4=None. Default matches
    nvinfer's own built-in NMS behavior. A custom parse_bbox_func_name that
    already performs its own NMS typically needs 4 -- leaving nvinfer's
    default (2) in that case double-NMS-es and silently drops valid
    detections."""
    network_type: int | None = None
    """0=detector, 1=classifier, 2=segmentation, 100=other. None leaves
    nvinfer's own default (0, detector) in effect -- set explicitly for a
    classifier stage."""
    maintain_aspect_ratio: bool | None = None
    symmetric_padding: bool | None = None
    custom_lib_path: str | None = None
    """Path to a compiled custom bbox-parser plugin (e.g.
    apps/deepstream/native/nvdsinfer_custom_impl_Yolo/
    libnvdsinfer_custom_impl_Yolo.so, built via
    scripts/build_yolo_parser.sh). None means no custom parser -- nvinfer's
    built-in decoding is used, correct for the placeholder/stock-model
    path."""
    parse_bbox_func_name: str | None = None
    """Symbol name custom_lib_path exports (e.g. NvDsInferParseYolo).
    Only meaningful together with custom_lib_path."""
    operate_on_class_ids: str | None = None
    """SGIE only -- semicolon-separated PGIE class ids to classify,
    nvinfer's own operate-on-class-ids format (e.g. "3" for a single
    class). None means classify every detected object."""
    input_object_min_width: int | None = None
    """SGIE only -- skip classifying detections narrower/shorter than this
    many pixels."""
    input_object_min_height: int | None = None
    infer_dims: str | None = None
    """"channels;height;width" (e.g. "3;640;640"). None (the default) omits
    this property entirely, so nvinfer auto-detects it from the ONNX
    model's own input tensor shape -- confirmed against a real working
    config during RM-11.SIV's DeepStream-Yolo integration review to be the
    *correct* default, not merely a fallback: a hardcoded guess here can
    silently mismatch the real model's trained input size, which
    auto-detection cannot get wrong. Only set this explicitly if a specific
    model genuinely requires overriding nvinfer's own detection."""


class ModelsSettings(BaseModel):
    pgie: ModelStageSettings
    sgie: ModelStageSettings


def load_models_settings(models_path: Path | None = None) -> ModelsSettings:
    path = models_path or DEFAULT_MODELS_PATH
    raw = _load_yaml(path)
    return ModelsSettings(**raw)


@lru_cache
def get_models_settings() -> ModelsSettings:
    return load_models_settings()


STAGE_LOGGER_NAMES = (
    "camera",
    "rtsp",
    "deepstream",
    "pgie",
    "nvdcf",
    "sgie",
    "runtime_adapter",
    "threat_runtime_adapter",
    "calibration",
    "threat_engine",
    "incident_service",
    "alarm_service",
    "recording",
    "health",
    "event_bus",
    "performance",
    "system",
    "visualization",
)
"""The stage loggers named in the RM-11.SIV approval's Pipeline
Instrumentation task, plus ``visualization`` (RM-11.SIV visualization
subsystem) -- the fixed, known set of ``radar_eye.stage.<name>`` loggers
that configs/logging.yaml's ``loggers:`` mapping may configure. Kept here
(rather than duplicated in stage_logging.py) as the single list both config
validation and logger setup read from."""


class LoggingSettings(BaseModel):
    default_level: str = "INFO"
    loggers: dict[str, str] = {}
    """Per-stage-logger level override, keyed by name from
    STAGE_LOGGER_NAMES (e.g. {"pgie": "DEBUG"}). Any name not present here
    falls back to default_level."""


def load_logging_settings(logging_path: Path | None = None) -> LoggingSettings:
    path = logging_path or DEFAULT_LOGGING_PATH
    raw = _load_yaml(path)
    return LoggingSettings(**raw)


@lru_cache
def get_logging_settings() -> LoggingSettings:
    return load_logging_settings()


class SIVFeatureFlags(BaseModel):
    """RM-11.SIV Decision A2: global, per-run validation switches -- not a
    database schema change, not per-camera. See validation.yaml."""

    enable_recording: bool = True
    enable_detection: bool = True
    enable_tracking: bool = True
    enable_classification: bool = True
    enable_calibration: bool = True


class WatchdogStaleThresholds(BaseModel):
    camera: float = 5.0
    rtsp: float = 5.0
    pipeline_fps: float = 5.0
    pgie: float = 5.0
    tracker: float = 5.0
    sgie: float = 5.0
    runtime_adapter: float = 5.0
    threat_runtime_adapter: float = 5.0
    threat_engine: float = 10.0
    calibration: float = 10.0
    incident: float = 10.0
    alarm: float = 10.0
    event_bus: float = 10.0
    heartbeat: float = 3.0


class WatchdogSettings(BaseModel):
    check_interval_seconds: float = 2.0
    stale_after_seconds: WatchdogStaleThresholds = WatchdogStaleThresholds()


class FrameTraceSettings(BaseModel):
    enabled: bool = False
    """RM-11.SIV: off by default -- verbose per-frame stage tracing, see
    apps/deepstream/app/siv/pipeline_trace.py."""


class ValidationSettings(BaseModel):
    feature_flags: SIVFeatureFlags = SIVFeatureFlags()
    watchdog: WatchdogSettings = WatchdogSettings()
    frame_trace: FrameTraceSettings = FrameTraceSettings()


def load_validation_settings(validation_path: Path | None = None) -> ValidationSettings:
    path = validation_path or DEFAULT_VALIDATION_PATH
    raw = _load_yaml(path)
    return ValidationSettings(**raw)


@lru_cache
def get_validation_settings() -> ValidationSettings:
    return load_validation_settings()


class ColorSchemeSettings(BaseModel):
    """RGBA hex colors (``#RRGGBB`` or ``#RRGGBBAA``, alpha defaults to
    fully opaque) for the visualization overlay -- see
    apps/deepstream/app/visualization/overlay.py, which is the only code
    that parses these. PGIE class names match the real label set
    (configs/models.yaml's pgie.labels), not a generic placeholder set --
    this model has no "vehicle" class, so none is defined here."""

    fire: str = "#FFA500FF"
    metal: str = "#FF0000FF"
    ranged_metal: str = "#FF0000FF"
    non_metal: str = "#808080FF"
    person: str = "#00FF00FF"
    civilian: str = "#00FFFFFF"
    military: str = "#800080FF"
    threat_high: str = "#FF0000FF"
    threat_medium: str = "#FFFF00FF"
    threat_low: str = "#00FF00FF"
    default: str = "#FFFFFFFF"
    """Fallback for a PGIE class not otherwise listed above."""


class VisualizationPerformanceSettings(BaseModel):
    enable_overlay_cache: bool = True
    """Reserved -- overlay.py implements no caching yet. Exists so a future
    caching change is additive config, not a new field."""


class VisualizationSettings(BaseModel):
    """RM-11.SIV visualization subsystem -- see
    apps/deepstream/app/visualization/. Off by default, matching this
    repo's convention for new/heavy optional subsystems (configs/
    models.yaml's enabled: false, frame_trace.enabled: false)."""

    version: int = 1
    enabled: bool = False
    stream_output_enabled: bool = True
    rtsp_output_enabled: bool = True
    draw_bbox: bool = True
    draw_labels: bool = True
    draw_tracker: bool = True
    draw_sgie: bool = True
    draw_distance: bool = True
    draw_zone: bool = True
    draw_threat: bool = True
    draw_fps: bool = True
    draw_latency: bool = True
    draw_timestamp: bool = True
    draw_camera_name: bool = True
    draw_gpu: bool = True
    draw_system_status: bool = False
    font_size: int = 12
    line_thickness: int = 3
    color_scheme: ColorSchemeSettings = ColorSchemeSettings()
    output_codec: Literal["h264"] = "h264"
    """Only h264 (via nvv4l2h264enc) is implemented -- a Literal, not a
    free string, so an unsupported value fails validation immediately
    rather than surfacing as a confusing GStreamer element-creation error
    later."""
    output_bitrate: int = 4_000_000
    output_fps: int = 30
    rtsp_port: int = 8554
    stream_name: str = "radar-eye"
    annotation_ttl_seconds: float = 5.0
    """How long a track's calibration/threat-engine annotation (zone,
    distance, threat level) stays valid for overlay purposes after its last
    update -- see visualization/track_annotations.py."""
    performance: VisualizationPerformanceSettings = VisualizationPerformanceSettings()


def load_visualization_settings(visualization_path: Path | None = None) -> VisualizationSettings:
    path = visualization_path or DEFAULT_VISUALIZATION_PATH
    raw = _load_yaml(path)
    return VisualizationSettings(**raw)


@lru_cache
def get_visualization_settings() -> VisualizationSettings:
    return load_visualization_settings()
