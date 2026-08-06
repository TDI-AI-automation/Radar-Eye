"""Live Streaming Service settings -- mirrors apps/ingestion/app/config.py's
shape (own reconnect/poll knobs), plus the WebRTC signaling bind
host/port and STUN server list ``apps/deepstream/app/config.py``'s
``LiveStreamSettings`` already established the shape of.

Deliberately its own config file (``configs/live_streaming.yaml``), not
``configs/live_stream.yaml`` -- that file, and the port it currently
configures (8590), still belong to the old, unmigrated
``apps.deepstream.app.live_stream`` package and ``apps.api``'s proxy
target during this build-alongside-then-cutover period (ADR-028's
migration phases). This service's own default port (8591) avoids
colliding with it; the cutover (removing the old package, repointing
``apps.api``'s proxy) is a distinct, later step.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LIVE_STREAMING_PATH = REPO_ROOT / "configs" / "live_streaming.yaml"


class LiveStreamingSettings(BaseModel):
    upstream_subsystem: str = "ingestion"
    """Which subsystem's published endpoints this service subscribes to
    -- always Camera Ingestion's raw stream for Live Streaming. AI
    Streaming (Phase 5), reusing the same shared/ WebRTC library, would
    set this to "ai" instead."""

    reconnect_initial_backoff_seconds: float = 1.0
    reconnect_max_backoff_seconds: float = 30.0
    reconnect_backoff_multiplier: float = 2.0
    desired_state_poll_interval_seconds: float = 1.0
    rtsp_default_latency_ms: int = 200

    signaling_host: str = "127.0.0.1"
    """Never network-exposed -- apps.api is the sole externally-reachable
    authenticated door (ADR-011)."""
    signaling_port: int = 8591
    stun_servers: list[str] = []
    """Empty by default -- a single-node, air-gapped, LAN deployment only
    ever needs host ICE candidates; no STUN/TURN server is reachable or
    required."""


def load_settings(path: Path | None = None) -> LiveStreamingSettings:
    config_path = path or DEFAULT_LIVE_STREAMING_PATH
    if not config_path.is_file():
        return LiveStreamingSettings()
    import yaml  # noqa: PLC0415

    raw: dict[str, Any] = yaml.safe_load(config_path.read_text()) or {}
    return LiveStreamingSettings(**raw)


@lru_cache
def get_settings() -> LiveStreamingSettings:
    return load_settings()
