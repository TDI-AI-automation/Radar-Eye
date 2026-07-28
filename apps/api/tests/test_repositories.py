from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from apps.api.app.models.audit_log import AuditLog
from apps.api.app.models.camera import Camera, CameraCalibration, CameraStreamProfile
from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.models.incident import Incident, IncidentEvent
from apps.api.app.models.recording import Recording, Snapshot
from apps.api.app.models.system_event import SystemEvent
from apps.api.app.models.user import User
from apps.api.app.repositories.audit_log import AuditLogRepository
from apps.api.app.repositories.camera import (
    CameraCalibrationRepository,
    CameraRepository,
    CameraStreamProfileRepository,
)
from apps.api.app.repositories.human_review import HumanReviewRepository
from apps.api.app.repositories.incident import IncidentEventRepository, IncidentRepository
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from apps.api.app.repositories.system_event import SystemEventRepository
from apps.api.app.repositories.user import UserRepository
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel


async def _make_camera(session, name: str = "cam-1") -> Camera:
    camera = Camera(name=name, location="north gate", status="CONNECTED")
    return await CameraRepository(session).add(camera)


@pytest.mark.asyncio
class TestCameraRepository:
    async def test_add_and_get_round_trips(self, db_session) -> None:
        camera = await _make_camera(db_session)

        fetched = await CameraRepository(db_session).get(camera.id)

        assert fetched is not None
        assert fetched.name == "cam-1"
        assert fetched.status == "CONNECTED"

    async def test_invalid_status_rejected_by_check_constraint(self, db_session) -> None:
        camera = Camera(name="cam-2", status="NOT_A_REAL_STATUS")
        with pytest.raises(IntegrityError):
            await CameraRepository(db_session).add(camera)

    async def test_list_returns_all(self, db_session) -> None:
        await _make_camera(db_session, name="cam-1")
        await _make_camera(db_session, name="cam-2-b")

        cameras = await CameraRepository(db_session).list()

        assert len(cameras) == 2


@pytest.mark.asyncio
class TestCameraStreamProfileAndCalibration:
    async def test_stream_profile_round_trips(self, db_session) -> None:
        camera = await _make_camera(db_session)
        profile = CameraStreamProfile(
            camera_id=camera.id,
            rtsp_url_encrypted="gAAAAA-fake-ciphertext",
            transport="tcp",
        )

        saved = await CameraStreamProfileRepository(db_session).add(profile)

        assert saved.camera_id == camera.id

    async def test_calibration_round_trips(self, db_session) -> None:
        camera = await _make_camera(db_session)
        calibration = CameraCalibration(
            camera_id=camera.id,
            homography_matrix={"matrix": [[1, 0], [0, 1]]},
            reference_points={"points": [[0, 0], [1, 1]]},
            calibrated_by="installer-1",
        )

        saved = await CameraCalibrationRepository(db_session).add(calibration)

        assert saved.homography_matrix == {"matrix": [[1, 0], [0, 1]]}


@pytest.mark.asyncio
class TestIncidentDeduplication:
    """Acceptance criterion: (camera_id, track_id) active-incident uniqueness."""

    async def test_second_active_incident_for_same_track_is_rejected(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = IncidentRepository(db_session)
        await repo.add(
            Incident(
                camera_id=camera.id,
                track_id=42,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={"rule_id": "RANGED_LETHAL_ZONE_1"},
            )
        )

        with pytest.raises(IntegrityError):
            await repo.add(
                Incident(
                    camera_id=camera.id,
                    track_id=42,
                    incident_type=IncidentType.THREAT,
                    threat_level=ThreatLevel.HIGH,
                    status=IncidentStatus.ACTIVE,
                    threat_summary={"rule_id": "RANGED_LETHAL_ZONE_1"},
                )
            )

    async def test_resolved_incident_does_not_block_a_new_one_for_same_track(
        self, db_session
    ) -> None:
        camera = await _make_camera(db_session)
        repo = IncidentRepository(db_session)
        await repo.add(
            Incident(
                camera_id=camera.id,
                track_id=7,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.RESOLVED,
                threat_summary={},
            )
        )

        # A resolved incident is terminal -- a new active one for the same
        # track must be allowed (docs/INCIDENT_LIFECYCLE.md).
        new_incident = await repo.add(
            Incident(
                camera_id=camera.id,
                track_id=7,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )

        assert new_incident.id is not None

    async def test_different_tracks_do_not_collide(self, db_session) -> None:
        camera = await _make_camera(db_session)
        repo = IncidentRepository(db_session)
        await repo.add(
            Incident(
                camera_id=camera.id,
                track_id=1,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )

        other = await repo.add(
            Incident(
                camera_id=camera.id,
                track_id=2,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )

        assert other.id is not None


@pytest.mark.asyncio
class TestIncidentEvent:
    async def test_round_trips(self, db_session) -> None:
        camera = await _make_camera(db_session)
        incident = await IncidentRepository(db_session).add(
            Incident(
                camera_id=camera.id,
                track_id=1,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )

        event = await IncidentEventRepository(db_session).add(
            IncidentEvent(
                incident_id=incident.id,
                event_type="STATUS_CHANGED",
                event_payload={"old": "NEW", "new": "ACTIVE"},
            )
        )

        assert event.incident_id == incident.id


@pytest.mark.asyncio
class TestHumanReviewRepository:
    async def test_round_trips_with_default_status(self, db_session) -> None:
        camera = await _make_camera(db_session)
        item = await HumanReviewRepository(db_session).add(
            HumanReviewItem(camera_id=camera.id, track_id=9, reason="uniform_unknown")
        )

        assert item.status == "OPEN"

    async def test_invalid_status_rejected(self, db_session) -> None:
        camera = await _make_camera(db_session)
        item = HumanReviewItem(
            camera_id=camera.id, track_id=9, reason="uniform_unknown", status="NOT_REAL"
        )

        with pytest.raises(IntegrityError):
            await HumanReviewRepository(db_session).add(item)


@pytest.mark.asyncio
class TestRecordingAndSnapshotRepositories:
    async def test_snapshot_round_trips(self, db_session) -> None:
        camera = await _make_camera(db_session)
        incident = await IncidentRepository(db_session).add(
            Incident(
                camera_id=camera.id,
                track_id=1,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )

        snapshot = await SnapshotRepository(db_session).add(
            Snapshot(
                incident_id=incident.id,
                camera_id=camera.id,
                file_path="/snapshots/cam-1/2026-07-20/evt.jpg",
                captured_at=datetime.now(tz=timezone.utc),
            )
        )

        assert snapshot.incident_id == incident.id

    async def test_recording_round_trips(self, db_session) -> None:
        camera = await _make_camera(db_session)
        incident = await IncidentRepository(db_session).add(
            Incident(
                camera_id=camera.id,
                track_id=1,
                incident_type=IncidentType.THREAT,
                threat_level=ThreatLevel.HIGH,
                status=IncidentStatus.NEW,
                threat_summary={},
            )
        )
        now = datetime.now(tz=timezone.utc)

        recording = await RecordingRepository(db_session).add(
            Recording(
                incident_id=incident.id,
                camera_id=camera.id,
                file_path="/recordings/cam-1/2026-07-20/events/evt.mp4",
                start_time=now,
                end_time=now,
            )
        )

        assert recording.incident_id == incident.id


@pytest.mark.asyncio
class TestSystemEventRepository:
    async def test_round_trips(self, db_session) -> None:
        event = await SystemEventRepository(db_session).add(
            SystemEvent(
                event_type="CAMERA_DISCONNECTED", severity="WARNING", payload={"camera": "cam-1"}
            )
        )

        assert event.severity == "WARNING"

    async def test_invalid_severity_rejected(self, db_session) -> None:
        event = SystemEvent(event_type="X", severity="NOT_REAL", payload={})

        with pytest.raises(IntegrityError):
            await SystemEventRepository(db_session).add(event)


@pytest.mark.asyncio
class TestUserRepository:
    async def test_round_trips(self, db_session) -> None:
        user = await UserRepository(db_session).add(
            User(username="operator1", password_hash="not-a-real-hash", role="operator")
        )

        assert user.username == "operator1"

    async def test_duplicate_username_rejected(self, db_session) -> None:
        await UserRepository(db_session).add(
            User(username="operator2", password_hash="hash1", role="operator")
        )

        with pytest.raises(IntegrityError):
            await UserRepository(db_session).add(
                User(username="operator2", password_hash="hash2", role="operator")
            )


@pytest.mark.asyncio
class TestAuditLogRepository:
    async def test_round_trips(self, db_session) -> None:
        user = await UserRepository(db_session).add(
            User(username="operator3", password_hash="not-a-real-hash", role="operator")
        )

        entry = await AuditLogRepository(db_session).add(
            AuditLog(
                actor_user_id=user.id,
                action="CONFIRM_MILITARY",
                resource_type="human_review_item",
                resource_id=str(user.id),
                details={"note": "confirmed via test"},
            )
        )

        assert entry.actor_user_id == user.id
        assert entry.details == {"note": "confirmed via test"}

    async def test_actor_user_id_is_nullable_for_system_generated_actions(self, db_session) -> None:
        entry = await AuditLogRepository(db_session).add(
            AuditLog(
                actor_user_id=None,
                action="AUTO_RESOLVE",
                resource_type="incident",
                resource_id="00000000-0000-0000-0000-000000000000",
                details={},
            )
        )

        assert entry.actor_user_id is None
