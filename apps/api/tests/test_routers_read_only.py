"""Tests for the Phase 3 read-only routers -- RM-12
(cameras, threats, incidents, reviews, calibration, evidence, analytics).

Router-level (real ``create_app()``, real DB), matching test_router_auth.py's
established pattern: seeded rows must be committed (not just flushed) --
``create_app()`` opens its own DB engine/connection, separate from the
``db_session`` fixture's.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.main import create_app
from apps.api.app.models.camera import Camera, CameraCalibration
from apps.api.app.models.human_review import HumanReviewItem
from apps.api.app.models.incident import Incident, IncidentEvent
from apps.api.app.models.recording import Recording, Snapshot
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel


async def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _make_camera(session: AsyncSession, **overrides) -> Camera:
    camera = Camera(name="cam-1", location="north gate", status="CONNECTED", **overrides)
    session.add(camera)
    await session.commit()
    return camera


async def _make_incident(session: AsyncSession, camera: Camera, **overrides) -> Incident:
    incident = Incident(
        camera_id=camera.id,
        track_id=1,
        incident_type=IncidentType.THREAT,
        threat_level=ThreatLevel.HIGH,
        status=IncidentStatus.NEW,
        threat_summary={"rule_id": "RANGED_LETHAL_ZONE_1"},
        **overrides,
    )
    session.add(incident)
    await session.commit()
    return incident


@pytest.mark.asyncio
class TestCamerasRouterReadOnly:
    async def test_requires_authentication(self, db_engine, db_session) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/cameras")
        assert response.status_code == 401

    async def test_list_returns_seeded_cameras(self, db_engine, db_session, auth_header) -> None:
        await _make_camera(db_session)
        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/cameras", headers=auth_header)
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 1
        assert body["data"][0]["name"] == "cam-1"

    async def test_get_by_id_returns_404_when_missing(
        self, db_engine, db_session, auth_header
    ) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.get(
                "/cameras/00000000-0000-0000-0000-000000000000", headers=auth_header
            )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    async def test_calibration_round_trips(self, db_engine, db_session, auth_header) -> None:
        camera = await _make_camera(db_session)
        db_session.add(
            CameraCalibration(
                camera_id=camera.id,
                homography_matrix={"m": [[1, 0], [0, 1]]},
                reference_points={"p": [[0, 0]]},
                calibrated_by="installer-1",
            )
        )
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            response = await client.get(f"/cameras/{camera.id}/calibration", headers=auth_header)

        assert response.status_code == 200
        assert response.json()["data"]["calibrated_by"] == "installer-1"

    async def test_calibration_returns_404_when_none_recorded(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        app = create_app()
        async with await _client(app) as client:
            response = await client.get(f"/cameras/{camera.id}/calibration", headers=auth_header)
        assert response.status_code == 404


@pytest.mark.asyncio
class TestThreatsRouterReadOnly:
    async def test_active_threats_is_honestly_empty_until_fed(
        self, db_engine, db_session, auth_header
    ) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/threats/active", headers=auth_header)
        assert response.status_code == 200
        assert response.json()["data"] == []


@pytest.mark.asyncio
class TestIncidentsRouterReadOnly:
    async def test_list_and_get(self, db_engine, db_session, auth_header) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)

        app = create_app()
        async with await _client(app) as client:
            list_response = await client.get("/incidents", headers=auth_header)
            get_response = await client.get(f"/incidents/{incident.id}", headers=auth_header)

        assert list_response.status_code == 200
        assert len(list_response.json()["data"]) == 1
        assert get_response.status_code == 200
        assert get_response.json()["data"]["threat_level"] == "HIGH"

    async def test_open_only_returns_active_statuses(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        await _make_incident(db_session, camera, track_id=1, status=IncidentStatus.ACTIVE)
        await _make_incident(db_session, camera, track_id=2, status=IncidentStatus.RESOLVED)

        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/incidents/open", headers=auth_header)

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_events_round_trip_and_404_for_missing_incident(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)
        db_session.add(
            IncidentEvent(
                incident_id=incident.id,
                event_type="STATUS_CHANGED",
                event_payload={"old": "NEW", "new": "ACTIVE"},
            )
        )
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            ok_response = await client.get(f"/incidents/{incident.id}/events", headers=auth_header)
            missing_response = await client.get(
                "/incidents/00000000-0000-0000-0000-000000000000/events", headers=auth_header
            )

        assert ok_response.status_code == 200
        assert len(ok_response.json()["data"]) == 1
        assert ok_response.json()["data"][0]["event_type"] == "STATUS_CHANGED"
        assert missing_response.status_code == 404

    async def test_evidence_combines_snapshots_and_recordings(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)
        now = datetime.now(tz=timezone.utc)
        db_session.add(
            Snapshot(
                incident_id=incident.id,
                camera_id=camera.id,
                file_path="/snapshots/does-not-exist.jpg",
                captured_at=now,
            )
        )
        db_session.add(
            Recording(
                incident_id=incident.id,
                camera_id=camera.id,
                file_path="/recordings/does-not-exist.mp4",
                start_time=now,
                end_time=now,
            )
        )
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            response = await client.get(f"/incidents/{incident.id}/evidence", headers=auth_header)

        assert response.status_code == 200
        types = {item["evidence_type"] for item in response.json()["data"]}
        assert types == {"snapshot", "recording"}


@pytest.mark.asyncio
class TestReviewsRouterReadOnly:
    async def test_list_and_get(self, db_engine, db_session, auth_header) -> None:
        camera = await _make_camera(db_session)
        db_session.add(HumanReviewItem(camera_id=camera.id, track_id=9, reason="uniform_unknown"))
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            response = await client.get("/reviews", headers=auth_header)

        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        assert response.json()["data"][0]["status"] == "OPEN"

    async def test_get_returns_404_when_missing(self, db_engine, db_session, auth_header) -> None:
        app = create_app()
        async with await _client(app) as client:
            response = await client.get(
                "/reviews/00000000-0000-0000-0000-000000000000", headers=auth_header
            )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestCalibrationRouterReadOnly:
    async def test_cameras_and_results_and_detail(self, db_engine, db_session, auth_header) -> None:
        camera = await _make_camera(db_session)
        db_session.add(
            CameraCalibration(
                camera_id=camera.id,
                homography_matrix={"m": [[1, 0], [0, 1]]},
                reference_points={"p": [[0, 0]]},
            )
        )
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            cameras_response = await client.get("/calibration/cameras", headers=auth_header)
            results_response = await client.get("/calibration/results", headers=auth_header)
            detail_response = await client.get(f"/calibration/{camera.id}", headers=auth_header)

        assert cameras_response.status_code == 200
        assert len(cameras_response.json()["data"]) == 1
        assert results_response.status_code == 200
        assert len(results_response.json()["data"]) == 1
        assert detail_response.status_code == 200
        assert detail_response.json()["data"]["camera_id"] == str(camera.id)


@pytest.mark.asyncio
class TestEvidenceRouterReadOnly:
    async def test_evidence_resolves_across_both_tables(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)
        now = datetime.now(tz=timezone.utc)
        snapshot = Snapshot(
            incident_id=incident.id,
            camera_id=camera.id,
            file_path="/snapshots/does-not-exist.jpg",
            captured_at=now,
        )
        recording = Recording(
            incident_id=incident.id,
            camera_id=camera.id,
            file_path="/recordings/does-not-exist.mp4",
            start_time=now,
            end_time=now,
        )
        db_session.add_all([snapshot, recording])
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            snap_response = await client.get(f"/evidence/{snapshot.id}", headers=auth_header)
            rec_response = await client.get(f"/evidence/{recording.id}", headers=auth_header)
            missing_response = await client.get(
                "/evidence/00000000-0000-0000-0000-000000000000", headers=auth_header
            )

        assert snap_response.json()["data"]["evidence_type"] == "snapshot"
        assert rec_response.json()["data"]["evidence_type"] == "recording"
        assert missing_response.status_code == 404

    async def test_download_returns_404_when_file_missing_on_disk(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        incident = await _make_incident(db_session, camera)
        now = datetime.now(tz=timezone.utc)
        recording = Recording(
            incident_id=incident.id,
            camera_id=camera.id,
            file_path="/recordings/does-not-exist.mp4",
            start_time=now,
            end_time=now,
        )
        db_session.add(recording)
        await db_session.commit()

        app = create_app()
        async with await _client(app) as client:
            response = await client.get(f"/recordings/{recording.id}/download", headers=auth_header)

        assert response.status_code == 404


@pytest.mark.asyncio
class TestAnalyticsRouterReadOnly:
    async def test_all_four_endpoints_return_the_documented_shape(
        self, db_engine, db_session, auth_header
    ) -> None:
        camera = await _make_camera(db_session)
        await _make_incident(db_session, camera)

        app = create_app()
        async with await _client(app) as client:
            threats = await client.get("/analytics/threats", headers=auth_header)
            incidents = await client.get("/analytics/incidents", headers=auth_header)
            cameras = await client.get("/analytics/cameras", headers=auth_header)
            system = await client.get("/analytics/system", headers=auth_header)

        assert threats.json()["data"]["counts_by_threat_level"] == {"HIGH": 1}
        assert incidents.json()["data"]["total"] == 1
        assert cameras.json()["data"]["total_cameras"] == 1
        assert system.json()["data"]["total_incidents"] == 1
