"""Tests for apps.deepstream.app.desired_state.DesiredStateReader.

Requires real PostgreSQL (RM-03's testing policy, no SQLite substitution) --
skips if unreachable, via this package's conftest.py fixtures. Uses the
``session_factory`` fixture (not ``db_session``) since ``DesiredStateReader``
opens its own short-lived session per ``read_all()`` call, matching
``ThreatEngineRuntimeAdapter``'s established pattern.
"""

from __future__ import annotations

import pytest

from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import FernetCredentialEncryptionProvider
from apps.deepstream.app.desired_state import DesiredStateReader

_TEST_KEY = "CLrFKStOGSTRHci9yIv1kJV-SxMwWNDHzUiSWl3C3jA="


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
    async def test_camera_without_stream_profile_has_no_connection_info(
        self, db_session, session_factory
    ) -> None:
        await _make_camera(db_session)
        await db_session.commit()
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)

        states = await DesiredStateReader(session_factory, encryption).read_all()

        assert len(states) == 1
        assert states[0].rtsp_url is None
        assert states[0].transport is None

    async def test_camera_with_stream_profile_has_decrypted_connection_info(
        self, db_session, session_factory
    ) -> None:
        camera = await _make_camera(db_session, name="gate-camera", ai_enabled=True)
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)
        rtsp_url = "rtsp://192.0.2.10:554/stream1"
        await CameraStreamProfileRepository(db_session).add(
            CameraStreamProfile(
                camera_id=camera.id,
                rtsp_url_encrypted=encryption.encrypt(rtsp_url),
                transport="tcp",
            )
        )
        await db_session.commit()

        states = await DesiredStateReader(session_factory, encryption).read_all()

        assert len(states) == 1
        state = states[0]
        assert state.camera_id == camera.id
        assert state.name == "gate-camera"
        assert state.ai_enabled is True
        assert state.rtsp_url == rtsp_url
        assert state.transport == "tcp"

    async def test_reads_current_desired_state_fields(self, db_session, session_factory) -> None:
        await _make_camera(
            db_session,
            ai_enabled=False,
            recording_enabled=True,
        )
        await db_session.commit()
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)

        states = await DesiredStateReader(session_factory, encryption).read_all()

        assert len(states) == 1
        assert states[0].ai_enabled is False
        assert states[0].recording_enabled is True

    async def test_each_call_sees_current_data_not_a_stale_snapshot(
        self, db_session, session_factory
    ) -> None:
        camera = await _make_camera(db_session, ai_enabled=False)
        await db_session.commit()
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)
        reader = DesiredStateReader(session_factory, encryption)

        first = await reader.read_all()
        assert first[0].ai_enabled is False

        camera.ai_enabled = True
        await db_session.commit()

        second = await reader.read_all()
        assert second[0].ai_enabled is True

    async def test_no_cameras_returns_empty_list(self, session_factory) -> None:
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)

        states = await DesiredStateReader(session_factory, encryption).read_all()

        assert states == []
