"""Desired State reading -- RM-12 Camera Runtime Step 4.

``DesiredStateReader`` is responsible only for reading Camera Registry's
Desired/Persistent state (``lifecycle_state``, ``ai_enabled``,
``recording_enabled``) plus enough connection info to build a source bin --
it decides nothing about what Camera Runtime should then do with what it
read (see ``synchronization.py``'s ``DesiredStateSynchronizer``). Read-only,
same convention as ``ingestion/camera_registry.py``'s ``CameraRegistry`` --
Camera Runtime never writes to Camera Registry's tables.

Deliberately not a long-lived session holder: each ``read_all()`` call opens
and closes its own short-lived session (matching ``runtime.py``'s existing
``async with self._session_factory() as session:`` pattern) so repeated
refreshes always see current data rather than a snapshot pinned to whenever
the reader was constructed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import CredentialEncryptionProvider
from shared.schemas.camera import CameraLifecycleState


@dataclass(frozen=True)
class DesiredCameraState:
    """One camera's Desired State snapshot, as Camera Registry currently
    records it. ``rtsp_url``/``transport`` are ``None`` when the camera has
    no ``camera_stream_profiles`` row yet -- mirrors
    ``CameraRegistry.load_camera_sources()``'s existing "skip, don't crash"
    handling of the same condition."""

    camera_id: uuid.UUID
    name: str
    lifecycle_state: CameraLifecycleState
    ai_enabled: bool
    recording_enabled: bool
    rtsp_url: str | None
    transport: str | None


class DesiredStateReader:
    """Reads every registered camera's current Desired State."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        encryption: CredentialEncryptionProvider,
    ) -> None:
        self._session_factory = session_factory
        self._encryption = encryption

    async def read_all(self) -> list[DesiredCameraState]:
        async with self._session_factory() as session:
            cameras = await CameraRepository(session).list()
            profiles = await CameraStreamProfileRepository(session).list()
            profile_by_camera_id = {profile.camera_id: profile for profile in profiles}

            states: list[DesiredCameraState] = []
            for camera in cameras:
                profile = profile_by_camera_id.get(camera.id)
                states.append(
                    DesiredCameraState(
                        camera_id=camera.id,
                        name=camera.name,
                        lifecycle_state=camera.lifecycle_state,  # type: ignore[arg-type]
                        ai_enabled=camera.ai_enabled,
                        recording_enabled=camera.recording_enabled,
                        rtsp_url=(
                            self._encryption.decrypt(profile.rtsp_url_encrypted)
                            if profile is not None
                            else None
                        ),
                        transport=profile.transport if profile is not None else None,
                    )
                )
            return states
