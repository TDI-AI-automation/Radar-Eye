"""EventBus -> WebSocket bridge -- RM-12 Phase 5 (docs/RM-12_ARCHITECTURE.md
§3.5).

One ``EventBus.subscribe()`` per event type, established once at app
startup (``WebSocketBridge.start()``, called from ``main.py``'s
``lifespan``) -- **not** per WebSocket connection. A single subscription's
handler translates the internal ``EventEnvelope[Payload]`` into the
matching frontend schema and broadcasts it to every currently-connected
client on that channel via ``ConnectionManager`` -- N connected clients on
one channel means one translation per event, not N.

Six of the seven ``/ws/*`` channels in docs/FRONTEND_BACKEND_CONTRACTS.md
are wired here: ``threats``, ``incidents``, ``camera_health``, ``reviews``,
``alarms``, ``alerts`` (the last added under ADR-029 Phase 6, Alert
Service). ``/ws/tracking`` is explicitly out of scope for RM-12
(docs/OPEN_QUESTIONS.md Q-015 -- no event model, payload, or publisher
exists for it anywhere in the codebase).

**Accepted limitation** (stated explicitly, per architecture §3.5):
``InProcessEventBus`` delivery is best-effort/at-most-once, in-process,
in-memory only -- a WebSocket client that is briefly disconnected misses
whatever published during the gap, and there is no durable log or replay.

**Process-topology note**: this bridge only ever receives events published
onto the *same* ``EventBus`` instance it was constructed with. Today,
``apps/api``'s ``create_app()`` and ``apps/deepstream``'s entrypoint
(``apps/deepstream/app/main.py``) each construct their own, independent
``InProcessEventBus()`` when run separately -- that module's own docstring
already documents that RM-14 (Jetson Deployment & Packaging) owns how the
single required OS process is actually composed (which module imports and
starts the other), a decision not yet made. Until that composition exists,
this bridge only observes events published from within its own process
(e.g. future in-process callers of ``IncidentService``/etc. inside
``apps/api``); wiring it to receive DeepStream/Threat-Engine/Incident-
Service events in production is RM-14's job, not invented here.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from apps.api.app.websockets.connection_manager import ConnectionManager
from shared.events.bus import EventBus
from shared.events.envelope import EventEnvelope
from shared.schemas.alarm import AlarmSchema
from shared.schemas.alert import AlertSchema
from shared.schemas.camera import CameraDisconnectedSchema, SystemEventSchema
from shared.schemas.incident import IncidentCreatedSchema, IncidentUpdatedSchema
from shared.schemas.review import HumanReviewSchema
from shared.schemas.threat import ThreatAssessmentSchema

Translator = Callable[[EventEnvelope], dict]


def _translate_threat_assessment(event: EventEnvelope) -> dict:
    p = event.payload
    return ThreatAssessmentSchema(
        camera_id=p.camera_id,
        track_id=p.track_id,
        weapon_type=p.weapon_type,
        uniform=p.uniform,
        zone=p.zone,
        threat_level=p.threat_level,
    ).model_dump(mode="json")


def _translate_incident_created(event: EventEnvelope) -> dict:
    p = event.payload
    return IncidentCreatedSchema(
        incident_id=p.incident_id, camera_id=p.camera_id, track_id=p.track_id, status=p.status
    ).model_dump(mode="json")


def _translate_incident_updated(event: EventEnvelope) -> dict:
    p = event.payload
    return IncidentUpdatedSchema(
        incident_id=p.incident_id, old_status=p.old_status, new_status=p.new_status
    ).model_dump(mode="json")


def _translate_review_created(event: EventEnvelope) -> dict:
    p = event.payload
    return HumanReviewSchema(
        review_item_id=p.review_item_id,
        camera_id=p.camera_id,
        track_id=p.track_id,
        reason=p.reason,
        created_at=event.timestamp,
    ).model_dump(mode="json")


def _translate_alarm_requested(event: EventEnvelope) -> dict:
    p = event.payload
    return AlarmSchema(
        incident_id=p.incident_id, camera_id=p.camera_id, threat_level=p.threat_level
    ).model_dump(mode="json")


def _translate_alert_raised(event: EventEnvelope) -> dict:
    p = event.payload
    return AlertSchema(
        alert_id=p.alert_id,
        incident_id=p.incident_id,
        camera_id=p.camera_id,
        severity=p.severity,
        channels=p.channels,
        deduplicated=p.deduplicated,
    ).model_dump(mode="json")


def _translate_camera_disconnected(event: EventEnvelope) -> dict:
    p = event.payload
    return CameraDisconnectedSchema(camera_id=p.camera_id, reason=p.reason).model_dump(mode="json")


def _translate_system_event(event: EventEnvelope) -> dict:
    p = event.payload
    return SystemEventSchema(
        severity=p.severity, source_component=p.source_component, message=p.message
    ).model_dump(mode="json")


_CHANNEL_BY_EVENT_TYPE: dict[str, str] = {
    "ThreatAssessmentEvent": "threats",
    "IncidentCreatedEvent": "incidents",
    "IncidentUpdatedEvent": "incidents",
    "HumanReviewItemCreatedEvent": "reviews",
    "AlarmRequestedEvent": "alarms",
    "AlertRaisedEvent": "alerts",
    "CameraDisconnectedEvent": "camera_health",
    "SystemEvent": "camera_health",
}

_TRANSLATOR_BY_EVENT_TYPE: dict[str, Translator] = {
    "ThreatAssessmentEvent": _translate_threat_assessment,
    "IncidentCreatedEvent": _translate_incident_created,
    "IncidentUpdatedEvent": _translate_incident_updated,
    "HumanReviewItemCreatedEvent": _translate_review_created,
    "AlarmRequestedEvent": _translate_alarm_requested,
    "AlertRaisedEvent": _translate_alert_raised,
    "CameraDisconnectedEvent": _translate_camera_disconnected,
    "SystemEvent": _translate_system_event,
}

CHANNELS: tuple[str, ...] = (
    "threats",
    "incidents",
    "camera_health",
    "reviews",
    "alarms",
    "alerts",
)


class WebSocketBridge:
    """Subscribes one handler per bus event type; each handler translates
    and broadcasts to that event type's WebSocket channel."""

    def __init__(self, bus: EventBus, connections: ConnectionManager) -> None:
        self._bus = bus
        self._connections = connections
        self._handlers: dict[str, Callable[[EventEnvelope], Awaitable[None]]] = {}

    async def start(self) -> None:
        for event_type, channel in _CHANNEL_BY_EVENT_TYPE.items():
            translate = _TRANSLATOR_BY_EVENT_TYPE[event_type]

            async def _handler(
                event: EventEnvelope, _channel: str = channel, _translate: Translator = translate
            ) -> None:
                await self._connections.broadcast(_channel, _translate(event))

            self._handlers[event_type] = _handler
            self._bus.subscribe(event_type, _handler, name=f"websocket_bridge:{event_type}")

    async def stop(self) -> None:
        for event_type, handler in self._handlers.items():
            await self._bus.unsubscribe(event_type, handler)
        self._handlers.clear()
