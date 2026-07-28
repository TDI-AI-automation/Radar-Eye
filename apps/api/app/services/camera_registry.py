"""Camera Registry service -- RM-12 (Bounded Contexts §4 / Camera Runtime
Ownership Refinement).

Owns camera registration and lifecycle-state transitions. Mirrors
``services.incident_service.service.IncidentService.request_transition()``'s
established shape exactly: a module-level transition table, a dedicated
exception, one entry point -- not a second, divergent pattern invented for
this domain.

Does not own: connection status (``Camera.status``, Observed state -- see
``apps.api.app.models.camera.Camera``'s docstring) -- that column is never
written here, only read.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models.camera import Camera, CameraStreamProfile
from apps.api.app.repositories.camera import CameraRepository, CameraStreamProfileRepository
from apps.api.app.security.encryption import CredentialEncryptionProvider
from shared.events.bus import EventBus
from shared.events.payloads import CameraLifecycleChangedPayload, CameraRegisteredPayload
from shared.events.types import CameraLifecycleChangedEvent, CameraRegisteredEvent
from shared.schemas.camera import CameraLifecycleState

LIFECYCLE_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"TESTING", "DISABLED"}),
    "TESTING": frozenset({"VERIFIED", "DRAFT", "DISABLED"}),
    "VERIFIED": frozenset({"OPERATIONAL", "DISABLED"}),
    "OPERATIONAL": frozenset({"MAINTENANCE", "DISABLED"}),
    "MAINTENANCE": frozenset({"OPERATIONAL", "DISABLED"}),
    "DISABLED": frozenset(),
}
"""RM-12 §10's Camera Lifecycle state machine, as data. ``DISABLED`` is
terminal for this transition path -- "removed/archived" is a separate,
not-yet-implemented concern (soft-delete), never a lifecycle transition
back out of DISABLED."""


class CameraLifecycleTransitionError(Exception):
    """Raised for any transition not present in LIFECYCLE_TRANSITIONS."""


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
        self._encryption = encryption
        self._bus = bus

    async def register(
        self,
        *,
        name: str,
        location: str | None,
        rtsp_url: str,
        username: str | None,
        password: str | None,
        transport: str,
        ai_enabled: bool = False,
        recording_enabled: bool = False,
    ) -> Camera:
        """Create a new camera (lifecycle_state=DRAFT) plus its stream
        profile, in one transaction. Raises CameraNameConflictError if
        ``name`` is already registered -- checked explicitly here (not left
        to the DB's unique constraint alone) so the router can return a
        precise 409 rather than a generic 500 on constraint violation.

        ``ai_enabled``/``recording_enabled`` are persisted as-given, purely
        as Desired state -- this method performs no AI/recording behavior
        and never calls Camera Runtime."""
        existing = await self._cameras.list()
        if any(c.name == name for c in existing):
            raise CameraNameConflictError(f"a camera named {name!r} is already registered")

        url = rtsp_url
        if username and password and "@" not in url:
            scheme, _, rest = url.partition("://")
            url = f"{scheme}://{username}:{password}@{rest}"

        camera = await self._cameras.add(
            Camera(
                name=name,
                location=location,
                status="DISCONNECTED",
                lifecycle_state="DRAFT",
                ai_enabled=ai_enabled,
                recording_enabled=recording_enabled,
            )
        )
        await self._profiles.add(
            CameraStreamProfile(
                camera_id=camera.id,
                rtsp_url_encrypted=self._encryption.encrypt(url),
                transport=transport,
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

    async def transition_lifecycle(
        self, camera: Camera, target_state: CameraLifecycleState
    ) -> Camera:
        """Single entry point for any lifecycle-state change. Idempotent:
        a request whose target already holds is a no-op that still returns
        200 with the current state (Implementation Precision Review,
        Finding 1) -- but does NOT re-publish CameraLifecycleChangedEvent
        in that case, since no state change actually occurred; the HTTP
        response itself is the redelivery's confirmation."""
        if camera.lifecycle_state == target_state:
            return camera

        allowed = LIFECYCLE_TRANSITIONS.get(camera.lifecycle_state, frozenset())
        if target_state not in allowed:
            raise CameraLifecycleTransitionError(
                f"Cannot transition camera {camera.id} from "
                f"{camera.lifecycle_state} to {target_state}"
            )

        previous_state = camera.lifecycle_state
        camera.lifecycle_state = target_state
        await self._session.flush()
        # updated_at is server-computed (onupdate=func.now()) -- an UPDATE's
        # onupdate value, unlike an INSERT's server_default, is not
        # auto-refreshed into the Python object; explicit refresh() is
        # required before _to_camera_schema() reads it back (same footgun
        # already documented/fixed once in routers/cameras.py's PATCH route).
        await self._session.refresh(camera)

        await self._publish(
            CameraLifecycleChangedEvent(
                event_type="CameraLifecycleChangedEvent",
                source="camera_registry",
                payload=CameraLifecycleChangedPayload(
                    camera_id=camera.id, previous_state=previous_state, new_state=target_state
                ),
            )
        )
        return camera

    async def _publish(self, event: CameraRegisteredEvent | CameraLifecycleChangedEvent) -> None:
        if self._bus is None:
            return
        await self._bus.publish(event)
