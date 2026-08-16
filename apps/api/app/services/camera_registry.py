"""Camera Registry service -- RM-12 (Bounded Contexts §4 / Camera Runtime
Ownership Refinement).

Owns camera registration. A registered camera has exactly two operator
controls: AI Enable/Disable (``Camera.ai_enabled``) and Connect/
Disconnect, which is implicit in registration/deletion -- there is no
Lifecycle state machine here to transition through.

Does not own: connection status (``Camera.status``, Observed state -- see
``apps.api.app.models.camera.Camera``'s docstring) -- that column is never
written here, only read.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.repositories.camera import (
    CameraCalibrationRepository,
    CameraRepository,
    CameraStreamProfileRepository,
)
from apps.api.app.repositories.human_review import HumanReviewRepository
from apps.api.app.repositories.incident import IncidentEventRepository, IncidentRepository
from apps.api.app.repositories.media import (
    CameraMediaEndpointRepository,
    CameraSubsystemHealthRepository,
)
from apps.api.app.repositories.recording import RecordingRepository, SnapshotRepository
from apps.api.app.security.encryption import CredentialEncryptionProvider
from apps.api.app.services.rtsp_url_generator import (
    default_port_for_brand,
    default_stream_path_for_brand,
    generate_rtsp_url,
)
from shared.events.bus import EventBus
from shared.events.payloads import CameraRegisteredPayload
from shared.events.types import CameraRegisteredEvent
from shared.schemas.camera import CameraBrand


class CameraNameConflictError(Exception):
    """Raised when ``register()`` is given a name that already exists --
    translated to HTTP 409 by the router."""


class CameraRegistryService:
    def __init__(
        self,
        session: AsyncSession,
        encryption: CredentialEncryptionProvider,
        bus: EventBus | None = None,
    ) -> None:
        self._session = session
        self._cameras = CameraRepository(session)
        self._profiles = CameraStreamProfileRepository(session)
        self._calibrations = CameraCalibrationRepository(session)
        self._media_endpoints = CameraMediaEndpointRepository(session)
        self._subsystem_health = CameraSubsystemHealthRepository(session)
        self._incidents = IncidentRepository(session)
        self._incident_events = IncidentEventRepository(session)
        self._snapshots = SnapshotRepository(session)
        self._recordings = RecordingRepository(session)
        self._reviews = HumanReviewRepository(session)
        self._encryption = encryption
        self._bus = bus

    async def register(
        self,
        *,
        name: str,
        location: str | None,
        brand: CameraBrand,
        ip_address: str,
        port: int | None,
        stream_path: str | None,
        username: str | None,
        password: str | None,
        transport: str,
        model: str | None = None,
        ai_enabled: bool = False,
        recording_enabled: bool = False,
    ) -> Camera:
        """Create a new camera plus its stream profile, in one
        transaction. Raises CameraNameConflictError if
        ``name`` is already registered -- checked explicitly here (not left
        to the DB's unique constraint alone) so the router can return a
        precise 409 rather than a generic 500 on constraint violation.

        The operator never supplies an RTSP URL -- ``brand``/``ip_address``/
        ``port``/``stream_path``/``username``/``password`` go to
        ``apps.api.app.services.rtsp_url_generator.generate_rtsp_url()``;
        only the generated URL (and the individually-encrypted password)
        are ever stored.

        ``ai_enabled``/``recording_enabled`` are persisted as-given, purely
        as Desired state -- this method performs no AI/recording behavior
        and never calls Camera Runtime."""
        existing = await self._cameras.list()
        if any(c.name == name for c in existing):
            raise CameraNameConflictError(f"a camera named {name!r} is already registered")

        resolved_port = port if port is not None else default_port_for_brand(brand)
        resolved_stream_path = stream_path if stream_path else default_stream_path_for_brand(brand)
        url = generate_rtsp_url(
            brand=brand,
            ip_address=ip_address,
            port=resolved_port,
            username=username,
            password=password,
            stream_path=resolved_stream_path,
        )

        camera = await self._cameras.add(
            Camera(
                name=name,
                location=location,
                status="DISCONNECTED",
                ai_enabled=ai_enabled,
                recording_enabled=recording_enabled,
            )
        )
        await self._profiles.add(
            CameraStreamProfile(
                camera_id=camera.id,
                rtsp_url_encrypted=self._encryption.encrypt(url),
                transport=transport,
                brand=brand,
                model=model,
                ip_address=ip_address,
                port=resolved_port,
                stream_path=resolved_stream_path,
                username=username,
                password_encrypted=self._encryption.encrypt(password) if password else None,
            )
        )
        await self._publish(
            CameraRegisteredEvent(
                event_type="CameraRegisteredEvent",
                source="camera_registry",
                payload=CameraRegisteredPayload(camera_id=camera.id, name=camera.name),
            )
        )
        return camera

    async def update_connection(
        self,
        camera_id: uuid.UUID,
        *,
        brand: CameraBrand | None = None,
        model: str | None = None,
        ip_address: str | None = None,
        port: int | None = None,
        stream_path: str | None = None,
        username: str | None = None,
        password: str | None = None,
        transport: str | None = None,
    ) -> CameraStreamProfile | None:
        """Merges whichever connection fields are given with the camera's
        existing profile, regenerates and re-encrypts the RTSP URL, and
        persists it. Fields left as ``None`` keep their current value --
        including ``password``, which is write-only (never returned by any
        route), so an edit that only changes e.g. the IP must still be able
        to rebuild a working URL without the operator re-typing a password
        they can't see. Returns ``None`` (no-op) if this camera has no
        stream profile at all -- callers decide whether that's an error.
        """
        profile = await self._profiles.get_by_camera_id(camera_id)
        if profile is None:
            return None

        resolved_brand: CameraBrand = brand or profile.brand or "HIKVISION"  # type: ignore[assignment]
        resolved_ip = ip_address or profile.ip_address or ""
        resolved_port = port if port is not None else profile.port
        resolved_stream = stream_path or profile.stream_path
        resolved_username = username if username is not None else profile.username
        if password:
            resolved_password: str | None = password
        elif profile.password_encrypted:
            resolved_password = self._encryption.decrypt(profile.password_encrypted)
        else:
            resolved_password = None

        url = generate_rtsp_url(
            brand=resolved_brand,
            ip_address=resolved_ip,
            port=resolved_port,
            username=resolved_username,
            password=resolved_password,
            stream_path=resolved_stream,
        )

        profile.brand = resolved_brand
        profile.model = model if model is not None else profile.model
        profile.ip_address = resolved_ip
        profile.port = resolved_port
        profile.stream_path = resolved_stream
        profile.username = resolved_username
        if password:
            profile.password_encrypted = self._encryption.encrypt(password)
        profile.transport = transport or profile.transport
        profile.rtsp_url_encrypted = self._encryption.encrypt(url)
        await self._session.flush()
        return profile

    async def delete(self, camera: Camera) -> None:
        """Removes a camera and everything referencing it -- setup data
        (stream profile, calibration history, ADR-028 media-distribution
        bookkeeping) and, per explicit product decision (2026-08-10,
        overriding CLAUDE.md's original Evidence Preservation default),
        evidence too: incidents (with their events/snapshots/recordings)
        and human review items. Deletion is unconditional now -- an
        operator who wants a camera gone gets it gone, including its
        history; nothing raises 409 for this anymore.

        ``camera_media_endpoints``/``camera_subsystem_health`` (ADR-028)
        are ephemeral cross-process runtime bookkeeping (which endpoint is
        currently published, which subsystem last reported healthy),
        re-created automatically the moment a camera is re-registered --
        deleted here regardless, same reasoning as before.

        Camera Runtime picks this up for free: DesiredStateSynchronizer
        already removes a source whose camera_id no longer appears in
        Desired State at all (synchronization.py), which is exactly what
        deleting the row here produces -- no DeepStream-side change
        needed."""
        for incident in await self._incidents.list_by_camera(camera.id):
            for event in await self._incident_events.list_by_incident(incident.id):
                await self._incident_events.delete(event)
            for snapshot in await self._snapshots.list_by_incident(incident.id):
                await self._snapshots.delete(snapshot)
            for recording in await self._recordings.list_by_incident(incident.id):
                await self._recordings.delete(recording)
            await self._incidents.delete(incident)
        for review in await self._reviews.list_by_camera(camera.id):
            await self._reviews.delete(review)
        profile = await self._profiles.get_by_camera_id(camera.id)
        if profile is not None:
            await self._profiles.delete(profile)
        for calibration in await self._calibrations.list_for_camera(camera.id):
            await self._calibrations.delete(calibration)
        for endpoint in await self._media_endpoints.list_by_camera(camera.id):
            await self._media_endpoints.delete(endpoint)
        for health in await self._subsystem_health.list_by_camera(camera.id):
            await self._subsystem_health.delete(health)
        await self._cameras.delete(camera)

    async def _publish(self, event: CameraRegisteredEvent) -> None:
        if self._bus is None:
            return
        await self._bus.publish(event)
