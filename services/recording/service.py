"""Recording & Evidence Service logic: snapshot capture, clip extraction, and storage retention.

Source: docs/IMPLEMENTATION_ROADMAP.md (RM-08), ADR-017 (Recording Strategy),
docs/DATABASE_SCHEMA.md ("Recording Storage Layout"), docs/EVENT_CONTRACTS.md.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from services.recording.storage import StorageManager
from services.recording.types import ClipResult, RecordingConfig, SnapshotResult
from shared.events.bus import EventBus
from shared.events.payloads import ClipCreatedPayload, SnapshotCreatedPayload, SystemEventPayload
from shared.events.types import (
    ClipCreatedEvent,
    IncidentCreatedEvent,
    SnapshotCreatedEvent,
    SystemEvent,
)


class RecordingService:
    """Owns evidence snapshot generation, event clip extraction, and retention management."""

    def __init__(
        self,
        session: AsyncSession,
        config: RecordingConfig | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self._session = session
        self._config = config or RecordingConfig()
        self._snapshot_repo = SnapshotRepository(session)
        self._recording_repo = RecordingRepository(session)
        self._storage = StorageManager(self._config)
        self._bus = bus

    async def on_incident_created(
        self,
        event: IncidentCreatedEvent,
        image_data: bytes | None = None,
        video_data: bytes | None = None,
    ) -> tuple[SnapshotResult, ClipResult]:
        """Event handler for IncidentCreatedEvent.

        Extracts snapshot and event clip media for the created incident.
        """
        snapshot = await self.create_snapshot(
            incident_id=event.payload.incident_id,
            camera_id=event.payload.camera_id,
            captured_at=event.timestamp,
            image_data=image_data,
        )
        clip = await self.create_event_clip(
            incident_id=event.payload.incident_id,
            camera_id=event.payload.camera_id,
            incident_time=event.timestamp,
            video_data=video_data,
        )
        return snapshot, clip

    async def create_snapshot(
        self,
        incident_id: uuid.UUID,
        camera_id: uuid.UUID,
        captured_at: datetime,
        image_data: bytes | None = None,
    ) -> SnapshotResult:
        """Captures a snapshot image asset, saves DB metadata, and emits SnapshotCreatedEvent."""
        snapshot_id = uuid.uuid4()
        filepath = self._storage.write_snapshot_file(
            camera_id=camera_id,
            snapshot_id=snapshot_id,
            timestamp=captured_at,
            data=image_data,
        )

        snapshot_model = Snapshot(
            id=snapshot_id,
            incident_id=incident_id,
            camera_id=camera_id,
            file_path=str(filepath),
            captured_at=captured_at,
        )
        await self._snapshot_repo.add(snapshot_model)

        result = SnapshotResult(
            snapshot_id=snapshot_id,
            incident_id=incident_id,
            camera_id=camera_id,
            file_path=str(filepath),
            captured_at=captured_at,
        )

        await self._publish_snapshot_created(result)
        return result

    async def create_event_clip(
        self,
        incident_id: uuid.UUID,
        camera_id: uuid.UUID,
        incident_time: datetime,
        video_data: bytes | None = None,
    ) -> ClipResult:
        """Extracts an event clip (10s pre / 20s post buffer),
        saves DB metadata, and emits ClipCreatedEvent.
        """
        start_time = incident_time - timedelta(seconds=self._config.pre_incident_buffer_sec)
        end_time = incident_time + timedelta(seconds=self._config.post_incident_buffer_sec)
        recording_id = uuid.uuid4()

        filepath = self._storage.write_event_clip_file(
            camera_id=camera_id,
            recording_id=recording_id,
            timestamp=incident_time,
            data=video_data,
        )

        recording_model = Recording(
            id=recording_id,
            incident_id=incident_id,
            camera_id=camera_id,
            file_path=str(filepath),
            start_time=start_time,
            end_time=end_time,
            created_at=incident_time,
        )
        await self._recording_repo.add(recording_model)

        result = ClipResult(
            recording_id=recording_id,
            incident_id=incident_id,
            camera_id=camera_id,
            file_path=str(filepath),
            start_time=start_time,
            end_time=end_time,
        )

        await self._publish_clip_created(result)
        return result

    async def check_storage_and_purge(self, now: datetime | None = None) -> int:
        """Purges expired continuous recordings based on `retention_days` and monitors disk quota.

        Emits a CRITICAL SystemEvent if disk space usage exceeds the configured threshold.
        """
        current_time = now or datetime.now(timezone.utc)
        cutoff_date = (current_time - timedelta(days=self._config.retention_days)).date()

        purged_count = self._storage.purge_expired_continuous(cutoff_date)

        pct, _, free = self._storage.check_disk_usage()
        if pct >= self._config.disk_warning_threshold_pct:
            free_mb = free // (1024 * 1024)
            await self._publish_system_event(
                severity="CRITICAL",
                message=f"Storage warning: disk usage at {pct:.1f}% ({free_mb} MB free)",
            )

        return purged_count

    async def _publish_snapshot_created(self, snapshot: SnapshotResult) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            SnapshotCreatedEvent(
                event_type="SnapshotCreatedEvent",
                source="recording_service",
                payload=SnapshotCreatedPayload(
                    snapshot_id=snapshot.snapshot_id,
                    incident_id=snapshot.incident_id,
                    camera_id=snapshot.camera_id,
                    file_path=snapshot.file_path,
                ),
            )
        )

    async def _publish_clip_created(self, clip: ClipResult) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            ClipCreatedEvent(
                event_type="ClipCreatedEvent",
                source="recording_service",
                payload=ClipCreatedPayload(
                    recording_id=clip.recording_id,
                    incident_id=clip.incident_id,
                    camera_id=clip.camera_id,
                    file_path=clip.file_path,
                ),
            )
        )

    async def _publish_system_event(self, severity: str, message: str) -> None:
        if self._bus is None:
            return
        await self._bus.publish(
            SystemEvent(
                event_type="SystemEvent",
                source="recording_service",
                payload=SystemEventPayload(
                    severity=severity,  # type: ignore[arg-type]
                    source_component="recording",
                    message=message,
                ),
            )
        )
