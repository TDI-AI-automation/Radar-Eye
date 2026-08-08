"""Tests for services.incident_service.main -- the Incident Service
process's own internal ObservationEvent/CalibrationUpdatedEvent handling
logic (ADR-029 Phase 4). No DB fixtures: CalibrationService/IncidentService
are monkeypatched out, since this module's own job is only to wire them
together correctly, not to re-test their already-covered business logic
(services/calibration, services/incident_service.service each have their
own test suites).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.calibration.types import CalibrationNotFoundError, DistanceEstimate
from services.incident_service import main as incident_main
from services.threat_engine.types import EscalationSignal, EscalationSignalType
from shared.constants.distance_zones import DistanceZone
from shared.constants.threat_levels import ThreatLevel
from shared.events.payloads import (
    BoundingBoxPayload,
    ObservationDetection,
    ObservationEventPayload,
)
from shared.events.types import ObservationEvent


def _make_detection(*, track_id: int | None) -> ObservationDetection:
    return ObservationDetection(
        detection_id=uuid.uuid4(),
        track_id=track_id,
        class_id=0,
        label="person",
        confidence=0.9,
        bbox=BoundingBoxPayload(left=0.1, top=0.1, width=0.2, height=0.3),
    )


def _make_observation_event(detections: list[ObservationDetection]) -> ObservationEvent:
    return ObservationEvent(
        event_type="ObservationEvent",
        source="ai_runtime",
        payload=ObservationEventPayload(
            observation_id=uuid.uuid4(),
            camera_id=uuid.uuid4(),
            frame_num=1,
            frame_timestamp=datetime.now(timezone.utc),
            detections=detections,
        ),
    )


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, *exc_info: object) -> bool:
        return False


def _make_session_factory():
    """Returns (session_factory, created_sessions) -- every call to
    session_factory() builds and records a brand-new fake session, so
    tests can assert no session/state leaks across events."""
    created: list[AsyncMock] = []

    def factory() -> _SessionContext:
        session = AsyncMock()
        created.append(session)
        return _SessionContext(session)

    return factory, created


@pytest.fixture
def patched_services(monkeypatch: pytest.MonkeyPatch):
    """Replaces CalibrationService/IncidentService (imported by name into
    services.incident_service.main) with fakes, and returns the fake
    IncidentService *instance* constructor sees, so tests can assert on
    handle_escalation calls."""
    calibration_instance = MagicMock()
    calibration_instance.estimate = AsyncMock(
        return_value=DistanceEstimate(distance_meters=12.0, zone=DistanceZone.ZONE_1)
    )
    calibration_cls = MagicMock(return_value=calibration_instance)
    monkeypatch.setattr(incident_main, "CalibrationService", calibration_cls)

    incident_instance = MagicMock()
    incident_instance.handle_escalation = AsyncMock()
    incident_cls = MagicMock(return_value=incident_instance)
    monkeypatch.setattr(incident_main, "IncidentService", incident_cls)

    return calibration_cls, calibration_instance, incident_cls, incident_instance


@pytest.mark.asyncio
async def test_untracked_detection_never_reaches_calibration_or_threat_engine(
    patched_services,
) -> None:
    _calibration_cls, calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()

    event = _make_observation_event([_make_detection(track_id=None)])
    await incident_main._handle_observation(
        event, session_factory=session_factory, threat_engine=threat_engine, bus=MagicMock()
    )

    calibration_instance.estimate.assert_not_called()
    threat_engine.ingest.assert_not_called()
    incident_instance.handle_escalation.assert_not_called()
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_calibration_miss_skips_detection_but_continues_the_event(patched_services) -> None:
    _calibration_cls, calibration_instance, _incident_cls, incident_instance = patched_services
    calibration_instance.estimate = AsyncMock(
        side_effect=CalibrationNotFoundError("no calibration")
    )
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event, session_factory=session_factory, threat_engine=threat_engine, bus=MagicMock()
    )

    threat_engine.ingest.assert_not_called()
    incident_instance.handle_escalation.assert_not_called()
    sessions[0].commit.assert_awaited_once()  # continues, doesn't abort/rollback the event


@pytest.mark.parametrize(
    "signal_type", [EscalationSignalType.INCIDENT_ELIGIBLE, EscalationSignalType.ALARM_ELIGIBLE]
)
@pytest.mark.asyncio
async def test_every_escalation_signal_type_routes_uniformly_to_handle_escalation(
    patched_services, signal_type: EscalationSignalType
) -> None:
    """Never inspects signal.signal_type -- INCIDENT_ELIGIBLE and
    ALARM_ELIGIBLE (and any future type) are forwarded identically. No
    AlarmService import/call exists anywhere in this module at all."""
    _calibration_cls, _calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    camera_id = uuid.uuid4()
    signal = EscalationSignal(
        camera_id=camera_id,
        track_id=7,
        signal_type=signal_type,
        threat_level=ThreatLevel.HIGH,
        reason="sustained_high_threat",
    )
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[signal])

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event, session_factory=session_factory, threat_engine=threat_engine, bus=MagicMock()
    )

    incident_instance.handle_escalation.assert_awaited_once()
    kwargs = incident_instance.handle_escalation.await_args.kwargs
    assert kwargs["camera_id"] == camera_id
    assert kwargs["track_id"] == 7
    assert kwargs["threat_level"] == ThreatLevel.HIGH
    assert kwargs["reason"] == "sustained_high_threat"
    sessions[0].commit.assert_awaited_once()
    assert "AlarmService" not in dir(incident_main)


@pytest.mark.asyncio
async def test_non_escalation_results_are_discarded_not_published(patched_services) -> None:
    _calibration_cls, _calibration_instance, _incident_cls, incident_instance = patched_services
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[MagicMock(name="ThreatAssessmentEvent-like")])
    bus = MagicMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    await incident_main._handle_observation(
        event, session_factory=session_factory, threat_engine=threat_engine, bus=bus
    )

    incident_instance.handle_escalation.assert_not_called()
    bus.publish.assert_not_called()
    sessions[0].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_each_call_opens_and_commits_its_own_independent_session(patched_services) -> None:
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()
    threat_engine.ingest = MagicMock(return_value=[])

    event = _make_observation_event([_make_detection(track_id=1)])
    await incident_main._handle_observation(
        event, session_factory=session_factory, threat_engine=threat_engine, bus=MagicMock()
    )
    await incident_main._handle_observation(
        event, session_factory=session_factory, threat_engine=threat_engine, bus=MagicMock()
    )

    assert len(sessions) == 2
    assert sessions[0] is not sessions[1]
    sessions[0].commit.assert_awaited_once()
    sessions[1].commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_mid_event_exception_rolls_back_and_propagates(patched_services) -> None:
    _calibration_cls, calibration_instance, _incident_cls, _incident_instance = patched_services
    calibration_instance.estimate = AsyncMock(side_effect=RuntimeError("unexpected failure"))
    session_factory, sessions = _make_session_factory()
    threat_engine = MagicMock()

    event = _make_observation_event([_make_detection(track_id=7)])
    with pytest.raises(RuntimeError, match="unexpected failure"):
        await incident_main._handle_observation(
            event, session_factory=session_factory, threat_engine=threat_engine, bus=MagicMock()
        )

    sessions[0].rollback.assert_awaited_once()
    sessions[0].commit.assert_not_called()


@pytest.mark.asyncio
async def test_calibration_updated_clears_the_calibration_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_cache = MagicMock()
    monkeypatch.setattr(incident_main.calibration_service_module, "clear_cache", clear_cache)

    await incident_main._handle_calibration_updated(MagicMock())

    clear_cache.assert_called_once_with()
