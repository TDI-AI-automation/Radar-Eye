"""Loads registered cameras and their RTSP connection config from the
database.

Reuses ``apps.api``'s persistence layer directly (``Camera``,
``CameraStreamProfile``, their repositories, and
``CredentialEncryptionProvider``) -- the same established
cross-subsystem pattern already used by ``services/calibration`` and
(today, pre-migration) ``apps/deepstream/app/ingestion/camera_registry.py``.
Deliberately a fresh module rather than importing that one: Camera
Ingestion must never import anything under ``apps.deepstream`` (ADR-028,
hard rule). Read-only: this service never writes Desired State.

No AI-eligibility filtering here at all -- every registered camera with
a stream profile is loaded, matching this service's own "always
ingest every registered camera" invariant.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import CredentialEncryptionProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CameraSource:
    """Everything Camera Ingestion needs to build one RTSP source bin."""

    camera_id: uuid.UUID
    name: str
    rtsp_url: str
    transport: str


class CameraRegistry:
    """Loads the current camera roster."""

    def __init__(self, session: AsyncSession, encryption: CredentialEncryptionProvider) -> None:
        self._cameras = CameraRepository(session)
        self._profiles = CameraStreamProfileRepository(session)
        self._encryption = encryption

    async def load_camera_sources(self) -> list[CameraSource]:
        """Return one ``CameraSource`` per registered camera that has a
        stream profile. Cameras without a profile are skipped (logged)
        -- Camera Ingestion cannot ingest a camera it has no RTSP
        connection details for."""
        cameras = await self._cameras.list()
        profiles = await self._profiles.list()
        profile_by_camera_id = {profile.camera_id: profile for profile in profiles}

        sources: list[CameraSource] = []
        for camera in cameras:
            profile = profile_by_camera_id.get(camera.id)
            if profile is None:
                logger.warning(
                    "Camera %s (%s) has no camera_stream_profiles row -- skipping",
                    camera.id,
                    camera.name,
                )
                continue
            sources.append(
                CameraSource(
                    camera_id=camera.id,
                    name=camera.name,
                    rtsp_url=self._encryption.decrypt(profile.rtsp_url_encrypted),
                    transport=profile.transport,
                )
            )
        return sources
