"""Unit and integration tests for Recording & Evidence Service (RM-08)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.camera import Camera
from apps.api.app.models.incident import Incident
from apps.api.app.repositories.camera import CameraRepository
from apps.api.app.repositories.incident import IncidentRepository
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from services.recording.service import RecordingService
from services.recording.storage import (
    StorageManager,
    get_continuous_dir,
    get_event_clip_dir,
    get_snapshot_dir,
)
from services.recording.types import RecordingConfig
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.events.bus import InProcessEventBus
from shared.events.payloads import IncidentCreatedPayload
from shared.events.types import (
    ClipCreatedEvent,
    IncidentCreatedEvent,
    SnapshotCreatedEvent,
    SystemEvent,
)


async def _setup_camera_and_incident(
    session: AsyncSession,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper to create a prerequisite Camera and Incident in DB."""
    camera_repo = CameraRepository(session)
    incident_repo = IncidentRepository(session)

    camera = Camera(name="Test Camera", location="North Gate", status="CONNECTED")
    await camera_repo.add(camera)

    incident = Incident(
        camera_id=camera.id,
        track_id=101,
        incident_type=IncidentType.THREAT,
        threat_level=ThreatLevel.HIGH,
        status=IncidentStatus.ACTIVE,
        threat_summary={"weapon": "ranged_lethal"},
    )
    await incident_repo.add(incident)
    await session.commit()

    return camera.id, incident.id


@pytest.mark.asyncio
async def test_create_snapshot(
    db_session: AsyncSession,
    recording_config: RecordingConfig,
) -> None:
    """Verifies snapshot file creation, database persistence, and layout."""
    bus = InProcessEventBus()
    service = RecordingService(db_session, config=recording_config, bus=bus)
    camera_id, incident_id = await _setup_camera_and_incident(db_session)
    captured_at = datetime.now(timezone.utc)

    # Subscribe to event bus
    received_events = []

    async def _on_event(evt: SnapshotCreatedEvent) -> None:
        received_events.append(evt)

    bus.subscribe("SnapshotCreatedEvent", _on_event)

    res = await service.create_snapshot(
        incident_id=incident_id,
        camera_id=camera_id,
        captured_at=captured_at,
        image_data=b"test-snapshot-jpeg-data",
    )
    await db_session.commit()

    # Verify file exists on disk with expected contents
    filepath = Path(res.file_path)
    assert filepath.exists()
    assert filepath.read_bytes() == b"test-snapshot-jpeg-data"

    # Verify layout path structure matches /snapshots/<camera_id>/<YYYY-MM-DD>/<snapshot_id>.jpg
    expected_dir = get_snapshot_dir(recording_config.storage_root, camera_id, captured_at)
    assert filepath.parent == expected_dir

    # Verify DB record via repository
    snapshot_repo = SnapshotRepository(db_session)
    db_snapshot = await snapshot_repo.get_by_incident_id(incident_id)
    assert db_snapshot is not None
    assert db_snapshot.id == res.snapshot_id
    assert db_snapshot.camera_id == camera_id
    assert db_snapshot.file_path == res.file_path

    # Verify event publication
    assert len(received_events) == 1
    assert received_events[0].payload.snapshot_id == res.snapshot_id
    assert received_events[0].payload.incident_id == incident_id


@pytest.mark.asyncio
async def test_create_event_clip(
    db_session: AsyncSession,
    recording_config: RecordingConfig,
) -> None:
    """Verifies event clip timing (-10s / +20s), file creation, DB record, and layout."""
    bus = InProcessEventBus()
    service = RecordingService(db_session, config=recording_config, bus=bus)
    camera_id, incident_id = await _setup_camera_and_incident(db_session)
    incident_time = datetime(2026, 7, 21, 12, 0, 0, tzinfo=timezone.utc)

    received_events = []

    async def _on_event(evt: ClipCreatedEvent) -> None:
        received_events.append(evt)

    bus.subscribe("ClipCreatedEvent", _on_event)

    res = await service.create_event_clip(
        incident_id=incident_id,
        camera_id=camera_id,
        incident_time=incident_time,
        video_data=b"test-clip-mp4-data",
    )
    await db_session.commit()

    # Verify 10s pre-incident and 20s post-incident buffer timing
    expected_start = incident_time - timedelta(seconds=10)
    expected_end = incident_time + timedelta(seconds=20)
    assert res.start_time == expected_start
    assert res.end_time == expected_end

    # Verify file exists on disk
    filepath = Path(res.file_path)
    assert filepath.exists()
    assert filepath.read_bytes() == b"test-clip-mp4-data"

    # Verify directory structure matches /recordings/<camera_id>/<YYYY-MM-DD>/events/
    expected_dir = get_event_clip_dir(recording_config.storage_root, camera_id, incident_time)
    assert filepath.parent == expected_dir

    # Verify DB record
    rec_repo = RecordingRepository(db_session)
    db_recording = await rec_repo.get_by_incident_id(incident_id)
    assert db_recording is not None
    assert db_recording.id == res.recording_id
    assert db_recording.start_time == expected_start
    assert db_recording.end_time == expected_end

    # Verify event publication
    assert len(received_events) == 1
    assert received_events[0].payload.recording_id == res.recording_id
    assert received_events[0].payload.file_path == res.file_path


@pytest.mark.asyncio
async def test_on_incident_created_handler(
    db_session: AsyncSession,
    recording_config: RecordingConfig,
) -> None:
    """Verifies on_incident_created generates both a snapshot and clip."""
    bus = InProcessEventBus()
    service = RecordingService(db_session, config=recording_config, bus=bus)
    camera_id, incident_id = await _setup_camera_and_incident(db_session)
    now = datetime.now(timezone.utc)

    event = IncidentCreatedEvent(
        event_type="IncidentCreatedEvent",
        source="incident_service",
        timestamp=now,
        payload=IncidentCreatedPayload(
            incident_id=incident_id,
            camera_id=camera_id,
            track_id=101,
            incident_type=IncidentType.THREAT,
            threat_level=ThreatLevel.HIGH,
            status=IncidentStatus.NEW,
        ),
    )

    snapshot_res, clip_res = await service.on_incident_created(event)
    await db_session.commit()

    assert snapshot_res.incident_id == incident_id
    assert clip_res.incident_id == incident_id
    assert Path(snapshot_res.file_path).exists()
    assert Path(clip_res.file_path).exists()


@pytest.mark.asyncio
async def test_purge_expired_continuous_recordings(
    recording_config: RecordingConfig,
) -> None:
    """Verifies continuous recording retention sweep purges older directories
    while preserving event clips.
    """
    storage = StorageManager(recording_config)
    camera_id = uuid.uuid4()

    # Create continuous recording file dated 40 days ago (expired)
    old_date = datetime.now(timezone.utc) - timedelta(days=40)
    old_dir = get_continuous_dir(recording_config.storage_root, camera_id, old_date)
    old_dir.mkdir(parents=True, exist_ok=True)
    old_file = old_dir / "old_stream.mp4"
    old_file.write_bytes(b"old_data")

    # Create continuous recording file dated 10 days ago (recent)
    recent_date = datetime.now(timezone.utc) - timedelta(days=10)
    recent_dir = get_continuous_dir(recording_config.storage_root, camera_id, recent_date)
    recent_dir.mkdir(parents=True, exist_ok=True)
    recent_file = recent_dir / "recent_stream.mp4"
    recent_file.write_bytes(b"recent_data")

    # Create event clip file dated 40 days ago (should NOT be purged by continuous retention sweep)
    event_dir = get_event_clip_dir(recording_config.storage_root, camera_id, old_date)
    event_dir.mkdir(parents=True, exist_ok=True)
    event_file = event_dir / "event_clip.mp4"
    event_file.write_bytes(b"event_data")

    # Run purge cutoff for 30 days ago
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=30)).date()
    purged_count = storage.purge_expired_continuous(cutoff_date)

    assert purged_count == 1
    assert not old_file.exists()
    assert recent_file.exists()
    assert event_file.exists()  # Event clips preserved


@pytest.mark.asyncio
async def test_disk_usage_warning_threshold(
    temp_storage_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies CRITICAL SystemEvent emission when disk usage exceeds warning threshold."""
    from unittest.mock import MagicMock

    bus = InProcessEventBus()
    config = RecordingConfig(
        storage_root=str(temp_storage_dir),
        disk_warning_threshold_pct=80.0,
    )
    mock_session = MagicMock(spec=AsyncSession)
    service = RecordingService(mock_session, config=config, bus=bus)

    # Mock shutil.disk_usage to return 85% usage
    class MockUsage:
        total = 1000 * 1024 * 1024
        used = 850 * 1024 * 1024
        free = 150 * 1024 * 1024

    monkeypatch.setattr("shutil.disk_usage", lambda _: MockUsage())

    received_system_events = []

    async def _on_system_event(evt: SystemEvent) -> None:
        received_system_events.append(evt)

    bus.subscribe("SystemEvent", _on_system_event)

    await service.check_storage_and_purge(now=datetime.now(timezone.utc))

    assert len(received_system_events) == 1
    assert received_system_events[0].payload.severity == "CRITICAL"
    assert "85.0%" in received_system_events[0].payload.message


@pytest.mark.asyncio
async def test_repository_helpers(
    db_session: AsyncSession,
    recording_config: RecordingConfig,
) -> None:
    """Verifies SnapshotRepository and RecordingRepository helper methods."""
    service = RecordingService(db_session, config=recording_config)
    camera_id, incident_id = await _setup_camera_and_incident(db_session)
    now = datetime.now(timezone.utc)

    snap = await service.create_snapshot(incident_id, camera_id, now)
    clip = await service.create_event_clip(incident_id, camera_id, now)
    await db_session.commit()

    snap_repo = SnapshotRepository(db_session)
    rec_repo = RecordingRepository(db_session)

    snaps_list = await snap_repo.list_by_incident(incident_id)
    assert len(snaps_list) == 1
    assert snaps_list[0].id == snap.snapshot_id

    recs_list = await rec_repo.list_by_incident(incident_id)
    assert len(recs_list) == 1
    assert recs_list[0].id == clip.recording_id

    future_cutoff = now + timedelta(hours=1)
    expired_recs = await rec_repo.list_expired(future_cutoff)
    assert len(expired_recs) == 1
    assert expired_recs[0].id == clip.recording_id
