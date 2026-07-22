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

import yaml
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "configs" / "settings.yaml"


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
