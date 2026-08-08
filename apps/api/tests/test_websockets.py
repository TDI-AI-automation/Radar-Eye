"""Tests for the RM-12 Phase 5 WebSocket bridge.

Greenfield WS test harness (docs/RM-12_ARCHITECTURE.md's Risks section --
no WebSocket test pattern existed in this repo before). Uses
``starlette.testclient.TestClient`` (the standard, Starlette-documented way
to test WebSocket routes) rather than the ``httpx.AsyncClient`` +
``ASGITransport`` pattern used elsewhere in this suite, since ``httpx`` has
no WebSocket support -- ``TestClient`` runs the ASGI app on its own
background thread/event loop via a blocking portal, so bus events are
published from a *separate* ``asyncio.run()`` call rather than an
``await`` inside the test itself; live-verified during implementation that
a plain, non-thread-safe ``asyncio.Queue.put()`` across that thread/loop
boundary works reliably for this single-publish-per-test usage.

No ``db_session``/``db_engine`` fixtures needed -- every published event
and its translation is database-free.

Since ADR-029 Phase 4, ``create_app()``'s event bus is ``ZmqEventBus``, not
``InProcessEventBus`` -- delivery is no longer same-process/in-memory, it
requires a real broker relaying between the app's own PUB and SUB sockets
(``shared.events.broker``, see that module's docstring). ``_broker``
(below) starts one real broker, once per test module, on the same fixed
ports every ``ZmqEventBus`` already connects to by default -- exactly the
production topology, not a mock.
"""

from __future__ import annotations

import asyncio
import threading
import time
import uuid
from collections.abc import Iterator

import pytest
from starlette.testclient import TestClient

from apps.api.app.config import Settings, get_settings
from apps.api.app.main import create_app
from apps.api.app.models.user import ROLE_OPERATOR
from apps.api.app.security.auth import create_token_pair
from shared.constants.distance_zones import DistanceZone
from shared.constants.incident_types import IncidentStatus, IncidentType
from shared.constants.threat_levels import ThreatLevel
from shared.constants.uniform_classes import UniformClass
from shared.constants.weapon_types import WeaponType
from shared.events.broker import run_broker
from shared.events.envelope import EventEnvelope
from shared.events.payloads import (
    AlarmRequestedPayload,
    CameraDisconnectedPayload,
    HumanReviewItemCreatedPayload,
    IncidentCreatedPayload,
    IncidentUpdatedPayload,
    SystemEventPayload,
    ThreatAssessmentPayload,
)

ACCEPTANCE_LATENCY_SECONDS = 2.0
"""docs/FRONTEND_BACKEND_CONTRACTS.md / RM-12_ARCHITECTURE.md §3.5's alert
latency acceptance criterion."""


@pytest.fixture(scope="module", autouse=True)
def _broker() -> Iterator[None]:
    """Every test in this module needs a real broker relaying its app's
    own ZmqEventBus publish/subscribe traffic -- see this module's
    docstring. A daemon thread is enough: it never outlives the test
    process, and this module never asserts anything about the broker's
    own lifecycle."""
    thread = threading.Thread(target=run_broker, daemon=True)
    thread.start()
    yield


def _token() -> str:
    return create_token_pair(
        user_id=uuid.uuid4(), role=ROLE_OPERATOR, settings=get_settings()
    ).access_token


def _publish(app, event: EventEnvelope) -> float:
    """Publishes ``event`` on the app's real event bus and returns the
    wall-clock time the publish call itself took (not receive time)."""
    start = time.monotonic()
    asyncio.run(app.state.event_bus.publish(event))
    return time.monotonic() - start


class TestWebSocketAuth:
    def test_missing_token_is_rejected(self, _default_env: None, test_settings: Settings) -> None:
        app = create_app(settings=test_settings)
        with TestClient(app) as client:
            try:
                with client.websocket_connect("/ws/threats"):
                    raise AssertionError("connection should have been rejected")
            except Exception:  # noqa: BLE001 -- WebSocketDisconnect, by design
                pass

    def test_invalid_token_is_rejected(self, _default_env: None, test_settings: Settings) -> None:
        app = create_app(settings=test_settings)
        with TestClient(app) as client:
            try:
                with client.websocket_connect("/ws/threats?token=not-a-real-token"):
                    raise AssertionError("connection should have been rejected")
            except Exception:  # noqa: BLE001 -- WebSocketDisconnect, by design
                pass


class TestThreatsChannel:
    def test_threat_assessment_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        camera_id = uuid.uuid4()
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/threats?token={_token()}") as ws:
                elapsed = _publish(
                    app,
                    EventEnvelope[ThreatAssessmentPayload](
                        event_type="ThreatAssessmentEvent",
                        source="test",
                        payload=ThreatAssessmentPayload(
                            camera_id=camera_id,
                            track_id=1,
                            weapon_type=WeaponType.RANGED_LETHAL,
                            uniform=UniformClass.CIVILIAN,
                            zone=DistanceZone.ZONE_1,
                            threat_level=ThreatLevel.HIGH,
                            rule_id="RANGED_LETHAL_ZONE_1",
                        ),
                    ),
                )
                message = ws.receive_json()

        assert elapsed < ACCEPTANCE_LATENCY_SECONDS
        assert message == {
            "camera_id": str(camera_id),
            "track_id": 1,
            "weapon_type": "ranged_lethal",
            "uniform": "civilian",
            "zone": "zone_1",
            "threat_level": "HIGH",
        }


class TestIncidentsChannel:
    def test_incident_created_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        incident_id, camera_id = uuid.uuid4(), uuid.uuid4()
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/incidents?token={_token()}") as ws:
                _publish(
                    app,
                    EventEnvelope[IncidentCreatedPayload](
                        event_type="IncidentCreatedEvent",
                        source="test",
                        payload=IncidentCreatedPayload(
                            incident_id=incident_id,
                            camera_id=camera_id,
                            track_id=1,
                            incident_type=IncidentType.THREAT,
                            threat_level=ThreatLevel.HIGH,
                            status=IncidentStatus.NEW,
                        ),
                    ),
                )
                message = ws.receive_json()

        assert message == {
            "incident_id": str(incident_id),
            "camera_id": str(camera_id),
            "track_id": 1,
            "status": "NEW",
        }

    def test_incident_updated_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        incident_id = uuid.uuid4()
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/incidents?token={_token()}") as ws:
                _publish(
                    app,
                    EventEnvelope[IncidentUpdatedPayload](
                        event_type="IncidentUpdatedEvent",
                        source="test",
                        payload=IncidentUpdatedPayload(
                            incident_id=incident_id,
                            old_status=IncidentStatus.NEW,
                            new_status=IncidentStatus.ACTIVE,
                        ),
                    ),
                )
                message = ws.receive_json()

        assert message == {
            "incident_id": str(incident_id),
            "old_status": "NEW",
            "new_status": "ACTIVE",
        }


class TestReviewsChannel:
    def test_human_review_item_created_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        review_item_id, camera_id = uuid.uuid4(), uuid.uuid4()
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/reviews?token={_token()}") as ws:
                _publish(
                    app,
                    EventEnvelope[HumanReviewItemCreatedPayload](
                        event_type="HumanReviewItemCreatedEvent",
                        source="test",
                        payload=HumanReviewItemCreatedPayload(
                            camera_id=camera_id,
                            track_id=1,
                            reason="uniform_unknown",
                            review_item_id=review_item_id,
                        ),
                    ),
                )
                message = ws.receive_json()

        assert message == {
            "review_item_id": str(review_item_id),
            "camera_id": str(camera_id),
            "track_id": 1,
            "reason": "uniform_unknown",
            "status": "OPEN",
        }


class TestAlarmsChannel:
    def test_alarm_requested_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        incident_id, camera_id = uuid.uuid4(), uuid.uuid4()
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/alarms?token={_token()}") as ws:
                _publish(
                    app,
                    EventEnvelope[AlarmRequestedPayload](
                        event_type="AlarmRequestedEvent",
                        source="test",
                        payload=AlarmRequestedPayload(
                            incident_id=incident_id,
                            camera_id=camera_id,
                            track_id=1,
                            threat_level=ThreatLevel.HIGH,
                            reason="sustained_high_threat",
                        ),
                    ),
                )
                message = ws.receive_json()

        assert message == {
            "incident_id": str(incident_id),
            "camera_id": str(camera_id),
            "threat_level": "HIGH",
        }


class TestCameraHealthChannel:
    def test_camera_disconnected_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        camera_id = uuid.uuid4()
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/camera-health?token={_token()}") as ws:
                _publish(
                    app,
                    EventEnvelope[CameraDisconnectedPayload](
                        event_type="CameraDisconnectedEvent",
                        source="test",
                        payload=CameraDisconnectedPayload(
                            camera_id=camera_id, reason="RTSP timeout"
                        ),
                    ),
                )
                message = ws.receive_json()

        assert message == {"camera_id": str(camera_id), "reason": "RTSP timeout"}

    def test_system_event_arrives_translated(
        self, _default_env: None, test_settings: Settings
    ) -> None:
        app = create_app(settings=test_settings)
        with TestClient(app) as client:
            with client.websocket_connect(f"/ws/camera-health?token={_token()}") as ws:
                _publish(
                    app,
                    EventEnvelope[SystemEventPayload](
                        event_type="SystemEvent",
                        source="test",
                        payload=SystemEventPayload(
                            severity="WARNING", source_component="deepstream", message="test"
                        ),
                    ),
                )
                message = ws.receive_json()

        assert message == {
            "severity": "WARNING",
            "source_component": "deepstream",
            "message": "test",
        }
