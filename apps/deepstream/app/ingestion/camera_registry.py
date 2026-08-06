"""The RTSP source bin's connection-info data contract.

``CameraRegistry.load_camera_sources()`` (a startup-time batch loader that
read ``camera_stream_profiles`` -- the physical camera's own credentials --
directly) was removed: it had no callers (superseded entirely by
``desired_state.py``'s ``DesiredStateReader``, which every live code path
actually uses) and, more importantly, it re-derived the camera's direct
RTSP URL instead of going through Camera Ingestion -- exactly the ADR-028
violation ``DesiredStateReader`` was fixed to avoid. Removed rather than
fixed-in-place, to avoid leaving two parallel readers of camera connection
info that could silently drift apart again.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraSource:
    """Everything RM-11 needs to build one RTSP source bin."""

    camera_id: uuid.UUID
    name: str
    rtsp_url: str
    transport: str
