"""Recording & Evidence Service package.

Source: docs/IMPLEMENTATION_ROADMAP.md (RM-08), ADR-017 (Recording Strategy).
"""

from __future__ import annotations

from services.recording.service import RecordingService
from services.recording.storage import (
    StorageManager,
    get_continuous_dir,
    get_event_clip_dir,
    get_snapshot_dir,
)
from services.recording.types import (
    ClipResult,
    RecordingConfig,
    RecordingError,
    SnapshotResult,
    StorageQuotaExceededError,
)

__all__ = [
    "RecordingService",
    "RecordingConfig",
    "RecordingError",
    "StorageQuotaExceededError",
    "SnapshotResult",
    "ClipResult",
    "StorageManager",
    "get_snapshot_dir",
    "get_event_clip_dir",
    "get_continuous_dir",
]
