"""Tests for scripts/siv_register_camera.py -- RM-11.SIV Decision A.

DB-backed (register_camera() manages its own engine/session against the
same settings the db_engine/db_session fixtures use) -- skips without
reachable PostgreSQL, same as every other DB-dependent test in this repo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from apps.api.app.config import Settings
from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.security.encryption import get_credential_encryption_provider
from apps.deepstream.app.env_yaml import MissingEnvironmentVariableError
from scripts.siv_register_camera import register_camera


def _write_camera_yaml(path: Path, **overrides) -> Path:
    data = {
        "camera_id": "test-cam-01",
        "friendly_name": "Test Camera",
        "rtsp_url": "rtsp://192.168.1.50:554/stream1",
        "username": "operator",
        "password": "s3cret",
        "transport": "tcp",
        **overrides,
    }
    camera_yaml = path / "camera.yaml"
    camera_yaml.write_text(yaml.safe_dump(data), encoding="utf-8")
    return camera_yaml


@pytest.mark.asyncio
class TestRegisterCamera:
    async def test_creates_camera_and_profile_when_none_exist(
        self,
        db_engine: AsyncEngine,
        db_session: AsyncSession,
        tmp_path: Path,
        test_settings: Settings,
    ) -> None:
        camera_yaml = _write_camera_yaml(tmp_path)

        await register_camera(camera_yaml, settings=test_settings)

        camera_result = await db_session.execute(select(Camera).where(Camera.name == "test-cam-01"))
        camera = camera_result.scalar_one()
        assert camera.status == "DISCONNECTED"

        profile_result = await db_session.execute(
            select(CameraStreamProfile).where(CameraStreamProfile.camera_id == camera.id)
        )
        profile = profile_result.scalar_one()
        assert profile.transport == "tcp"

        encryption = get_credential_encryption_provider(test_settings)
        decrypted = encryption.decrypt(profile.rtsp_url_encrypted)
        assert decrypted == "rtsp://operator:s3cret@192.168.1.50:554/stream1"

    async def test_rerun_updates_existing_profile_instead_of_duplicating(
        self,
        db_engine: AsyncEngine,
        db_session: AsyncSession,
        tmp_path: Path,
        test_settings: Settings,
    ) -> None:
        first_yaml = _write_camera_yaml(tmp_path)
        await register_camera(first_yaml, settings=test_settings)

        second_yaml = _write_camera_yaml(tmp_path, rtsp_url="rtsp://10.0.0.5:554/stream2")
        await register_camera(second_yaml, settings=test_settings)

        cameras = (await db_session.execute(select(Camera))).scalars().all()
        assert len(cameras) == 1

        profiles = (await db_session.execute(select(CameraStreamProfile))).scalars().all()
        assert len(profiles) == 1

        encryption = get_credential_encryption_provider(test_settings)
        decrypted = encryption.decrypt(profiles[0].rtsp_url_encrypted)
        assert decrypted == "rtsp://operator:s3cret@10.0.0.5:554/stream2"

    async def test_missing_env_var_raises_before_touching_the_database(
        self, db_engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("RADAR_CAMERA_PASSWORD", raising=False)
        camera_yaml = _write_camera_yaml(tmp_path, password="${RADAR_CAMERA_PASSWORD}")

        with pytest.raises(MissingEnvironmentVariableError):
            await register_camera(camera_yaml)
