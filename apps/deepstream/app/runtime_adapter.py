"""Runtime Adapter -- Phase 0 scope.

Source: RM-07/RM-09/RM-10 design notes, which already named this component
("the Threat Engine Runtime Adapter, deferred until RM-11") and the RM-11
design review, which confirmed it belongs here. Full scope (per-frame
Calibration/Threat Engine/Incident/Alarm wiring) is Phase 2 -- see
DEEPSTREAM_PIPELINE_SPEC.md's Implementation Order. Phase 0 only owns
camera connection-state transitions and the events DEEPSTREAM_PIPELINE_SPEC.md's
"Failure Handling" section assigns to camera/ingestion failures:
CameraDisconnectedEvent and SystemEvent.

All methods are ``async`` and must only ever be invoked on the application
asyncio loop -- GStreamer callbacks reach this class exclusively through
``AsyncBridge.schedule()`` (RM-11 design review, Decision A), never directly.
"""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from shared.events.bus import EventBus
from shared.events.payloads import CameraDisconnectedPayload, SystemEventPayload
from shared.events.types import CameraDisconnectedEvent, SystemEvent
from shared.schemas.camera import CameraConnectionStatus

logger = logging.getLogger(__name__)

_SOURCE_COMPONENT = "deepstream"
_DEFAULT_STATUS: CameraConnectionStatus = "DISCONNECTED"


class RuntimeAdapter:
    """Bridges DeepStream pipeline lifecycle events onto the internal event
    bus and tracks per-camera connection status for the heartbeat scheduler."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus
        self._status: dict[uuid.UUID, CameraConnectionStatus] = {}

    def status_for(self, camera_id: uuid.UUID) -> CameraConnectionStatus:
        """Synchronous, non-blocking read -- safe for HeartbeatScheduler's
        status_provider (called from the asyncio loop, same as everything
        else here; no cross-thread access)."""
        return self._status.get(camera_id, _DEFAULT_STATUS)

    async def on_camera_connected(self, camera_id: uuid.UUID) -> None:
        self._status[camera_id] = "CONNECTED"
        await self._bus.publish(
            SystemEvent(
                event_type="SystemEvent",
                source=_SOURCE_COMPONENT,
                payload=SystemEventPayload(
                    severity="INFO",
                    source_component=_SOURCE_COMPONENT,
                    message=f"Camera {camera_id} connected",
                ),
            )
        )

    async def on_camera_reconnecting(self, camera_id: uuid.UUID) -> None:
        self._status[camera_id] = "RECONNECTING"

    async def on_camera_disconnected(self, camera_id: uuid.UUID, reason: str) -> None:
        """DEEPSTREAM_PIPELINE_SPEC.md 'Failure Handling' -> 'Camera Failure':
        generate CameraDisconnectedEvent."""
        self._status[camera_id] = "DISCONNECTED"
        await self._bus.publish(
            CameraDisconnectedEvent(
                event_type="CameraDisconnectedEvent",
                source=_SOURCE_COMPONENT,
                payload=CameraDisconnectedPayload(camera_id=camera_id, reason=reason),
            )
        )

    async def on_pipeline_error(
        self, message: str, *, severity: Literal["ERROR", "CRITICAL"] = "ERROR"
    ) -> None:
        """Generic infrastructure failure not tied to one camera (e.g. a
        pipeline-level GStreamer error). Component-specific failures (model,
        calibration -- DEEPSTREAM_PIPELINE_SPEC.md's 'Failure Handling')
        arrive in Phase 1/2 once those stages exist."""
        logger.error("DeepStream pipeline error: %s", message)
        await self._bus.publish(
            SystemEvent(
                event_type="SystemEvent",
                source=_SOURCE_COMPONENT,
                payload=SystemEventPayload(
                    severity=severity,
                    source_component=_SOURCE_COMPONENT,
                    message=message,
                ),
            )
        )
