"""Tests for apps.deepstream.app.ingestion.camera_registry.CameraRegistry.

Requires real PostgreSQL (RM-03's testing policy, no SQLite substitution) --
skips if unreachable, via the db_session fixture in this package's
conftest.py.
"""

from __future__ import annotations

import pytest

from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import FernetCredentialEncryptionProvider
from apps.deepstream.app.ingestion.camera_registry import CameraRegistry

_TEST_KEY = "CLrFKStOGSTRHci9yIv1kJV-SxMwWNDHzUiSWl3C3jA="


async def _make_camera(session, *, name: str = "cam-1") -> Camera:
    return await CameraRepository(session).add(Camera(name=name, status="CONNECTED"))


@pytest.mark.asyncio
class TestLoadCameraSources:
    async def test_camera_without_stream_profile_is_skipped(self, db_session) -> None:
        await _make_camera(db_session)
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)
        registry = CameraRegistry(db_session, encryption)

        sources = await registry.load_camera_sources()

        assert sources == []

    async def test_camera_with_stream_profile_is_loaded_with_decrypted_url(
        self, db_session
    ) -> None:
        camera = await _make_camera(db_session, name="gate-camera")
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)
        rtsp_url = "rtsp://192.0.2.10:554/stream1"
        await CameraStreamProfileRepository(db_session).add(
            CameraStreamProfile(
                camera_id=camera.id,
                rtsp_url_encrypted=encryption.encrypt(rtsp_url),
                transport="tcp",
            )
        )

        sources = await CameraRegistry(db_session, encryption).load_camera_sources()

        assert len(sources) == 1
        source = sources[0]
        assert source.camera_id == camera.id
        assert source.name == "gate-camera"
        assert source.rtsp_url == rtsp_url
        assert source.transport == "tcp"

    async def test_loads_multiple_cameras(self, db_session) -> None:
        encryption = FernetCredentialEncryptionProvider(_TEST_KEY)
        profiles_repo = CameraStreamProfileRepository(db_session)

        camera_a = await _make_camera(db_session, name="cam-a")
        camera_b = await _make_camera(db_session, name="cam-b")
        for camera in (camera_a, camera_b):
            await profiles_repo.add(
                CameraStreamProfile(
                    camera_id=camera.id,
                    rtsp_url_encrypted=encryption.encrypt(f"rtsp://cam/{camera.name}"),
                    transport="tcp",
                )
            )

        sources = await CameraRegistry(db_session, encryption).load_camera_sources()

        assert {s.camera_id for s in sources} == {camera_a.id, camera_b.id}
