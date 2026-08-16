"""Recording & Evidence Service types and configuration.

Source: docs/IMPLEMENTATION_ROADMAP.md (RM-08), ADR-017 (Recording Strategy),
docs/DATABASE_SCHEMA.md ("Recording Storage Layout"), docs/EVENT_CONTRACTS.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RecordingConfig:
    """Configuration options for the Recording & Evidence Service.

    Retention policy duration (`retention_days`) remains ADR-017 as documented
    (30 days retention), but is kept isolated as a configurable value so future
    storage-sizing changes do not require code modifications.
    """

    storage_root: str = "storage"
    """Base directory on the local filesystem for recording and snapshot storage."""

    retention_days: int = 30
    """Continuous recording retention policy duration in days (ADR-017)."""

    pre_incident_buffer_sec: int = 10
    """Pre-incident video buffer duration in seconds for event clips."""

    post_incident_buffer_sec: int = 20
    """Post-incident video buffer duration in seconds for event clips."""

    disk_warning_threshold_pct: float = 90.0
    """Disk usage percentage at which a CRITICAL SystemEvent health warning is emitted."""


@dataclass(frozen=True)
class SnapshotResult:
    """Result of snapshot generation."""

    snapshot_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    file_path: str
    captured_at: datetime


@dataclass(frozen=True)
class ClipResult:
    """Result of event clip generation."""

    recording_id: uuid.UUID
    incident_id: uuid.UUID
    camera_id: uuid.UUID
    file_path: str
    start_time: datetime
    end_time: datetime


class RecordingError(Exception):
    """Base exception for Recording & Evidence Service errors."""


class StorageQuotaExceededError(RecordingError):
    """Raised when available disk space is exhausted or quota exceeded."""
