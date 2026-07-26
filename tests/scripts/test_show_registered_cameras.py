"""Tests for scripts/show_registered_cameras.py.

DB-backed -- skips without reachable PostgreSQL, same as every other
DB-dependent test in this repo. Pure-Python masking logic is tested
separately, without a database, in TestMaskRtspUrl.
"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.security.encryption import get_credential_encryption_provider
from scripts.show_registered_cameras import _mask_rtsp_url, show_registered_cameras


class TestMaskRtspUrl:
    def test_strips_embedded_credentials(self) -> None:
        assert _mask_rtsp_url("rtsp://operator:s3cret@192.168.1.50:554/stream1") == (
            "rtsp://192.168.1.50:554/stream1"
        )

    def test_no_credentials_unchanged_shape(self) -> None:
        assert _mask_rtsp_url("rtsp://192.168.1.50:554/stream1") == (
            "rtsp://192.168.1.50:554/stream1"
        )

    def test_unparseable_url_does_not_raise(self) -> None:
        assert _mask_rtsp_url("not a url :: at all") != ""


@pytest.mark.asyncio
class TestShowRegisteredCameras:
    async def test_lists_camera_with_masked_host(
        self, db_engine: AsyncEngine, db_session: AsyncSession
    ) -> None:
        from apps.api.app.config import get_settings

        camera = Camera(name="test-cam-01", status="DISCONNECTED")
        db_session.add(camera)
        await db_session.flush()

        encryption = get_credential_encryption_provider(get_settings())
        encrypted = encryption.encrypt("rtsp://operator:s3cret@192.168.1.50:554/stream1")
        db_session.add(
            CameraStreamProfile(camera_id=camera.id, rtsp_url_encrypted=encrypted, transport="tcp")
        )
        await db_session.commit()

        rows = await show_registered_cameras()

        row = next(r for r in rows if r["camera_id"] == str(camera.id))
        assert row["name"] == "test-cam-01"
        assert row["rtsp_host"] == "rtsp://192.168.1.50:554/stream1"
        assert "s3cret" not in row["rtsp_host"]
        assert "operator" not in row["rtsp_host"]
        assert row["transport"] == "tcp"

    async def test_camera_without_profile_shows_placeholder(
        self, db_engine: AsyncEngine, db_session: AsyncSession
    ) -> None:
        camera = Camera(name="no-profile-cam", status="DISCONNECTED")
        db_session.add(camera)
        await db_session.commit()

        rows = await show_registered_cameras()

        row = next(r for r in rows if r["camera_id"] == str(camera.id))
        assert row["rtsp_host"] == "<no stream profile>"
