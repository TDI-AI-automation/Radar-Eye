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
