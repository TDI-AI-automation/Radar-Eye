"""Filesystem storage layout and disk management for evidence and recordings.

Source: docs/DATABASE_SCHEMA.md ("Recording Storage Layout"):
  /recordings/
      <camera_id>/
          YYYY-MM-DD/
              continuous/
              events/
  /snapshots/
      <camera_id>/
          YYYY-MM-DD/
"""

from __future__ import annotations

import shutil
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from services.recording.types import RecordingConfig


def get_snapshot_dir(storage_root: str, camera_id: uuid.UUID, timestamp: datetime) -> Path:
    """Returns the snapshot directory for a given camera and timestamp.

    Path format: `<storage_root>/snapshots/<camera_id>/<YYYY-MM-DD>/`
    """
    date_str = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return Path(storage_root) / "snapshots" / str(camera_id) / date_str


def get_snapshot_path(
    storage_root: str, camera_id: uuid.UUID, snapshot_id: uuid.UUID, timestamp: datetime
) -> Path:
    """Returns the full filepath for a snapshot JPEG."""
    directory = get_snapshot_dir(storage_root, camera_id, timestamp)
    return directory / f"{snapshot_id}.jpg"


def get_event_clip_dir(storage_root: str, camera_id: uuid.UUID, timestamp: datetime) -> Path:
    """Returns the event clip directory for a given camera and timestamp.

    Path format: `<storage_root>/recordings/<camera_id>/<YYYY-MM-DD>/events/`
    """
    date_str = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return Path(storage_root) / "recordings" / str(camera_id) / date_str / "events"


def get_event_clip_path(
    storage_root: str, camera_id: uuid.UUID, recording_id: uuid.UUID, timestamp: datetime
) -> Path:
    """Returns the full filepath for an event clip MP4."""
    directory = get_event_clip_dir(storage_root, camera_id, timestamp)
    return directory / f"{recording_id}.mp4"


def get_continuous_dir(storage_root: str, camera_id: uuid.UUID, timestamp: datetime) -> Path:
    """Returns the continuous recording directory for a given camera and timestamp.

    Path format: `<storage_root>/recordings/<camera_id>/<YYYY-MM-DD>/continuous/`
    """
    date_str = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return Path(storage_root) / "recordings" / str(camera_id) / date_str / "continuous"


class StorageManager:
    """Handles filesystem writes and disk space monitoring for recordings."""

    def __init__(self, config: RecordingConfig) -> None:
        self.config = config

    def check_disk_usage(self) -> tuple[float, int, int]:
        """Checks disk usage for the storage root directory.

        Returns:
            Tuple of (usage_percentage, bytes_used, bytes_free)
        """
        root = Path(self.config.storage_root)
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(root)
        total = usage.total if usage.total > 0 else 1
        pct = (usage.used / total) * 100.0
        return pct, usage.used, usage.free

    def write_snapshot_file(
        self,
        camera_id: uuid.UUID,
        snapshot_id: uuid.UUID,
        timestamp: datetime,
        data: bytes | None = None,
    ) -> Path:
        """Writes snapshot file to disk under the specified storage layout."""
        path = get_snapshot_path(self.config.storage_root, camera_id, snapshot_id, timestamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            data if data is not None else b"\xFF\xD8\xFF\xE0\x00\x10JFIF"
        )  # Minimal JPEG header placeholder
        path.write_bytes(content)
        return path

    def write_event_clip_file(
        self,
        camera_id: uuid.UUID,
        recording_id: uuid.UUID,
        timestamp: datetime,
        data: bytes | None = None,
    ) -> Path:
        """Writes event clip MP4 file to disk under the specified storage layout."""
        path = get_event_clip_path(self.config.storage_root, camera_id, recording_id, timestamp)
        path.parent.mkdir(parents=True, exist_ok=True)
        content = (
            data if data is not None else b"\x00\x00\x00\x1cftypisom"
        )  # Minimal MP4 ftyp header placeholder
        path.write_bytes(content)
        return path

    def purge_expired_continuous(self, cutoff_date: date) -> int:
        """Purges continuous recording directories dated strictly before `cutoff_date`.

        Returns:
            Number of purged date directories.
        """
        recordings_dir = Path(self.config.storage_root) / "recordings"
        if not recordings_dir.exists():
            return 0

        purged_count = 0
        for camera_dir in recordings_dir.iterdir():
            if not camera_dir.is_dir():
                continue
            for date_dir in camera_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                try:
                    dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d").date()
                except ValueError:
                    continue

                if dir_date < cutoff_date:
                    continuous_dir = date_dir / "continuous"
                    if continuous_dir.exists():
                        shutil.rmtree(continuous_dir, ignore_errors=True)
                        purged_count += 1
                    # Clean up empty date directory if events is also empty/absent
                    if date_dir.exists() and not any(date_dir.iterdir()):
                        shutil.rmtree(date_dir, ignore_errors=True)

        return purged_count
