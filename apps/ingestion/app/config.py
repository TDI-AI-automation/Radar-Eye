"""Camera Ingestion Service settings.

Reads ``configs/ingestion.yaml``, mirroring
``apps.deepstream.app.config``'s ``load_*``/``get_*`` (cached) pair
convention exactly. Database and encryption secrets are not duplicated
here -- reuses ``apps.api.app.config.get_settings()`` for those, the
same established cross-subsystem pattern
``apps/deepstream/app/ingestion/camera_registry.py`` already uses.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_INGESTION_PATH = REPO_ROOT / "configs" / "ingestion.yaml"


class IngestionSettings(BaseModel):
    """Camera Ingestion's own settings -- reconnect backoff, desired-
    state poll cadence, and the Media Distribution Interface's Phase 1
    (RTSP) publish addressing."""

    reconnect_initial_backoff_seconds: float = 1.0
    reconnect_max_backoff_seconds: float = 30.0
    reconnect_backoff_multiplier: float = 2.0
    desired_state_poll_interval_seconds: float = 1.0
    """How often the camera roster (registered cameras + their RTSP
    connection config) is re-read from Camera Registry -- there is no
    AI-eligibility concept here at all; every registered camera with a
    stream profile is always ingested, matching this codebase's
    existing 'a registered camera always connects' invariant, now
    scoped to this service instead of DeepStream."""
    rtsp_default_latency_ms: int = 200

    publish_host: str = "127.0.0.1"
    """Media Distribution Interface publish bind host -- 127.0.0.1 only,
    never network-exposed, matching Live Monitoring's existing signaling
    server convention. Every consumer runs on the same node."""
    publish_rtsp_port: int = 8600
    publish_udp_port_range_start: int = 8700
    """Internal-only loopback UDP relay ports, one per published camera
    (mirrors apps/deepstream/app/visualization/stream_server.py's proven
    udpsrc-wrapping RTSP-out pattern) -- never exposed outside this
    process; only publish_rtsp_port is a real cross-process address."""


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def load_settings(settings_path: Path | None = None) -> IngestionSettings:
    path = settings_path or DEFAULT_INGESTION_PATH
    if not path.exists():
        return IngestionSettings()
    raw = _load_yaml(path)
    return IngestionSettings(**raw)


@lru_cache
def get_settings() -> IngestionSettings:
    return load_settings()
