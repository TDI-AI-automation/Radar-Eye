"""Desired State reading -- RM-12 Camera Runtime Step 4.

``DesiredStateReader`` is responsible only for reading Camera Registry's
Desired/Persistent state (``ai_enabled``, ``recording_enabled``) plus
enough connection info to build a source bin -- it decides nothing about
what Camera Runtime should then do with what it read (see
``synchronization.py``'s ``DesiredStateSynchronizer``). Read-only --
Camera Runtime never writes to Camera Registry's tables.

ADR-028 (Media Architecture Reset): AI Runtime is never a direct RTSP
consumer of the physical camera -- Camera Ingestion is the sole owner of
that connection. Connection info therefore comes from
``camera_media_endpoints`` (subsystem="ingestion", the row Camera
Ingestion itself publishes/upserts once it holds a camera's stream --
see ``apps/ingestion/app/runtime.py``), never from
``camera_stream_profiles`` directly, discovering its upstream through the
Media Distribution Interface rather than re-deriving the camera's own
credentials. No decryption is needed here: a published endpoint's
``address`` is a local loopback URL, not the camera's credentials.

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

from apps.api.app.repositories.camera import CameraRepository
from apps.api.app.repositories.media import CameraMediaEndpointRepository

_INGESTION_SUBSYSTEM = "ingestion"


@dataclass(frozen=True)
class DesiredCameraState:
    """One camera's Desired State snapshot, as Camera Registry currently
    records it. ``rtsp_url``/``transport`` are ``None`` when Camera
    Ingestion has not (yet) published an endpoint for this camera --
    AI Runtime has nothing to subscribe to until it does, and must never
    fall back to connecting the camera directly. A registered camera
    always wants an active source (Lifecycle, which used to gate this,
    has been removed entirely) -- ``DesiredStateSynchronizer`` no longer
    asks."""

    camera_id: uuid.UUID
    name: str
    ai_enabled: bool
    recording_enabled: bool
    rtsp_url: str | None
    transport: str | None


class DesiredStateReader:
    """Reads every registered camera's current Desired State."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def read_all(self) -> list[DesiredCameraState]:
        async with self._session_factory() as session:
            cameras = await CameraRepository(session).list()
            endpoints = await CameraMediaEndpointRepository(session).list_by_subsystem(
                _INGESTION_SUBSYSTEM
            )
            endpoint_by_camera_id = {endpoint.camera_id: endpoint for endpoint in endpoints}

            states: list[DesiredCameraState] = []
            for camera in cameras:
                endpoint = endpoint_by_camera_id.get(camera.id)
                states.append(
                    DesiredCameraState(
                        camera_id=camera.id,
                        name=camera.name,
                        ai_enabled=camera.ai_enabled,
                        recording_enabled=camera.recording_enabled,
                        rtsp_url=endpoint.address if endpoint is not None else None,
                        transport=endpoint.transport if endpoint is not None else None,
                    )
                )
            return states
