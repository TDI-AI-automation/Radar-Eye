"""DeepStream pipeline settings.

Reads the ``deepstream:`` section of the same ``configs/settings.yaml`` used
by every other subsystem. Database and encryption secrets are not
duplicated here -- camera ingestion reuses
``apps.api.app.config.get_settings()`` for those (RM-03's established
pattern; ``services/calibration`` already imports ``apps.api.app.models`` /
``apps.api.app.repositories`` directly, per its RM-05 design review).
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
    streammux_width: int = 1920
    streammux_height: int = 1080

    pgie_config_path: str = "apps/deepstream/configs/pgie_placeholder.txt"
    """Relative to the repo root unless already absolute. Placeholder model
    per RM-11 Phase 1 (Decision C) -- see the referenced file's header."""
    pgie_is_placeholder: bool = True
    """Logged/exposed alongside performance metrics so placeholder-model
    results are never mistaken for production-model benchmarks."""

    sgie_config_path: str = "apps/deepstream/configs/sgie_placeholder.txt"
    """Relative to the repo root unless already absolute. Placeholder
    classifier per RM-11 Phase 2 (Decision B) -- see the referenced file's
    header."""
    sgie_is_placeholder: bool = True

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


_STAGE_LOGGER_NAMES = (
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
)
"""The 17 stage loggers named in the RM-11.SIV approval's Pipeline
Instrumentation task -- the fixed, known set of ``radar_eye.stage.<name>``
loggers that configs/logging.yaml's ``loggers:`` mapping may configure.
Kept here (rather than duplicated in stage_logging.py) as the single list
both config validation and logger setup read from."""


class LoggingSettings(BaseModel):
    default_level: str = "INFO"
    loggers: dict[str, str] = {}
    """Per-stage-logger level override, keyed by name from
    _STAGE_LOGGER_NAMES (e.g. {"pgie": "DEBUG"}). Any name not present here
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
    pipeline_fps: float = 5.0
    pgie: float = 5.0
    tracker: float = 5.0
    sgie: float = 5.0
    runtime_adapter: float = 5.0
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
