"""Tests for apps.deepstream.app.desired_state.DesiredStateReader.

Requires real PostgreSQL (RM-03's testing policy, no SQLite substitution) --
skips if unreachable, via this package's conftest.py fixtures. Uses the
``session_factory`` fixture (not ``db_session``) since ``DesiredStateReader``
opens its own short-lived session per ``read_all()`` call, matching
``ThreatEngineRuntimeAdapter``'s established pattern.

ADR-028: connection info comes from ``camera_media_endpoints``
(subsystem="ingestion" -- the row Camera Ingestion publishes once it holds
a camera's stream), never ``camera_stream_profiles`` directly -- AI Runtime
must never connect to the physical camera itself.
"""

from __future__ import annotations

import pytest

from apps.api.app.models.camera import Camera
from apps.api.app.repositories.camera import CameraRepository
from apps.api.app.repositories.media import CameraMediaEndpointRepository
from apps.deepstream.app.desired_state import DesiredStateReader


async def _make_camera(
    session,
    *,
    name: str = "cam-1",
    ai_enabled: bool = False,
    recording_enabled: bool = False,
) -> Camera:
    return await CameraRepository(session).add(
        Camera(
            name=name,
            status="DISCONNECTED",
            ai_enabled=ai_enabled,
            recording_enabled=recording_enabled,
        )
    )


@pytest.mark.asyncio
class TestReadAll:
    async def test_camera_without_published_endpoint_has_no_connection_info(
        self, db_session, session_factory
    ) -> None:
        await _make_camera(db_session)
        await db_session.commit()

        states = await DesiredStateReader(session_factory).read_all()

        assert len(states) == 1
        assert states[0].rtsp_url is None
        assert states[0].transport is None

    async def test_camera_with_published_ingestion_endpoint_has_connection_info(
        self, db_session, session_factory
    ) -> None:
        camera = await _make_camera(db_session, name="gate-camera", ai_enabled=True)
        local_url = f"rtsp://127.0.0.1:8600/{camera.id}"
        await CameraMediaEndpointRepository(db_session).set_endpoint(
            camera.id, "ingestion", transport="tcp", address=local_url
        )
        await db_session.commit()

        states = await DesiredStateReader(session_factory).read_all()

        assert len(states) == 1
        state = states[0]
        assert state.camera_id == camera.id
        assert state.name == "gate-camera"
        assert state.ai_enabled is True
        assert state.rtsp_url == local_url
        assert state.transport == "tcp"

    async def test_ignores_endpoints_from_other_subsystems(
        self, db_session, session_factory
    ) -> None:
        """A published "ai" (annotated-media) endpoint must never be
        mistaken for the "ingestion" one AI Runtime is meant to subscribe
        to -- it would be this same process's own future output."""
        camera = await _make_camera(db_session)
        await CameraMediaEndpointRepository(db_session).set_endpoint(
            camera.id, "ai", transport="rtsp", address="rtsp://127.0.0.1:8601/other"
        )
        await db_session.commit()

        states = await DesiredStateReader(session_factory).read_all()

        assert len(states) == 1
        assert states[0].rtsp_url is None
        assert states[0].transport is None

    async def test_reads_current_desired_state_fields(self, db_session, session_factory) -> None:
        await _make_camera(
            db_session,
            ai_enabled=False,
            recording_enabled=True,
        )
        await db_session.commit()

        states = await DesiredStateReader(session_factory).read_all()

        assert len(states) == 1
        assert states[0].ai_enabled is False
        assert states[0].recording_enabled is True

    async def test_each_call_sees_current_data_not_a_stale_snapshot(
        self, db_session, session_factory
    ) -> None:
        camera = await _make_camera(db_session, ai_enabled=False)
        await db_session.commit()
        reader = DesiredStateReader(session_factory)

        first = await reader.read_all()
        assert first[0].ai_enabled is False

        camera.ai_enabled = True
        await db_session.commit()

        second = await reader.read_all()
        assert second[0].ai_enabled is True

    async def test_no_cameras_returns_empty_list(self, session_factory) -> None:
        states = await DesiredStateReader(session_factory).read_all()

        assert states == []
